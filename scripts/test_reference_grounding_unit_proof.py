#!/usr/bin/env python3
"""
test_reference_grounding_unit_proof.py — hand-checkable proof for
reference_grounding.py's check_reference_grounded()/find_reference_spans()
and propositions.py's boundary-safe stripper (_strip_ungrounded_references/
_remove_reference_span). PLAN.md #45, 2026-07-28 root-cause fabrication fix.

Uses REAL reconstructed source text (Leonard Ravenhill, "Paul's Passion,
Preaching, and Praying," document_id c19ad18c-ea97-4841-8fa0-e60afc273521),
per Step A's own findings, not a synthetic source document. Source text is
reconstructed via ONE bulk SELECT over that document's chunks, ordered by
chunk_index -- not per-chunk (N+1 lesson). All DB access here is READ-ONLY
(SELECT chunks.content, and closeness_check.build_verse_lookup()'s own
SELECT verse_id, text FROM verses) -- no writes anywhere in this file.

The test propositions themselves (content strings fed to the stripper) ARE
hand-constructed/synthetic where the task requires an injected fabricated
or boundary-collision reference (there is no other way to test "does a
FABRICATED reference get stripped" than to inject one) -- but the SOURCE
TEXT they're checked against, in every case, is the real corpus document.

Run: python3 scripts/test_reference_grounding_unit_proof.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_grounding as rg  # noqa: E402
import propositions as pm  # noqa: E402
import closeness_check as cc  # noqa: E402

RAVENHILL_DOC_ID = "c19ad18c-ea97-4841-8fa0-e60afc273521"


def _db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _reconstruct_document_text(db_params: dict, document_id: str) -> str:
    """ONE bulk SELECT of every chunk for document_id, ordered by
    chunk_index, joined -- not a per-chunk query (N+1 lesson)."""
    import psycopg2

    conn = psycopg2.connect(**db_params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"No chunks found for document_id={document_id!r} -- check the id.")
    return "\n".join(r[0] for r in rows)


def main() -> None:
    print("=" * 78)
    print("test_reference_grounding_unit_proof.py")
    print("=" * 78)

    db_params = _db_params()
    source_text = _reconstruct_document_text(db_params, RAVENHILL_DOC_ID)
    print(f"\nReconstructed Ravenhill source text: {len(source_text)} chars "
          f"(document_id={RAVENHILL_DOC_ID})")

    verse_lookup = cc.build_verse_lookup(db_params)
    print(f"Live verse_lookup: {len(verse_lookup)} rows (all WEB)")

    # ── Case 1: a genuine, explicitly-printed reference survives with
    #    `content` BYTE-IDENTICAL for that reference (no strip at all). ─────
    content_1 = (
        "The teacher grounds this claim explicitly in Romans 8:28, tying "
        "suffering to purpose."
    )
    new_content_1, records_1, found_1, grounded_1, fab_1, unc_1 = (
        pm._strip_ungrounded_references(content_1, source_text, RAVENHILL_DOC_ID, 1)
    )
    print("\n--- Case 1: genuine printed reference (Romans 8:28) ---")
    print(f"  new_content: {new_content_1!r}")
    print(f"  found={found_1} grounded={grounded_1} fabricated={fab_1} uncertain={unc_1}")
    assert new_content_1 == content_1, "genuine reference must survive byte-identical"
    assert records_1 == [], "no review record for a GROUNDED reference"
    assert (found_1, grounded_1, fab_1, unc_1) == (1, 1, 0, 0)

    # ── Case 2: a synthetically injected FABRICATED reference (a chapter:
    #    verse absent from Ravenhill's actual source, per Step A's own
    #    finding) gets its token span removed while everything else in
    #    `content` is untouched. verse_lookup is NOT passed to the stripper
    #    (propositions.py's real call site never has one -- see
    #    extract_propositions()'s docstring), so this reference is
    #    UNCERTAIN, not UNGROUNDED -- both reasons strip identically; this
    #    case proves the STRIP itself. Case 6 below proves the UNGROUNDED/
    #    "fabricated" reason-label path directly. ────────────────────────
    content_2 = (
        "The teacher urges believers to dwell on Philippians 4:8-9 in "
        "daily meditation."
    )
    assert "Philippians 4:8-9" not in [s.raw for s in rg.find_reference_spans(source_text)], (
        "sanity check: Ravenhill source must not print the literal citation "
        "'Philippians 4:8-9' anywhere, per Step A's finding"
    )
    new_content_2, records_2, found_2, grounded_2, fab_2, unc_2 = (
        pm._strip_ungrounded_references(content_2, source_text, RAVENHILL_DOC_ID, 2)
    )
    print("\n--- Case 2: injected fabricated reference (Philippians 4:8-9) ---")
    print(f"  new_content: {new_content_2!r}")
    print(f"  found={found_2} grounded={grounded_2} fabricated={fab_2} uncertain={unc_2}")
    print(f"  review record: {records_2}")
    expected_2 = "The teacher urges believers to dwell on in daily meditation."
    assert new_content_2 == expected_2, f"expected {expected_2!r}, got {new_content_2!r}"
    assert "Philippians 4:8-9" not in new_content_2
    assert len(records_2) == 1 and records_2[0]["reference"] == "Philippians 4:8-9"
    assert (found_2, grounded_2, fab_2 + unc_2) == (1, 0, 1)

    # ── Case 3: seam-normalization, comma variant -- "in Philippians 4:8-9,
    #    where" -> "in, where" (space-before-comma collapsed, comma itself
    #    and everything after kept verbatim; connector word "in" untouched). ─
    content_3 = "As Paul writes in Philippians 4:8-9, we should think on these things."
    new_content_3, records_3, *_ = pm._strip_ungrounded_references(
        content_3, source_text, RAVENHILL_DOC_ID, 3,
    )
    print("\n--- Case 3: seam normalization (comma) ---")
    print(f"  new_content: {new_content_3!r}")
    expected_3 = "As Paul writes in, we should think on these things."
    assert new_content_3 == expected_3, f"expected {expected_3!r}, got {new_content_3!r}"

    # ── Case 3b: seam-normalization, double-space variant (reference sits
    #    mid-sentence with a space on each side, no adjacent punctuation). ──
    content_3b = "He taught from Philippians 4:8-9 that everything is fine."
    new_content_3b, *_ = pm._strip_ungrounded_references(
        content_3b, source_text, RAVENHILL_DOC_ID, "3b",
    )
    print("\n--- Case 3b: seam normalization (double space) ---")
    print(f"  new_content: {new_content_3b!r}")
    expected_3b = "He taught from that everything is fine."
    assert new_content_3b == expected_3b, f"expected {expected_3b!r}, got {new_content_3b!r}"
    assert "  " not in new_content_3b, "no double space should survive seam cleanup"

    # ── Case 4: BOUNDARY SAFETY. content has both an ungrounded short
    #    reference ("Galatians 6:1", not printed anywhere in the Ravenhill
    #    source) and a separate, later, GENUINELY GROUNDED longer reference
    #    ("Galatians 6:14", which Ravenhill's source DOES print) whose own
    #    string literally starts with the shorter one's string. A blind
    #    str.replace("Galatians 6:1", "") would corrupt "Galatians 6:14"
    #    into "4" (demonstrated below); the real span-based stripper must
    #    remove ONLY "Galatians 6:1" and leave "Galatians 6:14" untouched. ──
    content_4 = (
        "Consider Galatians 6:1 first, then remember Galatians 6:14 which "
        "is different."
    )
    naive_blind_replace = content_4.replace("Galatians 6:1", "")
    print("\n--- Case 4: boundary safety (prefix collision) ---")
    print(f"  content:              {content_4!r}")
    print(f"  naive str.replace() WOULD produce: {naive_blind_replace!r}  <- WRONG, corrupts 6:14")
    assert "Galatians 6:14" not in naive_blind_replace, (
        "sanity check: confirms this IS a real collision a blind replace would hit"
    )
    new_content_4, records_4, found_4, grounded_4, fab_4, unc_4 = (
        pm._strip_ungrounded_references(content_4, source_text, RAVENHILL_DOC_ID, 4)
    )
    print(f"  real stripper produces:            {new_content_4!r}")
    expected_4 = "Consider first, then remember Galatians 6:14 which is different."
    assert new_content_4 == expected_4, f"expected {expected_4!r}, got {new_content_4!r}"
    assert "Galatians 6:14" in new_content_4, "grounded longer reference must survive intact"
    assert (found_4, grounded_4, fab_4 + unc_4) == (2, 1, 1)
    assert records_4[0]["reference"] == "Galatians 6:1"

    # ── Case 5: genuine translation-variance case, proven NOT falsely
    #    stripped. Ravenhill's real source text quotes Philippians 4:8 in
    #    KJV-flavored wording ("whatsoever things are true...") WITHOUT ever
    #    printing a "Philippians 4:8" citation anywhere nearby (confirmed
    #    directly against the live doc while building this test) -- so the
    #    citation-string arm alone (verse_lookup=None) cannot ground it, but
    #    the WORDING arm (verse_lookup supplied, WEB ground truth) correctly
    #    recognizes the quoted wording and returns GROUNDED. This is the
    #    predicate's wording arm, exercised directly (NOT through
    #    extract_propositions()/the stripper, which never supplies
    #    verse_lookup -- see note below and the report). ─────────────────
    citation_absent = all(
        s.parsed != ("PHP", 4, 8, 9) for s in rg.find_reference_spans(source_text)
    )
    assert citation_absent, "sanity check: no literal 'Philippians 4:8-9'-shaped citation in source"
    result_no_lookup = rg.check_reference_grounded("Philippians 4:8-9", source_text, None)
    result_with_lookup = rg.check_reference_grounded("Philippians 4:8-9", source_text, verse_lookup)
    print("\n--- Case 5: translation-variance / wording-arm proof ---")
    print(f"  no verse_lookup   -> {result_no_lookup}")
    print(f"  with verse_lookup -> {result_with_lookup}")
    assert result_no_lookup.status == rg.UNCERTAIN, (
        "without verse_lookup, an unlabeled quote must read UNCERTAIN, not a guess either way"
    )
    assert result_with_lookup.status == rg.GROUNDED, (
        "with verse_lookup, the wording arm must recognize the real unlabeled "
        "Philippians 4:8 quote in Ravenhill's own source text -- NOT falsely stripped"
    )
    assert result_with_lookup.reason == "verse_wording_match"
    matched_span_text = source_text[result_with_lookup.span[0]:result_with_lookup.span[1]]
    print(f"  matched wording span: {matched_span_text!r}")
    assert "things are true" in matched_span_text.lower(), (
        "matched span should be the actual Phil 4:8 wording in the source"
    )

    # ── Case 6: UNGROUNDED / "fabricated" reason-label path, proven
    #    directly. propositions._strip_ungrounded_references() never
    #    supplies verse_lookup in production (extract_propositions() has no
    #    DB connection of its own -- see that function's docstring), so
    #    check_reference_grounded() can never actually RETURN UNGROUNDED via
    #    that real call path today -- only UNCERTAIN or GROUNDED. That is a
    #    disclosed, intentional scope boundary, not a bug. This case proves
    #    the "fabricated" reason-mapping code inside
    #    _strip_ungrounded_references() itself is nonetheless correct, by
    #    monkeypatching reference_grounding.check_reference_grounded (as
    #    seen by propositions.py) to return a canned UNGROUNDED result for
    #    one call, confirming the record's reason == "fabricated". ────────
    content_6 = "This references Galatians 6:1 directly."
    original_check = pm.rg.check_reference_grounded

    def _fake_check(reference, source, verse_lookup=None):
        if reference == "Galatians 6:1":
            return rg.GroundingResult(rg.UNGROUNDED, None, "test_forced_ungrounded")
        return original_check(reference, source, verse_lookup)

    pm.rg.check_reference_grounded = _fake_check
    try:
        new_content_6, records_6, found_6, grounded_6, fab_6, unc_6 = (
            pm._strip_ungrounded_references(content_6, source_text, RAVENHILL_DOC_ID, 6)
        )
    finally:
        pm.rg.check_reference_grounded = original_check

    print("\n--- Case 6: UNGROUNDED -> reason='fabricated' mapping proof (forced) ---")
    print(f"  new_content: {new_content_6!r}")
    print(f"  records: {records_6}")
    assert records_6[0]["reason"] == "fabricated"
    assert (found_6, grounded_6, fab_6, unc_6) == (1, 0, 1, 0)

    print("\n" + "=" * 78)
    print("All assertions passed.")
    print("=" * 78)


if __name__ == "__main__":
    main()
