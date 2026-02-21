"""PDF ingest endpoint — upload a contract PDF, parse and store it."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from auth import require_api_key
from config import CONFIDENCE_THRESHOLD
from db import upsert_employee
from parse_contract import parse_contract

router = APIRouter()


@router.post("", status_code=status.HTTP_201_CREATED, tags=["ingest"])
async def ingest_contract(file: UploadFile, _: str = Depends(require_api_key)):
    """
    Upload a MOHRE contract PDF. Returns the stored employee record on success.
    Returns 422 if confidence is below the threshold, with per-field scores.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )

    contents = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = Path(tmp.name)

    try:
        result = parse_contract(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    confidence = result["confidence"]
    fields = result["fields"]
    scores = result["field_scores"]

    if confidence < CONFIDENCE_THRESHOLD:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Confidence below threshold — routed to exception queue",
                "confidence": confidence,
                "threshold": CONFIDENCE_THRESHOLD,
                "field_scores": scores,
            },
        )

    employee_id = upsert_employee(fields, file.filename, confidence)
    return {"employee_id": employee_id, "confidence": confidence, **fields}
