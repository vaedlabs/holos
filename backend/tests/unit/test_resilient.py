"""ResilientProvider: deadlines, backup calls, retries, fallback and the circuit breaker
(Plan C.9, Part E #28). Retry and breaker rules run on a fake clock; deadlines and
backup calls on real time with small speeds. The provider is the FakeProvider."""

import asyncio
import time

import pytest

from app.agents.schemas import MentalReply
from app.config.speeds import Speed
from app.providers import (
    Backups,
    BadRequest,
    Breakers,
    CallPlan,
    FairScheduler,
    FakeProvider,
    GenerateOptions,
    MalformedOutput,
    NoCapacity,
    OverBudget,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ResilientProvider,
    Route,
    Turn,
)
from app.providers import resilient as rs
from app.providers.fake import Slow, reply

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

OK = reply(MentalReply(kind="answer", summary="ok", items=[], notes=[], source_ids=[],
                       follow_up=None, risk_flag=False))
BACKUP_OK = reply(MentalReply(kind="answer", summary="backup", items=[], notes=[],
                              source_ids=[], follow_up=None, risk_flag=False))
MSG = [Turn("user", "hi")]
# Fake-clock tests: calls are instant, so p90 is never reached
SLOW_SPEED = Speed(p50=3.0, p90=60.0, p95=8.0, p99=120.0)
# Real-time tests
FAST = Speed(p50=0.05, p90=0.1, p95=0.15, p99=0.3)
SLOTS = {"openai": 24, "gemini": 4, "tavily": 4}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Meter:
    """Records every budget step; refuses reservations once `room` runs out."""

    def __init__(self, room: int = 100):
        self.room = room
        self.log: list[tuple[str, int]] = []
        self.usages: list = []
        self._n = 0

    async def reserve(self, options):
        if self.room == 0:
            return None
        self.room -= 1
        self._n += 1
        self.log.append(("reserve", self._n))
        return self._n

    async def settle(self, hold, options, usage):
        self.log.append(("settle", hold))
        self.usages.append(usage)

    async def keep(self, hold):
        self.log.append(("keep", hold))

    async def release(self, hold):
        self.log.append(("release", hold))

    def ends(self) -> list[str]:
        return sorted(step for step, _ in self.log if step != "reserve")


def _make(primary_script, fallback_script=None, *, clock=None, breakers=None,
          scheduler=None, real_time=False, backups=None):
    clock = clock or (time.monotonic if real_time else Clock())
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
        breakers or Breakers(clock),
        scheduler=scheduler or FairScheduler(SLOTS, global_slots=24, clock=clock),
        backups=backups,
        sleep=asyncio.sleep if real_time else sleep, jitter=lambda: 0.0, clock=clock,
    )
    return rp, primary, fallback, sleeps, clock


def _plan(clock, left=25.0, speed=SLOW_SPEED, meter=None, principal="p", kind=""):
    return CallPlan(deadline=clock() + left, speed=speed, principal=principal, meter=meter,
                    kind=kind)


# --- Retries and fallback ---


@pytest.mark.parametrize("error", [RateLimited("429"), ProviderUnavailable("503"),
                                   ProviderTimeout("timeout")])
