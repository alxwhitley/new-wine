from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import get_optional_user
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

Output as JSON only with this exact structure:
{
  "hebrew_root": "prose text with citations",
  "targumic_usage": "prose text with citations",
  "rabbinic_context": "prose text with citations",
  "messianic_fulfillment": "prose text with citations",
  "sources": ["Author Name — Article Title — URL", ...]
}

If a section has no source material write: "No source material found for this verse under this category."
"""

# Book map for verse_id lookup
BOOK_MAP = {
    "genesis": "GEN", "gen": "GEN",
    "exodus": "EXO", "exo": "EXO", "exod": "EXO",
    "leviticus": "LEV", "lev": "LEV",
    "numbers": "NUM", "num": "NUM",
    "deuteronomy": "DEU", "deut": "DEU", "deu": "DEU",
    "joshua": "JOS", "josh": "JOS", "jos": "JOS",
    "judges": "JDG", "judg": "JDG", "jdg": "JDG",
    "ruth": "RUT", "rut": "RUT",
    "1 samuel": "1SA", "1samuel": "1SA", "1 sam": "1SA", "1sam": "1SA", "1sa": "1SA",
    "2 samuel": "2SA", "2samuel": "2SA", "2 sam": "2SA", "2sam": "2SA", "2sa": "2SA",
    "1 kings": "1KI", "1kings": "1KI", "1 kgs": "1KI", "1kgs": "1KI", "1ki": "1KI",
    "2 kings": "2KI", "2kings": "2KI", "2 kgs": "2KI", "2kgs": "2KI", "2ki": "2KI",
    "1 chronicles": "1CH", "1chronicles": "1CH", "1 chr": "1CH", "1chr": "1CH", "1ch": "1CH",
    "2 chronicles": "2CH", "2chronicles": "2CH", "2 chr": "2CH", "2chr": "2CH", "2ch": "2CH",
    "ezra": "EZR", "ezr": "EZR",
    "nehemiah": "NEH", "neh": "NEH",
    "esther": "EST", "esth": "EST", "est": "EST",
    "job": "JOB",
    "psalms": "PSA", "psalm": "PSA", "psa": "PSA", "ps": "PSA",
    "proverbs": "PRO", "prov": "PRO", "pro": "PRO",
    "ecclesiastes": "ECC", "eccl": "ECC", "ecc": "ECC",
    "song of solomon": "SNG", "song of songs": "SNG", "song": "SNG", "sng": "SNG", "sos": "SNG",
    "isaiah": "ISA", "isa": "ISA",
    "jeremiah": "JER", "jer": "JER",
    "lamentations": "LAM", "lam": "LAM",
    "ezekiel": "EZK", "ezek": "EZK", "ezk": "EZK",
    "daniel": "DAN", "dan": "DAN",
    "hosea": "HOS", "hos": "HOS",
    "joel": "JOL", "jol": "JOL",
    "amos": "AMO", "amo": "AMO",
    "obadiah": "OBA", "obad": "OBA", "oba": "OBA",
    "jonah": "JON", "jon": "JON",
    "micah": "MIC", "mic": "MIC",
    "nahum": "NAM", "nah": "NAM", "nam": "NAM",
    "habakkuk": "HAB", "hab": "HAB",
    "zephaniah": "ZEP", "zeph": "ZEP", "zep": "ZEP",
    "haggai": "HAG", "hag": "HAG",
    "zechariah": "ZEC", "zech": "ZEC", "zec": "ZEC",
    "malachi": "MAL", "mal": "MAL",
    "matthew": "MAT", "matt": "MAT", "mat": "MAT",
    "mark": "MRK", "mrk": "MRK",
    "luke": "LUK", "luk": "LUK",
    "john": "JHN", "jhn": "JHN",
    "acts": "ACT", "act": "ACT",
    "romans": "ROM", "rom": "ROM",
    "1 corinthians": "1CO", "1corinthians": "1CO", "1 cor": "1CO", "1cor": "1CO", "1co": "1CO",
    "2 corinthians": "2CO", "2corinthians": "2CO", "2 cor": "2CO", "2cor": "2CO", "2co": "2CO",
    "galatians": "GAL", "gal": "GAL",
    "ephesians": "EPH", "eph": "EPH",
    "philippians": "PHP", "phil": "PHP", "php": "PHP",
    "colossians": "COL", "col": "COL",
    "1 thessalonians": "1TH", "1thessalonians": "1TH", "1 thess": "1TH", "1thess": "1TH", "1th": "1TH",
    "2 thessalonians": "2TH", "2thessalonians": "2TH", "2 thess": "2TH", "2thess": "2TH", "2th": "2TH",
    "1 timothy": "1TI", "1timothy": "1TI", "1 tim": "1TI", "1tim": "1TI", "1ti": "1TI",
    "2 timothy": "2TI", "2timothy": "2TI", "2 tim": "2TI", "2tim": "2TI", "2ti": "2TI",
    "titus": "TIT", "tit": "TIT",
    "philemon": "PHM", "phlm": "PHM", "phm": "PHM",
    "hebrews": "HEB", "heb": "HEB",
    "james": "JAS", "jas": "JAS",
    "1 peter": "1PE", "1peter": "1PE", "1 pet": "1PE", "1pet": "1PE", "1pe": "1PE",
    "2 peter": "2PE", "2peter": "2PE", "2 pet": "2PE", "2pet": "2PE", "2pe": "2PE",
    "1 john": "1JN", "1john": "1JN", "1 jn": "1JN", "1jn": "1JN",
    "2 john": "2JN", "2john": "2JN", "2 jn": "2JN", "2jn": "2JN",
    "3 john": "3JN", "3john": "3JN", "3 jn": "3JN", "3jn": "3JN",
    "jude": "JUD", "jud": "JUD",
    "revelation": "REV", "rev": "REV",
}


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
        return {"cached": True, "content": result.data[0]["content"]}

    return {"cached": False, "content": None}


class GenerateRequest(BaseModel):
    verse_text: Optional[str] = None


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
                response_mime_type="application/json",
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
