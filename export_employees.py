"""
Export the employee roster to employees.csv.

Usage:
    python export_employees.py
    python export_employees.py --out "path/to/employees.csv"

Output columns:
    All database fields + days_until_expiry (int) + expiry_flag (True/False)
    expiry_flag is True when days_until_expiry < EXPIRY_WARNING_DAYS (default 30).
    Dates are YYYY-MM-DD; numbers are numeric (no currency symbols).
"""

import csv
import sys
from datetime import date
from pathlib import Path

from config import EXPIRY_WARNING_DAYS
from db import fetch_all_employees

DEFAULT_OUT = "employees.csv"

COLUMNS = [
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


def export_employees(out: Path = Path(DEFAULT_OUT)) -> int:
    """Export all employees to *out*. Returns the number of rows written."""
    today = date.today()
    rows = fetch_all_employees()

    count = 0
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()

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
            writer.writerow({col: r.get(col) for col in COLUMNS})
            count += 1

    return count


def main():
    out = Path(DEFAULT_OUT)
    args = sys.argv[1:]
    if "--out" in args:
        idx = args.index("--out")
        if idx + 1 < len(args):
            out = Path(args[idx + 1])

    n = export_employees(out)
    if n == 0:
        print("No employees to export.")
    else:
        print(f"Exported {n} employee(s) to: {out}")


if __name__ == "__main__":
    main()
