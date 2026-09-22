from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.github_client import fetch_issues
from app.models import Issue, Repo


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _upsert_issues(
    db: Session,
    repo_id: int,
    issue_rows: list[dict],
) -> tuple[int, int]:
    """
    Perform a dialect-aware UPSERT of issue rows.

    Returns a (created, updated) tuple. Because MySQL and SQLite have different
    upsert syntax, we detect the dialect at runtime.
    """
    if not issue_rows:
        return 0, 0

    # Detect dialect via the connection bound to this session
    dialect_name = db.get_bind().dialect.name

    # Count existing (repo_id, number) pairs to compute created vs updated
    numbers = [r["number"] for r in issue_rows]
    existing_numbers: set[int] = {
        row[0]
        for row in db.execute(
            select(Issue.number).where(
                Issue.repo_id == repo_id,
                Issue.number.in_(numbers),
            )
        )
    }

    if dialect_name == "mysql":
        stmt = mysql_insert(Issue).values(issue_rows)
        stmt = stmt.on_duplicate_key_update(
            title=stmt.inserted.title,
            state=stmt.inserted.state,
            author=stmt.inserted.author,
            labels=stmt.inserted.labels,
            comments_count=stmt.inserted.comments_count,
            updated_at=stmt.inserted.updated_at,
            closed_at=stmt.inserted.closed_at,
        )
    else:
        # SQLite (used in tests)
        stmt = sqlite_insert(Issue).values(issue_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["repo_id", "number"],
            set_={
                "title": stmt.excluded.title,
                "state": stmt.excluded.state,
                "author": stmt.excluded.author,
                "labels": stmt.excluded.labels,
                "comments_count": stmt.excluded.comments_count,
                "updated_at": stmt.excluded.updated_at,
                "closed_at": stmt.excluded.closed_at,
            },
        )

    db.execute(stmt)
    db.commit()

    created = sum(1 for r in issue_rows if r["number"] not in existing_numbers)
    updated = len(issue_rows) - created
    return created, updated


def sync_repo_issues(
    db: Session,
    repo: Repo,
    *,
    github_client: httpx.Client | None = None,
) -> dict[str, int]:
    """
    Fetch all issues for *repo* from GitHub and upsert them into the database.

    Returns a dict with keys ``created`` and ``updated``.
    """
    issue_rows: list[dict] = []

    for raw in fetch_issues(repo.owner, repo.name, client=github_client):
        issue_rows.append(
            {
                "repo_id": repo.id,
                "number": raw["number"],
                "title": raw["title"],
                "state": raw["state"],
                "author": raw["user"]["login"],
                "labels": [lbl["name"] for lbl in raw.get("labels", [])],
                "comments_count": raw.get("comments", 0),
                "created_at": _parse_dt(raw.get("created_at")),
                "updated_at": _parse_dt(raw.get("updated_at")),
                "closed_at": _parse_dt(raw.get("closed_at")),
            }
        )

    created, updated = _upsert_issues(db, repo.id, issue_rows)

    # Update last_synced_at on the repo
    repo.last_synced_at = datetime.now(tz=timezone.utc)
    db.add(repo)
    db.commit()
    db.refresh(repo)

    return {"created": created, "updated": updated}
