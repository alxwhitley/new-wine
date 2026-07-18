from __future__ import annotations

import datetime
import json
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cohere
import httpx
from groq import Groq
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.auth import get_optional_user
from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.source_filter import get_disabled_filters, is_chunk_disabled
from app.services.llm_client import get_anthropic_client, get_guardrails_text


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
        "what does", "meaning of", "define "
    ]
    return any(phrase in q for phrase in word_study_phrases)

COHERE_API_KEY = os.environ.get("COHERE_API_KEY")

logger = logging.getLogger(__name__)

# Fix 4: source-kind weights applied during RRF fusion (before final ranking)
SOURCE_KIND_FUSION_WEIGHTS = {
    "commentary": 0.6,
    "book": 0.8,
    "lexicon": 0.5,
}
COMMENTARY_CONTEXT_CAP = 3  # max commentary chunks in the final assembled context

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

router = APIRouter()

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


_NEIGHBOR_SKIP_KINDS = frozenset({"commentary", "lexicon"})


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


class ChatMessage(BaseModel):
    role: str
    content: str


GUEST_QUERY_LIMIT = 6
# weekly_limit is stored per-user in user_usage.weekly_limit (migration 039).
# No hardcoded constant here — Phase 2 billing raises the limit per subscription tier.


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    messages: List[ChatMessage] = []
    anon_id: Optional[str] = None
    topics_established: Optional[Dict[str, int]] = {}

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty")
        if len(v) > 1000:
            raise ValueError("question must be 1000 characters or fewer")
        return v


def _save_conversation(
    db, user_id: str, conversation_id: str, is_new: bool,
    question: str, answer: str, message_id: str,
) -> None:
    """Save the exchange to Supabase. Accepts pre-generated IDs for background use."""
    try:
        if is_new:
            title = " ".join(question.split()[:6])
            logger.info("Creating new conversation %s for user %s: %r", conversation_id, user_id, title)
            result = db.table("conversations").insert({
                "id": conversation_id,
                "user_id": user_id,
                "title": title,
            }).execute()
            logger.info("Conversation insert result: %d row(s)", len(result.data) if result.data else 0)
        else:
            logger.info("Appending to existing conversation %s for user %s", conversation_id, user_id)

        result = db.table("messages").insert([
            {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "role": "user",
                "content": question,
            },
            {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": answer,
            },
        ]).execute()
        logger.info("Messages insert result: %d row(s) for conversation %s", len(result.data) if result.data else 0, conversation_id)
    except Exception:
        logger.exception("Failed to save conversation %s for user %s", conversation_id, user_id)


def _sse(data: str) -> str:
    return f"data: {data}\n\n"


def _get_client_ip(http_request: Request) -> Optional[str]:
    """Real client IP behind Railway's edge proxy. Uvicorn is not run with
    --proxy-headers, so http_request.client.host is Railway's internal proxy
    address, not the real client -- read X-Forwarded-For instead (set by
    Railway's edge; the leftmost entry is the original client)."""
    xff = http_request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return http_request.client.host if http_request.client else None


