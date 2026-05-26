from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from app.auth import get_optional_user
from app.constants import BOOK_MAP
from app.db.supabase import get_supabase

logger = logging.getLogger(__name__)

router = APIRouter()

SYSTEM_PROMPT = """You are a Messianic Jewish biblical scholar assistant. Research and synthesize \
a substantive summary of how the key words and themes in this verse are understood \
from a Messianic Jewish perspective. Research only from these approved domains:
sefaria.org, thelineoffire.org, oneforisrael.org, bibleproject.com, \
messianicstudies.com, umjc.org, jewsforjesus.org, ffoz.org

Do not use training data. Search the web and pull directly from these domains only.
If a source has no relevant content for this verse, skip it.
Do not add devotional application or charismatic interpretation.
Cite every claim by author or organization name.
Do not fabricate citations.

Output ONLY raw valid JSON with no preamble, no markdown backticks, and no explanation. Use this exact structure:
{
  "hebrew_root": "prose text with citations",
  "targumic_usage": "prose text with citations",
  "rabbinic_context": "prose text with citations",
  "messianic_fulfillment": "prose text with citations"
}

If a section has no source material write: "No source material found for this verse under this category."
"""

SECTION_KEYS = ["hebrew_root", "targumic_usage", "rabbinic_context", "messianic_fulfillment"]


def _parse_ref(ref):
    # type: (str) -> Optional[tuple]
    ref = ref.strip()
    m = re.match(r'^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)$', ref)
    if not m:
        return None
    book_raw = m.group(1).strip().lower()
    chapter = int(m.group(2))
    verse = int(m.group(3))
    book_normalized = re.sub(r'^(\d)\s*', r'\1 ', book_raw).strip()
    abbrev = BOOK_MAP.get(book_normalized) or BOOK_MAP.get(book_normalized.rstrip('s'))
    if not abbrev:
        return None
    return abbrev, chapter, verse


def _get_verse_text(db, verse_reference):
    # type: (object, str) -> Optional[str]
    parsed = _parse_ref(verse_reference)
    if not parsed:
        return None
    abbrev, chapter, verse = parsed
    verse_id = "{}.{}.{}".format(abbrev, chapter, verse)
    result = db.table("verses").select("text").eq("verse_id", verse_id).limit(1).execute()
    if result.data:
        return result.data[0].get("text", "")
    return None


def _require_user(request: Request) -> str:
    """Require authenticated user. Returns user_id or raises 401."""
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    import jwt as pyjwt
    from jwt import PyJWKClient
    import os
    jwks_client = PyJWKClient(os.environ["SUPABASE_JWT_JWKS_URL"])

    token = auth_header[7:]
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id


def _extract_grounding(response, raw_text, content):
    # type: (object, str, dict) -> tuple
    """Extract grounding sources and per-section citation indices from Gemini response.

    Returns (sources, section_citations) where:
    - sources: list of {index, title, url} dicts
    - section_citations: dict mapping section keys to lists of source indices
    """
    sources = []  # type: List[Dict]
    section_citations = {}  # type: Dict[str, List[int]]

    try:
        candidate = response.candidates[0]
        gm = getattr(candidate, "grounding_metadata", None)
        if not gm:
            return sources, section_citations

        # Extract source list from grounding_chunks
        chunks = getattr(gm, "grounding_chunks", None) or []
        for i, chunk in enumerate(chunks):
            web = getattr(chunk, "web", None)
            sources.append({
                "index": i,
                "title": getattr(web, "title", "") if web else "",
                "url": getattr(web, "uri", "") if web else "",
            })

        # Map each section's character range in the raw JSON text
        section_ranges = {}  # type: Dict[str, tuple]
        for key in SECTION_KEYS:
            val = content.get(key, "")
            if not val:
                continue
            pos = raw_text.find(val)
            if pos >= 0:
                section_ranges[key] = (pos, pos + len(val))

        # Map grounding_supports to sections
        supports = getattr(gm, "grounding_supports", None) or []
        section_indices = {k: set() for k in SECTION_KEYS}  # type: Dict[str, set]

        for sup in supports:
            seg = getattr(sup, "segment", None)
            if not seg:
                continue
            start = getattr(seg, "start_index", 0) or 0
            chunk_indices = getattr(sup, "grounding_chunk_indices", []) or []

            for key, (sec_start, sec_end) in section_ranges.items():
                if sec_start <= start < sec_end:
                    section_indices[key].update(chunk_indices)
                    break

        section_citations = {
            k: sorted(v) for k, v in section_indices.items() if v
        }

    except Exception:
        logger.exception("Failed to extract grounding metadata")

    return sources, section_citations


def _migrate_old_content(content):
    # type: (dict) -> dict
    """Migrate old cached content format (sources as plain strings) to new format."""
    sources = content.get("sources", [])
    if sources and isinstance(sources[0], str):
        content["sources"] = [
            {"index": i, "title": s, "url": ""}
            for i, s in enumerate(sources)
        ]
    if "section_citations" not in content:
        content["section_citations"] = {}
    return content


@router.get("/{verse_reference}")
async def get_jewish_perspective(verse_reference: str):
    ref = unquote(verse_reference)
    db = get_supabase()

    result = (
        db.table("jewish_perspectives")
        .select("content, model, generated_at")
        .eq("verse_reference", ref)
        .limit(1)
        .execute()
    )

    if result.data:
        # sources and section_citations are cached permanently with the content — never regenerated
        content = _migrate_old_content(result.data[0]["content"])
        return {"cached": True, "content": content}

    return {"cached": False, "content": None}


@router.post("/{verse_reference}")
async def generate_jewish_perspective(
    verse_reference: str,
    request: Request,
    user_id: str = Depends(_require_user),
):
    ref = unquote(verse_reference)
    db = get_supabase()

    # Check cache first
    existing = (
        db.table("jewish_perspectives")
        .select("content")
        .eq("verse_reference", ref)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {"cached": True, "content": existing.data[0]["content"]}

    # Get verse text
    verse_text = _get_verse_text(db, ref)
    if not verse_text:
        raise HTTPException(status_code=400, detail="Could not find verse text for: " + ref)

    # Call Gemini 2.5 Flash with search grounding
    import os
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    model_id = "gemini-2.5-flash"

    user_message = "Verse: {}\nVerse text: {}".format(ref, verse_text)

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw_text = response.text
    except Exception as e:
        logger.exception("Gemini call failed for %s", ref)
        raise HTTPException(status_code=500, detail="Failed to generate Jewish perspective")

    # Parse JSON from response
    try:
        content = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown code block
        m = re.search(r'```(?:json)?\s*(.*?)```', raw_text, re.DOTALL)
        if m:
            try:
                content = json.loads(m.group(1))
            except json.JSONDecodeError:
                logger.error("Failed to parse Gemini JSON for %s: %s", ref, raw_text[:500])
                raise HTTPException(status_code=500, detail="Failed to parse generated content")
        else:
            logger.error("Failed to parse Gemini JSON for %s: %s", ref, raw_text[:500])
            raise HTTPException(status_code=500, detail="Failed to parse generated content")

    # Extract grounding citations from Gemini response
    sources, section_citations = _extract_grounding(response, raw_text, content)
    # sources and section_citations are cached permanently with the content — never regenerated
    content["sources"] = sources
    content["section_citations"] = section_citations

    # Save to cache (includes sources and section_citations in JSONB)
    try:
        db.table("jewish_perspectives").insert({
            "verse_reference": ref,
            "content": content,
            "model": model_id,
        }).execute()
    except Exception:
        logger.exception("Failed to cache jewish_perspective for %s", ref)

    return {"cached": False, "content": content}
