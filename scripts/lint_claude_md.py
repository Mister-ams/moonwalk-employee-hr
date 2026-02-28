#!/usr/bin/env python3
"""Fail CI if CLAUDE.md exceeds the tier size limit (200 lines for project tier)."""

import sys
from pathlib import Path

TIER_LIMITS = {
    "CLAUDE.md": 200,  # project tier
}

failed = False
for fname, limit in TIER_LIMITS.items():
    p = Path(fname)
    if p.exists():
        lines = len(p.read_text(encoding="utf-8").splitlines())
        if lines > limit:
            print(f"ERROR: {fname} is {lines} lines (limit: {limit})")
            failed = True
        else:
            print(f"OK: {fname} is {lines}/{limit} lines")
    else:
        print(f"SKIP: {fname} not found")

sys.exit(1 if failed else 0)
