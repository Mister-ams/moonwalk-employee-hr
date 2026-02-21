"""
CLI entry point: parse a contract PDF and upsert into the local employee database.

Usage:
    python ingest_contract.py "path/to/contract.pdf"
"""

import sys
from pathlib import Path

from parse_contract import parse_contract
from db import upsert_employee

CONFIDENCE_THRESHOLD = 0.95


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

    confidence = result["confidence"]
    fields = result["fields"]
    scores = result["field_scores"]

    # Print per-field extraction results
    print(f"\n{'Field':<25} {'Value':<35} Score")
    print("-" * 65)
    for field, value in fields.items():
        score = scores.get(field, 0.0)
        flag = "" if score >= 1.0 else " <-- LOW"
        print(f"{field:<25} {str(value):<35} {score:.2f}{flag}")

    print(f"\nRecord confidence: {confidence:.2f}")

    if confidence < CONFIDENCE_THRESHOLD:
        print(f"\nFAILED: confidence {confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}")
        print("Routing to exception queue (manual review required).")
        sys.exit(1)

    employee_id = upsert_employee(fields, str(pdf_path), confidence)

    print(f"\nStored: {employee_id}")
    print(f"  Name:             {fields['full_name']}")
    print(f"  Job title:        {fields['job_title']}")
    print(f"  Base salary:      {fields['base_salary']} AED")
    print(f"  Total salary:     {fields['total_salary']} AED")
    print(f"  Contract expiry:  {fields['contract_expiry_date']}")
    print(f"  Insurance status: {fields['insurance_status']} (populated by benefits doc)")


if __name__ == "__main__":
    main()
