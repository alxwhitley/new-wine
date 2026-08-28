#!/usr/bin/env python3
"""CLI wrapper for the search-analytics gap-text retention purge.

Runs ONE purge pass and exits -- no polling loop, matching
scripts/search_analytics_finalizer.py's shape and the same rollout
decision the design spec left to Alex (item 7 of its rollout checklist:
"decide the retention-purge job's own schedule"). Alex's 2026-08-28
decision (Packet 2 of the back-to-back completion queue): run this once
daily. Safe to invoke repeatedly -- purge_expired_gap_text() is
idempotent, its WHERE clause excludes rows whose text is already NULL.

Usage:
  python3.12 scripts/search_analytics_retention.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "backend" / "app" / ".env")

from app.db.supabase import get_supabase  # noqa: E402
from app.services.search_analytics.retention import purge_expired_gap_text  # noqa: E402


def main() -> int:
    supabase = get_supabase()
    purged_count = purge_expired_gap_text(supabase)
    print({"purged": purged_count})
    return 0


if __name__ == "__main__":
    sys.exit(main())
