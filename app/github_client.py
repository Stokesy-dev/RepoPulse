from __future__ import annotations

import re
from collections.abc import Iterator

import httpx

from app.config import settings


class GitHubRateLimitError(Exception):
    """Raised when X-RateLimit-Remaining is 0."""

    def __init__(self, reset_at: int) -> None:
        self.reset_at = reset_at
        super().__init__(f"GitHub rate limit exceeded. Resets at Unix timestamp {reset_at}.")


def _build_headers(token: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    effective_token = token or settings.github_token
    if effective_token:
        headers["Authorization"] = f"Bearer {effective_token}"
    return headers


def _check_rate_limit(response: httpx.Response) -> None:
    """Raise GitHubRateLimitError if the rate limit is exhausted."""
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) == 0:
        reset_at = int(response.headers.get("X-RateLimit-Reset", "0"))
        raise GitHubRateLimitError(reset_at=reset_at)


def _next_url(link_header: str | None) -> str | None:
    """Parse GitHub's Link header and return the 'next' URL if present."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        match = re.match(r'<([^>]+)>;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None


def fetch_issues(
    owner: str,
    repo: str,
    *,
    client: httpx.Client | None = None,
    token: str = "",
    state: str = "all",
    per_page: int = 100,
) -> Iterator[dict]:
    """
    Fetch all issues (excluding pull requests) for a GitHub repository.

    Parameters
    ----------
    owner:     GitHub repository owner (login).
    repo:      GitHub repository name.
    client:    Optional injected ``httpx.Client`` — used for testing to avoid
               real network calls. A default client is created if omitted.
    token:     Optional Bearer token; falls back to ``settings.github_token``.
    state:     Issue state filter: "open", "closed", or "all".
    per_page:  Number of results per page (max 100).

    Yields
    ------
    Dicts representing individual GitHub issues (pull requests are excluded).
    """
    headers = _build_headers(token)
    url: str | None = (
        f"https://api.github.com/repos/{owner}/{repo}/issues"
        f"?state={state}&per_page={per_page}&filter=all"
    )

    _owns_client = client is None
    if _owns_client:
        client = httpx.Client(headers=headers, follow_redirects=True, timeout=30.0)

    try:
        while url:
            response = client.get(url, headers=headers)  # type: ignore[union-attr]
            if response.status_code >= 400:
                response.raise_for_status()
            _check_rate_limit(response)

            items: list[dict] = response.json()
            for item in items:
                # GitHub issues endpoint returns PRs too — skip them
                if "pull_request" in item:
                    continue
                yield item

            url = _next_url(response.headers.get("Link"))
    finally:
        if _owns_client:
            client.close()  # type: ignore[union-attr]
