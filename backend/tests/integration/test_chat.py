"""The chat endpoint end to end on a real Postgres, with scripted models (Plan C.2, P4.7):
each stage fails as documented; a crisis gets helplines with or without a session;
coaches run in parallel and the first answer goes out before the slowest; accounts save
the turn, guests store nothing; the request outlives its connection; a repeated
`client_request_id` attaches; a planned restart lets running requests finish."""

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.base import CRISIS_NOTE, BaseAgent
from app.agents.schemas import (
    ExerciseItem,
    MentalReply,
    PhysicalReply,
    PracticeItem,
    RouterReply,
)
from app.config.settings import get_settings
from app.data.state_store import StateStore
from app.data.stream_store import StreamStore
from app.dependencies import (
    get_db_sessions,
    get_image_store,
    get_state_store,
    get_stream_store,
)
from app.orchestration import composer as composer_module
from app.orchestration import coordinator, worker
from app.orchestration.budget import spend_keys
from app.orchestration.principal import csrf_token
from app.orchestration.router import Router
from app.orchestration.services import (
    COACHES,
    READER_OPTIONS,
    ROUTER_OPTIONS,
    SUMMARY_OPTIONS,
    Services,
    get_services,
)
from app.providers import (
    AccountFailure,
    BadRequest,
    Breakers,
    FakeProvider,
    LLMResult,
    ProviderUnavailable,
    ResilientProvider,
    Route,
    Usage,
)
from app.providers.fake import Slow
from app.routers import chat
from app.routers.errors import ApiError, api_error_handler
from app.storage.images import LocalImageStore

from .test_admission import APP, account, guest, seed_spend, settings, sql
from .test_intake import form

pytestmark = pytest.mark.asyncio

KNEE_NOTE = "torn ACL left knee"


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest_asyncio.fixture(autouse=True)
async def requests_finish(async_engine):
    """Each test's requests run on as their own tasks: wait for them before the
    database is emptied, or the emptying waits on their open transactions."""
    worker._reset_for_tests()
    yield
    await asyncio.wait_for(_settled(), 10)
    worker._reset_for_tests()


# --- Scripted models ---


def _result(parsed=None, text=None):
    text = text if text is not None else parsed.model_dump_json()
    return LLMResult(provider="fake", model="m", parsed=parsed, text=text,
                     usage=Usage(900, 120))


def _route(*agents, kind="coaching", reply=None):
    return _result(RouterReply(kind=kind, agents=list(agents), reply=reply))


def _ex(cid, **kw):
    return ExerciseItem(day=None, catalogue_id=cid, sets=kw.get("sets", 2),
                        reps=kw.get("reps", 10), duration_s=None, intensity="low", note="")


def _physical(*cids, risk=False):
    return _result(PhysicalReply(kind="plan", summary="Here is your plan.",
                                 items=[_ex(c) for c in cids], notes=[], source_ids=[],
                                 follow_up=None, risk_flag=risk))


def _mental(risk=False):
    return _result(MentalReply(kind="plan", summary="Try this tonight.", items=[
        PracticeItem(day=None, catalogue_id="box_breathing", duration_min=5, note="")],
        notes=[], source_ids=[], follow_up=None, risk_flag=risk))


class Models:
    """One fake per call kind: parallel coaches each read their own script."""

    def __init__(self, router=(), physical=(), nutrition=(), mental=(), summary=(),
                 reader=None):
        self.fakes = {name: FakeProvider(list(script), name="openai")
                      for name, script in (("router", router), ("physical", physical),
                                           ("nutrition", nutrition), ("mental", mental),
                                           ("summary", summary), ("reader", reader or ()))}
        breakers = Breakers()

        def llm(name, options):
            return ResilientProvider(Route(self.fakes[name], options), None, breakers)

        self.services = Services(
            router=Router(llm("router", ROUTER_OPTIONS)),
            coaches={n: cls(llm(n, cls.options())) for n, cls in COACHES.items()},
            summary=llm("summary", SUMMARY_OPTIONS), search=None, breaker=breakers["openai"],
            # None: no reading, as before the reader (Part E #59)
            reader=llm("reader", READER_OPTIONS) if reader is not None else None)


