"""Every failure names one cause from a closed list, with its timings and the provider's
request ID (Part E #39). Each cause is forced through the real ResilientProvider."""

import asyncio
import logging
import time

import pytest

from app.agents.schemas import MentalReply
from app.config.speeds import Speed
from app.observability import CAUSES, Trace, cause_of
from app.providers import (
    BadRequest,
    Breakers,
    CallPlan,
    FairScheduler,
    FakeProvider,
    GenerateOptions,
    MalformedOutput,
    NoCapacity,
    OverBudget,
    ProviderStalled,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ResilientProvider,
    Route,
    Turn,
)
from app.providers.fake import Slow, Stream, reply

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]

OK = reply(MentalReply(kind="answer", summary="ok", items=[], notes=[], source_ids=[],
                       follow_up=None, risk_flag=False), request_id="req_ok")
MSG = [Turn("user", "hi")]
SLOTS = {"openai": 24, "gemini": 4, "tavily": 4}
# Real time, small limits. No backups unless a case asks for one (first_p90 10 s)
SPEED = Speed(p50=0.05, p90=10.0, p95=0.15, p99=0.3, first_p90=10.0)
BACKUP = Speed(p50=0.05, p90=0.1, p95=0.15, p99=0.3, first_p90=0.1)


class NoRoom:
    async def reserve(self, options):
        return None


def _rp(script, *, streams=False, breakers=None, scheduler=None):
    fake = FakeProvider(list(script), name="openai", streams=streams, request_id="req_1")
    rp = ResilientProvider(
        Route(fake, GenerateOptions(model="m", max_output_tokens=100)), None,
        breakers or Breakers(), scheduler=scheduler or FairScheduler(SLOTS, global_slots=24),
        jitter=lambda: 0.0, stall_first_s=0.2, stall_gap_s=0.1)
    return rp, fake


async def _run(script, *, left=3.0, speed=SPEED, meter=None, **kw) -> Trace:
    rp, _ = _rp(script, **kw)
    trace = Trace("t-1")
    plan = CallPlan(deadline=time.monotonic() + left, speed=speed, principal="p",
                    meter=meter, kind="mental", trace=trace)
    try:
        await rp.generate(MSG, plan=plan)
    except Exception:  # noqa: S110 - the trace is what's checked
        pass
    return trace


def _bug(call):
    raise KeyError("oops")


class _LateScheduler(FairScheduler):
    """Grants the slot only after the deadline has passed."""

    async def acquire(self, provider, principal, start_by=None):
        await asyncio.sleep(0.35)
        self._take(provider, principal)


