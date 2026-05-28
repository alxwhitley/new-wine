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
cultural and historical context for this Bible verse from a Messianic Jewish perspective.

Only use sources from this approved domain list:
ffoz.org, jewsforjesus.org, oneforisrael.org, umjc.org, messianicstudies.com, \
engediresourcecenter.com, ourrabbijesus.com, ray-vander-laan.com, followtherabbi.com, \
sefaria.org, bibleproject.com, biblicalarchaeology.org, bible.org

Do not use any sources outside this list. If no relevant content is found on these domains \
for a section, write: "No source material found for this verse under this category."

Do not add devotional application or charismatic interpretation.
Cite every claim by author or organization name.
Do not fabricate citations.

Output as JSON only with this exact structure — no preamble, no markdown fences:
{
  "jewish_background": "prose text with citations",
  "messianic_perspective": "prose text with citations",
  "cultural_context": "prose text with citations",
  "sources": ["Author Name — Article Title — URL", ...]
}
"""

SECTION_KEYS = ["jewish_background", "messianic_perspective", "cultural_context"]


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


def _repair_truncated_json(raw):
    # type: (str) -> Optional[dict]
    """Attempt to repair truncated JSON by finding the last complete key-value pair."""
    # Strip markdown code fences if present
    m = re.search(r'```(?:json)?\s*(.*)', raw, re.DOTALL)
    if m:
        raw = m.group(1).rstrip('`').strip()

    # Must start with {
    if not raw.lstrip().startswith("{"):
        return None

    # Find the last complete quoted-string value ending with ," or "} or "\n
    # Pattern: find last occurrence of a complete "key": "value" pair
    last_good = None
    for match in re.finditer(r'"(jewish_background|messianic_perspective|cultural_context|sources)"\s*:\s*"', raw):
        key_start = match.start()
        val_start = match.end()
        # Walk forward to find the closing unescaped quote
        i = val_start
        while i < len(raw):
            if raw[i] == '\\':
                i += 2  # skip escaped character
                continue
            if raw[i] == '"':
                # Found closing quote — this key-value pair is complete
                last_good = i + 1
                break
            i += 1

    if not last_good:
        return None

    # Truncate after the last complete value and close the object
    truncated = raw[:last_good].rstrip().rstrip(",")
    if not truncated.endswith("}"):
        truncated += "\n}"

    try:
        return json.loads(truncated)
    except json.JSONDecodeError:
        return None


def _parse_gemini_json(raw_text, ref):
    # type: (str, str) -> dict
    """Parse Gemini JSON response with markdown extraction and truncation recovery."""
    # Try direct parse
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    m = re.search(r'```(?:json)?\s*(.*?)```', raw_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Truncation recovery
    repaired = _repair_truncated_json(raw_text)
    if repaired:
        missing = [k for k in SECTION_KEYS if k not in repaired]
        if missing:
            for k in missing:
                repaired[k] = "Content was truncated during generation. Please regenerate."
        logger.warning("Truncation recovery used for %s — repaired %d of %d sections", ref, len(SECTION_KEYS) - len(missing), len(SECTION_KEYS))
        return repaired

    logger.error("Failed to parse Gemini JSON for %s: %s", ref, raw_text[:500])
    raise HTTPException(status_code=500, detail="Failed to parse generated content")


def _migrate_old_content(content):
    # type: (dict) -> dict
    """Ensure cached content has expected shape regardless of format version."""
    if "sources" not in content:
        content["sources"] = []
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

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    model_id = "gemini-2.5-flash"

    user_message = "Verse: {}\nVerse text: {}".format(ref, verse_text)

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=4096,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        raw_text = response.text
    except Exception as e:
        logger.exception("Gemini call failed for %s", ref)
        raise HTTPException(status_code=500, detail="Failed to generate Jewish perspective")

    # Parse JSON from response, with truncation recovery
    content = _parse_gemini_json(raw_text, ref)

    # Ensure sources key exists (Gemini should include it in the JSON)
    if "sources" not in content or not isinstance(content.get("sources"), list):
        content["sources"] = []

    # Save to cache
    try:
        db.table("jewish_perspectives").insert({
            "verse_reference": ref,
            "content": content,
            "model": model_id,
        }).execute()
    except Exception:
        logger.exception("Failed to cache jewish_perspective for %s", ref)

    return {"cached": False, "content": content}
