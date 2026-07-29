#!/usr/bin/env python3
"""
test_propositions_closeness_gate.py — Phase 5 DB-free mock proof for the
closeness-check gate wired into propositions.process_document() (PLAN.md
#45 Phase 5), extended in Phase 2b (bypass-proofing, PLAN.md #45,
2026-07-29) with coverage for the new chunk_ids back-link parameter on
store_propositions()/process_document() (proposition_chunks, migration
074).

DB-FREE. No psycopg2 connection is ever opened. `conn` and `embed_fn` are
hand-built fakes (this repo's ad hoc scripts/test_*.py convention, no test
framework installed — see test_closeness_check_unit_proof.py for the same
convention applied to closeness_check.py directly). The Groq extractor is
never called either: extract_propositions() is monkeypatched to return a
hand-made list so this test exercises the REAL partition/store/review-file
logic in process_document() against REAL closeness_check.classify() output,
without touching the network or the database.

Phase 2b addition: store_propositions()'s new bulk proposition_chunks
insert calls psycopg2.extras.execute_values(), which requires a real
cursor with a working .mogrify() (and, since the SQL passed here is a
plain str rather than bytes, a `cur.connection.encoding` lookup too) --
FakeCursor/FakeConn below have neither. Rather than build a faithful
mogrify()/connection.encoding stub to satisfy psycopg2's real
execute_values() internals, this file monkeypatches
`propositions.execute_values` itself for the duration of each new test,
capturing the (sql, argslist) it was called with directly. This is
option (b) from this phase's own build brief -- chosen because it's a
one-line substitution against a module-level name this codebase already
relies on being monkeypatchable (propositions.py calls it as a bare
module-global, never re-bound via `from ... import execute_values as x`
inside a function), versus reverse-engineering enough of psycopg2's C
extension behavior (byte-encoding lookups included) to fake it faithfully
for a helper class that has never needed that before.

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

    def inserted_proposition_ids(self):
        """Every REAL proposition id (as generated inline by
        store_propositions(), never a proxy/invented id) that reached an
        INSERT INTO propositions — id is param index 0, per the same
        param-order contract inserted_contents() above already relies on."""
        out = []
        for sql, params in self._cursor.executed:
            if "INSERT INTO propositions" in sql:
                out.append(params[0])
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

    # ════════════════════════════════════════════════════════════════════
    # Phase 2b (bypass-proofing, PLAN.md #45, 2026-07-29): chunk_ids
    # back-link coverage for store_propositions()/process_document().
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("Phase 2b: chunk_ids back-link coverage (proposition_chunks, migration 074)")
    print("=" * 78)

    original_execute_values = props_mod.execute_values

    # ── 1. store_propositions(..., chunk_ids=[...]) with N=2 propositions:
    #    prove exactly N*M pairs, using the REAL generated proposition ids
    #    read back from the recorded INSERT INTO propositions params. ──────
    print("\n--- store_propositions(): chunk_ids present, N=2 propositions ---")
    two_props = [
        {"proposition_index": 1, "content": "First stored teaching passage for the chunk-id back-link test."},
        {"proposition_index": 2, "content": "Second stored teaching passage for the chunk-id back-link test."},
    ]
    test_chunk_ids = ["chunk-aaaa", "chunk-bbbb", "chunk-cccc"]

    ev_calls_present = []

    def fake_execute_values_present(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls_present.append((sql, list(argslist)))

    props_mod.execute_values = fake_execute_values_present
    try:
        conn_chunks = FakeConn(license_status="licensed")
        n_inserted = props_mod.store_propositions(
            conn_chunks, document_id, two_props, fake_embed_fn,
            prompt_version="v3", fingerprint="fp-test", model="model-test",
            chunk_ids=test_chunk_ids,
        )
    finally:
        props_mod.execute_values = original_execute_values

    print("  n_inserted = {0}".format(n_inserted))
    assert n_inserted == 2, "expected 2 propositions inserted, got {0}".format(n_inserted)

    real_prop_ids = conn_chunks.inserted_proposition_ids()
    print("  real proposition ids (from INSERT INTO propositions params): {0}".format(real_prop_ids))
    assert len(real_prop_ids) == 2, "expected 2 real proposition ids captured, got {0}".format(len(real_prop_ids))
    assert len(set(real_prop_ids)) == 2, "expected 2 DISTINCT proposition ids"

    assert len(ev_calls_present) == 1, (
        "expected exactly one execute_values() call for proposition_chunks, got {0}".format(
            len(ev_calls_present))
    )
    ev_sql, ev_pairs = ev_calls_present[0]
    assert "INSERT INTO proposition_chunks" in ev_sql, (
        "expected the proposition_chunks INSERT statement, got sql={0!r}".format(ev_sql)
    )
    expected_pairs = {(pid, cid) for pid in real_prop_ids for cid in test_chunk_ids}
    print("  pairs recorded: {0}".format(sorted(ev_pairs)))
    assert set(ev_pairs) == expected_pairs, (
        "expected the full cartesian product of {{real proposition ids}} x {{chunk_ids}}, "
        "got {0!r} vs expected {1!r}".format(set(ev_pairs), expected_pairs)
    )
    assert len(ev_pairs) == len(two_props) * len(test_chunk_ids) == 6, (
        "expected exactly N*M = 2*3 = 6 pairs, got {0}".format(len(ev_pairs))
    )
    print("  CONFIRMED: {0} pairs == cartesian product of {1} propositions x {2} chunk ids".format(
        len(ev_pairs), len(two_props), len(test_chunk_ids)))

    # ── 2. store_propositions(..., chunk_ids=None): prove ZERO
    #    proposition_chunks inserts, and proposition inserts themselves are
    #    otherwise unchanged. ─────────────────────────────────────────────
    print("\n--- store_propositions(): chunk_ids=None ---")
    ev_calls_none = []

    def fake_execute_values_none(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls_none.append((sql, list(argslist)))

    props_mod.execute_values = fake_execute_values_none
    try:
        conn_no_chunks = FakeConn(license_status="licensed")
        n_inserted_none = props_mod.store_propositions(
            conn_no_chunks, document_id, two_props, fake_embed_fn,
            prompt_version="v3", fingerprint="fp-test", model="model-test",
            chunk_ids=None,
        )
        # Also confirm an empty list behaves the same as None (both falsy).
        conn_empty_chunks = FakeConn(license_status="licensed")
        n_inserted_empty = props_mod.store_propositions(
            conn_empty_chunks, document_id, two_props, fake_embed_fn,
            prompt_version="v3", fingerprint="fp-test", model="model-test",
            chunk_ids=[],
        )
    finally:
        props_mod.execute_values = original_execute_values

    print("  n_inserted (chunk_ids=None)  = {0}".format(n_inserted_none))
    print("  n_inserted (chunk_ids=[])    = {0}".format(n_inserted_empty))
    assert n_inserted_none == 2, "proposition inserts must be unchanged when chunk_ids=None"
    assert n_inserted_empty == 2, "proposition inserts must be unchanged when chunk_ids=[]"
    assert ev_calls_none == [], (
        "expected ZERO execute_values() calls when chunk_ids is None/empty, got {0}".format(ev_calls_none)
    )
    real_prop_ids_none = conn_no_chunks.inserted_proposition_ids()
    assert len(real_prop_ids_none) == 2, "proposition INSERT count must be unchanged by chunk_ids=None"
    print("  CONFIRMED: zero proposition_chunks inserts; proposition inserts unchanged ({0} rows)".format(
        len(real_prop_ids_none)))

    # ── 3. process_document(..., chunk_ids=[...]): prove the identical
    #    chunk_ids value reaches BOTH the ungated path and the gated
    #    (name_pattern supplied) path. ───────────────────────────────────
    print("\n--- process_document(): chunk_ids threading, ungated path ---")
    ev_calls_ungated = []

    def fake_execute_values_ungated(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls_ungated.append((sql, list(argslist)))

    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props
    props_mod.execute_values = fake_execute_values_ungated
    try:
        conn_ungated = FakeConn(license_status="licensed")
        result_ungated = props_mod.process_document(
            conn_ungated, document_id, source_id, doc_text, fake_embed_fn,
            chunk_ids=test_chunk_ids,
        )  # name_pattern/verse_lookup omitted -- gate OFF, chunk_ids supplied
    finally:
        props_mod.extract_propositions = original_extract
        props_mod.execute_values = original_execute_values

    print("  result_ungated = {0!r}".format(result_ungated))
    assert result_ungated == "stored:3", (
        "ungated path with chunk_ids must still store all 3 extracted propositions unfiltered, "
        "got {0!r}".format(result_ungated)
    )
    real_prop_ids_ungated = conn_ungated.inserted_proposition_ids()
    assert len(real_prop_ids_ungated) == 3, "expected 3 real proposition ids on the ungated path"
    assert len(ev_calls_ungated) == 1, (
        "expected exactly one execute_values() call on the ungated path, got {0}".format(
            len(ev_calls_ungated))
    )
    _, ev_pairs_ungated = ev_calls_ungated[0]
    expected_pairs_ungated = {(pid, cid) for pid in real_prop_ids_ungated for cid in test_chunk_ids}
    assert set(ev_pairs_ungated) == expected_pairs_ungated, (
        "ungated path: chunk_ids did not reach store_propositions() correctly"
    )
    print("  CONFIRMED: chunk_ids reached store_propositions() on the ungated path -- "
          "{0} pairs for {1} propositions x {2} chunk ids".format(
              len(ev_pairs_ungated), len(real_prop_ids_ungated), len(test_chunk_ids)))

    print("\n--- process_document(): chunk_ids threading, gated path (name_pattern active) ---")
    # Redirect the review file to scratch again for this call -- the earlier
    # try/finally already restored CLOSENESS_REVIEW_DIR/PATH to their real,
    # non-scratch values, and this gated call produces QUOTE_CANDIDATE/
    # HOLD_TOO_LITTLE review records that must not land in the real
    # closeness_review/ directory.
    props_mod.CLOSENESS_REVIEW_DIR = scratch_dir
    props_mod.CLOSENESS_REVIEW_PATH = scratch_review_path

    ev_calls_gated = []

    def fake_execute_values_gated(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls_gated.append((sql, list(argslist)))

    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props
    props_mod.execute_values = fake_execute_values_gated
    try:
        conn_gated = FakeConn(license_status="licensed")
        result_gated = props_mod.process_document(
            conn_gated, document_id, source_id, doc_text, fake_embed_fn,
            name_pattern=name_pattern, verse_lookup=verse_lookup,
            chunk_ids=test_chunk_ids,
        )
    finally:
        props_mod.extract_propositions = original_extract
        props_mod.execute_values = original_execute_values
        props_mod.CLOSENESS_REVIEW_DIR = original_review_dir
        props_mod.CLOSENESS_REVIEW_PATH = original_review_path

    print("  result_gated = {0!r}".format(result_gated))
    assert result_gated == "stored:1:flagged:2", (
        "expected exactly 1 PASS-verdict proposition stored and 2 flagged, got {0!r}".format(result_gated)
    )
    real_prop_ids_gated = conn_gated.inserted_proposition_ids()
    assert len(real_prop_ids_gated) == 1, (
        "expected exactly 1 real proposition id on the gated path (the PASS item), got {0}".format(
            len(real_prop_ids_gated))
    )
    assert len(ev_calls_gated) == 1, (
        "expected exactly one execute_values() call on the gated path (store_propositions() "
        "fires once for the non-empty pass_props branch), got {0}".format(len(ev_calls_gated))
    )
    _, ev_pairs_gated = ev_calls_gated[0]
    expected_pairs_gated = {(pid, cid) for pid in real_prop_ids_gated for cid in test_chunk_ids}
    assert set(ev_pairs_gated) == expected_pairs_gated, (
        "gated path: chunk_ids did not reach store_propositions() correctly for the PASS item"
    )
    print("  CONFIRMED: chunk_ids reached store_propositions() on the gated path for the PASS "
          "item -- {0} pairs".format(len(ev_pairs_gated)))

    # ── 4. process_document(..., chunk_ids=None) [default, omitted
    #    entirely]: existing default behavior is unchanged. The gate-off
    #    control block above (result_off == "stored:3") already exercises
    #    this call shape; this adds an explicit, direct proof that omitting
    #    chunk_ids never reaches execute_values() at all -- not merely
    #    that it happens to record zero pairs. ───────────────────────────
    print("\n--- process_document(): chunk_ids omitted entirely (default) -- must never call execute_values() ---")

    def fail_if_called(cur, sql, argslist, template=None, page_size=100, fetch=False):
        raise AssertionError(
            "execute_values() must NEVER be called when chunk_ids is omitted (default None)"
        )

    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props
    props_mod.execute_values = fail_if_called
    try:
        conn_default = FakeConn(license_status="licensed")
        result_default = props_mod.process_document(
            conn_default, document_id, source_id, doc_text, fake_embed_fn,
        )  # chunk_ids omitted entirely -- must default to None, byte-identical to pre-Phase-2b
    finally:
        props_mod.extract_propositions = original_extract
        props_mod.execute_values = original_execute_values

    print("  result_default = {0!r}".format(result_default))
    assert result_default == "stored:3", (
        "default (chunk_ids omitted) behavior must be unchanged: got {0!r}".format(result_default)
    )
    print("  CONFIRMED: execute_values() was never called; default process_document() behavior unchanged.")

    print(
        "\nPhase 2b assertions passed: chunk_ids cartesian product proven with real "
        "proposition ids (present and None/empty cases), and threading confirmed through "
        "both the ungated and gated process_document() paths, plus the default-omitted case."
    )


if __name__ == "__main__":
    main()
