from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Issue, Repo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Database Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db_engine():
    """In-memory SQLite engine for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Enable JSON support in SQLite — SQLite stores JSON as TEXT
    @event.listens_for(engine, "connect")
    def enable_json(dbapi_connection, connection_record):
        pass  # SQLAlchemy's JSON type handles serialization for SQLite

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(db_engine):
    """Database session scoped to each test function."""
    connection = db_engine.connect()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        connection.close()


@pytest.fixture
def sample_repo(db: Session) -> Repo:
    """A persisted Repo for use in tests."""
    repo = Repo(owner="octocat", name="Hello-World")
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


# ── GitHub API Fixture Loaders ────────────────────────────────────────────────


@pytest.fixture
def issues_page1() -> list[dict]:
    return json.loads((FIXTURES_DIR / "issues_page1.json").read_text())


@pytest.fixture
def issues_page2() -> list[dict]:
    return json.loads((FIXTURES_DIR / "issues_page2.json").read_text())


@pytest.fixture
def pull_request_items() -> list[dict]:
    return json.loads((FIXTURES_DIR / "pull_request.json").read_text())
