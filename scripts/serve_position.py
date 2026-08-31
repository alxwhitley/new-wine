#!/usr/bin/env python3
"""
serve_position.py -- question-time serving path for the position layer
(PLAN.md track PL / #48, serving-path session 2026-08-01).

Lifecycle settled 2026-07-28: positions are generated ON DEMAND at question
time, persisted once written, and served from storage on the next identical
question -- never regenerated, never pre-written ahead of time. This module is
that path. It does NOT touch the live chat answer flow this session (Part 3 of
the build is a standalone proof); it is exercised by
scripts/prove_serving_path.py.

--------------------------------------------------------------------------
Lookup-or-generate
--------------------------------------------------------------------------
serve_position(topic, requested_teacher=None):
  1. Normalize topic -> topic_key (positions.normalize_topic_key -- the one
     shared contract with migration 077's SQL).
  2. Resolve the lineage lookup key: (topic_key, requested_teacher_id), where
     requested_teacher_id is the teacher a question EXPLICITLY named, or NULL
     for a topic/corpus question.
  3. If a current version exists -> serve it from storage, verbatim. No LLM
     call, no regeneration (an answer a user already saw must not change).
  4. Otherwise generate:
       - teacher-explicit question -> gather that teacher's evidence -> a
         teacher position (or honest-empty).
       - topic question -> gather corpus-wide -> determine scope by single-
         teacher dominance (positions.DOMINANCE_THRESHOLD) -> a teacher
         position for the dominant teacher, OR a corpus position naming its
         real contributors (or honest-empty).
     Generation stays SOURCE-BLIND throughout -- only proposition content
     (and, for corpus, plain teacher-NAME labels) ever reaches the LLM
     (CLAUDE.md Invariant 12). The honest-empty floor is checked before any
     generation, so NO LLM CALL is made on a refusal.

--------------------------------------------------------------------------
Versioning / scope widening
--------------------------------------------------------------------------
rebuild_position() writes a NEW version that supersedes the current one rather
than overwriting it (positions._insert_position_version). A topic lineage can
widen teacher->corpus across versions without a from-scratch rewrite, because
the lookup key is (topic_key, requested_teacher_id) -- unchanged by a scope
change -- while kind/source_id are per-version.

--------------------------------------------------------------------------
Empty-state -- the four permanent rules (PLAN.md, settled 2026-07-28)
--------------------------------------------------------------------------
  1. One empty message, always the same SHAPE -- thin vs absent is never
     exposed. (Teacher- vs topic-scoped messages differ only by naming the
     asked teacher, required by rule 3; within each, the wording is identical
     whether coverage is thin or zero.)
  2. Wording is about the LIBRARY, not the teacher -- never "he doesn't teach
     this," which the corpus cannot support wherever coverage is merely thin.
  3. Refuse in the asked-for teacher's voice, then SEPARATELY offer to show
     who else in the corpus addresses the topic. User-initiated crossover
     only -- this module returns the offer + candidate list but NEVER
     auto-serves another teacher.
  4. Near-miss: where the teacher has adjacent-but-off-question material,
     name what he addresses nearby (as pointers, not an answer). A hedged
     position is never served as an answer.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import positions as pos  # noqa: E402

# Exploratory floor used ONLY to detect near-miss adjacency -- below the real
# relevance floor (positions.SIMILARITY_FLOOR = 0.45). Material in
# [NEAR_MISS_FLOOR, SIMILARITY_FLOOR) is adjacent-but-not-an-answer: enough to
# say "he addresses X nearby," never enough to build a position from.
NEAR_MISS_FLOOR = 0.30
NEAR_MISS_MAX = 40
NEAR_MISS_NAME_COUNT = 3  # how many nearest adjacent snippets to surface

EMPTY_MESSAGE_TOPIC = (
    "I couldn't find enough in New Wine's library to give a grounded answer on "
    "that."
)


def _empty_message_teacher(teacher_name: str) -> str:
    """Rule 2: about the LIBRARY's coverage of the teacher, never a claim that
    the teacher never taught it. Rule 1: identical wording whether coverage is
    thin or zero -- thinness is never exposed."""
    return (
        f"I couldn't find enough of {teacher_name}'s teaching in New Wine's "
        "library to give a grounded answer on that."
    )


def resolve_teacher_source_id(params: dict, teacher_name: str) -> str:
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT id::text FROM sources WHERE name = %s", (teacher_name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise ValueError(f"No sources row named {teacher_name!r}")
    return row[0]


def lookup_current_position(
    params: dict, topic_key: str, requested_teacher_id: Optional[str]
) -> Optional[Dict]:
    """The current (is_current, non-retracted) position for this lineage, or
    None. Lineage key is (topic_key, requested_teacher_id); IS NOT DISTINCT
    FROM makes NULL requested_teacher_id (a topic/corpus question) match
    correctly."""
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id::text, kind, source_id::text, content, version,
                   lineage_id::text, status, prompt_version, created_at
            FROM positions
            WHERE topic_key = %s
              AND is_current = true
              AND requested_teacher_id IS NOT DISTINCT FROM %s
              AND status <> 'retracted'
            """,
            (topic_key, requested_teacher_id),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "id": row[0], "kind": row[1], "source_id": row[2], "content": row[3],
        "version": row[4], "lineage_id": row[5], "status": row[6],
        "prompt_version": row[7], "created_at": row[8],
    }