async def test_retries_retryable_errors(error):
    rp, primary, _, sleeps, clock = _make([error, OK])
    assert (await rp.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert len(primary.calls) == 2 and len(sleeps) == 1


async def test_backoff_doubles_and_retry_after_is_honoured_in_full():
    rp, _, _, sleeps, clock = _make([ProviderUnavailable("503"), ProviderUnavailable("503"), OK])
    await rp.generate(MSG, plan=_plan(clock))
    assert sleeps == [rs.BASE_DELAY_S * 0.5, rs.BASE_DELAY_S * 2 * 0.5]  # jitter 0 -> half
    # Longer than our own backoff cap, but there is time: waited exactly as asked
    rp, _, _, sleeps, clock = _make([RateLimited("429", retry_after=2.0),
                                     RateLimited("429", retry_after=10.0), OK])
    await rp.generate(MSG, plan=_plan(clock, left=40))
    assert sleeps == [2.0, 10.0]


async def test_a_retry_after_longer_than_the_time_left_gives_the_route_up_at_once():
    # Gemini's free tier asked for 34-53 s (Part D); 25 s left can't fit that
    rp, primary, fallback, sleeps, clock = _make([RateLimited("429", retry_after=40.0)], [OK])
    assert (await rp.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert len(primary.calls) == 1 and len(fallback.calls) == 1 and sleeps == []
    rp, primary, _, sleeps, clock = _make([RateLimited("429", retry_after=40.0), OK])
    with pytest.raises(RateLimited):
        await rp.generate(MSG, plan=_plan(clock))
    assert len(primary.calls) == 1 and sleeps == []


async def test_no_retry_unless_the_p95_plus_overshoot_is_left_after_the_wait():
    speed = Speed(p50=3.0, p90=60.0, p95=8.0, p99=120.0)
    # 0.25 s backoff, then 8.5 s needed: 8.7 s left is enough, 8.7 - 0.25 < 8.5 is not
    rp, primary, _, sleeps, clock = _make([ProviderUnavailable("503"), OK])
    await rp.generate(MSG, plan=_plan(clock, left=8.76, speed=speed))
    assert len(primary.calls) == 2
    rp, primary, _, sleeps, clock = _make([ProviderUnavailable("503"), OK])
    with pytest.raises(ProviderUnavailable):
        await rp.generate(MSG, plan=_plan(clock, left=8.7, speed=speed))
    assert len(primary.calls) == 1 and sleeps == []


async def test_at_most_two_retries_then_fallback():
    rp, primary, fallback, _, clock = _make([ProviderUnavailable("x")] * 3, [OK])
    assert (await rp.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert len(primary.calls) == 3 and len(fallback.calls) == 1
    assert fallback.calls[0].options.model == "fallback-m"


async def test_both_routes_fail_raises_the_last_error():
    rp, _, fallback, _, clock = _make([ProviderUnavailable("p")] * 3, [ProviderTimeout("f")] * 3)
    with pytest.raises(ProviderTimeout):
        await rp.generate(MSG, plan=_plan(clock))
    assert len(fallback.calls) == 3


@pytest.mark.parametrize("error", [BadRequest("400"), MalformedOutput("bad json")])
async def test_non_retryable_errors_are_raised_at_once(error):
    rp, primary, fallback, sleeps, clock = _make([error], [OK])
    with pytest.raises(type(error)):
        await rp.generate(MSG, plan=_plan(clock))
    assert len(primary.calls) == 1 and fallback.calls == [] and sleeps == []


# --- Deadlines ---


async def test_no_time_left_means_no_call():
    rp, primary, _, _, clock = _make([OK])
    with pytest.raises(ProviderTimeout):
        await rp.generate(MSG, plan=_plan(clock, left=0))
    assert primary.calls == []


async def test_a_hung_call_ends_at_its_deadline_not_the_sdk_timeout():
    rp, primary, _, _, clock = _make([Slow(10, OK)], real_time=True)
    began = time.monotonic()
    with pytest.raises(ProviderTimeout):
        await rp.generate(MSG, plan=_plan(clock, left=0.2, speed=Speed(0.05, 1, 1, 1)))
    assert time.monotonic() - began < 0.25
    # The SDK is given the time left, not the old fixed 25 s
    assert 0 < primary.calls[0].options.timeout_s <= 0.2


# --- Backup calls ---


async def test_a_slow_call_gets_a_backup_and_the_first_reply_wins():
    meter = Meter()
    rp, primary, _, _, clock = _make([Slow(5, OK), BACKUP_OK], real_time=True)
    began = time.monotonic()
    result = await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, meter=meter))
    took = time.monotonic() - began
    assert result.parsed == BACKUP_OK.parsed and len(primary.calls) == 2
    assert FAST.p90 <= took < FAST.p90 + 0.1
    # Both settle at the winner's usage: the cancelled call ran the same request
    assert meter.ends() == ["settle", "settle"]
    assert meter.usages == [BACKUP_OK.usage, BACKUP_OK.usage]
    assert rp._scheduler.in_use("openai") == 0


async def test_a_call_faster_than_p90_gets_no_backup():
    rp, primary, _, _, clock = _make([Slow(0.02, OK)], real_time=True)
    await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST))
    assert len(primary.calls) == 1


async def test_no_backup_without_a_free_slot():
    one = FairScheduler({"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], scheduler=one, real_time=True)
    assert (await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST))).parsed == OK.parsed
    assert len(primary.calls) == 1


async def test_no_backup_for_a_half_open_trial():
    breakers = Breakers(time.monotonic)
    breaker = breakers["openai"]
    for _ in range(5):
        breaker.record_failure()
    breaker.opened_at -= rs.BREAKER_COOLDOWN_S  # the cooldown has passed
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], breakers=breakers, real_time=True)
    assert (await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST))).parsed == OK.parsed
    assert len(primary.calls) == 1 and breaker.state == "closed"


async def test_no_backup_when_the_budget_has_no_room_for_it():
    meter = Meter(room=1)
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], real_time=True)
    result = await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, meter=meter))
    assert result.parsed == OK.parsed and len(primary.calls) == 1
    assert meter.ends() == ["settle"] and rp._scheduler.in_use("openai") == 0


async def test_no_backup_with_less_than_the_p50_left():
    speed = Speed(p50=0.5, p90=0.1, p95=0.15, p99=1)
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], real_time=True)
    await rp.generate(MSG, plan=_plan(clock, left=0.55, speed=speed))
    assert len(primary.calls) == 1


async def test_a_failed_backup_leaves_the_slow_call_running():
    rp, primary, _, _, clock = _make([Slow(0.25, OK), ProviderUnavailable("503")],
                                     real_time=True)
    assert (await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST))).parsed == OK.parsed
    assert len(primary.calls) == 2


async def test_when_both_fail_the_first_calls_error_is_raised():
    rp, primary, _, _, clock = _make(
        [Slow(0.3, BadRequest("first")), Slow(0.05, MalformedOutput("backup"))], real_time=True)
    with pytest.raises(BadRequest):
        await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST))


async def test_cancelling_the_request_cancels_both_calls_and_frees_their_slots():
    meter = Meter()
    rp, primary, _, _, clock = _make([Slow(5, OK), Slow(5, OK)], real_time=True)
    task = asyncio.create_task(rp.generate(MSG, plan=_plan(clock, left=10, speed=FAST,
                                                           meter=meter)))
    await asyncio.sleep(FAST.p90 + 0.05)
    assert len(primary.calls) == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rp._scheduler.in_use("openai") == 0
    assert meter.ends() == ["keep", "keep"]  # both may have been billed


# --- Backups follow live speed and are capped (Part E #32) ---


async def test_the_backup_threshold_is_the_live_p90_once_there_are_enough_calls():
    backups = Backups()
    table = Speed(p50=0.05, p90=0.1, p95=0.15, p99=0.3)
    assert backups.threshold("physical", table) == 0.1
    for i in range(rs.SPEED_MIN_SAMPLES - 1):
        backups.record_time("physical", 1.0 + i / 100)
    assert backups.threshold("physical", table) == 0.1  # too few calls yet: the table
    backups.record_time("physical", 1.49)
    assert backups.threshold("physical", table) == pytest.approx(1.45)
    assert backups.threshold("mental", table) == 0.1  # each kind on its own
    for _ in range(rs.SPEED_WINDOW):
        backups.record_time("physical", 2.0)
    assert backups.threshold("physical", table) == 2.0  # only recent calls count


async def test_on_a_slow_day_the_backup_waits_for_the_days_own_p90():
    # 27 Oct's p90 sits at 28 Oct's median: the table would back up half the calls
    backups = Backups()
    for _ in range(rs.SPEED_MIN_SAMPLES):
        backups.record_time("physical", 0.3)
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], real_time=True, backups=backups)
    await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, kind="physical"))
    assert len(primary.calls) == 1  # past the table's 0.1 s, not past the live 0.3 s
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], real_time=True)
    await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, kind="physical"))
    assert len(primary.calls) == 2  # a fresh process uses the table


async def test_calls_record_their_times_and_cancelled_ones_too():
    backups = Backups()
    rp, _, _, _, clock = _make([Slow(0.02, OK), Slow(1, OK), Slow(0.02, OK)],
                               real_time=True, backups=backups)
    await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, kind="nutrition"))
    await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, kind="nutrition"))
    times = sorted(backups._times["nutrition"])
    assert len(times) == 3  # fast call, backup winner, cancelled slow call
    assert times[-1] >= FAST.p90  # the cancelled one, at its time so far


async def test_backups_are_capped_at_a_tenth_of_the_last_minutes_calls():
    clock = Clock()
    backups = Backups(clock)
    assert backups.take()  # at least one a minute, even with little traffic
    assert not backups.take()
    for _ in range(20):
        backups.note_call()
    assert backups.take()  # 2 of 20 calls
    assert not backups.take()
    clock.now += rs.BACKUP_WINDOW_S + 1  # a minute later, the old ones have gone
    assert backups.take()


async def test_a_backup_over_the_cap_gives_back_its_slot_and_reservation():
    backups = Backups()
    assert backups.take()  # this minute's one backup is used
    meter = Meter()
    rp, primary, _, _, clock = _make([Slow(0.2, OK)], real_time=True, backups=backups)
    result = await rp.generate(MSG, plan=_plan(clock, left=3, speed=FAST, meter=meter))
    assert result.parsed == OK.parsed and len(primary.calls) == 1
    assert meter.ends() == ["release", "settle"] and rp._scheduler.in_use("openai") == 0



async def test_a_call_over_budget_doesnt_run():
    rp, primary, _, _, clock = _make([OK])
    with pytest.raises(OverBudget):
        await rp.generate(MSG, plan=_plan(clock, meter=Meter(room=0)))
    assert primary.calls == [] and rp._scheduler.in_use("openai") == 0


async def test_unbilled_errors_release_the_reservation_and_unknown_usage_keeps_it():
    meter = Meter()
    rp, _, _, _, clock = _make([RateLimited("429"), ProviderUnavailable("503"),
                                ProviderTimeout("t")], [MalformedOutput("bad"), BadRequest("x")])
    with pytest.raises(MalformedOutput):
        await rp.generate(MSG, plan=_plan(clock, meter=meter))
    # 429 and 503 weren't billed; the timeout and the unparsable reply may have been
    assert meter.ends() == ["keep", "keep", "release", "release"]


