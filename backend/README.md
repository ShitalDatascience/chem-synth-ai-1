# ChemSynth AI backend (Phase 1)

## Run

Create a virtualenv and install deps (recommended: `uv`):

```bash
cd backend
uv venv
uv pip install -r <(uv pip compile pyproject.toml)
uv run uvicorn app.main:app --reload --port 8000
```

## Environment

The backend reads Postgres config from `DATABASE_URL`, otherwise:

- `DB_NAME` (default `chembl_db`)
- `DB_USER` (default `shitalkale`)
- `DB_PASSWORD` (default empty)
- `DB_HOST` (default `localhost`)
- `DB_PORT` (default `5432`)
- `PG_STATEMENT_TIMEOUT_MS` (default `30000`)

