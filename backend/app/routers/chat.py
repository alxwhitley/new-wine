from __future__ import annotations

import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

from groq import Groq
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.auth import get_optional_user
from app.db.supabase import get_supabase
from app.services.embeddings import embed_text

logger = logging.getLogger(__name__)

system_prompt = (Path(__file__).resolve().parent.parent / "system_prompt.txt").read_text()

GROQ_MODEL = "llama-3.3-70b-versatile"
RRF_K = 60  # Reciprocal Rank Fusion constant

router = APIRouter()

_ai = None


def _get_ai():
    global _ai
    if _ai is None:
        _ai = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _ai


def expand_query(question: str) -> list[str]:
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


INCLUDE_COPYRIGHTED = os.environ.get("INCLUDE_COPYRIGHTED", "true").lower() == "true"


def hybrid_search_rrf(query: str, db, vector_k: int = 40, fts_k: int = 30) -> dict[str, tuple[float, dict]]:
    """Run vector + FTS search for a single query, return {chunk_id: (rrf_score, chunk)}."""
    embedding = embed_text(query)

    try:
        vector_result = db.rpc("match_chunks", {
            "query_embedding": embedding,
            "match_count": vector_k,
            "include_copyrighted": INCLUDE_COPYRIGHTED,
        }).execute()
    except Exception:
        logger.exception("Vector search RPC failed for query: %s", query[:100])
        raise

    try:
        fts_result = db.rpc("search_chunks_fts", {
            "query_text": query,
            "match_count": fts_k,
            "include_copyrighted": INCLUDE_COPYRIGHTED,
        }).execute()
    except Exception:
        logger.exception("FTS search RPC failed for query: %s", query[:100])
        raise

    scores: dict[str, tuple[float, dict]] = {}

    for rank, chunk in enumerate(vector_result.data):
        cid = chunk["id"]
        score = 1 / (RRF_K + rank)
        if cid not in scores or score > scores[cid][0]:
            scores[cid] = (score, chunk)
        else:
            scores[cid] = (scores[cid][0] + score, scores[cid][1])

    for rank, chunk in enumerate(fts_result.data):
        cid = chunk["id"]
        score = 1 / (RRF_K + rank)
        if cid in scores:
            scores[cid] = (scores[cid][0] + score, scores[cid][1])
        else:
            scores[cid] = (score, chunk)

    return scores


def _is_citable(chunk: dict) -> bool:
    """Return True if this chunk should appear in citations."""
    mode = chunk.get("citation_mode")
    if mode:
        return mode == "citable"
    # Fallback for rows without citation_mode
    return chunk.get("source_type") == "sermon"


def fetch_neighbor_chunks(document_id: str, chunk_index: int, db) -> list[dict]:
    """Fetch the chunks immediately before and after the given chunk_index in the same document."""
    neighbors = []
    for idx in [chunk_index - 1, chunk_index + 1]:
        if idx < 0:
            continue
        result = db.table("chunks").select("*").eq("document_id", document_id).eq("chunk_index", idx).limit(1).execute()
        if result.data:
            neighbors.append(result.data[0])
    return neighbors


class ChatMessage(BaseModel):
    role: str
    content: str


GUEST_QUERY_LIMIT = 6


class ChatRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    messages: list[ChatMessage] = []
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
    db, user_id: str, conversation_id: Optional[str], question: str, answer: str,
) -> str:
    """Save the exchange to Supabase. Returns the conversation_id."""
    is_new = conversation_id is None
    if is_new:
        conversation_id = str(uuid.uuid4())
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
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": answer,
        },
    ]).execute()
    logger.info("Messages insert result: %d row(s) for conversation %s", len(result.data) if result.data else 0, conversation_id)

    return conversation_id


def _sse(data: str) -> str:
    return f"data: {data}\n\n"


