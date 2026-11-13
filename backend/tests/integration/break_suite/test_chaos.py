"""Break suite part 1 (Part E #59): seeded fault combinations on the real chat path.

Each seed picks a person (guest or account, with or without a knee injury), a message
(one or several coaches, logging, a greeting, coaches chosen in the app, a crisis) and a
fault for every model call: slow, just inside or just past its deadline, each kind of
provider error, a malformed or cut-off reply. Some seeds drop the connection or send
the same request twice. Whatever happens, every rule in `harness.broken` must hold.

    pytest tests/integration/break_suite/test_chaos.py     # BREAK_SEEDS runs (150)
    BREAK_SEEDS=10000 pytest tests/integration/break_suite/test_chaos.py   # nightly
    pytest tests/integration/break_suite/test_chaos.py -k "seed-17"        # replay one
"""

import asyncio
import logging
import os
import random
import uuid
from dataclasses import dataclass, field, replace

import pytest
import pytest_asyncio

from app.agents.schemas import NutritionReply, PhysicalReply
from app.data.state_store import StateStore
from app.orchestration import coordinator
from app.orchestration.reader import ReaderReply
from app.providers import (
    AccountFailure,
    BadRequest,
    LLMResult,
    MalformedOutput,
    NoCapacity,
    ProviderStalled,
    ProviderTimeout,
    ProviderUnavailable,
    RateLimited,
    ToolCall,
    ToolResult,
    Usage,
)
from app.providers.fake import Slow

from ..test_admission import account, guest, sql
from ..test_chat import (
    KNEE_NOTE,
    _app,
    _mental,
    _payload,
    _physical,
    _result,
    _route,
    requests_finish,  # noqa: F401  (autouse: requests end before the DB is emptied)
)
from .harness import K, Models, broken, scale_time, send

pytestmark = pytest.mark.asyncio

SEEDS = int(os.getenv("BREAK_SEEDS", "150"))
SCRIPT = 8  # model calls a kind may make in one request, each with its own fault
PAD = 8  # good answers after those, so a script never runs out
KNEE = {"condition_ids": ["knee_ligament_injury"], "allergen_tags": [], "diet_tags": [],
        "notes": ""}
BRIDGES = {"catalogue_id": "glute_bridge", "sets": 3, "reps": 12, "duration_s": None,
           "note": ""}
SQUATS = {**BRIDGES, "catalogue_id": "back_squat"}
DAL = {"day": None, "name": "Dal", "ingredients": ["lentils"], "allergen_tags": [],
       "diet_tags": ["vegan"], "portion": "1 bowl", "calories": 230, "note": "",
       "protein_g": 12, "carbs_g": 35, "fat_g": 5}


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


# --- The good answer of each kind of call ---


def _calls(name, args) -> LLMResult:
    return LLMResult(provider="fake", model="m", usage=Usage(900, 40),
                     tool_calls=(ToolCall(f"c-{uuid.uuid4().hex[:6]}", name, args),))


def _coach(log: tuple[str, dict] | None, reply: LLMResult):
    """A coach that, offered its tools and not yet answered by them, calls its log
    tool; otherwise it replies, as a real model does."""
    def step(call):
        if log and call.tools and not any(isinstance(m, ToolResult) for m in call.messages):
            return _calls(*log)
        return reply
    return step


def _ack(cls, summary):
    return _result(cls(kind="log_ack", summary=summary, items=[], notes=[], source_ids=[],
                       follow_up=None, risk_flag=False))


def _answer():
    return _result(NutritionReply(kind="answer", summary="Dal and rice is a good dinner.",
                                  items=[], notes=[], source_ids=[], follow_up=None,
                                  risk_flag=False))


# --- Faults ---

DEADLINE = {"router": 5 * K, "physical": 60 * K, "nutrition": 60 * K, "mental": 60 * K,
            "summary": 8.7 * K, "reader": 4 * K}


def _error(rng: random.Random) -> Exception:
    return rng.choice([
        lambda: ProviderUnavailable("down", "openai"),
        lambda: ProviderTimeout("slow", "openai"),
        lambda: ProviderStalled("silent", "openai"),
        lambda: RateLimited("429", "openai", retry_after=rng.choice([0.01, 5.0])),
        lambda: BadRequest("400", "openai"),
        lambda: AccountFailure("bad key", "openai", status=401),
        lambda: MalformedOutput("bad json", "openai"),
        lambda: NoCapacity("full", "openai"),
    ])()


def _faulted(rng: random.Random, good, kind: str, p: float):
    """`good` as it is (most of the time), or with one fault: (step, label)."""
    if rng.random() >= p:
        return good, "ok"
    d = DEADLINE[kind]
    delay = rng.choice([0.005, 0.5 * d, d - 0.01, d + 0.01, 1.5 * d])
    roll = rng.randrange(5)
    if roll == 0:
        return Slow(delay, good), f"slow {delay:.3f}s"
    if roll == 1:
        exc = _error(rng)
        return exc, type(exc).__name__
    if roll == 2:
        exc = _error(rng)
        return Slow(delay, exc), f"{type(exc).__name__} after {delay:.3f}s"
    if roll == 3:
        return LLMResult(provider="fake", model="m", text="{not json", parsed=None,
                         usage=Usage(50, 5)), "malformed"

    def cut(call, good=good):
        result = good(call) if callable(good) else good
        return replace(result, truncated=True)
    return cut, "truncated"


