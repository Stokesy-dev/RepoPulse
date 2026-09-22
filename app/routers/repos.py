from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.github_client import GitHubRateLimitError
from app.models import Repo
from app.schemas import RepoCreate, RepoRead, SyncSummary
from app.services.sync import sync_repo_issues

router = APIRouter(prefix="/repos", tags=["repos"])


def _get_repo_or_404(repo_id: int, db: Session) -> Repo:
    repo = db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail=f"Repo {repo_id} not found")
    return repo


@router.post("", response_model=RepoRead, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db)) -> Repo:
    """Register a GitHub repository for tracking."""
    existing = (
        db.query(Repo)
        .filter(Repo.owner == body.owner, Repo.name == body.name)
        .first()
    )
    if existing:
        return existing

    repo = Repo(owner=body.owner, name=body.name)
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


@router.get("", response_model=list[RepoRead])
def list_repos(db: Session = Depends(get_db)) -> list[Repo]:
    """List all tracked repositories."""
    return db.query(Repo).order_by(Repo.created_at.desc()).all()


@router.post("/{repo_id}/sync", response_model=SyncSummary)
def sync_repo(repo_id: int, db: Session = Depends(get_db)) -> dict:
    """Fetch issues from GitHub and upsert them for the given repo."""
    repo = _get_repo_or_404(repo_id, db)

    try:
        result = sync_repo_issues(db, repo)
    except GitHubRateLimitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"GitHub rate limit exceeded. Resets at Unix timestamp {exc.reset_at}.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API error: {exc.response.status_code}",
        ) from exc

    return {"repo_id": repo_id, **result}
