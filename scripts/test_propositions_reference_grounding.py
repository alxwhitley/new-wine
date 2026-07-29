#!/usr/bin/env python3
"""
test_propositions_reference_grounding.py — proof that the always-on
reference-grounding fix (PLAN.md #45, 2026-07-28) actually fires INSIDE
extract_propositions() itself, not merely that the predicate module works
in isolation (see test_reference_grounding_unit_proof.py for that). Per
CLAUDE.md: "verify by grepping/testing the real call site -- comments and
docstrings lie."

MOCKED Groq client -- NO real API call anywhere in this file, generation
stays stopped. os.environ["GROQ_API_KEY"] is never read because
propositions._get_groq is monkeypatched out entirely before
extract_propositions() runs; the Groq SDK's real HTTP client is never
constructed.

Source text is REAL, reconstructed via one bulk SELECT from the Ravenhill
document's chunks (same document as test_reference_grounding_unit_proof.py)
-- only the model's MOCKED response content (the two proposition dicts) is
hand-constructed, since there's no other way to control which reference is
genuine vs. fabricated in a "model output" without a real Groq call.

Run: python3 scripts/test_propositions_reference_grounding.py
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propositions as pm  # noqa: E402
import citation_verifier_layers as cvl  # noqa: E402

RAVENHILL_DOC_ID = "c19ad18c-ea97-4841-8fa0-e60afc273521"
ALLOWED_BLOCK_MARKER = "ALLOWED SCRIPTURE REFERENCES (CLOSED LIST)"


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
    chunk_index -- not a per-chunk query (N+1 lesson)."""
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


# ── Fake Groq client (no network, no API key ever read) ────────────────────

