#!/usr/bin/env python3
"""
test_propositions_closeness_gate.py — Phase 5 DB-free mock proof for the
closeness-check gate wired into propositions.process_document() (PLAN.md
#45 Phase 5), extended in Phase 2b (bypass-proofing, PLAN.md #45,
2026-07-29) with coverage for the new chunk_ids back-link parameter on
store_propositions()/process_document() (proposition_chunks, migration
074).

RETIRED (project owner decision, 2026-07-29): near-verbatim reuse of a
teacher's own wording is now an accepted risk, not something to review or
block — propositions.CLOSENESS_CHECK_RETIRED forces process_document()'s
gate-off branch unconditionally, regardless of what any caller supplies
for name_pattern/verse_lookup/vocab_matcher. The sections below that
originally proved the gate-ACTIVE partition now instead prove the gate
stays OFF and closeness_check.classify() is never invoked from
process_document(), even when name_pattern/verse_lookup are explicitly
supplied — see the classify() call-spy in main() below. This is the
single clearest evidence that the retirement holds.

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
small hand-made set — a pure in-memory regex compile, no DB call) —
specifically to prove the gate stays OFF even when a caller tries to
activate it. Post-retirement this is "off no matter what," not merely
"off by default."

What this proves, both sides of the (now-collapsed) partition:
  1. All three hand-made propositions reach the (mocked) store_propositions()
     call unfiltered — visible via FakeCursor's recorded INSERT statements —
     even though name_pattern/verse_lookup were explicitly supplied.
  2. closeness_check.classify() is never called at all from
     process_document()'s path — proven via a call-spy, not merely inferred
     from the return value (this file's own established convention, see the
     extract_propositions() spy in Phase 3 below).
  3. The review file is never written.
  4. classify() called DIRECTLY (not through process_document()) is
     unaffected and still works — closeness_check.py itself is untouched by
     retirement, only process_document()'s wiring into it is.

Run: python3 scripts/test_propositions_closeness_gate.py
"""
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
    # propositions below are classified against. Padded to >=50 words
    # (bypass-proofing Phase 3, PLAN.md #45, 2026-07-29 word-count floor --
    # propositions.MIN_SUBSTANTIVE_WORD_COUNT) so process_document() below
    # proceeds past the new floor check instead of short-circuiting to
    # "too_thin_to_extract" before ever reaching the monkeypatched
    # extract_propositions(). The padding sentence is deliberately unrelated
    # filler (administrative record-keeping, no shared vocabulary with
    # pass_content/quote_content/hold_content below) appended AFTER the
    # original sentences -- it does not alter or remove any existing
    # substring, so it cannot change any classify() containment/longest-run
    # verdict against the original three hand-made propositions (confirmed
    # empirically by this file's own ground-truth assertions just below,
    # which are unchanged from before this padding was added).
    doc_text = (
        "The prophet declared that revival always begins with brokenness before God, "
        "not with strategy or method. This happened once at a large gathering many "
        "years ago in a small town, remembered vividly by those present. "
        "Attendance records from that season were later archived in a regional office "
        "building for administrative purposes, unrelated to anything preached that week."
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
    # Retained unchanged after retirement: this calls closeness_check.classify()
    # directly, not through process_document() -- it's a sanity-check of the
    # classifier function itself (still fully functional, untouched by
    # retirement), not a test of process_document()'s (now-retired) partition.
    # See the classify() call-spy below for the actual proof that
    # process_document() itself never reaches classify() anymore.
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

    # Call-spy on closeness_check.classify() -- proves process_document()
    # never reaches it, rather than merely inferring that from the return
    # value (this file's own established convention, see the
    # extract_propositions() spy in Phase 3 below). Wraps the real function
    # so it would still behave correctly if it WERE somehow called.
    classify_calls = []
    original_classify = cc.classify

    def _classify_spy(*a, **kw):
        classify_calls.append((a, kw))
        return original_classify(*a, **kw)

    cc.classify = _classify_spy
    try:
        conn = FakeConn(license_status="licensed")
        result = props_mod.process_document(
            conn, document_id, source_id, doc_text, fake_embed_fn,
            name_pattern=name_pattern, verse_lookup=verse_lookup,
        )
    finally:
        cc.classify = original_classify
        props_mod.extract_propositions = original_extract
        props_mod.CLOSENESS_REVIEW_DIR = original_review_dir
        props_mod.CLOSENESS_REVIEW_PATH = original_review_path

    print("\n--- process_document() result (gate retirement proof) ---")
    print("  result = {0!r}".format(result))
    print("  conn.committed = {0}".format(conn.committed))
    print("  conn.rolled_back = {0}".format(conn.rolled_back))
    print("  closeness_check.classify() call count = {0}".format(len(classify_calls)))

    assert classify_calls == [], (
        "expected closeness_check.classify() to be called ZERO times from "
        "process_document() now that CLOSENESS_CHECK_RETIRED makes the gate "
        "permanently inert -- got {0} call(s), even though name_pattern was "
        "explicitly supplied".format(len(classify_calls))
    )
    assert result == "stored:3", (
        "expected 'stored:3' (gate retired, all 3 unfiltered), got {0!r}".format(result)
    )
    assert not conn.rolled_back, "expected no rollback on a clean run"
    assert conn.committed, "expected store_propositions() to have committed (3 items, unfiltered)"

    # ── All three items reach store_propositions() unfiltered, even though
    #    name_pattern/verse_lookup were explicitly supplied ─────────────────
    inserted = conn.inserted_contents()
    print("\n--- Contents that reached the (mocked) store_propositions() INSERT ---")
    for c in inserted:
        print("  INSERTED: {0!r}".format(c))
    assert inserted == [pass_content, quote_content, hold_content], (
        "expected all three contents, unfiltered and in extraction order, "
        "got {0!r}".format(inserted)
    )

    # ── The review file is never written -- retirement means there is no
    #    QUOTE_CANDIDATE/HOLD_TOO_LITTLE side to the (now-collapsed)
    #    partition anymore ────────────────────────────────────────────────
    assert not scratch_review_path.exists(), (
        "expected the review file to NOT be written -- the gate is retired, "
        "so there is no partition to record"
    )
    print("\n--- Review file: absent, as expected (gate retired) ---")

    # ── Confirm the (now behaviorally identical) path with name_pattern
    #    omitted entirely still works the same way -- kept separate because
    #    it exercises a distinct call shape (omitting the params vs.
    #    supplying-but-ignored-per-retirement) ──────────────────────────────
    print("\n--- Control: same hand-made props, name_pattern=None (name_pattern omitted entirely) ---")
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
    assert not scratch_review_path.exists(), (
        "review file must still not exist after the omitted-name_pattern control call either"
    )

    print(
        "\nAll assertions passed. Gate retirement confirmed: classify() never called even "
        "with name_pattern explicitly supplied, all 3 items stored unfiltered, no review "
        "file written; name_pattern-omitted control path confirmed identical."
    )

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
            prompt_version="v3",
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
            prompt_version="v3",
            chunk_ids=None,
        )
        # Also confirm an empty list behaves the same as None (both falsy).
        conn_empty_chunks = FakeConn(license_status="licensed")
        n_inserted_empty = props_mod.store_propositions(
            conn_empty_chunks, document_id, two_props, fake_embed_fn,
            prompt_version="v3",
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

    print("\n--- process_document(): chunk_ids threading, name_pattern supplied but gate "
          "retired (proves chunk_ids threading is unaffected by an attempted gate activation) ---")
    # Redirect the review file to scratch again for this call -- defensively
    # unnecessary now (retirement means no review file will be written
    # regardless), but kept in case this decision is ever reversed.
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
    assert result_gated == "stored:3", (
        "expected 'stored:3' (gate retired, all 3 unfiltered even with name_pattern supplied), "
        "got {0!r}".format(result_gated)
    )
    real_prop_ids_gated = conn_gated.inserted_proposition_ids()
    assert len(real_prop_ids_gated) == 3, (
        "expected 3 real proposition ids (all items, gate retired), got {0}".format(
            len(real_prop_ids_gated))
    )
    assert len(ev_calls_gated) == 1, (
        "expected exactly one execute_values() call (store_propositions() fires once for the "
        "single unconditional store call), got {0}".format(len(ev_calls_gated))
    )
    _, ev_pairs_gated = ev_calls_gated[0]
    expected_pairs_gated = {(pid, cid) for pid in real_prop_ids_gated for cid in test_chunk_ids}
    assert set(ev_pairs_gated) == expected_pairs_gated, (
        "chunk_ids did not reach store_propositions() correctly for all 3 items"
    )
    assert len(ev_pairs_gated) == 3 * len(test_chunk_ids) == 9, (
        "expected 3 propositions x 3 chunk ids = 9 pairs, got {0}".format(len(ev_pairs_gated))
    )
    assert not scratch_review_path.exists(), (
        "review file must not be written even when name_pattern is supplied (gate retired)"
    )
    print("  CONFIRMED: chunk_ids reached store_propositions() for all 3 items even with "
          "name_pattern supplied -- {0} pairs, no review file written (gate retired).".format(
              len(ev_pairs_gated)))

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

    # ════════════════════════════════════════════════════════════════════
    # Phase 3 (bypass-proofing, PLAN.md #45, 2026-07-29): word-count floor
    # (MIN_SUBSTANTIVE_WORD_COUNT / "too_thin_to_extract") coverage.
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("Phase 3: word-count floor (too_thin_to_extract) coverage")
    print("=" * 78)

    class _ExtractSpy:
        """Call-counting stand-in for extract_propositions() -- proves the
        model path was or was NOT reached, not merely that process_document()
        returned without error (CLAUDE.md reporting rule: a clean exit is not
        proof a specific step ran)."""
        def __init__(self, return_value):
            self.calls = 0
            self._return_value = return_value

        def __call__(self, text, doc_id="", **kw):
            self.calls += 1
            return self._return_value

    # ── 1. Floor skips extraction, proven not just inferred: a genuinely
    #    thin (10-word) document returns "too_thin_to_extract" AND the spy
    #    shows extract_propositions() was called ZERO times. ───────────────
    print("\n--- 10-word document: floor fires, extract_propositions() never called ---")
    ten_word_text = "This is only a very short ten word document here."
    assert len(ten_word_text.split()) == 10, (
        "fixture must be exactly 10 words, got {0}".format(len(ten_word_text.split()))
    )
    spy_thin = _ExtractSpy(hand_made_props)
    props_mod.extract_propositions = spy_thin
    try:
        conn_thin = FakeConn(license_status="licensed")
        result_thin = props_mod.process_document(
            conn_thin, document_id, source_id, ten_word_text, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract

    print("  result_thin = {0!r}".format(result_thin))
    print("  extract_propositions() call count = {0}".format(spy_thin.calls))
    assert result_thin == "too_thin_to_extract", (
        "expected 'too_thin_to_extract' for a 10-word document, got {0!r}".format(result_thin)
    )
    assert spy_thin.calls == 0, (
        "extract_propositions() must NEVER be called when the floor fires, got {0} calls".format(
            spy_thin.calls)
    )
    assert not conn_thin.committed and not conn_thin.rolled_back, (
        "too_thin_to_extract must not touch the connection's commit/rollback state"
    )
    print("  CONFIRMED: floor fires, model never called, connection untouched.")

    # ── 2. Boundary test: exactly 50 words proceeds to extraction; exactly
    #    49 words does not. Strict less-than: MIN_SUBSTANTIVE_WORD_COUNT
    #    (50) words itself proceeds; 49 is too thin. ────────────────────────
    def _make_word_text(n):
        """Builds a plain n-word string of distinct filler words -- content
        doesn't matter here, only the word count."""
        return " ".join("word{0}".format(i) for i in range(n))

    text_50 = _make_word_text(50)
    text_49 = _make_word_text(49)
    assert len(text_50.split()) == 50
    assert len(text_49.split()) == 49
    assert props_mod.MIN_SUBSTANTIVE_WORD_COUNT == 50, (
        "this boundary test assumes the floor constant is 50 -- got {0}".format(
            props_mod.MIN_SUBSTANTIVE_WORD_COUNT)
    )

    print("\n--- Boundary: exactly 50 words -> proceeds to extraction ---")
    spy_50 = _ExtractSpy(hand_made_props)
    props_mod.extract_propositions = spy_50
    try:
        conn_50 = FakeConn(license_status="licensed")
        result_50 = props_mod.process_document(
            conn_50, document_id, source_id, text_50, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract
    print("  result_50 = {0!r}, extract_propositions() calls = {1}".format(result_50, spy_50.calls))
    assert spy_50.calls == 1, (
        "exactly 50 words must proceed to extraction (strict less-than boundary), "
        "got {0} calls".format(spy_50.calls)
    )
    assert result_50 == "stored:3", (
        "expected 'stored:3' for the 50-word boundary case (gate off, 3 hand-made props), "
        "got {0!r}".format(result_50)
    )

    print("\n--- Boundary: exactly 49 words -> too_thin_to_extract, extraction never called ---")
    spy_49 = _ExtractSpy(hand_made_props)
    props_mod.extract_propositions = spy_49
    try:
        conn_49 = FakeConn(license_status="licensed")
        result_49 = props_mod.process_document(
            conn_49, document_id, source_id, text_49, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract
    print("  result_49 = {0!r}, extract_propositions() calls = {1}".format(result_49, spy_49.calls))
    assert result_49 == "too_thin_to_extract", (
        "expected 'too_thin_to_extract' for a 49-word document, got {0!r}".format(result_49)
    )
    assert spy_49.calls == 0, (
        "49 words must be strictly below the floor -- extract_propositions() must not be "
        "called, got {0} calls".format(spy_49.calls)
    )
    print("  CONFIRMED boundary is strict less-than: 50 words proceeds to extraction, 49 does not.")

    # ── 3. Gate priority: a thin-but-Precept-Austin document still returns
    #    "skipped_precept_austin" (that gate fires FIRST, before the floor
    #    even runs), and a thin-but-public_domain document still returns
    #    "skipped_licensed" (license gate fires before the floor too) --
    #    extraction spy proves zero calls either way, and the RETURN VALUE
    #    proves which specific gate actually fired. ─────────────────────────
    print("\n--- Gate priority: thin (5-word) + Precept Austin -> 'skipped_precept_austin' ---")
    five_word_text = "Too short to matter here."
    assert len(five_word_text.split()) == 5
    spy_pa = _ExtractSpy(hand_made_props)
    props_mod.extract_propositions = spy_pa
    try:
        conn_pa = FakeConn(license_status="licensed")  # irrelevant -- PA gate fires before license lookup
        result_pa = props_mod.process_document(
            conn_pa, document_id, props_mod.PRECEPT_AUSTIN_SOURCE_ID, five_word_text, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract
    print("  result_pa = {0!r}, extract_propositions() calls = {1}".format(result_pa, spy_pa.calls))
    assert result_pa == "skipped_precept_austin", (
        "Precept Austin gate must fire before the word-count floor, got {0!r}".format(result_pa)
    )
    assert spy_pa.calls == 0

    print("\n--- Gate priority: thin (5-word) + public_domain source -> 'skipped_licensed' ---")
    spy_pd = _ExtractSpy(hand_made_props)
    props_mod.extract_propositions = spy_pd
    try:
        conn_pd = FakeConn(license_status="public_domain")
        result_pd = props_mod.process_document(
            conn_pd, document_id, source_id, five_word_text, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract
    print("  result_pd = {0!r}, extract_propositions() calls = {1}".format(result_pd, spy_pd.calls))
    assert result_pd == "skipped_licensed", (
        "license-status gate must fire before the word-count floor, got {0!r}".format(result_pd)
    )
    assert spy_pd.calls == 0

    print(
        "\nPhase 3 assertions passed: word-count floor proven via extract_propositions() call-"
        "count spy (not just inferred from a clean return), strict less-than boundary confirmed "
        "(50 proceeds, 49 doesn't), and gate priority confirmed (Precept-Austin and license-"
        "status gates both fire before the floor for an equally-thin document)."
    )

    # ════════════════════════════════════════════════════════════════════
    # Phase 4 (bypass-proofing, PLAN.md #45, 2026-07-29): provenance-
    # stamping enforcement at store_propositions()'s own signature --
    # prompt_version is now REQUIRED (no default), and fingerprint/model
    # are no longer caller-suppliable at all -- derived internally from
    # prompt_version every call (see propositions.py's store_propositions()
    # docstring).
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("Phase 4: provenance-stamping enforcement (store_propositions() signature)")
    print("=" * 78)

    # ── 1. Omitting prompt_version -> TypeError, ZERO DB calls. Mirrors the
    #    deleted sample_v4_propositions_2026-07-23.py's exact bypass shape:
    #    store_propositions(conn, doc_id, props, embed_fn) -- 4 bare
    #    positional args, nothing else. chunk_ids stays at its default
    #    (None) so execute_values()/mogrify is never reached -- this test
    #    only needs to prove the TypeError fires before ANY cursor
    #    activity, not exercise the chunk-linking path. ─────────────────────
    print("\n--- store_propositions() with no prompt_version -> TypeError, zero DB calls ---")
    bypass_shape_props = [
        {"proposition_index": 1, "content": "A hand-made teaching passage, no provenance supplied."},
    ]
    conn_bypass = FakeConn(license_status="licensed")
    raised = None
    try:
        # Exact 4-positional-arg call shape of the deleted bypass script --
        # no prompt_version, no fingerprint, no model, no chunk_ids.
        props_mod.store_propositions(conn_bypass, document_id, bypass_shape_props, fake_embed_fn)
    except TypeError as exc:
        raised = exc
    print("  raised: {0!r}".format(raised))
    assert raised is not None, "expected a TypeError when prompt_version is omitted"
    assert len(conn_bypass._cursor.executed) == 0, (
        "expected ZERO DB calls before the TypeError -- got {0}".format(
            len(conn_bypass._cursor.executed))
    )
    print("  CONFIRMED: TypeError raised at call-binding time, before any cursor.execute() call.")

    # ── 2. prompt_version="v3" supplied, no fingerprint/model kwargs (they
    #    no longer exist as parameters at all) -> succeeds, and the derived
    #    fingerprint/model recorded in the INSERT match prompt_fingerprint()
    #    computed independently in this test. ───────────────────────────────
    print("\n--- store_propositions(prompt_version='v3'), derived fingerprint/model correctness ---")
    conn_derived = FakeConn(license_status="licensed")
    n_derived = props_mod.store_propositions(
        conn_derived, document_id, bypass_shape_props, fake_embed_fn,
        prompt_version="v3",
    )
    assert n_derived == 1
    insert_calls = [
        (sql, params) for sql, params in conn_derived._cursor.executed
        if "INSERT INTO propositions" in sql
    ]
    assert len(insert_calls) == 1, "expected exactly 1 INSERT INTO propositions call"
    _, params = insert_calls[0]
    expected_fp_v3 = props_mod.prompt_fingerprint("v3")
    print("  params[5] (prompt_version) = {0!r}".format(params[5]))
    print("  params[6] (fingerprint)    = {0!r}".format(params[6]))
    print("  params[7] (model)          = {0!r}".format(params[7]))
    assert params[5] == "v3"
    assert params[6] == expected_fp_v3
    assert params[7] == props_mod.EXTRACTION_MODEL
    print("  CONFIRMED: derived fingerprint/model match prompt_fingerprint('v3')/EXTRACTION_MODEL, "
          "computed independently in this test.")

    # ── 3. process_document() end-to-end: the real ungated call site
    #    (DEFAULT_PROMPT_VERSION) produces the same independently-verifiable
    #    match in the actual INSERT params. ─────────────────────────────────
    print("\n--- process_document() end-to-end: ungated call site provenance ---")
    props_mod.extract_propositions = lambda text, doc_id="", **kw: hand_made_props
    try:
        conn_e2e = FakeConn(license_status="licensed")
        result_e2e = props_mod.process_document(
            conn_e2e, document_id, source_id, doc_text, fake_embed_fn,
        )
    finally:
        props_mod.extract_propositions = original_extract
    print("  result_e2e = {0!r}".format(result_e2e))
    assert result_e2e == "stored:3", (
        "expected 'stored:3' for the end-to-end ungated provenance check, got {0!r}".format(result_e2e)
    )
    insert_calls_e2e = [
        (sql, params) for sql, params in conn_e2e._cursor.executed
        if "INSERT INTO propositions" in sql
    ]
    assert len(insert_calls_e2e) == 3, "expected 3 INSERT INTO propositions calls"
    expected_fp_default = props_mod.prompt_fingerprint(props_mod.DEFAULT_PROMPT_VERSION)
    for _, params in insert_calls_e2e:
        assert params[5] == props_mod.DEFAULT_PROMPT_VERSION
        assert params[6] == expected_fp_default
        assert params[7] == props_mod.EXTRACTION_MODEL
    print("  CONFIRMED: process_document()'s real ungated call site stamps params[6]/[7] == "
          "prompt_fingerprint(DEFAULT_PROMPT_VERSION)/EXTRACTION_MODEL, computed independently.")

    print(
        "\nPhase 4 assertions passed: omitted prompt_version raises TypeError with zero DB calls; "
        "supplied prompt_version derives correct fingerprint/model internally; process_document()'s "
        "real call site stamps matching provenance end-to-end."
    )

    # ════════════════════════════════════════════════════════════════════
    # Step 6 (bypass-proofing Phase 4 disclosure, PLAN.md #45, 2026-07-29):
    # concrete demonstration of two gaps this phase does NOT close --
    # disclosed, not remediated. Neither is fixed here; the point of this
    # section is honest evidence, not remediation.
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("Step 6: disclosed-gap demonstrations (NOT fixed this phase)")
    print("=" * 78)

    # ── Gap 1: license-gate/Precept-Austin bypass is still real. Calling
    #    store_propositions() DIRECTLY (never through process_document())
    #    with a document_id that notionally belongs to a public_domain
    #    source, with a fully valid prompt_version supplied, still inserts
    #    -- because no license lookup exists anywhere on
    #    store_propositions()'s own call path. get_license_status()/
    #    PRECEPT_AUSTIN_SOURCE_ID checks live ONLY inside
    #    process_document(), one function up; a caller that reaches storage
    #    directly never passes through either check. ─────────────────────
    print("\n--- Gap 1: license-gate/Precept-Austin bypass still real ---")
    public_domain_document_id = "33333333-3333-3333-3333-333333333333"
    gap_props = [
        {"proposition_index": 1, "content": "A teaching passage notionally belonging to a public_domain source."},
    ]
    # license_status="public_domain" here is purely notional annotation --
    # store_propositions() never calls get_license_status() at all, so this
    # FakeConn's license_status is never even read on this call path. That
    # absence of a read is itself the point being demonstrated.
    conn_gap1 = FakeConn(license_status="public_domain")
    n_gap1 = props_mod.store_propositions(
        conn_gap1, public_domain_document_id, gap_props, fake_embed_fn,
        prompt_version="v3",
    )
    print("  n_inserted = {0}".format(n_gap1))
    assert n_gap1 == 1, (
        "store_propositions() has no license check of its own -- it inserts "
        "regardless of what license_status the document_id would resolve to "
        "via process_document()'s gate"
    )
    insert_calls_gap1 = [
        s for s, p in conn_gap1._cursor.executed if "INSERT INTO propositions" in s
    ]
    assert len(insert_calls_gap1) == 1
    print(
        "  CONFIRMED (disclosed, NOT fixed this phase): store_propositions() has no license "
        "lookup on its own call path -- a caller reaching it directly (bypassing "
        "process_document()'s get_license_status()/PRECEPT_AUSTIN_SOURCE_ID checks) inserts "
        "successfully for a document_id that would have been skipped ('skipped_licensed' / "
        "'skipped_precept_austin') had it gone through process_document() instead."
    )

    # ── Gap 2: authenticity of `propositions` content itself is still
    #    unverifiable at this layer. Hand-construct content that never went
    #    through ANY Groq call -- literal Python strings authored directly
    #    in this test, not extracted from anything -- and call
    #    store_propositions() with an HONESTLY-supplied prompt_version. It
    #    inserts successfully, with a real, internally-consistent derived
    #    fingerprint/model -- because store_propositions() can only verify
    #    that fingerprint/model correctly DERIVE from the stated
    #    prompt_version, never that the stated prompt_version (or any
    #    prompt_version at all) actually produced this content. ───────────
    print("\n--- Gap 2: hand-fabricated-content authenticity gap still real ---")
    fabricated_props = [
        {
            "proposition_index": 1,
            "content": (
                "This exact sentence was typed directly into a test file by a person. "
                "No Groq call, no model, no extraction pipeline of any kind produced it."
            ),
        },
    ]
    conn_gap2 = FakeConn(license_status="licensed")
    n_gap2 = props_mod.store_propositions(
        conn_gap2, document_id, fabricated_props, fake_embed_fn,
        prompt_version="v3",  # honestly supplied -- the gap is NOT about lying about this value
    )
    print("  n_inserted = {0}".format(n_gap2))
    assert n_gap2 == 1
    insert_calls_gap2 = [
        (s, p) for s, p in conn_gap2._cursor.executed if "INSERT INTO propositions" in s
    ]
    assert len(insert_calls_gap2) == 1
    _, params_gap2 = insert_calls_gap2[0]
    expected_fp_gap2 = props_mod.prompt_fingerprint("v3")
    assert params_gap2[2] == fabricated_props[0]["content"], (
        "the hand-fabricated content itself is stored verbatim, unexamined for authenticity"
    )
    assert params_gap2[6] == expected_fp_gap2
    assert params_gap2[7] == props_mod.EXTRACTION_MODEL
    print(
        "  CONFIRMED (disclosed, NOT fixed this phase): hand-fabricated content, never produced "
        "by any Groq call, inserts successfully with a real, internally-consistent derived "
        "fingerprint/model -- store_propositions() can only verify that fingerprint/model "
        "correctly DERIVE from the stated prompt_version, never that the stated prompt_version "
        "(or anything at all) actually produced this content."
    )

    print(
        "\nStep 6 disclosed-gap demonstrations complete: both gaps shown concretely via direct "
        "store_propositions() calls, neither remediated (out of scope for this phase, per its "
        "own build brief)."
    )


if __name__ == "__main__":
    main()
