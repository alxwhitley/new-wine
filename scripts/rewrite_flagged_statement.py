#!/usr/bin/env python3
"""
rewrite_flagged_statement.py — single-statement rewrite tool for statements
flagged by the closeness/citation checks after storage (docs/audits/
statement_recheck_closeness_citation_2026-07-28.md).

NOT a wrapper around store_propositions()'s delete-and-reinsert flow, and
NOT the reference-strip approach (scripts/propositions.py's
_strip_ungrounded_references) — both were considered and rejected: the
former would delete and non-deterministically regenerate every sibling
proposition in a flagged statement's document; the latter leaves
grammatically broken text and removes evidence rather than restoring
faithfulness. This tool calls the LLM to produce a fluent, faithful
correction of exactly one existing statement, verifies the fresh draft
against BOTH checks before writing anything, and — only on a pass — UPDATEs
that single row in place.

Alex has explicitly authorized this as a verified-per-row exception to the
2026-07-25 generation stop. The stop otherwise remains in force; nothing
here resumes bulk/document-level extraction.

--------------------------------------------------------------------------
Structurally single-row
--------------------------------------------------------------------------
The only table-modifying SQL statement anywhere in this file is:
    UPDATE propositions SET content = %s, embedding = %s::vector WHERE id = %s
parameterized ONLY by (new_content, new_embedding, proposition_id). No
document_id-scoped statement, no DELETE, no batch UPDATE, appears anywhere
in this module — grep for "propositions" + a write verb to confirm.

--------------------------------------------------------------------------
Verify-before-write gate
--------------------------------------------------------------------------
verify_draft() is a pure function (no DB, no LLM) — call it, get a verdict
dict back, pass it to passes_both() to get a plain bool. rewrite_one()
never reaches the UPDATE unless passes_both(verify_draft(...)) is True.
This separation is what scripts/test_rewrite_flagged_statement.py proves
directly: a draft that fails either check cannot reach the UPDATE, using
the same hand-built FakeConn/FakeCursor convention as
scripts/test_propositions_closeness_gate.py.

--------------------------------------------------------------------------
Provenance (CLAUDE.md Invariant 10)
--------------------------------------------------------------------------
Every write stamps a NEW, distinct prompt_version label ("rewrite_v1") —
not "v3"/"v4"/"legacy_unknown", since this is a materially different
prompt (single-statement correction, not multi-proposition extraction) —
with prompt_fingerprint computed fresh each call as
sha256(REWRITE_PROMPT_V1.encode()).hexdigest(), mirroring
propositions.prompt_fingerprint()'s own convention exactly (hash of the
literal, unfilled template text, never hand-maintained). model reuses
propositions.EXTRACTION_MODEL (same underlying model the "current corrected
generation process" already uses) rather than a duplicated string literal.

--------------------------------------------------------------------------
Retry policy
--------------------------------------------------------------------------
Up to 2 attempts per statement. Attempt 2 (only reached if attempt 1's
draft fails verification) appends a note describing exactly what still
failed, so the model gets one targeted second try rather than a blind
retry. If both attempts fail — or the LLM call/JSON parse fails on both —
the original row is left byte-untouched and the statement is reported
still_failing (or errored, for a call/parse failure), never forced in.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
Python 3.9 syntax (Optional[str], never str | None — Invariant 1). No
module-level client construction or env-var reads beyond what propositions.py
/ closeness_check.py already do (reuses their lazy client getters).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent / "backend"
for _p in (str(_THIS_DIR), str(_BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import closeness_check as cc  # noqa: E402
import reference_grounding as rg  # noqa: E402
import propositions as pw  # noqa: E402

# ── The rewrite prompt — a NEW, distinct instruction template, not v3/v4 ───────
# (v3/v4 extract MANY propositions from a whole document; this corrects ONE
# already-extracted statement against its own document.) Fingerprinted the
# same way propositions.prompt_fingerprint() fingerprints v3/v4: sha256 of
# this exact literal text, computed fresh every call, never hand-maintained.

REWRITE_PROMPT_VERSION = "rewrite_v1"

REWRITE_PROMPT_V1 = """\
You are correcting a single teaching statement that was extracted from a theological source document and later flagged for a specific, named defect. Your job is to produce ONE corrected statement that preserves the original teaching claim while fixing exactly the defect described below.

