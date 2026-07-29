#!/usr/bin/env python3
"""
test_rewrite_flagged_statement.py — DB-free proof that
rewrite_flagged_statement.py's verify-before-write gate is real: a draft
that fails either check (citation or closeness) cannot reach the UPDATE,
no matter how many attempts run. Mirrors test_propositions_closeness_gate.py's
convention exactly — hand-built FakeConn/FakeCursor, no psycopg2 connection
ever opened, no test framework installed.

call_rewrite_llm() is monkeypatched to return a scripted sequence of drafts
per call (never touches Groq/the network), so each case below exercises the
REAL verify_draft()/passes_both()/write_single_row() logic against REAL
closeness_check.classify() and reference_grounding.check_reference_grounded()
output.

Four cases:
  1. Citation-failing draft, both attempts -> still_failing, UPDATE never called.
  2. Closeness-failing draft, both attempts -> still_failing, UPDATE never called.
  3. Attempt 1 fails, attempt 2 passes -> fixed on the 2nd attempt, exactly
     ONE UPDATE call, with attempt 2's content (not attempt 1's).
  4. Clean pass on attempt 1 -> fixed, exactly ONE UPDATE call, correct
     provenance stamped (prompt_version/prompt_fingerprint/model), id-only
     WHERE clause (no document_id anywhere in the statement).

Run: python3 scripts/test_rewrite_flagged_statement.py
"""
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import closeness_check as cc  # noqa: E402
import rewrite_flagged_statement as rw  # noqa: E402


# ── Fake conn/cursor (DB-free, mirrors test_propositions_closeness_gate.py) ────

class FakeCursor:
    def __init__(self):
        self.executed = []  # [(sql, params), ...]
        self.rowcount = 1

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    def __init__(self):
        self._cursor = FakeCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True

    def update_calls(self):
        return [(sql, params) for sql, params in self._cursor.executed if "UPDATE propositions" in sql]


def fake_embed_fn(text):
    return [0.01, 0.02, 0.03]


# ── Shared fixtures ─────────────────────────────────────────────────────────

DOC_TEXT = (
    "The prophet declared that revival always begins with brokenness before God, "
    "not with strategy or method. This happened once at a large gathering many "
    "years ago in a small town, remembered vividly by those present."
)

ORIGINAL_CONTENT = (
    "The prophet taught that revival begins with brokenness before God, as stated "
    "in Acts 20:31, not through clever strategy."
)

GOOD_DRAFT = (
    "He taught that spiritual renewal starts when people humble themselves before "
    "God rather than relying on clever planning or strategy."
)

BAD_DRAFT_CITATION_STILL_PRESENT = (
    "He taught that spiritual renewal starts when people humble themselves before "
    "God, as stated in Acts 20:31, rather than relying on clever planning."
)

BAD_DRAFT_CLOSENESS = (
    "The prophet declared that revival always begins with brokenness before God, "
    "not with strategy or method."
)

# A hand-made verse_lookup with wording that shares nothing with DOC_TEXT, so
# the wording arm also fails and a genuine UNGROUNDED (not just UNCERTAIN)
# verdict is produced — proving the gate against both citation-failure shapes.
VERSE_LOOKUP = {
    "acts.20.31": "Take heed therefore unto yourselves and to all the flock among "
                  "which the Holy Ghost hath made you overseers to feed the church of God.",
}

NAME_PATTERN = cc.build_name_pattern({"Fake Teacher"})
VOCAB_MATCHER = None


def make_call(sequence):
    """Returns a fake call_rewrite_llm(original, source, defect) that pops
    the next scripted draft off `sequence` on each call, ignoring its real
    args entirely — this test is proving the gate, not the prompt."""
    calls = {"n": 0}

    def _fake(original_content, source_text, defect_description):
        draft = sequence[calls["n"]]
        calls["n"] += 1
        return draft
    _fake.call_count = lambda: calls["n"]
    return _fake


def run_case(label, sequence, expect_status, expect_update_calls, expect_written_content=None):
    print(f"\n--- {label} ---")
    original_call = rw.call_rewrite_llm
    rw.call_rewrite_llm = make_call(sequence)
    conn = FakeConn()

    # fetch_live_row would normally hit the DB; for a "fixed" case we short-
    # circuit it to reflect exactly what write_single_row just wrote, since
    # this test has no real database to re-query.
    original_fetch = rw.fetch_live_row
    written = {}

    def fake_fetch_live_row(prop_id):
        if prop_id in written:
            return {"id": prop_id, "document_id": "doc-1", "content": written[prop_id], "proposition_index": 1}
        return None

    def wrapped_conn_factory():
        return conn

    original_write = rw.write_single_row

    def wrapped_write_single_row(conn_, prop_id, new_content, new_embedding):
        original_write(conn_, prop_id, new_content, new_embedding)
        written[prop_id] = new_content

    rw.fetch_live_row = fake_fetch_live_row
    rw.write_single_row = wrapped_write_single_row

    try:
        result = rw.rewrite_one(
            conn_factory=wrapped_conn_factory,
            embed_fn=fake_embed_fn,
            prop_id="prop-1",
            document_id="doc-1",
            original_content=ORIGINAL_CONTENT,
            source_text=DOC_TEXT,
            name_pattern=NAME_PATTERN,
            verse_lookup=VERSE_LOOKUP,
            vocab_matcher=VOCAB_MATCHER,
            citation_fail=True,
            closeness_fail=False,
            failing_references=["Acts 20:31"],
            dry_run=False,
            max_attempts=2,
        )
    finally:
        rw.call_rewrite_llm = original_call
        rw.fetch_live_row = original_fetch
        rw.write_single_row = original_write

    print(f"  status = {result['status']!r} (expected {expect_status!r})")
    update_calls = conn.update_calls()
    print(f"  UPDATE calls = {len(update_calls)} (expected {expect_update_calls})")

    assert result["status"] == expect_status, (
        f"{label}: expected status {expect_status!r}, got {result['status']!r} -- full result: {result}"
    )
    assert len(update_calls) == expect_update_calls, (
        f"{label}: expected {expect_update_calls} UPDATE call(s), got {len(update_calls)}"
    )

    if expect_update_calls:
        sql, params = update_calls[0]
        assert "WHERE id = %s" in sql, f"{label}: UPDATE must be id-scoped, got: {sql}"
        assert "document_id" not in sql, f"{label}: UPDATE must never reference document_id, got: {sql}"
        new_content, embedding_str, prompt_version, fingerprint, model, prop_id = params
        assert prop_id == "prop-1"
        assert prompt_version == rw.REWRITE_PROMPT_VERSION
        assert fingerprint == rw.rewrite_prompt_fingerprint()
        assert model == rw.pw.EXTRACTION_MODEL
        if expect_written_content:
            assert new_content == expect_written_content, (
                f"{label}: expected written content {expect_written_content!r}, got {new_content!r}"
            )
        print(f"  provenance stamped: prompt_version={prompt_version!r} model={model!r} "
              f"fingerprint={fingerprint[:12]}...")
        assert conn.committed, f"{label}: expected commit() on a successful write"

    return result