def _app(store, async_engine, models: Models, images=None) -> FastAPI:
    """`images`: where account photos go; a fresh folder each time unless given, so no
    test writes into the real uploads folder."""
    images = images or LocalImageStore(Path(tempfile.mkdtemp(prefix="holos-images-")))
    cfg = settings()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(chat.router)
    db = async_sessionmaker(async_engine, expire_on_commit=False)
    app.dependency_overrides.update({
        get_settings: lambda: cfg, get_state_store: lambda: store,
        get_stream_store: lambda: StreamStore(async_engine), get_services: lambda: models.services,
        get_db_sessions: lambda: db, get_image_store: lambda: images})
    app.state.images = images
    return app


def _payload(message="a leg workout", rid=None, **kw):
    return {"message": message, "client_request_id": str(rid or uuid.uuid4()),
            "contract_version": 1, **kw}


async def _post(app, principal, payload, image=None, csrf=True, origin=APP):
    cfg = settings()
    headers = {"content-type": "multipart/form-data; boundary=holosboundary"}
    if origin:
        headers["origin"] = origin
    if principal is not None and csrf:
        headers["x-csrf-token"] = csrf_token(principal.raw_session_id, cfg)
    cookies = {cfg.session_cookie: principal.raw_session_id} if principal else {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                 base_url="http://testserver", timeout=30) as client:
        return await client.post("/agents/chat/stream", content=form(payload, image),
                                 headers=headers, cookies=cookies)


def _events(response) -> list[tuple[str, dict]]:
    out, name = [], None
    for line in response.text.splitlines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            out.append((name, json.loads(line[6:])))
    return out


def _names(events) -> list[str]:
    return [n if n != "step" else f"step:{d['name']}" for n, d in events]


async def _settled():
    """Wait for spawned requests to finish (the response already has their events)."""
    while worker.running():
        await asyncio.sleep(0.01)


# --- A guest's request from start to end ---


async def test_a_guest_plan_from_start_to_done(store, async_engine):
    models = Models(router=[_route("physical")], physical=[_physical("glute_bridge")])
    me = await guest(store)
    response = await _post(_app(store, async_engine, models), me, _payload())
    await _settled()
    assert response.status_code == 200
    events = _events(response)
    assert _names(events) == [
        "accepted", "step:admitted", "step:routed", "step:agent_started", "step:gate",
        "step:composing", "section_start", "text", "item", "section_end", "done"]
    assert [d["seq"] for _, d in events] == list(range(len(events)))
    done = events[-1][1]
    assert done["turn"]["content"] == "Here is your plan.\n1. Glute bridge: 2 x 10"
    assert done["trace"]["agents"] == ["physical"] and done["usage"]["tokens_in"] == 1800
    # Guests store nothing in user tables; the request is finished and its lease freed
    assert await sql(async_engine, "SELECT count(*) FROM conversation_messages") == [(0,)]
    assert await sql(async_engine, "SELECT finished_at IS NOT NULL FROM chat_requests") == [
        (True,)]
    assert await sql(async_engine, "SELECT count(*) FROM inflight_leases") == [(0,)]


async def test_holos_answers_a_greeting_itself(store, async_engine):
    models = Models(router=[_route(kind="greeting", reply="Good morning! How did you sleep?")])
    response = await _post(_app(store, async_engine, models), await guest(store),
                           _payload("good morning"))
    events = _events(response)
    text = [d for n, d in events if n == "text"]
    assert text == [{"seq": 3, "trace_id": text[0]["trace_id"],
                     "chunk": "Good morning! How did you sleep?"}]
    assert events[-1][1]["turn"]["content"] == "Good morning! How did you sleep?"
    assert events[-1][1]["trace"]["route"] == "greeting"


# --- Several coaches ---


async def test_coaches_run_in_parallel_and_the_first_answer_goes_out_first(store,
                                                                        async_engine):
    models = Models(router=[_route("physical", "mental")],
                    physical=[Slow(0.3, _physical("glute_bridge"))], mental=[_mental()],
                    summary=[_result(text="Move gently and breathe slowly tonight.")])
    response = await _post(_app(store, async_engine, models), await guest(store),
                           _payload("a workout and help with stress"))
    events = _events(response)
    sections = [d["agent"] for n, d in events if n == "section_start"]
    assert sections == ["mental", "physical"]  # the slow coach's section comes second
    summary = [d for n, d in events if n == "text" and d.get("summary")]
    assert summary[0]["chunk"] == "Move gently and breathe slowly tonight."
    assert _names(events)[-1] == "done"
    # Each coach was told the other answers the rest (C.10)
    assert "mental wellbeing coach is" in models.fakes["physical"].calls[0].messages[-1].text


