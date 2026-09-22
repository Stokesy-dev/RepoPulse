from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    issues: Mapped[list[Issue]] = relationship("Issue", back_populates="repo", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repos_owner_name"),
    )

    def __repr__(self) -> str:
        return f"<Repo id={self.id} owner={self.owner!r} name={self.name!r}>"


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    repo_id: Mapped[int] = mapped_column(Integer, ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)  # "open" | "closed"
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    labels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repo: Mapped[Repo] = relationship("Repo", back_populates="issues")

    __table_args__ = (
        UniqueConstraint("repo_id", "number", name="uq_issues_repo_number"),
        Index("ix_issues_repo_id", "repo_id"),
        Index("ix_issues_repo_state", "repo_id", "state"),
        Index("ix_issues_updated_at", "updated_at"),
        Index("ix_issues_comments_count", "comments_count"),
    )

    def __repr__(self) -> str:
        return f"<Issue id={self.id} repo_id={self.repo_id} number={self.number}>"
