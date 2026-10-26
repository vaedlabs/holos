"""Chat request intake (Plan C.7, P4.1): size caps, an in-memory parse, image cleaning.

The app is called through raw ASGI, so a test controls Content-Length and the body
chunks exactly, including a body that lies about its length.
"""

import base64
import io
import json
import struct
import tempfile
import zlib

import pytest
from fastapi import FastAPI, Request
from PIL import Image, PngImagePlugin

from app.config import limits
from app.routers import intake
from app.routers.errors import ApiError, api_error_handler
from app.routers.intake import clean_image, read_chat_request

pytestmark = pytest.mark.asyncio

MB = 1024 * 1024
BOUNDARY = "holosboundary"
PAYLOAD = {"message": "Is this a good lunch?", "client_request_id": "x", "contract_version": 1}


def make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)

    @app.post("/chat")
    async def chat(request: Request):
        got = await read_chat_request(request)
        out = {"payload": got.payload, "message": got.message,
               "image_bytes": len(got.image) if got.image else None}
        if got.image and request.query_params.get("clean"):
            out["jpeg"] = base64.b64encode(await clean_image(got.image)).decode()
        return out

    return app


APP = make_app()


def form(payload=PAYLOAD, image: bytes | None = None, filename="photo.jpg",
         extra: list[tuple[str, bytes, str | None]] = ()) -> bytes:
    """A multipart body: the payload field, an optional image, any extra parts."""
    parts = []
    if payload is not None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        parts.append(("payload", text.encode(), None))
    if image is not None:
        parts.append(("image", image, filename))
    parts += list(extra)
    out = b""
    for name, data, fname in parts:
        disposition = f'form-data; name="{name}"' + (f'; filename="{fname}"' if fname else "")
        out += f"--{BOUNDARY}\r\nContent-Disposition: {disposition}\r\n".encode()
        if fname:
            out += b"Content-Type: image/jpeg\r\n"
        out += b"\r\n" + data + b"\r\n"
    return out + f"--{BOUNDARY}--\r\n".encode()


class Sent:
    status: int
    body: dict
    chunks_read: int
    bytes_read: int


async def post(body: bytes, *, content_length: int | None | str = "auto",
               content_type=f"multipart/form-data; boundary={BOUNDARY}",
               query: str = "", chunk=64 * 1024, disconnect_after: int | None = None) -> Sent:
    """Call the app with exact headers and body chunks; count how much it read."""
    headers = [(b"content-type", content_type.encode())]
    if content_length == "auto":
        content_length = len(body)
    if content_length is not None:
        value = str(content_length)  # HTTP header bytes are latin-1, as Starlette decodes them
        headers.append((b"content-length", value.encode("latin-1", errors="backslashreplace")))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/chat", "raw_path": b"/chat",
             "query_string": query.encode(), "headers": headers,
             "client": ("127.0.0.1", 5000), "server": ("test", 80)}
    sent, pieces = Sent(), [body[i:i + chunk] for i in range(0, len(body), chunk)] or [b""]
    sent.chunks_read = sent.bytes_read = 0
    response = []

    async def receive():
        if disconnect_after is not None and sent.chunks_read >= disconnect_after:
            return {"type": "http.disconnect"}
        if sent.chunks_read < len(pieces):
            piece = pieces[sent.chunks_read]
            sent.chunks_read += 1
            sent.bytes_read += len(piece)
            return {"type": "http.request", "body": piece,
                    "more_body": sent.chunks_read < len(pieces)}
        return {"type": "http.disconnect"}

    async def send(message):
        response.append(message)

    await APP(scope, receive, send)
    sent.status = response[0]["status"]
    sent.body = json.loads(b"".join(m.get("body", b"") for m in response[1:]))
    return sent


def image_bytes(fmt="JPEG", size=(64, 48), mode="RGB", color=(200, 30, 30), **save) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format=fmt, **save)
    return out.getvalue()