async def test_the_summary_never_repeats_a_coach_or_talks_about_saving(store, async_engine):
    """Live, 9 Nov 2026: the closing line copied a coach's sentence word for word, and
    said saved entries were awaiting confirmation."""
    models = Models(router=[_route("physical", "mental")],
                    physical=[_physical("glute_bridge")], mental=[_result(MentalReply(
                        kind="plan", summary="Try this tonight; nice work.", items=[
                            PracticeItem(day=None, catalogue_id="box_breathing",
                                         duration_min=5, note="")],
                        notes=[], source_ids=[], follow_up=None, risk_flag=False))],
                    summary=[_result(text="Here is your plan! Move gently tonight. Nice work. "
                                           "Your plan is awaiting confirmation.")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("a workout and help with stress")))
    summary = [d for n, d in events if n == "text" and d.get("summary")]
    assert summary[0]["chunk"] == "Move gently tonight."
    assert "never repeat a coach's sentence" in models.fakes["summary"].calls[0].system


async def test_one_coach_failing_leaves_the_others_answer_and_a_notice(store, async_engine):
    models = Models(router=[_route("physical", "mental")],
                    physical=[_physical("glute_bridge")],
                    mental=[BadRequest("no", "openai"), BadRequest("no", "openai")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("a workout and help with stress")))
    failed = [d for n, d in events if n == "section_end" and d.get("error")]
    assert failed == [{**failed[0], "agent": "mental", "error": "unavailable"}]
    assert ("notice", "partial_result") in [(n, d.get("code")) for n, d in events]
    assert _names(events)[-1] == "done"
    assert not [d for n, d in events if n == "text" and d.get("summary")]  # one answer only