@router.post("")
async def chat(request: ChatRequest, http_request: Request, user_id: Optional[str] = Depends(get_optional_user)):
    db = get_supabase()

    # Captured here so generate() can include it in the final SSE meta event.
    user_usage_meta = {}  # type: dict

    # Query limit checks
    if not user_id:
        # Guest limit. Metering fails CLOSED: any exception here blocks the
        # request (503) rather than letting it through unmetered -- a
        # Supabase blip must not silently disable the guest query cap.
        if not request.anon_id:
            raise HTTPException(status_code=400, detail="anon_id required for guest users")
        client_ip = _get_client_ip(http_request)
        try:
            result = db.rpc("increment_guest_query", {
                "p_anon_id": request.anon_id,
                "p_ip_address": client_ip,
            }).execute()
            count = result.data if isinstance(result.data, int) else 0
            logger.info("[GUEST] anon_id=%s ip=%s query_count=%s", request.anon_id, client_ip, count)
            # count == -1 is the RPC's sentinel for "too many new guest
            # sessions from this IP recently" (migration 057) -- same
            # user-facing message as the ordinary limit, so an abuser
            # rotating anon_id gets no signal distinguishing the two reasons.
            if count < 0 or count > GUEST_QUERY_LIMIT:
                raise HTTPException(status_code=429, detail="guest_limit_reached")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Guest query count check failed for anon_id=%s -- failing closed", request.anon_id)
            raise HTTPException(status_code=503, detail="metering_unavailable")
    else:
        # Authenticated user weekly limit — atomic RPC, limit from per-user row (migration 039).
        # Fails CLOSED: see guest branch above for why.
        try:
            result = db.rpc("increment_user_query", {"p_user_id": user_id}).execute()
            row = result.data[0] if result.data else {}
            count = int(row.get("query_count", 0))
            weekly_limit = int(row.get("weekly_limit", 50))
            week_start_str = str(row.get("week_start", ""))
            allowed = bool(row.get("allowed", True))
            logger.info("[USER] user_id=%s weekly_count=%d limit=%d allowed=%s", user_id, count, weekly_limit, allowed)
            if not allowed:
                # RPC did not increment — count is already AT the limit, not over it.
                week_start_date = datetime.date.fromisoformat(week_start_str) if week_start_str else datetime.date.today()
                next_monday = week_start_date + datetime.timedelta(days=7)
                raise HTTPException(status_code=429, detail={
                    "error": "weekly_limit_reached",
                    "used": count,
                    "limit": weekly_limit,
                    "week_start": week_start_str,
                    "resets": next_monday.isoformat(),
                })
            user_usage_meta = {"used": count, "limit": weekly_limit, "week_start": week_start_str}
        except HTTPException:
            raise
        except Exception:
            logger.exception("User weekly query count check failed for user_id=%s -- failing closed", user_id)
            raise HTTPException(status_code=503, detail="metering_unavailable")

    try:

        # Step 0: Get source filter settings
        filters = get_disabled_filters()
        include_copyrighted = filters["include_copyrighted"] and INCLUDE_COPYRIGHTED_ENV

        # Step 0.5: Background topic injection
        _ensure_background_topics()
        current_turn = len(request.messages)
        matched_topics = match_background_topics(request.question)
        topics_to_inject = []   # type: List[str]  # full paper this turn
        topics_to_condense = [] # type: List[str]  # first chunk only (within 6-turn window)
        for topic_key in matched_topics:
            injection_turn = (request.topics_established or {}).get(topic_key, -99)
            if current_turn - injection_turn > 6:
                topics_to_inject.append(topic_key)
            else:
                # Fix 3: within suppression window — inject first chunk to keep guardrail active
                topics_to_condense.append(topic_key)

        topic_context_parts = []  # type: List[str]
        injected_doc_ids = set()  # type: set  # Fix 6: track for dedup against main pool
        updated_topics = dict(request.topics_established or {})
        if topics_to_inject or topics_to_condense:
            topic_lookup = {t["topic_key"]: t for t in _background_topics}

            for topic_key in topics_to_inject:
                topic = topic_lookup.get(topic_key)
                if not topic:
                    continue
                try:
                    chunk_result = db.table("chunks").select("content").eq(
                        "document_id", topic["document_id"]
                    ).order("chunk_index").execute()
                    if chunk_result.data:
                        full_text = "\n\n".join(c["content"] for c in chunk_result.data)
                        # Fix 4: use [Background] label with citation_mode tag
                        topic_context_parts.append(
                            "[Background] (citation_mode=silent_context) \"%s\"\n%s" % (topic["title"], full_text)
                        )
                        injected_doc_ids.add(topic["document_id"])
                        updated_topics[topic_key] = current_turn
                        logger.info("Injected background topic: %s (%d chunks)", topic_key, len(chunk_result.data))
                except Exception:
                    logger.exception("Failed to fetch chunks for topic %s", topic_key)

            # Fix 3: condensed injection — first chunk only for recently established topics
            for topic_key in topics_to_condense:
                topic = topic_lookup.get(topic_key)
                if not topic:
                    continue
                try:
                    chunk_result = db.table("chunks").select("content").eq(
                        "document_id", topic["document_id"]
                    ).order("chunk_index").limit(1).execute()
                    if chunk_result.data:
                        first_chunk = chunk_result.data[0]["content"]
                        topic_context_parts.append(
                            "[Background] (citation_mode=silent_context) \"%s\"\n%s" % (topic["title"], first_chunk)
                        )
                        injected_doc_ids.add(topic["document_id"])
                        logger.info("Condensed injection for established topic: %s", topic_key)
                except Exception:
                    logger.exception("Failed to fetch condensed chunk for topic %s", topic_key)

        # Step 1: Expand query into variants ([original, paraphrase1, paraphrase2]) + FTS keywords
        variants, keywords = expand_query(request.question)
        variant_weights = [1.0, 0.7, 0.7]
        FTS_WEIGHT = 1.0

        # Step 2: Fuse retrieval (Change 1). When we have distinctive keywords, run vector
        # search per variant plus a SINGLE keyword FTS pass — this avoids running (and
        # over-weighting) an identical FTS query for every variant. Without keywords, fall
        # back to full hybrid (vector + FTS on the full variant) per variant.
        all_scores: Dict[str, Tuple[float, dict]] = {}
        first_embedding = None  # type: Optional[List[float]]

        def _merge(scores, weight):
            # type: (Dict[str, Tuple[float, dict]], float) -> None
            for cid, (score, chunk) in scores.items():
                weighted = score * weight
                if cid in all_scores:
                    all_scores[cid] = (all_scores[cid][0] + weighted, all_scores[cid][1])
                else:
                    all_scores[cid] = (weighted, chunk)

        with ThreadPoolExecutor(max_workers=4) as ex:
            if keywords:
                # Vector-only per variant + one keyword FTS pass, all fired in parallel.
                variant_futures = [
                    ex.submit(hybrid_search_rrf, variant, db,
                              include_copyrighted=include_copyrighted, run_fts=False)
                    for variant in variants
                ]
                fts_future = ex.submit(hybrid_search_rrf, keywords, db,
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
                # Fallback: no keyword routing — full hybrid per variant (current behavior).
                futures = [
                    ex.submit(hybrid_search_rrf, variant, db, include_copyrighted=include_copyrighted)
                    for variant in variants
                ]
                for i, future in enumerate(futures):
                    weight = variant_weights[i] if i < len(variant_weights) else 0.5
                    variant_scores, embedding = future.result()
                    if i == 0:
                        first_embedding = embedding
                    _merge(variant_scores, weight)

        # Step 2.5: Filter out disabled source_kinds and source_names
        all_scores = {
            cid: (score, chunk)
            for cid, (score, chunk) in all_scores.items()
            if not is_chunk_disabled(chunk, filters)
        }

        # Fix 6: Remove chunks from injected position papers — they're already in
        # topic_context_parts, so including them in the main pool would duplicate content
        # and waste context slots for citable sources.
        if injected_doc_ids:
            all_scores = {
                cid: (score, chunk)
                for cid, (score, chunk) in all_scores.items()
                if chunk.get("document_id") not in injected_doc_ids
            }

        # Step 2.75: Apply boost_factor and source-kind fusion weights (Fix 4).
        # source-kind weights de-prioritize commentary/book/lexicon so citable sermons
        # and articles surface into the rerank pool more reliably.
        all_scores = {
            cid: (
                score
                * (chunk.get("boost_factor") or 1.0)
                * SOURCE_KIND_FUSION_WEIGHTS.get(
                    chunk.get("source_kind") or chunk.get("source_type") or "", 1.0
                ),
                chunk,
            )
            for cid, (score, chunk) in all_scores.items()
        }

        # Step 3: Document-level collapse — max 2 chunks per document
        ranked = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)
        doc_counts: Dict[str, int] = {}
        collapsed: List[Tuple[str, Tuple[float, dict]]] = []
        for cid, (score, chunk) in ranked:
            did = chunk.get("document_id", "")
            doc_counts[did] = doc_counts.get(did, 0) + 1
            if doc_counts[did] <= 2:
                collapsed.append((cid, (score, chunk)))

        # Step 3a: Per-author cap — max 3 chunks per unique author
        author_counts: Dict[str, int] = {}
        author_capped: List[Tuple[str, Tuple[float, dict]]] = []
        for cid, (score, chunk) in collapsed:
            author = chunk.get("author") or "Unknown"
            author_counts[author] = author_counts.get(author, 0) + 1
            if author_counts[author] <= 3:
                author_capped.append((cid, (score, chunk)))

        # Fix 1: widen rerank pool to 30, keep top 8 after Cohere.
        top_chunks = author_capped[:30]
        chunks = [chunk for _, (_, chunk) in top_chunks]

        # Step 3.5: Cohere rerank — narrow top 30 → top 8 by relevance (Fix 1)
        co = _get_cohere()
        if co and len(chunks) > 0:
            try:
                docs = [c.get("content", "") for c in chunks]
                rerank_result = co.rerank(
                    model="rerank-v3.5",
                    query=request.question,
                    documents=docs,
                    top_n=8,
                )
                chunks = [chunks[r.index] for r in rerank_result.results]
                logger.info("Cohere rerank: %d → %d chunks", len(docs), len(chunks))
            except Exception:
                logger.exception("Cohere rerank failed, using RRF top 8")
                chunks = chunks[:8]  # Fix 1: fallback also takes 8, not 5

        # Fix 2: count citable chunks across the full post-rerank set (top 8),
        # before neighbor expansion — this is the true "do we have material?" signal.
        citable_count = sum(1 for c in chunks if _is_citable(c))

        # Step 4: Neighbor chunk expansion — batch fetch ±1 chunk_index, cap at 12 total.
        # Fix 4: commentary/lexicon parents are skipped inside fetch_neighbor_chunks_batch.
        seen_ids = {c["id"] for c in chunks}
        neighbors = fetch_neighbor_chunks_batch(chunks, seen_ids, db)
        expanded = list(chunks)
        for n in neighbors:
            if len(expanded) >= 12:
                break
            seen_ids.add(n["id"])
            expanded.append(n)

        # Fix 4: cap commentary chunks in the final assembled context.
        commentary_seen = 0
        capped_expanded = []
        for c in expanded:
            if (c.get("source_kind") or c.get("source_type") or "") == "commentary":
                if commentary_seen >= COMMENTARY_CONTEXT_CAP:
                    continue
                commentary_seen += 1
            capped_expanded.append(c)
        chunks = capped_expanded

        # Step 5: Conditional lexicon retrieval — reuse cached embedding (Change 2)
        if is_word_study_query(request.question):
            try:
                lex_embedding = first_embedding if first_embedding else embed_text(request.question)
                lex_result = db.rpc("match_lexicon_chunks", {
                    "query_embedding": lex_embedding,
                    "match_count": 5,
                }).execute()
                if lex_result.data:
                    for lc in lex_result.data:
                        lc["_lexicon"] = True
                    chunks.extend(lex_result.data)
                    logger.info("Lexicon retrieval: %d chunks appended", len(lex_result.data))
            except Exception:
                logger.exception("Lexicon retrieval failed, continuing without")

        citations = [
            {
                "chunk_id": c["id"],
                "document_title": c.get("title"),
                "author": c.get("author"),
                "content": c["content"],
                "url": c.get("url"),
            }
            for c in chunks
            if _is_citable(c)
        ]

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unhandled error in /chat endpoint (pre-stream)")
        raise HTTPException(status_code=500, detail="An internal error occurred")

    def generate():
        # True-empty short-circuit: nothing retrieved at all — no citable, no background.
        # Only bail here; thin-citable-but-has-background takes the graceful-degradation path.
        truly_empty = not chunks and not topic_context_parts
        if truly_empty:
            fallback = "I don't have strong material on that topic in my current library."
            yield _sse(json.dumps({"token": fallback}))
            yield _sse(json.dumps({"citations": [], "conversation_id": None}))
            yield _sse("[DONE]")
            return

        regular = [c for c in chunks if not c.get("_lexicon")]
        lexicon = [c for c in chunks if c.get("_lexicon")]

        # Number only citable chunks contiguously ([Source 1], [Source 2], ...) so they
        # align with the citations array; silent_context chunks are labeled [Background].
        context_parts = []  # type: List[str]
        source_num = 0
        for i, c in enumerate(regular):
            if _is_citable(c):
                source_num += 1
                label = "[Source %d]" % source_num
            else:
                label = "[Background]"
            context_parts.append(
                f"{label} (source_kind={c.get('source_kind') or c.get('source_type', 'unknown')}, citation_mode={c.get('citation_mode', 'citable')}) \"{c.get('title', 'Unknown')}\" by {c.get('author', 'Unknown')}, chunk {c.get('chunk_index', i)}\n{c['content']}"
            )
        context = "\n\n---\n\n".join(context_parts)

        if topic_context_parts:
            topic_block = "\n\n---\n\n".join(topic_context_parts)
            context = topic_block + "\n\n---\n\n" + context

        # Graceful-degradation hint: when citable sources are thin but background exists,
        # tell the model so it follows the graceful degradation rules in the system prompt.
        if citable_count < 2 and not topic_context_parts:
            context += (
                "\n\n[Retrieval note: citable sources on this topic are thin or absent. "
                "The strongest available material is background-only. "
                "Follow the graceful degradation rules in your instructions.]"
            )

        if lexicon:
            lex_context = "\n\n---\n\n".join(
                f"[Lexicon] {c['content']}"
                for c in lexicon
            )
            context += "\n\n--- LEXICON CONTEXT (silent_context — do not cite by name) ---\n\n" + lex_context

        # Build conversation history for Anthropic Claude
        history = []
        recent_messages = request.messages[-6:] if len(request.messages) > 6 else request.messages
        for msg in recent_messages:
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": msg.content})
        history.append({
            "role": "user",
            "content": f"Sources:\n{context}\n\nQuestion: {request.question}",
        })

        # Stream from Anthropic Claude, extracting only <answer> content (Change 4: singleton)
        raw_full = []
        answer_parts = []
        in_answer = False
        answer_closed = False  # SP1: once True, never re-enter in_answer — protects
                                # against a stray "<answer>" substring appearing in
                                # content written after </answer> (see Task 11 note above).
        buffer = ""

        def _close_answer(buf: str, close_pos: int) -> str:
            """Shared close-tag handling for both close-detection sites
            (Site A: </answer> found in the same chunk as the opening
            <answer> tag; Site B: </answer> found mid-stream while already
            in_answer). Extracts the trailing content before </answer> and
            permanently flips BOTH guard flags together. Centralizing this
            makes it impossible for one site to set in_answer=False without
            also setting answer_closed=True — exactly the drift that caused
            Task 11's stream-leak bug (Site A set only in_answer=False,
            leaving answer_closed unset, so a later chunk containing the
            literal substring "<answer>" in trailing content re-opened
            in_answer and re-streamed it as real answer text).
            """
            nonlocal in_answer, answer_closed
            part = buf[:close_pos]
            if part:
                answer_parts.append(part)
            in_answer = False
            answer_closed = True
            return part

        try:
            client = get_anthropic_client()
            stream = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                system=ANSWER_SYSTEM_BLOCKS,
                messages=history,
                stream=True,
            )
            for event in stream:
                if event.type == "message_start":
                    usage = getattr(event.message, "usage", None)
                    if usage:
                        logger.debug(
                            "[CACHE] creation=%d read=%d input=%d",
                            getattr(usage, "cache_creation_input_tokens", 0) or 0,
                            getattr(usage, "cache_read_input_tokens", 0) or 0,
                            getattr(usage, "input_tokens", 0),
                        )
                    continue
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    text = event.delta.text
                else:
                    continue
                raw_full.append(text)
                buffer += text

                if not in_answer and not answer_closed:
                    # Check if <answer> tag has appeared in the buffer
                    tag_pos = buffer.find("<answer>")
                    if tag_pos != -1:
                        in_answer = True
                        # Emit anything after the opening tag
                        after_tag = buffer[tag_pos + len("<answer>"):]
                        buffer = after_tag
                        # Check if closing tag is already in this chunk
                        close_pos = buffer.find("</answer>")
                        if close_pos != -1:
                            part = _close_answer(buffer, close_pos)
                            if part:
                                yield _sse(json.dumps({"token": part}))
                            buffer = ""
                        elif buffer:
                            answer_parts.append(buffer)
                            yield _sse(json.dumps({"token": buffer}))
                            buffer = ""
                elif in_answer:
                    # Inside <answer> — check for closing tag
                    close_pos = buffer.find("</answer>")
                    if close_pos != -1:
                        part = _close_answer(buffer, close_pos)
                        if part:
                            yield _sse(json.dumps({"token": part}))
                        buffer = ""
                    else:
                        # Yield buffer but keep last 9 chars in case
                        # "</answer>" spans across chunks
                        safe_len = len(buffer) - 9
                        if safe_len > 0:
                            safe = buffer[:safe_len]
                            answer_parts.append(safe)
                            yield _sse(json.dumps({"token": safe}))
                            buffer = buffer[safe_len:]
                # else: answer_closed and not in_answer — SP1 guard. Silently
                # discard everything after </answer> (e.g. Task 10's trailing
                # <reference_mentions> block). Without this explicit no-op
                # branch, the two-way if/else above would fall through into
                # the "elif in_answer" branch's old unconditional "else" and
                # start re-streaming trailing content as if it were still
                # inside the answer — confirmed by simulation during Task 11
                # self-review. Never re-enters emission; never re-checks for
                # a stray "<answer>" substring (branch A above requires
                # `not answer_closed`).
        except Exception:
            logger.exception("Chat LLM stream failed")
            yield _sse(json.dumps({"error": "AI service temporarily unavailable"}))
            yield _sse("[DONE]")
            return

        # If stream ended mid-answer, flush remaining buffer
        if in_answer and buffer:
            answer_parts.append(buffer)
            yield _sse(json.dumps({"token": buffer}))
            buffer = ""

        # If we never found <answer> tags, the full raw output is the answer.
        # SP1: strip anything from a stray <reference_mentions> tag onward first —
        # a malformed generation could otherwise leak that block into what the
        # user reads (Global Constraint: answer text must be byte-for-byte
        # unaffected by anything added for the new block, even on malformed output).
        if not answer_parts:
            raw_text = "".join(raw_full).strip()
            ref_tag_pos = raw_text.find("<reference_mentions>")
            if ref_tag_pos != -1:
                raw_text = raw_text[:ref_tag_pos].strip()
            answer_parts.append(raw_text)
            yield _sse(json.dumps({"token": raw_text}))

        answer = "".join(answer_parts).strip()
        raw_output = "".join(raw_full)

        # SP1: verify proposed verse/teacher mentions against real data.
        # Wrapped so any failure here can never affect the answer already
        # sent, the conversation save below, or the final meta event.
        try:
            from app.services.reference_verifier import verify_references
            verified_references = verify_references(answer, raw_output, db)
        except Exception:
            logger.exception("SP1 reference verification failed — continuing without pointers")
            verified_references = []

        # Pre-generate IDs and fire background save (Change 6)
        conversation_id = request.conversation_id or str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        is_new = request.conversation_id is None
        if user_id:
            threading.Thread(
                target=_save_conversation,
                args=(db, user_id, conversation_id, is_new, request.question, answer, message_id),
                daemon=True,
            ).start()
            logger.info("Conversation save dispatched in background: %s", conversation_id)
        else:
            conversation_id = None
            message_id = None
            logger.debug("Skipping conversation save — no authenticated user")

        # Send metadata and close
        meta = {
            "citations": citations,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "verified_references": verified_references,
        }
        if updated_topics:
            meta["topics_established"] = updated_topics
        if user_usage_meta:
            meta["usage"] = user_usage_meta
        yield _sse(json.dumps(meta))
        yield _sse("[DONE]")

    return StreamingResponse(generate(), media_type="text/event-stream")
