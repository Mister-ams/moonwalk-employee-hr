"""Exception queue endpoint — employees with fields requiring human review."""

from fastapi import APIRouter

from auth import require_api_key
from db import fetch_exceptions

router = APIRouter()


@router.get("", tags=["exceptions"])
def list_exceptions(_: str = require_api_key):
    """
    Return employees where any field score is below 0.95.
    These are stored records with partial extractions that need human review.
    Scores: 1.0 = regex confirmed, 0.85 = LLM extracted (spot-check), 0.0 = not found (enter manually).
    """
    return fetch_exceptions()
