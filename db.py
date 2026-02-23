"""
Postgres storage layer for the Employee HR database.
Auto-assigns EID-10xx employee IDs on first insert; idempotent on re-ingest.

Connection: DATABASE_URL env var (Railway injects this automatically).
"""

import json
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from config import DATABASE_URL

_DDL = """
CREATE TABLE IF NOT EXISTS employees (
    employee_id          TEXT PRIMARY KEY,
    full_name            TEXT NOT NULL,
    nationality          TEXT,
    date_of_birth        TEXT,
    passport_number      TEXT UNIQUE,
    job_title            TEXT,
    base_salary          NUMERIC,
    total_salary         NUMERIC,
    contract_start_date  TEXT,
    contract_expiry_date TEXT,
    insurance_status     TEXT,
    mohre_transaction_no TEXT UNIQUE,
    source_file          TEXT,
    confidence_score     NUMERIC,
    field_scores         JSONB,
    source_doc_type      TEXT,
    ingested_at          TEXT
);

CREATE SEQUENCE IF NOT EXISTS eid_seq START 1;
"""

# Applied once on startup — safe to run against existing deployments.
_MIGRATIONS = [
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS field_scores JSONB",
    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS source_doc_type TEXT",
]


@contextmanager
def _get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
            for migration in _MIGRATIONS:
                cur.execute(migration)


def _next_eid(cur) -> str:
    cur.execute("SELECT nextval('eid_seq')")
    seq = cur.fetchone()[0]
    return f"EID-10{seq:02d}"  # EID-1001, EID-1002, ...


def upsert_employee(
    fields: dict,
    source_file: str,
    confidence: float,
    field_scores: dict,
    doc_type: str = "unknown",
) -> str:
    """
    Insert or update an employee record. Always stores regardless of confidence.
    Deduplication key: passport_number or mohre_transaction_no.
    Returns the employee_id assigned.
    """
    now = datetime.now(timezone.utc).isoformat()
    scores_json = json.dumps(field_scores)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT employee_id FROM employees
                   WHERE passport_number = %s OR mohre_transaction_no = %s""",
                (fields.get("passport_number"), fields.get("mohre_transaction_no")),
            )
            existing = cur.fetchone()

            if existing:
                employee_id = existing[0]
                cur.execute(
                    """UPDATE employees SET
                        full_name=%s, nationality=%s, date_of_birth=%s, job_title=%s,
                        base_salary=%s, total_salary=%s, contract_start_date=%s,
                        contract_expiry_date=%s, insurance_status=%s,
                        source_file=%s, confidence_score=%s, field_scores=%s,
                        source_doc_type=%s, ingested_at=%s
                       WHERE employee_id=%s""",
                    (
                        fields.get("full_name"),
                        fields.get("nationality"),
                        fields.get("date_of_birth"),
                        fields.get("job_title"),
                        fields.get("base_salary"),
                        fields.get("total_salary"),
                        fields.get("contract_start_date"),
                        fields.get("contract_expiry_date"),
                        fields.get("insurance_status"),
                        source_file,
                        confidence,
                        scores_json,
                        doc_type,
                        now,
                        employee_id,
                    ),
                )
            else:
                employee_id = _next_eid(cur)
                cur.execute(
                    """INSERT INTO employees (
                        employee_id, full_name, nationality, date_of_birth, passport_number,
                        job_title, base_salary, total_salary, contract_start_date,
                        contract_expiry_date, insurance_status, mohre_transaction_no,
                        source_file, confidence_score, field_scores, source_doc_type, ingested_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        employee_id,
                        fields.get("full_name"),
                        fields.get("nationality"),
                        fields.get("date_of_birth"),
                        fields.get("passport_number"),
                        fields.get("job_title"),
                        fields.get("base_salary"),
                        fields.get("total_salary"),
                        fields.get("contract_start_date"),
                        fields.get("contract_expiry_date"),
                        fields.get("insurance_status"),
                        fields.get("mohre_transaction_no"),
                        source_file,
                        confidence,
                        scores_json,
                        doc_type,
                        now,
                    ),
                )

    return employee_id


def fetch_all_employees() -> list[dict]:
    """Return all employee rows as a list of dicts, ordered by employee_id."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM employees ORDER BY employee_id")
            return [dict(r) for r in cur.fetchall()]


def fetch_employee(employee_id: str) -> dict | None:
    """Return a single employee by employee_id, or None if not found."""
    with _get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM employees WHERE employee_id = %s", (employee_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def fetch_exceptions() -> list[dict]:
    """
    Return employees with any field score below 0.95 (partial records needing review).
    Excludes insurance_status which is always null until Sprint 3.
    """
    rows = fetch_all_employees()
    result = []
    for row in rows:
        scores = row.get("field_scores") or {}
        if any(v < 0.95 for k, v in scores.items() if k != "insurance_status"):
            result.append(row)
    return result
