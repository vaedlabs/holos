"""Record and replay provider HTTP traffic (Plan P2.3), so contract tests need no network.

Both SDKs accept a custom httpx client; these transports sit underneath them.

* Recording keeps method, path, the JSON request body and the response (status,
  body, retry-after). Request headers are never stored and `key=` is stripped from
  URLs, so no API key reaches a fixture file.
* Replay serves the saved responses in order and checks that our request matches the
  recorded one exactly. A change to how a provider builds requests then fails the
  contract test until the fixture is recorded again.
"""

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "providers"
KEEP_RESPONSE_HEADERS = ("content-type", "retry-after")


def _path(url: httpx.URL) -> str:
    parts = urlsplit(str(url))
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.lower() != "key"]
    return parts.path + (f"?{urlencode(query)}" if query else "")


def _body(content: bytes) -> Any:
    if not content:
        return None
    try:
        return json.loads(content)
    except ValueError:
        return content.decode("utf-8", "replace")


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self._inner = httpx.AsyncHTTPTransport()
        self.exchanges: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        content = await response.aread()  # decoded (gzip removed)
        self.exchanges.append({
            "request": {"method": request.method, "path": _path(request.url),
                        "body": _body(request.content)},
            "response": {"status": response.status_code,
                         "headers": {k: v for k, v in response.headers.items()
                                     if k.lower() in KEEP_RESPONSE_HEADERS},
                         "body": _body(content)},
        })
        headers = [(k, v) for k, v in response.headers.items()
                   if k.lower() not in ("content-encoding", "content-length",
                                        "transfer-encoding")]
        return httpx.Response(response.status_code, headers=headers, content=content,
                              request=request)

    async def aclose(self) -> None:
        await self._inner.aclose()


class ReplayTransport(httpx.AsyncBaseTransport):
    def __init__(self, exchanges: list[dict[str, Any]], check_body: bool = True):
        self._exchanges = list(exchanges)
        self._check_body = check_body
        self.requests: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        sent = {"method": request.method, "path": _path(request.url),
                "body": _body(request.content)}
        self.requests.append(sent)
        if not self._exchanges:
            raise AssertionError(f"unexpected request with no recorded exchange: {sent['path']}")
        recorded = self._exchanges.pop(0)
        want = recorded["request"]
        assert (sent["method"], sent["path"]) == (want["method"], want["path"]), (
            f"request {sent['method']} {sent['path']} != recorded {want['method']} {want['path']}"
        )
        if self._check_body and want.get("body") is not None:
            assert sent["body"] == want["body"], "request body differs from the recording"
        response = recorded["response"]
        body = response["body"]
        content = (json.dumps(body) if not isinstance(body, str) else body).encode()
        headers = dict(response.get("headers", {}))
        headers.setdefault("content-type", "application/json")
        return httpx.Response(response["status"], headers=headers, content=content,
                              request=request)

    @property
    def remaining(self) -> int:
        return len(self._exchanges)


class RaisingTransport(httpx.AsyncBaseTransport):
    """Raises a transport error, e.g. httpx.ReadTimeout, for error-mapping tests."""

    def __init__(self, error: Exception):
        self._error = error

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise self._error


def fixture_path(provider: str, scenario: str) -> Path:
    return FIXTURES / provider / f"{scenario}.json"


def load(provider: str, scenario: str) -> list[dict[str, Any]]:
    return json.loads(fixture_path(provider, scenario).read_text(encoding="utf-8"))


def save(provider: str, scenario: str, exchanges: list[dict[str, Any]]) -> Path:
    path = fixture_path(provider, scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(exchanges, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
