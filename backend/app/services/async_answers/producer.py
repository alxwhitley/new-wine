"""Produce the SAME verified answer the live /chat path produces -- off-request.

This is the accuracy-critical seam. The launch guarantee (commit 9e5fe94) is
that nothing unverified ever reaches the reader and that a retry re-runs the
check. The producer preserves that by REUSING the live primitives:

  - retrieval leaf helpers imported from app.services.answer_toolbox
    (expand_query, hybrid_search_rrf, Cohere rerank, neighbor expansion,
    lexicon, _is_citable, ...) -- moved out of app.routers.chat 2026-08-07
    (mirror-unification batch 1); chat.py now imports from the same toolbox
    module rather than owning these definitions, so this is no longer a
    dependency on chat.py specifically, just on the shared toolbox both
    paths use.
  - apply_single_teacher_lock / get_paper_body imported directly from their
    real homes (single_teacher_lock.py / position_papers.py) rather than
    transiting through chat.py -- verified no behavior change (nothing
    monkeypatches either via chat.py).
  - exclude_contradicting_teachers is DELIBERATELY reached via the
    `position_paper_exclusion` module attribute (`from app.services import
    position_paper_exclusion`, then
    `position_paper_exclusion.exclude_contradicting_teachers(...)`), not a
    plain `from position_paper_exclusion import exclude_contradicting_teachers`
    -- retargeted 2026-08-07 (mirror-unification batch 4) off
    `app.routers.chat` (deleted this batch; used to be reached as
    `_chat.exclude_contradicting_teachers`). scripts/test_position_paper_fence.py
    monkeypatches `position_paper_exclusion.exclude_contradicting_teachers`
    to construct its everyone-excluded fallback case, and a plain import
    executed fresh per call would silently stop seeing that patch. See
    _retrieve()'s own comment for the proof.
  - the answer extraction imported from answer_toolbox._extract_answer_from_raw
  - the accuracy check imported from reference_verifier (build_retrieval_grounding,
    ungrounded_prose_teachers, verify_references) +
    answer_toolbox._ungrounded_reference_teachers

Two things remain DUPLICATED here rather than imported, because neither is
exposed as a reusable symbol (unchanged by the 2026-08-07 move -- a later
batch's job, not this one):
  1. the retrieval ORCHESTRATION sequence (mirrors chat.chat() ~L754-993)
  2. the generation constants + STRICT ATTRIBUTION CONSTRAINT string
     (mirrors chat._stream_answer)
Both are flagged DRIFT POINTs to unify at the cutover session. Everything
accuracy-bearing (extraction, grounding, verification) is imported, not copied.

Background-topic injection and position-paper (house-voice) interception are
now carried here too (Stage 2) -- see produce()'s own docstring; this module
docstring's earlier "not carried this session" note is stale and describes an
earlier state of this file, not the current one.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.source_filter import get_disabled_filters, is_chunk_disabled
from app.services.llm_client import get_anthropic_client, get_generation_model
from app.services.corpus_version import get_corpus_version
from .config import estimate_cost_usd

logger = logging.getLogger(__name__)

# ---- generation constants (DRIFT POINT: keep in sync with chat._stream_answer) ----
# The model ID is looked up fresh (via get_generation_model(), migration 081,
# cached 60s) at each _generate_and_capture() call below, not a module-level
# constant here -- a module-level snapshot would freeze at import time and
# never see a live model change. GEN_MAX_TOKENS remains hand-synced with
# chat._stream_answer.
GEN_MAX_TOKENS = 8000

# ---- policy versioning for the reuse key -----------------------------------
# prompt_version is a real fingerprint of the exact instruction wording the
# writer sees (system_prompt.txt + guardrails). A wording change busts reuse.
def _compute_prompt_version() -> str:
    app_dir = Path(__file__).resolve().parent.parent.parent  # backend/app
    try:
        sys_txt = (app_dir / "system_prompt.txt").read_text()
    except Exception:
        sys_txt = ""
    try:
        from app.services.llm_client import get_guardrails_text
        guard_txt = get_guardrails_text()
    except Exception:
        guard_txt = ""
    h = hashlib.sha256((sys_txt + "\x00" + guard_txt).encode("utf-8")).hexdigest()
    return "prompt_" + h[:12]


PROMPT_VERSION = _compute_prompt_version()
# policy_version tracks the answer-orchestration version. Bumped to v3 for the
# single-author attribution contract: a pre-v3 cached answer may legitimately
# omit its sole named source, so reusing it would bypass the new retry/label
# guarantee even though the current producer is correct.
POLICY_VERSION = "policy_v3"
# evidence_version is now the REAL shared corpus_version() signal (Stage 2,
# migration 079) -- see app.services.corpus_version. get_corpus_version() is
# cached + fail-safe, so the reuse key gets a real signal and can never raise.


@dataclass
class ProducerResult:
    answer: str
    outcome: str  # answered | refused_attribution | no_material | position_paper | error
    citations: List[Dict[str, Any]] = field(default_factory=list)
    verified_references: List[Dict[str, Any]] = field(default_factory=list)
    retrieved_chunk_ids: List[str] = field(default_factory=list)
    retrieved_point_ids: List[str] = field(default_factory=list)
    model: str = field(default_factory=get_generation_model)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    # Background-topic state to hand back to the client (parity with chat.py's
    # meta["topics_established"]).
    updated_topics: Dict[str, int] = field(default_factory=dict)
    # Quote rail (Project 3, wired 2026-08-06, async path only). IDS ONLY --
    # never quote text -- resolved later at render time via
    # quotes_service.resolve_quote(). See _select_quotes()'s call site below
    # for why this stays empty for the overwhelming majority of answers.
    quote_ids: List[str] = field(default_factory=list)


def current_policy(supabase) -> Dict[str, Any]:
    """The reuse-key inputs under the CURRENT effective policy. Submit paths call
    this to build the enqueue key; the producer regenerates under current filters
    at run time (documented cache-staleness tradeoff at zero users)."""
    from app.services import answer_toolbox
    from app.services.quotes import quote_selection_enabled
    filters = get_disabled_filters()
    include_copyrighted = bool(filters["include_copyrighted"]) and answer_toolbox.INCLUDE_COPYRIGHTED_ENV
    # Quote attachment changes the delivered answer payload, so durable reuse
    # and single-flight identity must change with the effective gate state.
    quote_policy = "true" if quote_selection_enabled() else "false"
    snapshot = {
        "source_kinds": sorted(filters.get("source_kinds") or []),
        "source_names": sorted(filters.get("source_names") or []),
        "include_copyrighted": include_copyrighted,
    }
    return {
        "filters": snapshot,
        "evidence_version": get_corpus_version(supabase),  # real shared signal (mig 079)
        "prompt_version": PROMPT_VERSION,
        "policy_version": "%s:quote_selection=%s" % (POLICY_VERSION, quote_policy),
    }


def _missing_required_single_author(answer: str, permitted_names: List[str]) -> bool:
    """Return True only when exactly one citable author exists and the
    answer omits that full name.

    This is a product-attribution requirement, not a claim-grounding check:
    the existing verifier still decides whether any name that does appear is
    actually grounded. Multi-author and genuinely anonymous evidence retain
    their existing behavior because choosing one display name for them would
    add a new editorial decision.
    """
    names = sorted({name.strip() for name in permitted_names if name and name.strip()})
    if len(names) != 1:
        return False
    pattern = r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(names[0])
    return re.search(pattern, answer or "", flags=re.IGNORECASE) is None


def _ensure_single_author_label(answer: str, permitted_names: List[str]) -> str:
    """Deterministically expose the sole citable source after a writer retry.

    The label describes the source voice; it does not rewrite or attribute an
    individual generated sentence. It is added before reference verification,
    so the existing grounding/link machinery validates the inserted name too.
    """
    names = sorted({name.strip() for name in permitted_names if name and name.strip()})
    if len(names) != 1 or not _missing_required_single_author(answer, names):
        return answer
    return "**Source voice: %s**\n\n%s" % (names[0], answer)


# ---- retrieval (MIRROR of chat.chat() ~L754-993; DRIFT POINT) ---------------
def _retrieve(db, question, injected_doc_ids=None, matched_pillar_key=None):
    # type: (object, str, Optional[set], Optional[str]) -> Tuple[List[dict], List[dict], int, bool]
    # Shared retrieval leaf helpers now live in answer_toolbox.py (moved from
    # chat.py 2026-08-07, mirror-unification batch 1) -- neither this module
    # nor chat.py owns them; both import from the toolbox. Of the 3 names
    # that did NOT move: apply_single_teacher_lock and get_paper_body are
    # imported directly from their real homes below (single_teacher_lock.py /
    # position_papers.py) -- verified no behavior change, nothing in the repo
    # monkeypatches either of them via chat.py.
    #
    # exclude_contradicting_teachers is DELIBERATELY reached via the
    # `position_paper_exclusion` module attribute, NOT a plain `from
    # position_paper_exclusion import exclude_contradicting_teachers` --
    # retargeted 2026-08-07 (mirror-unification batch 4) off the deleted
    # `from app.routers import chat as _chat` (chat.py no longer exists).
    # Confirmed live during this same batch that
    # scripts/test_position_paper_fence.py's fallback-case test
    # monkeypatches `position_paper_exclusion.exclude_contradicting_teachers`
    # (see that script's docstring), and a plain `from position_paper_exclusion
    # import exclude_contradicting_teachers` executed fresh inside this
    # function on every call would bind to the REAL function each time,
    # silently missing that patch (proven:
    # `position_paper_exclusion.exclude_contradicting_teachers is fake` ->
    # True, but a fresh plain import's identity -> False). Plain-importing
    # this one name would be a real behavior change, not just a
    # dependency-hop reduction -- so it stays as a module-attribute access.
    from app.services import answer_toolbox
    from app.services.single_teacher_lock import apply_single_teacher_lock
    from app.services.position_papers import get_paper_body
    from app.services import position_paper_exclusion

    filters = get_disabled_filters()
    include_copyrighted = bool(filters["include_copyrighted"]) and answer_toolbox.INCLUDE_COPYRIGHTED_ENV

    variants, keywords = answer_toolbox.expand_query(question)
    variant_weights = [1.0, 0.7, 0.7]
    FTS_WEIGHT = 1.0

    all_scores = {}  # type: Dict[str, Tuple[float, dict]]

    def _merge(scores, weight):
        for cid, (score, chunk) in scores.items():
            weighted = score * weight
            if cid in all_scores:
                all_scores[cid] = (all_scores[cid][0] + weighted, all_scores[cid][1])
            else:
                all_scores[cid] = (weighted, chunk)

    first_embedding = None  # type: Optional[List[float]]
    with ThreadPoolExecutor(max_workers=4) as ex:
        if keywords:
            variant_futures = [
                ex.submit(answer_toolbox.hybrid_search_rrf, variant, db,
                          include_copyrighted=include_copyrighted, run_fts=False)
                for variant in variants
            ]
            fts_future = ex.submit(answer_toolbox.hybrid_search_rrf, keywords, db,
                                   include_copyrighted=include_copyrighted, run_vector=False)
            for i, future in enumerate(variant_futures):
                weight = variant_weights[i] if i < len(variant_weights) else 0.5
                variant_scores, embedding = future.result()
                if i == 0:
                    first_embedding = embedding
                _merge(variant_scores, weight)
            fts_scores, _ = fts_future.result()
            _merge(fts_scores, FTS_WEIGHT)
        else:
            futures = [
                ex.submit(answer_toolbox.hybrid_search_rrf, variant, db, include_copyrighted=include_copyrighted)
                for variant in variants
            ]
            for i, future in enumerate(futures):
                weight = variant_weights[i] if i < len(variant_weights) else 0.5
                variant_scores, embedding = future.result()
                if i == 0:
                    first_embedding = embedding
                _merge(variant_scores, weight)

    # Filter disabled source_kinds / source_names.
    all_scores = {
        cid: (score, chunk)
        for cid, (score, chunk) in all_scores.items()
        if not is_chunk_disabled(chunk, filters)
    }

    # Hard-exclude commentary from the answer bag (Settled decision #5) --
    # MIRROR of chat.chat() Step 2.6. Must run before collapse/rerank.
    pre_commentary = len(all_scores)
    all_scores = {
        cid: (score, chunk)
        for cid, (score, chunk) in all_scores.items()
        if not answer_toolbox.is_commentary_chunk(chunk)
    }
    dropped_commentary = pre_commentary - len(all_scores)
    if dropped_commentary:
        logger.info(
            "Excluded %d commentary chunk(s) from answer retrieval (producer, decision #5)",
            dropped_commentary,
        )

    # Remove chunks from injected background-topic papers (chat.py Fix 6) -- they
    # are already in topic_context_parts, so keeping them in the main pool would
    # duplicate content and waste citable slots.
    if injected_doc_ids:
        all_scores = {
            cid: (score, chunk)
            for cid, (score, chunk) in all_scores.items()
            if chunk.get("document_id") not in injected_doc_ids
        }

    # boost_factor + source-kind fusion weights.
    all_scores = {
        cid: (
            score
            * (chunk.get("boost_factor") or 1.0)
            * answer_toolbox.SOURCE_KIND_FUSION_WEIGHTS.get(
                chunk.get("source_kind") or chunk.get("source_type") or "", 1.0
            ),
            chunk,
        )
        for cid, (score, chunk) in all_scores.items()
    }

    # Document-level collapse -- max 2 chunks per document.
    ranked = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)
    doc_counts = {}  # type: Dict[str, int]
    collapsed = []
    for cid, (score, chunk) in ranked:
        did = chunk.get("document_id", "")
        doc_counts[did] = doc_counts.get(did, 0) + 1
        if doc_counts[did] <= 2:
            collapsed.append((cid, (score, chunk)))

    # Single-teacher lock (Project 2 phase 1 step 2, CLAUDE.md #15) --
    # MIRROR of chat.chat()'s Step 3a; DRIFT POINT, imported not copied
    # (calls apply_single_teacher_lock directly, imported from its real home
    # single_teacher_lock.py -- same function chat.py calls) so this and
    # chat.py can never independently drift on the lock decision itself.
    locked_chunks, locked = apply_single_teacher_lock(question, collapsed, db)
    if locked:
        # Per-author cap skipped, not reapplied -- moot once already
        # restricted to one teacher (see single_teacher_lock.py).
        author_capped = locked_chunks
    else:
        # Per-author cap -- max 3 chunks per author.
        author_counts = {}  # type: Dict[str, int]
        author_capped = []
        for cid, (score, chunk) in collapsed:
            author = chunk.get("author") or "Unknown"
            author_counts[author] = author_counts.get(author, 0) + 1
            if author_counts[author] <= 3:
                author_capped.append((cid, (score, chunk)))

    top_chunks = author_capped[:30]
    chunks = [chunk for _, (_, chunk) in top_chunks]

    # Cohere rerank -- 30 -> 8.
    co = answer_toolbox._get_cohere()
    if co and len(chunks) > 0:
        try:
            docs = [c.get("content", "") for c in chunks]
            rerank_result = co.rerank(model="rerank-v3.5", query=question, documents=docs, top_n=8)
            chunks = [chunks[r.index] for r in rerank_result.results]
        except Exception:
            logger.exception("Cohere rerank failed (producer), using RRF top 8")
            chunks = chunks[:8]

    citable_count = sum(1 for c in chunks if answer_toolbox._is_citable(c))

    # Neighbor expansion, cap 12.
    seen_ids = {c["id"] for c in chunks}
    neighbors = answer_toolbox.fetch_neighbor_chunks_batch(chunks, seen_ids, db)
    expanded = list(chunks)
    for n in neighbors:
        if len(expanded) >= 12:
            break
        seen_ids.add(n["id"])
        expanded.append(n)

    # Defense-in-depth: decision #5 hard exclude after neighbor expansion
    # (primary gate is Step 2.6 above). Mirrors chat.chat().
    chunks = answer_toolbox.exclude_commentary_chunks(expanded)

    # House-position exclusion -- MIRROR of the deleted chat.py's former
    # Step 4.5; DRIFT POINT. get_paper_body is imported directly from its
    # real home (position_papers.py); exclude_contradicting_teachers is
    # called via position_paper_exclusion.exclude_contradicting_teachers on
    # purpose -- retargeted 2026-08-07 (mirror-unification batch 4) off
    # `_chat.exclude_contradicting_teachers`, see this function's own header
    # comment for why it stays a module-attribute call rather than a plain
    # import. Full reasoning (Alex's ruling, 2026-08-06, CLAUDE.md Settled
    # decision #9) unchanged by the retarget.
    fallback_to_paper_voice = False
    if matched_pillar_key and chunks:
        house_position_text = get_paper_body(matched_pillar_key)
        if house_position_text:
            chunks, excluded_authors = position_paper_exclusion.exclude_contradicting_teachers(
                matched_pillar_key, house_position_text, question, chunks,
            )
            if excluded_authors and not chunks:
                fallback_to_paper_voice = True

    # Conditional lexicon retrieval (word-study questions).
    if answer_toolbox.is_word_study_query(question):
        try:
            from app.services.embeddings import embed_text
            lex_embedding = first_embedding if first_embedding else embed_text(question)
            lex_result = db.rpc("match_lexicon_chunks", {
                "query_embedding": lex_embedding, "match_count": 5,
            }).execute()
            if lex_result.data:
                for lc in lex_result.data:
                    lc["_lexicon"] = True
                chunks.extend(lex_result.data)
        except Exception:
            logger.exception("Lexicon retrieval failed (producer), continuing without")

    citations = [
        {
            "chunk_id": c["id"],
            "document_title": c.get("title"),
            "author": c.get("author"),
            "content": c["content"],
            "url": c.get("url"),
        }
        for c in chunks
        if answer_toolbox._is_citable(c)
    ]
    return chunks, citations, citable_count, fallback_to_paper_voice


def _build_context(chunks, citable_count, topic_context_parts=None):
    # type: (List[dict], int, Optional[List[str]]) -> str
    from app.services import answer_toolbox
    regular = [c for c in chunks if not c.get("_lexicon")]
    lexicon = [c for c in chunks if c.get("_lexicon")]

    context_parts = []
    source_num = 0
    for i, c in enumerate(regular):
        if answer_toolbox._is_citable(c):
            source_num += 1
            label = "[Source %d]" % source_num
        else:
            label = "[Background]"
        context_parts.append(
            "%s (source_kind=%s, citation_mode=%s) \"%s\" by %s, chunk %s\n%s" % (
                label,
                c.get("source_kind") or c.get("source_type", "unknown"),
                c.get("citation_mode", "citable"),
                c.get("title", "Unknown"),
                c.get("author", "Unknown"),
                c.get("chunk_index", i),
                c["content"],
            )
        )
    context = "\n\n---\n\n".join(context_parts)

    # Prepend injected background-topic papers (chat.py generate() L1035-1037).
    if topic_context_parts:
        topic_block = "\n\n---\n\n".join(topic_context_parts)
        context = topic_block + "\n\n---\n\n" + context

    # Graceful-degradation hint -- only when citable sources are thin AND there is
    # no background paper carrying the topic (matches chat.py L1041).
    if citable_count < 2 and not topic_context_parts:
        context += (
            "\n\n[Retrieval note: citable sources on this topic are thin or absent. "
            "The strongest available material is background-only. "
            "Follow the graceful degradation rules in your instructions.]"
        )

    if lexicon:
        lex_context = "\n\n---\n\n".join("[Lexicon] %s" % c["content"] for c in lexicon)
        context += "\n\n--- LEXICON CONTEXT (silent_context -- do not cite by name) ---\n\n" + lex_context

    return context


def _build_history(messages: List[Dict[str, Any]], context: str, question: str) -> List[Dict[str, str]]:
    history = []  # type: List[Dict[str, str]]
    recent = messages[-6:] if len(messages) > 6 else messages
    for msg in recent:
        role = msg.get("role")
        if role in ("user", "assistant"):
            history.append({"role": role, "content": msg.get("content", "")})
    history.append({
        "role": "user",
        "content": "Sources:\n%s\n\nQuestion: %s" % (context, question),
    })
    return history


# ---- generation with usage capture (MIRROR of chat._stream_answer; DRIFT POINT) --
def _generate_and_capture(history, permitted_names=None):
    from app.services import answer_toolbox
    system = answer_toolbox.ANSWER_SYSTEM_BLOCKS
    if permitted_names is not None:
        unique_names = sorted({name.strip() for name in permitted_names if name and name.strip()})
        names = ", ".join(unique_names) if unique_names else "(no teachers were retrieved -- attribute to no one)"
        constraint = (
            "STRICT ATTRIBUTION CONSTRAINT (this answer only): you may attribute a claim BY NAME "
            "ONLY to these teachers, whose material was actually retrieved for this question: "
            + names + ". Do NOT name, cite, or attribute any point to any other teacher, author, "
            "commentator, or ministry -- not even in passing. If a point cannot be attributed to a "
            "permitted name, state it without attribution. This overrides any inclination to add "
            "other voices for balance."
        )
        if len(unique_names) == 1:
            constraint += (
                " Because this answer has exactly one named citable source, you MUST identify "
                + unique_names[0]
                + " by full name at least once in the answer."
            )
        system = list(answer_toolbox.ANSWER_SYSTEM_BLOCKS) + [{"type": "text", "text": constraint}]

    client = get_anthropic_client()
    model_used = get_generation_model()
    raw_full = []  # type: List[str]
    stop_reason = None
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}

    stream = client.messages.create(
        model=model_used, max_tokens=GEN_MAX_TOKENS, thinking={"type": "disabled"}, system=system, messages=history, stream=True,
    )
    for ev in stream:
        if ev.type == "message_start":
            u = getattr(getattr(ev, "message", None), "usage", None)
            if u is not None:
                usage["input_tokens"] = getattr(u, "input_tokens", 0) or 0
                usage["cache_read_tokens"] = getattr(u, "cache_read_input_tokens", 0) or 0
                usage["cache_write_tokens"] = getattr(u, "cache_creation_input_tokens", 0) or 0
        elif ev.type == "content_block_delta" and hasattr(ev.delta, "text"):
            raw_full.append(ev.delta.text)
        elif ev.type == "message_delta":
            d = getattr(ev, "delta", None)
            sr = getattr(d, "stop_reason", None)
            if sr:
                stop_reason = sr
            u = getattr(ev, "usage", None)
            out = getattr(u, "output_tokens", None) if u is not None else None
            if out is not None:
                usage["output_tokens"] = out

    raw_output = "".join(raw_full)
    answer = answer_toolbox._extract_answer_from_raw(raw_output, stop_reason) or answer_toolbox._NO_ANSWER_FALLBACK
    return answer, raw_output, stop_reason, usage, model_used


def _add_usage(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
    return {k: int(a.get(k, 0)) + int(b.get(k, 0)) for k in
            ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")}


def _inject_background_topics(db, question, messages, topics_established):
    # type: (object, str, List[Dict[str, Any]], Dict[str, int]) -> Tuple[List[str], set, Dict[str, int]]
    """Background-topic context injection -- MIRROR of chat.chat() Step 0.5
    (~L758-816). Returns (topic_context_parts, injected_doc_ids, updated_topics).
    Same 6-turn inject/condense window and the same [Background] labelling."""
    from app.services import answer_toolbox
    answer_toolbox._ensure_background_topics()
    current_turn = len(messages)
    matched_topics = answer_toolbox.match_background_topics(question)
    topics_to_inject = []    # type: List[str]  # full paper this turn
    topics_to_condense = []  # type: List[str]  # first chunk only (within 6-turn window)
    for topic_key in matched_topics:
        injection_turn = (topics_established or {}).get(topic_key, -99)
        if current_turn - injection_turn > 6:
            topics_to_inject.append(topic_key)
        else:
            topics_to_condense.append(topic_key)

    topic_context_parts = []  # type: List[str]
    injected_doc_ids = set()  # type: set
    updated_topics = dict(topics_established or {})
    if topics_to_inject or topics_to_condense:
        # answer_toolbox._background_topics is REBOUND (not mutated in place)
        # by _ensure_background_topics() above -- accessed via module
        # attribute, never a `from`-import, so this always reads the freshly
        # loaded value (see answer_toolbox.py's REBOUND-GLOBAL warning).
        topic_lookup = {t["topic_key"]: t for t in answer_toolbox._background_topics}

        # License/visibility gate (Invariant 2 / is_source_servable) --
        # background_topics rows carry no source_id of their own
        # (answer_toolbox._ensure_background_topics only selects topic_key/
        # document_id/aliases/title), so it's resolved here via the same
        # batched documents->source_id lookup single_teacher_lock.py already
        # exposes publicly for exactly this kind of reuse, rather than
        # forking a second document_id->source_id query. A topic whose
        # document cannot be resolved to a currently-servable source is
        # silently skipped -- same fail-closed posture as every other
        # consumer of this gate (get_teacher_card, reference_verifier,
        # stored_position_evidence).
        from app.services.source_resolver import is_source_servable
        from app.services.single_teacher_lock import resolve_source_ids_for_documents
        candidate_doc_ids = [
            topic_lookup[k]["document_id"] for k in (topics_to_inject + topics_to_condense)
            if k in topic_lookup
        ]
        doc_to_source = resolve_source_ids_for_documents(db, candidate_doc_ids)
        servable_cache = {}  # type: Dict[str, bool]

        def _topic_servable(topic):
            source_id = doc_to_source.get(topic["document_id"])
            if not source_id:
                return False
            if source_id not in servable_cache:
                servable_cache[source_id] = is_source_servable(db, source_id)
            return servable_cache[source_id]

        for topic_key in topics_to_inject:
            topic = topic_lookup.get(topic_key)
            if not topic or not _topic_servable(topic):
                continue
            try:
                chunk_result = db.table("chunks").select("content").eq(
                    "document_id", topic["document_id"]).order("chunk_index").execute()
                if chunk_result.data:
                    full_text = "\n\n".join(c["content"] for c in chunk_result.data)
                    topic_context_parts.append(
                        "[Background] (citation_mode=silent_context) \"%s\"\n%s" % (topic["title"], full_text))
                    injected_doc_ids.add(topic["document_id"])
                    updated_topics[topic_key] = current_turn
            except Exception:
                logger.exception("Producer failed to fetch chunks for topic %s", topic_key)
        for topic_key in topics_to_condense:
            topic = topic_lookup.get(topic_key)
            if not topic or not _topic_servable(topic):
                continue
            try:
                chunk_result = db.table("chunks").select("content").eq(
                    "document_id", topic["document_id"]).order("chunk_index").limit(1).execute()
                if chunk_result.data:
                    first_chunk = chunk_result.data[0]["content"]
                    topic_context_parts.append(
                        "[Background] (citation_mode=silent_context) \"%s\"\n%s" % (topic["title"], first_chunk))
                    injected_doc_ids.add(topic["document_id"])
            except Exception:
                logger.exception("Producer failed to fetch condensed chunk for topic %s", topic_key)
    return topic_context_parts, injected_doc_ids, updated_topics


def produce(supabase, question, messages=None, topics_established=None):
    # type: (object, str, Optional[List[Dict[str, Any]]], Optional[Dict[str, int]]) -> ProducerResult
    """Position-paper interception -> background-topic injection -> retrieve ->
    buffered generation -> ungrounded-attribution resolution (regenerate-once-
    then-refuse) -> verify_references. Matches chat.py's ordering exactly. Raises
    only on an unexpected fault the worker should retry."""
    from app.services import answer_toolbox
    from app.services.reference_verifier import (
        verify_references, build_retrieval_grounding, build_name_universe, ungrounded_prose_teachers,
    )
    from app.services.position_papers import match_position_paper, render_paper_voice_with_disclaimer, get_paper_body
    from app.services.stored_position_topics import match_stored_position
    from app.services.stored_position_evidence import fetch_stored_position_evidence
    messages = messages or []
    topics_established = topics_established or {}

    # Position-paper match (Alex's ruling, 2026-08-06 -- MIRROR of
    # chat.chat()'s matched_pillar_key comment; DRIFT POINT). A position
    # paper is constraining silent context, never a served answer: retrieval
    # below runs completely normally on a match, same as a non-match. See
    # position_papers.py's module docstring for the full architecture.
    matched_pillar_key = match_position_paper(question)

    # Stored-position evidence injection (Project 2 "one-hop", PLAN.md Phase 3
    # item 5; CLAUDE.md Settled decision #18) -- a materially different
    # mechanism from the position-paper fence above: a paper bounds the
    # answer as silent context; a matched stored position instead NARROWS
    # what evidence reaches the writer, replacing normal retrieval's chunk
    # set with the position's own vetted propositions, still run through the
    # exact same generation/verification pipeline below with real citations.
    # Never both at once -- a position-paper match (semantic, independent
    # mechanism) takes precedence if it somehow also fires for the same
    # question; match_stored_position() already independently excludes
    # debate topics (decision #11) and paper-fenced topics (baptism/tongues)
    # by construction, so overlap is not expected in practice, but this
    # ordering makes the precedence explicit rather than accidental.
    matched_topic_key = None if matched_pillar_key else match_stored_position(question)
    stored_evidence_chunks = (
        fetch_stored_position_evidence(supabase, matched_topic_key)
        if matched_topic_key else None
    )

    # Background-topic injection (chat.py Step 0.5).
    topic_context_parts, injected_doc_ids, updated_topics = _inject_background_topics(
        supabase, question, messages, topics_established)

    # Position-paper fence injection -- MIRROR of chat.chat()'s Step 0.6.
    # _PILLAR_BY_KEY is not itself rebound, but accessed via the module
    # (answer_toolbox._PILLAR_BY_KEY) for the same consistent-access reason
    # chat.py now uses -- see answer_toolbox.py's REBOUND-GLOBAL warning.
    if matched_pillar_key:
        pillar = answer_toolbox._PILLAR_BY_KEY.get(matched_pillar_key)
        if pillar and pillar["document_id"] not in injected_doc_ids:
            paper_body = get_paper_body(matched_pillar_key)
            if paper_body:
                topic_context_parts.append(
                    "[House Position] (citation_mode=silent_context) This is "
                    "Rhemata's own settled house position on %s. It bounds what "
                    "this answer may claim — do not state anything that "
                    "contradicts it. Never cite, name, quote, or copy its exact "
                    "wording into your answer.\n\n%s" % (pillar["voice_topic_name"], paper_body)
                )
                injected_doc_ids.add(pillar["document_id"])

    if stored_evidence_chunks:
        # Narrowed evidence path: skip normal _retrieve() entirely. Every
        # chunk here already passed the live license/visibility gate and the
        # commentary/word_study exclusion inside
        # fetch_stored_position_evidence(); everything else below (context
        # building, grounding, generation, the attribution guard,
        # verify_references, quote selection) is completely unchanged and
        # does not know or care that these chunks came from stored evidence
        # rather than live retrieval.
        chunks = stored_evidence_chunks
        citable_count = sum(1 for c in chunks if answer_toolbox._is_citable(c))
        citations = [
            {
                "chunk_id": c["id"],
                "document_title": c.get("title"),
                "author": c.get("author"),
                "content": c["content"],
                "url": c.get("url"),
            }
            for c in chunks
            if answer_toolbox._is_citable(c)
        ]
        fallback_to_paper_voice = False
        logger.info(
            "stored_position_topics: injecting stored evidence | topic_key=%r "
            "| evidence_count=%d",
            matched_topic_key, len(chunks),
        )
    else:
        chunks, citations, citable_count, fallback_to_paper_voice = _retrieve(
            supabase, question, injected_doc_ids, matched_pillar_key,
        )

    # Sanctioned No-Oracle-Rule fallback -- MIRROR of chat.chat()'s generate()
    # fallback_to_paper_voice branch. Fires ONLY when exclusion emptied a
    # non-empty retrieval; never for thin/empty retrieval, never on no match.
    if fallback_to_paper_voice:
        answer = render_paper_voice_with_disclaimer(matched_pillar_key, question, messages)
        if not answer:
            answer = answer_toolbox._NO_ANSWER_FALLBACK
        logger.info(
            "position_paper_exclusion: FALLBACK fired (producer) | pillar=%s | question=%r",
            matched_pillar_key, question,
        )
        return ProducerResult(
            answer=answer, outcome="position_paper", citations=[], verified_references=[],
            model="position_paper",
            # render_paper_voice_with_disclaimer does not expose token usage --
            # same measured house-voice median used before, so the spend
            # ceiling isn't blind to this rare fallback either.
            cost_usd=0.015,
            updated_topics=dict(topics_established),
        )

    # truly_empty short-circuit (chat.py generate() L1008): nothing to answer from.
    if not chunks and not topic_context_parts:
        return ProducerResult(
            answer="I don't have strong material on that topic in my current library.",
            outcome="no_material", updated_topics=updated_topics,
        )

    context = _build_context(chunks, citable_count, topic_context_parts)
    history = _build_history(messages, context, question)

    grounding = build_retrieval_grounding(chunks, supabase)
    permitted_names = sorted({
        (c.get("author") or "").strip() for c in chunks
        if answer_toolbox._is_citable(c) and (c.get("author") or "").strip()
    })

    answer, raw_output, _sr, usage, model_used = _generate_and_capture(history)
    total_usage = dict(usage)

    refused = False
    try:
        name_universe = build_name_universe(supabase)

        def _has_ungrounded(ans, raw):
            if answer_toolbox._ungrounded_reference_teachers(ans, raw, grounding, supabase):
                return True
            if ungrounded_prose_teachers(ans, name_universe, grounding, supabase):
                return True
            return False

        needs_single_author = _missing_required_single_author(answer, permitted_names)
        if _has_ungrounded(answer, raw_output) or needs_single_author:
            answer2, raw2, _sr2, usage2, model_used = _generate_and_capture(history, permitted_names=permitted_names)
            total_usage = _add_usage(total_usage, usage2)
            if _has_ungrounded(answer2, raw2):
                logger.warning("Producer regeneration still credits an ungrounded teacher -- clean refusal")
                answer, raw_output, refused = answer_toolbox._ATTRIBUTION_REFUSAL, "", True
            else:
                answer, raw_output = answer2, raw2
                if _missing_required_single_author(answer, permitted_names):
                    logger.warning(
                        "Producer regeneration omitted the sole citable author -- adding deterministic source label"
                    )
                    answer = _ensure_single_author_label(answer, permitted_names)
    except Exception:
        logger.exception("Producer attribution-resolution failed -- refusing cleanly (fail closed)")
        answer, raw_output, refused = answer_toolbox._ATTRIBUTION_REFUSAL, "", True

    try:
        verified_references = [] if refused else verify_references(answer, raw_output, supabase, grounding)
    except Exception:
        logger.exception("Producer SP1 reference verification failed -- continuing without pointers")
        verified_references = []

    # Quote selection is disabled by default while inherited topic labels are
    # repaired. Existing quote rows stay untouched; the selector remains
    # available behind this explicit opt-in for the attended re-enablement
    # gate.
    #
    # Runs post-generation, after verify_references, and only on a non-
    # refused answer (an attribution refusal already empties citations
    # above; pairing a quote beside a refusal would be the same
    # misattribution-by-juxtaposition risk in a different shape). Fail-soft:
    # any fault here -- embedding API, DB -- must never affect answer
    # delivery, so it's wrapped and swallowed here, not left to
    # select_quotes_for_answer() itself (which does not swallow its own
    # errors; see its docstring).
    quote_ids = []  # type: List[str]
    if not refused:
        try:
            from app.services.quotes import quote_selection_enabled
            if quote_selection_enabled():
                from app.services.quotes import select_quotes_for_answer
                from app.services.single_teacher_lock import resolve_source_ids_for_documents
                considered_doc_ids = [c.get("document_id") for c in chunks if c.get("document_id")]
                doc_to_source = resolve_source_ids_for_documents(supabase, considered_doc_ids)
                quote_ids = select_quotes_for_answer(supabase, question, doc_to_source.values())
        except Exception:
            logger.exception("Producer quote-rail selection failed -- continuing without quotes")
            quote_ids = []

    cost = estimate_cost_usd(
        total_usage["input_tokens"], total_usage["output_tokens"],
        total_usage["cache_read_tokens"], total_usage["cache_write_tokens"],
    )
    # "Points" == retrieved chunks on the current answer path (propositions are
    # the separate position layer, not the chat path). Record both the full
    # retrieved set and the citable subset for Phase-4 traceability.
    retrieved_chunk_ids = [c["id"] for c in chunks]
    retrieved_point_ids = [c["id"] for c in chunks if answer_toolbox._is_citable(c)]

    return ProducerResult(
        answer=answer,
        outcome="refused_attribution" if refused else "answered",
        citations=[] if refused else citations,
        verified_references=verified_references,
        quote_ids=quote_ids,
        retrieved_chunk_ids=retrieved_chunk_ids,
        retrieved_point_ids=retrieved_point_ids,
        model=model_used,
        input_tokens=total_usage["input_tokens"],
        output_tokens=total_usage["output_tokens"],
        cache_read_tokens=total_usage["cache_read_tokens"],
        cache_write_tokens=total_usage["cache_write_tokens"],
        cost_usd=cost,
        updated_topics=updated_topics,
    )