async def test_every_coach_failing_ends_with_an_error(store, async_engine):
    models = Models(router=[_route("physical")],
                    physical=[BadRequest("no", "openai"), BadRequest("no", "openai")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert events[-1] == ("error", {**events[-1][1], "code": "unavailable"})


async def test_an_account_failure_says_the_service_is_unreachable(store, async_engine):
    """Failure library (Part E #55): out of credit or a rejected key, at the router."""
    models = Models(router=[AccountFailure("no credit", "openai", status=429)])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert events[-1][0] == "error"
    assert (events[-1][1]["code"], events[-1][1]["message"]) == (
        "service_unavailable",
        "Holos can't reach its AI service right now. Please try again later.")


async def test_an_account_failure_at_a_coach_says_the_same(store, async_engine):
    models = Models(router=[_route("physical")],
                    physical=[AccountFailure("bad key", "openai", status=401)])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert (events[-1][0], events[-1][1]["code"]) == ("error", "service_unavailable")
    assert len(models.fakes["physical"].calls) == 1  # not retried


# A short routing window: these tests time out the router without waiting 5 s
@pytest.fixture
def quick_routing(monkeypatch):
    monkeypatch.setattr(coordinator, "ROUTING_DEADLINE_S", 0.3)


async def test_a_router_that_times_out_gets_one_more_try(store, async_engine, quick_routing):
    """Live, 10 Nov 2026: the first message after 70 idle minutes never connected."""
    models = Models(router=[Slow(5.0, _route("physical")), _route("physical")],
                    physical=[_physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert ("step", "retry", "router") in [(n, d.get("name"), d.get("detail"))
                                           for n, d in events]
    assert [d["agent"] for n, d in events if n == "section_start"] == ["physical"]
    assert _names(events)[-1] == "done" and len(models.fakes["router"].calls) == 2


@pytest.mark.parametrize("second", [Slow(5.0, _route("physical")),
                                    ProviderUnavailable("down", "openai")])
async def test_a_router_that_fails_twice_says_holos_couldnt_connect(store, async_engine,
                                                                   quick_routing, second):
    models = Models(router=[ProviderUnavailable("down", "openai"), second])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert events[-1][0] == "error"
    assert (events[-1][1]["code"], events[-1][1]["message"]) == (
        "connection", "Holos couldn't connect just now. Your message is still here; tap to "
        "try again.")
    assert len(models.fakes["router"].calls) == 2  # never a third


@pytest.mark.parametrize("failure, code", [
    (BadRequest("no", "openai"), "unavailable"),
    (AccountFailure("bad key", "openai", status=401), "service_unavailable"),
])
async def test_a_router_failure_that_wont_pass_isnt_tried_again(store, async_engine,
                                                               quick_routing, failure, code):
    models = Models(router=[failure, _route("physical")], physical=[_physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert (events[-1][0], events[-1][1]["code"]) == ("error", code)
    assert len(models.fakes["router"].calls) == 1


async def test_no_second_try_when_the_coaches_would_lose_time_to_it(store, async_engine,
                                                                    quick_routing, monkeypatch):
    monkeypatch.setattr(coordinator, "AGENT_DEADLINE_S", coordinator.REQUEST_DEADLINE_S)
    models = Models(router=[ProviderUnavailable("down", "openai"), _route("physical")],
                    physical=[_physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert (events[-1][0], events[-1][1]["code"]) == ("error", "connection")
    assert len(models.fakes["router"].calls) == 1


# --- The mention reader (Part E #59) ---


def _reads(*sentences):
    from app.orchestration.reader import ReaderMention, ReaderReply, ReaderSentence
    reply = ReaderReply(sentences=[
        ReaderSentence(n=n, mentions=[ReaderMention(item=i, stance=st) for i, st in ms])
        for n, ms in enumerate(sentences, 1)])
    return _result(reply)


def _devanagari_squats():
    return _result(PhysicalReply(kind="answer", summary="आज रात 12 स्क्वाट करें। Keep it gentle.",
                                 items=[], notes=[], source_ids=[], follow_up=None,
                                 risk_flag=False))


async def test_the_reader_removes_what_the_word_lists_cant_see(store, async_engine):
    models = Models(router=[_route("physical")], physical=[_devanagari_squats()] * 3,
                    reader=[_reads([("bodyweight_squat", "recommends")], [])] * 3)
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("leg workout", guest_history=[], guest_profile={
                                     "condition_ids": ["knee_ligament_injury"],
                                     "allergen_tags": [], "diet_tags": [], "notes": ""})))
    said = " ".join(d["chunk"] for n, d in events if n == "text")
    assert "स्क्वाट" not in said and "Keep it gentle." in said
    assert "EX-KNEE-01" in [x["rule_id"] for x in events[-1][1]["trace"]["decisions"]]
    assert models.fakes["reader"].calls[0].messages[-1].text == (
        "1. आज रात 12 स्क्वाट करें।\n2. Keep it gentle.")


async def test_a_profile_with_nothing_to_protect_is_not_read(store, async_engine):
    models = Models(router=[_route("physical")], physical=[_devanagari_squats()], reader=[])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("leg workout")))
    assert events[-1][0] == "done" and models.fakes["reader"].calls == []


async def test_without_the_reader_the_word_lists_still_check(store, async_engine, monkeypatch):
    down = ProviderUnavailable("down", "openai")
    models = Models(router=[_route("physical")], physical=[_physical("glute_bridge")],
                    reader=[down] * 6)
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("leg workout", guest_history=[], guest_profile={
                                     "condition_ids": ["knee_ligament_injury"],
                                     "allergen_tags": [], "diet_tags": [], "notes": ""})))
    assert events[-1][0] == "done"
    assert [d["agent"] for n, d in events if n == "section_start"] == ["physical"]
    steps = [s["name"] for s in events[-1][1]["trace"]["steps"]]
    assert "reader" in steps


async def test_coaches_chosen_in_the_app_skip_routing(store, async_engine):
    models = Models(mental=[_mental()])  # the router has no script: a call would fail
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("stress", agents=["mental"])))
    assert [d["agent"] for n, d in events if n == "section_start"] == ["mental"]
    assert models.fakes["router"].calls == []


# --- Accounts ---


