from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Repo schemas ──────────────────────────────────────────────────────────────

class RepoCreate(BaseModel):
    owner: str
    name: str


class RepoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner: str
    name: str
    last_synced_at: datetime | None
    created_at: datetime


# ── Issue schemas ─────────────────────────────────────────────────────────────

class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repo_id: int
    number: int
    title: str
    state: str
    author: str
    labels: list[str]
    comments_count: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


# ── Sync schemas ──────────────────────────────────────────────────────────────

class SyncSummary(BaseModel):
    repo_id: int
    created: int
    updated: int
