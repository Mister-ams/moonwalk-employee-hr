"""Centralised configuration for the Employee HR service."""

import os
from pathlib import Path

# Postgres connection URL — Railway injects this automatically via the
# ${{Postgres.DATABASE_URL}} reference variable set on the service.
# For local dev, set DATABASE_URL in .env (see .env.example).
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Legacy SQLite path — kept for local CLI fallback when DATABASE_URL is not set.
_default_db = Path(__file__).parent / "employees.db"
DB_PATH = Path(os.environ.get("HR_DB_PATH", str(_default_db)))

# API key — must be set in production; empty string = reject all requests.
API_KEY = os.environ.get("HR_API_KEY", "")

# OpenAI API key — used by the LLM fallback in parse_contract.py.
# If unset, LLM fallback is skipped and missed fields go straight to human review.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Confidence threshold for flagging fields as needing human review (display only — no records rejected).
CONFIDENCE_THRESHOLD = 0.95

# Days-until-expiry below which the expiry_flag column is True in CSV export.
EXPIRY_WARNING_DAYS = 30
