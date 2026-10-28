"""Spend and search credits: the keys a request counts against, model prices, and the
reservation around each LLM call (Plan C.12, C.13).

    keys = spend_keys(principal, now)                        # once, at admission
    held = await budget.reserve_call(keys, model, tokens_in, max_output_tokens)
    if held is None: ...                                      # a cap is reached: no call
    result = await provider.generate(...)
    await budget.settle_call(held, model, result.usage)      # or budget.cancel(held)

A reservation holds the most the call can cost (its input tokens and its whole output
limit), so calls running at the same time can't pass a cap together.

C.11 allows only `day` and `month` periods (Part E #13). A guest session's row is a
`day` row that starts when the session starts (it lives 240 minutes); a guest IP key's
row is a `day` row that starts at its 240-minute window. Those windows are aligned to
00:00 UTC, when the IP key's salt changes, so one row never spans two IP keys.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal

from app.config import limits
from app.data.state_store import Reservation, SpendKey, StateStore
from app.providers.base import GenerateOptions, Usage

from .principal import Principal

MILLION = Decimal(1_000_000)
USD_STEP = Decimal("0.000001")  # the spend table keeps 6 decimal places


@dataclass(frozen=True)
class Price:
    """USD per 1M tokens (Part D, 26 Oct 2026)."""

    input: Decimal
    cached_input: Decimal
    output: Decimal  # includes reasoning tokens


PRICES = {
    "gpt-6-luna": Price(Decimal("0.10"), Decimal("0.01"), Decimal("0.50")),
    # Gemini's cached price isn't recorded, so cached tokens cost full price: never too low
    "gemini-3.5-flash-lite": Price(Decimal("0.30"), Decimal("0.30"), Decimal("2.50")),
}


def _price(model: str) -> Price:
    try:
        return PRICES[model]
    except KeyError:
        # A model without a price can't be budgeted: fail loudly, never call it for free
        raise ValueError(f"no price for model {model!r}; add it to budget.PRICES") from None


def _usd(tokens: int, per_million: Decimal) -> Decimal:
    """Rounded up, so many small calls never add up to less than they cost."""
    return (Decimal(tokens) * per_million / MILLION).quantize(USD_STEP, rounding=ROUND_CEILING)


def max_call_usd(model: str, tokens_in: int, max_output_tokens: int) -> Decimal:
    """The most one call can cost: what is reserved before it runs."""
    price = _price(model)
    return _usd(tokens_in, price.input) + _usd(max_output_tokens, price.output)


def call_usd(model: str, usage: Usage) -> Decimal:
    """What a call cost, from the token counts the provider reported."""
    price = _price(model)
    cached = min(usage.cached_tokens, usage.tokens_in)
    return (_usd(usage.tokens_in - cached, price.input) + _usd(cached, price.cached_input)
            + _usd(usage.tokens_out, price.output))


# --- Periods ---


def _utc(now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)).astimezone(UTC)


def day_start(now: datetime | None = None) -> datetime:
    return _utc(now).replace(hour=0, minute=0, second=0, microsecond=0)


def month_start(now: datetime | None = None) -> datetime:
    return day_start(now).replace(day=1)


def window_start(window: timedelta, now: datetime | None = None) -> datetime:
    """Fixed windows aligned to the Unix epoch, as the rate counters use."""
    seconds = int(window.total_seconds())
    epoch = int(_utc(now).timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


def billing_month_start(billing_day: int, now: datetime | None = None) -> datetime:
    """The start of the current Tavily billing month (its credits reset on billing_day)."""
    today = day_start(now)
    if today.day >= billing_day:
        return today.replace(day=billing_day)
    last_month = today.replace(day=1) - timedelta(days=1)
    return last_month.replace(day=billing_day)


# --- Keys ---

GLOBAL_KEY = "global"  # USD for every model
SEARCH_KEY = "tavily"  # global search credits; its month follows Tavily's billing day


def ip_spend_key(ip_key: str, now: datetime | None = None) -> SpendKey:
    """A guest IP key's 240-minute row; the cap is the hard stop (3× the allowance)."""
    return SpendKey(f"ip:{ip_key}", "day", window_start(limits.GUEST_IP_WINDOW, now),
                    cap_usd=limits.GUEST_IP_USD * limits.GUEST_IP_HARD_STOP_FACTOR,
                    name="ip")


