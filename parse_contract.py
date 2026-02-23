"""
Contract PDF / image parser for UAE MOHRE standard employment contracts.
Extraction strategy (tried in order per page):
  1. PyMuPDF (fitz) — cleaner Arabic/English separation; primary extractor
  2. pdfplumber — fallback for pages where fitz yields too little text
  3. PyMuPDF OCR via Tesseract — for scanned pages (requires Tesseract installed)
  4. pytesseract + pdf2image — legacy OCR path for images and PDF pages

Each field tries patterns in order; first match wins.
"""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image

    LEGACY_OCR_AVAILABLE = True
except ImportError:
    LEGACY_OCR_AVAILABLE = False

# Each field maps to a list of (pattern, flags) tuples tried in order.
_S = re.IGNORECASE
_SD = re.IGNORECASE | re.DOTALL

PATTERNS: dict[str, list[tuple[str, int]]] = {
    "full_name": [
        # PyMuPDF/pdfplumber: "2. Name FRANK ..." or "2 Name\nFRANK ..." (OCR may drop the dot)
        # [A-Z ]+ stops at newlines and Arabic chars naturally
        (r"2\.?\s*Name\s+([A-Z][A-Z ]+)", _S),
    ],
    "nationality": [
        # PyMuPDF: "2. Name\n[NAME]\nNationality\n[COUNTRY]"
        # Anchors to employee section — avoids matching employer's "Nationality EMIRATES"
        # \.? — OCR sometimes drops the dot in "2. Name"
        (r"2\.?\s*Name\s+[A-Z][A-Z ]+\s+Nationality\s+([A-Z]+)", _S),
        # pdfplumber fallback: employee nationality appears before their DOB on same line
        # e.g. "Nationality PAKISTAN of 05/08/1999" — employer line never has "of [date]"
        (r"Nationality\s+([A-Z]+)\s+of\s+\d{2}/\d{2}/\d{4}", _S),
        # OCR fallback: employer nationality appears BEFORE the "First Party / Employer" marker;
        # employee nationality appears after it — use lazy DOTALL to skip OCR noise between them
        (r"First Party.+?Nationality\s*([A-Z]+)", _SD),
    ],
    "date_of_birth": [
        # PyMuPDF: "Date\nof\nBirth\n14/04/1996"
        (r"Date\s+of\s+Birth\s+(\d{2}/\d{2}/\d{4})", _S),
        # pdfplumber Frank: "Date 14/04/1996" (value immediately after label)
        (r"\bDate\b\s+(\d{2}/\d{2}/\d{4})", _S),
        # pdfplumber Adil: "Nationality PAKISTAN of 05/08/1999" (DOB embedded in nationality line)
        (r"Nationality\s+[A-Z]+\s+of\s+(\d{2}/\d{2}/\d{4})", _S),
        # OCR noise: scanned PDFs sometimes produce a garbled day ("99/11/1999") before the real
        # date ("29/11/1999") — skip the first invalid date and capture the second
        (r"(?:Date|Daret)[^\d]+\d{2}/\d{2}/\d{4}[^\d]+(\d{2}/\d{2}/\d{4})", _S),
        # OCR fallback: any DOB-adjacent label ("Daret", "Birt") followed by a single date
        (r"(?:Date|Daret|Birth|Birt)[^\d]+(\d{2}/\d{2}/\d{4})", _S),
    ],
    "passport_number": [
        # PyMuPDF: "Passport Number\nA00580269" or "Passport\nNumber\nWE4134592"
        # OCR: "PassportNumber P10474550" (no space — \s* handles both)
        # Employer uses "Passport No" — "Passport Number" is employee-only
        (r"Passport\s*Number\s+([A-Z][0-9A-Z]{5,})", _S),
        # pdfplumber fallback: Arabic column reorders text; passport value precedes "Telephone"
        (r"([A-Z][0-9A-Z]{5,})\s+Telephone", _S),
    ],
    "job_title": [
        # PyMuPDF: "profession of Launderer\nin the UAE" — clean, no Arabic on same line
        # pdfplumber: "profession of Sales Officer in the UAE" (same line)
        # OCR noise: "profession of Laundererin the UAE" (space dropped before "in")
        # \s* (not \s+) handles the zero-space OCR case; lazy match stops at first "in the UAE"
        (r"profession of\s+(.+?)\s*in the UAE", _SD),
    ],
    "base_salary": [
        (r"Basic Salary:\s*(\d+(?:\.\d+)?)\s*AED", _S),
    ],
    "total_salary": [
        (r"Total Salary:\s*(\d+(?:\.\d+)?)\s*AED", _S),
    ],
    "contract_start_date": [
        (r"starting from\s+(\d{2}/\d{2}/\d{4})", _S),
    ],
    "contract_expiry_date": [
        # [^\d]* matches Arabic text / newlines between label and date without re.DOTALL
        (r"ending on[^\d]*(\d{2}/\d{2}/\d{4})", _S),
    ],
    "mohre_transaction_no": [
        # PyMuPDF + Adil pdfplumber: value on same or next line after label
        (r"Transaction Number\s+([A-Z0-9]+)", _S),
        # Frank pdfplumber: Arabic sits between label and value across a newline
        (r"Transaction Number[^\n]*\n([A-Z0-9]+)", _S),
    ],
}

DATE_FIELDS = {"date_of_birth", "contract_start_date", "contract_expiry_date"}
DECIMAL_FIELDS = {"base_salary", "total_salary"}

# Pages whose extracted text is shorter than this are treated as scanned
_MIN_TEXT_CHARS = 100


def _to_iso(value: str) -> str:
    return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")


def _extract_pdfplumber_safe(pdf_path: Path) -> tuple[str, list[str]]:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages), pages


