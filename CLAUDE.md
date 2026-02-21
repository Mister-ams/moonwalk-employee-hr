# CLAUDE.md — Employee HR Database

Project-specific instructions. Global standards: `~/CLAUDE.md`.

## Project

Extract structured employee data from UAE MOHRE labour contract PDFs into a locally operated SQLite database, exported to CSV/Excel for daily use. Priority is clearing the PDF extraction technical hurdle and producing a usable employee roster locally. Cloud-native infrastructure (OneDrive sync, Postgres, FastAPI, RBAC, Appsmith) is a future phase.

**GitHub**: `Mister-ams/moonwalk-employee-hr`
**Roadmap**: `PythonScript/roadmap-employee-hr.md` in `Mister-ams/moonwalk-analytics`

## Architecture

```
PDF contracts (drop file locally for PoC; OneDrive /HR/Contracts/ for Sprint 3+)
        |
        v
ingest_contract.py         <- CLI: single PDF
ingest_folder.py           <- CLI: batch folder
    |
    +-> parse_contract.py  <- pdfplumber + regex, confidence scoring
    |
    +-> db.py              <- SQLite storage (Postgres in Sprint 3+)
        |
        v
employees.db               <- local SQLite (gitignored)
        |
        v
export_employees.py        <- CSV export with days_until_expiry + expiry_flag

FastAPI (main.py)
    /health               <- GET — health check (no auth)
    /employees            <- GET — list all employees
    /employees/{id}       <- GET — single employee
    /ingest               <- POST — upload PDF, parse + store
    /export/csv           <- GET — stream employees.csv
```

### Module Roles

| File | Purpose |
|------|---------|
| `config.py` | Env-var based `DB_PATH` (`HR_DB_PATH`), `API_KEY` (`HR_API_KEY`), `CONFIDENCE_THRESHOLD`, `EXPIRY_WARNING_DAYS` |
| `auth.py` | FastAPI `X-API-Key` dependency — reads `HR_API_KEY` at request time, fail-closed |
| `main.py` | FastAPI entrypoint — lifespan (`init_db`), CORS, route registration |
| `routers/health.py` | `GET /health` |
| `routers/employees.py` | `GET /employees`, `GET /employees/{id}` |
| `routers/ingest.py` | `POST /ingest` — multipart PDF upload, parse, upsert; 422 on low confidence with per-field scores |
| `routers/export.py` | `GET /export/csv` — streams CSV with `days_until_expiry` + `expiry_flag` columns |
| `parse_contract.py` | MOHRE contract PDF parser — 10 fields, per-field confidence scoring, bilingual layout aware |
| `db.py` | SQLite storage — EID-10xx auto-assign, idempotent upsert on `passport_number` / `mohre_transaction_no` |
| `ingest_contract.py` | CLI — single PDF parse + store, exits non-zero below confidence threshold |
| `ingest_folder.py` | CLI — batch folder ingest, idempotent, writes `exceptions.csv` for low-confidence records |
| `export_employees.py` | CLI — SQLite → `employees.csv` with `days_until_expiry` + `expiry_flag` |

### Employee ID Standard

Format: `EID-10xx` — EID-1001, EID-1002, ...
Assigned on first insert; stable across re-ingests.
Deduplication key: `passport_number` OR `mohre_transaction_no` (whichever matches first).

### Document Types

| Type | Sprint | Fields |
|------|--------|--------|
| Employment contract PDF (MOHRE standard) | 1 — done | full_name, nationality, date_of_birth, passport_number, job_title, base_salary, total_salary, contract_start_date, contract_expiry_date, mohre_transaction_no |
| Compensation sheet | 3 | TBD |
| Benefits form | 3 | insurance_status (confirmed NOT in contract PDF) |

## Commands

```bash
# Run the API (local dev)
uvicorn main:app --reload --port 8001

# Ingest a single contract PDF
python ingest_contract.py "path/to/contract.pdf"

# Ingest all PDFs in a folder
python ingest_folder.py "path/to/contracts/"
python ingest_folder.py "path/to/contracts/" --exceptions-out "path/to/exceptions.csv"

# Export roster to CSV
python export_employees.py
python export_employees.py --out "path/to/employees.csv"

# Query the local DB
sqlite3 employees.db "SELECT employee_id, full_name, job_title, contract_expiry_date FROM employees"
```

## Railway Deployment

```
Railway env vars required:
  HR_API_KEY     — API key for the service (generate with secrets.token_urlsafe(32))
  HR_DB_PATH     — Set to /data/employees.db if a volume is mounted; omit for ephemeral

Build: nixpacks picks up requirements.txt automatically
Start: Procfile -> uvicorn main:app --host 0.0.0.0 --port $PORT
```

**SQLite + Railway**: Without a mounted volume, the DB resets on each deploy. For persistent storage, mount a volume at `/data` and set `HR_DB_PATH=/data/employees.db`. Postgres migration is Sprint 3.

## Critical Gotchas

**pdfplumber + bilingual MOHRE PDFs** — Arabic column reorders extracted text. Three non-obvious patterns:

- `date_of_birth`: table cell splits to `"Date 14/04/1996"` (not `"Date of Birth"`).
  Pattern: `r"\bDate\b\s+(\d{2}/\d{2}/\d{4})"`

- `passport_number`: value appears on the line BEFORE the `Passport Number` label.
  Pattern: `r"([A-Z][0-9A-Z]{5,})\s+Telephone"`

- `mohre_transaction_no`: Arabic text sits between label and value across a newline.
  Pattern: `r"Transaction Number[^\n]*\n([A-Z0-9]+)"`

**insurance_status**: NOT present in MOHRE contract PDFs — field is always `null` until Sprint 3 (benefits form). This is expected; confidence scoring treats it as 1.0.

**confidence threshold**: 0.95 — records below this are printed with per-field scores and not stored.

## Current State

- **Sprint 1 POC Tick — COMPLETED 2026-02-21**: parser + SQLite storage working. Frank Ssebaggala (EID-1001), confidence 1.00.
- **Sprint 2 Local Operations Tick — COMPLETED 2026-02-21**: `ingest_folder.py`, `export_employees.py`, FastAPI (health/employees/ingest/export), Railway config (Procfile, requirements.txt, config.py, auth.py, .env.example).
- **Next**: Sprint 3 — MVP (Prefect, three document types, compliance rules, Appsmith exception queue)
