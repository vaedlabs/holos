"""The chat stream (Plan C.5). P4.7 adds `POST /agents/chat/stream`.

    GET /agents/chat/stream/{client_request_id}?after=<seq>   → the rest of a request

A reconnect (Part E #34): the events the phone missed after `seq` (or the
`Last-Event-ID` header), then the live ones, until the terminal event. It takes no
lease, counts nowhere and costs nothing: the request is already running or done.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from app.data.stream_store import StreamStore
from app.dependencies import get_principal, get_stream_store
from app.orchestration.principal import Principal
from app.orchestration.stream import follow, sse_response
from app.routers.errors import ApiError

router = APIRouter(prefix="/agents/chat", tags=["chat"])


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
