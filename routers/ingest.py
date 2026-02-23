"""PDF ingest endpoint — upload a contract PDF, parse and store it."""

import base64
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from auth import require_api_key
from db import upsert_employee
from parse_contract import parse_contract

router = APIRouter()

_REVIEW_ACTIONS = {
    0.0: "enter_manually",  # regex and LLM both missed — human must fill in
    0.85: "spot_check",  # LLM extracted — likely correct, verify before relying on it
}


def _build_needs_review(scores: dict) -> list[dict]:
    """Return fields that require human attention (score < 0.95, excluding insurance_status)."""
    return [
        {
            "field": field,
            "score": score,
            "action": _REVIEW_ACTIONS.get(score, "spot_check"),
        }
        for field, score in scores.items()
        if field != "insurance_status" and score < 0.95
    ]


def _parse_and_store(contents: bytes, filename: str) -> dict:
    """Write contents to a temp file, parse, and always upsert regardless of confidence."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        result = parse_contract(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    fields = result["fields"]
    scores = result["field_scores"]
    confidence = result["confidence"]
    doc_type = result["doc_type"]

    employee_id = upsert_employee(fields, filename, confidence, scores, doc_type)
    needs_review = _build_needs_review(scores)

    warning = None
    if doc_type == "job_offer":
        warning = (
            "Document is a Job Offer, not a signed Employment Contract. "
            "Contract dates are derived from signing date + duration. "
            "Upload the Employment Contract (MB-series) when available to confirm dates."
        )

    return {
        "employee_id": employee_id,
        "source_doc_type": doc_type,
        "warning": warning,
        "confidence": confidence,
        "needs_review": needs_review,
        **fields,
    }


@router.post("", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_contract(file: UploadFile, _: str = Depends(require_api_key)):
    """
    Upload a MOHRE contract PDF via multipart/form-data.
    Returns the stored employee record on success.
    Returns 422 if confidence is below the threshold, with per-field scores.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )
    contents = await file.read()
    return _parse_and_store(contents, file.filename)


class IngestBase64Request(BaseModel):
    filename: str
    data: str  # base64-encoded PDF bytes


@router.post("/base64", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_contract_base64(
    body: IngestBase64Request, _: str = Depends(require_api_key)
):
    """
    Upload a MOHRE contract PDF as a base64-encoded JSON body.
    Intended for Appsmith (which cannot reliably send multipart/form-data).
    Body: {"filename": "contract.pdf", "data": "<base64>"}
    """
    if not body.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )
    try:
        # Appsmith sends files as data URLs: "data:application/pdf;base64,<data>"
        raw = body.data.split(",", 1)[-1] if "," in body.data else body.data
        contents = base64.b64decode(raw)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 data",
        )
    return _parse_and_store(contents, body.filename)
