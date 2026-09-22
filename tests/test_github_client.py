from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.github_client import GitHubRateLimitError, fetch_issues, _next_url


# ── _next_url unit tests ──────────────────────────────────────────────────────


def test_next_url_returns_none_when_no_header():
    assert _next_url(None) is None


def test_next_url_returns_none_when_no_next_rel():
    header = '<https://api.github.com/repos/o/r/issues?page=1>; rel="prev"'
    assert _next_url(header) is None


def test_next_url_parses_next_correctly():
    header = (
        '<https://api.github.com/repos/o/r/issues?page=1>; rel="prev", '
        '<https://api.github.com/repos/o/r/issues?page=3>; rel="next"'
    )
    assert _next_url(header) == "https://api.github.com/repos/o/r/issues?page=3"


def test_next_url_single_next_link():
    header = '<https://api.github.com/repos/o/r/issues?page=2>; rel="next"'
    assert _next_url(header) == "https://api.github.com/repos/o/r/issues?page=2"


# ── fetch_issues with injected mock client ────────────────────────────────────


def _make_response(body: list | dict, *, status_code: int = 200, headers: dict | None = None) -> httpx.Response:
    """Build a fake httpx.Response with a dummy request attached."""
    all_headers = {"Content-Type": "application/json", "X-RateLimit-Remaining": "60", "X-RateLimit-Reset": "9999999999"}
    if headers:
        all_headers.update(headers)
    request = httpx.Request("GET", "https://api.github.com/repos/octocat/Hello-World/issues")
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(body).encode(),
        headers=all_headers,
        request=request,
    )


def test_fetch_issues_basic(issues_page1):
    """fetch_issues yields all non-PR issues from a single page."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(issues_page1)

    results = list(fetch_issues("octocat", "Hello-World", client=mock_client))

    assert len(results) == 3
    assert all("pull_request" not in item for item in results)
    assert results[0]["number"] == 42


def test_fetch_issues_filters_pull_requests(pull_request_items):
    """Items with 'pull_request' key must be excluded."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(pull_request_items)

    results = list(fetch_issues("octocat", "Hello-World", client=mock_client))

    assert results == [], "Pull requests should be filtered out entirely"


def test_fetch_issues_pagination(issues_page1, issues_page2):
    """fetch_issues follows Link rel=next and yields from all pages."""
    page1_response = _make_response(
        issues_page1,
        headers={
            "Link": '<https://api.github.com/repos/octocat/Hello-World/issues?page=2>; rel="next"'
        },
    )
    page2_response = _make_response(issues_page2)

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = [page1_response, page2_response]

    results = list(fetch_issues("octocat", "Hello-World", client=mock_client))

    assert len(results) == 4  # 3 from page1 + 1 from page2
    assert mock_client.get.call_count == 2


def test_fetch_issues_rate_limit_raises():
    """When X-RateLimit-Remaining is 0, GitHubRateLimitError is raised."""
    exhausted_response = _make_response(
        [],
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
    )
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = exhausted_response

    with pytest.raises(GitHubRateLimitError) as exc_info:
        list(fetch_issues("octocat", "Hello-World", client=mock_client))

    assert exc_info.value.reset_at == 1700000000


def test_fetch_issues_mixed_pr_and_issues(issues_page1, pull_request_items):
    """Only real issues are yielded when a page contains both issues and a PR."""
    mixed = issues_page1 + pull_request_items
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _make_response(mixed)

    results = list(fetch_issues("octocat", "Hello-World", client=mock_client))

    assert len(results) == 3
    assert all(r["number"] != 99 for r in results)  # PR number 99 must be excluded