async def test_an_account_profile_is_resolved_and_the_turn_saved(store, async_engine):
    me = await account(store, async_engine)
    await sql(async_engine, "INSERT INTO medical_history (user_id, conditions, medications) "
              "VALUES (:u, :c, 'ibuprofen')", u=me.user_id, c=KNEE_NOTE)
    models = Models(router=[_route("physical")],
                    physical=[_physical("back_squat"), _physical("glute_bridge")])
    rid = uuid.uuid4()
    events = _events(await _post(_app(store, async_engine, models), me, _payload(rid=rid)))
    await _settled()
    # The saved text "torn ACL" became the condition the gate checks: squats were blocked
    assert ("step", "block") in [(n, d.get("detail")) for n, d in events]
    end = [d for n, d in events if n == "section_end"][0]
    assert "We couldn't check this note: 'medications: ibuprofen'" in end["warnings"]
    assert "turn" not in events[-1][1]  # accounts: the server keeps the history
    rows = await sql(async_engine, "SELECT role, content, agent_type, client_request_id "
                     "FROM conversation_messages ORDER BY id")
    assert rows == [("user", "a leg workout", "user", rid),
                    ("assistant", "Here is your plan.\n1. Glute bridge: 2 x 10", "physical",
                     None)]
    # The next turn's history is that conversation
    models2 = Models(router=[_route("physical")], physical=[_physical("glute_bridge")])
    await _post(_app(store, async_engine, models2), me, _payload("make it easier"))
    history = [m.text for m in models2.fakes["physical"].calls[0].messages]
    assert "a leg workout" in history and any("Glute bridge" in t for t in history)
    # The router sees who answered, so a follow-up goes back to that coach (C.15)
    routed = [m.text for m in models2.fakes["router"].calls[0].messages]
    assert any(t.startswith("[physical] Here is your plan.") for t in routed)


async def test_an_account_may_not_send_a_guest_profile(store, async_engine):
    me = await account(store, async_engine)
    response = await _post(_app(store, async_engine, Models()), me,
                           _payload(guest_history=[]))
    assert response.status_code == 400 and response.json()["code"] == "bad_request"


# --- The stages fail as documented (C.2) ---


async def test_each_stage_fails_with_its_status(store, async_engine, monkeypatch):
    app = _app(store, async_engine, Models())
    me = await guest(store)
    assert (await _post(app, None, _payload())).status_code == 401
    assert (await _post(app, me, _payload(), csrf=False)).json()["code"] == "bad_csrf"
    assert (await _post(app, me, _payload(), origin="https://evil.example")).status_code == 403
    assert (await _post(app, me, {"message": "", "client_request_id": "x"})).status_code == 400
    big = {"condition_ids": [], "allergen_tags": [], "diet_tags": [], "notes": "x" * 1000}
    big_profile = _payload(guest_profile={**big, "notes": "é" * 1000})
    assert (await _post(app, me, big_profile)).status_code == 400
    monkeypatch.setattr(chat, "CONTRACT_VERSION", 3)
    assert (await _post(app, me, _payload())).json()["code"] == "upgrade_required"
    monkeypatch.undo()
    # An image that isn't one: 415 after admission, and the lease is given back
    response = await _post(app, me, _payload(), image=b"<script>")
    assert response.status_code == 415
    assert await sql(async_engine, "SELECT count(*) FROM inflight_leases") == [(0,)]
    # Over the spend cap: 429 before any model call
    await seed_spend(async_engine, spend_keys(me)[0], "0.05")
    assert (await _post(app, me, _payload())).json()["code"] == "cap_reached"


# --- Crisis (C.16) ---


async def test_a_crisis_gets_helplines_without_a_session_and_without_a_model(store,
                                                                         async_engine):
    models = Models()  # no scripts: any model call would fail
    app = _app(store, async_engine, models)
    for principal, csrf in ((None, False), (await guest(store), False)):
        events = _events(await _post(app, principal, _payload("I want to kill myself"),
                                     csrf=csrf))
        assert _names(events) == ["accepted", "crisis", "done"]
        assert events[2][1]["trace"]["route"] == "crisis"
        assert "kill" not in json.dumps(events[2][1]["trace"])  # the rule, never the text
    assert await sql(async_engine, "SELECT count(*) FROM principal_flags") == [(0,)]
    # With a valid session and CSRF token the flag is set, even over a cap
    me = await guest(store, "ipk-b")
    await seed_spend(async_engine, spend_keys(me)[0], "0.05")
    events = _events(await _post(app, me, _payload("I want to kill myself")))
    assert _names(events) == ["accepted", "crisis", "done"]
    assert await store.crisis_active(me.principal_key)


