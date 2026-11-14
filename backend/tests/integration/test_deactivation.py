"""Deactivating an account (Plan C.6, Part E #48): every session ends at once, a session
of an inactive account is refused however the account was switched off, and the account
can be activated again. Who deactivates, and why, is still the owner's decision."""

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.data.state_store import StateStore
from app.dependencies import get_current_user
from app.orchestration.passwords import get_password_hash
from app.orchestration.principal import Principal
from app.routers.errors import ApiError
from app.storage.images import LocalImageStore

from .accounts import account_app, call
from .test_admission import account, guest, sql
from .test_chat import Models, _app, _payload, _post

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def store(async_engine):
    return StateStore(async_engine)


@pytest.fixture
def app(store, async_engine, tmp_path):
    return account_app(store, async_engine, LocalImageStore(tmp_path))


async def test_deactivating_ends_every_session(store, async_engine, app):
    me = await account(store, async_engine)
    raw, session = await store.create_session("account", "ipk-b", user_id=me.user_id)
    phone = Principal(session, raw, "ipk-b")
    assert (await call(app, me, "GET", "/profile/check")).status_code == 200

    assert await store.set_active(me.user_id, False)
    assert await sql(async_engine, "SELECT count(*) FROM sessions") == [(0,)]
    for principal in (me, phone):
        response = await call(app, principal, "GET", "/profile/check")
        assert (response.status_code, response.json()["code"]) == (401, "no_session")


async def test_an_inactive_account_cant_chat(store, async_engine):
    me = await account(store, async_engine)
    await store.set_active(me.user_id, False)
    response = await _post(_app(store, async_engine, Models()), me, _payload())
    assert response.status_code == 401


async def test_a_session_of_an_account_switched_off_directly_is_refused(store, async_engine,
                                                                        app):
    me = await account(store, async_engine)
    await sql(async_engine, "UPDATE users SET is_active = false WHERE id = :u", u=me.user_id)
    assert await store.touch_session(me.raw_session_id) is None
    assert (await call(app, me, "GET", "/profile/check")).status_code == 401


@pytest.mark.parametrize(("change", "status", "code"), [
    ("UPDATE users SET is_active = false WHERE id = :u", 403, "inactive"),
    ("DELETE FROM users WHERE id = :u", 401, "no_session"),
])
async def test_an_account_switched_off_after_its_session_was_read_gets_nothing(
        store, async_engine, change, status, code):
    """A request whose session passed just before the change: the account routes still
    refuse it when they load the user."""
    me = await account(store, async_engine)
    await sql(async_engine, change, u=me.user_id)
    with pytest.raises(ApiError) as caught:
        await get_current_user(me, async_sessionmaker(async_engine))
    assert (caught.value.status, caught.value.code) == (status, code)


async def test_an_inactive_account_cant_sign_in_until_activated(store, async_engine, app):
    user_id = (await sql(async_engine, "INSERT INTO users (email, username, password_hash) "
                         "VALUES ('a@example.com', 'a', :h) RETURNING id",
                         h=get_password_hash("correct horse")))[0][0]
    login = {"email": "a@example.com", "password": "correct horse"}
    await store.set_active(user_id, False)
    response = await call(app, None, "POST", "/auth/login", json=login)
    assert (response.status_code, response.json()["code"]) == (403, "inactive")

    assert await store.set_active(user_id, True)
    assert (await call(app, None, "POST", "/auth/login", json=login)).status_code == 200


async def test_guests_and_other_accounts_are_untouched(store, async_engine, app):
    me = await account(store, async_engine)
    other = await account(store, async_engine, email="b@example.com")
    visitor = await guest(store)
    await store.set_active(me.user_id, False)
    assert await store.touch_session(other.raw_session_id) is not None
    assert await store.touch_session(visitor.raw_session_id) is not None


async def test_no_such_account(store):
    assert await store.set_active(999_999, False) is False


async def test_is_active_is_never_null(async_engine):
    [(active,)] = await sql(async_engine, "INSERT INTO users (email, username, password_hash) "
                            "VALUES ('n@example.com', 'n', 'h') RETURNING is_active")
    assert active is True
    with pytest.raises(IntegrityError):
        await sql(async_engine, "UPDATE users SET is_active = NULL")
