"""User-scoped repositories: each reads and writes only its own user's rows (Plan P1.3)."""

import inspect
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data import repositories as repos
from app.models import ConversationMessage, User, WorkoutLog
from app.models.trace import GateDecision

ALL_REPOS = [getattr(repos, name) for name in repos.__all__]

# Every public method, so a new one can't skip the isolation tests below
EXPECTED_METHODS = {
    "ProfileRepository": {"get_medical", "get_preferences", "save_medical", "save_preferences"},
    "WorkoutLogRepository": {"add", "recent", "delete"},
    "NutritionLogRepository": {"add", "recent", "delete"},
    "MentalLogRepository": {"add", "recent", "delete"},
    "MessageRepository": {"add", "recent", "clear"},
    "ImageRepository": {"keys", "owns"},
    "TraceRepository": {"add", "get", "recent", "add_decisions", "decisions"},
}


def _public_methods(cls) -> dict[str, object]:
    return {
        name: fn for name, fn in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }


def test_no_public_method_takes_a_user_id():
    for cls in ALL_REPOS:
        for name, fn in _public_methods(cls).items():
            assert "user_id" not in inspect.signature(fn).parameters, f"{cls.__name__}.{name}"


def test_every_public_method_is_covered():
    assert {c.__name__: set(_public_methods(c)) for c in ALL_REPOS} == EXPECTED_METHODS


@pytest_asyncio.fixture
async def users(async_engine):
    """Two users, each with data in every repository. Yields (session, alice_id, bob_id)."""
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        alice = User(email="alice@x.io", username="alice", password_hash="h")
        bob = User(email="bob@x.io", username="bob", password_hash="h")
        session.add_all([alice, bob])
        await session.flush()
        for uid, name in ((alice.id, "alice"), (bob.id, "bob")):
            await repos.ProfileRepository(session, uid).save_medical(conditions=f"{name} knee")
            await repos.ProfileRepository(session, uid).save_preferences(goals=f"{name} goal")
            for repo in (repos.WorkoutLogRepository, repos.NutritionLogRepository,
                         repos.MentalLogRepository):
                await repo(session, uid).add(notes=f"{name} log")
            await repos.MessageRepository(session, uid).add(
                "user", f"{name} says hi", image_path=f"images/{name}.jpg",
                client_request_id=uuid.uuid4())
            traces = repos.TraceRepository(session, uid)
            await traces.add(f"t-{name}", "physical", [], {}, True)
            await traces.add_decisions(f"t-{name}", [dict(
                rule_id="EX-KNEE-01", rules_version=1, action="block", item="back_squat",
                reason=f"{name}")])
        await session.commit()
        yield session, alice.id, bob.id


@pytest.mark.asyncio
async def test_profile_isolated(users):
    session, alice, bob = users
    mine = repos.ProfileRepository(session, alice)
    assert (await mine.get_medical()).conditions == "alice knee"
    assert (await mine.get_preferences()).goals == "alice goal"
    await mine.save_medical(conditions="alice back")
    await mine.save_preferences(goals="alice new goal")
    theirs = repos.ProfileRepository(session, bob)
    assert (await theirs.get_medical()).conditions == "bob knee"
    assert (await theirs.get_preferences()).goals == "bob goal"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repo", [repos.WorkoutLogRepository, repos.NutritionLogRepository, repos.MentalLogRepository]
)
async def test_logs_isolated(users, repo):
    session, alice, bob = users
    mine, theirs = repo(session, alice), repo(session, bob)
    assert [r.notes for r in await mine.recent(days=7)] == ["alice log"]
    bob_row = (await theirs.recent(days=7))[0]
    assert await mine.delete(bob_row.id) is False  # can't delete someone else's entry
    assert [r.notes for r in await theirs.recent(days=7)] == ["bob log"]
    own = await mine.add(notes="alice second")
    assert own.user_id == alice
    assert await mine.delete(own.id) is True


@pytest.mark.asyncio
async def test_log_add_rejects_user_id_field(users):
    session, alice, bob = users
    with pytest.raises(ValueError, match="unknown fields"):
        await repos.WorkoutLogRepository(session, alice).add(user_id=bob, notes="sneaky")


@pytest.mark.asyncio
async def test_recent_logs_capped_and_newest_first(users):
    session, alice, _ = users
    mine = repos.WorkoutLogRepository(session, alice)
    for i in range(25):
        await mine.add(notes=f"n{i}")
    rows = await mine.recent(days=7, limit=100)
    assert len(rows) == 20  # Plan C.10: up to 20 entries
    assert rows[0].notes == "n24"


@pytest.mark.asyncio
async def test_messages_isolated(users):
    session, alice, bob = users
    mine = repos.MessageRepository(session, alice)
    assert [m.content for m in await mine.recent()] == ["alice says hi"]
    await mine.add("assistant", "alice reply")
    assert [m.content for m in await mine.recent()] == ["alice says hi", "alice reply"]
    assert await mine.clear() == 2
    assert [m.content for m in await repos.MessageRepository(session, bob).recent()] == [
        "bob says hi"
    ]
    total = await session.scalar(select(func.count()).select_from(ConversationMessage))
    assert total == 1


@pytest.mark.asyncio
async def test_images_isolated(users):
    session, alice, bob = users
    mine = repos.ImageRepository(session, alice)
    assert await mine.keys() == ["images/alice.jpg"]
    assert await mine.owns("images/alice.jpg") is True
    assert await mine.owns("images/bob.jpg") is False
    assert await repos.ImageRepository(session, bob).keys() == ["images/bob.jpg"]


@pytest.mark.asyncio
async def test_traces_isolated(users):
    session, alice, bob = users
    mine = repos.TraceRepository(session, alice)
    assert (await mine.get("t-alice")).route == "physical"
    assert await mine.get("t-bob") is None
    assert [t.trace_id for t in await mine.recent()] == ["t-alice"]
    assert [d.reason for d in await mine.decisions("t-alice")] == ["alice"]
    assert await mine.decisions("t-bob") == []
    # Writing a decision under someone else's trace id still records it as this user's
    await mine.add_decisions("t-bob", [dict(rule_id="X", rules_version=1, action="warn",
                                             item=None, reason="alice")])
    rows = await session.scalars(select(GateDecision).where(GateDecision.trace_id == "t-bob"))
    assert {d.user_id for d in rows} == {alice, bob}
    assert [d.reason for d in await repos.TraceRepository(session, bob).decisions("t-bob")] == [
        "bob"
    ]


@pytest.mark.asyncio
async def test_writes_carry_the_repository_user(users):
    session, alice, _ = users
    row = await repos.WorkoutLogRepository(session, alice).add(notes="x")
    stored = await session.get(WorkoutLog, row.id)
    assert stored.user_id == alice
