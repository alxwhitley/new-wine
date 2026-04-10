"""
Shared Bible reference extraction via Groq Llama 3.3 70B.

Used by:
- scripts/ingest.py              (populate bible_references on insert)
- scripts/ingest_magazine.py     (populate bible_references on insert)
- extract_bible_refs.py          (backfill existing documents)

Public API:
- extract_bible_references(content: str) -> List[str]
    Extracts Bible refs from free text. Segments large content into
    ~12k char chunks, calls Groq per segment, normalizes and dedupes.
    Returns [] on any failure (non-fatal).
"""

import json
import os
import re
from typing import List, Optional

from groq import Groq


MAX_REF_CONTENT_CHARS = 12000
GROQ_MODEL = "llama-3.3-70b-versatile"


_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


BIBLE_REF_SYSTEM_PROMPT = """You are a Bible reference extractor. Extract all Bible verse references from the text below and return them in canonical format.

RULES:
- Canonical format: "Book Chapter:Verse" (e.g. "Romans 8:28") or "Book Chapter" for whole-chapter references (e.g. "Psalm 23")
- Use FULL book names. Examples: "1 Corinthians" not "1 Cor", "John" not "Jn", "Psalm" not "Ps", "Revelation" not "Rev", "Matthew" not "Mt"
- For verse ranges, keep as range: "Romans 8:28-30"
- For multiple non-contiguous verses in the same chapter (e.g. "Romans 8:28, 30"), return them as separate entries: ["Romans 8:28", "Romans 8:30"]
- Deduplicate — each reference should appear only once in the output
- Only extract references that are explicitly cited in the text (e.g. "Romans 8:28", "John 3", "Ps 23:1"). Do NOT infer references from paraphrased content or quoted passages that are not labeled with a reference
- Skip ambiguous, misspelled, or clearly-not-a-Bible-reference strings
- Return JSON only: {"bible_references": ["Romans 8:28", "John 3:16", ...]}
- If no references found, return: {"bible_references": []}"""


# Canonical 66-book names used for validation.
_CANONICAL_BOOKS = {
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy", "Joshua", "Judges",
    "Ruth", "1 Samuel", "2 Samuel", "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles",
    "Ezra", "Nehemiah", "Esther", "Job", "Psalm", "Proverbs", "Ecclesiastes",
    "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy", "Titus",
    "Philemon", "Hebrews", "James", "1 Peter", "2 Peter", "1 John", "2 John",
    "3 John", "Jude", "Revelation",
}


