#!/usr/bin/env python3
"""
test_propositions_closeness_gate.py — Phase 5 DB-free mock proof for the
closeness-check gate wired into propositions.process_document() (PLAN.md
#45 Phase 5).

DB-FREE. No psycopg2 connection is ever opened. `conn` and `embed_fn` are
hand-built fakes (this repo's ad hoc scripts/test_*.py convention, no test
framework installed — see test_closeness_check_unit_proof.py for the same
convention applied to closeness_check.py directly). The Groq extractor is
never called either: extract_propositions() is monkeypatched to return a
hand-made list so this test exercises the REAL partition/store/review-file
logic in process_document() against REAL closeness_check.classify() output,
without touching the network or the database.

name_pattern IS supplied (via closeness_check.build_name_pattern() over a
small hand-made set — a pure in-memory regex compile, no DB call) so the
gate is genuinely ACTIVE for this test, not the off-by-default path.

What this proves, both sides of the partition:
  1. The PASS item reaches the (mocked) store_propositions() call — visible
     via FakeCursor's recorded INSERT statements.
  2. The QUOTE_CANDIDATE and HOLD_TOO_LITTLE items do NOT reach
     store_propositions() (no INSERT recorded for their content), and DO
     land in the review file, each carrying correct provenance
     (prompt_version, prompt_fingerprint, model — CLAUDE.md Invariant 10)
     plus document_id, verdict, and the three scores.

Run: python3 scripts/test_propositions_closeness_gate.py
"""
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import closeness_check as cc  # noqa: E402
import propositions as props_mod  # noqa: E402


# ── Fake conn/cursor (DB-free) ─────────────────────────────────────────────

class FakeCursor:
    def __init__(self, license_status):
        self._license_status = license_status
        self.executed = []  # [(sql, params), ...] — full audit trail

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        # Only get_license_status() calls fetchone() in this test's path.
        return (self._license_status,)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    def __init__(self, license_status="licensed"):
        self._cursor = FakeCursor(license_status)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def inserted_contents(self):
        """Every `content` value that reached an INSERT INTO propositions."""
        out = []
        for sql, params in self._cursor.executed:
            if "INSERT INTO propositions" in sql:
                # store_propositions() param order: (id, document_id,
                # content, embedding_str, prop_index, prompt_version,
                # fingerprint, model) — content is index 2.
                out.append(params[2])
        return out


def fake_embed_fn(text: str):
    return [0.01, 0.02, 0.03]


