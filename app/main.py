from __future__ import annotations

from fastapi import FastAPI

from app.routers import health, issues, repos

app = FastAPI(
    title="RepoPulse",
    description="Sync and triage GitHub repository issues.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(repos.router)
app.include_router(issues.router)
