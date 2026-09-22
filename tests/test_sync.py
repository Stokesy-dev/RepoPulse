from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.orm import Session

from app.models import Issue, Repo
from app.services.sync import sync_repo_issues

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_response(body: list, *, headers: dict | None = None) -> httpx.Response:
    all_headers = {
        "Content-Type": "application/json",
        "X-RateLimit-Remaining": "60",
        "X-RateLimit-Reset": "9999999999",
    }
    if headers:
        all_headers.update(headers)
    request = httpx.Request("GET", "https://api.github.com/repos/octocat/Hello-World/issues")
    return httpx.Response(
        status_code=200,
        content=json.dumps(body).encode(),
        headers=all_headers,
        request=request,
    )


def test_sync_creates_new_issues(db: Session, sample_repo: Repo, issues_page1):
    """First sync creates all issues from the fixture."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(issues_page1)

    result = sync_repo_issues(db, sample_repo, github_client=mock_client)

    assert result["created"] == 3
    assert result["updated"] == 0

    issues = db.query(Issue).filter(Issue.repo_id == sample_repo.id).all()
    assert len(issues) == 3


def test_sync_is_idempotent(db: Session, sample_repo: Repo, issues_page1):
    """Running sync twice on the same data must not create duplicates."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [
        _make_response(issues_page1),
        _make_response(issues_page1),
    ]

    result1 = sync_repo_issues(db, sample_repo, github_client=mock_client)
    result2 = sync_repo_issues(db, sample_repo, github_client=mock_client)

    assert result1["created"] == 3
    assert result2["created"] == 0
    assert result2["updated"] == 3

    # Still only 3 rows in DB
    count = db.query(Issue).filter(Issue.repo_id == sample_repo.id).count()
    assert count == 3


def test_sync_updates_existing_issue(db: Session, sample_repo: Repo, issues_page1):
    """Sync updates mutable fields on rows that already exist."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(issues_page1)
    sync_repo_issues(db, sample_repo, github_client=mock_client)

    # Simulate updated data: issue 42 is now closed with more comments
    updated_page = [
        {**issues_page1[0], "state": "closed", "comments": 10, "closed_at": "2024-02-01T00:00:00Z"},
        *issues_page1[1:],
    ]
    mock_client.get.return_value = _make_response(updated_page)
    sync_repo_issues(db, sample_repo, github_client=mock_client)

    updated = db.query(Issue).filter(Issue.repo_id == sample_repo.id, Issue.number == 42).one()
    assert updated.state == "closed"
    assert updated.comments_count == 10
    assert updated.closed_at is not None


def test_sync_updates_last_synced_at(db: Session, sample_repo: Repo, issues_page1):
    """sync_repo_issues updates Repo.last_synced_at after a successful sync."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(issues_page1)

    assert sample_repo.last_synced_at is None
    sync_repo_issues(db, sample_repo, github_client=mock_client)
    db.refresh(sample_repo)

    assert sample_repo.last_synced_at is not None
    # Verify it's recent (within last 5 seconds)
    now = datetime.now(tz=timezone.utc)
    diff = abs((now - sample_repo.last_synced_at.replace(tzinfo=timezone.utc)).total_seconds())
    assert diff < 5


def test_sync_skips_pull_requests(db: Session, sample_repo: Repo, pull_request_items):
    """PR-shaped items must not be stored as Issues."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(pull_request_items)

    result = sync_repo_issues(db, sample_repo, github_client=mock_client)

    assert result["created"] == 0
    assert db.query(Issue).filter(Issue.repo_id == sample_repo.id).count() == 0
