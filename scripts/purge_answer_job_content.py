#!/usr/bin/env python3
"""CLI wrapper for the answer_jobs content-retention purge.

Runs ONE purge pass and exits -- no polling loop, matching
scripts/search_analytics_retention.py's shape. Alex's 2026-08-28 decision
(Packet 4, Task 4.4 of the back-to-back completion queue): answer_jobs'
question/answer/messages content is purged after 90 days
(backend/app/services/answer_job_retention.py::RETENTION_DAYS); numeric/
instrumentation columns are untouched. Safe to invoke repeatedly --
purge_expired_answer_job_content() is idempotent, its WHERE clause excludes
rows already purged.

Usage:
  python3.12 scripts/purge_answer_job_content.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT.parent / "backend" / "app" / ".env")

from app.db.supabase import get_supabase  # noqa: E402
from app.services.answer_job_retention import purge_expired_answer_job_content  # noqa: E402


def main() -> int:
    supabase = get_supabase()
    purged_count = purge_expired_answer_job_content(supabase)
    print({"purged": purged_count})
    return 0


if __name__ == "__main__":
    sys.exit(main())
