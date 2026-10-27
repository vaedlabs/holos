"""Model prices, call costs and the period of each spend key (Plan C.12, C.13, Part E #13)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import limits
from app.data.state_store import SessionInfo
from app.orchestration import budget
from app.orchestration.principal import Principal
from app.providers.base import Usage

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 26, 13, 47, 5, tzinfo=UTC)


def guest(created=NOW - timedelta(minutes=30)) -> Principal:
    session = SessionInfo("h" * 64, "guest", None, "ipk-start", created,
                          created + limits.GUEST_SESSION_TTL)
    return Principal(session, "raw", "ipk-now")


def account() -> Principal:
    session = SessionInfo("a" * 64, "account", 7, "ipk-start", NOW, NOW + timedelta(days=7))
    return Principal(session, "raw", "ipk-now")


def test_a_luna_call_costs_its_tokens_at_list_price():
    usage = Usage(tokens_in=10_000, tokens_out=1_000, cached_tokens=4_000)
    # 6,000 × $0.10 + 4,000 × $0.01 + 1,000 × $0.50, per million
    assert budget.call_usd("gpt-6-luna", usage) == Decimal("0.00114")


def test_gemini_cached_tokens_are_never_cheaper_than_input():
    full = budget.call_usd("gemini-3.5-flash-lite", Usage(1000, 100))
    cached = budget.call_usd("gemini-3.5-flash-lite", Usage(1000, 100, cached_tokens=1000))
    assert full == cached == Decimal("0.00055")


def test_costs_round_up_to_the_millionth():
    # 1 token of luna input is $0.0000001: it still counts as $0.000001
    assert budget.call_usd("gpt-6-luna", Usage(1, 0)) == Decimal("0.000001")
    assert budget.call_usd("gpt-6-luna", Usage(0, 0)) == Decimal("0")


def test_more_cached_tokens_than_input_tokens_cannot_lower_the_cost():
    assert (budget.call_usd("gpt-6-luna", Usage(100, 0, cached_tokens=10**6))
            == budget.call_usd("gpt-6-luna", Usage(100, 0, cached_tokens=100)))


def test_the_reservation_covers_the_whole_output_limit():
    # Physical and Mental: 1,200 reply + 1,000 reasoning (C.9)
    assert budget.max_call_usd("gpt-6-luna", 3_000, 2_200) == Decimal("0.0014")
    reported = budget.call_usd("gpt-6-luna", Usage(3_000, 2_200))
    assert reported <= budget.max_call_usd("gpt-6-luna", 3_000, 2_200)


def test_a_model_without_a_price_is_refused():
    with pytest.raises(ValueError, match="no price"):
        budget.max_call_usd("gpt-7", 10, 10)


def test_periods():
    assert budget.day_start(NOW) == datetime(2026, 10, 26, tzinfo=UTC)
    assert budget.month_start(NOW) == datetime(2026, 10, 1, tzinfo=UTC)
    # 240-minute windows start at 00:00, 04:00, 08:00, 12:00 ... UTC
    assert budget.window_start(limits.GUEST_IP_WINDOW, NOW) == datetime(2026, 10, 26, 12,
                                                                        tzinfo=UTC)
    ist = NOW.astimezone(datetime.now().astimezone().tzinfo)  # any zone: the same instant
    assert budget.day_start(ist) == budget.day_start(NOW)


@pytest.mark.parametrize("billing_day, today, start", [
    (1, datetime(2026, 10, 26), datetime(2026, 10, 1)),
    (15, datetime(2026, 10, 26), datetime(2026, 10, 15)),
    (15, datetime(2026, 10, 15), datetime(2026, 10, 15)),
    (15, datetime(2026, 10, 14, 23, 59), datetime(2026, 9, 15)),
    (28, datetime(2026, 3, 1), datetime(2026, 2, 28)),
    (20, datetime(2027, 1, 5), datetime(2026, 12, 20)),  # across a year
])
def test_the_search_month_follows_tavilys_billing_day(billing_day, today, start):
    assert (budget.billing_month_start(billing_day, today.replace(tzinfo=UTC))
            == start.replace(tzinfo=UTC))


def test_a_guest_spends_against_its_session_its_ip_key_and_the_global_caps():
    me = guest()
    keys = budget.spend_keys(me, NOW)
    assert [(k.name, k.key, k.period, k.cap_usd) for k in keys] == [
        ("session", me.principal_key, "day", Decimal("0.05")),
        ("ip", "ip:ipk-now", "day", Decimal("0.30")),  # the hard stop, 3× $0.10
        ("global_day", "global", "day", Decimal("0.75")),
        ("global_month", "global", "month", Decimal("10")),
    ]
    # The session's row lives as long as the session; the IP key's is its 4-hour window
    assert keys[0].period_start == me.session.created_at
    assert keys[1].period_start == datetime(2026, 10, 26, 12, tzinfo=UTC)
    assert all(k.cap_credits is None for k in keys)


def test_a_session_started_before_midnight_keeps_one_row():
    me = guest(created=datetime(2026, 10, 25, 23, 0, tzinfo=UTC))
    after_midnight = datetime(2026, 10, 26, 1, 0, tzinfo=UTC)
    assert (budget.spend_keys(me, after_midnight)[0].period_start
            == budget.spend_keys(me, NOW.replace(day=25, hour=23, minute=30))[0].period_start)


def test_an_account_spends_per_utc_day():
    keys = budget.spend_keys(account(), NOW)
    assert [(k.name, k.key, k.period_start) for k in keys[:1]] == [
        ("account", "user:7", datetime(2026, 10, 26, tzinfo=UTC))]
    assert [k.name for k in keys] == ["account", "global_day", "global_month"]


def test_search_credit_caps():
    g = budget.search_keys(guest(), 15, NOW)
    assert [(k.name, k.key, k.cap_credits) for k in g] == [
        ("session", guest().principal_key, 5), ("ip", "ip:ipk-now", 10),
        ("global_day", "tavily", 40), ("global_month", "tavily", 800)]
    assert g[-1].period_start == datetime(2026, 10, 15, tzinfo=UTC)
    a = budget.search_keys(account(), 1, NOW)
    assert [(k.name, k.cap_credits) for k in a] == [
        ("account", 10), ("global_day", 40), ("global_month", 800)]
    assert all(k.cap_usd is None for k in g + a)


# --- When a full cap has room again (admission's Retry-After) ---


@pytest.mark.parametrize("now, name, seconds", [
    (datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC), "global_month", 1),  # year end
    (datetime(2026, 1, 31, 12, 0, tzinfo=UTC), "global_month", 12 * 3600),
    (datetime(2028, 2, 28, 0, 0, tzinfo=UTC), "global_month", 2 * 86400),  # leap year
    (datetime(2026, 10, 26, 23, 0, tzinfo=UTC), "global_day", 3600),
    (datetime(2026, 10, 26, 23, 0, tzinfo=UTC), "account", 3600),
    (datetime(2026, 10, 26, 15, 59, 59, tzinfo=UTC), "ip", 1),  # window ends at 16:00
    (datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC), "ip", 4 * 3600),
])
def test_retry_after_points_at_when_the_cap_resets(now, name, seconds):
    from app.orchestration.admission import _cap_retry_after

    got = _cap_retry_after(name, guest(created=now - timedelta(minutes=10)), now)
    assert seconds <= got <= seconds + 1  # rounded up, never 0


def test_a_session_cap_resets_when_the_session_ends():
    from app.orchestration.admission import _cap_retry_after

    me = guest(created=NOW - timedelta(minutes=200))
    assert 40 * 60 <= _cap_retry_after("session", me, NOW) <= 40 * 60 + 1
    expired = guest(created=NOW - timedelta(minutes=300))
    assert _cap_retry_after("session", expired, NOW) == 1  # never 0 or negative