def png_claiming(width: int, height: int) -> bytes:
    """A tiny PNG whose header claims a huge size: a decompression bomb."""
    png = bytearray(image_bytes("PNG", (8, 8)))
    ihdr = 8 + 8  # signature, then length and type of the IHDR chunk
    png[ihdr:ihdr + 8] = struct.pack(">II", width, height)
    crc = zlib.crc32(bytes(png[ihdr - 4:ihdr + 13]))  # type and data
    png[ihdr + 13:ihdr + 17] = struct.pack(">I", crc)
    return bytes(png)


def decoded(result: Sent) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(result.body["jpeg"])))


# --- Size caps ---


async def test_declared_length_over_the_cap_is_refused_unread():
    result = await post(b"x" * 100, content_length=8 * MB)
    assert result.status == 413
    assert result.body["code"] == "too_large"
    assert result.chunks_read == 0


async def test_a_body_that_lies_about_its_length_is_cut_off_at_7_mb():
    body = form(image=b"\xff\xd8" + b"x" * (8 * MB))
    result = await post(body, content_length=1000)
    assert result.status == 413
    assert result.bytes_read <= limits.REQUEST_BODY_BYTES + 64 * 1024


async def test_the_body_counter_works_without_an_image_part():
    # Data after the closing boundary is skipped by the parser, so only the counter stops it
    body = form(image=image_bytes()) + b"x" * (8 * MB)
    result = await post(body, content_length=1000)
    assert result.status == 413
    assert result.bytes_read <= limits.REQUEST_BODY_BYTES + 64 * 1024


async def test_a_body_without_length_is_counted_too():
    result = await post(form(image=b"x" * (8 * MB)), content_length=None)
    assert result.status == 413
    assert result.bytes_read <= limits.REQUEST_BODY_BYTES + 64 * 1024


async def test_an_image_over_5_mb_is_refused():
    result = await post(form(image=b"x" * (limits.IMAGE_UPLOAD_BYTES + 1)))
    assert result.status == 413
    assert "image" in result.body["message"]


async def test_bad_content_length():
    assert (await post(form(), content_length="12abc")).status == 400


# --- In memory, not decoded ---