def _extract_text_fitz(pdf_path: Path) -> tuple[str, list[str]]:
    """Extract text using PyMuPDF (cleaner Arabic/English separation)."""
    doc = fitz.open(str(pdf_path))
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages), pages


_TESSDATA_CANDIDATES = [
    None,  # environment default (works when tesseract is in PATH)
    "C:/Program Files/Tesseract-OCR/tessdata",
    "C:/Program Files (x86)/Tesseract-OCR/tessdata",
]


def _ocr_page_fitz(pdf_path: Path, page_index: int) -> str:
    """OCR a single PDF page via PyMuPDF's built-in Tesseract integration.

    Tries the environment default first, then common Windows install paths.
    Returns empty string if Tesseract is not found.
    """
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]  # hold reference so textpage isn't GC'd
        for tessdata in _TESSDATA_CANDIDATES:
            try:
                kwargs: dict = {"language": "eng"}
                if tessdata:
                    kwargs["tessdata"] = tessdata
                tp = page.get_textpage_ocr(**kwargs)
                return page.get_text(textpage=tp)
            except RuntimeError:
                continue
        return ""
    finally:
        doc.close()


def _ocr_image(image_path: Path) -> str:
    """OCR a standalone image file via pytesseract."""
    img = Image.open(image_path)
    return pytesseract.image_to_string(img)


def _get_text(file_path: Path) -> tuple[str, bool]:
    """
    Extract full text from a PDF or image file.

    Returns:
        (text, ocr_used): combined text from all pages, and whether OCR was invoked.

    Extraction order per page:
      1. PyMuPDF (fitz)
      2. pdfplumber fallback (if fitz page < _MIN_TEXT_CHARS)
      3. PyMuPDF Tesseract OCR (if still < _MIN_TEXT_CHARS and Tesseract installed)
      4. pytesseract + pdf2image legacy path (if above unavailable)
    """
    suffix = file_path.suffix.lower()

    # Image files: OCR directly
    if suffix in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
        if LEGACY_OCR_AVAILABLE:
            return _ocr_image(file_path), True
        return "", False

    # PDF: try extractors in order
    ocr_used = False

    if PYMUPDF_AVAILABLE:
        _, fitz_pages = _extract_text_fitz(file_path)
        _, plumber_pages = _extract_pdfplumber_safe(file_path)

        result_pages = []
        for i, fitz_text in enumerate(fitz_pages):
            if len(fitz_text.strip()) >= _MIN_TEXT_CHARS:
                result_pages.append(fitz_text)
                continue

            # fitz got too little — try pdfplumber
            plumb_text = plumber_pages[i] if i < len(plumber_pages) else ""
            if len(plumb_text.strip()) >= _MIN_TEXT_CHARS:
                result_pages.append(plumb_text)
                continue

            # Both text extractors failed — attempt OCR
            ocr_text = _ocr_page_fitz(file_path, i)
            if ocr_text.strip():
                result_pages.append(ocr_text)
                ocr_used = True
            elif LEGACY_OCR_AVAILABLE:
                try:
                    images = convert_from_path(str(file_path), dpi=300)
                    if i < len(images):
                        result_pages.append(pytesseract.image_to_string(images[i]))
                        ocr_used = True
                    else:
                        result_pages.append("")
                except Exception:
                    result_pages.append("")
            else:
                result_pages.append("")

        return "\n".join(result_pages), ocr_used

    # PyMuPDF not available — pdfplumber with optional legacy OCR
    full_text, pages = _extract_pdfplumber_safe(file_path)
    if LEGACY_OCR_AVAILABLE:
        try:
            images = convert_from_path(str(file_path), dpi=300)
            merged = []
            for i, page_text in enumerate(pages):
                if len(page_text.strip()) < _MIN_TEXT_CHARS and i < len(images):
                    merged.append(pytesseract.image_to_string(images[i]))
                    ocr_used = True
                else:
                    merged.append(page_text)
            return "\n".join(merged), ocr_used
        except Exception:
            pass

    return full_text, ocr_used


def _match_field(field: str, text: str) -> tuple[str | None, float]:
    """Try each pattern for a field; return (value, confidence).

    Uses finditer so that if a pattern matches multiple times, each occurrence
    is tried before falling through to the next pattern. This handles OCR noise
    where an invalid value appears before the real one (e.g. garbled date).
    """
    for pattern, flags in PATTERNS[field]:
        for m in re.finditer(pattern, text, flags):
            raw = m.group(1).strip()
            if field in DATE_FIELDS:
                try:
                    return _to_iso(raw), 1.0
                except ValueError:
                    continue
            elif field in DECIMAL_FIELDS:
                try:
                    return float(raw), 1.0
                except ValueError:
                    continue
            else:
                return raw, 1.0
    return None, 0.0


def parse_contract(file_path: Path) -> dict:
    """
    Parse a MOHRE contract PDF or image and return extracted fields.

    Returns:
        {
            "fields":       { field_name: value | None, ... },
            "field_scores": { field_name: 0.0 | 1.0, ... },
            "confidence":   float,   # min score across required fields
            "ocr_used":     bool,
        }
    """
    text, ocr_used = _get_text(file_path)

    fields: dict = {}
    scores: dict = {}

    for field in PATTERNS:
        value, score = _match_field(field, text)
        fields[field] = value
        scores[field] = score

    # insurance_status not in contract PDF — populated by benefits doc (Sprint 3)
    fields["insurance_status"] = None
    scores["insurance_status"] = 1.0

    required = [k for k in scores if k != "insurance_status"]
    confidence = min(scores[k] for k in required)

    return {
        "fields": fields,
        "field_scores": scores,
        "confidence": confidence,
        "ocr_used": ocr_used,
    }
