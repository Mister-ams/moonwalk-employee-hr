"""
Contract PDF / image parser for UAE MOHRE standard employment contracts.

Extraction pipeline (two stages):

Stage 1 — Text extraction (per page, tried in order):
  1. PyMuPDF (fitz) — cleaner Arabic/English separation; primary extractor
  2. pdfplumber — fallback for pages where fitz yields too little text
  3. PyMuPDF OCR via Tesseract — for scanned pages (requires Tesseract installed)
  4. pytesseract + pdf2image — legacy OCR path for images and PDF pages

Stage 2 — Field parsing (per field, tried in order):
  1. Regex patterns — score 1.0 on match
  2. OpenAI GPT-4o-mini fallback — score 0.85 for any field that regex missed
  3. Human review — score 0.0 fields flagged in needs_review output

Records are ALWAYS stored regardless of confidence. Per-field scores surface
in the portal so HR can review and correct partial extractions.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

try:
    import openai

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False

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

from config import OPENAI_API_KEY

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
        # Standard MOHRE: "starting from 16/07/2025"
        (r"starting from\s+(\d{2}/\d{2}/\d{4})", _S),
        # "commencing on/from DD/MM/YYYY"
        (r"commenc(?:ing|es?)\s+(?:on|from)\s+(\d{2}/\d{2}/\d{4})", _S),
        # "effective from/on DD/MM/YYYY"
        (r"effective\s+(?:from|on|date)\s+(\d{2}/\d{2}/\d{4})", _S),
        # "from DD/MM/YYYY to/until/and ending"
        (r"from\s+(\d{2}/\d{2}/\d{4})\s+(?:to|until|and\s+ending)", _S),
        # Table layout: "Start Date: DD/MM/YYYY" or "Start Date\nDD/MM/YYYY"
        (r"Start\s*Date[\s:]+(\d{2}/\d{2}/\d{4})", _S),
        # "term ... from DD/MM/YYYY" (DOTALL — Arabic text may sit between)
        (r"term\b.{0,80}?\bfrom\s+(\d{2}/\d{2}/\d{4})", _SD),
    ],
    "contract_expiry_date": [
        # Standard MOHRE: "ending on DD/MM/YYYY" ([^\d]* absorbs Arabic between label and date)
        (r"ending on[^\d]*(\d{2}/\d{2}/\d{4})", _S),
        # "expiring/expires on/at DD/MM/YYYY"
        (r"expir(?:ing|es?|y\s*date)\s*(?:on|at|from|:)?\s*(\d{2}/\d{2}/\d{4})", _S),
        # "until/up to/through/till DD/MM/YYYY"
        (r"(?:until|up\s+to|through|till)\s+(\d{2}/\d{2}/\d{4})", _S),
        # "from DD/MM/YYYY to/until DD/MM/YYYY" — capture the second date
        (
            r"from\s+\d{2}/\d{2}/\d{4}\s+(?:to|until|and\s+ending\s+on)\s+(\d{2}/\d{2}/\d{4})",
            _S,
        ),
        # Table layout: "End Date: DD/MM/YYYY" or "Ending Date\nDD/MM/YYYY"
        (r"End(?:ing)?\s*Date[\s:]+(\d{2}/\d{2}/\d{4})", _S),
        # "valid until/till DD/MM/YYYY"
        (r"valid\s+(?:until|till)\s+(\d{2}/\d{2}/\d{4})", _S),
        # "term ... ending DD/MM/YYYY" (DOTALL)
        (r"term\b.{0,80}?\bending\s+(?:on\s+)?(\d{2}/\d{2}/\d{4})", _SD),
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


# --- Document type detection ---


def _detect_doc_type(text: str) -> str:
    """Return 'employment_contract', 'job_offer', or 'unknown'."""
    if re.search(r"EMPLOYMENT CONTRACT", text, re.IGNORECASE):
        return "employment_contract"
    if re.search(r"JOB OFFER", text, re.IGNORECASE):
        return "job_offer"
    return "unknown"


# Job offer: signing date from "Corresponding to = DD/MM/YYYY" (OCR may merge the words)
_JO_SIGNING_DATE_PATTERNS = [
    (r"Corresponding\s*to\s*[=:]?\s*(\d{2}/\d{2}/\d{4})", _S),
]

# Job offer: contract duration "for a period of 2 years" or "Two Year"
_JO_DURATION_PATTERNS = [
    (r"for\s+a\s+period\s+of\s+(\d+)\s+[Yy]ear", _S),
    (r"for\s+a\s+period\s+of\s+(one|two|three|four|five)\s+[Yy]ear", _S),
]
_YEAR_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _extract_job_offer_dates(text: str) -> tuple[str | None, str | None]:
    """
    Derive start and expiry from job offer format.
    Start  = signing date ("Corresponding to = DD/MM/YYYY")
    Expiry = start + contract duration years
    Scores as 0.85 — derived/computed, needs spot-check.
    """
    start_iso = None
    for pattern, flags in _JO_SIGNING_DATE_PATTERNS:
        m = re.search(pattern, text, flags)
        if m:
            try:
                start_iso = _to_iso(m.group(1))
                break
            except ValueError:
                continue

    if not start_iso:
        return None, None

    years = None
    for pattern, flags in _JO_DURATION_PATTERNS:
        m = re.search(pattern, text, flags)
        if m:
            raw = m.group(1).lower()
            years = _YEAR_WORDS.get(raw) or (int(raw) if raw.isdigit() else None)
            if years:
                break

    if not years:
        return start_iso, None

    start_dt = datetime.strptime(start_iso, "%Y-%m-%d")
    try:
        expiry_dt = start_dt.replace(year=start_dt.year + years)
    except ValueError:  # Feb 29 on non-leap year
        expiry_dt = start_dt.replace(year=start_dt.year + years, day=28)

    return start_iso, expiry_dt.strftime("%Y-%m-%d")


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
            except Exception:
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


_LLM_FIELD_DEFS = {
    "full_name": "Employee's full name (Second Party / employee, not the employer)",
    "nationality": "Employee's nationality (e.g. UGANDAN, PAKISTANI, SUDANESE)",
    "date_of_birth": "Employee's date of birth in DD/MM/YYYY format",
    "passport_number": "Employee's passport number (alphanumeric, starts with a letter)",
    "job_title": "Employee's job title or profession",
    "base_salary": "Basic/base salary in AED — return a number only, no currency symbol",
    "total_salary": "Total monthly salary in AED — return a number only, no currency symbol",
    "contract_start_date": "Date the employment contract starts or commences, in DD/MM/YYYY format",
    "contract_expiry_date": "Date the employment contract ends or expires, in DD/MM/YYYY format",
    "mohre_transaction_no": "MOHRE or Ministry transaction/reference number (alphanumeric code)",
}


def _llm_extract_fields(
    text: str, missing_fields: list[str]
) -> dict[str, tuple[str | None, float]]:
    """
    OpenAI GPT-4o-mini fallback for fields that regex missed.
    Called once per document with all 0.0-scored fields batched into a single request.
    Returns {field: (value, score)} where score=0.85 for LLM extractions.
    Returns {} silently if OpenAI is unavailable or the API call fails.
    """
    if not _OPENAI_AVAILABLE or not OPENAI_API_KEY or not missing_fields:
        return {}

    fields_to_extract = "\n".join(
        f"- {f}: {_LLM_FIELD_DEFS[f]}" for f in missing_fields if f in _LLM_FIELD_DEFS
    )
    if not fields_to_extract:
        return {}

    prompt = (
        "Extract the following fields from this UAE MOHRE employment contract text.\n"
        "Return a JSON object with exactly these keys. Use null for any field not found.\n"
        "For dates use DD/MM/YYYY format. For salaries return numbers only.\n\n"
        f"Fields to extract:\n{fields_to_extract}\n\n"
        f"Contract text:\n{text[:4000]}"
    )

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = json.loads(response.choices[0].message.content)
    except Exception:
        return {}

    results: dict[str, tuple[str | None, float]] = {}
    for field in missing_fields:
        val = raw.get(field)
        if val is None:
            results[field] = (None, 0.0)
            continue
        if field in DATE_FIELDS:
            try:
                results[field] = (_to_iso(str(val)), 0.85)
            except ValueError:
                results[field] = (None, 0.0)
        elif field in DECIMAL_FIELDS:
            try:
                results[field] = (float(val), 0.85)
            except (ValueError, TypeError):
                results[field] = (None, 0.0)
        else:
            results[field] = (str(val).strip(), 0.85)

    return results


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

    # Detect document type before LLM fallback
    doc_type = _detect_doc_type(text)

    # Job offer: derive dates from signing date + duration BEFORE calling the LLM.
    # The LLM tends to return the signing date as the expiry — deriving avoids that.
    if doc_type == "job_offer":
        jo_start, jo_expiry = _extract_job_offer_dates(text)
        if jo_start and scores["contract_start_date"] == 0.0:
            fields["contract_start_date"] = jo_start
            scores["contract_start_date"] = 0.85
        if jo_expiry and scores["contract_expiry_date"] == 0.0:
            fields["contract_expiry_date"] = jo_expiry
            scores["contract_expiry_date"] = 0.85

    # LLM fallback — batch all remaining 0.0-scored fields into one API call
    missing = [f for f in PATTERNS if scores[f] == 0.0]
    if missing:
        for field, (value, score) in _llm_extract_fields(text, missing).items():
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
        "doc_type": doc_type,
    }
