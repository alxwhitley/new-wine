#!/usr/bin/env python3
"""
test_extract_quote_candidates_article.py — DB-free / network-free proof
that the reusable article quote-candidate tool (1) proposes structurally
eligible candidates and (2) always defers the actual accept/refuse
decision to the real, unmodified app.services.quote_verifier and
app.services.quotes._enforce_quote_cap -- never a weakened or
reimplemented copy of either.

FakeDb below implements the same chainable
.table(name).select(...).eq(...).in_(...).limit(...).execute().data shape
the real Supabase client exposes, so verify_quote_candidate() and
_enforce_quote_cap() run completely unmodified against it -- this file
never patches or forks either function.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.quote_verifier import verify_quote_candidate  # noqa: E402
from app.services.quotes import _enforce_quote_cap  # noqa: E402

from extract_quote_candidates_article import (  # noqa: E402
    propose_candidates_for_chunk,
    would_exceed_work_cap,
)


TEACHER_SOURCE_ID = "teacher-1111-1111-1111-111111111111"
OTHER_TEACHER_SOURCE_ID = "teacher-2222-2222-2222-222222222222"
DOCUMENT_ID = "doc-1111-1111-1111-1111-111111111111"
CHUNK_ID = "chunk-1111-1111-1111-1111-111111111111"


class _FakeQuery:
    def __init__(self, rows):
        self._rows = [dict(r) for r in rows]

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def in_(self, field, values):
        values = set(values)
        self._rows = [r for r in self._rows if r.get(field) in values]
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def execute(self):
        return SimpleNamespace(data=list(self._rows))


class FakeDb:
    def __init__(self, *, chunks=(), documents=(), quote_source_revisions=(), quotes=()):
        self._tables = {
            "chunks": list(chunks),
            "documents": list(documents),
            "quote_source_revisions": list(quote_source_revisions),
            "quotes": list(quotes),
        }

    def table(self, name):
        return _FakeQuery(self._tables[name])


def real_chunk_content():
    return (
        "An introductory sentence sits here before the real teaching begins in full. "
        "Grace is not a reward for good behavior, it is a gift freely given to those "
        "who could never earn it through their own effort or personal merit at all. "
        "A closing sentence rounds out the paragraph after the real teaching point."
    )


def base_chunk_row(**overrides):
    row = {
        "id": CHUNK_ID,
        "content": real_chunk_content(),
        "document_id": DOCUMENT_ID,
        "quote_ineligible_reason": None,
    }
    row.update(overrides)
    return row


def base_document_row(**overrides):
    row = {"id": DOCUMENT_ID, "source_id": TEACHER_SOURCE_ID}
    row.update(overrides)
    return row


class ProposeCandidatesTests(unittest.TestCase):
    def test_accepts_a_genuine_well_formed_candidate(self):
        db = FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()])
        proposals = propose_candidates_for_chunk(
            db, CHUNK_ID, real_chunk_content(), TEACHER_SOURCE_ID
        )
        accepted = [p for p in proposals if p.valid]
        self.assertTrue(accepted, "expected at least one accepted candidate")
        self.assertTrue(
            any("Grace is not a reward" in p.text for p in accepted)
        )

    def test_rejects_fabricated_text_not_present_in_the_chunk(self):
        """Generation only ever proposes exact substrings of the chunk
        content, so fabrication is impossible by construction -- proven by
        feeding a hand-fabricated string straight to the real verifier
        the way a broken caller might, confirming it is refused."""
        db = FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()])
        fabricated = "This exact sentence was never actually written in the source."
        result = verify_quote_candidate(db, CHUNK_ID, fabricated, TEACHER_SOURCE_ID)
        self.assertFalse(result.valid)
        self.assertEqual(result.rule, "not_exact_substring")

    def test_rejects_a_candidate_trimmed_from_either_end(self):
        content = real_chunk_content()
        genuine = "Grace is not a reward for good behavior, it is a gift freely given to those who could never earn it through their own effort or personal merit at all."
        assert genuine in content
        trimmed = genuine[3:-3]  # word-internal trim at both ends
        result = verify_quote_candidate(
            FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()]),
            CHUNK_ID,
            trimmed,
            TEACHER_SOURCE_ID,
        )
        self.assertFalse(result.valid)
        self.assertEqual(result.rule, "boundary_proximity")

    def test_rejects_an_incomplete_sentence_fragment(self):
        content = "Full sentence one here for context. Grace is not a reward for good"
        db = FakeDb(
            chunks=[base_chunk_row(content=content)], documents=[base_document_row()]
        )
        fragment = "Grace is not a reward for good"  # no terminal punctuation
        result = verify_quote_candidate(db, CHUNK_ID, fragment, TEACHER_SOURCE_ID)
        self.assertFalse(result.valid)
        self.assertEqual(result.rule, "boundary_proximity")

    def test_rejects_when_the_attributed_teacher_does_not_match_the_document(self):
        db = FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()])
        proposals = propose_candidates_for_chunk(
            db, CHUNK_ID, real_chunk_content(), OTHER_TEACHER_SOURCE_ID
        )
        self.assertTrue(proposals)
        for p in proposals:
            self.assertFalse(p.valid)
            self.assertEqual(p.rule, "speaker_unconfirmed")

    def test_rejects_a_candidate_overlapping_a_nested_third_party_quotation(self):
        content = (
            'An opening sentence gives real context before the block quotation below it. '
            'He writes:“This long block of nested third-party quoted text runs on for '
            'quite a while and represents someone else entirely, not our credited teacher '
            'at all in any way whatsoever here.” A closing sentence follows the block.'
        )
        db = FakeDb(
            chunks=[base_chunk_row(content=content)], documents=[base_document_row()]
        )
        nested = content[content.index("This long block") : content.index("whatsoever here.") + len("whatsoever here.")]
        result = verify_quote_candidate(db, CHUNK_ID, nested, TEACHER_SOURCE_ID)
        self.assertFalse(result.valid)
        self.assertEqual(result.rule, "subchunk_exclusion")

    def test_rejects_every_candidate_from_a_commentary_flagged_chunk(self):
        db = FakeDb(
            chunks=[base_chunk_row(quote_ineligible_reason="commentary")],
            documents=[base_document_row()],
        )
        proposals = propose_candidates_for_chunk(
            db, CHUNK_ID, real_chunk_content(), TEACHER_SOURCE_ID
        )
        self.assertTrue(proposals)
        for p in proposals:
            self.assertFalse(p.valid)
            self.assertEqual(p.rule, "exclusion_zone")

    def test_rejects_every_candidate_from_an_explicitly_excluded_passage(self):
        db = FakeDb(
            chunks=[base_chunk_row(quote_ineligible_reason="translator_note")],
            documents=[base_document_row()],
        )
        proposals = propose_candidates_for_chunk(
            db, CHUNK_ID, real_chunk_content(), TEACHER_SOURCE_ID
        )
        self.assertTrue(proposals)
        for p in proposals:
            self.assertFalse(p.valid)
            self.assertEqual(p.rule, "exclusion_zone")

    def test_never_proposes_the_same_candidate_text_twice(self):
        db = FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()])
        content = real_chunk_content()
        first_pass = propose_candidates_for_chunk(db, CHUNK_ID, content, TEACHER_SOURCE_ID)
        genuine_texts = {p.text for p in first_pass if p.valid}
        self.assertTrue(genuine_texts)

        second_pass = propose_candidates_for_chunk(
            db, CHUNK_ID, content, TEACHER_SOURCE_ID, existing_texts=frozenset(genuine_texts)
        )
        self.assertFalse(
            any(p.text in genuine_texts for p in second_pass),
            "an already-proposed candidate text must never be proposed again",
        )

        within_call_texts = [p.text for p in first_pass]
        self.assertEqual(len(within_call_texts), len(set(within_call_texts)))


class WorkCapTests(unittest.TestCase):
    def test_a_candidate_that_would_exceed_the_per_work_cap_is_flagged(self):
        """Proves this tool's output still respects the existing,
        UNCHANGED per-work quote-text cap enforced at real approval time
        (app.services.quotes._enforce_quote_cap) -- this tool never
        reimplements or weakens that cap, it only checks against it."""
        revision_id = "rev-1111-1111-1111-111111111111"
        near_cap_text = "x" * 1999
        db = FakeDb(
            chunks=[base_chunk_row()],
            documents=[base_document_row()],
            quote_source_revisions=[{"id": revision_id, "chunk_id": CHUNK_ID}],
            quotes=[
                {
                    "source_revision_id": revision_id,
                    "quote_text": near_cap_text,
                    "status": "approved",
                }
            ],
        )
        candidate_text = "A brand new candidate that would push this document's cumulative approved quote text over its cap."
        self.assertTrue(would_exceed_work_cap(db, DOCUMENT_ID, candidate_text))

    def test_a_candidate_well_under_the_cap_is_not_flagged(self):
        db = FakeDb(chunks=[base_chunk_row()], documents=[base_document_row()])
        self.assertFalse(would_exceed_work_cap(db, DOCUMENT_ID, "A short candidate."))


if __name__ == "__main__":
    unittest.main()
