from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import Issue, Repo
from app.services.filters import apply_triage_filters


def _make_issue(db: Session, repo: Repo, *, number: int, state: str = "open",
                comments_count: int = 0, labels: list[str] | None = None,
                updated_days_ago: int = 1) -> Issue:
    """Helper to insert an Issue directly for filter tests."""
    now = datetime.now(tz=timezone.utc)
    issue = Issue(
        repo_id=repo.id,
        number=number,
        title=f"Issue #{number}",
        state=state,
        author="tester",
        labels=labels or [],
        comments_count=comments_count,
        created_at=now - timedelta(days=updated_days_ago + 1),
        updated_at=now - timedelta(days=updated_days_ago),
        closed_at=now if state == "closed" else None,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return issue


def test_filter_no_params_returns_all(db: Session, sample_repo: Repo):
    """Calling with no filter params returns every issue for the repo."""
    _make_issue(db, sample_repo, number=1, state="open")
    _make_issue(db, sample_repo, number=2, state="closed")

    results = apply_triage_filters(db, sample_repo.id)
    assert len(results) == 2


def test_filter_stale_days(db: Session, sample_repo: Repo):
    """stale_days filters open issues not updated within N days."""
    _make_issue(db, sample_repo, number=1, state="open", updated_days_ago=15)
    _make_issue(db, sample_repo, number=2, state="open", updated_days_ago=2)
    _make_issue(db, sample_repo, number=3, state="closed", updated_days_ago=20)

    results = apply_triage_filters(db, sample_repo.id, stale_days=7)

    assert len(results) == 1
    assert results[0].number == 1


def test_filter_unanswered(db: Session, sample_repo: Repo):
    """unanswered=True returns only open issues with zero comments."""
    _make_issue(db, sample_repo, number=1, state="open", comments_count=0)
    _make_issue(db, sample_repo, number=2, state="open", comments_count=5)
    _make_issue(db, sample_repo, number=3, state="closed", comments_count=0)

    results = apply_triage_filters(db, sample_repo.id, unanswered=True)

    assert len(results) == 1
    assert results[0].number == 1


def test_filter_label(db: Session, sample_repo: Repo):
    """label filter returns issues whose labels array contains the string."""
    _make_issue(db, sample_repo, number=1, labels=["good-first-issue", "bug"])
    _make_issue(db, sample_repo, number=2, labels=["enhancement"])
    _make_issue(db, sample_repo, number=3, labels=[])

    results = apply_triage_filters(db, sample_repo.id, label="good-first-issue")

    assert len(results) == 1
    assert results[0].number == 1


def test_filter_composable_stale_and_unanswered(db: Session, sample_repo: Repo):
    """stale_days and unanswered are AND-ed together."""
    _make_issue(db, sample_repo, number=1, state="open", comments_count=0, updated_days_ago=30)
    _make_issue(db, sample_repo, number=2, state="open", comments_count=0, updated_days_ago=1)
    _make_issue(db, sample_repo, number=3, state="open", comments_count=5, updated_days_ago=30)

    results = apply_triage_filters(db, sample_repo.id, stale_days=7, unanswered=True)

    assert len(results) == 1
    assert results[0].number == 1


def test_filter_composable_label_and_unanswered(db: Session, sample_repo: Repo):
    """label and unanswered filters combine correctly."""
    _make_issue(db, sample_repo, number=1, labels=["good-first-issue"], comments_count=0)
    _make_issue(db, sample_repo, number=2, labels=["good-first-issue"], comments_count=3)
    _make_issue(db, sample_repo, number=3, labels=["bug"], comments_count=0)

    results = apply_triage_filters(db, sample_repo.id, unanswered=True, label="good-first-issue")

    assert len(results) == 1
    assert results[0].number == 1


def test_filter_isolates_by_repo(db: Session, sample_repo: Repo, db_engine):
    """Filters must not return issues belonging to other repos."""
    from sqlalchemy.orm import sessionmaker

    # Create a second repo and issue
    other_repo = Repo(owner="other", name="repo")
    db.add(other_repo)
    db.commit()
    db.refresh(other_repo)

    _make_issue(db, sample_repo, number=1, labels=["good-first-issue"])
    _make_issue(db, other_repo, number=1, labels=["good-first-issue"])

    results = apply_triage_filters(db, sample_repo.id, label="good-first-issue")

    assert len(results) == 1
    assert results[0].repo_id == sample_repo.id
