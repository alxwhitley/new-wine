#!/usr/bin/env python3
"""
remediate_fabricated_propositions_2026-08-04.py -- one-off, narrowly-scoped
remediation for the two ID-confirmed fabricated propositions found by the
position-layer design pressure test. See docs/audits/
position_layer_revival_diagnostic_2026-08-04.md, "Fabricated-proposition
remediation" section, for the full diagnostic this executes.

Scope, approved by Alex -- do not extend beyond this without a new decision:
  1. Mark 0892b75d-1c9f-4a65-a47e-768c1c5c1803 (Ravenhill / Philippians 4:8-9,
     a real citation grafted onto the wrong claim in the same sermon) and
     18783354-931f-4244-bfe3-f47ce185b3ba (Carter Conlon / Matthew 7:21-23,
     same defect shape) eligible=false. Both are CLAUDE.md-documented,
     ID-confirmed fabrication cases.
  2. Do NOT touch 23d846db-66de-4cc6-8308-138877fd3772 (the Savchuk "Devil's
     Voice" candidate) -- a strong content match but never ID-confirmed
     against an original finding. Alex has not ruled on it.
  3. Do NOT rewrite content -- eligibility flip only. Alex has not ruled on
     rewriting.
  4. Rebuild the "holiness and personal purity" corpus position via the
     EXISTING, already-tested scripts.serve_position.rebuild_position() --
     no new machinery. This is the only one of the three propositions
     actually consumed as position evidence (confirmed in the diagnostic).
  5. Whatever rebuild_position() already does to the superseded version by
     default (is_current=false, status left as-is) is what happens here --
     no retraction mechanism invented.

Not idempotent for the rebuild step: re-running this script after a
successful execution would call rebuild_position() again and write an
unnecessary v3 (rebuild_position() always writes a new version when
called; it does not check whether evidence actually changed since the
last version -- that lookup-or-generate behavior belongs to
serve_position(), not rebuild_position()). Run once, deliberately.

Procedure (all stages run in one execution, printed in order):
  1. Read-only confirmation of current state.
  2. Dry-run the eligibility UPDATE inside a transaction that is rolled
     back, proving it affects exactly the right 2 rows before anything
     commits.
  3. Real eligibility UPDATE, committed.
  4. Preview the rebuild's evidence set (gather_evidence_corpus(), a
     read-only call -- the same one rebuild_position() runs internally)
     against the now-corrected eligible set, before triggering the one
     real (LLM-calling, persisting) rebuild.
  5. The real rebuild_position() call.
  6. Post-write verification.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "backend" / "app" / ".env")

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

import positions as pos  # noqa: E402
import serve_position as sp  # noqa: E402
import eligible_statements as es  # noqa: E402

RAVENHILL_ID = "0892b75d-1c9f-4a65-a47e-768c1c5c1803"
CONLON_ID = "18783354-931f-4244-bfe3-f47ce185b3ba"
SAVCHUK_UNTOUCHED_ID = "23d846db-66de-4cc6-8308-138877fd3772"  # sanity-check only, never written
TARGET_IDS = [RAVENHILL_ID, CONLON_ID]
CORPUS_TOPIC = "holiness and personal purity"


def _fetchall(cur):
    return [dict(r) for r in cur.fetchall()]


def stage1_readonly_confirm(params):
    print("=" * 100)
    print("STAGE 1 -- read-only confirmation of current state")
    print("=" * 100)
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT id::text, eligible, prompt_version FROM propositions WHERE id::text = ANY(%s)",
        (TARGET_IDS + [SAVCHUK_UNTOUCHED_ID],),
    )
    rows = _fetchall(cur)
    for r in rows:
        print(f"  proposition {r['id']}: eligible={r['eligible']} prompt_version={r['prompt_version']}")
    assert len(rows) == 3, f"expected 3 rows, found {len(rows)}"
    by_id = {r["id"]: r for r in rows}
    assert by_id[RAVENHILL_ID]["eligible"] is True, "Ravenhill row not eligible=true as expected pre-write"
    assert by_id[CONLON_ID]["eligible"] is True, "Conlon row not eligible=true as expected pre-write"
    assert by_id[SAVCHUK_UNTOUCHED_ID]["eligible"] is True, "Savchuk sanity row unexpectedly not eligible=true"

    cur.execute("SELECT count(*) AS c FROM propositions WHERE eligible = true")
    total_eligible_before = cur.fetchone()["c"]
    print(f"  total eligible=true propositions corpus-wide (before): {total_eligible_before}")

    cur.execute(
        """
        SELECT id::text, topic, kind, status, is_current, version, lineage_id::text, supersedes_id::text
        FROM positions WHERE topic = %s
        ORDER BY version
        """,
        (CORPUS_TOPIC,),
    )
    position_rows_before = _fetchall(cur)
    print(f"  positions rows for topic {CORPUS_TOPIC!r} (before): {len(position_rows_before)}")
    for r in position_rows_before:
        print(f"    {r}")
    assert len(position_rows_before) == 1, "expected exactly one existing version before rebuild"
    current_position_id = position_rows_before[0]["id"]

    cur.execute(
        "SELECT proposition_id::text FROM position_evidence WHERE position_id = %s ORDER BY proposition_id",
        (current_position_id,),
    )
    evidence_before = [r["proposition_id"] for r in _fetchall(cur)]
    print(f"  position_evidence for current version ({len(evidence_before)} rows): {evidence_before}")
    assert RAVENHILL_ID in evidence_before, "expected Ravenhill proposition in current evidence set"

    cur.execute("SELECT count(*) AS c FROM positions")
    total_positions_before = cur.fetchone()["c"]
    print(f"  total positions rows corpus-wide (before): {total_positions_before}")

    cur.close()
    conn.close()
    return {
        "total_eligible_before": total_eligible_before,
        "current_position_id": current_position_id,
        "position_rows_before": position_rows_before,
        "total_positions_before": total_positions_before,
    }


def stage2_dry_run_eligibility_flip(params):
    print()
    print("=" * 100)
    print("STAGE 2 -- dry-run the eligibility UPDATE (transaction rolled back, nothing committed)")
    print("=" * 100)
    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        "UPDATE propositions SET eligible = false WHERE id::text = ANY(%s) AND eligible = true",
        (TARGET_IDS,),
    )
    print(f"  dry-run UPDATE would affect {cur.rowcount} row(s) (expected 2)")
    assert cur.rowcount == 2, f"dry-run affected {cur.rowcount} rows, expected exactly 2"
    conn.rollback()
    print("  rolled back -- no change committed")
    cur.close()
    conn.close()


def stage3_real_eligibility_flip(params):
    print()
    print("=" * 100)
    print("STAGE 3 -- real eligibility UPDATE (committed)")
    print("=" * 100)
    conn = psycopg2.connect(**params)
    conn.autocommit = False
    cur = conn.cursor()
    cur.execute(
        "UPDATE propositions SET eligible = false WHERE id::text = ANY(%s) AND eligible = true",
        (TARGET_IDS,),
    )
    rowcount = cur.rowcount
    print(f"  UPDATE affected {rowcount} row(s) (expected 2)")
    assert rowcount == 2, f"real UPDATE affected {rowcount} rows, expected exactly 2 -- rolling back"
    conn.commit()
    print("  committed")
    cur.close()
    conn.close()


def stage4_preview_rebuild_evidence(params):
    print()
    print("=" * 100)
    print("STAGE 4 -- preview the rebuild's evidence set (read-only gather_evidence_corpus call)")
    print("=" * 100)
    eligible_ids = es.load_eligible_ids(params)
    print(f"  materialized eligible set size (after flip): {len(eligible_ids)}")
    assert RAVENHILL_ID not in eligible_ids, "Ravenhill proposition still in eligible set after flip"
    assert CONLON_ID not in eligible_ids, "Conlon proposition still in eligible set after flip"
    assert SAVCHUK_UNTOUCHED_ID in eligible_ids, "Savchuk proposition unexpectedly removed from eligible set"

    evidence = pos.gather_evidence_corpus(params, CORPUS_TOPIC, eligible_ids)
    ids = [e["id"] for e in evidence]
    print(f"  gather_evidence_corpus({CORPUS_TOPIC!r}) would now return {len(ids)} propositions:")
    for e in evidence:
        print(f"    [{e['teacher']}] sim={e['similarity']:.3f} {e['id']}")
    assert RAVENHILL_ID not in ids, "Ravenhill proposition still surfaces in fresh evidence gather"
    return eligible_ids


def stage5_real_rebuild(params, eligible_ids):
    print()
    print("=" * 100)
    print("STAGE 5 -- real rebuild_position() call (the one write that persists)")
    print("=" * 100)
    result = sp.rebuild_position(params, CORPUS_TOPIC, eligible_ids, requested_teacher=None)
    print(f"  rebuild_position() result:")
    for k, v in result.items():
        print(f"    {k}: {v}")
    assert result.get("status") == "served", f"unexpected rebuild status: {result.get('status')}"
    return result


def stage6_verify(params, before):
    print()
    print("=" * 100)
    print("STAGE 6 -- post-write verification")
    print("=" * 100)
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT id::text, eligible FROM propositions WHERE id::text = ANY(%s)",
        (TARGET_IDS + [SAVCHUK_UNTOUCHED_ID],),
    )
    by_id = {r["id"]: r["eligible"] for r in _fetchall(cur)}
    print(f"  Ravenhill eligible now: {by_id[RAVENHILL_ID]} (expected False)")
    print(f"  Conlon eligible now: {by_id[CONLON_ID]} (expected False)")
    print(f"  Savchuk (untouched) eligible now: {by_id[SAVCHUK_UNTOUCHED_ID]} (expected True, unchanged)")
    assert by_id[RAVENHILL_ID] is False
    assert by_id[CONLON_ID] is False
    assert by_id[SAVCHUK_UNTOUCHED_ID] is True

    cur.execute("SELECT count(*) AS c FROM propositions WHERE eligible = true")
    total_eligible_after = cur.fetchone()["c"]
    delta = before["total_eligible_before"] - total_eligible_after
    print(f"  total eligible=true propositions (after): {total_eligible_after} (delta: -{delta}, expected -2)")
    assert delta == 2, f"expected eligible-count delta of exactly 2, got {delta}"

    cur.execute(
        """
        SELECT id::text, topic, kind, status, is_current, version, lineage_id::text, supersedes_id::text, content
        FROM positions WHERE topic = %s
        ORDER BY version
        """,
        (CORPUS_TOPIC,),
    )
    position_rows_after = _fetchall(cur)
    print(f"  positions rows for topic {CORPUS_TOPIC!r} (after): {len(position_rows_after)} (expected 2)")
    assert len(position_rows_after) == 2, f"expected exactly 2 versions after rebuild, found {len(position_rows_after)}"

    v1 = next(r for r in position_rows_after if r["version"] == 1)
    v2 = next(r for r in position_rows_after if r["version"] == 2)

    v1_before = before["position_rows_before"][0]
    print(f"  v1 (superseded): id={v1['id']} is_current={v1['is_current']} status={v1['status']!r} "
          f"kind={v1['kind']}")
    assert v1["id"] == v1_before["id"], "v1 row identity changed -- should be untouched"
    assert v1["is_current"] is False, "v1 should now be is_current=false"
    assert v1["status"] == v1_before["status"], (
        f"v1 status changed from {v1_before['status']!r} to {v1['status']!r} -- "
        "rebuild_position() should leave status as-is (no retraction mechanism invented)"
    )
    assert v1["lineage_id"] == v1_before["lineage_id"]

    print(f"  v2 (current): id={v2['id']} is_current={v2['is_current']} status={v2['status']!r} "
          f"kind={v2['kind']} supersedes_id={v2['supersedes_id']}")
    assert v2["is_current"] is True
    assert v2["supersedes_id"] == v1["id"]
    assert v2["lineage_id"] == v1["lineage_id"]

    cur.execute(
        "SELECT proposition_id::text FROM position_evidence WHERE position_id = %s ORDER BY proposition_id",
        (v2["id"],),
    )
    evidence_after = [r["proposition_id"] for r in _fetchall(cur)]
    print(f"  v2 position_evidence ({len(evidence_after)} rows): {evidence_after}")
    assert RAVENHILL_ID not in evidence_after, "v2 still references the Ravenhill fabrication proposition"
    assert CONLON_ID not in evidence_after, "v2 unexpectedly references the Conlon proposition (was never in v1 either)"

    cur.execute(
        "SELECT proposition_id::text FROM position_evidence WHERE position_id = %s ORDER BY proposition_id",
        (v1["id"],),
    )
    evidence_v1_unchanged = [r["proposition_id"] for r in _fetchall(cur)]
    print(f"  v1 position_evidence unchanged, still {len(evidence_v1_unchanged)} rows (historical record preserved)")
    assert RAVENHILL_ID in evidence_v1_unchanged, "v1's historical evidence set should NOT be altered"

    cur.execute("SELECT count(*) AS c FROM positions")
    total_positions_after = cur.fetchone()["c"]
    print(f"  total positions rows corpus-wide (after): {total_positions_after} "
          f"(expected {before['total_positions_before'] + 1})")
    assert total_positions_after == before["total_positions_before"] + 1

    print()
    print("  v2 content:")
    print("  " + "-" * 96)
    for line in v2["content"].splitlines():
        print(f"  {line}")
    print("  " + "-" * 96)

    cur.close()
    conn.close()
    print()
    print("ALL VERIFICATION CHECKS PASSED.")


def main():
    params = pos.db_params()
    before = stage1_readonly_confirm(params)
    stage2_dry_run_eligibility_flip(params)
    stage3_real_eligibility_flip(params)
    eligible_ids = stage4_preview_rebuild_evidence(params)
    stage5_real_rebuild(params, eligible_ids)
    stage6_verify(params, before)


if __name__ == "__main__":
    main()
