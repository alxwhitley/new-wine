"""
stored_position_evidence.py -- Project 2 "one-hop" evidence-injection
(PLAN.md Phase 3 item 5's remaining sequence; CLAUDE.md Settled decision #18;
docs/audits/position_layer_revival_diagnostic_2026-08-04.md's "Design
pressure test" section, which pressure-tested and explicitly REJECTED the
original two-hop design -- store a position's rendered text, then synthesize
a served answer directly from THAT text. That design is NOT what this
module does.

app.services.stored_position_topics.match_stored_position(question) already
exists, is tested, and (until this module lands a caller in producer.py) has
no live caller: given a question, it returns the matched V1 topic_key (one
of six) or None, correctly deferring to debate framing (decision #11) and
staying silent on paper-fenced topics (baptism/tongues). This module
supplies the missing next step: given a matched topic_key, look up the
CURRENT stored positions row and return its underlying PROPOSITIONS --
never its rendered `content` text, never its phrasing -- reshaped into
chunk-compatible dicts the existing retrieval/generation/verification
pipeline (async_answers/producer.py) already knows how to consume. This is
a narrowing of what evidence reaches the writer, not a new answer path:
every downstream step (context building, retrieval grounding, generation,
the attribution regenerate-once-then-refuse guard, verify_references, quote
selection) runs completely unchanged on whatever `chunks` list it's handed,
whether that list came from real-time retrieval or from here.

Why REST, not scripts/positions.py's psycopg2 connection reuse: scripts/ is
outside the backend Railway deploy root (backend/nixpacks.toml's Root
Directory is backend/) -- confirmed unreachable from a live backend import,
the same constraint single_teacher_lock.py already documents for the same
reason. This module is a second, independent implementation of the position
lookup, using the same Supabase REST client every other live answer-path
module uses (positions/position_evidence RLS is service-role-full-access,
migration 073) -- not a reuse of scripts/serve_position.py's
lookup_current_position(), which cannot be imported here.

Why the license/visibility gate is re-applied HERE, live, not trusted from
storage time: position_evidence rows were gate-filtered when the position
was BUILT (positions.py's LICENSE_GATE_SQL, diagnostic step 3), but a
source's visibility/license can change afterward -- and for this exact
corpus, it already has diverged in effect: live-confirmed 2026-08-08, four
of the six seeded positions' evidence includes Vlad Savchuk and/or Leonard
Ravenhill, both currently unlicensed/hidden (CLAUDE.md Phase 1.3).
Re-deriving servability here, per evidence item, at serve time -- via
source_resolver.is_source_servable(), reused rather than forked, the same
predicate Invariant 2 requires everywhere else -- is what keeps this path
from ever citing a currently-hidden teacher's material as if it were
live-retrieved. Commentary/word_study content is excluded the same way
answer_toolbox.is_commentary_chunk() already excludes it from normal
retrieval (Settled decision #5) -- defense-in-depth, since propositions
extraction has no equivalent gate today.

Fail-safe throughout: any DB fault, missing position, empty evidence, or
every candidate proposition filtered by the live gate all return None,
never an empty-but-truthy list and never a raised exception up to the
caller -- `None` means "no usable stored evidence for this topic right
now," and the caller's contract is to fall through to normal RAG on None,
the same fail direction stored_position_topics.py already documents for
match_stored_position() itself ("no match -> normal RAG, never invent a
position").
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services import answer_toolbox
from app.services.source_resolver import is_source_servable

logger = logging.getLogger(__name__)


def _current_position_id(supabase, topic_key: str) -> Optional[str]:
    """The is_current, non-retracted positions.id for `topic_key` -- ANY
    lineage, not filtered on requested_teacher_id.

    Corrected during this build's own verification: an earlier version of
    this function required requested_teacher_id IS NULL (matching
    scripts/serve_position.py's lookup_current_position(), keyed on the
    lineage pair (topic_key, requested_teacher_id)), on the assumption that
    a topic-only matcher like match_stored_position() should only ever
    resolve a topic-only lineage. Live-confirmed 2026-08-08 (build session)
    that assumption is wrong for this actual corpus: 4 of the 6 seeded V1
    positions ("fasting", "deliverance from demons and spiritual warfare",
    "how to pray effectively", "the divine exchange at the cross") were
    originally built via a teacher-EXPLICIT ask, so their current row has
    requested_teacher_id set to that teacher's own source_id, not NULL --
    the requested_teacher_id-IS-NULL filter silently missed all four,
    returning None (indistinguishable from "no stored position exists").
    match_stored_position() itself never identifies a specific teacher --
    it is deliberately topic-only phrase matching -- so it has no basis to
    prefer one lineage over another by requested_teacher_id in the first
    place; the only thing that matters here is "does current vetted
    evidence exist for this TOPIC," regardless of how that lineage was
    originally created.

    Confirmed live (build session) that exactly one is_current=true,
    non-retracted row exists per topic_key across the whole table today, so
    dropping the requested_teacher_id filter introduces no ambiguity in
    practice. If a future second lineage for the same topic_key ever goes
    current simultaneously (e.g. a later teacher-explicit ask on a topic
    that currently only has a topic-only lineage, or vice versa), this
    fails safe rather than guessing which one a topic-only match should
    prefer: logs a warning and returns None (falls through to normal RAG),
    the same fail-safe posture stored_position_topics.py already uses for
    its own multi-match refusal.

    Deliberately does NOT filter on status='approved' -- no code anywhere in
    this repo ever sets that value (every stored position is permanently
    'draft' by construction, per the diagnostic's finding), and requiring it
    would make this feature permanently inert. Consistent with Settled
    decision #1 ("no human review gate anywhere on the serving path") and
    with serve_position.py's own existing status filter."""
    result = (
        supabase.table("positions")
        .select("id")
        .eq("topic_key", topic_key)
        .eq("is_current", True)
        .neq("status", "retracted")
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "stored_position_evidence: %d current lineages found for "
            "topic_key=%r (ambiguous -- multiple requested_teacher_id "
            "values are_current simultaneously) -- refusing to guess, "
            "falling through to normal RAG",
            len(rows), topic_key,
        )
        return None
    return rows[0]["id"]


def fetch_stored_position_evidence(supabase, topic_key: str) -> Optional[List[Dict[str, Any]]]:
    """Return the current stored position's evidence propositions for
    `topic_key`, reshaped into chunk-compatible dicts, or None (see module
    docstring for the exhaustive list of None conditions). Never raises --
    every DB call is wrapped; any exception logs and returns None so a fault
    here degrades to normal RAG, never a broken request."""
    try:
        position_id = _current_position_id(supabase, topic_key)
        if not position_id:
            return None

        ev_result = (
            supabase.table("position_evidence")
            .select("proposition_id")
            .eq("position_id", position_id)
            .execute()
        )
        proposition_ids = [row["proposition_id"] for row in (ev_result.data or [])]
        if not proposition_ids:
            return None

        props_result = (
            supabase.table("propositions")
            .select("id, content, document_id, proposition_index")
            .in_("id", proposition_ids)
            .execute()
        )
        propositions = props_result.data or []
        if not propositions:
            return None

        doc_ids = sorted({p["document_id"] for p in propositions if p.get("document_id")})
        if not doc_ids:
            return None
        docs_result = (
            supabase.table("documents")
            .select("id, title, source_id, source_kind, source_type, citation_mode, url, boost_factor")
            .in_("id", doc_ids)
            .execute()
        )
        docs_by_id = {d["id"]: d for d in (docs_result.data or [])}

        source_ids = sorted({
            d["source_id"] for d in docs_by_id.values() if d.get("source_id")
        })
        names_by_source = {}  # type: Dict[str, str]
        if source_ids:
            sources_result = (
                supabase.table("sources").select("id, name").in_("id", source_ids).execute()
            )
            names_by_source = {s["id"]: s["name"] for s in (sources_result.data or [])}

        servable_cache = {}  # type: Dict[str, bool]

        def _servable(source_id: str) -> bool:
            if source_id not in servable_cache:
                servable_cache[source_id] = is_source_servable(supabase, source_id)
            return servable_cache[source_id]

        chunks = []  # type: List[Dict[str, Any]]
        dropped_unservable = 0
        dropped_commentary = 0
        for p in propositions:
            doc = docs_by_id.get(p.get("document_id"))
            if not doc:
                continue
            source_id = doc.get("source_id")
            if not source_id or not _servable(source_id):
                dropped_unservable += 1
                continue
            chunk = {
                "id": p["id"],
                "content": p["content"],
                "document_id": p["document_id"],
                "title": doc.get("title"),
                "author": names_by_source.get(source_id),
                "source_kind": doc.get("source_kind"),
                "source_type": doc.get("source_type"),
                "citation_mode": doc.get("citation_mode"),
                "chunk_index": p.get("proposition_index") or 0,
                "url": doc.get("url"),
                "boost_factor": doc.get("boost_factor") or 1.0,
            }
            if answer_toolbox.is_commentary_chunk(chunk):
                dropped_commentary += 1
                continue
            chunks.append(chunk)

        if dropped_unservable or dropped_commentary:
            logger.info(
                "stored_position_evidence: topic_key=%r position_id=%s dropped "
                "%d unservable + %d commentary of %d total evidence propositions "
                "at live gate time",
                topic_key, position_id, dropped_unservable, dropped_commentary,
                len(propositions),
            )

        if not chunks:
            return None
        return chunks
    except Exception:
        logger.exception(
            "stored_position_evidence: fetch failed for topic_key=%r -- "
            "falling through to normal RAG (fail-safe)",
            topic_key,
        )
        return None
