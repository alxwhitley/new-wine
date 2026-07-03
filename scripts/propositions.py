"""
propositions.py — shared module for proposition extraction and storage.

Called by ingest scripts after chunk insertion for unlicensed and licensed
documents (see process_document's gate). Non-fatal by contract: no public
function raises.
"""

import json
import logging
import os
import re
import uuid
from typing import Callable, List, Optional

from groq import Groq

logger = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are extracting propositions from a single theological document for a research tool. A proposition is one self-contained teaching claim from the document, restated entirely in your own words.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the document text provided. You are summarizing this one document, not teaching the topic. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided text, it does not exist for this task. When in doubt, leave it out.

Applying that rule:

Scripture references — capture every one the source gives, invent none it doesn't. If the document explicitly prints a reference (e.g. the text says "Hebrews 3:1" or "Mark 11:23"), and a proposition covers that teaching, that reference MUST appear in the proposition. At the same time: if the author quotes or alludes to a verse without naming it, restate the teaching but do NOT supply the reference, even if you recognize the verse. Two equal failures to avoid: dropping a reference the author printed, and adding one the author didn't. Capture what's there; invent nothing that isn't.
Examples and illustrations: Use only the examples the document actually contains. Never introduce an illustration, story, or analogy of your own.
Claims: Represent only what the document asserts. Do not extend, infer, or theologize beyond it.

Paraphrase rules:

Full rewrite in your own words. Never reuse the author's distinctive phrasing or sentence structure. Never reproduce three or more consecutive words from the source (quoted scripture excepted — scripture wording may stand). If a restatement starts mirroring the original, rebuild it from scratch.
This applies even to short, simple, or definitional sentences — those are the easiest to copy by accident. For example, if the author writes "A disciple is simply a follower of Christ," do not reuse that clause; restructure the idea, e.g. "The author defines discipleship plainly — following Christ, not attaining a special status." Only quoted scripture wording may stand unchanged.
Attribute naturally ("the author teaches…") but only to what the author actually said.
Neutral voice. Never use charged language ("heretical," "demonic," "apostate") in your own voice even if the source does.

Count and distinctness:

Extract one proposition per genuinely distinct teaching point. There is NO target number. Short documents may yield three or four; long ones more. Do not pad.
If two points make substantially the same claim, MERGE them into one. Near-duplicate propositions are a failure.

Length: ~80–150 words each.

Output ONLY a JSON array, no preamble, no markdown fences:
[{"proposition_index": 1, "content": "..."}, {"proposition_index": 2, "content": "..."}]"""

# ── Groq client (lazy) ────────────────────────────────────────────────────────

_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# ── Public API ────────────────────────────────────────────────────────────────

def extract_propositions(text: str, doc_id: str = "") -> List[dict]:
    """Send text to Groq and return parsed proposition list.

    Returns [] on any failure — never raises.
    Logs PROPOSITION_EXTRACT_FAIL on error.
    """
    try:
        client = _get_groq()
        msg = f"{EXTRACTION_PROMPT}\n\n---\n\n{text}"
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": msg}],
            temperature=0.2,
            max_tokens=8192,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        logger.warning("PROPOSITION_EXTRACT_FAIL doc=%r error=%s", doc_id, exc)
        return []


def get_license_status(conn, source_id: str) -> Optional[str]:
    """Return license_status for source_id, or None if not found."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT license_status FROM sources WHERE id = %s",
            (source_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def store_propositions(
    conn,
    document_id: str,
    propositions: List[dict],
    embed_fn: Callable[[str], List[float]],
) -> int:
    """Clear existing propositions for document_id, then embed and insert new ones.

    Commits the transaction. Returns count inserted.
    fts column is GENERATED ALWAYS AS STORED — not included in INSERT.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM propositions WHERE document_id = %s",
            (document_id,),
        )

        inserted = 0
        for prop in propositions:
            content = prop["content"]
            prop_index = prop["proposition_index"]
            embedding = embed_fn(content)
            embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
            cur.execute(
                """INSERT INTO propositions
                       (id, document_id, content, embedding, proposition_index)
                   VALUES (%s, %s, %s, %s::vector, %s)""",
                (
                    str(uuid.uuid4()),
                    document_id,
                    content,
                    embedding_str,
                    prop_index,
                ),
            )
            inserted += 1

    conn.commit()
    return inserted


def process_document(
    conn,
    document_id: str,
    source_id: str,
    text: str,
    embed_fn: Callable[[str], List[float]],
) -> str:
    """Top-level entry point for ingest scripts.

    Returns one of:
      "skipped_licensed"   — source is owned/public_domain (or missing); nothing written
      "no_propositions"    — extraction returned empty list
      "stored:{n}"         — n propositions written to DB
      "error"              — unexpected failure (logged)

    Extracts for "unlicensed" and "licensed" sources only. Skips "owned" and
    "public_domain" (already safely servable as verbatim chunks -- no future
    license-grant toggle applies, so propositions add cost with no serving
    benefit) and skips a missing/unknown source_id (fail closed, same as the
    original unlicensed-only gate did for None).

    Never raises.
    """
    try:
        license_status = get_license_status(conn, source_id)
        if license_status not in ("unlicensed", "licensed"):
            return "skipped_licensed"

        props = extract_propositions(text, doc_id=document_id)
        if not props:
            return "no_propositions"

        count = store_propositions(conn, document_id, props, embed_fn)
        return f"stored:{count}"
    except Exception as exc:
        logger.warning(
            "PROPOSITION_PROCESS_FAIL doc=%r source=%r error=%s",
            document_id, source_id, exc,
        )
        try:
            conn.rollback()
        except Exception:
            pass
        return "error"
