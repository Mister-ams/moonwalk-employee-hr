"""CSV export endpoint — streams the employee roster."""

import csv
import io
from datetime import date

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from auth import require_api_key
from config import EXPIRY_WARNING_DAYS
from db import fetch_all_employees

router = APIRouter()

_COLUMNS = [
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


def _enrich(rows: list[dict]) -> list[dict]:
    today = date.today()
    for r in rows:
        expiry_str = r.get("contract_expiry_date")
        if expiry_str:
            try:
                days = (date.fromisoformat(str(expiry_str)) - today).days
            except ValueError:
                days = None
        else:
            days = None
        r["days_until_expiry"] = days
        r["expiry_flag"] = (days is not None) and (days < EXPIRY_WARNING_DAYS)
    return rows


@router.get("", tags=["export"])
def export_csv(_: str = require_api_key):
    """Stream all employees as a CSV file with days_until_expiry and expiry_flag columns."""
    rows = _enrich(fetch_all_employees())

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )
