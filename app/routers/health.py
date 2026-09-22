from __future__ import annotations

from fastapi import APIRouter

from app.db import check_db_connection

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness() -> dict[str, str]:
    """Liveness probe — no database dependency."""
    return {"status": "ok"}


@router.get("/readyz")
def readiness() -> dict[str, str]:
    """Readiness probe — checks database connectivity."""
    if check_db_connection():
        return {"status": "ok"}
    return {"status": "unavailable"}