async def test_after_a_crisis_replies_carry_the_reminder_and_the_mental_coach_is_told(
        store, async_engine):
    me = await guest(store)
    await store.set_crisis(me.principal_key)
    models = Models(router=[_route("mental")], mental=[_mental()])
    events = _events(await _post(_app(store, async_engine, models), me, _payload("stress")))
    crisis = [d for n, d in events if n == "crisis"]
    assert crisis[0]["text"].startswith("If things feel heavy")
    assert CRISIS_NOTE in models.fakes["mental"].calls[0].messages[-1].text


async def test_a_risk_flag_brings_the_full_helpline_message(store, async_engine):
    models = Models(router=[_route("mental")], mental=[_mental(risk=True)])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("everything feels pointless")))
    crisis = [d for n, d in events if n == "crisis"]
    assert crisis[0]["text"].startswith("It sounds like you're going through")
    assert _names(events)[-2:] == ["crisis", "done"]


# --- The request outlives its connection (Part E #34) ---


async def test_a_repeated_request_id_attaches_to_the_request(store, async_engine):
    models = Models(router=[_route("physical")], physical=[Slow(0.2, _physical("plank"))])
    app = _app(store, async_engine, models)
    me = await guest(store)
    rid = uuid.uuid4()
    first, second = await asyncio.gather(_post(app, me, _payload(rid=rid)),
                                         _post(app, me, _payload(rid=rid)))
    assert first.status_code == second.status_code == 200
    assert _events(first) == _events(second)  # the same request, once
    assert len(models.fakes["physical"].calls) == 1


async def test_a_dropped_connection_does_not_stop_the_request(store, async_engine):
    models = Models(router=[_route("physical")], physical=[Slow(0.3, _physical("plank"))])
    app = _app(store, async_engine, models)
    me = await guest(store)
    cfg = settings()
    body = form(_payload())
    received: asyncio.Queue = asyncio.Queue()
    disconnect = asyncio.Event()
    chunks = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        if chunks:
            return chunks.pop(0)
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        await received.put(message)

    headers = [(b"content-type", b"multipart/form-data; boundary=holosboundary"),
               (b"content-length", str(len(body)).encode()), (b"origin", APP.encode()),
               (b"x-csrf-token", csrf_token(me.raw_session_id, cfg).encode()),
               (b"cookie", f"{cfg.session_cookie}={me.raw_session_id}".encode())]
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/agents/chat/stream",
             "raw_path": b"/agents/chat/stream", "query_string": b"", "root_path": "",
             "headers": headers, "client": ("203.0.113.7", 5000),
             "server": ("testserver", 80)}
    task = asyncio.create_task(app(scope, receive, send))
    assert (await asyncio.wait_for(received.get(), 5))["status"] == 200
    first = await asyncio.wait_for(received.get(), 5)
    assert b"event: accepted" in first["body"]
    disconnect.set()  # the phone switches networks
    await asyncio.wait_for(task, 5)
    await asyncio.wait_for(_settled(), 5)
    # The coach still answered; every event was saved for the reconnect
    assert len(models.fakes["physical"].calls) == 1
    saved = await sql(async_engine, "SELECT event FROM stream_events ORDER BY seq")
    assert saved[-1] == ("done",) and ("section_end",) in saved
    assert await sql(async_engine, "SELECT count(*) FROM inflight_leases") == [(0,)]


async def test_a_planned_restart_lets_running_requests_finish(store, async_engine):
    models = Models(router=[_route("physical")], physical=[Slow(0.3, _physical("plank"))])
    app = _app(store, async_engine, models)
    me, other = await guest(store), await guest(store, "ipk-b")
    running = asyncio.create_task(_post(app, me, _payload()))
    while not worker.running():
        await asyncio.sleep(0.01)
    left = await worker.drain(timeout=5)
    assert left == 0 and _names(_events(await running))[-1] == "done"
    refused = await _post(app, other, _payload())
    assert refused.status_code == 503 and refused.json()["code"] == "server_busy"


async def test_a_long_request_keeps_its_lease_and_says_it_is_still_working(
        store, async_engine, monkeypatch):
    monkeypatch.setattr(worker, "HEARTBEAT_S", 0.05)
    monkeypatch.setattr(composer_module, "STILL_WORKING_S", 0.1)
    renewed = []
    real = store.renew_leases

    async def renew(trace_id):
        renewed.append(trace_id)
        await real(trace_id)

    monkeypatch.setattr(store, "renew_leases", renew)
    models = Models(router=[_route("physical")], physical=[Slow(0.35, _physical("plank"))])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload()))
    assert "step:still_working" in _names(events)
    assert len(renewed) >= 3


