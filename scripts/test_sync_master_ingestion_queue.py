#!/usr/bin/env python3
"""Regression tests for sync_master_ingestion_queue.py.

No test file for this script existed before 2026-08-26 -- this is a new,
from-scratch synthetic-scenario test, not a rerun of a prior artifact (none
was found in the repo or its git history). It covers the two things that
matter for the 2026-08-26 xlsx -> TSV conversion:

  1. read_sheet() against a real TSV file (not the live production one --
     a throwaway temp file matching the Queue tab's exact schema), proving
     bool/int coercion and blank-handling still work when every raw value
     arrives as a string (never a native openpyxl bool/int) -- the actual
     behavior change this conversion introduces.
  2. build_plan()'s NOT-NULL-safe blank handling, which is unchanged code
     but is exactly the kind of thing that silently breaks if read_sheet()
     ever starts returning "" instead of None for a blank cell: a blank
     cell on a NOT NULL database column must be treated as "leave
     unchanged" on an overwrite, never as an explicit NULL write.

Makes zero database connections and zero writes to
docs/ingestion/master_ingestion_queue_queue.tsv.

Run: python3.12 scripts/test_sync_master_ingestion_queue.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingestion_sheet_io as sheet_io
import sync_master_ingestion_queue as sync

_checks = []
_failures = []


def check(label, condition):
    _checks.append(label)
    if not condition:
        _failures.append(label)
        print(f"FAIL: {label}")


# ---------------------------------------------------------------------------
# read_sheet() against a synthetic Queue-shaped TSV file.
# ---------------------------------------------------------------------------
_QUEUE_HEADERS = [sheet_field for sheet_field, _ in sync.WRITABLE_FIELDS] + ["stage", "name", "source_db_id", "origin"]

_tmpdir = Path(tempfile.mkdtemp())
_original_sheet_path = sync.SHEET_PATH
try:
    _tsv_path = _tmpdir / "queue.tsv"
    _rows = [
        {
            "stage": "ready_to_queue", "name": "New Row", "url": "https://new.example.com",
            "source_format": "web_page", "source_scope": "single", "attribute_to": "Someone",
            "attribution_mode": "declared", "on_unknown_author": None, "retain_original_text": True,
            "notes": None, "flag_reason": None, "cleared_to_run": False,
            "db_status": None, "db_execution_stage": None, "attempts": None, "max_attempts": None,
            "worker_id": None, "lease_expires_at": None, "run_after": None, "final_url": None,
            "content_sha256": None, "fetched_bytes": None, "attempted_documents": None,
            "stored_documents": None, "skipped_documents": None, "errored_documents": None,
            "result_document_id": None, "submitted_by": "abc-user-id",
            "source_db_id": None, "origin": "test",
        },
        {
            # Overwrite candidate: has a source_db_id, and BLANK cells on
            # several NOT NULL db columns (url, status, attempts, ...) --
            # this is the exact shape of the historical blank-cell bug:
            # a blank sheet cell must mean "leave the existing db value
            # alone", never "write NULL into a NOT NULL column".
            "stage": "already_queued", "name": "Existing Row", "url": None,
            "source_format": None, "source_scope": None, "attribute_to": "Changed Attribution",
            "attribution_mode": None, "on_unknown_author": None, "retain_original_text": None,
            "notes": None, "flag_reason": None, "cleared_to_run": None,
            "db_status": None, "db_execution_stage": None, "attempts": None, "max_attempts": None,
            "worker_id": None, "lease_expires_at": None, "run_after": None, "final_url": None,
            "content_sha256": None, "fetched_bytes": None, "attempted_documents": None,
            "stored_documents": None, "skipped_documents": None, "errored_documents": None,
            "result_document_id": None, "submitted_by": None,
            "source_db_id": "11111111-1111-1111-1111-111111111111", "origin": "test",
        },
    ]
    sheet_io.write_tab(_tsv_path, _QUEUE_HEADERS, _rows)

    sync.SHEET_PATH = _tsv_path
    problems: list = []
    parsed = sync.read_sheet(problems)

    check("read_sheet returns every row", len(parsed) == 2)
    check("read_sheet reports no problems on clean data", problems == [])

    new_row = next(r for r in parsed if r["name"] == "New Row")
    check("bool TRUE cell coerces to real Python True", new_row["retain_original_text"] is True)
    check("bool FALSE cell coerces to real Python False", new_row["cleared_to_run"] is False)
    check("blank non-bool/int field coerces to None, not ''", new_row["notes"] is None)
    check("plain string field passes through unchanged", new_row["url"] == "https://new.example.com")
    check("row carries a 1-based sheet-row label for error messages", new_row["_excel_row"] == 2)

    existing_row = next(r for r in parsed if r["name"] == "Existing Row")
    check("blank bool field coerces to None (unknown), not False", existing_row["retain_original_text"] is None)
    check("blank int field coerces to None", existing_row["attempts"] is None)

    # ------------------------------------------------------------------
    # build_plan(): the actual NOT-NULL-safe blank-handling guarantee.
    # ------------------------------------------------------------------
    db_rows = {
        "11111111-1111-1111-1111-111111111111": {
            "id": "11111111-1111-1111-1111-111111111111",
            "url": "https://existing.example.com",       # NOT NULL -- must survive a blank sheet cell
            "status": "queued",                            # NOT NULL -- must survive
            "attempts": 3,                                  # NOT NULL -- must survive
            "attribute_to": "Original Attribution",         # nullable -- sheet value should win
            "notes": "some prior note",                     # nullable -- blank sheet cell should clear it
        },
    }
    creates, overwrites, unchanged, orphans, blocked, stale_refs = sync.build_plan(
        parsed, db_rows, default_submitted_by="abc-user-id", problems=[]
    )

    check("exactly one create planned (New Row)", len(creates) == 1)
    check("exactly one overwrite planned (Existing Row)", len(overwrites) == 1)
    ov = overwrites[0]
    changed_fields = {f for f, _old, _new in ov["diffs"]}
    check("NOT NULL 'url' is NOT in the overwrite payload despite a blank sheet cell", "url" not in ov["payload"])
    check("NOT NULL 'status' is NOT in the overwrite payload despite a blank sheet cell", "status" not in ov["payload"])
    check("nullable 'attribute_to' DOES update from the sheet's non-blank value", ov["payload"].get("attribute_to") == "Changed Attribution")
    check("nullable 'notes' DOES get cleared to None from a blank sheet cell", "notes" in ov["payload"] and ov["payload"]["notes"] is None)

    create = creates[0]
    check("submitted_by required-for-create field is present", create["payload"].get("submitted_by") == "abc-user-id")
    check("create defaults retain_original_text to True per migration 088", create["payload"].get("retain_original_text") is True)
finally:
    sync.SHEET_PATH = _original_sheet_path
    shutil.rmtree(_tmpdir, ignore_errors=True)


print(f"\n{len(_checks) - len(_failures)}/{len(_checks)} checks passed")
if _failures:
    print("\nFAILED:")
    for f in _failures:
        print(f"  - {f}")
    raise SystemExit(1)
