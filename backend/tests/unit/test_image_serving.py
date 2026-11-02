"""Serving stored images: only the owner, only well-formed names (Plan C.7). Upload
moved into the chat request (routers/intake.py, tested in test_intake.py)."""

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


def test_serving_checks_shape_and_owner(client, uploads):
    (uploads / "7_0123abcd.jpg").write_bytes(_image("JPEG"))
    (uploads / "8_0123abcd.jpg").write_bytes(_image("JPEG"))
    assert client.get("/conversation/images/7_0123abcd.jpg").status_code == 200
    assert client.get("/conversation/images/8_0123abcd.jpg").status_code == 403
    # Malformed names, including the null byte that used to cause a 500
    for name in ["7_0123abcd.jpg%00.png", "7_..%2F8_0123abcd.jpg", "7_0123abcd.png", "7_x.jpg"]:
        assert client.get(f"/conversation/images/{name}").status_code == 404, name
