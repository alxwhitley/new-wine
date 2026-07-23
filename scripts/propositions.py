"""
propositions.py — shared module for proposition extraction and storage.

Called by ingest scripts after chunk insertion. Gate: extracts for licensed
and unlicensed sources only (skips public_domain and owned), with Precept
Austin locked out by name (see process_document). Non-fatal by contract: no
public function raises.
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

# ── v4 prompt (2026-07-16, revised 2026-07-23) ────────────────────────────────
# Added alongside EXTRACTION_PROMPT (v3), which is unchanged and remains the
# default. Selected via extract_propositions(prompt_version="v4", speaker=...).
# Original three changes from v3:
#   1. Length: v3's length line was a bare, unexplained number ("~80-150 words
#      each") sitting directly after count/dedup language ("do not pad" /
#      "merge near-duplicates") that governs proposition COUNT, not length --
#      the adjacency plausibly caused the model to read "don't pad" as
#      governing length too. Observed result: median 40 words against a
#      stated 80-150 target. v4 gives length its own clearly separated
#      section, states explicitly what should fill the space (claim +
#      grounding + qualification), and gives a worked thin-vs-complete
#      example, matching the weight every other rule in this prompt already
#      gets.
#   2. Attribution: v3 explicitly modeled "the author teaches..." as the
#      correct form, which is why every v3 proposition uses that exact
#      framing. v4 removes it and requires the passed-in speaker name instead
#      (or no attributive frame at all).
#   3. Voice: v3's paraphrase rules are entirely about NOT copying wording;
#      nothing tells the model to keep concrete specifics once it starts
#      generalizing wording, so specifics get abstracted away along with the
#      phrasing. v4 separates "generalize the wording" from "preserve the
#      content" explicitly.
#
# 2026-07-23 revision (4th change, sentence structure): a 5-teacher/15-doc
# sample test found #2 fixed outright (zero "the author" instances) but #1
# only partially -- average landed at ~62 words against the 80-150 target,
# one document relapsing to the pre-fix ~40 word average. Manual review of
# the raw output found the likely cause: the model was writing each
# proposition as a single run-on sentence chaining claims with repeated
# "and that... and that..." constructions rather than as several well-formed
# sentences -- a chained clause hits a natural stopping point earlier than a
# real paragraph would, capping length artificially. The original "Complete"
# worked example (kept below, now labeled "Thin") was itself a single long
# sentence plus a short second one, which plausibly reinforced the pattern
# rather than correcting it. This revision adds an explicit sentence-count
# instruction (2-4 well-formed sentences, one main idea per sentence) and
# replaces that example with a three-way thin/run-on/well-formed contrast
# using the same content, so the model sees the fix is about restructuring,
# not padding. Nothing else changed: attribution, specifics-preservation,
# the four-corners rule, scripture-reference capture, no-3+-consecutive-
# words, neutral voice, and JSON-only output are all untouched.
EXTRACTION_PROMPT_V4 = """\
You are extracting propositions from a single theological document for a research tool. A proposition is one self-contained teaching claim from the document, restated entirely in your own words — the claim itself, the grounding the speaker gives for it, and any qualification the speaker attaches to it, all in one proposition.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the document text provided. You are summarizing this one document, not teaching the topic. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided text, it does not exist for this task. When in doubt, leave it out.

Applying that rule:

Scripture references — capture every one the source gives, invent none it doesn't. If the document explicitly prints a reference (e.g. the text says "Hebrews 3:1" or "Mark 11:23"), and a proposition covers that teaching, that reference MUST appear in the proposition. At the same time: if the speaker quotes or alludes to a verse without naming it, restate the teaching but do NOT supply the reference, even if you recognize the verse. Two equal failures to avoid: dropping a reference the speaker printed, and adding one the speaker didn't. Capture what's there; invent nothing that isn't.
Examples and illustrations: Use only the examples the document actually contains. Never introduce an illustration, story, or analogy of your own.
Claims: Represent only what the document asserts. Do not extend, infer, or theologize beyond it.
Overstatement and walk-back: if the speaker overstates a claim and then qualifies, hedges, or walks it back within the same passage, both belong in the SAME proposition — the overstatement and its walk-back are one teaching move, not two separate propositions.

