"""OpenAIProvider maps errors that arrive inside a stream (Part E #35). Live, 29 Oct 2026:
an `error` event mid-stream came out of the SDK as a bare openai.APIError and escaped
unmapped, so the request crashed instead of being retried. Every result and error
carries OpenAI's request ID (Part E #39)."""

import json

import httpx
import pytest

from app.agents.schemas import MentalReply
from app.providers import BadRequest, GenerateOptions, ProviderUnavailable, Turn
from app.providers.openai import OpenAIProvider

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


def _sse(*events: dict) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def _provider(body: bytes, status: int = 200) -> OpenAIProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        kind = "text/event-stream" if status == 200 else "application/json"
        return httpx.Response(status, content=body,
                              headers={"content-type": kind, "x-request-id": "req_abc"})
    return OpenAIProvider("test-key", http_client=httpx.AsyncClient(
        transport=httpx.MockTransport(handler)))


async def _generate(provider, progress=None, opened=None):
    return await provider.generate([Turn("user", "hi")],
                                   options=GenerateOptions(model="m", max_output_tokens=50),
                                   schema=MentalReply, progress=progress, opened=opened)


CREATED = {"type": "response.created", "sequence_number": 0,
           "response": {"id": "r", "object": "response", "created_at": 0,
                        "status": "in_progress", "model": "m", "output": [],
                        "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}}


async def test_an_error_event_mid_stream_is_retryable():
    body = _sse({"type": "response.created", "sequence_number": 0,
                 "response": {"id": "r", "object": "response", "created_at": 0,
                              "status": "in_progress", "model": "m", "output": [],
                              "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}},
                # As OpenAI sends it: the SDK raises a bare APIError for a nested "error"
                {"type": "error", "sequence_number": 1,
                 "error": {"type": "server_error", "code": "server_error",
                           "message": "An error occurred while processing your request."}})
    events = []
    with pytest.raises(ProviderUnavailable) as caught:
        await _generate(_provider(body), events.append)
    assert caught.value.retryable and events[:1] == [False]
    assert caught.value.request_id == "req_abc"


async def test_a_stream_that_ends_without_a_reply_is_retryable():
    with pytest.raises(ProviderUnavailable, match="ended without a reply"):
        await _generate(_provider(b""))


async def test_the_request_id_is_reported_when_the_headers_arrive():
    opened = []
    with pytest.raises(ProviderUnavailable) as caught:
        await _generate(_provider(_sse(CREATED)), opened=opened.append)
    assert opened == ["req_abc"] and caught.value.request_id == "req_abc"


async def test_a_refused_call_carries_its_request_id_and_status():
    body = json.dumps({"error": {"message": "bad", "type": "invalid_request_error"}}).encode()
    with pytest.raises(BadRequest) as caught:
        await _generate(_provider(body, status=400))
    assert caught.value.request_id == "req_abc" and caught.value.status == 400
    assert caught.value.cause == "bad_request"
