#!/usr/bin/env python3
"""
Proves is_source_servable() against two real, known-state sources:
one confirmed servable, one confirmed not servable (F.F. Bosworth —
unlicensed/hidden per CLAUDE.md's migration-050 decision entry).

Run from project root: python3 scripts/test_is_source_servable.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.source_resolver import is_source_servable, normalize_alias_key

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]


def main():
    db = create_client(SB_URL, SB_SVC)

    # Known NOT servable: the sentinel (unlicensed/hidden, always fails the gate).
    # Migration 049 established "Unassigned — needs source" as the sentinel with UUID
    # 267a09ac-76f3-43fb-901f-3015aef88e22, license_status='unlicensed', visibility='hidden'.
    sentinel_id = "267a09ac-76f3-43fb-901f-3015aef88e22"
    sentinel_row = db.table("sources").select("license_status, visibility, name").eq("id", sentinel_id).limit(1).execute()
    assert sentinel_row.data, "Expected sentinel source to exist"
    print(f"Sentinel source row: {sentinel_row.data}")
    assert is_source_servable(db, sentinel_id) is False, "Sentinel (unlicensed/hidden) should NOT be servable"
    print("PASS — Sentinel (unlicensed/hidden) correctly not servable")

    # Known servable: pick the first public_domain source live.
    pd_source = db.table("sources").select("id, name").eq("license_status", "public_domain").limit(1).execute()
    assert pd_source.data, "Expected at least one public_domain source live"
    pd_id = pd_source.data[0]["id"]
    print(f"Testing known-servable public_domain source: {pd_source.data[0]['name']}")
    assert is_source_servable(db, pd_id) is True, f"{pd_source.data[0]['name']} (public_domain) should be servable"
    print("PASS — public_domain source correctly servable")

    # Unknown source_id — should fail closed, not throw.
    assert is_source_servable(db, "00000000-0000-0000-0000-000000000000") is False
    print("PASS — nonexistent source_id correctly fails closed")

    print("\nALL PASSED")


if __name__ == "__main__":
    main()
