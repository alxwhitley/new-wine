"""
single_teacher_lock.py -- Project 2 phase 1, step 2 (PLAN.md v5.24, CLAUDE.md
Settled decision #15). Retrieval-time restriction: for a question whose
topic app.services.debate_topics explicitly and confidently classifies as
SETTLED -- never merely a topic that fails to match a debate topic -- and
whose retrieved evidence for THIS question actually concentrates in one
teacher, restrict what feeds the writer to that one dominant teacher's own
material, instead of pulling from multiple teachers.

Scope, restated from decision #15 (read it before changing this file):
retrieval-only. This does NOT label the served answer with that teacher's
name and does NOT replace or bypass reference_verifier.py's existing
ungrounded-attribution guard -- that guard stays exactly as-is and gets
strictly MORE precise here for free, since chunks -> permitted_names
collapses to a size-1 set once locked. No attribution-injection mechanism
of any kind lives in this file.

Gated on matched_settled_topic(), not classify_topic()=="settled": the
classifier's own binary output is safe on its own terms (SETTLED never
fires as a default -- see debate_topics.py), but this module names the
specific-topic function anyway, for the same defensive reason
get_teacher_card()'s fix (backend/app/routers/study.py) already gates on
matched_debate_topic() rather than classify_topic()=="debate" -- a
consumer here should never have to re-derive that classify_topic()=="debate"
would silently include every unmatched question, on the branch that would
make this lock fire far too often.

Dominance decision reused from app.services.dominance
(DOMINANCE_THRESHOLD=0.60, determine_scope()) -- the SAME function
scripts/positions.py's teacher-vs-corpus scope determination uses for the
stored position layer, not a second, independently-reasoned dominance
calculation. scripts/positions.py's own gather_evidence_corpus()/
determine_scope() could NOT be imported directly here -- two separate
reasons, not one: (1) scripts/ is not on the backend Railway service's
deploy root (backend/nixpacks.toml's Root Directory is backend/), so
scripts/positions.py is unreachable from a live backend import in
production, only in a local monorepo checkout; (2) even set that aside --
gather_evidence_corpus() opens its own psycopg2 connection (db_params(),
reading SUPABASE_DB_URL directly) and runs a fresh embedding search over
`propositions` (paraphrased extraction, gated by the pass-both eligible
set -- confirmed CPU-bound unless materialized, PLAN.md's position-layer
landmine), a structurally different, heavier operation than what this
retrieval path needs: chat.py/producer.py have ALREADY retrieved and
scored `chunks` for this exact question by the time this module runs: a
second embedding call and a second table's worth of evidence would not
even be guaranteed to agree with what was actually retrieved for the
answer. app.services.dominance.determine_scope() is the one piece that
generalizes cleanly across both: pure, no I/O, keyed only on a
"source_id" per evidence item.

A retrieved chunk does not carry source_id (match_chunks/search_chunks_fts
return a plain `author` text string, not a foreign key -- migration 049) so
this module does one small additional read-only lookup against `documents`
to attach a real source_id per chunk, batched over the already-retrieved
document_ids, not a per-chunk query.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.services.debate_topics import matched_settled_topic
from app.services.dominance import DOMINANCE_THRESHOLD, determine_scope

logger = logging.getLogger(__name__)

# (chunk_id, (score, chunk)) -- the exact shape chat.py's/producer.py's own
# `collapsed` list already uses internally (post document-level collapse,
# pre per-author cap).
ChunkEntry = Tuple[str, Tuple[float, dict]]


def resolve_source_ids_for_documents(db, document_ids):
    # type: (object, List[str]) -> Dict[str, str]
    """document_id -> source_id, via one batched read-only SELECT against
    `documents`. Fails soft: an empty/partial mapping just means fewer (or
    zero) chunks are locatable to a source_id, which
    apply_single_teacher_lock() treats as "cannot determine dominance, do
    not lock" -- never a crash on the live answer path.

    Public (promoted from _resolve_source_ids 2026-08-06) so the quote-rail
    selection wiring (app.services.async_answers.producer) can derive the
    same considered-teacher-source_ids from `chunks` without forking this
    lookup -- the same "one shared implementation" move already made for
    DOMINANCE_THRESHOLD/determine_scope (dominance.py)."""
    unique_ids = sorted({d for d in document_ids if d})
    if not unique_ids:
        return {}
    try:
        result = (
            db.table("documents")
            .select("id, source_id")
            .in_("id", unique_ids)
            .execute()
        )
        return {
            row["id"]: row["source_id"]
            for row in (result.data or [])
            if row.get("source_id")
        }
    except Exception:
        logger.exception(
            "single_teacher_lock: documents->source_id lookup failed for %d "
            "document_ids -- lock cannot apply this call",
            len(unique_ids),
        )
        return {}


def apply_single_teacher_lock(question, collapsed, db):
    # type: (str, List[ChunkEntry], object) -> Tuple[List[ChunkEntry], bool]
    """Return (chunks, locked). `collapsed` is returned unchanged (locked=
    False) UNLESS `question`'s topic is a confirmed settled topic
    (matched_settled_topic(question) is not None) AND one teacher supplies
    >= DOMINANCE_THRESHOLD of `collapsed`'s own retrieved evidence for this
    specific question -- in which case only that teacher's entries from
    `collapsed` are returned (locked=True), unfiltered by count.

    Callers should skip their own per-author cap entirely when locked=True:
    the cap's purpose (stop one teacher's material crowding out other
    teachers in the rerank pool) is moot once already restricted to one
    teacher, and reapplying it would just discard that teacher's own good
    material for no benefit -- see chat.py's/producer.py's own call sites.

    `collapsed` is expected to already be sorted by score (highest first,
    chat.py's/producer.py's own convention) -- order is preserved, only
    membership is filtered.
    """
    settled_key = matched_settled_topic(question)
    if settled_key is None:
        return collapsed, False
    if not collapsed:
        return collapsed, False

    document_ids = [chunk.get("document_id", "") for _, (_, chunk) in collapsed]
    doc_to_source = resolve_source_ids_for_documents(db, document_ids)

    evidence = [
        {"source_id": doc_to_source[chunk.get("document_id", "")]}
        for _, (_, chunk) in collapsed
        if chunk.get("document_id", "") in doc_to_source
    ]
    if not evidence:
        logger.info(
            "single_teacher_lock: settled topic=%r matched but no source_id "
            "resolved for any retrieved chunk -- no lock",
            settled_key,
        )
        return collapsed, False

    scope, dominant_source_id = determine_scope(evidence)
    if scope != "teacher":
        logger.info(
            "single_teacher_lock: settled topic=%r matched but no teacher "
            "clears DOMINANCE_THRESHOLD=%.2f among %d retrieved chunks -- no lock",
            settled_key, DOMINANCE_THRESHOLD, len(evidence),
        )
        return collapsed, False

    locked = [
        (cid, (score, chunk))
        for cid, (score, chunk) in collapsed
        if doc_to_source.get(chunk.get("document_id", "")) == dominant_source_id
    ]
    logger.info(
        "single_teacher_lock: settled topic=%r LOCKED to source_id=%s (%d/%d chunks)",
        settled_key, dominant_source_id, len(locked), len(collapsed),
    )
    return locked, True