def _current_lineage_row(params: dict, topic_key: str,
                         requested_teacher_id: Optional[str]) -> Optional[Dict]:
    """The current version's lineage-bearing fields, for a rebuild's
    supersedes= argument."""
    import psycopg2

    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id::text, lineage_id::text, version
            FROM positions
            WHERE topic_key = %s
              AND is_current = true
              AND requested_teacher_id IS NOT DISTINCT FROM %s
            """,
            (topic_key, requested_teacher_id),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not row:
        return None
    return {"id": row[0], "lineage_id": row[1], "version": row[2]}


def who_else_addresses(
    params: dict, topic: str, eligible_ids, exclude_source_id: Optional[str],
    floor: float = pos.SIMILARITY_FLOOR, min_count: int = 1,
) -> List[Dict]:
    """Backs the user-INITIATED crossover offer (rule 3). Distinct teachers
    (excluding the asked one) with >= min_count eligible statements >= floor on
    the topic, by count desc. Never auto-served -- returned as an offer only."""
    ev = pos.gather_evidence_corpus(
        params, topic, eligible_ids, floor=floor, max_evidence=80
    )
    counts: Counter = Counter()
    names: Dict[str, str] = {}
    for e in ev:
        if e["source_id"] == exclude_source_id:
            continue
        counts[e["source_id"]] += 1
        names[e["source_id"]] = e["teacher"]
    return [
        {"source_id": sid, "name": names[sid], "count": n}
        for sid, n in counts.most_common()
        if n >= min_count
    ]


def _serve_stored(params: dict, row: Dict) -> Dict:
    out = {
        "status": "served",
        "served_from": "stored",
        "position_id": row["id"],
        "kind": row["kind"],
        "source_id": row["source_id"],
        "version": row["version"],
        "lineage_id": row["lineage_id"],
        "position_status": row["status"],
        "prompt_version": row["prompt_version"],
        "content": row["content"],
        "created_at": row["created_at"].isoformat()
        if hasattr(row["created_at"], "isoformat") else row["created_at"],
    }
    if row["kind"] == "corpus":
        out["contributors"] = pos.contributor_breakdown_from_db(params, row["id"])
    return out


def _serve_written(params: dict, result: Dict, scope_note: Optional[str] = None) -> Dict:
    """Map a write_position()/write_corpus_position() result to a served
    response. Passes refusals/errors through unchanged (their floor check
    already guaranteed no LLM call on refusal)."""
    if result["status"] != "written":
        return result
    out = dict(result)
    out["status"] = "served"
    out["served_from"] = "generated"
    if scope_note:
        out["scope_determined"] = scope_note
    if result["kind"] == "corpus":
        # Re-derive contributors authoritatively from the persisted evidence
        # rows (not the in-memory list), matching how a stored serve reports.
        out["contributors"] = pos.contributor_breakdown_from_db(
            params, result["position_id"]
        )
    return out


def _empty_teacher(params: dict, topic: str, teacher_name: str, source_id: str,
                   low_evidence: List[Dict], eligible_ids) -> Dict:
    """Honest-empty for a teacher-explicit question. No LLM call was made."""
    near = [e for e in low_evidence if e["similarity"] < pos.SIMILARITY_FLOOR]
    crossover = who_else_addresses(params, topic, eligible_ids, exclude_source_id=source_id)
    return {
        "status": "empty",
        "served_from": "generated",
        "no_llm_call": True,
        "kind": "teacher",
        "topic": topic,
        "requested_teacher": teacher_name,
        "message": _empty_message_teacher(teacher_name),  # rules 1, 2
        # rule 4: name what he addresses nearby, as pointers -- never a position
        "near_miss": {
            "available": len(near) > 0,
            "nearest_adjacent": [
                {"content": e["content"], "similarity": round(e["similarity"], 3)}
                for e in near[:NEAR_MISS_NAME_COUNT]
            ],
            "not_a_position": True,
        },
        # rule 3: separate, user-initiated crossover offer -- never auto-served
        "crossover_offer": {
            "available": len(crossover) > 0,
            "teachers": crossover,
            "user_initiated_only": True,
        },
    }


def _empty_topic(topic: str) -> Dict:
    """Honest-empty for a topic/corpus question. No teacher voice, no crossover
    (already corpus-wide). No LLM call was made."""
    return {
        "status": "empty",
        "served_from": "generated",
        "no_llm_call": True,
        "kind": "topic",
        "topic": topic,
        "message": EMPTY_MESSAGE_TOPIC,  # rules 1, 2
    }


def _generate_teacher_explicit(params, topic, teacher_name, source_id, eligible_ids):
    low = pos.gather_evidence(
        params, source_id, topic, eligible_ids,
        floor=NEAR_MISS_FLOOR, max_evidence=NEAR_MISS_MAX,
    )
    primary = [e for e in low if e["similarity"] >= pos.SIMILARITY_FLOOR][: pos.MAX_EVIDENCE]
    if len(primary) < pos.MIN_EVIDENCE_COUNT:
        return _empty_teacher(params, topic, teacher_name, source_id, low, eligible_ids)
    result = pos.write_position(
        params, source_id, topic, primary,
        kind="teacher", teacher_name=teacher_name,
        requested_teacher_id=source_id,  # teacher-explicit: requested IS the teacher
    )
    return _serve_written(params, result, scope_note="teacher-explicit")


def _generate_topic(params, topic, eligible_ids, dominance_threshold=None):
    if dominance_threshold is None:
        dominance_threshold = pos.DOMINANCE_THRESHOLD
    low = pos.gather_evidence_corpus(
        params, topic, eligible_ids, floor=NEAR_MISS_FLOOR, max_evidence=NEAR_MISS_MAX,
    )
    primary = [e for e in low if e["similarity"] >= pos.SIMILARITY_FLOOR][: pos.MAX_EVIDENCE]
    if len(primary) < pos.MIN_EVIDENCE_COUNT:
        return _empty_topic(topic)

    # Scope by single-teacher dominance over the gathered evidence.
    counts = Counter(e["source_id"] for e in primary)
    total = sum(counts.values())
    top_source, top_n = counts.most_common(1)[0]
    if top_n / total >= dominance_threshold:
        # Teacher-dominated: build the dominant teacher's own position (a topic
        # question, so requested_teacher_id stays NULL -- it can later widen to
        # corpus). Re-gather the dominant teacher's own top evidence for a
        # richer position than his slice of the corpus top-N.
        teacher_name = next(e["teacher"] for e in primary if e["source_id"] == top_source)
        tprimary = pos.gather_evidence(params, top_source, topic, eligible_ids)
        if len(tprimary) >= pos.MIN_EVIDENCE_COUNT:
            result = pos.write_position(
                params, top_source, topic, tprimary,
                kind="teacher", teacher_name=teacher_name,
                requested_teacher_id=None,  # topic question -> NULL lineage key
            )
            return _serve_written(
                params, result,
                scope_note="teacher-dominated (%d/%d >= %.2f)" % (top_n, total, dominance_threshold),
            )
        # Dominant teacher's own on-topic evidence is itself thin -> fall back
        # to a corpus position over the distributed evidence (guaranteed >=
        # floor). Honest: contributors + counts show the real distribution.
        result = pos.write_corpus_position(
            params, topic, primary, requested_teacher_id=None,
        )
        return _serve_written(
            params, result,
            scope_note="corpus (dominant-teacher gather below floor)",
        )

    result = pos.write_corpus_position(params, topic, primary, requested_teacher_id=None)
    return _serve_written(
        params, result,
        scope_note="corpus (top share %d/%d < %.2f)" % (top_n, total, dominance_threshold),
    )


def serve_position(
    params: dict,
    topic: str,
    eligible_ids,
    requested_teacher: Optional[str] = None,
) -> Dict:
    """Lookup-or-generate. Serves a stored current version if one exists (no
    LLM call), else generates, persists, and serves. See module docstring."""
    topic_key = pos.normalize_topic_key(topic)
    requested_teacher_id = (
        resolve_teacher_source_id(params, requested_teacher)
        if requested_teacher else None
    )

    existing = lookup_current_position(params, topic_key, requested_teacher_id)
    if existing is not None:
        return _serve_stored(params, existing)

    if requested_teacher_id is not None:
        return _generate_teacher_explicit(
            params, topic, requested_teacher, requested_teacher_id, eligible_ids
        )
    return _generate_topic(params, topic, eligible_ids)


def rebuild_position(
    params: dict,
    topic: str,
    eligible_ids,
    requested_teacher: Optional[str] = None,
    dominance_threshold: Optional[float] = None,
) -> Dict:
    """Force a NEW version of an existing lineage (versioning-on-rebuild), even
    when a current version exists -- used when more evidence has arrived. The
    prior version is retained (is_current=false), never overwritten. Scope is
    re-determined from current evidence, so a topic lineage can WIDEN
    teacher->corpus here without a from-scratch rewrite. dominance_threshold
    overrides positions.DOMINANCE_THRESHOLD for this rebuild (lets a caller
    reflect a changed evidence landscape, and lets the proof demonstrate
    widening deterministically)."""
    topic_key = pos.normalize_topic_key(topic)
    requested_teacher_id = (
        resolve_teacher_source_id(params, requested_teacher)
        if requested_teacher else None
    )
    prior = _current_lineage_row(params, topic_key, requested_teacher_id)
    if prior is None:
        # Nothing to rebuild -- fall back to a first-time generate.
        return serve_position(params, topic, eligible_ids, requested_teacher)

    if requested_teacher_id is not None:
        source_id = requested_teacher_id
        primary = pos.gather_evidence(params, source_id, topic, eligible_ids)
        if len(primary) < pos.MIN_EVIDENCE_COUNT:
            return {
                "status": "rebuild_refused_floor",
                "topic": topic,
                "evidence_count": len(primary),
                "note": "prior version left current; not superseded",
            }
        result = pos.write_position(
            params, source_id, topic, primary, kind="teacher",
            teacher_name=requested_teacher, requested_teacher_id=source_id,
            supersedes=prior,
        )
        return _serve_written(params, result, scope_note="rebuild (teacher-explicit)")

    # Topic lineage: re-determine scope; may widen teacher->corpus.
    dt = dominance_threshold if dominance_threshold is not None else pos.DOMINANCE_THRESHOLD
    primary_corpus = [
        e for e in pos.gather_evidence_corpus(
            params, topic, eligible_ids, floor=NEAR_MISS_FLOOR, max_evidence=NEAR_MISS_MAX)
        if e["similarity"] >= pos.SIMILARITY_FLOOR
    ][: pos.MAX_EVIDENCE]
    if len(primary_corpus) < pos.MIN_EVIDENCE_COUNT:
        return {
            "status": "rebuild_refused_floor",
            "topic": topic,
            "evidence_count": len(primary_corpus),
            "note": "prior version left current; not superseded",
        }
    counts = Counter(e["source_id"] for e in primary_corpus)
    total = sum(counts.values())
    top_source, top_n = counts.most_common(1)[0]
    if top_n / total >= dt:
        teacher_name = next(e["teacher"] for e in primary_corpus if e["source_id"] == top_source)
        tprimary = pos.gather_evidence(params, top_source, topic, eligible_ids)
        if len(tprimary) >= pos.MIN_EVIDENCE_COUNT:
            result = pos.write_position(
                params, top_source, topic, tprimary, kind="teacher",
                teacher_name=teacher_name, requested_teacher_id=None,
                supersedes=prior,
            )
            return _serve_written(params, result, scope_note="rebuild (teacher-dominated)")
    result = pos.write_corpus_position(
        params, topic, primary_corpus, requested_teacher_id=None, supersedes=prior,
    )
    return _serve_written(params, result, scope_note="rebuild (corpus)")
