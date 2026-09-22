from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import cast, func
from sqlalchemy.orm import Query, Session
from sqlalchemy.types import String

from app.models import Issue


def apply_triage_filters(
    db: Session,
    repo_id: int,
    *,
    stale_days: int | None = None,
    unanswered: bool | None = None,
    label: str | None = None,
) -> list[Issue]:
    """
    Return issues for *repo_id* filtered by any combination of triage criteria.

    All filtering is done in SQL — no Python-level post-filtering.

    Parameters
    ----------
    stale_days:  Return open issues whose ``updated_at`` is older than this
                 many days.
    unanswered:  If True, return open issues with ``comments_count == 0``.
    label:       Return issues whose labels array contains this string.
    """
    query: Query = db.query(Issue).filter(Issue.repo_id == repo_id)

    if stale_days is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=stale_days)
        query = query.filter(Issue.state == "open", Issue.updated_at < cutoff)

    if unanswered:
        query = query.filter(Issue.state == "open", Issue.comments_count == 0)

    if label is not None:
        # Use JSON_CONTAINS for MySQL; fall back to a LIKE check for SQLite.
        # Detect dialect via the connection bound to this session
        dialect = db.get_bind().dialect.name
        if dialect == "mysql":
            query = query.filter(
                func.json_contains(Issue.labels, func.json_quote(label)) == 1
            )
        else:
            # SQLite stores JSON as text; a LIKE search is accurate enough
            # for test fixtures and correctness testing.
            query = query.filter(
                cast(Issue.labels, String).contains(f'"{label}"')
            )

    return query.order_by(Issue.updated_at.desc()).all()
