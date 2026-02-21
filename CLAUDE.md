# CLAUDE.md — Employee HR Database

Project-specific instructions. Global standards: `~/CLAUDE.md`.

## Project

Auto-populating employee database from structured employment documents (PDF contracts, compensation sheets, benefits forms) uploaded to OneDrive. Extracts fields, stores in Postgres (SQLite for local PoC), surfaces compliance alerts via Appsmith portal with RBAC.

**GitHub**: `Mister-ams/moonwalk-employee-hr`
**Roadmap**: `PythonScript/roadmap-employee-hr.md` in `Mister-ams/moonwalk-analytics`

## Architecture

```
PDF contracts (drop file locally for PoC; OneDrive /HR/Contracts/ for Sprint 3+)
        |
        v
ingest_contract.py     <- CLI: python ingest_contract.py "path/to/pdf"
    |
    +-> parse_contract.py   <- pdfplumber + regex, confidence scoring
    |
    +-> db.py               <- SQLite (local PoC); Postgres in Sprint 2+
        |
        v
employees.db           <- local SQLite (gitignored)
```

### Module Roles

| File | Purpose |
|------|---------|
| `parse_contract.py` | MOHRE contract PDF parser — 10 fields, per-field confidence scoring, bilingual layout aware |
| `db.py` | SQLite storage — EID-10xx auto-assign, idempotent upsert on `passport_number` / `mohre_transaction_no` |
| `ingest_contract.py` | CLI — parse + store, exits non-zero and prints failing fields when confidence < 0.95 |

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
# Ingest a contract PDF
python ingest_contract.py "path/to/contract.pdf"

# Query the local DB
sqlite3 employees.db "SELECT employee_id, full_name, job_title, contract_expiry_date FROM employees"
```

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

- **Sprint 1 POC Tick — COMPLETED 2026-02-21**: parser + SQLite storage working against real MOHRE PDF. Frank Ssebaggala ingested as EID-1001, confidence 1.00.
- **Next**: Sprint 2 — schema validation tests, idempotency tests, RBAC baseline (FastAPI + Postgres)
