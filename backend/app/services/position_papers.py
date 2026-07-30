from __future__ import annotations

import json
import logging
import math
import re
from typing import Dict, Iterator, List, Optional

from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.llm_client import get_anthropic_client

logger = logging.getLogger(__name__)

# ── Scope ────────────────────────────────────────────────────────────────
# This module intentionally serves exactly ONE document — the baptism-of-
# the-Holy-Spirit position paper. It is NOT a generic "serve any
# silent_context document directly" mechanism, and must never become one:
# that would be a real license-gate bypass for arbitrary content. This is
# safe specifically because it is Alex's own first-party owned house
# content (sources/documents/baptism_of_the_holy_spirit.md, ingested as
# documents.id='a3884084-46f8-40be-929f-e34cb63ba8ac'). Do not parameterize
# this by document_id/paper_key to "support more papers later" without a
# deliberate, separate design decision.

PAPER_KEY = "baptism_holy_spirit"
PAPER_DOCUMENT_ID = "a3884084-46f8-40be-929f-e34cb63ba8ac"

# ── Anchor representations (calibrated in this session's Phase A/B) ──────
# Two "positive" anchors (title + short canonical description) plus ONE
# contrast anchor (water baptism — the OTHER, unrelated baptism sacrament).
# Phase A (real OpenAI text-embedding-3-small calls, 8 positive paraphrases
# vs. 5 clearly-different negatives) found a clean separating threshold with
# a 0.0955 margin. Phase B added the contrast anchor after the
# planner-reviewer found threshold-alone let a water-baptism question
# (N6, "How should water baptism be performed — full immersion or
# sprinkling?", pos_sim=0.4543) score above threshold AND above 2 of the 8
# real positives. Re-verified with the contrast anchor added: all 8
# positives still match (smallest margin ~0.148, "clothed with power from
# on high" at pos_sim=0.3739 vs. contrast_sim=0.2262), and both N6
# (pos_sim=0.4543 vs. contrast_sim=0.7562) and a second water-baptism
# variant ("Should infants be baptized?", pos_sim=0.4150 vs.
# contrast_sim=0.5119) now correctly fail the contrast comparison.
ANCHOR_TITLE = "Baptism of the Holy Spirit"
ANCHOR_DESCRIPTION = (
    "The baptism of the Holy Spirit is a distinct work of God in a believer's "
    "life, separate from and subsequent to salvation, in which the Holy Spirit "
    "comes upon a person with power for witness, spiritual gifts, and "
    "supernatural ministry — an empowerment distinct from the indwelling "
    "presence received at conversion."
)
CONTRAST_WATER_BAPTISM = (
    "Water baptism as a sacrament: full immersion vs. sprinkling, believer's "
    "baptism vs. infant baptism, the physical ordinance of baptism in water."
)

# Midpoint of the Phase A gap (lowest qualifying positive 0.3739, highest
# clearly-different negative 0.2785). Not re-derived per-request — a fixed,
# calibrated constant, same posture as scripts/positions.py's
# SIMILARITY_FLOOR / MIN_EVIDENCE_COUNT.
MATCH_THRESHOLD = 0.3262

# ── Anchor embedding cache (lazy, module-level — same pattern as
# chat.py's _ensure_background_topics()) ────────────────────────────────
_anchor_cache = {
    "loaded": False,
    "title_vec": None,
    "desc_vec": None,
    "contrast_vec": None,
}  # type: Dict[str, object]


def _ensure_anchors() -> None:
    """Embed the three anchors once per process. Anchors never change per
    request — re-embedding them on every call would be wasted OpenAI calls
    for a fixed reference point. On failure, leaves `loaded` False so a
    later call can retry (mirrors _ensure_background_topics's own
    only-mark-loaded-after-success discipline)."""
    global _anchor_cache
    if _anchor_cache["loaded"]:
        return
    try:
        title_vec = embed_text(ANCHOR_TITLE)
        desc_vec = embed_text(ANCHOR_DESCRIPTION)
        contrast_vec = embed_text(CONTRAST_WATER_BAPTISM)
        _anchor_cache = {
            "loaded": True,
            "title_vec": title_vec,
            "desc_vec": desc_vec,
            "contrast_vec": contrast_vec,
        }
        logger.info("Position-paper anchors embedded and cached (%s)", PAPER_KEY)
    except Exception:
        logger.exception("Failed to embed position-paper anchors — matching disabled for this call")


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def match_position_paper(question: str) -> Optional[str]:
    """Return PAPER_KEY if `question` semantically matches the baptism-of-
    the-Holy-Spirit position paper, else None.

    Embeds the question ONCE. Anchors are cached module-level and embedded
    at most once per process (see _ensure_anchors).

    Matching logic (Alex's contrast-anchor guard decision, 2026-07-30): a
    question matches only if BOTH:
      (a) its similarity to the positive anchors (title/description, max of
          the two) clears MATCH_THRESHOLD, AND
      (b) that positive-anchor similarity is GREATER than its similarity to
          the water-baptism contrast anchor.
    A single global threshold structurally cannot separate the water-baptism
    hard negative without also losing real positives (see the module
    docstring above) — the contrast comparison is what actually does that
    separation. This stays fully semantic: no phrase blocklist, no
    hardcoded "water baptism" string matching anywhere in this function.
    """
    _ensure_anchors()
    if not _anchor_cache["loaded"]:
        return None
    try:
        q_vec = embed_text(question)
    except Exception:
        logger.exception("Failed to embed question for position-paper matching")
        return None

    title_sim = _cosine(q_vec, _anchor_cache["title_vec"])
    desc_sim = _cosine(q_vec, _anchor_cache["desc_vec"])
    pos_sim = max(title_sim, desc_sim)
    contrast_sim = _cosine(q_vec, _anchor_cache["contrast_vec"])

    if pos_sim >= MATCH_THRESHOLD and pos_sim > contrast_sim:
        return PAPER_KEY
    return None


