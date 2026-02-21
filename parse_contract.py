"""
Contract PDF parser for UAE Ministry of Human Resources (MOHRE) standard employment contracts.
Extracts fields using regex against the consistent government template layout.
"""

import re
import pdfplumber
from datetime import datetime
from pathlib import Path


# (pattern, confidence_if_matched)
PATTERNS = {
    "full_name": r"2\.\s*Name\s+([A-Z][A-Z ]+)",
    "nationality": r"Nationality\s+([A-Z]+)\s",
    # pdfplumber splits the DoB table cell — "Date" lands alone before the value
    "date_of_birth": r"\bDate\b\s+(\d{2}/\d{2}/\d{4})",
    # Arabic column reorders text: passport value precedes the "Telephone" label
    "passport_number": r"([A-Z][0-9A-Z]{5,})\s+Telephone",
    "job_title": r"profession of\s+(.+?)\s+in the UAE",
    "base_salary": r"Basic Salary:\s*(\d+(?:\.\d+)?)\s*AED",
    "total_salary": r"Total Salary:\s*(\d+(?:\.\d+)?)\s*AED",
    "contract_start_date": r"starting from\s+(\d{2}/\d{2}/\d{4})",
    "contract_expiry_date": r"ending on\s+(\d{2}/\d{2}/\d{4})",
    # Arabic text sits between label and value — value is on the next line
    "mohre_transaction_no": r"Transaction Number[^\n]*\n([A-Z0-9]+)",
}

DATE_FIELDS = {"date_of_birth", "contract_start_date", "contract_expiry_date"}
DECIMAL_FIELDS = {"base_salary", "total_salary"}


def _to_iso(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")


def parse_contract(pdf_path: Path) -> dict:
    """
    Parse a MOHRE contract PDF and return extracted fields with per-field confidence scores.

    Returns:
        {
            "fields":       { field_name: value, ... },
            "field_scores": { field_name: 0.0 | 1.0, ... },
            "confidence":   float  # min of required field scores
        }
    """
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    fields = {}
    scores = {}

    for field, pattern in PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip()
            if field in DATE_FIELDS:
                try:
                    value = _to_iso(value)
                    scores[field] = 1.0
                except ValueError:
                    value = None
                    scores[field] = 0.0
            elif field in DECIMAL_FIELDS:
                try:
                    value = float(value)
                    scores[field] = 1.0
                except ValueError:
                    value = None
                    scores[field] = 0.0
            else:
                scores[field] = 1.0
            fields[field] = value
        else:
            fields[field] = None
            scores[field] = 0.0

    # insurance_status is not present in contract PDFs — populated by benefits doc in Sprint 3
    fields["insurance_status"] = None
    scores["insurance_status"] = 1.0  # expected null, not an extraction failure

    # Record confidence = min score across all required fields (excluding insurance_status)
    required = [k for k in scores if k != "insurance_status"]
    confidence = min(scores[k] for k in required)

    return {
        "fields": fields,
        "field_scores": scores,
        "confidence": confidence,
    }
