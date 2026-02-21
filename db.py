"""
SQLite storage layer for the Employee HR database.
Auto-assigns EID-10xx employee IDs on first insert; idempotent on re-ingest.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DB_PATH

_DDL = """
CREATE TABLE IF NOT EXISTS employees (
    employee_id          TEXT PRIMARY KEY,
    full_name            TEXT NOT NULL,
    nationality          TEXT,
    date_of_birth        TEXT,
    passport_number      TEXT UNIQUE,
    job_title            TEXT,
    base_salary          REAL,
    total_salary         REAL,
    contract_start_date  TEXT,
    contract_expiry_date TEXT,
    insurance_status     TEXT,
    mohre_transaction_no TEXT UNIQUE,
    source_file          TEXT,
    confidence_score     REAL,
    ingested_at          TEXT
);

CREATE TABLE IF NOT EXISTS _eid_seq (
    id INTEGER PRIMARY KEY AUTOINCREMENT
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(_DDL)


def _next_eid(conn: sqlite3.Connection) -> str:
    conn.execute("INSERT INTO _eid_seq DEFAULT VALUES")
    seq = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return f"EID-10{seq:02d}"  # EID-1001, EID-1002, ...


def upsert_employee(
    fields: dict, source_file: str, confidence: float, db_path: Path = DB_PATH
) -> str:
    """
    Insert or update an employee record.
    Deduplication key: passport_number or mohre_transaction_no.
    Returns the employee_id assigned.
    """
    init_db(db_path)
    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            """SELECT employee_id FROM employees
               WHERE passport_number = ? OR mohre_transaction_no = ?""",
            (fields.get("passport_number"), fields.get("mohre_transaction_no")),
        ).fetchone()

        if existing:
            employee_id = existing[0]
            conn.execute(
                """UPDATE employees SET
                    full_name=?, nationality=?, date_of_birth=?, job_title=?,
                    base_salary=?, total_salary=?, contract_start_date=?,
                    contract_expiry_date=?, insurance_status=?,
                    source_file=?, confidence_score=?, ingested_at=?
                   WHERE employee_id=?""",
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
                    now,
                    employee_id,
                ),
            )
        else:
            employee_id = _next_eid(conn)
            conn.execute(
                """INSERT INTO employees (
                    employee_id, full_name, nationality, date_of_birth, passport_number,
                    job_title, base_salary, total_salary, contract_start_date,
                    contract_expiry_date, insurance_status, mohre_transaction_no,
                    source_file, confidence_score, ingested_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
                    now,
                ),
            )

    return employee_id
