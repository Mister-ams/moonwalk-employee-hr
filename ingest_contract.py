"""
CLI entry point: parse a contract PDF and upsert into the local employee database.
Always stores the record — partial extractions are flagged for review, not rejected.

Usage:
    python ingest_contract.py "path/to/contract.pdf"
"""

import sys
from pathlib import Path

from db import upsert_employee
from parse_contract import parse_contract

_SOURCE_LABELS = {
    1.0: "regex",
    0.85: "LLM",
    0.0: "not found",
}


def _print_review_summary(fields: dict, scores: dict) -> list[str]:
    """Print per-field table and return list of field names needing review."""
    print(f"\n  {'Field':<25} {'Value':<30} {'Score':<6} Source")
    print("  " + "-" * 70)
    for field, value in fields.items():
        if field == "insurance_status":
            continue
        score = scores.get(field, 0.0)
        source = _SOURCE_LABELS.get(score, "LLM")
        flag = "  <-- REVIEW" if score < 0.95 else ""
        print(f"  {field:<25} {str(value):<30} {score:<6.2f} {source}{flag}")

    needs_review = [f for f, s in scores.items() if f != "insurance_status" and s < 0.95]
    return needs_review


def main():
    if len(sys.argv) < 2:
        print("Usage: python ingest_contract.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    print(f"Parsing: {pdf_path.name}")
    result = parse_contract(pdf_path)

    fields = result["fields"]
    scores = result["field_scores"]
    min_field_score = result["min_field_score"]
    ocr_used = result["ocr_used"]
    doc_type = result["doc_type"]

    needs_review = _print_review_summary(fields, scores)

    employee_id = upsert_employee(fields, str(pdf_path), min_field_score, scores, doc_type)

    print(f"\nStored: {employee_id}  {fields.get('full_name', '(unknown)')}")
    if ocr_used:
        print("  Note: OCR was used on one or more pages.")

    if doc_type == "job_offer":
        print("\n  WARNING: This is a Job Offer document, not a signed Employment Contract.")
        print("  Contract dates are derived from signing date + contract duration.")
        print("  Action: upload the Employment Contract (MB-series) to confirm dates.")

    if needs_review:
        print(f"\n  {len(needs_review)} field(s) require review:")
        for field in needs_review:
            score = scores[field]
            if score == 0.0:
                action = "not found — enter manually"
            else:
                action = "extracted by LLM — spot-check recommended"
            print(f"    - {field:<25} {action}")
    else:
        print("  All fields confirmed.")


if __name__ == "__main__":
    main()
