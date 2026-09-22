# RepoPulse

RepoPulse is a FastAPI microservice that syncs public GitHub repository issues and stores them in a MySQL database. It provides composable API filters to triage those issues (e.g., finding stale issues, unanswered issues, or filtering by label like "good-first-issue"). It's designed to demonstrate clean architecture, robust rate-limit handling, testability, and idempotent data syncing.

## Architecture
```text
+-------------------+      +----------------+      +-------------------+
|                   |      |                |      |                   |
|  GitHub REST API  +----->+  RepoPulse API +----->+  MySQL 8 Database |
|                   | HTTP |   (FastAPI)    |      |                   |
+-------------------+      +-------+--------+      +-------------------+
                                   |
                                   | (Test DB)
                                   v
                           +-------+--------+
                           | SQLite In-Mem  |
                           |    (pytest)    |
                           +----------------+
```

## Setup & Running Locally

1. Create a `.env` file (optional if you want higher GitHub rate limits):
   ```bash
   cp .env.example .env
   # Edit .env and add your GITHUB_TOKEN
   ```

2. Start the database and API via Docker Compose:
   ```bash
   docker-compose up --build
   ```
   *The entrypoint script will automatically run Alembic migrations on startup.*

3. The API will be available at `http://localhost:8000`.

## Example Usage

### 1. Register a repository
```bash
curl -X POST http://localhost:8000/repos \
  -H "Content-Type: application/json" \
  -d '{"owner": "fastapi", "name": "fastapi"}'
```
Response: `{"id": 1, "owner": "fastapi", "name": "fastapi", "last_synced_at": null, "created_at": "..."}`

### 2. Sync issues from GitHub
```bash
curl -X POST http://localhost:8000/repos/1/sync
```
Response: `{"repo_id": 1, "created": 100, "updated": 0}`

### 3. List and filter issues
Find unanswered "good-first-issue" issues that haven't been updated in 7 days:
```bash
curl "http://localhost:8000/repos/1/issues?unanswered=true&label=good-first-issue&stale_days=7"
```

## Design Decisions

*   **Idempotent UPSERT**: Sync operations are designed to be run repeatedly safely. Issues are uniquely constrained by `(repo_id, number)`. The sync service uses a dialect-aware UPSERT (`ON DUPLICATE KEY UPDATE` for MySQL, `ON CONFLICT DO UPDATE` for SQLite) to create new rows and update mutable fields (state, comments, etc.) on existing ones without duplication.
*   **Pull Request Filtering**: GitHub's `/issues` endpoint returns pull requests as well. The GitHub client filters out any item containing a `pull_request` key before it reaches the service layer.
*   **Rate Limiting**: Rate limit exhaustion (`X-RateLimit-Remaining: 0`) is intercepted at the client level and raised as a specific `GitHubRateLimitError`, which the API maps to a `429 Too Many Requests` response containing the reset timestamp.
*   **Scale Limitations**: Currently, syncing fetches all open issues. At scale, this would be moved to a background worker (e.g., Celery) to prevent API timeouts, and the sync logic would use GitHub's `since` parameter for incremental updates.
