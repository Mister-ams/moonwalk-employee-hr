"""Centralised configuration for the Employee HR service."""

import os
from pathlib import Path

# Database path — override with HR_DB_PATH env var.
# On Railway, set HR_DB_PATH to a mounted volume path (e.g. /data/employees.db)
# to persist data across deploys. Without a volume the SQLite DB is ephemeral.
_default_db = Path(__file__).parent / "employees.db"
DB_PATH = Path(os.environ.get("HR_DB_PATH", str(_default_db)))

# API key — must be set in production; empty string = reject all requests.
API_KEY = os.environ.get("HR_API_KEY", "")

# Confidence threshold below which a parse is routed to the exception queue.
CONFIDENCE_THRESHOLD = 0.95

# Days-until-expiry below which the expiry_flag column is True in CSV export.
EXPIRY_WARNING_DAYS = 30