Paraphrase rules:

Full rewrite in your own words. Never reuse the speaker's distinctive phrasing or sentence structure. Never reproduce three or more consecutive words from the source (quoted scripture excepted — scripture wording may stand). If a restatement starts mirroring the original, rebuild it from scratch.
This applies even to short, simple, or definitional sentences — those are the easiest to copy by accident. Only quoted scripture wording may stand unchanged.
Neutral voice in your own narration. Never use charged language ("heretical," "demonic," "apostate") as your own assessment even if the source does.

SPEAKER ATTRIBUTION. The speaker is {speaker}. Never write "the author." Either name {speaker} naturally ("{speaker} teaches that...", "{speaker} argues...", "According to {speaker}...") or state the teaching directly with no attributive frame at all (e.g. "Prayer matters more than preaching, because..."). Both are acceptable. "The author" is never acceptable.

PRESERVE THE SPECIFICS. Generalize the WORDING, not the CONTENT. Keep the concrete detail that gives the teaching its force: names, numbers, the specific illustration or story used, the actual shape of the argument (if the speaker reasons "because X, therefore Y," keep that shape — don't flatten it to a bare abstract claim). A paraphrase that keeps only the general idea and drops the specifics has lost the thing worth retrieving, even if every word is original.

SENTENCE STRUCTURE — write 2-4 sentences, not one chained sentence. Each proposition should read as several distinct, well-formed sentences — never as a single sentence that chains multiple claims together with repeated "and that... and that..." constructions. If you notice yourself writing "and that" more than once in one sentence, stop and start a new sentence instead. Break at natural claim boundaries: each sentence carries one main idea (the claim, a piece of grounding, a specific detail, a qualification) rather than piling every piece onto one breathless sentence. This is not about cutting content — the same content reads as 2-4 clear sentences instead of one overloaded one.

LENGTH AND COMPLETENESS. Target 80-150 words across those 2-4 sentences. A proposition this length has room for three things, and each one works better as its own sentence than as a clause bolted onto the last: the claim itself, the grounding or reasoning the speaker gives for it (why they say it, what it's based on), and any qualification, exception, or walk-back the speaker attaches. A 20-30 word proposition is almost always missing one of these three pieces — check what got left out before finalizing.
  Thin (do not do this): "{speaker} teaches that prayer matters more than preaching."
  Run-on (do not do this either — this is the more common failure): "{speaker} teaches that prayer matters more than preaching, and that this is because the disciples asked 'Lord, teach us to pray' rather than 'teach us to preach,' and that this is despite Jesus himself preaching the greatest sermon ever given, and that the point is standing before God on behalf of people outweighs standing before people on behalf of God."
  Well-formed (do this instead): "{speaker} teaches that prayer matters more than preaching. The disciples asked Jesus to teach them to pray, not to preach — even though Jesus himself preached the greatest sermon ever given. The point, {speaker} argues, is that standing before God on behalf of people outweighs standing before people on behalf of God."

Count and distinctness — fewer, fuller propositions is correct. Extract one proposition per genuinely distinct teaching point. There is NO target number. Short documents may yield three or four; long ones more. Do NOT increase the count to hit a length or count target — a document with few distinct points should yield few, fuller propositions, not more thin ones.
If two points make substantially the same claim, MERGE them into one. Near-duplicate propositions are a failure.

Output ONLY a JSON array, no preamble, no markdown fences:
[{{"proposition_index": 1, "content": "..."}}, {{"proposition_index": 2, "content": "..."}}]"""

# ── Groq client (lazy) ────────────────────────────────────────────────────────

_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


# ── Public API ────────────────────────────────────────────────────────────────

class PropositionExtractionFailed(Exception):
    """Raised by extract_propositions() when the model call itself did not
    complete -- network error, rate limit, timeout, or a response that
    doesn't parse as the expected JSON array. Deliberately distinct from a
    genuine empty result: extract_propositions() returning [] must always
    mean the model was called successfully and legitimately found nothing
    to extract, never that the call broke. process_document() catches this
    (it's still an Exception) and reports "error" -- the same signal
    already used for a storage-side failure, since both mean "nothing was
    written, safe to retry," just at different steps.
    """


def extract_propositions(
    text: str,
    doc_id: str = "",
    speaker: Optional[str] = None,
    prompt_version: str = "v3",
) -> List[dict]:
    """Send text to Groq and return parsed proposition list.

    prompt_version: "v3" (default) uses EXTRACTION_PROMPT unchanged -- every
    existing caller (process_document, all ingest scripts) is unaffected.
    "v4" uses EXTRACTION_PROMPT_V4 (fuller length, named-speaker attribution,
    specifics-preserving voice -- see that constant's comment for the full
    diff against v3) and REQUIRES a non-empty `speaker`; raises ValueError
    rather than silently falling back to "the author"-style prose if one
    isn't given.

    Returns [] ONLY for a genuine empty result -- the model was called
    successfully and found nothing worth extracting. Raises
    PropositionExtractionFailed for everything else (network error, rate
    limit, timeout, a response that fails to parse as JSON): a failed call
    must never be indistinguishable from a legitimate empty one.
    """
    if prompt_version == "v4":
        if not speaker:
            raise ValueError("prompt_version='v4' requires a non-empty speaker name")
        prompt = EXTRACTION_PROMPT_V4.format(speaker=speaker)
    else:
        prompt = EXTRACTION_PROMPT
    try:
        client = _get_groq()
        msg = f"{prompt}\n\n---\n\n{text}"
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
        raise PropositionExtractionFailed(str(exc)) from exc


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


# Precept Austin is locked OUT of the propositions layer entirely (decided
# 2026-07-02): its existing excerpts are near-verbatim reorderings of the
# source text, not paraphrases, and fresh Groq extraction was explicitly
# declined. Enforced here by source_id so no caller (including future
# backfills) can wire it in by accident.
PRECEPT_AUSTIN_SOURCE_ID = "698e0596-a9c6-4890-958d-9199f1b8f762"


def process_document(
    conn,
    document_id: str,
    source_id: str,
    text: str,
    embed_fn: Callable[[str], List[float]],
) -> str:
    """Top-level entry point for ingest scripts.

    Returns one of:
      "skipped_licensed"        — source is public_domain/owned (or missing); nothing written
      "skipped_precept_austin"  — Precept Austin, locked out by name; nothing written
      "no_propositions"         — the model ran successfully and genuinely found nothing
                                   to extract. A completed result, not a failure.
      "stored:{n}"              — n propositions written to DB
      "error"                   — the extraction call itself failed (network, rate limit,
                                   timeout, unparseable response) or a later step (license
                                   lookup, storage) failed. Nothing was written; safe to
                                   retry. Distinct from "no_propositions" by construction —
                                   see PropositionExtractionFailed above.

    Gate: extracts for "licensed" and "unlicensed" sources only. Skips
    "public_domain" and "owned" (already safely servable as verbatim
    chunks), and skips a missing/unknown source_id (fail closed). One named
    exception: Precept Austin never gets propositions — see
    PRECEPT_AUSTIN_SOURCE_ID above.

    Never raises.
    """
    try:
        if source_id == PRECEPT_AUSTIN_SOURCE_ID:
            return "skipped_precept_austin"

        license_status = get_license_status(conn, source_id)
        if license_status not in ("licensed", "unlicensed"):
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
