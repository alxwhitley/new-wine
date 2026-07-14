#!/usr/bin/env python3
"""
Track-B (constructed/injected) tests for the SP1 reference verifier.
Covers: biblical-figure backstop (proven as a real short-circuit via a fake
db, not a name that merely happens to have no alias), nonexistent verse,
not-servable teacher (Leonard Ravenhill — a live-fixture SKIP here counts
as a failure, not a silent pass-through), MISS (unaliased teacher) and
sentinel (fake-db, since no live alias currently points at the sentinel)
as two distinct checks, presence-check drop, occurrence anchoring for both
verses (every occurrence) and teachers (first occurrence only, via Derek
Prince — a real, live, currently-servable teacher), and malformed/
vague-reference robustness.

Run from project root: python3 scripts/test_reference_verifier.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services import reference_verifier
from app.services.reference_verifier import (
    parse_reference_mentions,
    find_occurrences,
    verify_references,
    verify_teacher_mention,
)
from app.services.source_resolver import normalize_alias_key

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]

db = create_client(SB_URL, SB_SVC)
failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  {status}  {label}")
    if not condition:
        failures.append(label)


class _FakeResult:
    """Mimics the `.data` attribute the real Supabase client's `.execute()`
    call returns."""

    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Mimics the chained `.select().eq().limit().execute()` call — each
    chain method just returns self; `.execute()` returns the canned rows
    for whichever table this chain was built for."""

    def __init__(self, data):
        self._data = data

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeDB:
    """Minimal stand-in for the real Supabase client, used only for
    constructed cases that need to exercise a specific guard branch
    directly rather than rely on a live fixture — either because no live
    fixture for that branch exists today (the sentinel), or because the
    point of the test is to prove a short-circuit happens BEFORE any DB
    call, which a live client can't prove on its own.

    `table_responses`: dict of table name -> list of rows `.execute().data`
    should return for that table.
    `on_table_call`: optional callback invoked with the table name every
    time `.table(name)` is called — lets a test assert a table was (or was
    NOT) ever touched.
    """

    def __init__(self, table_responses, on_table_call=None):
        self._table_responses = table_responses
        self._on_table_call = on_table_call

    def table(self, name):
        if self._on_table_call is not None:
            self._on_table_call(name)
        return _FakeQuery(self._table_responses.get(name, []))


