# Contributing to RepoPulse

Thank you for your interest in contributing!

## Development Setup

1. Make sure you have Python 3.11+ installed.
2. Install the dependencies using the provided `poetry` setup or via standard `pip` in a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install fastapi "uvicorn[standard]" sqlalchemy alembic pydantic pydantic-settings httpx pymysql cryptography pytest pytest-mock pytest-asyncio ruff
   ```

## Running Tests

We use `pytest` with an in-memory SQLite database for fast, isolated testing. No external database or network connection is required.

To run the test suite:
```bash
pytest tests/ -v
```

## Code Quality

We use `ruff` for fast linting and formatting.

To check the code:
```bash
ruff check .
```

Please ensure all tests pass and `ruff` reports no errors before submitting a Pull Request.
