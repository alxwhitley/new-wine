from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import anthropic
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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

logger = logging.getLogger(__name__)

_app_dir = Path(__file__).resolve().parent.parent
_system_prompt_text = (_app_dir / "system_prompt.txt").read_text()
_guardrails_text = (_app_dir / "theological_guardrails.txt").read_text() + (
    "\n\nRepresent the views of the source documents faithfully and accurately, "
    "even when those views reflect traditional or complementarian theology. "
    "Do not editorialize or add modern qualifications unless they appear in the source material."
)
ANSWER_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": _system_prompt_text,
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": _guardrails_text,
        "cache_control": {"type": "ephemeral"},
    },
]

GROQ_MODEL = "llama-3.3-70b-versatile"
RRF_K = 60  # Reciprocal Rank Fusion constant

router = APIRouter()

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


_anthropic_client = None


def _get_anthropic():
    # type: () -> anthropic.Anthropic
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def expand_query(question: str) -> List[str]:
    """Ask Llama to rewrite the query into 3 search variants."""
    try:
        response = _get_ai().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": (
                    "Rewrite the following theological question into 3 distinct search queries "
                    "that capture the same intent using different phrasings, vocabulary, or angles. "
                    "Return ONLY a JSON array of 3 strings. No explanation.\n\n"
                    f"Question: {question}"
                ),
            }],
        )
    except Exception:
        logger.exception("Query expansion call failed, falling back to original query")
        return [question]

    raw = (response.choices[0].message.content or "").strip()
    try:
        variants = json.loads(raw)
        if isinstance(variants, list) and len(variants) >= 1:
            return variants[:3]
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())[:3]
            except json.JSONDecodeError:
                pass
    return [question]


INCLUDE_COPYRIGHTED_ENV = os.environ.get("INCLUDE_COPYRIGHTED", "true").lower() == "true"


FTS_QUERY_MAX_LEN = 300  # Truncate FTS queries to avoid Cloudflare 400s


def hybrid_search_rrf(query, db, vector_k=40, fts_k=30, include_copyrighted=True, precomputed_embedding=None):
    # type: (str, object, int, int, bool, Optional[List[float]]) -> Tuple[dict, List[float]]
    """Run vector + FTS search for a single query.

    Returns ({chunk_id: (rrf_score, chunk)}, embedding_used).
    Accepts an optional precomputed_embedding to avoid redundant embed calls (Change 2).
    Fires embed_text and FTS in parallel since FTS doesn't need the embedding (Change 5).
    FTS and vector failures are non-fatal — each falls back to empty results.
    """
    fts_query = query[:FTS_QUERY_MAX_LEN]

    with ThreadPoolExecutor(max_workers=2) as ex:
        # Fire FTS immediately — no dependency on embedding
        fts_future = ex.submit(
            lambda: db.rpc("search_chunks_fts", {
                "query_text": fts_query,
                "match_count": fts_k,
                "include_copyrighted": include_copyrighted,
            }).execute()
        )

        # Get embedding: use precomputed or compute (runs concurrently with FTS)
        if precomputed_embedding is not None:
            embedding = precomputed_embedding
        else:
            embedding = embed_text(query)

        # Vector search needs the embedding — fires after embed completes
        vector_data = []  # type: list
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
        try:
            fts_result = fts_future.result()
            fts_data = fts_result.data or []
        except Exception:
            logger.exception("FTS search failed, continuing with vector only: %s", query[:100])

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


def fetch_neighbor_chunks_batch(chunks: List[dict], seen_ids: set, db) -> List[dict]:
    """Fetch ±1 neighbor chunks for all given chunks in a single query."""
    # Collect all needed (document_id, chunk_index) pairs
    needed = set()  # type: set
    chunk_parents = {}  # type: Dict[str, dict]  # "doc_id:idx" -> parent chunk
    for c in chunks:
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
USER_DAILY_QUERY_LIMIT = 65  # ~$2/day at ~$0.03/query


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    messages: List[ChatMessage] = []
    anon_id: Optional[str] = None

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


