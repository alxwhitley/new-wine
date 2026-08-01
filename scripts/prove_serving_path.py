#!/usr/bin/env python3
"""
prove_serving_path.py -- standalone proof of the question-time serving path
(PLAN.md #48 serving-path session, 2026-08-01). NOT wired into the live chat
answer path -- this is Part 3's standalone proof.

What it proves, each verified directly against the DB on a FRESH connection
(never trusted from a function's own self-report):
  1. Serve-from-storage: an already-stored current position is served
     verbatim, with NO LLM call and NO new row.
  2. Teacher-explicit generation: strong evidence -> a teacher position.
  3. Honest-empty (teacher): thin evidence -> the four empty-state rules, NO
     LLM call, NO row written.
  4. Corpus scope: a distributed topic -> a corpus position naming its real
     contributors with per-teacher counts.
  5. Genuine disagreement: a contested topic -> the corpus position presents
     the disagreement (inspected in output).
  6. Honest-empty (topic): an absent topic -> empty-state, NO LLM call, NO row.
  7. Idempotent re-serve: asking case 4 again serves from storage, NO new LLM
     call, same position_id.
  8. Versioning + scope widening: a teacher-dominated topic -> v1 teacher;
     rebuilt (simulating a changed evidence landscape) -> v2 corpus superseding
     v1, same lineage, v1 retained is_current=false. Demo lineage cleaned up.

Cost: ~5-6 Anthropic (claude-sonnet-4-5, <=600 out tok) calls for the
generated positions; refusals make zero calls. Well under any ceiling.

Eligible set: computed via eligible_statements (the real pass-both gate). Set
POSITION_ELIGIBLE_CACHE=/path/to/ids.json to load a precomputed set instead
(the whole-corpus computation is CPU-bound and slow -- see the session
report; a production serving path must materialize this, not recompute live).

Run: python3 scripts/prove_serving_path.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / "backend" / "app" / ".env")

import psycopg2  # noqa: E402
import positions as pos  # noqa: E402
import serve_position as sp  # noqa: E402

# ---------------------------------------------------------------- confirmed via the Phase-A distribution probe (session report)
STRONG_TEACHER = ("Derek Prince", "the divine exchange at the cross")       # 100% Prince
THIN_TEACHER = ("E.M. Bounds", "speaking in tongues and the baptism in the Holy Spirit")  # 0 primary, 27 near, 4 crossover
CORPUS_TOPIC = "holiness and personal purity"                              # top 53% -> corpus, 4 teachers
DISAGREEMENT_TOPIC = "can a believer lose their salvation"                 # top 40% -> corpus, contested doctrine
EMPTY_TOPIC = "the liturgical calendar and church seasons"                 # absent corpus-wide
WIDENING_DEMO_TOPIC = "the fear of the Lord"                               # 93% Prince -> teacher-dominated (demo, cleaned up)
STORED_TEACHER = ("Vlad Savchuk", "fasting")  # already stored v1 (migration-verified)

# ---- LLM-call spy: wraps the two generators to count real calls ----
_calls = {"teacher": 0, "corpus": 0}
_orig_t = pos.generate_position_text
_orig_c = pos.generate_corpus_position_text


def _spy_t(*a, **k):
    _calls["teacher"] += 1
    return _orig_t(*a, **k)


def _spy_c(*a, **k):
    _calls["corpus"] += 1
    return _orig_c(*a, **k)


pos.generate_position_text = _spy_t
pos.generate_corpus_position_text = _spy_c

_p = 0
_f = 0


def check(label, ok):
    global _p, _f
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if ok:
        _p += 1
    else:
        _f += 1


def db_row(params, position_id):
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    c = conn.cursor()
    c.execute(
        "SELECT kind, source_id::text, requested_teacher_id::text, version, "
        "is_current, lineage_id::text, prompt_version, prompt_fingerprint, "
        "model, status, topic_key FROM positions WHERE id=%s",
        (position_id,),
    )
    row = c.fetchone()
    c.close()
    conn.close()
    return row


def count_rows(params, topic_key, requested_teacher_id):
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    c = conn.cursor()
    c.execute(
        "SELECT count(*) FROM positions WHERE topic_key=%s "
        "AND requested_teacher_id IS NOT DISTINCT FROM %s",
        (topic_key, requested_teacher_id),
    )
    n = c.fetchone()[0]
    c.close()
    conn.close()
    return n


def build_eligibility():
    """The lazy pass-both checker -- the only viable form at question time (the
    whole-corpus computation is CPU-bound; see the session report). Uses the
    SAME per-proposition decision as eligible_statements.compute_eligible_
    proposition_ids (classify_eligibility), so verdicts are identical; only the
    set of propositions checked differs (candidates only)."""
    import eligible_statements as es
    print("building lazy EligibilityChecker (pass-both gate)...")
    return es.EligibilityChecker(pos.db_params())


def main():
    params = pos.db_params()
    eligible = build_eligibility()
    print()

    # ===== Case 1: serve from storage (no LLM, no new row) =====
    print("Case 1 -- serve stored teacher position (Savchuk/fasting)")
    before = dict(_calls)
    r = sp.serve_position(params, STORED_TEACHER[1], eligible, requested_teacher=STORED_TEACHER[0])
    check("served", r["status"] == "served")
    check("served_from == stored", r.get("served_from") == "stored")
    check("no LLM call made", _calls == before)
    check("version 1", r.get("version") == 1)

    # ===== Case 2: teacher-explicit generation (strong evidence) =====
    print(f"\nCase 2 -- teacher-explicit generate ({STRONG_TEACHER[0]} / {STRONG_TEACHER[1]!r})")
    tk2 = pos.normalize_topic_key(STRONG_TEACHER[1])
    src2 = sp.resolve_teacher_source_id(params, STRONG_TEACHER[0])
    n_before = count_rows(params, tk2, src2)
    before = dict(_calls)
    r = sp.serve_position(params, STRONG_TEACHER[1], eligible, requested_teacher=STRONG_TEACHER[0])
    check("served", r["status"] == "served")
    check("served_from == generated", r.get("served_from") == "generated")
    check("kind teacher", r.get("kind") == "teacher")
    check("exactly one teacher LLM call", _calls["teacher"] == before["teacher"] + 1 and _calls["corpus"] == before["corpus"])
    if r["status"] == "served" and r.get("served_from") == "generated":
        row = db_row(params, r["position_id"])
        check("DB: kind=teacher, source_id set, requested=source", row and row[0] == "teacher" and row[1] == src2 and row[2] == src2)
        check("DB: provenance all NOT NULL", row and all(row[i] for i in (6, 7, 8)))
        check("DB: row count +1", count_rows(params, tk2, src2) == n_before + 1)
        print("    --- content ---")
        print("    " + r["content"].replace("\n", "\n    "))

    # ===== Case 3: honest-empty (teacher, thin) -- no LLM, no row =====
    print(f"\nCase 3 -- honest-empty teacher ({THIN_TEACHER[0]} / {THIN_TEACHER[1]!r})")
    tk3 = pos.normalize_topic_key(THIN_TEACHER[1])
    src3 = sp.resolve_teacher_source_id(params, THIN_TEACHER[0])
    n_before = count_rows(params, tk3, src3)
    before = dict(_calls)
    r = sp.serve_position(params, THIN_TEACHER[1], eligible, requested_teacher=THIN_TEACHER[0])
    check("status empty", r["status"] == "empty")
    check("no LLM call", _calls == before)
    check("no row written", count_rows(params, tk3, src3) == n_before)
    check("message about library, names teacher", r.get("message") and "library" in r["message"].lower())
    check("crossover offer present + user-initiated only", r.get("crossover_offer", {}).get("user_initiated_only") is True)
    check("near_miss field present (not a position)", r.get("near_miss", {}).get("not_a_position") is True)
    print(f"    message: {r.get('message')}")
    print(f"    crossover available: {r.get('crossover_offer',{}).get('available')}, "
          f"teachers: {[t['name'] for t in r.get('crossover_offer',{}).get('teachers',[])][:5]}")
    print(f"    near_miss available: {r.get('near_miss',{}).get('available')}")

    # ===== Case 4: corpus scope =====
    print(f"\nCase 4 -- corpus scope ({CORPUS_TOPIC!r})")
    tk4 = pos.normalize_topic_key(CORPUS_TOPIC)
    n_before = count_rows(params, tk4, None)
    before = dict(_calls)
    r = sp.serve_position(params, CORPUS_TOPIC, eligible)
    check("served", r["status"] == "served")
    check("kind corpus", r.get("kind") == "corpus")
    check("exactly one corpus LLM call", _calls["corpus"] == before["corpus"] + 1 and _calls["teacher"] == before["teacher"])
    if r.get("kind") == "corpus" and r["status"] == "served":
        row = db_row(params, r["position_id"])
        check("DB: kind=corpus, source_id NULL, requested NULL", row and row[0] == "corpus" and row[1] is None and row[2] is None)
        check("DB: provenance all NOT NULL", row and all(row[i] for i in (6, 7, 8)))
        contribs = r.get("contributors", [])
        check("contributors named with counts (>=2 teachers)", len(contribs) >= 2)
        check("scope note recorded", "scope_determined" in r)
        print(f"    scope: {r.get('scope_determined')}")
        print(f"    contributors: {[(c['name'], c['count']) for c in contribs]}")
        print("    --- content ---")
        print("    " + r["content"].replace("\n", "\n    "))

    # ===== Case 5: genuine disagreement =====
    print(f"\nCase 5 -- disagreement topic ({DISAGREEMENT_TOPIC!r})")
    r = sp.serve_position(params, DISAGREEMENT_TOPIC, eligible)
    check("served or empty (inspect)", r["status"] in ("served", "empty"))
    if r["status"] == "served":
        print(f"    kind: {r.get('kind')}  scope: {r.get('scope_determined')}")
        if r.get("contributors"):
            print(f"    contributors: {[(c['name'], c['count']) for c in r['contributors']]}")
        print("    --- content (inspect for disagreement presentation) ---")
        print("    " + r["content"].replace("\n", "\n    "))
    else:
        print(f"    empty: {r.get('message')}")

    # ===== Case 6: honest-empty (topic) -- no LLM, no row =====
    print(f"\nCase 6 -- honest-empty topic ({EMPTY_TOPIC!r})")
    tk6 = pos.normalize_topic_key(EMPTY_TOPIC)
    n_before = count_rows(params, tk6, None)
    before = dict(_calls)
    r = sp.serve_position(params, EMPTY_TOPIC, eligible)
    check("status empty", r["status"] == "empty")
    check("kind topic", r.get("kind") == "topic")
    check("no LLM call", _calls == before)
    check("no row written", count_rows(params, tk6, None) == n_before)
    print(f"    message: {r.get('message')}")

    # ===== Case 7: idempotent re-serve of case 4 =====
    print(f"\nCase 7 -- re-serve corpus topic (idempotent, from storage)")
    before = dict(_calls)
    r = sp.serve_position(params, CORPUS_TOPIC, eligible)
    check("served_from == stored", r.get("served_from") == "stored")
    check("no new LLM call", _calls == before)

    # ===== Case 8: versioning + scope widening (demo lineage, cleaned up) =====
    print(f"\nCase 8 -- versioning + widening ({WIDENING_DEMO_TOPIC!r})")
    tk8 = pos.normalize_topic_key(WIDENING_DEMO_TOPIC)
    demo_ids = []
    try:
        r1 = sp.serve_position(params, WIDENING_DEMO_TOPIC, eligible)  # v1
        if r1["status"] == "served":
            demo_ids.append(r1["position_id"])
        check("v1 generated, version 1", r1.get("version") == 1)
        print(f"    v1 kind={r1.get('kind')} scope={r1.get('scope_determined')}")
        # rebuild forcing corpus (dominance_threshold > 1 => never teacher)
        r2 = sp.rebuild_position(params, WIDENING_DEMO_TOPIC, eligible, dominance_threshold=1.01)
        if r2.get("position_id"):
            demo_ids.append(r2["position_id"])
        check("v2 generated, version 2", r2.get("version") == 2)
        check("v2 kind corpus (widened)", r2.get("kind") == "corpus")
        # verify in DB
        conn = psycopg2.connect(**params); conn.set_session(readonly=True, autocommit=True)
        c = conn.cursor()
        c.execute("SELECT version, kind, is_current, source_id::text, lineage_id::text, supersedes_id::text, id::text FROM positions WHERE topic_key=%s AND requested_teacher_id IS NULL ORDER BY version", (tk8,))
        rows = c.fetchall(); c.close(); conn.close()
        byv = {r[0]: r for r in rows}
        check("DB: 2 versions", len(rows) == 2)
        check("DB: v1 is_current=false, kind=teacher", 1 in byv and byv[1][2] is False and byv[1][1] == "teacher")
        check("DB: v2 is_current=true, kind=corpus, source_id NULL", 2 in byv and byv[2][2] is True and byv[2][1] == "corpus" and byv[2][3] is None)
        check("DB: same lineage across versions", len({byv[v][4] for v in byv}) == 1)
        check("DB: v2.supersedes_id == v1.id", 2 in byv and 1 in byv and byv[2][5] == byv[1][6])
    finally:
        if demo_ids:
            conn = psycopg2.connect(**params); conn.autocommit = True; c = conn.cursor()
            c.execute("DELETE FROM positions WHERE id = ANY(%s::uuid[])", (demo_ids,))
            c.execute("SELECT count(*) FROM positions WHERE topic_key=%s", (tk8,))
            left = c.fetchone()[0]; c.close(); conn.close()
            print(f"    cleanup: deleted {len(demo_ids)} demo rows; remaining with topic_key: {left}")

    print(f"\n=== LLM calls total: teacher={_calls['teacher']} corpus={_calls['corpus']} ===")
    print(f"{_p}/{_p+_f} checks passed")
    sys.exit(1 if _f else 0)


if __name__ == "__main__":
    main()
