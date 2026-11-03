"""The chat stream (Plan C.2, C.5).

    POST /agents/chat/stream                                   → a new request's events
    GET  /agents/chat/stream/{client_request_id}?after=<seq>   → the rest of a request
    POST /agents/writes/{write_id}/confirm                     → log a pending write

POST runs stages 1–8: intake, the crisis check (before the session, so a crisis gets
helplines even without one), the session and CSRF check, the payload, admission and the
image. Then the request runs on its own (`orchestration.worker`): a dropped connection
doesn't stop it, and the phone reconnects with GET (Part E #34). A repeated
`client_request_id` attaches to the request it names instead of starting another.

GET is the reconnect: the events the phone missed after `seq` (or the `Last-Event-ID`
header), then the live ones, until the terminal event. It takes no lease, counts
nowhere and costs nothing.

Confirm (C.17, accounts): a write held after a web search or for a conflict with the
profile is gated again against the profile as it is now, then logged with its warnings,
in one transaction. The body may name what the person left out (`{"left_out":
["peanut"]}`, from the event's `attributes`). A repeat gets the first answer. Guests
confirm in the browser, which keeps their logs.
"""

import json
import uuid

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from app.agents.schemas import CONTRACT_VERSION, ChatPayload, ConfirmWrite, Usage
from app.config import limits
from app.config.settings import Settings, get_settings
from app.data.state_store import StateStore
from app.data.stream_store import StreamStore
from app.dependencies import (
    get_db_sessions,
    get_principal,
    get_state_store,
    get_stream_store,
)
from app.guardrails.crisis import CrisisMatch, crisis_check
from app.observability.tracer import Trace
from app.orchestration import worker
from app.orchestration.admission import admit
from app.orchestration.composer import Composer, confirmation, trace_view
from app.orchestration.coordinator import ChatJob
from app.orchestration.principal import Principal, check_csrf, resolve_principal
from app.orchestration.services import Services, get_services
from app.orchestration.staging import (
    UNCHECKABLE,
    confirm_attributes,
    held_entry,
    recheck,
    with_left_out,
)
from app.orchestration.stream import LiveSink, SavedSink, follow, sse_response
from app.providers import ImageInput
from app.routers.errors import ApiError
from app.routers.intake import clean_image, read_chat_request
from app.storage.context import Sessions, load_profile
from app.storage.logs import insert_log

router = APIRouter(prefix="/agents/chat", tags=["chat"])
writes_router = APIRouter(prefix="/agents/writes", tags=["chat"])

NO_USAGE = Usage(tokens_in=0, tokens_out=0, cost_usd=0.0)


@router.post("/stream")
async def chat_stream(
    request: Request,
    store: StateStore = Depends(get_state_store),
    streams: StreamStore = Depends(get_stream_store),
    settings: Settings = Depends(get_settings),
    services: Services = Depends(get_services),
    sessions: Sessions = Depends(get_db_sessions),
) -> StreamingResponse:
    if worker.draining():
        raise ApiError(503, "server_busy", "Holos is restarting. Please try again in a few "
                       "seconds.", retry_after=5)
    intake = await read_chat_request(request)  # 2
    match = crisis_check(intake.message)  # 3
    if match.matched:
        return await _crisis_stream(request, store, settings, match)
    principal = await resolve_principal(request, store, settings)  # 4
    if principal is None:
        raise ApiError(401, "no_session", "Your session has ended. Please sign in again.")
    check_csrf(request, principal, settings)
    payload = _payload(intake.payload, principal)  # 5
    try:  # 6
        admitted = await admit(principal, payload.client_request_id, store,
                               settings.tavily_billing_day, breaker=services.breaker)
    except ApiError as refused:
        if refused.code == "duplicate_request":
            return await _attach(streams, principal, payload.client_request_id, refused)
        raise
    try:  # 7
        image = (ImageInput(await clean_image(intake.image), "image/jpeg")
                 if intake.image else None)
    except BaseException:
        await admitted.release()
        raise
    # 8: the stream opens; the request runs on its own from here
    trace_id = admitted.trace_id
    live = LiveSink()
    composer = Composer(trace_id, principal.mode, SavedSink(streams, trace_id, live))
    trace = Trace(trace_id, listener=composer.on_trace_step)
    job = ChatJob(principal=principal, payload=payload, admitted=admitted, composer=composer,
                  trace=trace, store=store, sessions=sessions, image=image)
    worker.spawn(worker.run_job(job, services, streams, payload.contract_version))
    return sse_response(live.events())


