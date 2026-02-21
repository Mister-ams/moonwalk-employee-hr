"""Employee read endpoints."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from auth import require_api_key
from config import DB_PATH

router = APIRouter()


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def _get_or_404(employee_id: str, db_path: Path = DB_PATH) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM employees WHERE employee_id = ?", (employee_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    return _row_to_dict(row)


@router.get("", tags=["employees"])
def list_employees(_: str = Depends(require_api_key)):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM employees ORDER BY employee_id").fetchall()
    return [_row_to_dict(r) for r in rows]


@router.get("/{employee_id}", tags=["employees"])
def get_employee(employee_id: str, _: str = Depends(require_api_key)):
    return _get_or_404(employee_id)