async def test_a_5_mb_jpeg_creates_no_temporary_file(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("intake must not create a temporary file")

    for name in ("TemporaryFile", "NamedTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, refuse)
    jpeg = image_bytes("JPEG", (640, 480))
    jpeg += b"\0" * (limits.IMAGE_UPLOAD_BYTES - len(jpeg) - 1024)  # readers ignore the tail
    result = await post(form(image=jpeg), query="clean=1")
    assert result.status == 200, result.body
    assert result.body["image_bytes"] == len(jpeg)
    assert decoded(result).size == (640, 480)


async def test_the_parse_does_not_decode_the_image(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the parse must not decode the image")

    monkeypatch.setattr(Image, "open", refuse)
    monkeypatch.setattr(intake.Image, "open", refuse)
    result = await post(form(image=b"not even an image"))
    assert result.status == 200
    assert result.body["image_bytes"] == len(b"not even an image")


# --- Image cleaning ---


async def test_a_png_named_jpg_is_accepted_by_content():
    result = await post(form(image=image_bytes("PNG"), filename="lunch.jpg"), query="clean=1")
    assert result.status == 200
    assert decoded(result).format == "JPEG"


async def test_webp_is_accepted():
    result = await post(form(image=image_bytes("WEBP"), filename="x.webp"), query="clean=1")
    assert result.status == 200


@pytest.mark.parametrize("data", [
    b"hello, I am a text file",
    image_bytes("GIF"),  # a real image, but not an allowed format
    image_bytes("BMP"),
    image_bytes("JPEG")[:200],  # truncated
])
async def test_other_content_is_unsupported(data):
    result = await post(form(image=data, filename="photo.jpg"), query="clean=1")
    assert result.status == 415
    assert result.body["code"] == "unsupported_image"


async def test_a_decompression_bomb_is_unsupported():
    # Over 2x MAX_IMAGE_PIXELS: Pillow refuses at open, from the header alone
    bomb = png_claiming(50_000, 50_000)
    assert len(bomb) < 1024
    assert (await post(form(image=bomb), query="clean=1")).status == 415


async def test_an_image_between_1x_and_2x_the_pixel_cap_is_unsupported():
    # 36 MP: Pillow only warns here; a real, decodable image, so only the warning stops it
    big = image_bytes("PNG", (6_000, 6_000), mode="1", color=1)
    assert len(big) < limits.IMAGE_UPLOAD_BYTES
    assert (await post(form(image=big), query="clean=1")).status == 415


async def test_output_has_no_exif_and_fits_1024_px():
    exif = Image.Exif()
    exif[0x8825] = {2: (51, 30, 0), 4: (0, 7, 0)}  # GPSInfo: latitude, longitude
    exif[0x010F] = "Phone maker"
    jpeg = image_bytes("JPEG", (3000, 1500), exif=exif.tobytes())
    assert Image.open(io.BytesIO(jpeg)).getexif().get(0x8825)  # the fixture really has GPS
    result = await post(form(image=jpeg), query="clean=1")
    out = decoded(result)
    assert out.size == (1024, 512)
    assert not out.getexif()
    assert b"Exif" not in base64.b64decode(result.body["jpeg"])


async def test_rotation_from_exif_is_applied_before_it_is_removed():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees
    jpeg = image_bytes("JPEG", (200, 100), exif=exif.tobytes())
    assert decoded(await post(form(image=jpeg), query="clean=1")).size == (100, 200)


async def test_transparency_becomes_white():
    png = image_bytes("PNG", (10, 10), mode="RGBA", color=(0, 0, 0, 0))
    out = decoded(await post(form(image=png), query="clean=1")).convert("RGB")
    assert min(out.getpixel((5, 5))) > 245


# --- Form shape ---


@pytest.mark.parametrize("body", [
    form(payload=None),  # no payload
    form(payload="{not json"),
    form(payload="[1, 2]"),  # not an object
    form(image=b""),  # empty image
    form(extra=[("note", b"hi", None)]),  # a second field
    form(image=b"a", extra=[("image2", b"b", "b.jpg")]),  # a second file
    form(payload=None, extra=[("payload", b"{}", "payload.json")]),  # payload sent as a file
    form(extra=[("photo", b"x", "a.jpg")]),  # the one file under the wrong name
    form(payload="x" * (65 * 1024)),  # payload over 64 KB
    b"--" + BOUNDARY.encode() + b"\r\ngarbage without headers",
])
async def test_malformed_forms_are_400(body):
    result = await post(body)
    assert result.status == 400
    assert set(result.body) == {"code", "message"}


@pytest.mark.parametrize("cut", [20, 200, 5000])
async def test_a_body_cut_off_before_the_closing_boundary_is_400(cut):
    # Found by a live probe on uvicorn: a short body parsed as text-only, dropping the image
    body = form(image=image_bytes("JPEG", (300, 200)))
    result = await post(body[:-cut])
    assert result.status == 400
    assert result.body["message"] == "The request ended early."


async def test_wrong_content_type_is_400():
    result = await post(b'{"message": "hi"}', content_type="application/json")
    assert result.status == 400


async def test_message_is_available_before_validation():
    # The crisis check (stage 3) runs before the payload is validated (stage 5)
    result = await post(form(payload={"message": "I want to die", "contract_version": "bad"}))
    assert result.status == 200
    assert result.body["message"] == "I want to die"
    assert (await post(form(payload={"message": 7}))).body["message"] == ""


async def test_image_work_has_its_own_limiter():
    assert intake._image_limiter.total_tokens == intake.IMAGE_THREADS


# --- Edges: exact limits ---


def padded_to(total: int, image=b"") -> bytes:
    """A valid form padded after the closing boundary (which the parser skips) to `total`."""
    body = form(image=image or image_bytes())
    return body + b"x" * (total - len(body))


async def test_a_body_of_exactly_7_mb_is_accepted():
    assert (await post(padded_to(limits.REQUEST_BODY_BYTES))).status == 200
    assert (await post(padded_to(limits.REQUEST_BODY_BYTES + 1))).status == 413


async def test_counted_body_of_exactly_7_mb_is_accepted():
    body = padded_to(limits.REQUEST_BODY_BYTES)
    assert (await post(body, content_length=None)).status == 200
    assert (await post(body + b"x", content_length=None)).status == 413


async def test_an_image_of_exactly_5_mb_is_accepted():
    jpeg = image_bytes()
    jpeg += b"\0" * (limits.IMAGE_UPLOAD_BYTES - len(jpeg))
    result = await post(form(image=jpeg))
    assert result.status == 200
    assert result.body["image_bytes"] == limits.IMAGE_UPLOAD_BYTES


async def test_a_payload_of_exactly_64_kb_is_accepted():
    text = json.dumps({"message": ""})
    text = text[:-2] + "x" * (intake.PAYLOAD_MAX_BYTES - len(text)) + '"}'
    assert len(text.encode()) == intake.PAYLOAD_MAX_BYTES
    assert (await post(form(payload=text))).status == 200
    assert (await post(form(payload=text[:-2] + 'x"}'))).status == 400


@pytest.mark.parametrize("value", [
    "²",  # latin-1 superscript two: isdigit() is true, int() raises
    "５",  # full-width five
    "-1", "+5", " 5", "", "1e3", "0x10", "9" * 40,
])
async def test_odd_content_length_is_400_or_413_never_500(value):
    result = await post(form(), content_length=value)
    assert result.status in (400, 413)
    assert set(result.body) == {"code", "message"}


async def test_content_length_zero_and_an_empty_body_are_400():
    assert (await post(b"", content_length=0)).status == 400
    assert (await post(b"", content_length=None)).status == 400


# --- Edges: form shape ---


async def test_content_type_is_case_insensitive():
    result = await post(form(), content_type=f"Multipart/Form-Data; boundary={BOUNDARY}")
    assert result.status == 200


@pytest.mark.parametrize("content_type", ["multipart/form-data", "", "text/plain"])
async def test_missing_boundary_or_content_type_is_400(content_type):
    assert (await post(form(), content_type=content_type)).status == 400


async def test_parts_may_come_in_any_order():
    body = form(payload=None, image=image_bytes(),
                extra=[("payload", json.dumps(PAYLOAD).encode(), None)])
    result = await post(body)
    assert result.status == 200
    assert result.body["payload"] == PAYLOAD


async def test_a_preamble_before_the_first_boundary_is_400():
    # RFC 2046 allows a preamble, browsers never send one, python-multipart refuses it
    result = await post(b"This is a preamble.\r\n" + form())
    assert result.status == 400
    assert result.body["message"] == "Malformed form data."


async def test_an_image_sent_without_a_filename_is_400():
    # Without a filename the part is a text field, and only one field is allowed
    body = form(payload=None, extra=[("image", image_bytes(), None)])
    assert (await post(body)).status == 400


async def test_a_part_without_a_name_is_400():
    body = (f"--{BOUNDARY}\r\nContent-Disposition: form-data\r\n\r\nx\r\n"
            f"--{BOUNDARY}--\r\n").encode()
    assert (await post(body)).status == 400


async def test_a_huge_part_header_is_refused_without_a_crash():
    header = b"X-Junk: " + b"a" * (6 * MB) + b"\r\n"
    body = (f"--{BOUNDARY}\r\n".encode() + header
            + b'Content-Disposition: form-data; name="payload"\r\n\r\n{}\r\n'
            + f"--{BOUNDARY}--\r\n".encode())
    assert (await post(body)).status in (200, 400, 413)
    assert (await post(body + b"a" * (2 * MB))).status == 413


@pytest.mark.parametrize("filename", ["../../etc/passwd", "a\0b.jpg", "x" * 5000, "名前.jpg"])
async def test_the_filename_is_ignored(filename):
    result = await post(form(image=image_bytes(), filename=filename), query="clean=1")
    assert result.status == 200
    assert not hasattr(intake.ChatIntake, "filename")


async def test_a_client_that_disconnects_mid_body_gets_400_not_500():
    body = form(image=b"x" * (2 * MB))
    assert (await post(body, disconnect_after=3)).status == 400


# --- Edges: payload JSON ---


@pytest.mark.parametrize("text", [
    "[" * 20_000,  # deep nesting: RecursionError in the JSON parser
    '{"a":' * 10_000 + "1" + "}" * 10_000,
    "﻿" + json.dumps(PAYLOAD),  # a byte-order mark
    "",
])
async def test_payload_json_edges_are_400_never_500(text):
    result = await post(form(payload=text))
    assert result.status == 400


async def test_payload_that_is_not_utf8_is_handled():
    body = form(payload=None, extra=[("payload", b'{"message": "caf\xe9"}', None)])
    assert (await post(body)).status in (200, 400)


@pytest.mark.parametrize("message", ["मैं ठीक हूँ", "😀 lunch?", "a​b", "line\nbreak"])
async def test_the_message_arrives_exactly_as_sent(message):
    result = await post(form(payload={"message": message}))
    assert result.body["message"] == message


async def test_odd_json_values_pass_intake_for_stage_5():
    # Validation is stage 5's job; intake must just not crash
    result = await post(form(payload='{"message": "hi", "x": NaN, "x": 1}'))
    assert result.status == 200


# --- Edges: image formats phones and apps produce ---


def saved(img: Image.Image, fmt: str, **kw) -> bytes:
    out = io.BytesIO()
    img.save(out, format=fmt, **kw)
    return out.getvalue()


@pytest.mark.parametrize("data", [
    saved(Image.new("L", (50, 40), 128), "PNG"),
    saved(Image.new("LA", (50, 40), (128, 255)), "PNG"),
    saved(Image.new("P", (50, 40), 0), "PNG", transparency=0),
    saved(Image.new("I;16", (50, 40), 30000), "PNG"),
    saved(Image.new("1", (50, 40), 1), "PNG"),
    saved(Image.new("CMYK", (50, 40), (0, 50, 50, 0)), "JPEG"),
    saved(Image.new("RGB", (50, 40)), "JPEG", progressive=True),
    saved(Image.new("RGBA", (50, 40), (1, 2, 3, 100)), "WEBP", lossless=True),
    saved(Image.new("RGB", (50, 40)), "WEBP", save_all=True,
          append_images=[Image.new("RGB", (50, 40), "red")]),  # animated
    saved(Image.new("RGB", (50, 40)), "PNG", save_all=True,
          append_images=[Image.new("RGB", (50, 40), "red")]),  # APNG
    saved(Image.new("RGB", (50, 40)), "MPO", save_all=True,
          append_images=[Image.new("RGB", (50, 40))]),  # multi-picture JPEG from phone cameras
], ids=["L", "LA", "P-transparent", "I16", "1-bit", "CMYK", "progressive", "webp-alpha",
        "webp-animated", "apng", "mpo"])
async def test_common_formats_become_an_rgb_jpeg(data):
    result = await post(form(image=data), query="clean=1")
    assert result.status == 200, result.body
    out = decoded(result)
    assert (out.format, out.mode, out.size) == ("JPEG", "RGB", (50, 40))


@pytest.mark.parametrize(("data", "marker"), [
    (saved(Image.new("RGB", (50, 40)), "JPEG", comment=b"SECRET note"), b"SECRET"),
    (saved(Image.new("RGB", (50, 40)), "JPEG",
           xmp=b'<x:xmpmeta xmlns:x="adobe:ns:meta/">GPS 51.5</x:xmpmeta>'), b"xmpmeta"),
    (saved(Image.new("RGB", (50, 40)), "JPEG", icc_profile=b"ICCSECRET" * 30), b"ICCSECRET"),
], ids=["comment", "xmp", "icc"])
async def test_no_metadata_survives(data, marker):
    assert marker in data  # the fixture really carries it
    result = await post(form(image=data), query="clean=1")
    jpeg = base64.b64decode(result.body["jpeg"])
    assert marker not in jpeg
    assert set(decoded(result).info) <= {"jfif", "jfif_version", "jfif_unit", "jfif_density"}


async def test_png_text_and_exif_chunks_are_dropped():
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "SECRET")
    exif = Image.Exif()
    exif[0x010F] = "SECRETMAKER"
    data = saved(Image.new("RGB", (50, 40)), "PNG", pnginfo=info, exif=exif.tobytes())
    jpeg = base64.b64decode((await post(form(image=data), query="clean=1")).body["jpeg"])
    assert b"SECRET" not in jpeg


async def test_the_pixel_cap_boundary():
    exact = saved(Image.new("1", (5_000, 5_000), 1), "PNG")  # exactly 25,000,000 pixels
    over = saved(Image.new("1", (5_000, 5_001), 1), "PNG")
    assert (await post(form(image=exact), query="clean=1")).status == 200
    assert (await post(form(image=over), query="clean=1")).status == 415


async def test_the_pixel_cap_holds_if_pillows_global_is_changed(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", None)  # some other code turned it off
    big = saved(Image.new("1", (6_000, 6_000), 1), "PNG")
    assert (await post(form(image=big), query="clean=1")).status == 415


async def test_an_extreme_aspect_ratio_keeps_at_least_one_pixel():
    data = saved(Image.new("1", (20_000, 1), 1), "PNG")
    assert decoded(await post(form(image=data), query="clean=1")).size == (1024, 1)


async def test_a_small_image_is_not_enlarged():
    assert decoded(await post(form(image=image_bytes()), query="clean=1")).size == (64, 48)


# --- Image work runs off the event loop, two at a time ---


async def test_image_cleaning_runs_two_at_a_time_off_the_loop(monkeypatch):
    import threading
    import time

    import anyio

    lock, running, peak = threading.Lock(), [0], [0]

    def slow(data: bytes) -> bytes:
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.2)
        with lock:
            running[0] -= 1
        return b"jpeg"

    monkeypatch.setattr(intake, "_clean", slow)
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await anyio.sleep(0.01)

    async with anyio.create_task_group() as group:
        group.start_soon(ticker)
        start = time.perf_counter()
        async with anyio.create_task_group() as cleaners:
            for _ in range(6):
                cleaners.start_soon(clean_image, b"x")
        elapsed = time.perf_counter() - start
        group.cancel_scope.cancel()
    assert peak[0] == intake.IMAGE_THREADS
    assert 0.55 < elapsed < 1.5  # 6 jobs of 0.2 s, 2 at a time: about 0.6 s
    assert ticks > 30  # the event loop kept running


# --- The error body ---


async def test_api_error_handler_sets_retry_after():
    from app.routers.errors import api_error_handler as handler
    response = await handler(None, ApiError(429, "busy", "Try again soon.", retry_after=7))
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert json.loads(response.body) == {"code": "busy", "message": "Try again soon.",
                                         "retry_after": 7}
    plain = await handler(None, ApiError(400, "bad_request", "No."))
    assert "retry-after" not in plain.headers
    assert json.loads(plain.body) == {"code": "bad_request", "message": "No."}
