"""CSV export endpoint — streams the employee roster."""

import csv
import io
import sqlite3
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from auth import require_api_key
from config import DB_PATH, EXPIRY_WARNING_DAYS

router = APIRouter()


def _build_csv_rows(rows: list[sqlite3.Row]) -> list[dict]:
    today = date.today()
    result = []
    for row in rows:
        r = dict(row)
        expiry_str = r.get("contract_expiry_date")
        if expiry_str:
            try:
                expiry = date.fromisoformat(expiry_str)
                days = (expiry - today).days
            except ValueError:
                days = None
        else:
            days = None
        r["days_until_expiry"] = days
        r["expiry_flag"] = (days is not None) and (days < EXPIRY_WARNING_DAYS)
        result.append(r)
    return result


@router.get("", tags=["export"])
def export_csv(_: str = Depends(require_api_key)):
    """Stream all employees as a CSV file with days_until_expiry and expiry_flag columns."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM employees ORDER BY employee_id").fetchall()

    enriched = _build_csv_rows(rows)

    if not enriched:
        columns = [
            "employee_id",
            "full_name",
            "nationality",
            "date_of_birth",
            "passport_number",
            "job_title",
            "base_salary",
            "total_salary",
            "contract_start_date",
            "contract_expiry_date",
            "insurance_status",
            "mohre_transaction_no",
            "source_file",
            "confidence_score",
            "ingested_at",
            "days_until_expiry",
            "expiry_flag",
        ]
    else:
        columns = list(enriched[0].keys())

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(enriched)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )
