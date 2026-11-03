"""Account images (Plan C.8): a local folder in dev and tests, S3-compatible storage in
production. Keys are `users/{user_id}/{uuid}.jpg`; images from before P4.9 keep their
old keys, `images/{user_id}_{hex}.jpg`.

    store = get_image_store()                  # OBJECT_STORE_* empty → local folder
    key = image_key(user_id)                   # users/7/3f2a….jpg
    await store.put(key, data)
    data = await store.get(key)                # None if there is no such object
    await store.delete_prefix(f"users/{user_id}/")

No caller passes a key it got from a request: the routes build keys from the session's
user ID, and every key is checked here too (no "..", no leading slash).
"""

import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import anyio

LOCAL_ROOT = Path("uploads")
_KEY = re.compile(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*(?:\.jpg)?/?")


def image_key(user_id: int) -> str:
    return f"users/{user_id}/{uuid.uuid4().hex}.jpg"


def user_prefix(user_id: int) -> str:
    return f"users/{user_id}/"


def checked(key: str) -> str:
    if not _KEY.fullmatch(key) or ".." in key:
        raise ValueError(f"not an image key: {key!r}")
    return key


class ImageStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...
    async def get(self, key: str) -> bytes | None: ...
    async def delete_prefix(self, prefix: str) -> int: ...


class LocalImageStore:
    def __init__(self, root: Path = LOCAL_ROOT):
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / checked(key)).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"not an image key: {key!r}")
        return path

    async def put(self, key: str, data: bytes) -> None:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await anyio.to_thread.run_sync(write)

    async def get(self, key: str) -> bytes | None:
        path = self._path(key)
        return await anyio.to_thread.run_sync(
            lambda: path.read_bytes() if path.is_file() else None)

    async def delete_prefix(self, prefix: str) -> int:
        """Every object whose key starts with `prefix` (a folder ending in "/", or one
        key). A failure raises, so the caller can queue the prefix."""
        checked(prefix)

        def delete() -> int:
            found = [p for p in self.root.rglob("*") if p.is_file()
                     and p.relative_to(self.root).as_posix().startswith(prefix)]
            for path in found:
                path.unlink()
            return len(found)

        return await anyio.to_thread.run_sync(delete)


class S3ImageStore:
    """Any S3-compatible service through boto3 (the provider is chosen in P7.1), whose
    calls block: each runs in a worker thread."""

    def __init__(self, client, bucket: str):
        self._client = client
        self._bucket = bucket

    async def put(self, key: str, data: bytes) -> None:
        await anyio.to_thread.run_sync(lambda: self._client.put_object(
            Bucket=self._bucket, Key=checked(key), Body=data, ContentType="image/jpeg"))

    async def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        def read() -> bytes | None:
            try:
                return self._client.get_object(Bucket=self._bucket, Key=checked(key))[
                    "Body"].read()
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    return None
                raise

        return await anyio.to_thread.run_sync(read)

    async def delete_prefix(self, prefix: str) -> int:
        checked(prefix)

        def delete() -> int:
            count, token = 0, None
            while True:
                page = self._client.list_objects_v2(
                    Bucket=self._bucket, Prefix=prefix,
                    **({"ContinuationToken": token} if token else {}))
                keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if keys:  # at most 1,000 per listing page, which is the delete limit
                    result = self._client.delete_objects(
                        Bucket=self._bucket, Delete={"Objects": keys, "Quiet": True})
                    if result.get("Errors"):
                        raise RuntimeError(f"{len(result['Errors'])} objects not deleted")
                    count += len(keys)
                if not page.get("IsTruncated"):
                    return count
                token = page["NextContinuationToken"]

        return await anyio.to_thread.run_sync(delete)


@lru_cache(maxsize=1)
def get_image_store() -> ImageStore:
    """S3-compatible when OBJECT_STORE_URL is set (B.3), else the local folder."""
    url = os.getenv("OBJECT_STORE_URL", "").strip()
    if not url:
        return LocalImageStore()
    import boto3

    client = boto3.client(
        "s3", endpoint_url=url, aws_access_key_id=os.environ["OBJECT_STORE_KEY"],
        aws_secret_access_key=os.environ["OBJECT_STORE_SECRET"],
        region_name=os.getenv("OBJECT_STORE_REGION", "auto"))
    return S3ImageStore(client, os.environ["OBJECT_STORE_BUCKET"])
