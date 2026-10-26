"""Request intake for the chat endpoint (Plan C.7, C.2 stages 2 and 7).

    intake = await read_chat_request(request)   # stage 2: size caps, in-memory parse
    jpeg = await clean_image(intake.image)      # stage 7: after admission

The body is counted as it arrives and cut off at 7 MB. The multipart parse keeps
everything in memory (one `payload` field, at most one `image` file) and never
decodes the image, so a request that admission refuses costs no image work.
Image processing runs in a thread behind its own limiter: the format is detected
from the content, decompression bombs are refused, the longest side is resized to
1024 px and the result is re-encoded as JPEG without EXIF.
"""

import io
import json
import re
import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

import anyio
from PIL import Image, ImageOps, UnidentifiedImageError
from python_multipart.exceptions import FormParserError
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect, Request

from app.config import limits

from .errors import ApiError

PAYLOAD_FIELD = "payload"
IMAGE_FIELD = "image"
PAYLOAD_MAX_BYTES = 64 * 1024
SPOOL_MAX_BYTES = 8 * 1024 * 1024  # above the body cap, so nothing ever rolls over to disk
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
JPEG_QUALITY = 85
IMAGE_THREADS = 2  # concurrent image decodes; each can hold ~100 MB at 25 MP
MAX_IMAGE_PIXELS = 25_000_000
# ASCII digits only: str.isdigit() accepts "²" and "５", and int("²") raises
_CONTENT_LENGTH = re.compile(r"[0-9]{1,15}")

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
_image_limiter = anyio.CapacityLimiter(IMAGE_THREADS)


def _too_large(what: str, limit: int) -> ApiError:
    return ApiError(413, "too_large", f"The {what} is larger than {limit // (1024 * 1024)} MB.")


def _bad_request(message: str) -> ApiError:
    return ApiError(400, "bad_request", message)


@dataclass(frozen=True)
class ChatIntake:
    payload: dict[str, Any]  # parsed JSON; ChatPayload validates it at stage 5
    image: bytes | None  # raw upload, not decoded

    @property
    def message(self) -> str:
        """The message for the crisis check (stage 3), before the payload is validated."""
        message = self.payload.get("message")
        return message if isinstance(message, str) else ""


class _ChatParser(MultiPartParser):
    """One `payload` field and at most one `image` file, all in memory."""

    spool_max_size = SPOOL_MAX_BYTES

    def __init__(self, request: Request, stream: AsyncGenerator[bytes, None]):
        super().__init__(request.headers, stream, max_files=1, max_fields=1,
                         max_part_size=PAYLOAD_MAX_BYTES)
        self.image_bytes = 0
        self.finished = False

    def on_end(self) -> None:
        # python-multipart calls this only at the closing boundary, and its finalize()
        # doesn't check, so a body cut off mid-part would otherwise parse as if the
        # unfinished part had never been sent
        self.finished = True

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._current_part.file is not None:
            self.image_bytes += end - start
            if self.image_bytes > limits.IMAGE_UPLOAD_BYTES:
                raise _too_large("image", limits.IMAGE_UPLOAD_BYTES)
        super().on_part_data(data, start, end)


async def _counted(request: Request) -> AsyncGenerator[bytes, None]:
    """The body, stopped as soon as it passes the cap, whatever Content-Length said."""
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limits.REQUEST_BODY_BYTES:
            raise _too_large("request", limits.REQUEST_BODY_BYTES)
        yield chunk


async def read_chat_request(request: Request) -> ChatIntake:
    """C.2 stage 2. Raises ApiError 413 or 400."""
    declared = request.headers.get("content-length")
    if declared is not None:
        if not _CONTENT_LENGTH.fullmatch(declared):
            raise _bad_request("Content-Length is not a number.")
        if int(declared) > limits.REQUEST_BODY_BYTES:
            raise _too_large("request", limits.REQUEST_BODY_BYTES)
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise _bad_request("Send the chat request as multipart/form-data.")

    parser = _ChatParser(request, _counted(request))
    try:
        form = await parser.parse()
    except MultiPartException as exc:
        raise _bad_request(f"Malformed form data: {exc.message}") from None
    except FormParserError:  # python-multipart's own errors: bad boundary, broken framing
        raise _bad_request("Malformed form data.") from None
    except ClientDisconnect:
        raise _bad_request("The request ended early.") from None
    if not parser.finished:
        raise _bad_request("The request ended early.")

    payload_text, image = None, None
    for name, value in form.multi_items():
        if name == PAYLOAD_FIELD and isinstance(value, str):
            payload_text = value
        elif name == IMAGE_FIELD and not isinstance(value, str):
            image = await value.read()
            await value.close()
        else:
            raise _bad_request(f"Unexpected form part '{name[:40]}'.")
    if payload_text is None:
        raise _bad_request("The form has no 'payload' field.")
    try:
        payload = json.loads(payload_text)
    except (ValueError, RecursionError):  # RecursionError: deeply nested arrays
        raise _bad_request("The payload is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise _bad_request("The payload must be a JSON object.")
    if image is not None and not image:
        raise _bad_request("The image is empty.")
    return ChatIntake(payload, image)


def _unsupported() -> ApiError:
    return ApiError(415, "unsupported_image", "Send a JPEG, PNG or WebP photo.")


def _clean(data: bytes) -> bytes:
    try:
        # The exact cap below refuses what Pillow only warns about, so silence the warning
        with (warnings.catch_warnings(action="ignore", category=Image.DecompressionBombWarning),
              Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS) as img):
            # Pillow errors above 2x its MAX_IMAGE_PIXELS but only warns between 1x and 2x;
            # this exact cap, read from the header, also holds if other code changes the global
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise _unsupported()
            img = ImageOps.exif_transpose(img)  # keep the photo upright once EXIF is gone
            img.thumbnail((limits.IMAGE_MAX_SIDE_PX, limits.IMAGE_MAX_SIDE_PX))
            if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
                rgba = img.convert("RGBA")
                img = Image.new("RGB", rgba.size, "white")
                img.paste(rgba, mask=rgba.getchannel("A"))
            img = img.convert("RGB")
            img.info.clear()  # JPEG comments and other metadata would be written back
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=JPEG_QUALITY)
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, OSError, ValueError, SyntaxError):
        raise _unsupported() from None
    return out.getvalue()


async def clean_image(data: bytes) -> bytes:
    """C.2 stage 7, after admission. Raises ApiError 415."""
    return await anyio.to_thread.run_sync(_clean, data, limiter=_image_limiter)