@router.post("")
async def chat(request: ChatRequest, user_id: Optional[str] = Depends(get_optional_user)):
    db = get_supabase()

    # Query limit checks
    if not user_id:
        # Guest limit
        if not request.anon_id:
            raise HTTPException(status_code=400, detail="anon_id required for guest users")
        try:
            result = db.rpc("increment_guest_query", {"p_anon_id": request.anon_id}).execute()
            count = result.data if isinstance(result.data, int) else 0
            logger.info("[GUEST] anon_id=%s query_count=%s", request.anon_id, count)
            if count > GUEST_QUERY_LIMIT:
                raise HTTPException(status_code=429, detail="guest_limit_reached")
        except HTTPException:
            raise
        except Exception:
            logger.exception("Guest query count check failed for anon_id=%s", request.anon_id)
    else:
        # Authenticated user daily limit
        try:
            result = db.rpc("increment_user_daily_query", {"p_user_id": user_id}).execute()
            count = result.data if isinstance(result.data, int) else 0
            logger.info("[USER] user_id=%s daily_query_count=%s", user_id, count)
            if count > USER_DAILY_QUERY_LIMIT:
                raise HTTPException(status_code=429, detail="daily_limit_reached")
        except HTTPException:
            raise
        except Exception:
            logger.exception("User daily query count check failed for user_id=%s", user_id)

    try:

        # Step 0: Get source filter settings
        filters = get_disabled_filters()
        include_copyrighted = filters["include_copyrighted"] and INCLUDE_COPYRIGHTED_ENV

        # Step 1: Expand query into variants
        variants = expand_query(request.question)
        variant_weights = [1.0, 0.8, 0.6]

        # Step 2: Run hybrid search for each variant in parallel (Change 1)
        all_scores: Dict[str, Tuple[float, dict]] = {}
        first_embedding = None  # type: Optional[List[float]]

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = [
                ex.submit(hybrid_search_rrf, variant, db, include_copyrighted=include_copyrighted)
                for variant in variants
            ]
            for i, future in enumerate(futures):
                weight = variant_weights[i] if i < len(variant_weights) else 0.5
                variant_scores, embedding = future.result()
                if i == 0:
                    first_embedding = embedding
                for cid, (score, chunk) in variant_scores.items():
                    weighted = score * weight
                    if cid in all_scores:
                        all_scores[cid] = (all_scores[cid][0] + weighted, all_scores[cid][1])
                    else:
                        all_scores[cid] = (weighted, chunk)

        # Step 2.5: Filter out disabled source_kinds and source_names
        all_scores = {
            cid: (score, chunk)
            for cid, (score, chunk) in all_scores.items()
            if not is_chunk_disabled(chunk, filters)
        }

        # Step 2.75: Apply boost_factor from RPC results — no extra query (Change 3)
        all_scores = {
            cid: (score * (chunk.get("boost_factor") or 1.0), chunk)
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

        top_chunks = author_capped[:10]
        chunks = [chunk for _, (_, chunk) in top_chunks]

        # Step 3.5: Cohere rerank — narrow top 10 → top 5 by relevance (Change 4: singleton)
        co = _get_cohere()
        if co and len(chunks) > 0:
            try:
                docs = [c.get("content", "") for c in chunks]
                rerank_result = co.rerank(
                    model="rerank-v3.5",
                    query=request.question,
                    documents=docs,
                    top_n=5,
                )
                chunks = [chunks[r.index] for r in rerank_result.results]
                logger.info("Cohere rerank: %d → %d chunks", len(docs), len(chunks))
            except Exception:
                logger.exception("Cohere rerank failed, using RRF top 10")

        # Step 4: Neighbor chunk expansion — batch fetch ±1 chunk_index, cap at 12 total
        seen_ids = {c["id"] for c in chunks}
        neighbors = fetch_neighbor_chunks_batch(chunks, seen_ids, db)
        expanded = list(chunks)
        for n in neighbors:
            if len(expanded) >= 12:
                break
            seen_ids.add(n["id"])
            expanded.append(n)
        chunks = expanded

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
        # Low-material fallback
        if len(chunks) < 3:
            fallback = "I don't have strong material on that topic in my current library."
            yield _sse(json.dumps({"token": fallback}))
            yield _sse(json.dumps({"citations": [], "conversation_id": None}))
            yield _sse("[DONE]")
            return

        regular = [c for c in chunks if not c.get("_lexicon")]
        lexicon = [c for c in chunks if c.get("_lexicon")]

        context = "\n\n---\n\n".join(
            f"[Source {i+1}] (source_kind={c.get('source_kind') or c.get('source_type', 'unknown')}, citation_mode={c.get('citation_mode', 'citable')}) \"{c.get('title', 'Unknown')}\" by {c.get('author', 'Unknown')}, chunk {c.get('chunk_index', i)}\n{c['content']}"
            for i, c in enumerate(regular)
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
        buffer = ""

        try:
            client = _get_anthropic()
            stream = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1500,
                system=ANSWER_SYSTEM_BLOCKS,
                messages=history,
                stream=True,
            )
            for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    text = event.delta.text
                else:
                    continue
                raw_full.append(text)
                buffer += text

                if not in_answer:
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
                            part = buffer[:close_pos]
                            if part:
                                answer_parts.append(part)
                                yield _sse(json.dumps({"token": part}))
                            in_answer = False
                            buffer = ""
                        elif buffer:
                            answer_parts.append(buffer)
                            yield _sse(json.dumps({"token": buffer}))
                            buffer = ""
                else:
                    # Inside <answer> — check for closing tag
                    close_pos = buffer.find("</answer>")
                    if close_pos != -1:
                        part = buffer[:close_pos]
                        if part:
                            answer_parts.append(part)
                            yield _sse(json.dumps({"token": part}))
                        in_answer = False
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

        # If we never found <answer> tags, the full raw output is the answer
        if not answer_parts:
            raw_text = "".join(raw_full).strip()
            answer_parts.append(raw_text)
            yield _sse(json.dumps({"token": raw_text}))

        answer = "".join(answer_parts).strip()

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
        yield _sse(json.dumps({"citations": citations, "conversation_id": conversation_id, "message_id": message_id}))
        yield _sse("[DONE]")

    return StreamingResponse(generate(), media_type="text/event-stream")