def main():
    # --- Parsing robustness ---
    raw_output_malformed = "<answer>...</answer>\n<reference_mentions>\nVERSE: Romans 8:28\nGARBAGE LINE\nTEACHER:\n</reference_mentions>"
    proposals = parse_reference_mentions(raw_output_malformed)
    check(
        "Malformed lines are skipped, well-formed line survives",
        proposals == [{"type": "verse", "raw": "Romans 8:28"}],
    )

    check(
        "Missing <reference_mentions> block returns empty, not an error",
        parse_reference_mentions("<answer>no block here</answer>") == [],
    )

    # --- B1: Biblical-figure backstop ---
    # A tautological version of this test would just propose "Paul" against
    # the real live db and assert [] — but no source_aliases row for 'paul'
    # exists at all (confirmed live), so that assertion would still pass
    # even if the biblical-figure guard were deleted outright (the ordinary
    # MISS path alone would produce the same result). To prove the guard
    # itself short-circuits, use a fake db whose source_aliases lookup
    # WOULD resolve "Paul" to a real, non-sentinel, servable source if the
    # guard didn't fire first — and prove via a call-tracking flag that the
    # alias table is never even queried.
    b1_table_calls = []
    b1_fake_db = _FakeDB(
        table_responses={
            "source_aliases": [{"source_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
            "sources": [{"license_status": "owned", "visibility": "shown"}],
            "app_settings": [{"value": "off"}],
        },
        on_table_call=lambda name: b1_table_calls.append(name),
    )
    result_1 = verify_teacher_mention(b1_fake_db, "Paul")
    check(
        "B1: biblical-figure backstop short-circuits 'Paul' before any DB "
        "call — fake alias table (which would otherwise resolve to a real, "
        "non-sentinel, servable source) is never even queried",
        result_1 is None and b1_table_calls == [],
    )

    # --- B2: Nonexistent verse (Genesis 50 has 26 verses) ---
    answer_text_2 = "This is discussed in Genesis 50:99."
    raw_output_2 = "<reference_mentions>\nVERSE: Genesis 50:99\n</reference_mentions>"
    result_2 = verify_references(answer_text_2, raw_output_2, db)
    check("B2: nonexistent verse (Genesis 50:99) never resolves", result_2 == [])

    # --- B3: Not-servable teacher (Leonard Ravenhill — unlicensed/hidden) ---
    ravenhill_alias = db.table("source_aliases").select("source_id").eq(
        "alias_key", normalize_alias_key("Leonard Ravenhill")
    ).limit(1).execute()
    if not ravenhill_alias.data:
        # A SKIP here means the one fixture built to be "proven on demand,
        # every time" has silently drifted out from under the suite — the
        # exact kind of drift that already hit the Bosworth example earlier
        # in this plan. That must fail the run loudly, not print SKIP and
        # exit 0 as "ALL PASSED".
        print("  SKIP  B3: no live alias for 'Leonard Ravenhill' — treating as a FAILURE, not a pass-through")
        failures.append("B3: SKIPPED — live fixture 'Leonard Ravenhill' alias is missing (drift)")
    else:
        answer_text_3 = "Leonard Ravenhill preached extensively on revival and repentance."
        raw_output_3 = "<reference_mentions>\nTEACHER: Leonard Ravenhill\n</reference_mentions>"
        result_3 = verify_references(answer_text_3, raw_output_3, db)
        check("B3: Leonard Ravenhill (real alias, not servable) never resolves", result_3 == [])

    # --- MISS: a teacher name with no source_aliases row at all ---
    answer_text_4 = "Some Nonexistent Teacher Name talks about grace."
    raw_output_4 = "<reference_mentions>\nTEACHER: Some Nonexistent Teacher Name\n</reference_mentions>"
    result_4 = verify_references(answer_text_4, raw_output_4, db)
    check("MISS: an unaliased teacher name never resolves", result_4 == [])

    # --- Sentinel: alias resolves, but specifically to the sentinel id ---
    # No live source_aliases row currently points at the sentinel UUID, so
    # the sentinel-check branch itself (`if source_id == _SENTINEL_SOURCE_ID:
    # return None`) has no live fixture and was previously untested. Use a
    # fake db whose alias lookup returns the sentinel id directly, proving
    # this branch fires — rather than folding it into the MISS case above,
    # which only ever exercised the "no alias row at all" path.
    sentinel_fake_db = _FakeDB(
        table_responses={
            "source_aliases": [{"source_id": reference_verifier._SENTINEL_SOURCE_ID}],
        },
    )
    result_sentinel = verify_teacher_mention(sentinel_fake_db, "Fake Sentinel-Resolving Teacher")
    check(
        "Sentinel: an alias that resolves to the sentinel source_id never resolves",
        result_sentinel is None,
    )

    # --- Presence-check drop: proposal not actually in the text ---
    answer_text_5 = "This answer never mentions any verse at all."
    raw_output_5 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_5 = verify_references(answer_text_5, raw_output_5, db)
    check("Presence check drops a proposal that never appears in the answer", result_5 == [])

    # --- Vague reference: both fail the regex's required "chapter:verse"
    # colon match — neither "that verse" nor "verse 26" contains a colon,
    # so the regex never matches at all and no book-name lookup is ever
    # attempted ---
    answer_text_6 = "That verse we discussed earlier is important."
    raw_output_6 = "<reference_mentions>\nVERSE: that verse\nVERSE: verse 26\n</reference_mentions>"
    result_6 = verify_references(answer_text_6, raw_output_6, db)
    check("Vague references ('that verse', 'verse 26') never resolve", result_6 == [])

    # --- Occurrence anchoring: verse repeated 2x, every occurrence anchored ---
    answer_text_7 = "Romans 8:28 tells us this. Later, Romans 8:28 is echoed again."
    raw_output_7 = "<reference_mentions>\nVERSE: Romans 8:28\n</reference_mentions>"
    result_7 = verify_references(answer_text_7, raw_output_7, db)
    check(
        "Repeated verse mention anchors every occurrence",
        len(result_7) == 1 and result_7[0]["type"] == "verse" and len(result_7[0]["positions"]) == 2,
    )

    # --- Occurrence anchoring: teacher repeated 2x, only the FIRST anchored ---
    # Derek Prince confirmed live before writing this assertion:
    # source_aliases has 'derek prince' -> a source with
    # license_status='unlicensed', visibility='shown', and
    # is_source_servable() == True — a real, currently-servable teacher,
    # not a fake fixture.
    answer_text_8 = (
        "Derek Prince taught extensively on deliverance. "
        "Later in the sermon, Derek Prince returns to the same theme."
    )
    raw_output_8 = "<reference_mentions>\nTEACHER: Derek Prince\n</reference_mentions>"
    result_8 = verify_references(answer_text_8, raw_output_8, db)
    expected_first_position = find_occurrences(answer_text_8, "Derek Prince")[0]
    check(
        "Repeated teacher mention anchors ONLY the first occurrence position",
        len(result_8) == 1
        and result_8[0]["type"] == "teacher"
        and result_8[0]["position"] == expected_first_position,
    )

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
