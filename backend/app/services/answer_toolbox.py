"""Shared answer-path toolbox — retrieval leaf helpers, generation constants,
and background/position-paper support functions used by BOTH backend/app/
routers/chat.py (the legacy synchronous /chat endpoint) and backend/app/
services/async_answers/producer.py (the async answer path). Neither path
owns these; both import from here.

Extracted 2026-08-07 (mirror-unification batch 1) from chat.py, where these
23 names previously lived as top-level definitions that producer.py reached
through `from app.routers import chat as _chat`. That import created a
second live mirror of definitions that belong to neither path -- this module
is the single home. chat.py now imports these names rather than defining
them; nothing here was rewritten, only relocated.

REBOUND-GLOBAL WARNING: _background_topics, _ai, _cohere_client,
_alias_to_topic_key, and _background_topics_loaded are all rebound (not
mutated in place) by their respective loader functions
(_ensure_background_topics / _get_ai / _get_cohere). Any consumer MUST
access these as `answer_toolbox.NAME`, never via
`from answer_toolbox import NAME` -- a from-import captures the value at
import time and goes silently stale the moment the loader next reassigns
the module-level name.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cohere
import httpx
from groq import Groq

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.llm_client import get_guardrails_text
from app.services.position_papers import PILLARS

logger = logging.getLogger(__name__)


def is_word_study_query(question: str) -> bool:
    q = question.lower()
    strongs_pattern = re.compile(r'\b[gh]\d{1,4}\b', re.IGNORECASE)
    if strongs_pattern.search(question):
        return True
    word_study_phrases = [
        "original greek", "original hebrew", "greek word", "hebrew word",
        "root word", "strong's", "strongs", "lexicon", "what does the word",
        "definition of the word", "biblical definition", "greek meaning",
        "hebrew meaning", "word study", "etymology", "transliteration",
        "meaning of", "define "
        # NOTE: bare "what does" was removed here (2026-08-02) — it false-matched
        # ordinary attribution questions like "What does Derek Prince teach about
        # deliverance?", firing an ~8s lexicon RPC and injecting irrelevant
        # lexicon chunks. The specific "what does the word" above still catches
        # genuine word-study intent.
    ]
    return any(phrase in q for phrase in word_study_phrases)


COHERE_API_KEY = os.environ.get("COHERE_API_KEY")


# Source-kind weights applied during RRF fusion (before final ranking).
# Commentary is NOT listed: Settled decision #5 excludes it from answers
# entirely (hard filter in is_commentary_chunk / exclude_commentary_chunks),
# not a soft down-weight. Study Mode still serves commentaries separately.
SOURCE_KIND_FUSION_WEIGHTS = {
    "book": 0.8,
    "lexicon": 0.5,
}


_COMMENTARY_EQUIVALENT_KINDS = frozenset({
    "commentary",
    # Precept Austin's word-study articles (source_kind="word_study",
    # source_type="background") are third-party interpretive material, the
    # same category as commentary -- study.py's CORPUS_SOURCE_KINDS already
    # groups them with commentary as Study-Mode-searchable content. They
    # were never actually caught by the "commentary" check above (found
    # 2026-08-07 live: 33/67 retrieved chunks on an ordinary question were
    # uncaught Precept Austin word_study chunks, several citation_mode=
    # 'citable', reaching the pre-rerank pool). Hard-excluded here, same as
    # commentary, not soft-weighted -- do not add "word_study" to
    # SOURCE_KIND_FUSION_WEIGHTS instead, that would leave it competing for
    # a citable slot rather than removing it.
    "word_study",
})


def is_commentary_chunk(chunk: dict) -> bool:
    """True if this chunk is commentary-equivalent (answer path must never use it).

    Settled product decision #5 (2026-08-01): commentaries are excluded from
    answers; searchable only (Study Mode / dedicated commentary endpoints).
    Checks source_kind first, then source_type — same field order used
    elsewhere on this path.
    """
    sk = chunk.get("source_kind") or chunk.get("source_type") or ""
    return sk in _COMMENTARY_EQUIVALENT_KINDS


def exclude_commentary_chunks(chunks):
    # type: (List[dict]) -> List[dict]
    """Drop every commentary chunk. Idempotent; order-preserving."""
    return [c for c in chunks if not is_commentary_chunk(c)]


_app_dir = Path(__file__).resolve().parent.parent
_system_prompt_text = (_app_dir / "system_prompt.txt").read_text()
ANSWER_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": _system_prompt_text,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": get_guardrails_text(),
        "cache_control": {"type": "ephemeral"},
    },
]


GROQ_MODEL = "llama-3.3-70b-versatile"
RRF_K = 60  # Reciprocal Rank Fusion constant


# Very-high-frequency theological terms that would match most chunks in this corpus
# and cause FTS OR queries to time out. Excluded from OR-fallback token lists.
_FTS_BROAD_TERMS = frozenset({
    "spirit", "spirits", "holy", "god", "lord", "jesus", "christ",
    "church", "christian", "faith", "bible", "scripture", "grace",
    "prayer", "pray", "worship", "salvation", "believe", "truth",
    "spiritual", "spiritual", "divine", "doctrine", "theology",
    # query filler words
    "what", "does", "corpus", "teach", "about", "give", "quotes",
    "from", "the", "say", "says", "how", "when", "where", "who",
    "does", "have", "will", "this", "that", "with", "your", "they",
})


def _or_keywords(text: str) -> Optional[str]:
    """Convert a keyword string to a targeted websearch_to_tsquery OR query.

    Rules:
    - Skip if text already contains ' OR '
    - Keep only tokens that are ≥ 6 chars and not in _FTS_BROAD_TERMS
    - Use up to 3 most specific (longest) tokens to avoid over-broad OR queries
    - Return None if no useful tokens remain

    websearch_to_tsquery('english', 'word1 OR word2') evaluates as word1 | word2.
    """
    if " OR " in text:
        return None
    tokens = [re.sub(r"[^a-zA-Z0-9]", "", t) for t in text.split()]
    tokens = [t for t in tokens if len(t) >= 6 and t.lower() not in _FTS_BROAD_TERMS]
    if not tokens:
        return None
    # Prefer the most specific (longest) tokens
    tokens = sorted(tokens, key=len, reverse=True)[:3]
    return " OR ".join(tokens)


# Pillar metadata lookup (document_id / voice_topic_name) for the fence
# injection below — mirrors position_papers.py's own internal
# _PILLARS_BY_KEY rather than adding new API surface there; PILLARS is
# already a plain, already-imported module-level list.
_PILLAR_BY_KEY = {p["pillar_key"]: p for p in PILLARS}  # type: Dict[str, dict]


# ── Background topics cache ──────────────────────────────────────────
_background_topics: list = []
_alias_to_topic_key: Dict[str, str] = {}  # flat alias → topic_key (first mapping wins)

_background_topics_loaded = False


def _ensure_background_topics():
    """Lazy-load background_topics table into module-level cache on first use."""
    global _background_topics, _background_topics_loaded, _alias_to_topic_key
    if _background_topics_loaded:
        return
    try:
        db = get_supabase()
        result = db.table("background_topics").select("topic_key, document_id, aliases, title").execute()
        _background_topics = result.data or []
        # Build alias lookup dict — first mapping wins; log warning on collision
        alias_map = {}  # type: Dict[str, str]
        for topic in _background_topics:
            for alias in (topic.get("aliases") or []):
                if alias in alias_map:
                    logger.warning(
                        "Alias collision: %r already maps to %r — skipping duplicate for %r",
                        alias, alias_map[alias], topic["topic_key"],
                    )
                else:
                    alias_map[alias] = topic["topic_key"]
        _alias_to_topic_key = alias_map
        _background_topics_loaded = True  # only mark loaded after success
        logger.info("Loaded %d background topics, %d unique aliases", len(_background_topics), len(alias_map))
    except Exception:
        logger.exception("Failed to load background_topics — topic injection disabled")
        _background_topics = []


def match_background_topics(question: str) -> List[str]:
    """Return topic_keys whose aliases appear in the question (max 2)."""
    _ensure_background_topics()
    q = question.lower()
    hit_counts: Dict[str, int] = {}
    for alias, topic_key in _alias_to_topic_key.items():
        if alias in q:
            hit_counts[topic_key] = hit_counts.get(topic_key, 0) + 1
    ranked = sorted(hit_counts.items(), key=lambda x: x[1], reverse=True)
    return [key for key, _ in ranked[:2]]


# ── Module-level client singletons (Change 4) ──────────────────────────

_ai = None


def _get_ai():
    global _ai
    if _ai is None:
        _ai = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _ai


_cohere_client = None


def _get_cohere():
    # type: () -> Optional[cohere.ClientV2]
    global _cohere_client
    if _cohere_client is None and COHERE_API_KEY:
        _cohere_client = cohere.ClientV2(
            api_key=COHERE_API_KEY,
            httpx_client=httpx.Client(http2=False),
        )
    return _cohere_client


def expand_query(question: str) -> Tuple[List[str], Optional[str]]:
    """Ask Llama to rewrite the query into search variants plus FTS keywords.

    Returns (variants, keywords) where:
      - variants = [original_question, paraphrase1, paraphrase2] (original is always index 0)
      - keywords = a space-separated string of distinctive theological terms for FTS routing,
        or None when no keyword routing applies.

    On parse failure, falls back to current behavior: up to 3 paraphrases and keywords=None
    (no keyword routing — callers should run FTS on the full variant).
    """
    try:
        response = _get_ai().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": (
                    "Rewrite the following theological question to improve search retrieval. "
                    "Return ONLY a JSON object with these two fields, no explanation:\n"
                    '  "paraphrases": an array of 2 distinct rephrasings that capture the same '
                    "intent using different phrasings, vocabulary, or angles.\n"
                    '  "keywords": a string of the 3-6 most distinctive theological terms from '
                    "the query, separated by spaces — key terms only, not a sentence "
                    '(e.g. "baptism Holy Spirit tongues gifts").\n\n'
                    f"Question: {question}"
                ),
            }],
        )
    except Exception:
        logger.exception("Query expansion call failed, falling back to original query")
        return [question], None

    raw = (response.choices[0].message.content or "").strip()

    # Parse loosely, tolerating markdown fences or surrounding prose.
    parsed = None  # type: object
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        for pattern in (r"\{.*\}", r"\[.*\]"):
            match = re.search(pattern, raw, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    break
                except json.JSONDecodeError:
                    continue

    # Preferred: structured object with paraphrases + keywords.
    if isinstance(parsed, dict):
        paraphrases = parsed.get("paraphrases")
        keywords = parsed.get("keywords")
        if isinstance(paraphrases, list):
            valid = [p for p in paraphrases if isinstance(p, str) and p.strip()][:2]
            if valid:
                kw = keywords.strip() if isinstance(keywords, str) and keywords.strip() else None
                return [question] + valid, kw

    # Fallback: plain list of paraphrases (old format) — no keyword routing.
    if isinstance(parsed, list):
        valid = [p for p in parsed if isinstance(p, str) and p.strip()][:3]
        if valid:
            return valid, None

    return [question], None


INCLUDE_COPYRIGHTED_ENV = os.environ.get("INCLUDE_COPYRIGHTED", "true").lower() == "true"


FTS_QUERY_MAX_LEN = 300  # Truncate FTS queries to avoid Cloudflare 400s


def hybrid_search_rrf(query, db, vector_k=40, fts_k=30, include_copyrighted=True, precomputed_embedding=None, fts_text=None, run_vector=True, run_fts=True):
    # type: (str, object, int, int, bool, Optional[List[float]], Optional[str], bool, bool) -> Tuple[dict, List[float]]
    """Run vector and/or FTS search and fuse the results with RRF.

    Returns ({chunk_id: (rrf_score, chunk)}, embedding_used).
    Accepts an optional precomputed_embedding to avoid redundant embed calls (Change 2).
    Fires embed_text and FTS in parallel since FTS doesn't need the embedding (Change 5).
    FTS and vector failures are non-fatal — each falls back to empty results.

    When fts_text is provided, FTS runs on it (distinctive keywords) instead of `query`.
    run_vector / run_fts toggle each leg, so the same function serves both vector-only
    variant searches and a single FTS-only keyword search.
    """
    fts_query = (fts_text if fts_text else query)[:FTS_QUERY_MAX_LEN]
    embedding = precomputed_embedding

    with ThreadPoolExecutor(max_workers=2) as ex:
        # Fire FTS immediately — no dependency on embedding
        fts_future = None
        if run_fts:
            fts_future = ex.submit(
                lambda: db.rpc("search_chunks_fts", {
                    "query_text": fts_query,
                    "match_count": fts_k,
                    "include_copyrighted": include_copyrighted,
                }).execute()
            )

        # Vector leg needs an embedding — runs concurrently with FTS
        vector_data = []  # type: list
        if run_vector:
            if embedding is None:
                embedding = embed_text(query)
            try:
                vector_result = db.rpc("match_chunks", {
                    "query_embedding": embedding,
                    "match_count": vector_k,
                    "include_copyrighted": include_copyrighted,
                }).execute()
                vector_data = vector_result.data or []
            except Exception:
                logger.exception("Vector search failed, continuing with FTS only: %s", query[:100])

        # Collect FTS result
        fts_data = []  # type: list
        if fts_future is not None:
            try:
                fts_result = fts_future.result()
                fts_data = fts_result.data or []
            except Exception:
                logger.exception("FTS search failed, continuing with vector only: %s", query[:100])

        # Fix 3: OR-fallback — when AND query returns 0, retry with OR-joined tokens.
        # websearch_to_tsquery already supports "word1 OR word2" syntax natively.
        if run_fts and not fts_data:
            or_query = _or_keywords(fts_query)
            if or_query:
                try:
                    or_result = db.rpc("search_chunks_fts", {
                        "query_text": or_query[:FTS_QUERY_MAX_LEN],
                        "match_count": fts_k,
                        "include_copyrighted": include_copyrighted,
                    }).execute()
                    fts_data = or_result.data or []
                    if fts_data:
                        logger.info("FTS OR-fallback: %d hits for %r", len(fts_data), or_query[:80])
                except Exception:
                    logger.debug("FTS OR-fallback also failed: %s", fts_query[:100])

    scores: Dict[str, Tuple[float, dict]] = {}

    for rank, chunk in enumerate(vector_data):
        cid = chunk["id"]
        score = 1 / (RRF_K + rank)
        if cid not in scores or score > scores[cid][0]:
            scores[cid] = (score, chunk)
        else:
            scores[cid] = (scores[cid][0] + score, scores[cid][1])

    for rank, chunk in enumerate(fts_data):
        cid = chunk["id"]
        score = 1 / (RRF_K + rank)
        if cid in scores:
            scores[cid] = (scores[cid][0] + score, scores[cid][1])
        else:
            scores[cid] = (score, chunk)

    return scores, embedding


def _is_citable(chunk: dict) -> bool:
    """Return True if this chunk should appear in citations."""
    mode = chunk.get("citation_mode")
    if mode:
        return mode == "citable"
    # Fallback for rows without citation_mode
    return chunk.get("source_type") == "sermon"


_NEIGHBOR_SKIP_KINDS = frozenset({"commentary", "lexicon", "word_study"})


def fetch_neighbor_chunks_batch(chunks: List[dict], seen_ids: set, db) -> List[dict]:
    """Fetch ±1 neighbor chunks for all given chunks in a single query.

    Fix 4: commentary and lexicon chunks are skipped — their neighbors don't add useful
    context and would further crowd out citable content.
    """
    # Collect all needed (document_id, chunk_index) pairs
    needed = set()  # type: set
    chunk_parents = {}  # type: Dict[str, dict]  # "doc_id:idx" -> parent chunk
    for c in chunks:
        # Skip neighbor expansion for commentary and lexicon source_kinds
        sk = c.get("source_kind") or c.get("source_type") or ""
        if sk in _NEIGHBOR_SKIP_KINDS:
            continue
        doc_id = c.get("document_id", "")
        idx = c.get("chunk_index", 0)
        for neighbor_idx in [idx - 1, idx + 1]:
            if neighbor_idx < 0:
                continue
            key = "%s:%d" % (doc_id, neighbor_idx)
            needed.add(key)
            chunk_parents[key] = c

    if not needed:
        return []

    # Build OR filter: (doc_id, chunk_index) pairs
    # Supabase REST doesn't support tuple IN, so use .or_() with eq conditions
    or_parts = []
    for key in needed:
        doc_id, idx_str = key.rsplit(":", 1)
        or_parts.append("and(document_id.eq.%s,chunk_index.eq.%s)" % (doc_id, idx_str))

    # Supabase .or_() has URL length limits — batch if needed
    BATCH = 30
    all_neighbors = []  # type: List[dict]
    or_list = list(or_parts)
    for i in range(0, len(or_list), BATCH):
        batch_filter = ",".join(or_list[i:i + BATCH])
        result = db.table("chunks").select("*").or_(batch_filter).execute()
        all_neighbors.extend(result.data or [])

    # Dedupe, skip already-seen, and copy parent metadata
    results = []
    for n in all_neighbors:
        if n["id"] in seen_ids:
            continue
        key = "%s:%d" % (n.get("document_id", ""), n.get("chunk_index", 0))
        parent = chunk_parents.get(key)
        if parent:
            for k in ("title", "author", "source_type", "source_kind", "citation_mode", "url"):
                if k not in n and k in parent:
                    n[k] = parent[k]
        results.append(n)
    return results


_NO_ANSWER_FALLBACK = (
    "I wasn't able to finish composing a complete answer to that. "
    "Please try again, or narrow the question a little."
)
_ATTRIBUTION_REFUSAL = (
    "I started to answer, but I couldn't tie part of it to the sources in my library with "
    "confidence, so I'm holding it back rather than put words in a teacher's mouth. Try "
    "rephrasing, or ask about a specific teacher or passage."
)


def _extract_answer_from_raw(raw_text, stop_reason):
    # type: (str, Optional[str]) -> str
    """Extract the servable <answer> text from a full (buffered) model output,
    preserving the Phase 0 s7a guarantees: never leak reasoning scratchpad, never
    serve a mid-sentence truncation without a clean cutoff note. Returns "" only
    when there is no usable answer (caller serves the clean fallback)."""
    a0 = raw_text.find("<answer>")
    a1 = raw_text.find("</answer>")
    if a0 != -1 and a1 != -1 and a1 > a0:
        return raw_text[a0 + len("<answer>"):a1].strip()
    if a0 != -1:
        # <answer> opened but never closed -- budget cut mid-answer.
        tail = raw_text[a0 + len("<answer>"):]
        rp = tail.find("<reference_mentions>")
        if rp != -1:
            tail = tail[:rp]
        tail = tail.strip()
        if tail and stop_reason == "max_tokens":
            tail += "\n\n_(This answer was cut off before it finished -- ask a follow-up to continue.)_"
        return tail
    # No <answer> block at all.
    if ("<thinking>" in raw_text) or ("<research_analysis>" in raw_text) or not raw_text.strip():
        return ""  # reasoning scratchpad only -- signal caller to serve the clean fallback
    clean = raw_text.strip()
    rp = clean.find("<reference_mentions>")
    if rp != -1:
        clean = clean[:rp].strip()
    return clean


def _ungrounded_reference_teachers(answer, raw_output, grounding, db):
    # type: (str, str, object, object) -> List[str]
    """DECLARED-BLOCK arm of the residual guard: teachers the model CREDITED IN
    THE SERVED PROSE *and* self-reported in its <reference_mentions> block, whose
    material was not retrieved. The prose-scan arm (ungrounded_prose_teachers)
    covers credits the model did NOT declare; both feed the same
    regenerate-once-then-refuse resolution. Kept as the shipped declared arm — it
    still catches a declared surname the full-name-only prose scan skips."""
    from app.services.reference_verifier import (
        parse_reference_mentions, _is_retrieval_grounded, find_occurrences, resolve_alias_source_id,
    )
    from app.services.biblical_figures import is_biblical_figure
    out = []  # type: List[str]
    for p in parse_reference_mentions(raw_output):
        if p["type"] != "teacher":
            continue
        name = p["raw"]
        if is_biblical_figure(name) or not find_occurrences(answer, name):
            continue
        # Shared resolver (fails toward None/ungrounded on error) — one notion of
        # name->source_id, not a fork of the resolution the prose scan uses.
        sid = resolve_alias_source_id(db, name)
        if not _is_retrieval_grounded(name, sid, grounding):
            out.append(name)
    return out
