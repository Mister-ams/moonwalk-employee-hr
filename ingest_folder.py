"""
Batch-ingest all contract PDFs in a folder.

Usage:
    python ingest_folder.py "path/to/contracts/"
    python ingest_folder.py "path/to/contracts/" --exceptions-out "path/to/exceptions.csv"

Idempotent: files whose passport_number or mohre_transaction_no already exists in the
database are updated (not duplicated). Confidence failures are written to exceptions.csv.
"""

import csv
import sys
from pathlib import Path

from config import CONFIDENCE_THRESHOLD
from db import upsert_employee
from parse_contract import parse_contract

DEFAULT_EXCEPTIONS_FILE = "exceptions.csv"

EXCEPTION_FIELDS = [
    "source_file",
    "confidence",
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
    # per-field scores
    "score_full_name",
    "score_nationality",
    "score_date_of_birth",
    "score_passport_number",
    "score_job_title",
    "score_base_salary",
    "score_total_salary",
    "score_contract_start_date",
    "score_contract_expiry_date",
    "score_mohre_transaction_no",
    "error",
]


def ingest_folder(folder: Path, exceptions_out: Path) -> dict:
    """
    Process all PDFs in *folder*. Returns summary counts.
    Low-confidence records are written to *exceptions_out* CSV.
    """
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in: {folder}")
        return {"total": 0, "stored": 0, "skipped": 0, "failed": 0}

    total = len(pdfs)
    stored = 0
    skipped = 0
    failed = 0
    exceptions = []

    for pdf in pdfs:
        print(f"Processing: {pdf.name}", end="  ", flush=True)
        try:
            result = parse_contract(pdf)
        except Exception as exc:
            print("ERROR")
            failed += 1
            exceptions.append(
                {
                    "source_file": pdf.name,
                    "confidence": 0.0,
                    "error": str(exc),
                    **{
                        f: None
                        for f in EXCEPTION_FIELDS
                        if f not in ("source_file", "confidence", "error")
                    },
                }
            )
            continue

        confidence = result["confidence"]
        fields = result["fields"]
        scores = result["field_scores"]

        if confidence < CONFIDENCE_THRESHOLD:
            print(f"LOW CONFIDENCE ({confidence:.2f})")
            failed += 1
            row = {
                "source_file": pdf.name,
                "confidence": confidence,
                "error": "",
            }
            for f in fields:
                row[f] = fields[f]
            for f in scores:
                row[f"score_{f}"] = scores[f]
            # Fill missing columns
            for col in EXCEPTION_FIELDS:
                if col not in row:
                    row[col] = None
            exceptions.append(row)
            continue

        employee_id = upsert_employee(fields, str(pdf), confidence)
        # Distinguish new inserts from updates by checking if EID existed before
        print(f"OK -> {employee_id}")
        stored += 1

    # Write exceptions CSV
    if exceptions:
        with open(exceptions_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=EXCEPTION_FIELDS, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(exceptions)
        print(f"\nExceptions written to: {exceptions_out}")
    else:
        skipped = 0  # No exceptions at all

    return {"total": total, "stored": stored, "skipped": skipped, "failed": failed}


def _print_summary(summary: dict) -> None:
    print()
    print("-" * 40)
    print(f"{'Total PDFs processed':<25} {summary['total']}")
    print(f"{'Stored / updated':<25} {summary['stored']}")
    print(f"{'Failed (low conf/error)':<25} {summary['failed']}")
    print("-" * 40)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python ingest_folder.py <folder> [--exceptions-out <path>]")
        sys.exit(1)

    folder = Path(args[0])
    if not folder.is_dir():
        print(f"Not a directory: {folder}")
        sys.exit(1)

    exceptions_out = Path(DEFAULT_EXCEPTIONS_FILE)
    if "--exceptions-out" in args:
        idx = args.index("--exceptions-out")
        if idx + 1 < len(args):
            exceptions_out = Path(args[idx + 1])

    summary = ingest_folder(folder, exceptions_out)
    _print_summary(summary)

    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
