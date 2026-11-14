"""DELETE /auth/delete-account (Plan C.18): every row that names the user, every row
keyed by their principal key, and their images; a failed image delete is queued and
the job clears it."""

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.data.state_store import StateStore
from app.database import Base
from app.storage.deletion import retry_deletions
from app.storage.images import LocalImageStore, image_key

from .accounts import account_app, call
from .test_admission import account, sql
from .test_migrations import _user_columns, _user_tables, _value

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


async def _fill(async_engine, user_id: int) -> None:
    """One row in every table with a user link (found from the models), and one row per
    principal-keyed table."""
    async with async_engine.begin() as conn:
        for table in _user_tables():
            if table.name == "users":
                continue
            values = {c.name: _value(table, c, user_id) for c in table.columns
                      if not (c.primary_key and c.autoincrement is True)
                      and c.server_default is None and c.name != "id"}
            for c in table.primary_key.columns:  # composite keys need values too
                values.setdefault(c.name, _value(table, c, user_id))
            await conn.execute(sa.insert(table).values(**values))
        key = f"user:{user_id}"
        for statement in (
            "INSERT INTO inflight_leases VALUES (:k, 't', now())",
            "INSERT INTO principal_flags VALUES (:k, now())",
            "INSERT INTO rate_counters VALUES (:km, now(), 1)",
            "INSERT INTO spend (key, period, period_start) VALUES (:k, 'day', now())",
        ):
            await conn.execute(sa.text(statement), {"k": key, "km": f"{key}:minute"})


async def _left(async_engine, user_id: int) -> dict[str, int]:
    left = {}
    async with async_engine.connect() as conn:
        for table in _user_tables():
            for column in _user_columns(table):
                n = await conn.scalar(sa.select(sa.func.count()).select_from(table)
                                      .where(column == user_id))
                if n:
                    left[f"{table.name}.{column.name}"] = n
        for table, column in (("inflight_leases", "principal_key"),
                              ("principal_flags", "principal_key"),
                              ("rate_counters", "key"), ("spend", "key")):
            n = await conn.scalar(sa.text(
                f"SELECT count(*) FROM {table} WHERE {column} LIKE :p"),
                {"p": f"user:{user_id}%"})
            if n:
                left[table] = n
    return left


async def test_every_row_and_image_of_the_user_goes(store, async_engine, tmp_path):
    images = LocalImageStore(tmp_path)
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="other@example.com")
    for p in (me, other):
        await _fill(async_engine, p.user_id)
    mine, theirs = image_key(me.user_id), image_key(other.user_id)
    old = f"images/{me.user_id}_0123abcd.jpg"  # an image from before P4.9
    for key in (mine, theirs, old):
        await images.put(key, b"jpg")
    await sql(async_engine, "UPDATE conversation_messages SET image_path = :k "
              "WHERE user_id = :u", k=old, u=me.user_id)
    assert len(Base.metadata.tables) and await _left(async_engine, me.user_id)

    response = await call(account_app(store, async_engine, images), me, "DELETE",
                          "/auth/delete-account")
    assert response.status_code == 204
    assert await _left(async_engine, me.user_id) == {}
    assert await images.get(mine) is None and await images.get(old) is None
    # The other account is untouched
    assert await _left(async_engine, other.user_id)
    assert await images.get(theirs) == b"jpg"
    assert await sql(async_engine, "SELECT count(*) FROM deletion_queue") == [(0,)]


class Flaky(LocalImageStore):
    def __init__(self, root, fails: int):
        super().__init__(root)
        self.fails = fails

    async def delete_prefix(self, prefix):
        if self.fails:
            self.fails -= 1
            raise OSError("storage down")
        return await super().delete_prefix(prefix)


async def test_a_failed_image_delete_is_queued_and_the_job_clears_it(store, async_engine,
                                                                    tmp_path):
    images = Flaky(tmp_path, fails=2)
    me = await account(store, async_engine)
    key = image_key(me.user_id)
    await images.put(key, b"jpg")
    response = await call(account_app(store, async_engine, images), me, "DELETE",
                          "/auth/delete-account")
    # The account is gone at once; only the images wait
    assert response.status_code == 204
    assert await sql(async_engine, "SELECT count(*) FROM users") == [(0,)]
    assert await sql(async_engine, "SELECT prefix, attempts FROM deletion_queue") == [
        (f"users/{me.user_id}/", 1)]
    assert await retry_deletions(async_engine, images) == 0  # still down: counted
    assert await sql(async_engine, "SELECT attempts FROM deletion_queue") == [(2,)]
    assert await retry_deletions(async_engine, images) == 1
    assert await sql(async_engine, "SELECT count(*) FROM deletion_queue") == [(0,)]
    assert await images.get(key) is None


async def _photo_message(async_engine, user_id: int, images) -> str:
    key = image_key(user_id)
    await images.put(key, b"jpg")
    await sql(async_engine, "INSERT INTO conversation_messages (user_id, role, content, "
              "agent_type, image_path) VALUES (:u, 'user', 'is this ok?', 'user', :k)",
              u=user_id, k=key)
    return key


async def test_clearing_the_chat_deletes_its_photos(store, async_engine, tmp_path):
    images = LocalImageStore(tmp_path)
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="other@example.com")
    mine = await _photo_message(async_engine, me.user_id, images)
    theirs = await _photo_message(async_engine, other.user_id, images)
    response = await call(account_app(store, async_engine, images), me, "DELETE",
                          "/conversation/messages")
    assert response.status_code == 204
    assert await sql(async_engine, "SELECT user_id FROM conversation_messages") == [
        (other.user_id,)]
    assert await images.get(mine) is None and await images.get(theirs) == b"jpg"


async def test_a_photo_that_cant_be_deleted_on_clearing_is_queued(store, async_engine,
                                                                  tmp_path):
    images = Flaky(tmp_path, fails=1)
    me = await account(store, async_engine)
    key = await _photo_message(async_engine, me.user_id, images)
    response = await call(account_app(store, async_engine, images), me, "DELETE",
                          "/conversation/messages")
    # The messages are gone at once; only the photo waits for the job
    assert response.status_code == 204
    assert await sql(async_engine, "SELECT count(*) FROM conversation_messages") == [(0,)]
    assert await sql(async_engine, "SELECT prefix FROM deletion_queue") == [(key,)]
    assert await retry_deletions(async_engine, images) == 1
    assert await images.get(key) is None


async def test_a_guest_cant_delete_an_account(store, async_engine, tmp_path):
    from .test_admission import guest
    response = await call(account_app(store, async_engine, LocalImageStore(tmp_path)),
                          await guest(store), "DELETE", "/auth/delete-account")
    assert response.status_code == 401