def test_the_crisis_note_is_guidance_for_the_coach_only():
    # Never sent to the person: it reaches the model inside the per-turn note
    assert isinstance(CRISIS_NOTE, str) and issubclass(BaseAgent, object)


async def test_holos_own_reply_is_gated_too(store, async_engine):
    knee = {"condition_ids": ["knee_ligament_injury"], "allergen_tags": [], "diet_tags": [],
            "notes": ""}
    models = Models(router=[_route(kind="off_topic", reply="Try back squats today! I can "
                                   "help with workouts and meals.")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("what about squats lol", guest_profile=knee)))
    text = [d["chunk"] for n, d in events if n == "text"]
    assert text == ["I can help with workouts and meals."]
    assert events[-1][1]["trace"]["decisions"][0]["rule_id"].startswith("EX-KNEE")


async def test_the_first_answer_leaves_before_the_slow_coach_ends(store, async_engine):
    models = Models(router=[_route("physical", "mental")],
                    physical=[Slow(0.6, _physical("glute_bridge"))], mental=[_mental()],
                    summary=[_result(text="Both together.")])
    await _post(_app(store, async_engine, models), await guest(store),
                _payload("a workout and help with stress"))
    saved = dict(await sql(async_engine, "SELECT data->>'agent', created_at FROM stream_events "
                           "WHERE event = 'section_end'"))
    # Saved (and sent) as each coach ended, not all at the end
    assert (saved["physical"] - saved["mental"]).total_seconds() > 0.4


async def test_running_out_of_budget_mid_request_is_a_notice(store, async_engine):
    me = await guest(store)
    await seed_spend(async_engine, spend_keys(me)[0], "0.0499")  # admitted, but no room
    models = Models(router=[_route("physical")])  # the call's reservation fails first
    events = _events(await _post(_app(store, async_engine, models), me, _payload()))
    assert _names(events)[-2:] == ["notice", "done"]
    assert events[-2][1]["code"] == "cap_reached"
    assert models.fakes["router"].calls == []


async def test_a_photo_goes_to_the_food_coach_with_the_image(store, async_engine):
    import io

    from PIL import Image

    from app.agents.schemas import FoodItem, NutritionReply

    out = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(out, "JPEG")
    reply = NutritionReply(kind="plan", summary="Looks like dal and rice.", items=[
        FoodItem(day=None, name="Dal", ingredients=["lentils"], allergen_tags=[],
                 diet_tags=[], portion="1 bowl", calories=250, note="")],
        notes=[], source_ids=[], follow_up=None, risk_flag=False)
    models = Models(nutrition=[_result(reply)])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("is this ok?"), image=out.getvalue()))
    assert [d["agent"] for n, d in events if n == "section_start"] == ["nutrition"]
    images = models.fakes["nutrition"].calls[0].messages[-1].images
    assert len(images) == 1 and images[0].data[:2] == b"\xff\xd8"  # the cleaned JPEG
    assert models.fakes["router"].calls == []  # a photo goes to nutrition directly


async def test_a_guests_notes_are_checked_and_bring_no_caveat(store, async_engine):
    # The knee is only in the guest's own notes: the gate still blocks the squats
    notes = {"condition_ids": [], "allergen_tags": [], "diet_tags": [],
             "notes": "torn ACL last year, very little free time"}
    models = Models(router=[_route("physical")],
                    physical=[_physical("back_squat"), _physical("glute_bridge")])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload(guest_profile=notes)))
    assert ("step", "block") in [(n, d.get("detail")) for n, d in events]
    end = [d for n, d in events if n == "section_end"][0]
    assert not any("couldn't check" in w for w in end.get("warnings", []))


# --- Account photos are kept (C.8, P4.9) ---


def _photo_turn():
    import io

    from PIL import Image

    from app.agents.schemas import FoodItem, NutritionReply

    out = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 120, 40)).save(out, "JPEG")
    reply = NutritionReply(kind="plan", summary="Looks like dal.", items=[
        FoodItem(day=None, name="Dal", ingredients=["lentils"], allergen_tags=[],
                 diet_tags=[], portion="1 bowl", calories=250, note="")],
        notes=[], source_ids=[], follow_up=None, risk_flag=False)
    return Models(nutrition=[_result(reply)]), out.getvalue()


