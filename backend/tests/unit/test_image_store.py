"""The ImageStore (Plan C.8): the local folder and the S3-compatible store behave alike;
keys can't leave their folder; a failed delete raises so it can be queued."""

import io

import boto3
import pytest
from botocore.stub import Stubber

from app.storage.images import LocalImageStore, S3ImageStore, checked, image_key

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def test_local_put_get_and_delete_a_prefix(tmp_path):
    store = LocalImageStore(tmp_path)
    a, b, other = image_key(7), image_key(7), image_key(70)
    for key in (a, b, other):
        await store.put(key, key.encode())
    assert await store.get(a) == a.encode()
    assert await store.get("users/7/missing.jpg") is None
    assert await store.delete_prefix("users/7/") == 2  # not user 70's
    assert await store.get(a) is None and await store.get(other) == other.encode()


@pytest.mark.parametrize("key", ["../x.jpg", "/etc/passwd", "users/7/../8/a.jpg",
                                 "users\\7\\a.jpg", "users/7/a.png", "", "users//a.jpg"])
def test_keys_cant_leave_the_store(key):
    with pytest.raises(ValueError):
        checked(key)


def _s3():
    client = boto3.client("s3", endpoint_url="https://s3.example.test", region_name="auto",
                          aws_access_key_id="k", aws_secret_access_key="s")
    return client, Stubber(client)


async def test_s3_put_and_get():
    client, stub = _s3()
    stub.add_response("put_object", {}, {"Bucket": "b", "Key": "users/7/a.jpg",
                                         "Body": b"img", "ContentType": "image/jpeg"})
    stub.add_response("get_object", {"Body": io.BytesIO(b"img")},
                      {"Bucket": "b", "Key": "users/7/a.jpg"})
    stub.add_client_error("get_object", "NoSuchKey", http_status_code=404,
                          expected_params={"Bucket": "b", "Key": "users/7/b.jpg"})
    with stub:
        store = S3ImageStore(client, "b")
        await store.put("users/7/a.jpg", b"img")
        assert await store.get("users/7/a.jpg") == b"img"
        assert await store.get("users/7/b.jpg") is None
    stub.assert_no_pending_responses()


async def test_s3_deletes_every_page_of_a_prefix():
    client, stub = _s3()

    def page(keys, more):
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": more,
                **({"NextContinuationToken": "t"} if more else {})}

    stub.add_response("list_objects_v2", page(["users/7/a.jpg"], True),
                      {"Bucket": "b", "Prefix": "users/7/"})
    stub.add_response("delete_objects", {}, {"Bucket": "b", "Delete": {
        "Objects": [{"Key": "users/7/a.jpg"}], "Quiet": True}})
    stub.add_response("list_objects_v2", page(["users/7/b.jpg"], False),
                      {"Bucket": "b", "Prefix": "users/7/", "ContinuationToken": "t"})
    stub.add_response("delete_objects", {}, {"Bucket": "b", "Delete": {
        "Objects": [{"Key": "users/7/b.jpg"}], "Quiet": True}})
    with stub:
        assert await S3ImageStore(client, "b").delete_prefix("users/7/") == 2
    stub.assert_no_pending_responses()


async def test_s3_partial_delete_failure_raises():
    client, stub = _s3()
    stub.add_response("list_objects_v2", {"Contents": [{"Key": "users/7/a.jpg"}],
                                          "IsTruncated": False},
                      {"Bucket": "b", "Prefix": "users/7/"})
    stub.add_response("delete_objects", {"Errors": [{"Key": "users/7/a.jpg",
                                                     "Code": "AccessDenied"}]})
    with stub, pytest.raises(RuntimeError):
        await S3ImageStore(client, "b").delete_prefix("users/7/")