async def test_a_shed_call_releases_its_reservation():
    full = FairScheduler({"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    full._take("openai", "someone")
    meter = Meter()
    rp, primary, _, _, clock = _make([OK], scheduler=full)
    with pytest.raises(NoCapacity):
        await rp.generate(MSG, plan=_plan(clock, left=5, meter=meter))  # p95 8 s: no time
    assert primary.calls == [] and meter.ends() == ["release"]


# --- Circuit breaker ---


async def test_breaker_opens_after_five_bad_calls_in_sixty_seconds():
    clock = Clock()
    breakers = Breakers(clock)
    # 5 failures: one full attempt (3) plus two more
    rp, _, _, _, _ = _make([ProviderUnavailable("x")] * 3, clock=clock, breakers=breakers)
    with pytest.raises(ProviderUnavailable):
        await rp.generate(MSG, plan=_plan(clock))
    rp2, _, _, _, _ = _make([ProviderUnavailable("x")] * 2, clock=clock, breakers=breakers)
    with pytest.raises(ProviderUnavailable):
        await rp2.generate(MSG, plan=_plan(clock))  # the 5th failure opens it: no 3rd try
    assert breakers["openai"].state == "open"
    assert breakers["openai"].retry_after() == pytest.approx(rs.BREAKER_COOLDOWN_S)
    # While open, calls fail fast without reaching the provider and go to the fallback
    rp3, primary3, fallback3, _, _ = _make([OK], [OK], clock=clock, breakers=breakers)
    assert (await rp3.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert primary3.calls == [] and len(fallback3.calls) == 1


async def test_a_few_bad_calls_among_many_good_ones_dont_open_the_breaker():
    # 1% of healthy calls pass p99: at 350 calls a minute that is 3-4 slow calls
    clock = Clock()
    breaker = Breakers(clock)["openai"]
    for i in range(350):
        breaker.record_failure() if i % 50 == 0 else breaker.record_success()
        clock.now += 60 / 350
    for _ in range(4):
        breaker.record_failure()
    assert breaker.state == "closed"


async def test_bad_calls_open_the_breaker_once_they_are_half():
    clock = Clock()
    breaker = Breakers(clock)["openai"]
    for _ in range(6):
        breaker.record_success()
    for _ in range(5):
        breaker.record_failure()
    assert breaker.state == "closed"  # 5 of 11
    breaker.record_failure()
    assert breaker.state == "open"  # 6 of 12


async def test_a_slow_success_counts_as_bad():
    breakers = Breakers(time.monotonic)
    speed = Speed(p50=0.01, p90=10, p95=0.02, p99=0.05)
    rp, _, _, _, clock = _make([Slow(0.06, OK)] * 5, breakers=breakers, real_time=True)
    for _ in range(5):
        assert (await rp.generate(MSG, plan=_plan(clock, left=3, speed=speed))).parsed
    assert breakers["openai"].state == "open"


async def test_our_own_short_deadlines_dont_count_against_the_provider():
    # Live, 28 Oct 2026: five calls cut at 0.5-3 s deadlines opened the breaker
    breakers = Breakers(time.monotonic)
    rp, _, _, _, clock = _make([Slow(1, OK)] * 6, breakers=breakers, real_time=True)
    for _ in range(6):
        with pytest.raises(ProviderTimeout):
            await rp.generate(MSG, plan=_plan(clock, left=0.05, speed=FAST))
    assert breakers["openai"].state == "closed" and not breakers["openai"].calls


async def test_a_timeout_after_the_p99_counts_as_bad():
    breakers = Breakers(time.monotonic)
    speed = Speed(p50=0.01, p90=10, p95=0.01, p99=0.04)
    rp, _, _, _, clock = _make([Slow(1, OK)] * 5, breakers=breakers, real_time=True)
    for _ in range(5):
        with pytest.raises(ProviderTimeout):
            await rp.generate(MSG, plan=_plan(clock, left=0.05, speed=speed))
    assert breakers["openai"].state == "open"


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
    assert not breaker.allow() and breaker.retry_after() == pytest.approx(1)
    clock.now += 1
    assert breaker.allow() and breaker.state == "half_open"
    assert breaker.retry_after() is None  # admission lets the trial request in
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
    rp, _, _, _, _ = _make([OK], clock=clock, breakers=breakers)
    assert (await rp.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert breakers["openai"].state == "closed"


async def test_a_trial_that_never_ran_lets_the_next_call_try():
    clock = Clock()
    breakers = Breakers(clock)
    for _ in range(5):
        breakers["openai"].record_failure()
    clock.now += 30
    rp, primary, _, _, _ = _make([OK], clock=clock, breakers=breakers)
    with pytest.raises(OverBudget):
        await rp.generate(MSG, plan=_plan(clock, meter=Meter(room=0)))
    assert primary.calls == [] and breakers["openai"].state == "half_open"
    assert (await rp.generate(MSG, plan=_plan(clock))).parsed == OK.parsed
    assert breakers["openai"].state == "closed"


async def test_breakers_are_per_provider():
    clock = Clock()
    breakers = Breakers(clock)
    for _ in range(5):
        breakers["openai"].record_failure()
    assert breakers["openai"].state == "open" and breakers["gemini"].state == "closed"