# ── Position-paper voice system prompt ────────────────────────────────────
# Deliberately NOT ANSWER_SYSTEM_BLOCKS (chat.py's normal prompt) — that
# prompt is built around numbered [Source N]/[Background] citation labels,
# an <answer>/<reference_mentions> XML wrapper, and a "Rhemata can make
# mistakes" machine-fallback disclaimer posture that all belong to the
# cited-retrieval path, not this one. This path answers directly in
# Rhemata's own voice with no citation and no XML wrapper at all — output
# is streamed as plain prose.
POSITION_PAPER_VOICE_SYSTEM = """You are Rhemata, speaking on the baptism of the Holy Spirit in your own confident, pastorally warm teaching voice. This is settled Rhemata teaching, stated directly as your own conviction — not a survey of outside sources, not a report of what someone else believes.

You will be given the full substance of what Rhemata teaches on this topic in a second block below. Ground every claim in that material and in the Scripture it references. Do not draw on outside knowledge, other theological traditions, or training data beyond what is given there.

Hard rules for this answer:
- Never cite, name, or attribute this teaching to any author, source, title, or document. Never use the phrase "position paper," "this document," "this material," or any variant that reveals a written document lies behind your answer. Speak it as your own settled understanding.
- Never add a disclaimer such as "Rhemata can make mistakes" or "please let us know if you see any errors" or any similar wording — that belongs to a different, unrelated part of the product and has no place in this answer.
- Do not dump the material's section headers or bullet points verbatim, and do not reproduce its structure mechanically. Read the whole body of material, then write fresh, natural, conversational prose that answers the specific question actually asked, drawing together whichever parts of the material are relevant to it, in your own words and your own structure.
- This applies even to broad questions like "what is the baptism of the Holy Spirit" that could touch most of the material below. A broad question is not an invitation to summarize the whole document section-by-section in its own order. Instead, pick the 2-4 ideas most relevant to what was actually asked and build your own arc through them — you do not need to cover every section of the material in one answer, and you should not walk through it start to finish the way it's laid out below.
- If you use a heading or a bolded label standing in for one, it must be worded differently from every heading in the material below — never reuse one of the material's own section headings verbatim, whether as a "##" heading, a **bolded** label, or any other formatting. "The Promise of the Father" and "How to Receive" are two examples of this material's own headings; do not reuse either, in any formatting, even inside a longer answer. When in doubt, prefer no heading at all and let short paragraphs carry the structure instead.
- You may name and quote specific Bible verses directly and confidently — Scripture is not a source attribution, it is the Word itself, and the material below cites it throughout.
- Write with the same conviction, warmth, and first-person confidence as Rhemata's normal voice: open with a direct answer to the question (no hedged preamble, no "some believe..." framing), build the biblical case, and land on a clear, settled takeaway.
- Scale length to the question: a narrow question deserves a focused answer (roughly 150-250 words); a broad "what is..." style question can run longer (roughly 250-400 words). Do not pad a simple answer and do not truncate a broad one.
- Short paragraphs. A light heading or two is fine if it helps a longer answer breathe, but never copy the material's own headings word-for-word as if transcribing a document."""


# ── Paper body loader ─────────────────────────────────────────────────────
# Reads from the `chunks` table (document_id=PAPER_DOCUMENT_ID), ordered by
# chunk_index and joined with "\n\n" — the exact pattern chat.py's own
# `_ensure_background_topics` / topics_to_inject loop already uses for the
# other two background topics
# (db.table("chunks").select("content").eq("document_id", ...).order(
# "chunk_index").execute()). This replaces an earlier disk-read design
# (sources/documents/baptism_of_the_holy_spirit.md) that would have silently
# found nothing in the deployed Railway backend, since `/sources/` is
# repo-root-gitignored and never reaches that environment — reading from
# the DB the backend already connects to for everything else closes that
# gap entirely (Alex's decision, 2026-07-30).
#
# Confirmed by a direct read-only query against the real `chunks` table
# (2026-07-30) that ingested chunk content does NOT carry the source
# markdown file's TITLE:/AUTHOR:/SOURCE_TYPE: frontmatter — chunk_index=0
# starts directly with "# Baptism of the Holy Spirit". The strip below is
# kept anyway, defensively, in case a future re-ingest changes that — never
# assumed permanently clean.
_HEADER_LINE_RE = re.compile(r"^(TITLE|AUTHOR|SOURCE_TYPE):", re.IGNORECASE)