def _full() -> FairScheduler:
    full = FairScheduler({"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    full._take("openai", "someone")
    return full


def _open_breakers() -> Breakers:
    breakers = Breakers()
    for _ in range(5):
        breakers["openai"].record_failure()
    return breakers


# Built per test: breakers and schedulers keep state (an open breaker half-opens
# after 30 s)
CASES = {
    "rate_limited": lambda: dict(script=[RateLimited("429"), OK]),
    "unavailable": lambda: dict(script=[ProviderUnavailable("503"), OK]),
    "bad_request": lambda: dict(script=[BadRequest("400")]),
    "provider_timeout": lambda: dict(script=[ProviderTimeout("read timeout"), OK]),
    "malformed": lambda: dict(script=[MalformedOutput("not json")]),
    "truncated": lambda: dict(script=[MalformedOutput("cut off", cause="truncated")]),
    "bug": lambda: dict(script=[_bug]),
    "over_budget": lambda: dict(script=[OK], meter=NoRoom()),
    "queue_full": lambda: dict(script=[OK], scheduler=_full(), left=0.2),
    "circuit_open": lambda: dict(script=[OK], breakers=_open_breakers()),
    "no_time_left": lambda: dict(script=[OK], left=0.3, scheduler=_LateScheduler(SLOTS,
                                                                         global_slots=24)),
    "no_first_output": lambda: dict(script=[Stream((), OK, silent=5), OK], streams=True),
    "output_stopped": lambda: dict(script=[Stream((0.02, 5.0), OK), OK], streams=True),
    "deadline_waiting": lambda: dict(script=[Slow(5, OK)], left=0.4),
    "deadline_writing": lambda: dict(script=[Stream((0.05,) * 40, OK)], left=0.4, streams=True),
    "cancelled": lambda: dict(script=[Slow(1, OK), OK], speed=BACKUP),
}


def test_every_cause_is_tested_here():
    # wrong_language is the router's: tests/unit/test_router.py
    assert set(CASES) | {"wrong_language"} == CAUSES


def test_a_cause_must_be_on_the_list():
    with pytest.raises(ValueError):
        ProviderUnavailable("x", cause="network_glitch")
    defaults = {RateLimited: "rate_limited", ProviderUnavailable: "unavailable",
                ProviderTimeout: "provider_timeout", ProviderStalled: "no_first_output",
                BadRequest: "bad_request", NoCapacity: "queue_full", OverBudget: "over_budget",
                MalformedOutput: "malformed"}
    assert {cls: cls("x").cause for cls in defaults} == defaults
    assert cause_of(KeyError()) == "bug" and cause_of(asyncio.CancelledError()) == "cancelled"


@pytest.mark.parametrize("cause", sorted(CASES))
async def test_each_cause_is_named_on_the_trace(cause):
    trace = await _run(**CASES[cause]())
    assert trace.attempts[0].outcome == cause
    assert trace.attempts[0].call == "mental" and trace.attempts[0].role == "first"


async def test_a_call_that_never_went_out_has_no_send_time():
    for cause in ("over_budget", "queue_full", "circuit_open"):
        attempt = (await _run(**CASES[cause]())).attempts[0]
        assert attempt.sent_ms is None and attempt.request_id is None, cause


async def test_retries_and_backups_are_separate_attempts():
    trace = await _run(**CASES["unavailable"]())
    assert [(a.role, a.outcome) for a in trace.attempts] == [("first", "unavailable"),
                                                             ("retry", "ok")]
    trace = await _run(**CASES["cancelled"]())
    assert [(a.role, a.outcome) for a in trace.attempts] == [("first", "cancelled"),
                                                             ("backup", "ok")]


async def test_timings_and_request_ids():
    trace = await _run([Stream((0.05, 0.02), OK)], streams=True)
    a = trace.attempts[0]
    assert a.outcome == "ok" and a.request_id == "req_ok"  # the result's own ID wins
    assert a.queued_ms == 0 and a.sent_ms is not None and a.opened_ms is not None
    assert 40 <= a.first_output_ms - a.sent_ms < 200 and a.ended_ms >= a.first_output_ms
    assert (a.tokens_in, a.tokens_out) == (100, 50)
    # A call that never wrote still has the request ID from its headers
    stalled = (await _run(**CASES["no_first_output"]())).attempts[0]
    assert stalled.request_id == "req_1" and stalled.first_output_ms is None
    assert stalled.opened_ms is not None


async def test_a_failure_is_logged_with_the_trace_and_request_ids(caplog):
    with caplog.at_level(logging.WARNING, logger="app.observability.tracer"):
        await _run(**CASES["no_first_output"]())
    line = caplog.records[0].getMessage()
    assert "trace=t-1" in line and "cause=no_first_output" in line
    assert "request_id=req_1" in line and caplog.records[0].levelno == logging.WARNING


async def test_a_lost_race_is_not_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="app.observability.tracer"):
        await _run(**CASES["cancelled"]())
    assert caplog.records == []


async def test_without_a_trace_failures_are_still_logged(caplog):
    rp, _ = _rp([BadRequest("400")])
    plan = CallPlan(deadline=time.monotonic() + 3, speed=SPEED, principal="p")
    with caplog.at_level(logging.WARNING, logger="app.observability.tracer"):
        with pytest.raises(BadRequest):
            await rp.generate(MSG, plan=plan)
    assert "trace=untraced" in caplog.records[0].getMessage()


def test_the_trace_holds_no_text():
    trace = Trace("t")
    trace.step("tool_call", "physical", "staged", "log_workout")
    assert set(trace.as_dict()) == {"trace_id", "steps", "attempts"}


async def test_a_slow_call_without_a_backup_says_why():
    # One slot: the slow call holds it, so its backup has none (live, 29 Oct 2026: a
    # router call that never answered, and the trace couldn't say why no backup ran)
    one = FairScheduler({"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    trace = await _run([Slow(0.3, OK)], speed=BACKUP, scheduler=one)
    assert [(s.name, s.outcome, s.detail) for s in trace.steps] == [
        ("backup_skipped", "no_slot", "mental")]
    assert trace.attempts[0].outcome == "ok"


async def test_an_error_names_its_request_id_without_headers():
    rp, fake = _rp([BadRequest("400", "openai", request_id="req_err", status=400)])
    fake.request_id = None  # no `opened` call: the ID comes from the error
    trace = Trace("t")
    plan = CallPlan(deadline=time.monotonic() + 3, speed=SPEED, principal="p", trace=trace)
    with pytest.raises(BadRequest):
        await rp.generate(MSG, plan=plan)
    assert (trace.attempts[0].request_id, trace.attempts[0].status) == ("req_err", 400)


async def test_time_waiting_for_a_slot_is_recorded():
    one = FairScheduler({"openai": 1, "gemini": 1, "tavily": 1}, global_slots=1)
    one._take("openai", "someone")
    asyncio.get_running_loop().call_later(0.1, one.release, "openai", "someone")
    trace = await _run([OK], scheduler=one, left=60.0)  # room for the predicted wait
    assert trace.attempts[0].outcome == "ok" and 80 <= trace.attempts[0].queued_ms < 300
