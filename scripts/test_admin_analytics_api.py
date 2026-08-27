#!/usr/bin/env python3
"""Router-level tests for /admin/analytics/*. Calls route functions
directly with explicit kwargs -- no live server, no real database.

Run: python3.12 scripts/test_admin_analytics_api.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

import asyncio  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from app.routers import admin_analytics  # noqa: E402
from app.services.search_analytics import aggregation, gaps as gaps_module  # noqa: E402

_pass = 0
_fail = 0


def check(label: str, condition: bool, detail: str = None) -> None:
    global _pass, _fail
    print("  [%s] %s" % ("PASS" if condition else "FAIL", label))
    if detail:
        print("         %s" % detail)
    if condition:
        _pass += 1
    else:
        _fail += 1


def main() -> int:
    with patch.object(admin_analytics, "get_supabase", return_value=object()), \
         patch.object(aggregation, "get_summary", return_value={"monitored_searches": 10}), \
         patch.object(aggregation, "get_topic_bars", return_value=[{"topic": "Deliverance Ministry", "total": 5, "no_material": 2}]):
        result = asyncio.run(admin_analytics.get_summary_route(days=30, admin_id="admin-1"))
        check("summary route returns aggregation output", result["summary"]["monitored_searches"] == 10)
        check("summary route includes the ranked topic bars", result["topics"][0]["topic"] == "Deliverance Ministry")

    with patch.object(admin_analytics, "get_supabase", return_value=object()), \
         patch.object(gaps_module, "list_gaps_for_topic", return_value={"gaps": [], "next_cursor": None}):
        result = asyncio.run(admin_analytics.list_gaps_route(topic_key="Deliverance Ministry", cursor=None, admin_id="admin-1"))
        check("gaps list route returns the paginated shape", "next_cursor" in result)

    with patch.object(admin_analytics, "get_supabase", return_value=object()), \
         patch.object(admin_analytics, "Db") as mock_db_cls, \
         patch.object(admin_analytics, "current_policy", return_value={"evidence_version": "e1", "prompt_version": "p1", "policy_version": "policy_v3"}), \
         patch.object(gaps_module, "create_retest", return_value={"job_id": "job-1", "occurrence_id": "occ-1"}):
        result = asyncio.run(admin_analytics.create_retest_route(gap_id="gap-1", admin_id="admin-1"))
        check("retest route returns the new job/occurrence ids", result["job_id"] == "job-1")

    with patch.object(admin_analytics, "get_supabase", return_value=object()), \
         patch.object(gaps_module, "resolve_gap", return_value={"status": "resolved", "resolved_at": "2026-08-27T00:00:00Z", "text_purge_at": "2026-09-26T00:00:00Z"}):
        result = asyncio.run(admin_analytics.resolve_gap_route(gap_id="gap-1", admin_id="admin-1"))
        check("resolve route returns resolved status on success", result["status"] == "resolved")

    with patch.object(admin_analytics, "get_supabase", return_value=object()), \
         patch.object(gaps_module, "resolve_gap", side_effect=gaps_module.GapNotRetestedError("not retested")):
        raised_400 = False
        try:
            asyncio.run(admin_analytics.resolve_gap_route(gap_id="gap-2", admin_id="admin-1"))
        except HTTPException as exc:
            raised_400 = exc.status_code == 400
        check("resolving a gap with no successful retest is rejected with 400, not silently resolved",
              raised_400)

    print("\n%d passed, %d failed" % (_pass, _fail))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
