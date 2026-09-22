from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Issue, Repo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Test client fixture with SQLite override ──────────────────────────────────


@pytest.fixture(scope="function")
def client():
    """FastAPI TestClient wired to a fresh in-memory SQLite DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    connection = engine.connect()
    test_db = Session(bind=connection)

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        c.test_db = test_db  # expose for direct DB manipulation in tests
        yield c
    test_db.close()
    connection.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def issues_page1() -> list[dict]:
    return json.loads((FIXTURES_DIR / "issues_page1.json").read_text())


# ── /healthz and /readyz ──────────────────────────────────────────────────────


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_with_db(client):
    """readyz should return ok when DB is up (SQLite in-memory is always up)."""
    with patch("app.routers.health.check_db_connection", return_value=True):
        resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── POST /repos ───────────────────────────────────────────────────────────────


def test_create_repo(client):
    resp = client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner"] == "octocat"
    assert body["name"] == "Hello-World"
    assert body["id"] is not None


def test_create_repo_idempotent(client):
    """POST /repos with an existing owner/name returns the existing record."""
    resp1 = client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    resp2 = client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]

    # Still only one row
    db: Session = client.test_db
    assert db.query(Repo).count() == 1


# ── GET /repos ────────────────────────────────────────────────────────────────


def test_list_repos_empty(client):
    resp = client.get("/repos")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_repos_returns_all(client):
    client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    client.post("/repos", json={"owner": "torvalds", "name": "linux"})
    resp = client.get("/repos")
    assert len(resp.json()) == 2


# ── POST /repos/{id}/sync ─────────────────────────────────────────────────────


def test_sync_repo_creates_issues(client, issues_page1):
    create_resp = client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    repo_id = create_resp.json()["id"]

    with patch("app.routers.repos.sync_repo_issues") as mock_sync:
        mock_sync.return_value = {"created": 3, "updated": 0}
        resp = client.post(f"/repos/{repo_id}/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["repo_id"] == repo_id
    assert body["created"] == 3
    assert body["updated"] == 0


def test_sync_repo_404(client):
    resp = client.post("/repos/9999/sync")
    assert resp.status_code == 404


def test_sync_repo_rate_limit(client):
    """When GitHubRateLimitError is raised, the API returns 429."""
    from app.github_client import GitHubRateLimitError

    create_resp = client.post("/repos", json={"owner": "octocat", "name": "Hello-World"})
    repo_id = create_resp.json()["id"]

    with patch("app.routers.repos.sync_repo_issues", side_effect=GitHubRateLimitError(reset_at=1700000000)):
        resp = client.post(f"/repos/{repo_id}/sync")

    assert resp.status_code == 429
    assert "1700000000" in resp.json()["detail"]


# ── GET /repos/{id}/issues ────────────────────────────────────────────────────


def _seed_issues(db: Session, repo: Repo, count: int = 3) -> list[Issue]:
    now = datetime.now(tz=timezone.utc)
    issues = []
    for i in range(count):
        issue = Issue(
            repo_id=repo.id,
            number=i + 1,
            title=f"Issue {i + 1}",
            state="open",
            author="tester",
            labels=["good-first-issue"] if i == 0 else [],
            comments_count=0 if i < 2 else 5,
            created_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=20 - i),
        )
        db.add(issue)
        issues.append(issue)
    db.commit()
    return issues


def test_list_issues_basic(client):
    db: Session = client.test_db
    repo = Repo(owner="octocat", name="Hello-World")
    db.add(repo)
    db.commit()
    db.refresh(repo)
    _seed_issues(db, repo)

    resp = client.get(f"/repos/{repo.id}/issues")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_list_issues_unanswered_filter(client):
    db: Session = client.test_db
    repo = Repo(owner="octocat", name="Hello-World")
    db.add(repo)
    db.commit()
    db.refresh(repo)
    _seed_issues(db, repo)

    resp = client.get(f"/repos/{repo.id}/issues?unanswered=true")
    assert resp.status_code == 200
    results = resp.json()
    assert all(r["comments_count"] == 0 for r in results)


def test_list_issues_label_filter(client):
    db: Session = client.test_db
    repo = Repo(owner="octocat", name="Hello-World")
    db.add(repo)
    db.commit()
    db.refresh(repo)
    _seed_issues(db, repo)

    resp = client.get(f"/repos/{repo.id}/issues?label=good-first-issue")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert "good-first-issue" in results[0]["labels"]


def test_list_issues_stale_filter(client):
    db: Session = client.test_db
    repo = Repo(owner="octocat", name="Hello-World")
    db.add(repo)
    db.commit()
    db.refresh(repo)

    now = datetime.now(tz=timezone.utc)
    # Issue updated 30 days ago — stale
    stale = Issue(
        repo_id=repo.id, number=1, title="Stale", state="open", author="x",
        labels=[], comments_count=0,
        created_at=now - timedelta(days=31),
        updated_at=now - timedelta(days=30),
    )
    # Issue updated 1 day ago — not stale
    fresh = Issue(
        repo_id=repo.id, number=2, title="Fresh", state="open", author="x",
        labels=[], comments_count=0,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )
    db.add_all([stale, fresh])
    db.commit()

    resp = client.get(f"/repos/{repo.id}/issues?stale_days=7")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["number"] == 1


def test_list_issues_repo_404(client):
    resp = client.get("/repos/9999/issues")
    assert resp.status_code == 404