def main():
    print("=" * 78)
    print("test_rewrite_flagged_statement.py — verify-before-write gate proof")
    print("=" * 78)

    # Sanity: confirm the ground-truth verdicts for the hand-made drafts
    # BEFORE using them in the gate test, so the assertions below check
    # against known-correct ground truth, not assumed behavior.
    v_good = rw.verify_draft(GOOD_DRAFT, DOC_TEXT, NAME_PATTERN, VERSE_LOOKUP, VOCAB_MATCHER)
    v_bad_cit = rw.verify_draft(BAD_DRAFT_CITATION_STILL_PRESENT, DOC_TEXT, NAME_PATTERN, VERSE_LOOKUP, VOCAB_MATCHER)
    v_bad_close = rw.verify_draft(BAD_DRAFT_CLOSENESS, DOC_TEXT, NAME_PATTERN, VERSE_LOOKUP, VOCAB_MATCHER)
    print("\n--- Ground-truth verify_draft() verdicts ---")
    print(f"  GOOD_DRAFT                     : closeness={v_good.closeness_verdict} citation={v_good.citation_verdict}")
    print(f"  BAD_DRAFT_CITATION_STILL_PRESENT: closeness={v_bad_cit.closeness_verdict} citation={v_bad_cit.citation_verdict} refs={v_bad_cit.citation_failing_references}")
    print(f"  BAD_DRAFT_CLOSENESS             : closeness={v_bad_close.closeness_verdict} citation={v_bad_close.citation_verdict}")

    assert rw.passes_both(v_good), f"expected GOOD_DRAFT to pass both checks, got {v_good}"
    assert not rw.passes_both(v_bad_cit), f"expected BAD_DRAFT_CITATION_STILL_PRESENT to fail, got {v_bad_cit}"
    assert v_bad_cit.citation_verdict == "fail" and "Acts 20:31" in v_bad_cit.citation_failing_references, (
        f"expected a genuine UNGROUNDED citation fail (not just uncertain), got {v_bad_cit}"
    )
    assert not rw.passes_both(v_bad_close), f"expected BAD_DRAFT_CLOSENESS to fail, got {v_bad_close}"
    assert v_bad_close.closeness_verdict != "PASS"

    # ── Case 1: citation-failing draft on both attempts -> never reaches UPDATE ──
    run_case(
        "Case 1: citation fails both attempts",
        sequence=[BAD_DRAFT_CITATION_STILL_PRESENT, BAD_DRAFT_CITATION_STILL_PRESENT],
        expect_status="still_failing", expect_update_calls=0,
    )

    # ── Case 2: closeness-failing draft on both attempts -> never reaches UPDATE ──
    run_case(
        "Case 2: closeness fails both attempts",
        sequence=[BAD_DRAFT_CLOSENESS, BAD_DRAFT_CLOSENESS],
        expect_status="still_failing", expect_update_calls=0,
    )

    # ── Case 3: attempt 1 fails, attempt 2 passes -> exactly one UPDATE, with
    #    attempt 2's content (proves the retry path, not just the first-try path) ──
    run_case(
        "Case 3: fails attempt 1, passes attempt 2",
        sequence=[BAD_DRAFT_CITATION_STILL_PRESENT, GOOD_DRAFT],
        expect_status="fixed", expect_update_calls=1, expect_written_content=GOOD_DRAFT,
    )

    # ── Case 4: clean pass on attempt 1 -> exactly one UPDATE, correct provenance ──
    run_case(
        "Case 4: clean pass on attempt 1",
        sequence=[GOOD_DRAFT],
        expect_status="fixed", expect_update_calls=1, expect_written_content=GOOD_DRAFT,
    )

    print("\nAll assertions passed. The verify-before-write gate structurally "
          "cannot be bypassed: a failing draft never reaches the UPDATE, "
          "in either the first-attempt or retry path, across 4 independent cases.")


if __name__ == "__main__":
    main()