class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, raw_json: str):
        self._raw_json = raw_json
        self.calls = 0
        self.last_kwargs = None  # captures the real kwargs .create() was
        # called with -- specifically `messages` -- so a test can assert
        # what was actually SENT to the model, not just what came back.

    def create(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return _FakeResponse(self._raw_json)


class _FakeChat:
    def __init__(self, raw_json: str):
        self.completions = _FakeCompletions(raw_json)


class _FakeGroqClient:
    def __init__(self, raw_json: str):
        self.chat = _FakeChat(raw_json)


def main() -> None:
    print("=" * 78)
    print("test_propositions_reference_grounding.py")
    print("=" * 78)

    db_params = _db_params()
    source_text = _reconstruct_document_text(db_params, RAVENHILL_DOC_ID)
    print(f"\nReconstructed Ravenhill source text: {len(source_text)} chars")

    grounded_content = (
        "Ravenhill grounds this exhortation about suffering and purpose "
        "explicitly in Romans 8:28, tying it to God's larger design."
    )
    fabricated_content = (
        "Ravenhill also urges believers to dwell often on Philippians 4:8-9 "
        "in their daily walk."
    )
    mock_response_json = json.dumps([
        {"proposition_index": 1, "content": grounded_content},
        {"proposition_index": 2, "content": fabricated_content},
    ])

    fake_client = _FakeGroqClient(mock_response_json)

    # Point the review-file constants at a scratch path so this run never
    # touches (or is contaminated by) the real reference_grounding_review/
    # directory.
    scratch_dir = Path(
        "/private/tmp/claude-501/-Users-alexwhitley-rhemata/"
        "947652e0-7a9a-4bf5-9c8c-badd1f72dc29/scratchpad"
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_review_path = scratch_dir / "test_grounding_review.jsonl"
    if scratch_review_path.exists():
        scratch_review_path.unlink()

    original_get_groq = pm._get_groq
    original_review_dir = pm.GROUNDING_REVIEW_DIR
    original_review_path = pm.GROUNDING_REVIEW_PATH
    original_verify = cvl.verify_reference_grounded
    pm._get_groq = lambda: fake_client
    pm.GROUNDING_REVIEW_DIR = scratch_dir
    pm.GROUNDING_REVIEW_PATH = scratch_review_path

    # "Philippians 4:8-9" (the injected fabricated reference) is UNCERTAIN at
    # the primary check (verse_lookup=None on this real call path), so after
    # PLAN.md #45 Phase 1's arbitration build (2026-07-29) it now reaches the
    # arbiter before any strip decision. Pin it deterministically (confirmed=
    # False, "layer3_llm_denied") so the strip still fires -- the exact
    # pre-arbitration outcome this test already asserted below -- and no
    # live Groq/network call fires for it (or for anything else: "Romans
    # 8:28" is genuinely GROUNDED at the primary check and never reaches
    # arbitration at all, so a call for it would hit this mock's own
    # "unexpected reference" guard if that branch were ever wrongly taken).
    arbitration_calls = []

    def _fake_verify(reference, source_text, verse_lookup=None, llm_enabled=False):
        arbitration_calls.append(reference)
        if reference == "Philippians 4:8-9":
            return cvl.VerificationResult(False, None, "layer3_llm_denied", False, 0)
        raise AssertionError(f"unexpected arbitration call for {reference!r}")

    cvl.verify_reference_grounded = _fake_verify

    try:
        result = pm.extract_propositions(source_text, doc_id=RAVENHILL_DOC_ID)
    finally:
        pm._get_groq = original_get_groq
        pm.GROUNDING_REVIEW_DIR = original_review_dir
        pm.GROUNDING_REVIEW_PATH = original_review_path
        cvl.verify_reference_grounded = original_verify

    print(f"\nMocked Groq .create() call count: {fake_client.chat.completions.calls}")
    assert fake_client.chat.completions.calls == 1, "expected exactly one mocked model call"
    print(f"Arbitration calls: {arbitration_calls}")
    assert arbitration_calls == ["Philippians 4:8-9"], (
        "arbitration must be invoked exactly once, only for the UNCERTAIN reference"
    )

    # ── Proof 0 (Step 2, PLAN.md #45 Phase 1): the allowed-reference-list
    #    block was actually SENT to the model as part of the real message,
    #    not merely built and discarded. Reads the captured `messages`
    #    kwarg the fake .create() call received -- this is the real call
    #    site's own outgoing content, not a separate call to the builder. ──
    sent_content = fake_client.chat.completions.last_kwargs["messages"][0]["content"]
    assert ALLOWED_BLOCK_MARKER in sent_content, (
        "allowed-reference-list block must be present in the v3 outgoing message"
    )
    assert "Romans 8:28" in sent_content, (
        "the block must list a real reference actually printed in the source "
        "document (Romans 8:28, per Case 1 of test_reference_grounding_unit_proof.py)"
    )

    print("\n--- extract_propositions() result ---")
    for prop in result:
        print(f"  [{prop['proposition_index']}] {prop['content']!r}")

    # ── Proof 1: no proposition dropped -- same count, same indices. ───────
    assert len(result) == 2, f"expected 2 propositions returned, got {len(result)}"
    by_index = {p["proposition_index"]: p for p in result}
    assert set(by_index.keys()) == {1, 2}

    # ── Proof 2: the GROUNDED reference (Romans 8:28, genuinely printed in
    #    Ravenhill's source) survives byte-identical. ───────────────────────
    assert by_index[1]["content"] == grounded_content, (
        "grounded reference's proposition content must be untouched"
    )

    # ── Proof 3: the FABRICATED reference is stripped from `content`, but
    #    the proposition itself is still present (not dropped), and the
    #    surrounding text survives (minus the removed span + seam cleanup). ─
    stripped_content = by_index[2]["content"]
    assert "Philippians 4:8-9" not in stripped_content, (
        "fabricated reference must be stripped from content"
    )
    expected_stripped = (
        "Ravenhill also urges believers to dwell often on in their daily walk."
    )
    assert stripped_content == expected_stripped, (
        f"expected {expected_stripped!r}, got {stripped_content!r}"
    )

    # ── Proof 4: the strip was logged to the review file with correct
    #    provenance (document_id, proposition_index, the stripped
    #    reference, a reason), AND now carries the arbitration label
    #    alongside the original reason (PLAN.md #45 Phase 1). ─────────────
    assert scratch_review_path.exists(), "expected the grounding review file to have been written"
    review_lines = [
        json.loads(line) for line in scratch_review_path.read_text().splitlines() if line.strip()
    ]
    print(f"\n--- Grounding review-file records ({len(review_lines)}) ---")
    for rec in review_lines:
        print(f"  {rec}")
    assert len(review_lines) == 1, f"expected exactly 1 review record, got {len(review_lines)}"
    rec = review_lines[0]
    assert rec["document_id"] == RAVENHILL_DOC_ID
    assert rec["proposition_index"] == 2
    assert rec["reference"] == "Philippians 4:8-9"
    assert rec["reason"] in ("fabricated", "uncertain")
    assert rec["arbitration"] == "arbitration_agreed"
    assert rec["arbitration_reason"] == "layer3_llm_denied"

    # ── Proof 5 (Step 2, v4 branch): the allowed-reference-list block is
    #    ALSO sent on the v4 (speaker-attributed) path -- a SEPARATE fake
    #    client/call, single grounded-only proposition so this pass doesn't
    #    need its own arbitration mock (nothing here is UNCERTAIN/
    #    UNGROUNDED). Proves the block-wiring line is genuinely unconditional
    #    across both branches, not just the v3 default. ────────────────────
    v4_mock_response_json = json.dumps([
        {"proposition_index": 1, "content": grounded_content},
    ])
    fake_client_v4 = _FakeGroqClient(v4_mock_response_json)
    pm._get_groq = lambda: fake_client_v4
    try:
        result_v4 = pm.extract_propositions(
            source_text, doc_id=RAVENHILL_DOC_ID,
            speaker="Leonard Ravenhill", prompt_version="v4",
        )
    finally:
        pm._get_groq = original_get_groq
    assert fake_client_v4.chat.completions.calls == 1
    sent_content_v4 = fake_client_v4.chat.completions.last_kwargs["messages"][0]["content"]
    assert ALLOWED_BLOCK_MARKER in sent_content_v4, (
        "allowed-reference-list block must ALSO be present in the v4 outgoing message"
    )
    assert "Romans 8:28" in sent_content_v4
    assert len(result_v4) == 1 and result_v4[0]["content"] == grounded_content

    print("\n" + "=" * 78)
    print("All assertions passed -- grounding fires INSIDE extract_propositions() itself.")
    print("=" * 78)


def test_build_allowed_reference_block() -> None:
    """Pure-function proof for propositions._build_allowed_reference_block()
    (Step 2) -- no DB, no Groq, synthetic text only. Run as part of this
    file's own main() below, matching this repo's ad hoc test-file
    convention (plain function calls, no pytest)."""
    print("\n" + "=" * 78)
    print("test_build_allowed_reference_block()")
    print("=" * 78)

    # ── Dedupe: "Rom 8:28" and "Romans 8:28" both parse to the identical
    #    (abbrev, chapter, verse_start, verse_end) tuple via BOOK_MAP -- must
    #    collapse to ONE entry, showing the FIRST-SEEN raw spelling. ───────
    text_dupe = "As Rom 8:28 says, and later Romans 8:28 again, plus John 3:16."
    block_dupe = pm._build_allowed_reference_block(text_dupe)
    print(f"\n--- dedupe collapse ---\n{block_dupe}")
    assert ALLOWED_BLOCK_MARKER in block_dupe
    assert "- Rom 8:28" in block_dupe, "first-seen raw spelling ('Rom 8:28') must be shown"
    assert "- Romans 8:28" not in block_dupe, (
        "second-seen spelling of the SAME parsed reference must NOT appear as its own line"
    )
    assert "- John 3:16" in block_dupe
    assert block_dupe.count("8:28") == 1, "the duplicate-parse reference must appear exactly once"

    # ── Empty / reference-free input -> explicit "no references" text. ─────
    text_empty = "This document contains no scripture citations of any kind."
    block_empty = pm._build_allowed_reference_block(text_empty)
    print(f"\n--- empty / reference-free ---\n{block_empty}")
    assert ALLOWED_BLOCK_MARKER in block_empty
    assert "must not include ANY scripture reference at all" in block_empty
    assert not any(line.strip().startswith("- ") for line in block_empty.splitlines()), (
        "empty case must not render any bullet-list reference line"
    )

    print("\nAll _build_allowed_reference_block() assertions passed.")


def test_new_language_reaches_groq_message() -> None:
    """Bypass-proofing Phase 3 (PLAN.md #45, 2026-07-29) coverage: proves the
    new Count-and-distinctness wording -- empty-is-fine permission, the
    genuine-however-brief-still-extract affirmation, "no minimum count", and
    removal of the old implicit-floor "Short documents may yield three or
    four" phrasing -- is present in BOTH prompt constants' literal text AND
    actually reaches the real outgoing Groq message for both the v3 and v4
    branches, not merely built and never sent. Also confirms
    EXTRACTION_PROMPT_V4.format(speaker=...) still succeeds with no
    exception (brace-safety requirement for this phase's edit). MOCKED Groq
    client throughout -- no network call, matching this file's own
    top-level convention; DB-free (the fixture source text here has zero
    scripture references, so no arbitration call fires either)."""
    print("\n" + "=" * 78)
    print("test_new_language_reaches_groq_message() -- bypass-proofing Phase 3")
    print("=" * 78)

    # ── Literal content checks on the constants themselves. ─────────────────
    for name, template in (("EXTRACTION_PROMPT (v3)", pm.EXTRACTION_PROMPT),
                            ("EXTRACTION_PROMPT_V4 (v4)", pm.EXTRACTION_PROMPT_V4)):
        assert "no minimum count" in template, (
            "{0} must state there is no minimum count".format(name)
        )
        assert "empty array" in template, (
            "{0} must explicitly permit an empty array as a correct result".format(name)
        )
        assert "Short documents may yield three or four" not in template, (
            "{0} must not retain the old implicit-floor example-count phrasing".format(name)
        )
        assert "however brief" in template, (
            "{0} must explicitly preserve the affirmative case for a genuine, "
            "however-brief teaching point".format(name)
        )
    print("  OK: both constants contain the new empty-permission + no-minimum-count "
          "language and no longer contain the old 'three or four' floor phrasing.")

    # ── The two-statement distinction: "no genuine content -> empty" is a
    #    SEPARATE explicit statement from "genuine content, however brief ->
    #    still extract" -- not merely implied by one sentence doing both
    #    jobs. Checked as two independently-locatable phrases. ──────────────
    for name, template in (("EXTRACTION_PROMPT (v3)", pm.EXTRACTION_PROMPT),
                            ("EXTRACTION_PROMPT_V4 (v4)", pm.EXTRACTION_PROMPT_V4)):
        empty_case = "no genuine, distinct teaching point at all" in template
        brief_case = "however brief, it must still be" in template
        assert empty_case, "{0} must explicitly state the no-genuine-content -> empty case".format(name)
        assert brief_case, (
            "{0} must explicitly state the genuine-however-brief -> still-extract case".format(name)
        )
    print("  OK: both constants state the empty-case and the still-extract-if-genuine "
          "case as two distinct, explicit statements.")

    # ── v4 .format() safety: no stray single braces beyond {speaker}. ───────
    formatted = pm.EXTRACTION_PROMPT_V4.format(speaker="Test Speaker")
    assert "Test Speaker" in formatted
    print("  OK: EXTRACTION_PROMPT_V4.format(speaker='Test Speaker') succeeded with no exception.")

    # ── The new language must actually reach the real outgoing Groq message
    #    -- v3 path. Fixture source text has NO scripture references, so no
    #    arbitration call is triggered (matches this file's simpler-fixture
    #    convention in test_build_allowed_reference_block() above). ─────────
    plain_source_text = (
        "This is a short plain source document with no scripture citations "
        "in it at all, used only to confirm outgoing message content."
    )
    mock_json_v3 = json.dumps([{"proposition_index": 1, "content": "A harmless paraphrase."}])
    fake_client_v3b = _FakeGroqClient(mock_json_v3)
    original_get_groq_local = pm._get_groq
    pm._get_groq = lambda: fake_client_v3b
    try:
        pm.extract_propositions(plain_source_text, doc_id="lang-check-v3")
    finally:
        pm._get_groq = original_get_groq_local
    sent_v3b = fake_client_v3b.chat.completions.last_kwargs["messages"][0]["content"]
    assert "no minimum count" in sent_v3b
    assert "empty array" in sent_v3b
    assert "however brief" in sent_v3b
    print("  OK: new language present in the real outgoing v3 Groq message.")

    # ── Same, v4 path. ───────────────────────────────────────────────────────
    fake_client_v4b = _FakeGroqClient(mock_json_v3)
    pm._get_groq = lambda: fake_client_v4b
    try:
        pm.extract_propositions(
            plain_source_text, doc_id="lang-check-v4",
            speaker="Test Speaker", prompt_version="v4",
        )
    finally:
        pm._get_groq = original_get_groq_local
    sent_v4b = fake_client_v4b.chat.completions.last_kwargs["messages"][0]["content"]
    assert "no minimum count" in sent_v4b
    assert "empty array" in sent_v4b
    assert "however brief" in sent_v4b
    print("  OK: new language present in the real outgoing v4 Groq message.")

    print("\nAll test_new_language_reaches_groq_message() assertions passed.")


if __name__ == "__main__":
    main()
    test_build_allowed_reference_block()
    test_new_language_reaches_groq_message()
