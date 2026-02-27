---
project: employee-hr
type: guide
status: active
created: 2026-02-27
updated: 2026-02-27
---

# Phase 1 Wave 1 Completion Notes — employee-hr

## What was done

### S1A — Alembic adoption + pyproject.toml (commit 98271f1)

- Created `pyproject.toml` with all project dependencies, ruff/mypy/pytest config.
  Coverage target is `--cov=.` (flat structure, not `app/`). Pytest ignores the
  `alembic/` directory to avoid importing migration files under test.
- `requirements.txt` preserved but marked deprecated at the top.
- Alembic initialized (`alembic init alembic`).
- `alembic/env.py` rewritten to read `DATABASE_URL` from environment, appends
  `?options=-csearch_path%3Dhr` for loomi-db connections.
- `alembic.ini` `sqlalchemy.url` left blank — URL always comes from env.
- Migration `alembic/versions/001_hr_schema.py` creates `hr` schema +
  `hr.employees` table + `hr.eid_seq` sequence + two unique indexes. Column list
  verified against `db.py` DDL and matches exactly.

### S1D — pydantic-settings + structlog + /health/deep (commit bac97c3)

- `settings.py` created at repo root using `pydantic-settings`. Fields have
  empty-string defaults (not hard required) to preserve the existing graceful
  fallback behaviour in `config.py` and `auth.py`. On Railway, missing env vars
  surface as HTTP 403 / no DB connection rather than startup crash.
- `main.py`: added `import structlog` + `structlog.configure(...)` block for
  JSON-formatted logs with ISO timestamp and log level.
- `routers/health.py`: added `/health/deep` endpoint. Uses `psycopg2.connect`
  directly (no SQLAlchemy session). Returns gracefully if `DATABASE_URL` is unset
  (returns degraded, not 500). Checks pending migrations via AlembicMigrationContext.

### S1E — railway.json (commit 3956ef3)

- `railway.json` created. `startCommand` uses `main:app` (flat structure).
- `preDeployCommand: alembic upgrade head` runs before Railway opens traffic.
- `.gitignore` updated: `employees.db` -> `*.db` glob, added `*.sqlite`, `.venv/`.

### S1F-1 — Pre-commit config (commit bc2681e)

- `.pre-commit-config.yaml` with ruff (v0.9.0), mypy (v1.10.0), detect-secrets
  (v1.5.0), and standard pre-commit-hooks.
- `.secrets.baseline` generated. One known false-positive: `.env.example` line 6
  contains a placeholder password that detect-secrets flags as Basic Auth
  Credentials.

## Deviations from generic plan

| Area | Deviation | Reason |
|------|-----------|--------|
| Flat structure | All files at root, not in `app/` | Original repo design |
| Raw psycopg2 | No SQLAlchemy ORM models | Original repo design |
| `_get_conn()` | Context manager, not `get_db()` | Original repo design |
| settings.py defaults | Fields default to `""` not required | Existing code handles missing vars gracefully; hard crash on startup would break local dev without a .env file |
| `HR_API_KEY` | Not `LOOMI_API_KEY` | Existing env var name in use on Railway |
| Coverage flag | `--cov=.` | Flat structure |
| `eid_seq` in migration | Added `hr.eid_seq` | Mirrors `public.eid_seq` used by `_next_eid()` in db.py |

## Manual actions required before `alembic upgrade head`

1. **Provision loomi-db-staging** (Wave 0 of phase1-PLAN.md) — this migration
   cannot run until `DATABASE_URL` points to a live Postgres instance.
2. Set `DATABASE_URL` on the Railway service (or in `.env` for local dev).
3. Run `alembic upgrade head` manually for first-time setup, or deploy to Railway
   which will run it via `preDeployCommand`.
4. Install pre-commit hooks locally: `pre-commit install` (requires `pre-commit`
   package; not yet in pyproject.toml dev dependencies — add if needed).

## Tests

No test files exist in this repo yet. The `pyproject.toml` sets
`--cov-fail-under=60` which will fail with 0% coverage if pytest is run without
tests. Test scaffolding is a separate sprint (S1G or similar).

## Known gaps

- `settings.py` is created but not yet imported by `main.py` or `config.py`.
  Config reads env vars directly via `os.environ.get`. Wiring settings into the
  app (replacing config.py reads with settings.*) is deferred — it would require
  restructuring existing startup code and re-testing.
- structlog is configured in `main.py` but existing log calls use the stdlib
  `logging` module. Full migration to structlog bound loggers is deferred.
- `pre-commit install` has not been run in this session (requires interactive
  shell with the repo checked out locally by the developer).