@dataclass
class Scenario:
    seed: int
    account: bool
    knee: bool
    message: str
    agents: list[str] | None  # chosen in the app
    scripts: dict[str, list] = field(default_factory=dict)
    faults: dict[str, list[str]] = field(default_factory=dict)
    drop_after: int | None = None
    twice: bool = False
    crisis: bool = False

    def __str__(self):
        who = ("account" if self.account else "guest") + (" with knee" if self.knee else "")
        faults = {k: [f for f in v if f != "ok"] for k, v in self.faults.items()}
        return (f"seed {self.seed}: {who}, {self.message!r}, app agents {self.agents}, "
                f"drop after {self.drop_after}, twice {self.twice}, faults "
                f"{ {k: v for k, v in faults.items() if v} }")


def scenario(seed: int) -> Scenario:
    rng = random.Random(seed)
    s = Scenario(seed, account=rng.random() < 0.5, knee=rng.random() < 0.4,
                 message="a leg workout, dinner and help sleeping", agents=None)
    p = rng.choice([0.0, 0.2, 0.4, 0.7])  # how much goes wrong in this run
    roll = rng.random()
    goods: dict[str, object] = {}
    if roll < 0.05:
        s.message = "I don't want to live anymore"  # crisis: no model is called
        s.crisis = True
    elif roll < 0.12:
        s.message = "good morning"
        goods["router"] = _route(kind="greeting", reply="Good morning! How did you sleep?")
    else:
        agents = sorted(rng.sample(["physical", "nutrition", "mental"], rng.randint(1, 3)))
        if roll < 0.2:
            s.agents = agents
        else:
            goods["router"] = _route(*agents)
        unsafe = s.knee and rng.random() < 0.3  # the coach first suggests squats
        if "physical" in agents:
            log = rng.random() < 0.4
            reply = (_ack(PhysicalReply, "Nice work.") if log
                     else _physical("back_squat" if unsafe else "glute_bridge"))
            goods["physical"] = _coach(("log_workout", rng.choice([BRIDGES, SQUATS]))
                                       if log else None, reply)
            if log:
                s.message = "log my 3x12 glute bridges"
        if "nutrition" in agents:
            log = rng.random() < 0.4
            goods["nutrition"] = _coach(("log_meal", {"meal": "lunch", "foods": [DAL]})
                                        if log else None,
                                        _ack(NutritionReply, "Lunch noted.") if log
                                        else _answer())
        if "mental" in agents:
            goods["mental"] = _mental()
        goods["summary"] = _result(text="Logged your bridges. Nice work tonight.")
    if s.knee and "router" in goods or s.knee and s.agents:
        # A profile with something to protect: every reply is read (Part E #59)
        goods["reader"] = _result(ReaderReply(sentences=[]))
    for kind, good in goods.items():
        steps = [_faulted(rng, good, kind, p) for _ in range(SCRIPT)]
        s.scripts[kind] = [st for st, _ in steps] + [good] * PAD
        s.faults[kind] = [label for _, label in steps]
        if kind in ("physical",) and s.knee:
            # the safe plan after a blocked squat, as the retry asks
            s.scripts[kind][SCRIPT:] = [_coach(None, _physical("glute_bridge"))] * PAD
    if rng.random() < 0.15:
        s.drop_after = rng.randint(1, 6)
    elif rng.random() < 0.1:
        s.twice = True
    return s


@pytest.mark.parametrize("seed", range(SEEDS), ids=lambda n: f"seed-{n}")
async def test_every_rule_holds_whatever_fails(seed, store, async_engine, monkeypatch,
                                               caplog):
    scale_time(monkeypatch)
    s = scenario(seed)
    models = Models(**s.scripts)
    app = _app(store, async_engine, models)
    if s.account:
        me = await account(store, async_engine, email=f"seed{seed}@example.com",
                           ipk=f"ipk-{seed}")
        if s.knee:
            await sql(async_engine, "INSERT INTO medical_history (user_id, conditions) "
                      "VALUES (:u, :c)", u=me.user_id, c=KNEE_NOTE)
        extra = {}
    else:
        me = await guest(store, ipk=f"ipk-{seed}")
        extra = {"guest_profile": KNEE if s.knee else {**KNEE, "condition_ids": []},
                 "guest_history": []}
    if s.agents:
        extra["agents"] = s.agents
    payload = _payload(s.message, **extra)
    caplog.set_level(logging.ERROR, logger="app")
    if s.twice:
        first, second = await asyncio.gather(send(app, me, payload),
                                             send(app, me, payload))
        run = first
        if s.crisis:  # checked before the request is claimed: each gets the helplines
            same = all("crisis" in [n for n, _ in r.events] for r in (first, second))
        else:
            same = first.events == second.events
        attach = [] if same else [
            f"the same request twice gave different streams ({second.status})"]
    else:
        run = await send(app, me, payload, drop_after=s.drop_after)
        attach = []
        if s.crisis and run.dropped:
            # Not saved, so no reconnect: sending the message again must bring the
            # helplines (the app's retry after a reconnect finds nothing, Part E #59)
            again = await send(app, me, payload)
            if "crisis" not in [n for n, _ in again.events]:
                attach.append("a dropped crisis, sent again, got no helplines")
    # An ALERT line is the designed answer to a refused key (failure library), not a bug
    bugs = [r.getMessage()[:200] for r in caplog.records
            if r.levelno >= logging.ERROR and r.name.startswith("app")
            and not r.getMessage().startswith("ALERT ")]
    problems = attach + await broken(async_engine, models, run,
                                     user_id=me.user_id if s.account else None, bugs=bugs,
                                     crisis=s.crisis)
    assert not problems, f"{s}\n  " + "\n  ".join(problems)


def test_the_scaled_deadlines_keep_their_order(monkeypatch):
    """The scale keeps the request's time rules in the order they have unscaled."""
    scale_time(monkeypatch)
    assert (coordinator.ROUTING_DEADLINE_S < coordinator.AGENT_DEADLINE_S
            < coordinator.REQUEST_DEADLINE_S)
