from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Repo
from app.schemas import IssueRead
from app.services.filters import apply_triage_filters

router = APIRouter(prefix="/repos", tags=["issues"])


@router.get("/{repo_id}/issues", response_model=list[IssueRead])
def list_issues(
    repo_id: int,
    stale_days: int | None = None,
    unanswered: bool | None = None,
    label: str | None = None,
    db: Session = Depends(get_db),
) -> list:
    """
    List issues for a tracked repository with optional triage filters.

    Query parameters (all composable):
    - **stale_days**: open issues with ``updated_at`` older than N days.
    - **unanswered**: open issues with no comments (``comments_count == 0``).
    - **label**: issues whose labels array contains this string.
    """
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")

    return apply_triage_filters(
        db,
        repo_id,
        stale_days=stale_days,
        unanswered=unanswered,
        label=label,
    )
