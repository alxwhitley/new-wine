#!/usr/bin/env python3
"""
test_quote_candidates.py — DB-free tests for the reusable, deterministic
quote-candidate GENERATION layer (scripts/quote_candidates.py): sentence
splitting, sentence-window candidate spans, and the conservative
structural eligibility filter shared by any teacher/source, not just
Derek Prince's own corpus-tuned extraction script.

Generation is deliberately kept separate from verification here: nothing
in this file imports app.services.quote_verifier. See
test_extract_quote_candidates_article.py for the tool that composes this
generation layer with the real, unweakened quote_verifier.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from quote_candidates import generate_candidate_spans, split_sentences


class SplitSentencesTests(unittest.TestCase):
    def test_splits_on_terminal_punctuation_and_spans_are_exact_substrings(self):
        text = "First sentence here. Second one follows! Is this a third?"
        spans = split_sentences(text)
        self.assertEqual(len(spans), 3)
        for start, end, sentence in spans:
            self.assertEqual(text[start:end], sentence)
        self.assertEqual(spans[0][2], "First sentence here.")
        self.assertEqual(spans[1][2], "Second one follows!")
        self.assertEqual(spans[2][2], "Is this a third?")

    def test_keeps_closing_quote_attached_to_its_sentence(self):
        text = 'He said, "Grace changes everything." Then he sat down.'
        spans = split_sentences(text)
        self.assertEqual(spans[0][2], 'He said, "Grace changes everything."')


class GenerateCandidateSpansTests(unittest.TestCase):
    def test_accepts_a_well_formed_one_to_three_sentence_candidate(self):
        content = (
            "Some introductory sentence sits before the real content begins here. "
            "Grace is not a reward for good behavior, it is a gift freely given "
            "to those who could never earn it on their own merit at all. "
            "A closing sentence follows after it to round out this fixture."
        )
        spans = generate_candidate_spans(content)
        texts = [text for _start, _end, text in spans]
        self.assertTrue(
            any("Grace is not a reward for good behavior" in t for t in texts)
        )

    def test_skips_candidates_flush_against_either_chunk_edge(self):
        content = "First sentence starts right at position zero. Middle one. Last sentence ends the chunk."
        spans = generate_candidate_spans(content)
        for start, end, _text in spans:
            self.assertNotEqual(start, 0)
            self.assertNotEqual(end, len(content))

    def test_rejects_candidates_outside_the_length_bounds(self):
        content = "Short. " * 40  # each candidate window would be very short
        spans = generate_candidate_spans(content, min_len=120, max_len=500)
        for _start, _end, text in spans:
            self.assertGreaterEqual(len(text), 120)
            self.assertLessEqual(len(text), 500)

    def test_rejects_candidates_starting_with_a_weak_connective_word(self):
        content = (
            "A real opening sentence gives this fixture enough length to pass the floor. "
            "But this sentence should never stand alone as a quote on its own merit. "
            "A closing sentence rounds things out safely past the minimum length required."
        )
        spans = generate_candidate_spans(content)
        for _start, _end, text in spans:
            self.assertFalse(text.strip().lower().startswith("but "))

    def test_rejects_candidates_dominated_by_a_long_direct_quotation(self):
        quoted = "x" * 200
        content = (
            'An opening sentence long enough to matter for this specific fixture. '
            '"%s" A short trailing sentence after the long quotation block ends.'
        ) % quoted
        spans = generate_candidate_spans(content)
        for _start, _end, text in spans:
            self.assertNotIn(quoted, text)

    def test_rejects_candidates_containing_a_blank_line_poetic_block(self):
        content = (
            "An opening sentence long enough to matter for this fixture overall.\n\n"
            "A second block separated by a blank line like verse-per-line text. "
            "A closing sentence long enough to round out the minimum length needed."
        )
        spans = generate_candidate_spans(content)
        for _start, _end, text in spans:
            self.assertNotIn("\n\n", text)


if __name__ == "__main__":
    unittest.main()