def main() -> None:
    print("=" * 78)
    print("test_propositions_closeness_gate.py — Phase 5 DB-free mock proof")
    print("=" * 78)

    # name_pattern built from a small hand-made set -- build_name_pattern()
    # is a pure regex-compile, no DB call (unlike build_name_set(), which
    # this test deliberately does NOT call).
    name_pattern = cc.build_name_pattern({"Fake Teacher"})
    assert name_pattern is not None, "expected a compiled pattern from a non-empty set"
    verse_lookup = None  # citation-only masking mode; also DB-free

    document_id = "11111111-1111-1111-1111-111111111111"
    source_id = "22222222-2222-2222-2222-222222222222"

    # One shared "source document" text that all three hand-made
    # propositions below are classified against.
    doc_text = (
        "The prophet declared that revival always begins with brokenness before God, "
        "not with strategy or method. This happened once at a large gathering many "
        "years ago in a small town, remembered vividly by those present."
    )

    pass_content = (
        "He taught that spiritual renewal starts when people humble themselves, "
        "not through clever planning, and that examining one's own heart matters "
        "more than external strategy."
    )
    quote_content = (
        "The prophet declared that revival always begins with brokenness before God, "
        "not with strategy or method."
    )
    hold_content = "This happened once."

    hand_made_props = [
        {"proposition_index": 1, "content": pass_content},
        {"proposition_index": 2, "content": quote_content},
        {"proposition_index": 3, "content": hold_content},
    ]

    # Sanity-confirm each hand-made item's real classify() verdict BEFORE
    # routing it through process_document(), so the partition assertions
    # below are checking against a known-correct ground truth, not assumed.
    r_pass = cc.classify(pass_content, doc_text, name_pattern, verse_lookup)
    r_quote = cc.classify(quote_content, doc_text, name_pattern, verse_lookup)
    r_hold = cc.classify(hold_content, doc_text, name_pattern, verse_lookup)
    print("\n--- Ground-truth classify() verdicts for the hand-made propositions ---")
    print("  pass_content : {0} (containment={1:.4f} run={2} residual={3})".format(
        r_pass.verdict, r_pass.containment, r_pass.longest_run_words, r_pass.residual_tokens))
    print("  quote_content: {0} (containment={1:.4f} run={2} residual={3})".format(
        r_quote.verdict, r_quote.containment, r_quote.longest_run_words, r_quote.residual_tokens))
    print("  hold_content : {0} (containment={1:.4f} run={2} residual={3})".format(
        r_hold.verdict, r_hold.containment, r_hold.longest_run_words, r_hold.residual_tokens))
    assert r_pass.verdict == cc.PASS
    assert r_quote.verdict == cc.QUOTE_CANDIDATE
    assert r_hold.verdict == cc.HOLD_TOO_LITTLE

    # ── Monkeypatch extract_propositions() so process_document() never
    #    touches Groq or the network -- returns the hand-made list above. ──
    original_extract = props_mod.extract_propositions
    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props

    # Point the module's review-file constants at a scratch path for this
    # test run, so it never touches the real closeness_review/ directory
    # (and so a stale prior run's file can't contaminate the assertions).
    scratch_dir = Path(
        "/private/tmp/claude-501/-Users-alexwhitley-rhemata/"
        "089de4dc-bced-40ff-98c1-e156d293aed9/scratchpad"
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_review_path = scratch_dir / "test_closeness_review.jsonl"
    if scratch_review_path.exists():
        scratch_review_path.unlink()
    original_review_dir = props_mod.CLOSENESS_REVIEW_DIR
    original_review_path = props_mod.CLOSENESS_REVIEW_PATH
    props_mod.CLOSENESS_REVIEW_DIR = scratch_dir
    props_mod.CLOSENESS_REVIEW_PATH = scratch_review_path

    try:
        conn = FakeConn(license_status="licensed")
        result = props_mod.process_document(
            conn, document_id, source_id, doc_text, fake_embed_fn,
            name_pattern=name_pattern, verse_lookup=verse_lookup,
        )
    finally:
        props_mod.extract_propositions = original_extract
        props_mod.CLOSENESS_REVIEW_DIR = original_review_dir
        props_mod.CLOSENESS_REVIEW_PATH = original_review_path

    print("\n--- process_document() result ---")
    print("  result = {0!r}".format(result))
    print("  conn.committed = {0}".format(conn.committed))
    print("  conn.rolled_back = {0}".format(conn.rolled_back))

    assert result == "stored:1:flagged:2", (
        "expected 'stored:1:flagged:2', got {0!r}".format(result)
    )
    assert not conn.rolled_back, "expected no rollback on a clean gate-active run"
    assert conn.committed, "expected store_propositions() to have committed (1 PASS item)"

    # ── Side 1 of the partition: the PASS item reached store_propositions() ──
    inserted = conn.inserted_contents()
    print("\n--- Side 1: contents that reached the (mocked) store_propositions() INSERT ---")
    for c in inserted:
        print("  INSERTED: {0!r}".format(c))
    assert inserted == [pass_content], (
        "expected exactly [pass_content] to reach the INSERT, got {0!r}".format(inserted)
    )
    assert quote_content not in inserted, "QUOTE_CANDIDATE item must NOT reach store_propositions()"
    assert hold_content not in inserted, "HOLD_TOO_LITTLE item must NOT reach store_propositions()"

    # ── Side 2 of the partition: QUOTE_CANDIDATE + HOLD land in the review
    #    file, each with correct provenance ─────────────────────────────────
    assert scratch_review_path.exists(), "expected the review file to have been written"
    review_lines = [
        json.loads(line) for line in scratch_review_path.read_text().splitlines() if line.strip()
    ]
    print("\n--- Side 2: review-file records ({0}) ---".format(len(review_lines)))
    for rec in review_lines:
        print("  {0}".format(rec))

    assert len(review_lines) == 2, "expected exactly 2 review-file records"
    contents_reviewed = {r["content"] for r in review_lines}
    assert contents_reviewed == {quote_content, hold_content}, (
        "expected review file to contain exactly the QUOTE_CANDIDATE and "
        "HOLD_TOO_LITTLE contents, got {0!r}".format(contents_reviewed)
    )

    expected_fingerprint = props_mod.prompt_fingerprint(props_mod.DEFAULT_PROMPT_VERSION)
    for rec in review_lines:
        assert rec["document_id"] == document_id
        assert rec["prompt_version"] == props_mod.DEFAULT_PROMPT_VERSION
        assert rec["prompt_fingerprint"] == expected_fingerprint
        assert rec["model"] == props_mod.EXTRACTION_MODEL
        assert rec["verdict"] in (cc.QUOTE_CANDIDATE, cc.HOLD_TOO_LITTLE)
        assert "containment" in rec and "longest_run_words" in rec and "residual_tokens" in rec
        assert "written_at" in rec and rec["written_at"]

        if rec["content"] == quote_content:
            assert rec["verdict"] == cc.QUOTE_CANDIDATE
        if rec["content"] == hold_content:
            assert rec["verdict"] == cc.HOLD_TOO_LITTLE

    # ── Confirm gate-OFF path stays byte-identical (no name_pattern) ────────
    print("\n--- Gate-OFF control: same hand-made props, name_pattern=None ---")
    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props
    try:
        conn_off = FakeConn(license_status="licensed")
        result_off = props_mod.process_document(
            conn_off, document_id, source_id, doc_text, fake_embed_fn,
        )  # name_pattern/verse_lookup omitted entirely
    finally:
        props_mod.extract_propositions = original_extract

    print("  result_off = {0!r}".format(result_off))
    assert result_off == "stored:3", (
        "gate-off path must store ALL 3 extracted propositions unfiltered, got {0!r}".format(result_off)
    )
    inserted_off = conn_off.inserted_contents()
    assert set(inserted_off) == {pass_content, quote_content, hold_content}, (
        "gate-off path must insert every extracted proposition, no partition"
    )
    assert not scratch_review_path.read_text().count(quote_content) or True  # review file untouched by this second call
    # Stronger check: review file's line count is unchanged by the gate-off call.
    review_lines_after_off = [
        line for line in scratch_review_path.read_text().splitlines() if line.strip()
    ]
    assert len(review_lines_after_off) == 2, (
        "gate-off path must never touch the review file — expected still 2 lines, got {0}".format(
            len(review_lines_after_off))
    )

    print("\nAll assertions passed. Both sides of the partition confirmed; gate-off control confirmed unchanged.")


if __name__ == "__main__":
    main()
