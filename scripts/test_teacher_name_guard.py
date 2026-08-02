#!/usr/bin/env python3
"""Deterministic tests for the Phase 2 teacher-name guard (retrieval-grounded
naming). These reconstruct the exact fabrication mechanisms the 2026-08-01
Phase 0 pass measured (docs/audits/phase0_measurement_2026-08-01.md §1) as
controlled inputs, so the guard's blocking logic is proven regardless of
whether live generation happens to re-trigger the intermittent fabrication.

Everything here runs against fake DBs — no network, no live fixtures, no
cost. Live end-to-end confirmation against real generated answers is the
separate, cost-gated `verify_teacher_name_guard_live.py`.

Run from project root: python3 scripts/test_teacher_name_guard.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.reference_verifier import (
    RetrievalGrounding,
    build_retrieval_grounding,
    verify_references,
    verify_teacher_mention,
    _is_retrieval_grounded,
)
from app.services.source_resolver import normalize_alias_key

failures = []


def check(label, condition):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}")
    if not condition:
        failures.append(label)


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, data):
        self._data = data

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return _FakeResult(self._data)


class _RaisingQuery:
    def select(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def execute(self):
        raise RuntimeError("simulated documents lookup failure")


class _FakeDB:
    def __init__(self, table_responses, raising_tables=None):
        self._tr = table_responses
        self._raising = set(raising_tables or [])

    def table(self, name):
        if name in self._raising:
            return _RaisingQuery()
        return _FakeQuery(self._tr.get(name, []))


# A fake DB in which ANY teacher name resolves to one real, servable, non-
# sentinel source. This is the worst case for the guard: resolution, sentinel,
# and license checks all PASS, so the ONLY thing that can deny the link is the
# retrieval-grounding gate. Exactly the A.W. Tozer condition from Phase 0 §1(c).
def _resolving_servable_db(source_id):
    return _FakeDB(table_responses={
        "source_aliases": [{"source_id": source_id}],
        "sources": [{"license_status": "owned", "visibility": "shown"}],
        "app_settings": [{"value": "off"}],
    })


def _mentions(name):
    return (f"<answer>According to {name}, this is taught.</answer>\n"
            f"<reference_mentions>\nTEACHER: {name}\n</reference_mentions>")


def _answer(name):
    return f"According to {name}, this is taught."


def main():
    RETRIEVED = "11111111-aaaa-bbbb-cccc-222222222222"      # a source that WAS retrieved
    NOT_RETRIEVED = "99999999-dddd-eeee-ffff-888888888888"  # a source that was NOT

    # Grounding for a question where only "Derek Prince" (src RETRIEVED) and
    # "Andrew Murray" (by author name, no alias row) were retrieved.
    grounding = RetrievalGrounding(
        source_ids=frozenset({RETRIEVED}),
        author_keys=frozenset({normalize_alias_key("Andrew Murray")}),
        established=True,
    )

    # ── Mechanism (c): verified-link-but-not-retrieved — THE PRIMARY GOAL ──
    # A.W. Tozer resolves to a real servable source (NOT_RETRIEVED), so the
    # pre-guard verifier PASSED him as a verified clickable link. The guard
    # must now deny it because that source was not retrieved for this question.
    tozer_db = _resolving_servable_db(NOT_RETRIEVED)
    tozer_out = verify_references(_answer("A.W. Tozer"), _mentions("A.W. Tozer"), tozer_db, grounding)
    check(
        "PRIMARY: A.W. Tozer resolves+servable but source NOT retrieved -> "
        "verified link DENIED (the Bevere/Tozer symptom is killed)",
        tozer_out == [],
    )
    # Control: the SAME db + SAME name, but with Tozer's source in the retrieved
    # set, DOES verify — proving resolution/servable pass and grounding is the
    # sole differentiator (the guard is not just failing everything).
    tozer_grounded = RetrievalGrounding(source_ids=frozenset({NOT_RETRIEVED}), established=True)
    tozer_ok = verify_references(_answer("A.W. Tozer"), _mentions("A.W. Tozer"), tozer_db, tozer_grounded)
    check(
        "CONTROL: same Tozer name+db, but source now IN retrieved set -> "
        "verifies (proves grounding is the only differentiator, not a blanket block)",
        len(tozer_ok) == 1 and tozer_ok[0]["type"] == "teacher" and tozer_ok[0]["source_id"] == NOT_RETRIEVED,
    )

    # ── Finding #2 (planner-reviewer): homonym / author-name collision ──
    # A name resolves via alias to source B (servable) that was NOT retrieved,
    # while a DIFFERENT retrieved source shares the same normalized author name
    # (so the name IS in author_keys). The verified LINK must be DENIED — a link
    # points at B, and B was not retrieved. This is the fail-open the source-id-
    # only link gate closes; the author-name arm would previously have granted it.
    homonym_grounding = RetrievalGrounding(
        source_ids=frozenset({RETRIEVED}),                            # B (NOT_RETRIEVED) is NOT here
        author_keys=frozenset({normalize_alias_key("Chris Green")}),  # a same-name author WAS retrieved
        established=True,
    )
    homonym_db = _resolving_servable_db(NOT_RETRIEVED)  # "Chris Green" -> source B (not retrieved)
    homonym_out = verify_references(_answer("Chris Green"), _mentions("Chris Green"), homonym_db, homonym_grounding)
    check(
        "FINDING#2: name resolves to a servable-but-NOT-retrieved source while a "
        "different retrieved source shares the normalized author name -> verified "
        "LINK DENIED (homonym hole closed; link gate is source-id arm only)",
        homonym_out == [],
    )
    check(
        "FINDING#2 split: that same name is still GROUNDED for DETECTION via the "
        "author-name arm — only the link is denied, not the fabrication classification",
        _is_retrieval_grounded("Chris Green", NOT_RETRIEVED, homonym_grounding) is True,
    )

    # ── Mechanism (b): nested-quote re-attribution (Stedman/Wilson/…) ──
    # Same structural shape as Tozer: the name resolves to a servable source,
    # but that teacher's OWN material was not retrieved (the quote was lifted
    # from a Precept Austin word study). Denied.
    stedman_db = _resolving_servable_db(NOT_RETRIEVED)
    stedman_out = verify_references(_answer("Ray Stedman"), _mentions("Ray Stedman"), stedman_db, grounding)
    check("Nested-quote re-attribution (Ray Stedman, not retrieved) -> DENIED", stedman_out == [])

    # ── Mechanism (a): pure invention (Warren Wiersbe) ──
    # No source_aliases row at all -> denied at resolution (unchanged behavior),
    # and grounding also does not contain him. Confirms the class stays blocked.
    wiersbe_db = _FakeDB(table_responses={"source_aliases": []})
    wiersbe_out = verify_references(_answer("Warren Wiersbe"), _mentions("Warren Wiersbe"), wiersbe_db, grounding)
    check("Pure invention (Warren Wiersbe, no alias row) -> DENIED", wiersbe_out == [])

    # ── Requirement 1 / false-positive avoidance: Andrew Murray ──
    # Retrieved, but has NO alias row (the documented alias-gap Landmine). The
    # grounding predicate must count him as grounded via the AUTHOR-NAME arm,
    # NOT alias resolution — otherwise a legitimately retrieved teacher is
    # false-flagged. (He still gets no *link* because a link needs a resolved
    # source_id, which is the unchanged pre-guard behavior; the point here is
    # that the grounding logic itself does not misclassify him as fabricated.)
    check(
        "REQ1: Andrew Murray (retrieved, no alias) is GROUNDED via author-name "
        "arm, not alias resolution (no false positive)",
        _is_retrieval_grounded("Andrew Murray", None, grounding) is True,
    )

    # ── Positive: a legitimately retrieved teacher still verifies ──
    prince_db = _resolving_servable_db(RETRIEVED)
    prince_out = verify_references(_answer("Derek Prince"), _mentions("Derek Prince"), prince_db, grounding)
    check(
        "Legitimate retrieved teacher (Derek Prince, source in retrieved set) -> VERIFIED",
        len(prince_out) == 1 and prince_out[0]["source_id"] == RETRIEVED,
    )

    # ── Requirement 3: FAIL CLOSED ──
    # If the grounding set could not be established, even a fully-resolvable,
    # servable, would-be-grounded teacher is denied.
    failclosed = RetrievalGrounding(established=False)
    fc_out = verify_references(_answer("Derek Prince"), _mentions("Derek Prince"),
                              _resolving_servable_db(RETRIEVED), failclosed)
    check("REQ3: grounding.established=False -> ALL teacher links denied (fail closed)", fc_out == [])

    # build_retrieval_grounding itself fails closed when the documents lookup raises.
    raising_db = _FakeDB(table_responses={}, raising_tables={"documents"})
    g_failclosed = build_retrieval_grounding(
        [{"author": "Derek Prince", "document_id": "doc-1"}], raising_db
    )
    check(
        "REQ3: build_retrieval_grounding returns established=False when the "
        "documents lookup raises (fail closed at construction)",
        g_failclosed.established is False,
    )

    # ── build_retrieval_grounding happy path: author_keys + source_ids ──
    docs_db = _FakeDB(table_responses={
        "documents": [
            {"id": "doc-1", "source_id": "src-prince"},
            {"id": "doc-2", "source_id": "src-murray"},
        ],
    })
    g_ok = build_retrieval_grounding([
        {"author": "Derek Prince", "document_id": "doc-1"},
        {"author": "Andrew Murray", "document_id": "doc-2"},
        {"author": None, "document_id": "doc-2"},  # missing author tolerated
    ], docs_db)
    check(
        "build_retrieval_grounding: author_keys normalized + source_ids mapped, established=True",
        g_ok.established is True
        and g_ok.author_keys == frozenset({"derek prince", "andrew murray"})
        and g_ok.source_ids == frozenset({"src-prince", "src-murray"}),
    )

    # ── verify_teacher_mention is structurally un-callable without grounding ──
    # (the Invariant-10-style guarantee: you cannot skip the gate by omission).
    try:
        verify_teacher_mention(_resolving_servable_db(RETRIEVED), "Derek Prince")  # type: ignore
        structurally_required = False
    except TypeError:
        structurally_required = True
    check(
        "STRUCTURAL: verify_teacher_mention() with no grounding arg raises "
        "TypeError (gate cannot be skipped by omission)",
        structurally_required,
    )

    print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