# Common abbreviations/variants → canonical name. Keys are lowercase, normalized.
_BOOK_ALIASES = {
    # Old Testament
    "gen": "Genesis", "ge": "Genesis", "gn": "Genesis",
    "exo": "Exodus", "ex": "Exodus", "exod": "Exodus",
    "lev": "Leviticus", "lv": "Leviticus",
    "num": "Numbers", "nu": "Numbers", "nm": "Numbers", "nb": "Numbers",
    "deut": "Deuteronomy", "dt": "Deuteronomy", "deu": "Deuteronomy",
    "josh": "Joshua", "jos": "Joshua", "jsh": "Joshua",
    "judg": "Judges", "jdg": "Judges", "jg": "Judges",
    "rut": "Ruth", "rth": "Ruth",
    "1 sam": "1 Samuel", "1sam": "1 Samuel", "1sa": "1 Samuel",
    "i sam": "1 Samuel", "i samuel": "1 Samuel", "first samuel": "1 Samuel",
    "2 sam": "2 Samuel", "2sam": "2 Samuel", "2sa": "2 Samuel",
    "ii sam": "2 Samuel", "ii samuel": "2 Samuel", "second samuel": "2 Samuel",
    "1 kgs": "1 Kings", "1 kings": "1 Kings", "1ki": "1 Kings", "1kg": "1 Kings",
    "i kgs": "1 Kings", "i kings": "1 Kings", "first kings": "1 Kings",
    "2 kgs": "2 Kings", "2 kings": "2 Kings", "2ki": "2 Kings", "2kg": "2 Kings",
    "ii kgs": "2 Kings", "ii kings": "2 Kings", "second kings": "2 Kings",
    "1 chr": "1 Chronicles", "1 chron": "1 Chronicles", "1ch": "1 Chronicles",
    "i chr": "1 Chronicles", "i chronicles": "1 Chronicles", "first chronicles": "1 Chronicles",
    "2 chr": "2 Chronicles", "2 chron": "2 Chronicles", "2ch": "2 Chronicles",
    "ii chr": "2 Chronicles", "ii chronicles": "2 Chronicles", "second chronicles": "2 Chronicles",
    "ezr": "Ezra",
    "neh": "Nehemiah",
    "est": "Esther", "esth": "Esther",
    "jb": "Job",
    "ps": "Psalm", "psa": "Psalm", "pss": "Psalm", "psalms": "Psalm", "psalm": "Psalm",
    "prov": "Proverbs", "pr": "Proverbs", "prv": "Proverbs", "prob": "Proverbs",
    "eccl": "Ecclesiastes", "ecc": "Ecclesiastes", "ec": "Ecclesiastes", "qoh": "Ecclesiastes",
    "song": "Song of Solomon", "sos": "Song of Solomon",
    "song of songs": "Song of Solomon", "songs": "Song of Solomon",
    "canticle of canticles": "Song of Solomon", "canticles": "Song of Solomon",
    "isa": "Isaiah", "is": "Isaiah",
    "jer": "Jeremiah", "je": "Jeremiah",
    "lam": "Lamentations", "la": "Lamentations",
    "ezek": "Ezekiel", "eze": "Ezekiel", "ezk": "Ezekiel",
    "dan": "Daniel", "dn": "Daniel", "da": "Daniel",
    "hos": "Hosea", "ho": "Hosea",
    "joe": "Joel", "jl": "Joel",
    "amo": "Amos", "am": "Amos",
    "obad": "Obadiah", "oba": "Obadiah", "ob": "Obadiah",
    "jon": "Jonah", "jnh": "Jonah",
    "mic": "Micah", "mi": "Micah",
    "nah": "Nahum", "na": "Nahum",
    "hab": "Habakkuk", "hb": "Habakkuk",
    "zeph": "Zephaniah", "zep": "Zephaniah", "zp": "Zephaniah",
    "hag": "Haggai", "hg": "Haggai",
    "zech": "Zechariah", "zec": "Zechariah", "zc": "Zechariah",
    "mal": "Malachi", "ml": "Malachi",
    # New Testament
    "matt": "Matthew", "mt": "Matthew", "mat": "Matthew",
    "mk": "Mark", "mrk": "Mark", "mar": "Mark",
    "lk": "Luke", "luk": "Luke", "lu": "Luke",
    "jn": "John", "jhn": "John", "joh": "John",
    "act": "Acts",
    "rom": "Romans", "ro": "Romans", "rm": "Romans",
    "1 cor": "1 Corinthians", "1cor": "1 Corinthians", "1co": "1 Corinthians",
    "i cor": "1 Corinthians", "i corinthians": "1 Corinthians", "first corinthians": "1 Corinthians",
    "2 cor": "2 Corinthians", "2cor": "2 Corinthians", "2co": "2 Corinthians",
    "ii cor": "2 Corinthians", "ii corinthians": "2 Corinthians", "second corinthians": "2 Corinthians",
    "gal": "Galatians", "ga": "Galatians",
    "eph": "Ephesians", "ep": "Ephesians",
    "phil": "Philippians", "php": "Philippians", "pp": "Philippians",
    "col": "Colossians", "co": "Colossians",
    "1 thess": "1 Thessalonians", "1 thes": "1 Thessalonians", "1th": "1 Thessalonians",
    "i thess": "1 Thessalonians", "i thessalonians": "1 Thessalonians", "first thessalonians": "1 Thessalonians",
    "2 thess": "2 Thessalonians", "2 thes": "2 Thessalonians", "2th": "2 Thessalonians",
    "ii thess": "2 Thessalonians", "ii thessalonians": "2 Thessalonians", "second thessalonians": "2 Thessalonians",
    "1 tim": "1 Timothy", "1tim": "1 Timothy", "1ti": "1 Timothy",
    "i tim": "1 Timothy", "i timothy": "1 Timothy", "first timothy": "1 Timothy",
    "2 tim": "2 Timothy", "2tim": "2 Timothy", "2ti": "2 Timothy",
    "ii tim": "2 Timothy", "ii timothy": "2 Timothy", "second timothy": "2 Timothy",
    "tit": "Titus", "ti": "Titus",
    "philem": "Philemon", "phm": "Philemon", "phlm": "Philemon",
    "heb": "Hebrews", "he": "Hebrews",
    "jas": "James", "jm": "James",
    "1 pet": "1 Peter", "1pet": "1 Peter", "1pe": "1 Peter",
    "i pet": "1 Peter", "i peter": "1 Peter", "first peter": "1 Peter",
    "2 pet": "2 Peter", "2pet": "2 Peter", "2pe": "2 Peter",
    "ii pet": "2 Peter", "ii peter": "2 Peter", "second peter": "2 Peter",
    "1 jn": "1 John", "1jn": "1 John", "1jo": "1 John", "1 john": "1 John",
    "i jn": "1 John", "i john": "1 John", "first john": "1 John",
    "2 jn": "2 John", "2jn": "2 John", "2jo": "2 John", "2 john": "2 John",
    "ii jn": "2 John", "ii john": "2 John", "second john": "2 John",
    "3 jn": "3 John", "3jn": "3 John", "3jo": "3 John", "3 john": "3 John",
    "iii jn": "3 John", "iii john": "3 John", "third john": "3 John",
    "jud": "Jude", "jd": "Jude",
    "rev": "Revelation", "re": "Revelation", "rv": "Revelation", "apoc": "Revelation",
    "apocalypse": "Revelation",
}