@router.get("/stream/{client_request_id}")
async def reconnect(
    client_request_id: uuid.UUID,
    request: Request,
    after: int = Query(default=-1, ge=-1),
    principal: Principal = Depends(get_principal),
    streams: StreamStore = Depends(get_stream_store),
) -> StreamingResponse:
    last_seen = request.headers.get("last-event-id", "")
    if last_seen.isdigit():
        after = max(after, int(last_seen))
    state = await streams.find(principal.principal_key, client_request_id)
    if state is None:  # someone else's request looks like no request
        raise ApiError(404, "not_found", "There is no such request.")
    if state.finished and not await streams.after(state.trace_id, -1):
        raise ApiError(410, "expired", "This answer is no longer available. Please ask again.")
    return sse_response(follow(streams, state.trace_id, after))


@writes_router.post("/{write_id}/confirm")
async def confirm_write(
    write_id: uuid.UUID,
    body: ConfirmWrite | None = Body(default=None),
    principal: Principal = Depends(get_principal),
    store: StateStore = Depends(get_state_store),
    sessions: Sessions = Depends(get_db_sessions),
) -> JSONResponse:
    user_id = principal.user_id
    if user_id is None:  # a guest's pending entries live in the browser
        raise ApiError(404, "not_found", "There is no such entry to confirm.")
    left_out = set(body.left_out) if body else set()

    async def regate(payload: dict) -> str | None:
        write = held_entry(payload["kind"], payload)
        if write is None:
            return UNCHECKABLE
        if not left_out <= set(confirm_attributes(write)):
            # Raised inside the transaction: it rolls back and the write stays pending
            raise ApiError(400, "bad_request", "Only what the warning names can be left out.")
        # Read under the row lock, so the check sees the profile as late as it can
        return recheck(write, (await load_profile(sessions, user_id)).profile)

    async def commit(session, payload: dict) -> dict:
        write = with_left_out(held_entry(payload["kind"], payload), left_out)
        log_id = await insert_log(session, user_id, write)
        return {"writes": [confirmation(write, str(log_id), "account")]}

    result = await store.confirm_write(write_id, user_id, regate, commit)
    return JSONResponse(result.body, status_code=result.status_code)


def _payload(raw: dict, principal: Principal) -> ChatPayload:
    """C.2 stage 5: the payload, its contract version and the storage mode's rules."""
    version = raw.get("contract_version")
    if isinstance(version, int) and version < CONTRACT_VERSION - 1:
        raise ApiError(400, "upgrade_required", "Holos has been updated. Please reload.")
    try:
        payload = ChatPayload.model_validate(raw)
    except ValidationError:
        raise ApiError(400, "bad_request", "The message couldn't be read.") from None
    if payload.contract_version > CONTRACT_VERSION:
        raise ApiError(400, "bad_request", "Unknown contract version.")
    if principal.user_id is not None:
        if payload.guest_profile is not None or payload.guest_history is not None:
            raise ApiError(400, "bad_request", "An account's profile and history are "
                           "kept by Holos, not sent with the message.")
    elif payload.guest_profile is not None:
        size = len(json.dumps(payload.guest_profile.model_dump(mode="json")).encode())
        if size > limits.GUEST_PROFILE_BYTES:
            raise ApiError(400, "bad_request", "The profile is too long.")
    return payload


async def _attach(streams: StreamStore, principal: Principal, client_request_id: uuid.UUID,
                  refused: ApiError) -> StreamingResponse:
    """A repeated `client_request_id`: the request it names, from the start (#34)."""
    state = await streams.find(principal.principal_key, client_request_id)
    if state is None:
        raise refused
    return sse_response(follow(streams, state.trace_id, -1))


async def _crisis_stream(request: Request, store: StateStore, settings: Settings,
                         match: CrisisMatch) -> StreamingResponse:
    """Stage 3: the signed-off text and helplines, with no session needed and no LLM
    call. The flag is set only for a request that passes the session and CSRF check
    (C.16); a failed check never blocks the helplines. Not saved: it is complete at
    once."""
    principal = await resolve_principal(request, store, settings)
    mode = principal.mode if principal is not None else "guest"
    if principal is not None:
        try:
            check_csrf(request, principal, settings)
        except ApiError:
            pass
        else:
            await store.set_crisis(principal.principal_key)
    trace_id = uuid.uuid4().hex
    trace = Trace(trace_id)
    trace.step("crisis", detail=match.rule_id or "")  # the rule, never the message
    live = LiveSink()
    composer = Composer(trace_id, mode, live)
    await composer.accepted(CONTRACT_VERSION)
    await composer.crisis()
    await composer.done(trace_view(trace, "crisis", [], [], [], NO_USAGE), NO_USAGE)
    return sse_response(live.events())