THE GOVERNING RULE — FOUR CORNERS. Use ONLY what is physically present in the source document text provided below. You may not add anything from your own knowledge — not a Bible reference, not an example, not a cross-reference, not a related verse, not background context. If it is not in the provided source text, it does not exist for this task.

THE ORIGINAL STATEMENT (correct this — do not write an unrelated new one):
{original_content}

THE SPECIFIC DEFECT TO FIX:
{defect_description}

RULES FOR THE CORRECTION:
1. Preserve the original statement's substance: the same teaching claim, the same specific details (names, numbers, illustrations) it already contains. You are correcting this one statement, not re-summarizing the whole source document.
2. Scripture references — if the defect above names a reference the source document does not actually state or quote, remove it entirely. Add a corrected reference in its place ONLY if the source document genuinely names a different, correct reference for this exact claim. Never supply a reference the source doesn't contain, and never guess at one.
3. Change wording only where necessary to fix the named defect and keep the result grammatically fluent. If the defect is a citation problem only, keep the rest of the sentence's wording as close to the original as reasonably possible — do not rewrite unrelated portions of the statement.
4. If the defect requires rephrasing away from the source's own wording, do a full rewrite in your own words for the affected portion. Never reproduce three or more consecutive words from the source document in your revision (quoted scripture wording excepted).
5. The corrected statement MUST read as fluent, complete, grammatically correct prose — full sentences, no dangling clauses, no orphaned connector words, no leftover fragments from the defect. This is the most important rule: a technically-passing but ungrammatical sentence is not an acceptable correction.
6. Keep the same attributive voice the original statement already uses (e.g. if it says "The author teaches...", keep that framing — do not switch styles). Neutral voice — never use charged language ("heretical," "demonic," "apostate") in your own voice even if the source does.
7. Similar length to the original statement — do not pad or drastically shorten it.

Output ONLY a JSON object, no preamble, no markdown fences, no explanation:
{{"content": "..."}}

SOURCE DOCUMENT TEXT (the ONLY source of truth — nothing outside it is permitted):
{source_text}
"""


def rewrite_prompt_fingerprint() -> str:
    """sha256 of REWRITE_PROMPT_V1's literal, unfilled text — mirrors
    propositions.prompt_fingerprint()'s exact convention (hash the raw
    template, not any per-call filled-in variable content)."""
    return hashlib.sha256(REWRITE_PROMPT_V1.encode("utf-8")).hexdigest()


class RewriteFailed(Exception):
    """The LLM call itself failed, or its response didn't parse as the
    expected JSON shape. Distinct from a draft that parsed fine but failed
    verification — mirrors propositions.PropositionExtractionFailed's own
    "a failed call must never be indistinguishable from a legitimate
    result" rationale."""


def build_defect_description(
    citation_fail: bool, closeness_fail: bool,
    failing_references: List[str], flagged_span: Optional[str],
    retry_note: Optional[str] = None,
) -> str:
    parts = []
    if citation_fail:
        refs = ", ".join(failing_references) if failing_references else "an unspecified reference"
        parts.append(
            f"This statement contains the following scripture reference(s) that the "
            f"source document does NOT actually state or quote: {refs}."
        )
    if closeness_fail:
        span_note = f" The following span was flagged as near-verbatim: {flagged_span!r}." if flagged_span else ""
        parts.append(
            "This statement's wording overlaps too closely with the source document's "
            "own phrasing." + span_note + " Rephrase it in your own words while preserving its meaning."
        )
    if retry_note:
        parts.append(f"NOTE: a previous attempt to fix this defect still failed verification: {retry_note} "
                      "Make sure your revision genuinely fixes this before responding.")
    return " ".join(parts)


