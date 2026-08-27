#!/usr/bin/env python3
"""CLI wrapper for the search-analytics classification finalizer.

Runs ONE finalization pass and exits (no polling loop in this session --
Assumption 5 in the design spec: whether this becomes a long-running
Railway service or a scheduled job is Alex's rollout decision). Safe to
invoke repeatedly (e.g. via cron) -- each pass only claims currently-
pending, currently-done work.

Usage:
  python3.12 scripts/search_analytics_finalizer.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "backend" / "app" / ".env")

from app.services.async_answers.db import Db  # noqa: E402
from app.services.search_analytics.finalizer import run_finalizer_once  # noqa: E402


def main() -> int:
    db = Db()
    try:
        counts = run_finalizer_once(db)
    finally:
        db.close()
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
