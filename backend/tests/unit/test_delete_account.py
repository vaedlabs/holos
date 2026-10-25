"""DELETE /auth/delete-account removes the user and every row that references them."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_database
from app.models.agent_execution_log import AgentExecutionLog
from app.models.conversation_message import ConversationMessage
from app.models.user import User
from app.routers import auth

pytestmark = pytest.mark.unit


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    # Enforce foreign keys like Postgres does
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def _client(session_factory, user_id):
    app = FastAPI()
    app.include_router(auth.router)

    def _db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    def _user():
        db = session_factory()
        try:
            return db.get(User, user_id)
        finally:
            db.close()

    app.dependency_overrides[get_database] = _db
    app.dependency_overrides[get_current_user] = _user
    return TestClient(app)


def test_delete_account_with_agent_logs(session_factory):
    db = session_factory()
    user = User(email="a@example.com", username="alice", password_hash="x")
    other = User(email="b@example.com", username="bob", password_hash="x")
    db.add_all([user, other])
    db.flush()
    for owner in (user, other):
        db.add(AgentExecutionLog(trace_id=f"t-{owner.id}", agent_type="nutrition",
                                 user_id=owner.id))
        db.add(ConversationMessage(user_id=owner.id, role="user", content="hi"))
    db.commit()
    user_id, other_id = user.id, other.id
    db.close()

    response = _client(session_factory, user_id).delete("/auth/delete-account")
    assert response.status_code == 204

    db = session_factory()
    assert db.get(User, user_id) is None
    assert db.query(AgentExecutionLog).filter_by(user_id=user_id).count() == 0
    assert db.query(ConversationMessage).filter_by(user_id=user_id).count() == 0
    # Other users' data is untouched
    assert db.get(User, other_id) is not None
    assert db.query(AgentExecutionLog).filter_by(user_id=other_id).count() == 1
    db.close()


def test_every_user_foreign_key_is_cleaned_up(session_factory):
    # Guards against a new table referencing users.id without a delete step
    tables = {
        table
        for table in inspect(session_factory.kw["bind"]).get_table_names()
        for fk in inspect(session_factory.kw["bind"]).get_foreign_keys(table)
        if fk["referred_table"] == "users"
    }
    source = open(auth.__file__).read()
    model_for = {m.__tablename__: m.__name__ for m in Base.__subclasses__()}
    missing = [model_for[t] for t in tables if f"db.query({model_for[t]})" not in source]
    assert not missing, f"delete_account does not delete: {missing}"