def call_rewrite_llm(original_content: str, source_text: str, defect_description: str) -> str:
    """One Groq call. Returns the raw `content` string from the parsed JSON
    response. Raises RewriteFailed on any network/parse failure — never
    returns a partial or guessed result."""
    prompt = REWRITE_PROMPT_V1.format(
        original_content=original_content,
        defect_description=defect_description,
        source_text=source_text,
    )
    try:
        client = pw._get_groq()
        resp = client.chat.completions.create(
            model=pw.EXTRACTION_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1024,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        content = parsed["content"]
        if not isinstance(content, str) or not content.strip():
            raise RewriteFailed("empty or non-string 'content' in LLM response")
        return content.strip()
    except RewriteFailed:
        raise
    except Exception as exc:
        raise RewriteFailed(str(exc)) from exc


class DraftVerdict(NamedTuple):
    closeness_verdict: str
    closeness_containment: float
    closeness_residual_tokens: int
    citation_verdict: str  # pass | fail | uncertain | no_references
    citation_failing_references: List[str]


def verify_draft(
    content: str, source_text: str, name_pattern, verse_lookup: Dict[str, str], vocab_matcher,
) -> DraftVerdict:
    """Pure — no DB, no LLM, no side effects. Runs the SAME two checks used
    corpus-wide (closeness_check.classify / reference_grounding.
    check_reference_grounded) against a fresh draft. This is the function
    scripts/test_rewrite_flagged_statement.py calls directly to prove the
    gate's logic in isolation."""
    cr = cc.classify(content, source_text, name_pattern, verse_lookup, vocab_matcher)
    spans = rg.find_reference_spans(content)
    failing: List[str] = []
    any_uncertain = False
    for span in spans:
        gr = rg.check_reference_grounded(span.raw, source_text, verse_lookup)
        if gr.status == rg.UNGROUNDED:
            failing.append(span.raw)
        elif gr.status == rg.UNCERTAIN:
            any_uncertain = True
    if failing:
        cit = "fail"
    elif any_uncertain:
        cit = "uncertain"
    elif spans:
        cit = "pass"
    else:
        cit = "no_references"
    return DraftVerdict(
        closeness_verdict=cr.verdict,
        closeness_containment=cr.containment,
        closeness_residual_tokens=cr.residual_tokens,
        citation_verdict=cit,
        citation_failing_references=failing,
    )


def passes_both(v: DraftVerdict) -> bool:
    """The gate. A draft may only reach the UPDATE if this returns True."""
    return v.closeness_verdict == "PASS" and v.citation_verdict in ("pass", "no_references")


def failure_reason(v: DraftVerdict) -> str:
    reasons = []
    if v.closeness_verdict != "PASS":
        reasons.append(f"closeness={v.closeness_verdict} (containment={v.closeness_containment:.3f})")
    if v.citation_verdict not in ("pass", "no_references"):
        reasons.append(f"citation={v.citation_verdict} refs={v.citation_failing_references}")
    return "; ".join(reasons) if reasons else "unknown"


def write_single_row(conn, prop_id: str, new_content: str, new_embedding: List[float]) -> None:
    """The ONLY table-modifying statement in this module. WHERE clause is
    id-only — structurally incapable of touching any other row, no matter
    what document_id/proposition_index the caller has in scope.

    Stamps real provenance (CLAUDE.md Invariant 10) on every write: this
    row's prompt_version/prompt_fingerprint/model now describe THIS
    correction event, not whatever produced the original (mostly
    legacy_unknown/NULL) content — an unstamped write here would silently
    reopen the exact hole Invariant 10 exists to close."""
    embedding_str = "[" + ",".join(str(v) for v in new_embedding) + "]"
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE propositions SET content = %s, embedding = %s::vector, "
            "prompt_version = %s, prompt_fingerprint = %s, model = %s WHERE id = %s",
            (
                new_content, embedding_str,
                REWRITE_PROMPT_VERSION, rewrite_prompt_fingerprint(), pw.EXTRACTION_MODEL,
                prop_id,
            ),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"expected to update exactly 1 row for id={prop_id}, updated {cur.rowcount}")
    conn.commit()