async def test_an_accounts_photo_is_kept_under_its_key(store, async_engine, tmp_path):
    images = LocalImageStore(tmp_path)
    me = await account(store, async_engine)
    models, photo = _photo_turn()
    await _post(_app(store, async_engine, models, images), me, _payload("is this ok?"),
                image=photo)
    await _settled()
    [(key,)] = await sql(async_engine, "SELECT image_path FROM conversation_messages "
                         "WHERE role = 'user'")
    assert key.startswith(f"users/{me.user_id}/") and key.endswith(".jpg")
    stored = await images.get(key)
    assert stored[:2] == b"\xff\xd8"  # the cleaned JPEG, not the upload


async def test_a_photo_storage_failure_keeps_the_turn(store, async_engine, tmp_path, caplog):
    """Failure library (Part E #55): storage down, the answer and the turn still saved."""
    class Down(LocalImageStore):
        async def put(self, key, data):
            raise OSError("storage unreachable")

    me = await account(store, async_engine)
    models, photo = _photo_turn()
    events = _events(await _post(_app(store, async_engine, models, Down(tmp_path)), me,
                                 _payload("is this ok?"), image=photo))
    await _settled()
    assert events[-1][0] == "done"
    assert await sql(async_engine, "SELECT role, image_path FROM conversation_messages "
                     "ORDER BY id") == [("user", None), ("assistant", None)]
    assert any("image not stored" in r.getMessage() for r in caplog.records)


async def test_a_guests_photo_is_not_kept(store, async_engine, tmp_path):
    models, photo = _photo_turn()
    await _post(_app(store, async_engine, models, LocalImageStore(tmp_path)),
                await guest(store), _payload("is this ok?"), image=photo)
    await _settled()
    assert list(tmp_path.rglob("*.jpg")) == []


async def test_a_turn_that_isnt_saved_leaves_no_photo(store, async_engine, tmp_path,
                                                      monkeypatch):
    from app.orchestration import coordinator

    async def broken(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(coordinator, "save_turn", broken)
    me = await account(store, async_engine)
    models, photo = _photo_turn()
    events = _events(await _post(_app(store, async_engine, models, LocalImageStore(tmp_path)),
                                 me, _payload("is this ok?"), image=photo))
    await _settled()
    assert events[-1][0] == "error"
    assert list(tmp_path.rglob("*.jpg")) == []


async def test_a_request_past_its_hard_limit_stops_its_coaches(store, async_engine,
                                                               monkeypatch):
    """No model call goes on, and is paid for, after the person got the error."""
    monkeypatch.setattr(worker, "HARD_LIMIT_S", 0.3)
    answered = []

    def late(call):
        answered.append(call)
        return _physical("glute_bridge")

    models = Models(router=[_route("physical", "mental")], physical=[Slow(1, late)],
                    mental=[Slow(1, _mental())])
    events = _events(await _post(_app(store, async_engine, models), await guest(store),
                                 _payload("a workout and help with stress")))
    await _settled()
    assert events[-1][0] == "error"
    await asyncio.sleep(1.2)
    assert answered == []


async def test_a_bug_in_a_request_ends_its_stream_and_frees_its_slot(store, async_engine,
                                                                    monkeypatch, caplog):
    """Whatever escapes the turn, the person gets the error, not a stream left open, and
    can send again."""
    real = worker.run_chat

    async def broken(job, services):
        raise RuntimeError("a bug")

    monkeypatch.setattr(worker, "run_chat", broken)
    me = await guest(store)
    # Bounded: without the error event the stream would stay open
    response = await asyncio.wait_for(_post(_app(store, async_engine, Models()), me,
                                            _payload()), 10)
    events = _events(response)
    await _settled()
    assert events[-1] == ("error", {**events[-1][1], "code": "unavailable"})
    assert await sql(async_engine, "SELECT count(*) FROM inflight_leases") == [(0,)]
    assert any("cause=bug" in r.getMessage() for r in caplog.records)

    monkeypatch.setattr(worker, "run_chat", real)
    models = Models(router=[_route("physical")], physical=[_physical("plank")])
    assert _names(_events(await _post(_app(store, async_engine, models), me,
                                      _payload())))[-1] == "done"
