"""Serving stored images: only the signed-in account's, only well-formed names, through
the ImageStore (Plan C.8, P4.9). Upload is part of the chat request (test_intake.py)."""

import io
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.dependencies import get_image_store, get_principal
from app.routers import conversation
from app.storage.images import LocalImageStore

pytestmark = pytest.mark.unit

NEW = "0123456789abcdef0123456789abcdef.jpg"


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture
def store(tmp_path):
    root = tmp_path
    for key in (f"users/7/{NEW}", f"users/8/{NEW}", "images/7_0123abcd.jpg",
                "images/8_0123abcd.jpg"):
        (root / key).parent.mkdir(parents=True, exist_ok=True)
        (root / key).write_bytes(_jpeg())
    return LocalImageStore(root)


def _client(store, user_id=7):
    app = FastAPI()
    app.include_router(conversation.router)
    app.dependency_overrides[get_principal] = lambda: SimpleNamespace(user_id=user_id)
    app.dependency_overrides[get_image_store] = lambda: store
    return TestClient(app)


def test_the_owner_gets_new_and_old_images(store):
    client = _client(store)
    for name in (NEW, "7_0123abcd.jpg"):
        response = client.get(f"/conversation/images/{name}")
        assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
        assert response.headers["cache-control"].startswith("private")


def test_another_accounts_image_looks_like_no_image(store):
    # User 8 asks for user 7's names: the key is built from user 8, so nothing is found
    client = _client(store, user_id=8)
    assert client.get("/conversation/images/7_0123abcd.jpg").status_code == 404
    assert client.get(f"/conversation/images/{NEW}").content == \
        (store.root / f"users/8/{NEW}").read_bytes()  # their own file of that name


def test_a_guest_has_no_images(store):
    assert _client(store, user_id=None).get(f"/conversation/images/{NEW}").status_code == 404


@pytest.mark.parametrize("name", [
    "7_0123abcd.jpg%00.png", "7_..%2F8_0123abcd.jpg", "7_0123abcd.png", "7_x.jpg",
    "..%2Fusers%2F8%2F" + NEW, "ABCDEF0123456789abcdef0123456789.jpg",
])
def test_malformed_names_are_404(store, name):
    assert _client(store).get(f"/conversation/images/{name}").status_code == 404