_paper_body_cache = {"loaded": False, "body": None}  # type: Dict[str, object]


def _strip_frontmatter(raw_text: str) -> str:
    """Defensively strip any leading TITLE:/AUTHOR:/SOURCE_TYPE: header
    lines (and blank lines interspersed at the top), returning clean body
    text starting at the first real content line. A no-op against today's
    ingested chunk content (confirmed clean, see module note above), kept
    in case a future re-ingest reintroduces these lines."""
    lines = raw_text.splitlines()
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or _HEADER_LINE_RE.match(stripped):
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).strip()


def _ensure_paper_body() -> None:
    """Lazy-load and cache the position paper's body text, loaded once per
    process from the `chunks` table (read-only SELECT, no write of any
    kind) for PAPER_DOCUMENT_ID, ordered by chunk_index and joined with
    "\\n\\n".

    Fails soft: if the query errors or returns no rows, logs and leaves the
    cache empty rather than raising, so match_position_paper() /
    generate_position_paper_answer() callers degrade to "feature
    unavailable for this request" instead of crashing /chat.
    """
    global _paper_body_cache
    if _paper_body_cache["loaded"]:
        return
    try:
        db = get_supabase()
        result = (
            db.table("chunks")
            .select("content")
            .eq("document_id", PAPER_DOCUMENT_ID)
            .order("chunk_index")
            .execute()
        )
        rows = result.data or []
        if not rows:
            logger.error(
                "No chunks found for position paper document_id=%s — position-paper serving disabled for this call",
                PAPER_DOCUMENT_ID,
            )
            return
        raw = "\n\n".join(r["content"] for r in rows)
        body = _strip_frontmatter(raw)
        _paper_body_cache = {"loaded": True, "body": body}
        logger.info(
            "Loaded position paper body from chunks table (document_id=%s, %d chunks, %d chars)",
            PAPER_DOCUMENT_ID, len(rows), len(body),
        )
    except Exception:
        logger.exception(
            "Failed to load position paper chunks for document_id=%s — position-paper serving disabled for this call",
            PAPER_DOCUMENT_ID,
        )


def get_paper_body() -> Optional[str]:
    """Return the cached, frontmatter-stripped paper body, or None if it
    could not be loaded (see _ensure_paper_body's fail-soft note)."""
    _ensure_paper_body()
    if not _paper_body_cache["loaded"]:
        return None
    return _paper_body_cache["body"]  # type: ignore[return-value]


def _sse(data: str) -> str:
    """Same SSE framing as chat.py's _sse() — duplicated here (not
    imported) to keep this module import-independent of chat.py, since
    chat.py imports FROM this module."""
    return f"data: {data}\n\n"


def generate_position_paper_answer(question: str, messages: Optional[List[object]] = None) -> Iterator[str]:
    """Stream an SSE token event per output chunk for a position-paper-
    grounded answer to `question`, using POSITION_PAPER_VOICE_SYSTEM +
    the loaded paper body as system context and the real conversation
    history (if any) as prior turns.

    `messages` accepts the same shape as chat.py's ChatRequest.messages
    (a list of objects/dicts with .role/.content or ["role"]/["content"]) —
    duck-typed here rather than importing chat.py's ChatMessage, to avoid a
    circular import (chat.py imports from this module).

    No <answer> tag parsing is needed or performed: this dedicated prompt
    does not wrap its output in XML tags, so every content_block_delta is
    streamed directly as a token event.
    """
    paper_body = get_paper_body()
    if paper_body is None:
        logger.error("Position paper body unavailable — cannot generate position-paper answer")
        yield _sse(json.dumps({"error": "position_paper_unavailable"}))
        return

    system_blocks = [
        {
            "type": "text",
            "text": POSITION_PAPER_VOICE_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (
                "Here is the full body of what Rhemata teaches on this topic — "
                "treat this as your own settled understanding, not as an "
                "external source to cite:\n\n" + paper_body
            ),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    history = []  # type: List[Dict[str, str]]
    msgs = messages or []
    recent = msgs[-6:] if len(msgs) > 6 else msgs
    for msg in recent:
        role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    history.append({"role": "user", "content": question})

    try:
        client = get_anthropic_client()
        stream = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2048,
            system=system_blocks,
            messages=history,
            stream=True,
        )
        for event in stream:
            if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                text = event.delta.text
                if text:
                    yield _sse(json.dumps({"token": text}))
    except Exception:
        logger.exception("Position-paper LLM stream failed")
        yield _sse(json.dumps({"error": "AI service temporarily unavailable"}))