def spend_keys(principal: Principal, now: datetime | None = None) -> list[SpendKey]:
    """USD caps (C.12): the session or account, the guest's IP key, global day and month."""
    if principal.user_id is not None:
        own = SpendKey(principal.principal_key, "day", day_start(now),
                       cap_usd=limits.ACCOUNT_DAY_USD, name="account")
        keys = [own]
    else:
        own = SpendKey(principal.principal_key, "day", principal.session.created_at,
                       cap_usd=limits.GUEST_SESSION_USD, name="session")
        keys = [own, ip_spend_key(principal.ip_key, now)]
    return keys + [
        SpendKey(GLOBAL_KEY, "day", day_start(now), cap_usd=limits.GLOBAL_DAY_USD,
                 name="global_day"),
        SpendKey(GLOBAL_KEY, "month", month_start(now), cap_usd=limits.GLOBAL_MONTH_USD,
                 name="global_month"),
    ]


def search_keys(
    principal: Principal, billing_day: int, now: datetime | None = None
) -> list[SpendKey]:
    """Search credit caps (C.12). The per-request limit of 2 is the tool's own count."""
    if principal.user_id is not None:
        keys = [SpendKey(principal.principal_key, "day", day_start(now),
                         cap_credits=limits.SEARCHES_PER_ACCOUNT_DAY, name="account")]
    else:
        keys = [
            SpendKey(principal.principal_key, "day", principal.session.created_at,
                     cap_credits=limits.SEARCHES_PER_GUEST_SESSION, name="session"),
            SpendKey(f"ip:{principal.ip_key}", "day",
                     window_start(limits.GUEST_IP_WINDOW, now),
                     cap_credits=limits.SEARCHES_PER_GUEST_IP_WINDOW, name="ip"),
        ]
    return keys + [
        SpendKey(SEARCH_KEY, "day", day_start(now), cap_credits=limits.SEARCHES_GLOBAL_DAY,
                 name="global_day"),
        SpendKey(SEARCH_KEY, "month", billing_month_start(billing_day, now),
                 cap_credits=limits.SEARCHES_GLOBAL_MONTH, name="global_month"),
    ]


async def ip_window_usd(store: StateStore, ip_key: str) -> Decimal:
    """What a guest IP key has spent and reserved in its current 240-minute window."""
    key = ip_spend_key(ip_key)
    row = await store.spend(key.key, key.period, key.period_start)
    return (row["cost_usd"] + row["reserved_usd"]) if row else Decimal("0")


class Budget:
    """Reserve before each LLM call, settle after it (C.13)."""

    def __init__(self, store: StateStore):
        self._store = store

    async def reserve_call(
        self, keys: list[SpendKey], model: str, tokens_in: int, max_output_tokens: int
    ) -> Reservation | None:
        """None if any cap would be passed: the call must not run."""
        return await self._store.reserve(
            keys, usd=max_call_usd(model, tokens_in, max_output_tokens))

    async def settle_call(self, reservation: Reservation, model: str, usage: Usage) -> None:
        await self._store.settle(reservation, call_usd(model, usage),
                                 tokens_in=usage.tokens_in, tokens_out=usage.tokens_out)

    async def cancel(self, reservation: Reservation) -> None:
        """The call never ran, or wasn't billed (429, 5xx, a refused request)."""
        await self._store.cancel(reservation)

    async def keep(self, reservation: Reservation) -> None:
        """Usage unknown (timed out, cancelled, unparsable): spent at the reserved maximum."""
        await self._store.settle(reservation, reservation.usd)


class CallMeter:
    """One caller's LLM calls against its spend keys: the ResilientProvider's Meter.
    Every call, backups included, reserves its maximum first (C.13)."""

    def __init__(self, budget: Budget, keys: list[SpendKey], tokens_in: int):
        self._budget = budget
        self._keys = keys
        self._tokens_in = tokens_in

    async def reserve(self, options: GenerateOptions) -> Reservation | None:
        return await self._budget.reserve_call(self._keys, options.model, self._tokens_in,
                                               options.max_output_tokens)

    async def settle(self, hold: Reservation, options: GenerateOptions, usage: Usage) -> None:
        await self._budget.settle_call(hold, options.model, usage)

    async def keep(self, hold: Reservation) -> None:
        await self._budget.keep(hold)

    async def release(self, hold: Reservation) -> None:
        await self._budget.cancel(hold)