@router.post("")
async def chat(request: ChatRequest, user_id: Optional[str] = Depends(get_optional_user)):
    # TODO: temporary debug log — remove after confirming auth works
    logger.info("[DEBUG AUTH] user_id=%s | SUPABASE_JWT_JWKS_URL present=%s",
                user_id, bool(os.environ.get("SUPABASE_JWT_JWKS_URL")))

    db = get_supabase()

    # Guest query limit check
    if not user_id:
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

    try:

        # Step 1: Expand query into variants
        variants = expand_query(request.question)
        variant_weights = [1.0, 0.8, 0.6]

        # Step 2: Run hybrid search for each variant with weighted RRF SUM
        all_scores: dict[str, tuple[float, dict]] = {}
        for i, variant in enumerate(variants):
            weight = variant_weights[i] if i < len(variant_weights) else 0.5
            variant_scores = hybrid_search_rrf(variant, db)
            for cid, (score, chunk) in variant_scores.items():
                weighted = score * weight
                if cid in all_scores:
                    all_scores[cid] = (all_scores[cid][0] + weighted, all_scores[cid][1])
                else:
                    all_scores[cid] = (weighted, chunk)

        # Step 3: Document-level collapse — max 2 chunks per document
        ranked = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)
        doc_counts: dict[str, int] = {}
        collapsed: list[tuple[str, tuple[float, dict]]] = []
        for cid, (score, chunk) in ranked:
            did = chunk.get("document_id", "")
            doc_counts[did] = doc_counts.get(did, 0) + 1
            if doc_counts[did] <= 2:
                collapsed.append((cid, (score, chunk)))
        top_chunks = collapsed[:10]
        chunks = [chunk for _, (_, chunk) in top_chunks]

        # Step 4: Neighbor chunk expansion — fetch ±1 chunk_index, cap at 12 total
        seen_ids = {c["id"] for c in chunks}
        expanded = list(chunks)
        for c in chunks:
            if len(expanded) >= 12:
                break
            neighbors = fetch_neighbor_chunks(c.get("document_id", ""), c.get("chunk_index", 0), db)
            for n in neighbors:
                if n["id"] not in seen_ids and len(expanded) < 12:
                    # Copy parent metadata to neighbor
                    for key in ("title", "author", "source_type", "source_kind", "citation_mode", "url"):
                        if key not in n and key in c:
                            n[key] = c[key]
                    seen_ids.add(n["id"])
                    expanded.append(n)
        chunks = expanded

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

        context = "\n\n---\n\n".join(
            f"[Source {i+1}] (source_kind={c.get('source_kind') or c.get('source_type', 'unknown')}, citation_mode={c.get('citation_mode', 'citable')}) \"{c.get('title', 'Unknown')}\" by {c.get('author', 'Unknown')}, chunk {c.get('chunk_index', i)}\n{c['content']}"
            for i, c in enumerate(chunks)
        )

        # Build conversation history for Groq
        history = [{"role": "system", "content": system_prompt}]
        for msg in request.messages:
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": msg.content})
        history.append({
            "role": "user",
            "content": f"Sources:\n{context}\n\nQuestion: {request.question}",
        })

        # Stream from Groq, extracting only <answer> content
        raw_full = []
        answer_parts = []
        in_answer = False
        buffer = ""

        try:
            stream = _get_ai().chat.completions.create(
                model=GROQ_MODEL,
                max_tokens=8192,
                messages=history,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta or not delta.content:
                    continue
                text = delta.content
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

        # Save conversation if authenticated
        conversation_id = None
        if user_id:
            try:
                conversation_id = _save_conversation(
                    db, user_id, request.conversation_id, request.question, answer,
                )
                logger.info("Conversation saved successfully: %s", conversation_id)
            except Exception:
                logger.exception("Failed to save conversation for user %s", user_id)
        else:
            logger.debug("Skipping conversation save — no authenticated user")

        # Send metadata and close
        yield _sse(json.dumps({"citations": citations, "conversation_id": conversation_id}))
        yield _sse("[DONE]")

    return StreamingResponse(generate(), media_type="text/event-stream")
