# ADR 0001: Rate Limit Exception Mapping

## Context
When syncing repository issues from the public GitHub REST API, API requests may be rejected or halted if rate limits are exceeded (`X-RateLimit-Remaining == 0`).

## Decision
We will catch rate limit exhaustion in `github_client.py` and raise a domain-specific exception `GitHubRateLimitError`. In the FastAPI application, an exception handler will translate this error into an `HTTP 429 Too Many Requests` response containing error details and the rate limit reset timestamp.

## Consequences
- Callers of the API receive an explicit HTTP 429 status code instead of a generic 500 error.
- Keeps upstream rate-limiting behavior distinct from internal application failures.
