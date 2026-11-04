"""Unresolved health phrases for the catalogue review (P4.10, Part E #42, #47): counted
when first saved, never on a read; no user link; shown only from 3 people."""

import pytest
import pytest_asyncio

from app.data.state_store import StateStore
from app.observability.terms import PURGE, TOP, new_terms

from .accounts import call
from .test_admission import account, sql
from .test_tenant_isolation import world  # noqa: F401  (reuses its app wiring)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def app(world):  # noqa: F811
    return world


async def _save(app, me, path, **body):
    response = await call(app.app, me, "POST", path, json=body)
    assert response.status_code in (200, 201), response.text
    return response


async def _top(engine, minimum=3):
    return await sql(engine, str(TOP), keep=90, min=minimum, n=50)


def test_only_new_unresolved_phrases_count():
    assert new_terms(None, "torn ACL left knee, Bad Hip Thing") == ["bad hip thing"]
    assert new_terms("bad hip thing", "bad hip thing, asthma, wobbly ankle") == ["wobbly ankle"]
    assert new_terms(None, "x" * 41) == []  # long phrases aren't stored at all


async def test_a_save_adds_one_count_with_no_user_link(app):
    await _save(app, app.a, "/medical/history", conditions="bad hip thing, asthma")
    rows = await sql(app.engine, "SELECT * FROM unresolved_terms")
    assert [(r[0], r[1], r[3]) for r in rows] == [("bad hip thing", "conditions", 1)]
    assert len(rows[0]) == 4  # term, field, day, count: nothing that names a person
    # Saving again, or chatting (a read), adds nothing
    await _save(app, app.a, "/medical/history", conditions="bad hip thing, asthma")
    assert await sql(app.engine, "SELECT count FROM unresolved_terms") == [(1,)]


async def test_a_phrase_shows_only_from_three_people(app):
    store = StateStore(app.engine)
    people = [app.a, app.b, await account(store, app.engine, email="c@example.com")]
    for me in people[:2]:
        await _save(app, me, "/preferences", dietary_restrictions="no nightshades")
    assert await _top(app.engine) == []  # 2 people: not shown
    await _save(app, people[2], "/preferences", dietary_restrictions="No Nightshades")
    assert await _top(app.engine) == [("no nightshades", "dietary_restrictions", 3)]


async def test_old_counts_are_purged(app):
    await sql(app.engine, "INSERT INTO unresolved_terms VALUES ('old', 'conditions', "
              "current_date - 91, 5), ('new', 'conditions', current_date - 89, 5)")
    await sql(app.engine, str(PURGE), keep=90)
    assert await sql(app.engine, "SELECT term FROM unresolved_terms") == [("new",)]


async def test_a_counting_failure_never_fails_the_save(app, monkeypatch):
    from app.routers import medical

    def broken(*args):
        raise RuntimeError("db down")

    monkeypatch.setattr(medical, "count_saved", broken)
    await _save(app, app.a, "/medical/history", conditions="bad hip thing")
    assert await sql(app.engine, "SELECT conditions FROM medical_history WHERE user_id = :u",
                     u=app.a.user_id) == [("bad hip thing",)]
