"""One error body for every route: `{code, message}` (C.2, `routers/errors.py`), plus
`details` on a 422 (Part E #57). No body carries an exception's text; the log does.

    HTTPException (Starlette's 404 and 405 too)  → its status, a code for the status
    RequestValidationError                        → 422 bad_request with the field list
    database refused, timed out or pool full      → 503 server_busy, Retry-After (#55)
    anything else                                 → 500 server_error
"""

import logging
from http import HTTPStatus

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)
DATABASE_RETRY_AFTER_S = 5

CODES = {400: "bad_request", 401: "no_session", 403: "forbidden", 404: "not_found",
         405: "method_not_allowed", 409: "conflict", 410: "expired", 413: "too_large",
         415: "unsupported_media", 429: "too_many_requests", 503: "server_busy"}


def register_error_handlers(app) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
        logger.log(level, "HTTP %d on %s %s: %s", exc.status_code, request.method,
                   request.url.path, exc.detail)
        message = exc.detail if isinstance(exc.detail, str) else _phrase(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": CODES.get(exc.status_code, "error"), "message": message},
            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        # A custom validator's error carries the exception object: encode it as text, or
        # the handler itself fails into a CORS-less 500 (Part E #16)
        details = jsonable_encoder(exc.errors(), custom_encoder={BaseException: str})
        logger.warning("Validation error on %s %s: %s", request.method, request.url.path,
                       details)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"code": "bad_request", "message": "Some of what was sent isn't valid.",
                     "details": details})

    async def database_unavailable(request: Request, exc: Exception):
        """The database refused, timed out or has no free connection (failure library,
        Part E #55): a moment's wait, not a bug. Handled inside the middleware, so CORS
        and the security headers are on the response."""
        logger.error("database unavailable on %s %s: %s", request.method, request.url.path,
                     type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"code": "server_busy", "message": "Holos is busy right now. "
                     "Please try again in a few seconds."},
            headers={"Retry-After": str(DATABASE_RETRY_AFTER_S)})

    for error in (OperationalError, InterfaceError, PoolTimeout):
        app.add_exception_handler(error, database_unavailable)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        # Starlette runs this handler outside every add_middleware layer, so the
        # security headers and CORS (for the app's origin) are added here
        from app.config.settings import get_settings
        from app.middleware.headers import HEADERS

        headers = dict(HEADERS)
        origin = request.headers.get("origin")
        if origin and origin == get_settings().app_origin:
            headers.update({"Access-Control-Allow-Origin": origin,
                            "Access-Control-Allow-Credentials": "true", "Vary": "Origin"})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "server_error",
                     "message": "Something went wrong. Please try again."},
            headers=headers)


def _phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase + "."
    except ValueError:
        return "Something went wrong."
