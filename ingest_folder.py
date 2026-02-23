"""
Batch-ingest all contract PDFs in a folder.
Always stores every record — partial extractions are flagged for review, not rejected.
A partial-records CSV is written for any record where any field scored below 0.95.

Usage:
    python ingest_folder.py "path/to/contracts/"
    python ingest_folder.py "path/to/contracts/" --partials-out "path/to/partials.csv"
"""

import csv
import sys
from pathlib import Path

from db import upsert_employee
from parse_contract import parse_contract

DEFAULT_PARTIALS_FILE = "partial_records.csv"

_PARTIAL_FIELDS = [
    "employee_id",
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
    "mohre_transaction_no",
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


def ingest_folder(folder: Path, partials_out: Path) -> dict:
    """
    Process all PDFs in *folder*. Returns summary counts.
    All records are stored. Partial records (any field < 0.95) are written to *partials_out*.
    """
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in: {folder}")
        return {"total": 0, "stored": 0, "partial": 0, "failed": 0}

    total = len(pdfs)
    stored = 0
    partial = 0
    failed = 0
    partial_rows = []

    for pdf in pdfs:
        print(f"Processing: {pdf.name}", end="  ", flush=True)
        try:
            result = parse_contract(pdf)
        except Exception as exc:
            print("ERROR")
            failed += 1
            partial_rows.append(
                {
                    "source_file": pdf.name,
                    "confidence": 0.0,
                    "error": str(exc),
                    **{
                        f: None
                        for f in _PARTIAL_FIELDS
                        if f not in ("source_file", "confidence", "error")
                    },
                }
            )
            continue

        fields = result["fields"]
        scores = result["field_scores"]
        min_field_score = result["min_field_score"]

        employee_id = upsert_employee(fields, str(pdf), min_field_score, scores)

        needs_review = [
            f for f, s in scores.items() if f != "insurance_status" and s < 0.95
        ]

        if needs_review:
            tag = f"PARTIAL ({len(needs_review)} field(s) need review)"
            partial += 1
            row = {
                "employee_id": employee_id,
                "source_file": pdf.name,
                "confidence": min_field_score,
                "error": "",
            }
            for f in fields:
                row[f] = fields[f]
            for f, s in scores.items():
                row[f"score_{f}"] = s
            for col in _PARTIAL_FIELDS:
                if col not in row:
                    row[col] = None
            partial_rows.append(row)
        else:
            tag = "OK"

        print(f"{tag} -> {employee_id}")
        stored += 1

    if partial_rows:
        with open(partials_out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=_PARTIAL_FIELDS, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(partial_rows)
        print(f"\nPartial records written to: {partials_out}")

    return {"total": total, "stored": stored, "partial": partial, "failed": failed}


def _print_summary(summary: dict) -> None:
    print()
    print("-" * 45)
    print(f"{'Total PDFs processed':<28} {summary['total']}")
    print(f"{'Stored / updated':<28} {summary['stored']}")
    print(f"{'  of which partial (needs review)':<28} {summary['partial']}")
    print(f"{'Failed (parse error)':<28} {summary['failed']}")
    print("-" * 45)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: python ingest_folder.py <folder> [--partials-out <path>]")
        sys.exit(1)

    folder = Path(args[0])
    if not folder.is_dir():
        print(f"Not a directory: {folder}")
        sys.exit(1)

    partials_out = Path(DEFAULT_PARTIALS_FILE)
    if "--partials-out" in args:
        idx = args.index("--partials-out")
        if idx + 1 < len(args):
            partials_out = Path(args[idx + 1])
    # Backward-compat alias
    elif "--exceptions-out" in args:
        idx = args.index("--exceptions-out")
        if idx + 1 < len(args):
            partials_out = Path(args[idx + 1])

    summary = ingest_folder(folder, partials_out)
    _print_summary(summary)

    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
