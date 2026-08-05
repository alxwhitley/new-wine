#!/usr/bin/env python3
"""
backfill_proposition_eligibility.py -- one-time batch backfill of
propositions.eligible (migration 080), reusing
eligible_statements.compute_eligible_proposition_ids() VERBATIM -- the same
per-proposition decision function the lazy EligibilityChecker uses, so the
materialized value can never diverge from what the live serving path would
decide if it recomputed (the fork hazard CLAUDE.md's Landmines warn about).

Read-only compute, then a single batched write pass. Dry-run by default
(Standing Session Rule #1/#2: read-only diagnostic before any write); pass
--apply to actually write. Ends with a hard reconciliation count (Standing
Session Rule #3), re-checked on a FRESH connection (migration 049 landmine).

REAL MEASURED COST (2026-08-04, corrected the prior "~15+ min" estimate,
which was never independently re-measured until this run): the whole-corpus
compute took 2h04m wall-clock against 11,139 propositions (8,284 eligible).
Every invocation of this script recomputes from scratch -- the computed set
is cached to CACHE_PATH immediately after computing (not just on --apply) so
a failed/retried write step never has to pay this cost twice. A cached file
is only ever read if you pass --use-cache explicitly; it is NOT trusted by
default, since it can go stale the same way the materialized column itself
can (see migration 080's disclosed staleness note) -- treat it as a recovery
mechanism for this run, not a substitute for a fresh compute on a later
re-backfill.

Usage:
  python3 scripts/backfill_proposition_eligibility.py                # dry run, computes + caches
  python3 scripts/backfill_proposition_eligibility.py --apply         # real write, computes + caches
  python3 scripts/backfill_proposition_eligibility.py --apply --use-cache  # write from the last cached compute, no recompute
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import eligible_statements as es  # noqa: E402
import positions as pos  # noqa: E402

BATCH_SIZE = 500
CACHE_PATH = Path(__file__).resolve().parent / "eligible_ids_cache.json"


def _total_propositions(params: dict) -> int:
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM propositions")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def _apply_eligible(params: dict, eligible_ids) -> int:
    """Batched UPDATE ... SET eligible = true WHERE id = ANY(batch). Returns
    the total rowcount across all batches -- checked by the caller against
    len(eligible_ids) and a fresh post-write SELECT."""
    import psycopg2

    ids = list(eligible_ids)
    updated = 0
    conn = psycopg2.connect(**params)
    conn.autocommit = False
    try:
        cur = conn.cursor()
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i : i + BATCH_SIZE]
            cur.execute(
                "UPDATE propositions SET eligible = true WHERE id = ANY(%s::uuid[])",
                (batch,),
            )
            updated += cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually write eligible=true for the computed set. Default is dry-run (compute + report only).",
    )
    parser.add_argument(
        "--use-cache", action="store_true",
        help="Skip recomputing; load the eligible-ID set from CACHE_PATH (must exist from a prior run "
             "this same session -- not trusted across a code/corpus change).",
    )
    args = parser.parse_args()

    params = pos.db_params()
    total = _total_propositions(params)

    if args.use_cache:
        if not CACHE_PATH.exists():
            raise SystemExit(f"--use-cache given but {CACHE_PATH} does not exist -- run without it first.")
        cached = json.loads(CACHE_PATH.read_text())
        eligible_ids = set(cached["eligible_ids"])
        print(f"Loaded {len(eligible_ids)} eligible ID(s) from cache: {CACHE_PATH}")
        print(f"  (cached at total_propositions={cached['total_propositions']}; live total is now {total})")
    else:
        print("Computing pass-both eligibility (compute_eligible_proposition_ids, reused verbatim)...")
        eligible_ids = es.compute_eligible_proposition_ids(params, verbose=True)
        CACHE_PATH.write_text(json.dumps({
            "eligible_ids": sorted(eligible_ids),
            "total_propositions": total,
        }))
        print(f"Cached computed set to {CACHE_PATH} ({len(eligible_ids)} ids)")

    print(f"\nTotal propositions:   {total}")
    print(f"Eligible (pass both): {len(eligible_ids)}")
    print(f"Not eligible:         {total - len(eligible_ids)}")

    if not args.apply:
        print("\nDRY RUN -- no rows written. Re-run with --apply to write.")
        return

    print(f"\nApplying eligible=true to {len(eligible_ids)} row(s), batch size {BATCH_SIZE}...")
    updated = _apply_eligible(params, eligible_ids)

    # Hard reconciliation on a FRESH connection (migration 049 landmine: never
    # trust the write connection's own view of what it just wrote).
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM propositions WHERE eligible = true")
    live_true = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM propositions WHERE eligible = false")
    live_false = cur.fetchone()[0]
    cur.close()
    conn.close()

    print("\n" + "=" * 60)
    print("RECONCILIATION")
    print(f"  attempted (computed eligible set):  {len(eligible_ids)}")
    print(f"  UPDATE reported rowcount:            {updated}")
    print(f"  live eligible=true (fresh conn):     {live_true}")
    print(f"  live eligible=false (fresh conn):    {live_false}")
    print(f"  live total (fresh conn):             {live_true + live_false}")
    ok = (
        updated == len(eligible_ids)
        and live_true == len(eligible_ids)
        and live_true + live_false == total
    )
    print(f"  RECONCILED: {ok}")
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
