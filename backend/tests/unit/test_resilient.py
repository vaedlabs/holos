"""ResilientProvider: retries, fallback and the circuit breaker (Plan P2.3). Fake clock."""

import pytest

from app.agents.schemas import MentalReply
from app.providers import (
    BadRequest,
    Breakers,
    FakeProvider,
    GenerateOptions,
    MalformedOutput,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ResilientProvider,
    Route,
    Turn,
)
from app.providers import resilient as rs
from app.providers.fake import reply

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

OK = reply(MentalReply(kind="answer", summary="ok", items=[], notes=[], source_ids=[],
                       follow_up=None, risk_flag=False))
MSG = [Turn("user", "hi")]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _make(primary_script, fallback_script=None, clock=None, breakers=None):
    clock = clock or Clock()
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)
        clock.now += seconds

    primary = FakeProvider(list(primary_script), name="openai")
    fallback = FakeProvider(list(fallback_script or []), name="gemini")
    opts = GenerateOptions(model="m", max_output_tokens=100)
    rp = ResilientProvider(
        Route(primary, opts),
        Route(fallback, GenerateOptions(model="fallback-m", max_output_tokens=100))
        if fallback_script is not None else None,
        breakers or Breakers(clock), sleep=sleep, jitter=lambda: 0.0,
    )
    return rp, primary, fallback, sleeps, clock


@pytest.mark.parametrize("error", [RateLimited("429"), ProviderUnavailable("503"),
                                   ProviderTimeout("timeout")])
async def test_retries_retryable_errors(error):
    rp, primary, _, sleeps, _ = _make([error, OK])
    assert (await rp.generate(MSG)).parsed == OK.parsed
    assert len(primary.calls) == 2 and len(sleeps) == 1


async def test_backoff_doubles_and_retry_after_is_honoured_but_capped():
    rp, _, _, sleeps, _ = _make([ProviderUnavailable("503"), ProviderUnavailable("503"), OK])
    await rp.generate(MSG)
    assert sleeps == [rs.BASE_DELAY_S * 0.5, rs.BASE_DELAY_S * 2 * 0.5]  # jitter 0 -> half
    rp, _, _, sleeps, _ = _make([RateLimited("429", retry_after=2.0),
                                 RateLimited("429", retry_after=60.0), OK])
    await rp.generate(MSG)
    assert sleeps == [2.0, rs.MAX_DELAY_S]


async def test_at_most_two_retries_then_fallback():
    rp, primary, fallback, _, _ = _make([ProviderUnavailable("x")] * 3, [OK])
    assert (await rp.generate(MSG)).parsed == OK.parsed
    assert len(primary.calls) == 3 and len(fallback.calls) == 1
    assert fallback.calls[0].options.model == "fallback-m"


async def test_both_routes_fail_raises_the_last_error():
    rp, _, fallback, _, _ = _make([ProviderUnavailable("p")] * 3, [ProviderTimeout("f")] * 3)
    with pytest.raises(ProviderTimeout):
        await rp.generate(MSG)
    assert len(fallback.calls) == 3


@pytest.mark.parametrize("error", [BadRequest("400"), MalformedOutput("bad json")])
async def test_non_retryable_errors_are_raised_at_once(error):
    rp, primary, fallback, sleeps, _ = _make([error], [OK])
    with pytest.raises(type(error)):
        await rp.generate(MSG)
    assert len(primary.calls) == 1 and fallback.calls == [] and sleeps == []


async def test_breaker_opens_after_five_failures_in_sixty_seconds():
    clock = Clock()
    breakers = Breakers(clock)
    # 5 failures: one full attempt (3) plus two more
    rp, primary, _, _, _ = _make([ProviderUnavailable("x")] * 5, clock=clock, breakers=breakers)
    with pytest.raises(ProviderUnavailable):
        await rp.generate(MSG)
    rp2, primary2, _, _, _ = _make([ProviderUnavailable("x")] * 2, clock=clock, breakers=breakers)
    with pytest.raises(ProviderUnavailable):
        await rp2.generate(MSG)
    assert breakers["openai"].state == "open"
    # While open, calls fail fast without reaching the provider and go to the fallback
    rp3, primary3, fallback3, _, _ = _make([OK], [OK], clock=clock, breakers=breakers)
    assert (await rp3.generate(MSG)).parsed == OK.parsed
    assert primary3.calls == [] and len(fallback3.calls) == 1


async def test_spread_out_failures_do_not_open_the_breaker():
    clock = Clock()
    breaker = Breakers(clock)["openai"]
    for _ in range(10):
        breaker.record_failure()
        clock.now += 20  # never 5 within 60 s
    assert breaker.state == "closed"


async def test_half_open_after_thirty_seconds_then_close_or_reopen():
    clock = Clock()
    breaker = Breakers(clock)["openai"]
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == "open" and not breaker.allow()
    clock.now += 29
    assert not breaker.allow()
    clock.now += 1
    assert breaker.allow() and breaker.state == "half_open"
    assert not breaker.allow()  # only one trial at a time
    breaker.record_failure()
    assert breaker.state == "open"
    clock.now += 30
    assert breaker.allow()
    breaker.record_success()
    assert breaker.state == "closed" and breaker.allow()


async def test_half_open_trial_succeeds_through_the_provider():
    clock = Clock()
    breakers = Breakers(clock)
    for _ in range(5):
        breakers["openai"].record_failure()
    clock.now += 30
    rp, primary, _, _, _ = _make([OK], clock=clock, breakers=breakers)
    assert (await rp.generate(MSG)).parsed == OK.parsed
    assert breakers["openai"].state == "closed"


async def test_breakers_are_per_provider():
    clock = Clock()
    breakers = Breakers(clock)
    for _ in range(5):
        breakers["openai"].record_failure()
    assert breakers["openai"].state == "open" and breakers["gemini"].state == "closed"
