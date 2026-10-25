"""Image upload and serving: only clean, size-capped JPEGs reach the disk (Plan C.7)."""

import base64
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.dependencies import get_current_user, get_database
from app.routers import conversation

pytestmark = pytest.mark.unit


class _User:
    id = 7


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation, "UPLOADS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(uploads):
    app = FastAPI()
    app.include_router(conversation.router)
    app.dependency_overrides[get_current_user] = lambda: _User()
    app.dependency_overrides[get_database] = lambda: None
    return TestClient(app)


def _image(fmt="PNG", size=(64, 48), exif=False) -> bytes:
    img = Image.new("RGB", size, (200, 30, 30))
    out = io.BytesIO()
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCamera"  # Make
        kwargs["exif"] = data
    img.save(out, format=fmt, **kwargs)
    return out.getvalue()


def _upload(client, raw: bytes, prefix="data:image/png;base64,"):
    return client.post(
        "/conversation/upload-image",
        json={"image_base64": prefix + base64.b64encode(raw).decode()},
    )


def test_valid_image_is_stored_as_clean_jpeg(client, uploads):
    resp = _upload(client, _image("JPEG", size=(3000, 1500), exif=True))
    assert resp.status_code == 200
    stored = uploads / resp.json()["image_path"].split("/")[-1]
    with Image.open(stored) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1024  # resized, aspect kept
        assert img.size == (1024, 512)
        assert not img.getexif()  # metadata stripped


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_png_and_webp_accepted(client, fmt):
    assert _upload(client, _image(fmt)).status_code == 200


@pytest.mark.parametrize(
    "raw",
    [b"<script>alert(1)</script>", bytes(range(256)) * 40, _image("GIF")],
    ids=["script", "random-bytes", "gif"],
)
def test_non_images_rejected_and_not_stored(client, uploads, raw):
    resp = _upload(client, raw)
    assert resp.status_code == 415
    assert list(uploads.iterdir()) == []


def test_oversized_upload_rejected_before_decoding(client, uploads, monkeypatch):
    monkeypatch.setattr(conversation, "MAX_IMAGE_BYTES", 1000)
    resp = _upload(client, _image(size=(400, 400)) + b"\0" * 2000)
    assert resp.status_code == 413
    assert list(uploads.iterdir()) == []


def test_pixel_bomb_rejected(client, monkeypatch):
    # A small file that decodes to more pixels than the cap
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 10_000)
    assert _upload(client, _image(size=(200, 100))).status_code == 415


def test_invalid_base64_rejected(client):
    resp = client.post("/conversation/upload-image", json={"image_base64": "not*base64!"})
    assert resp.status_code == 400


def test_serving_checks_shape_and_owner(client, uploads):
    (uploads / "7_0123abcd.jpg").write_bytes(_image("JPEG"))
    (uploads / "8_0123abcd.jpg").write_bytes(_image("JPEG"))
    assert client.get("/conversation/images/7_0123abcd.jpg").status_code == 200
    assert client.get("/conversation/images/8_0123abcd.jpg").status_code == 403
    # Malformed names, including the null byte that used to cause a 500
    for name in ["7_0123abcd.jpg%00.png", "7_..%2F8_0123abcd.jpg", "7_0123abcd.png", "7_x.jpg"]:
        assert client.get(f"/conversation/images/{name}").status_code == 404, name