# Matches "Book Chapter" or "Book Chapter:Verse[s]".
# Book group allows a leading 1/2/3 digit + optional space.
_REF_PATTERN = re.compile(
    r"^\s*(?P<book>(?:[1-3]\s*)?[A-Za-z][A-Za-z\s]*?)\s+"
    r"(?P<chap>\d+)"
    r"(?::(?P<verses>[\d,\-\s]+))?\s*$"
)


def _normalize_book(raw: str) -> Optional[str]:
    """Map a raw book string to its canonical form. Returns None if unknown."""
    key = re.sub(r"\s+", " ", raw.strip()).lower().rstrip(".")
    if not key:
        return None
    if key in _BOOK_ALIASES:
        return _BOOK_ALIASES[key]
    # Try direct title-case match against canonical set
    title = " ".join(w.capitalize() for w in key.split())
    title = title.replace(" Of ", " of ")
    if title in _CANONICAL_BOOKS:
        return title
    return None


def _normalize_ref(ref: str) -> Optional[str]:
    """Normalize a single reference string to 'Book Chapter[:Verse]'.
    Returns None if the reference cannot be parsed to a canonical book."""
    if not ref:
        return None
    ref = ref.strip().rstrip(".")
    if not ref:
        return None
    m = _REF_PATTERN.match(ref)
    if not m:
        return None
    book = _normalize_book(m.group("book"))
    if not book:
        return None
    chap = m.group("chap")
    verses = m.group("verses")
    if verses:
        verses_clean = re.sub(r"\s+", "", verses)
        return f"{book} {chap}:{verses_clean}"
    return f"{book} {chap}"


def normalize_refs(raw_refs: List[str]) -> List[str]:
    """Normalize and dedupe a list of raw references. Preserves first-seen order."""
    seen = set()
    out: List[str] = []
    for r in raw_refs:
        norm = _normalize_ref(str(r))
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _parse_json_response(raw: str) -> Optional[dict]:
    """Parse JSON from a Groq response, handling code fences and trailing text."""
    if not raw:
        return None
    json_str = raw
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1).strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass
    obj_match = re.search(r"\{[\s\S]*\}", json_str)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except json.JSONDecodeError:
            return None
    return None


def _extract_from_segment(segment: str) -> List[str]:
    """Call Groq on a single text segment. Returns raw (un-normalized) refs.
    Returns [] on any failure."""
    try:
        response = _get_groq().chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": BIBLE_REF_SYSTEM_PROMPT},
                {"role": "user", "content": f"TEXT:\n{segment}"},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"  Bible ref extraction (Groq) failed: {e}")
        return []

    parsed = _parse_json_response(raw)
    if not parsed:
        print(f"  Bible ref extraction: non-JSON response: {raw[:200]}")
        return []

    refs = parsed.get("bible_references", [])
    if not isinstance(refs, list):
        return []
    return [str(r) for r in refs]


def extract_bible_references(content: str) -> List[str]:
    """Extract Bible references from text via Groq.

    Segments long content into ~12k char chunks and merges results.
    Returns a normalized, deduped list. Returns [] on any failure."""
    if not content or not content.strip():
        return []

    all_raw: List[str] = []
    for start in range(0, len(content), MAX_REF_CONTENT_CHARS):
        segment = content[start:start + MAX_REF_CONTENT_CHARS]
        if not segment.strip():
            continue
        all_raw.extend(_extract_from_segment(segment))

    return normalize_refs(all_raw)
