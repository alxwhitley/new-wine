#!/usr/bin/env python3.12
"""
rebuild_positions_after_reingest_2026-09-04.py — one-off.

The 2026-09-04 truncated-YouTube re-ingest deleted 18 position_evidence rows,
because the propositions they cited had been extracted from text that was
missing 20-63% of what the teacher actually said. Those propositions are gone
and better ones now exist, but nothing links them: four CURRENT positions are
serving on thinner evidence than the corpus can support.

    can a believer lose their salvation        corpus   lost 5 of 15
    deliverance from demons and spiritual war  teacher  lost 4 of 15
    how to pray effectively                    teacher  lost 4 of 15
    fasting                                    teacher  lost 3 of 15

Rebuild goes through serve_position.rebuild_position(), the canonical path --
NOT a hand-rolled gather/write. It re-determines scope from current evidence
and supersedes the prior version rather than overwriting it (Settled #22), so
every rebuild here is reversible by flipping is_current back.

TWO THINGS TO WATCH, both expected rather than faults:
  - SCOPE CAN CHANGE. CLAUDE.md records a live case where removing a single
    proposition flipped `holiness and personal purity` from a 4-teacher corpus
    position to a Prince-only teacher position. That is a real change in what
    the product says, not a cosmetic diff, so every scope change is printed
    loudly and should be reviewed before being left to serve.
  - The three teacher-scope rows carry requested_teacher_id = Vlad Savchuk, so
    they are teacher-EXPLICIT lineages and must be rebuilt with that teacher
    named, or rebuild_position() would look up a different lineage key.

Dry-run by default. --apply is required to write.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / "backend" / "app" / ".env")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402

import positions as pos  # noqa: E402
import serve_position as sp  # noqa: E402
import eligible_statements as es  # noqa: E402

SAVCHUK = "Vlad Savchuk"

# (topic, requested_teacher or None) -- None means a topic lineage whose scope
# is re-determined by dominance; a name means a teacher-explicit lineage.
TARGETS = [
    ("can a believer lose their salvation", None),
    ("deliverance from demons and spiritual warfare", SAVCHUK),
    ("how to pray effectively", SAVCHUK),
    ("fasting", SAVCHUK),
]


def current_rows(params):
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        select topic, topic_key, kind, version, source_id::text sid,
               requested_teacher_id::text rt, id::text pid,
               (select count(*) from position_evidence pe where pe.position_id = p.id) ev
        from positions p where is_current
    """)
    rows = {r["topic"]: r for r in cur.fetchall()}
    cur.close()
    conn.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--topic", help="rebuild only this topic")
    args = ap.parse_args()

    targets = TARGETS
    if args.topic:
        targets = [t for t in TARGETS if t[0] == args.topic]
        if not targets:
            sys.exit("ERROR: %r is not one of the four affected topics" % args.topic)

    params = pos.db_params()
    before = current_rows(params)

    print("\n=== rebuild positions after re-ingest [%s] — %d topic(s) ===\n"
          % ("APPLY" if args.apply else "DRY-RUN", len(targets)))

    eligible_ids = es.load_eligible_ids(params)
    print("eligible proposition set: %d\n" % len(eligible_ids))

    results = []
    for topic, teacher in targets:
        b = before.get(topic)
        print("-" * 72)
        print("%s" % topic)
        if not b:
            print("  SKIP: no current version"); continue
        print("  now: %s v%s, %d evidence rows, lineage=%s"
              % (b["kind"], b["version"], b["ev"], "teacher-explicit" if b["rt"] else "topic"))

        if teacher:
            sid = sp.resolve_teacher_source_id(params, teacher)
            fresh = pos.gather_evidence(params, sid, topic, eligible_ids)
            print("  fresh gather (%s): %d propositions" % (teacher, len(fresh)))
        else:
            fresh = pos.gather_evidence_corpus(params, topic, eligible_ids)
            from app.services.dominance import determine_scope
            scope, top = determine_scope(fresh)
            print("  fresh gather (corpus): %d propositions -> scope would be %s"
                  % (len(fresh), scope))
        if len(fresh) < pos.MIN_EVIDENCE_COUNT:
            print("  WOULD REFUSE: below the honest-empty floor (%d) — prior version stays current"
                  % pos.MIN_EVIDENCE_COUNT)

        if not args.apply:
            print("  [dry-run] would rebuild")
            continue

        res = sp.rebuild_position(params, topic, eligible_ids, requested_teacher=teacher)
        status = res.get("status")
        print("  rebuild: status=%s" % status)
        for k in ("kind", "version", "evidence_count", "note"):
            if k in res:
                print("    %s: %s" % (k, res[k]))
        results.append((topic, b, res))

    if not args.apply:
        return

    after = current_rows(params)
    print("\n" + "=" * 72)
    print("%-44s%-10s%-10s%s" % ("topic", "was", "now", "evidence"))
    print("-" * 72)
    scope_changes = []
    for topic, b, res in results:
        a = after.get(topic)
        if not a:
            print("%-44s%-10s%-10s%s" % (topic[:43], b["kind"], "MISSING", "-")); continue
        print("%-44s%-10s%-10s%d -> %d"
              % (topic[:43], "%s v%s" % (b["kind"], b["version"]),
                 "%s v%s" % (a["kind"], a["version"]), b["ev"], a["ev"]))
        if a["kind"] != b["kind"]:
            scope_changes.append((topic, b["kind"], a["kind"]))
    print("-" * 72)
    print("RECONCILIATION  attempted=%d rebuilt=%d" % (len(targets), len(results)))
    if scope_changes:
        print("\n!! SCOPE CHANGED — review before leaving these to serve:")
        for topic, was, now in scope_changes:
            print("   %s: %s -> %s" % (topic, was, now))
    else:
        print("no scope changes")


if __name__ == "__main__":
    main()