def rewrite_one(
    conn_factory,
    embed_fn,
    prop_id: str,
    document_id: str,
    original_content: str,
    source_text: str,
    name_pattern,
    verse_lookup: Dict[str, str],
    vocab_matcher,
    citation_fail: bool,
    closeness_fail: bool,
    failing_references: List[str],
    flagged_span: Optional[str] = None,
    dry_run: bool = True,
    max_attempts: int = 2,
) -> dict:
    """Orchestrates one statement's full cycle: rewrite -> verify draft ->
    (if not dry_run and passing) write -> re-query live -> re-verify live.
    Never touches any row but prop_id. Returns a structured result dict;
    never raises for an ordinary rewrite/verify failure (those are reported
    in the returned dict's "status" field) — only a genuine bug (e.g. the
    UPDATE affecting != 1 row) propagates."""
    retry_note: Optional[str] = None
    last_verdict: Optional[DraftVerdict] = None
    last_draft: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        defect_description = build_defect_description(
            citation_fail, closeness_fail, failing_references, flagged_span, retry_note,
        )
        try:
            draft = call_rewrite_llm(original_content, source_text, defect_description)
        except RewriteFailed as exc:
            last_verdict = None
            last_draft = None
            if attempt == max_attempts:
                return {
                    "prop_id": prop_id, "status": "errored", "attempts": attempt,
                    "reason": f"LLM call/parse failed: {exc}",
                }
            retry_note = f"the LLM call itself failed ({exc})"
            continue

        verdict = verify_draft(draft, source_text, name_pattern, verse_lookup, vocab_matcher)
        last_verdict = verdict
        last_draft = draft

        if passes_both(verdict):
            result = {
                "prop_id": prop_id, "document_id": document_id, "status": "draft_passes",
                "attempts": attempt, "old_content": original_content, "new_content": draft,
                "verdict": verdict._asdict(),
            }
            if dry_run:
                result["status"] = "dry_run_pass"
                return result

            new_embedding = embed_fn(draft)
            conn = conn_factory()
            try:
                write_single_row(conn, prop_id, draft, new_embedding)
            except Exception:
                conn.rollback()
                conn.close()
                raise
            conn.close()

            live = fetch_live_row(prop_id)
            if live is None or live["content"] != draft:
                result["status"] = "write_verification_failed"
                return result

            live_verdict = verify_draft(live["content"], source_text, name_pattern, verse_lookup, vocab_matcher)
            result["live_verdict"] = live_verdict._asdict()
            result["status"] = "fixed" if passes_both(live_verdict) else "write_verification_failed"
            return result

        retry_note = failure_reason(verdict)

    return {
        "prop_id": prop_id, "document_id": document_id, "status": "still_failing",
        "attempts": max_attempts, "old_content": original_content,
        "last_draft": last_draft, "last_verdict": last_verdict._asdict() if last_verdict else None,
        "reason": failure_reason(last_verdict) if last_verdict else "no valid draft produced",
    }


def fetch_live_row(prop_id: str) -> Optional[dict]:
    import detect_reference_fabrication as drf
    params = drf.db_params()
    import psycopg2
    conn = psycopg2.connect(**params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id::text, document_id::text, content, proposition_index FROM propositions WHERE id::text = %s",
            (prop_id,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if row is None:
        return None
    return {"id": row[0], "document_id": row[1], "content": row[2], "proposition_index": row[3]}
