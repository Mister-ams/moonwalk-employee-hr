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
    +-> parse_contract.py  <- 4-strategy extraction chain + per-field PATTERNS
    |       |
    |       +-[1] PyMuPDF (fitz)       <- primary; cleaner Arabic/English separation
    |       +-[2] pdfplumber           <- fallback if fitz page < 100 chars
    |       +-[3] PyMuPDF OCR          <- Tesseract via fitz for scanned pages
    |       +-[4] pytesseract+pdf2image <- legacy OCR if fitz unavailable
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
    /ingest/base64        <- POST — base64 PDF upload (Appsmith workaround)
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
| `parse_contract.py` | MOHRE contract PDF/image parser — 4-strategy extraction chain (PyMuPDF → pdfplumber → PyMuPDF OCR → pytesseract), per-field PATTERNS list, returns `{fields, field_scores, confidence, ocr_used}` |
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

**Live URL**: `https://moonwalk-employee-hr-production.up.railway.app`
**Project**: `moonwalk-employee-hr` on Railway (mister-ams's Projects)

```
Railway env vars:
  HR_API_KEY     — set (see .env.example for key storage)
  DATABASE_URL   — set automatically via Railway Postgres plugin (persistent)

Build: nixpacks picks up requirements.txt automatically
Start: Procfile -> uvicorn main:app --host 0.0.0.0 --port $PORT
```

**Postgres + Railway**: Storage is backed by Railway's managed Postgres plugin. `DATABASE_URL` is injected automatically and data persists across redeploys. No volume mount needed.

**IMPORTANT — No GitHub auto-deploy**: Railway service has `source: null` — git pushes do NOT trigger deployments. Always run `railway up` from `~/Downloads/EmployeeHR/` after pushing to deploy.

**Tesseract not on Railway**: OCR via Tesseract is unavailable in the Railway container. Scanned pages fall through to LLM vision (score 0.80) or LLM text fallback. Mixed documents (some pages text, some scanned) use LLM text fallback — scanned pages' content (e.g. Adil's salary page) will not be extracted and must be entered manually.

## Critical Gotchas

**Extraction strategy** — `parse_contract.py` tries 4 strategies per page in order. The threshold `_MIN_TEXT_CHARS = 100` decides whether fitz/pdfplumber output is "good enough" or OCR is needed. Strategy priority: PyMuPDF (fitz) → pdfplumber → PyMuPDF OCR via Tesseract → pytesseract+pdf2image (legacy). Both `PYMUPDF_AVAILABLE` and `LEGACY_OCR_AVAILABLE` are soft flags set at import time — parser degrades gracefully if optional deps are missing.

**PATTERNS is a prioritized list per field** — each field maps to `list[tuple[pattern, flags]]`. `_match_field()` uses `re.finditer` (not `re.search`) so that when a pattern matches multiple times, each occurrence is tried before falling through to the next pattern. This handles OCR noise where a garbled value appears before the real one (e.g. `"99/11/1999"` before `"29/11/1999"` for date_of_birth).

**Nationality anchor** — primary pattern anchors to `2.?\s*Name` prefix: `r"2\.?\s*Name\s+[A-Z][A-Z ]+\s+Nationality\s+([A-Z]+)"`. Without this anchor, a bare `Nationality\s+([A-Z]+)` matches the employer's "Nationality EMIRATES" instead of the employee's nationality. The dot after `2` is optional because OCR sometimes drops it.

**PyMuPDF OCR GC bug** — must hold `page` reference as a local variable during `get_textpage_ocr()`. The page object must not be GC'd while the textpage is in use. Pattern: `page = doc[i]` → `tp = page.get_textpage_ocr(...)` → `text = page.get_text(textpage=tp)`. Always wrap `doc` in a try/finally with `doc.close()`.

**Tesseract auto-discovery** — `_ocr_page_fitz()` tries `tessdata=None` (PATH default) first, then `C:/Program Files/Tesseract-OCR/tessdata`, then the x86 path. `RuntimeError` is caught per-candidate. If none work, returns `""` (does not raise).

**Job Offer format** — `contract_start_date` and `contract_expiry_date` are absent in MOHRE Job Offer documents (no `"starting from"` / `"ending on"` phrases). These records get `confidence=0.0` and correctly route to the exception queue. This is expected behaviour, not a parser bug.

**pdfplumber bilingual layout** — still relevant as the fallback extractor. Three non-obvious patterns that pdfplumber requires (PyMuPDF handles these cleanly but pdfplumber is still used on pages where fitz yields < 100 chars):

- `date_of_birth`: pdfplumber splits the cell to `"Date 14/04/1996"` — pattern `r"\bDate\b\s+(\d{2}/\d{2}/\d{4})"` (list position 2, after PyMuPDF pattern)
- `passport_number`: value appears before `"Telephone"` label — pattern `r"([A-Z][0-9A-Z]{5,})\s+Telephone"` (list position 2, fallback only)
- `mohre_transaction_no`: Arabic text between label and value across newline — pattern `r"Transaction Number[^\n]*\n([A-Z0-9]+)"` (list position 2)

**insurance_status**: NOT present in MOHRE contract PDFs — always `null` until Sprint 3 (benefits form). Confidence scoring treats it as 1.0.

**confidence threshold**: 0.95 — records below this are printed with per-field scores and not stored.

## Current State

- **Sprint 1 POC Tick — COMPLETED 2026-02-21**: parser + SQLite storage working. Frank Ssebaggala (EID-1001), confidence 1.00.
- **Sprint 2 Local Operations Tick — COMPLETED 2026-02-21**: `ingest_folder.py`, `export_employees.py`, FastAPI (health/employees/ingest/export), Railway config (Procfile, requirements.txt, config.py, auth.py, .env.example).
- **Sprint 2B Appsmith Portal Bootstrap — COMPLETED 2026-02-22**: HR Portal live at `https://app.appsmith.com/app/hr-portal/page1-699a032d2267980abdf9034d`. 4 queries wired (GetEmployees/GetEmployee/IngestPDF/ExportCSV), EmployeeTable + FilePicker + Upload Contract + Download CSV buttons. `/ingest/base64` endpoint added for Appsmith upload compatibility. Setup guide: `appsmith/hr-portal-setup.md`.
- **Parser hardening — commit `5db2374` (2026-02-23)**: PyMuPDF added as primary extractor, Tesseract OCR wired for scanned pages, PATTERNS refactored to prioritized list per field. Validated against 3 real contracts: Frank 10/10 (confidence 1.0), Adil 10/10 (confidence 1.0, OCR used for scanned salary page), Altahir 8/10 (confidence 0.0 — Job Offer format lacks contract dates, routes to exception queue correctly).
- **Per-field review — commit `bbdd211` (2026-02-24)**: `confidence` → `min_field_score` throughout (floor of per-field scores, not a doc-level gate). `_build_needs_review` now includes `current_value` per flagged field. API response adds `field_scores` dict. Documents always stored; only individual low-confidence fields flagged.
- **Railway verified (2026-02-24)**: All 3 contracts return 201. Frank: 10/10 score 1.0. Altahir: 10/10 score 0.8 via LLM vision. Adil: 8/10 score 0.0 (salary fields null — scanned page, no Tesseract on Railway, correctly flagged `enter_manually`).
- **Tests**: 0 (no test suite yet — Sprint 4 mandates ≥80% coverage)
- **Next**: Sprint 2C (portal UX brainstorm, mobile-first layout design) → Sprint 3 MVP
