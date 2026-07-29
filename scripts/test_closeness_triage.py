#!/usr/bin/env python3
"""Unit proof for the retroactive closeness-triage review materials."""

import json
import tempfile
import unittest
from pathlib import Path

import closeness_check as cc
import closeness_triage as triage


class ClosenessTriageTests(unittest.TestCase):
    def test_balanced_batches_stay_between_fifteen_and_twenty(self):
        items = list(range(139))

        batches = triage.balanced_batches(items)

        self.assertEqual(7, len(batches))
        self.assertEqual(139, sum(len(batch) for batch in batches))
        self.assertTrue(all(15 <= len(batch) <= 20 for batch in batches))

    def test_highlight_run_marks_the_exact_words_in_both_texts(self):
        passage = "The teacher says quiet daily habits drain their strength little by little."
        source = "Before this, he warns that daily habits drain their strength little by little until nothing remains."
        run = ("daily", "habits", "drain", "their", "strength", "little", "by", "little")

        highlighted_passage = triage.highlight_token_run(passage, run)
        highlighted_source = triage.highlight_token_run(source, run)

        self.assertIn("**daily habits drain their strength little by little**", highlighted_passage)
        self.assertIn("**daily habits drain their strength little by little**", highlighted_source)

    def test_context_excerpt_keeps_highlight_and_marks_omissions(self):
        source = (
            "Opening sentence gives earlier context. "
            "The copied words sit together in the middle of this source passage. "
            "Closing sentence gives later context."
        )
        run = ("copied", "words", "sit", "together")

        excerpt = triage.context_excerpt(source, run, radius=25)

        self.assertIn("**copied words sit together**", excerpt)
        self.assertTrue(excerpt.startswith("…"))
        self.assertTrue(excerpt.endswith("…"))

    def test_initialize_ledger_preserves_decisions_across_regeneration(self):
        records = [
            {"proposition_id": "fast-1", "queue": "fast"},
            {"proposition_id": "real-1", "queue": "real_attention"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "decisions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "items": {
                            "fast-1": {
                                "queue": "fast",
                                "decision": "clear",
                                "reviewed_at": "2026-07-29T12:00:00Z",
                                "reviewer_note": "Looks fine.",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            ledger = triage.initialize_ledger(path, records)

            self.assertEqual("clear", ledger["items"]["fast-1"]["decision"])
            self.assertEqual("Looks fine.", ledger["items"]["fast-1"]["reviewer_note"])
            self.assertIsNone(ledger["items"]["real-1"]["decision"])
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(ledger, on_disk)

    def test_decision_options_are_closed_per_queue(self):
        with self.assertRaises(ValueError):
            triage.validate_decision("fast", "keep_as_is")
        with self.assertRaises(ValueError):
            triage.validate_decision("real_attention", "clear")

        self.assertEqual("clear", triage.validate_decision("fast", "clear"))
        self.assertEqual(
            "needs shortening or rewording",
            triage.validate_decision("real_attention", "needs shortening or rewording"),
        )

    def test_theology_masking_possessive_breaks_masked_run_raw_run_fixes_it(self):
        # Reproduces the real renderer bug: closeness_check.py's
        # _mask_theology() does `_THEOLOGY_RE.sub(...)` where
        # _THEOLOGY_RE = re.compile(r"\b(?:...THEOLOGY_TERMS...)\b", re.IGNORECASE).
        # \b matches between a word char and an apostrophe, so "Bible" inside
        # "Bible's" gets substituted on its own, leaving a dangling "'s" that
        # tokenize()'s word regex ([a-z0-9]+(?:'[a-z]+)?) then retokenizes as
        # a standalone one-letter token "s" -- a token that never exists as a
        # literal token in the real, unmasked text (there "Bible's" tokenizes
        # as ONE token, "bible's"). Passage and source share a contiguous run
        # of real wording built around a "Bible's" possessive, shaped like the
        # real bug.
        passage = (
            "Understanding the Bible's story and theme is essential for "
            "every teacher today."
        )
        source = (
            "Preachers often forget that Bible's story and theme is "
            "essential for every teacher who wants depth."
        )

        # (a) Document the bug: classify()'s own masked run (the same
        # run-finding path used for the classifier-integrity check in
        # generate()) genuinely does not exist as a literal contiguous run in
        # the real, unmasked text -- this proves the scenario actually
        # exercises the bug, not one that happens to work fine.
        run_length, run_tokens = cc.longest_common_run(passage, source, None)
        self.assertEqual(9, run_length)
        self.assertEqual("s", run_tokens[0])
        with self.assertRaises(ValueError):
            triage.highlight_token_run(passage, run_tokens)

        # (b) Prove the fix: the new raw-run rendering path
        # (compute_real_highlight_run, built on the existing
        # raw_longest_run over RAW unmasked text) locates a real contiguous
        # run containing the possessive and renders a highlight in both the
        # passage and the source context, without raising.
        raw_run = triage.compute_real_highlight_run(passage, source)
        highlighted_passage = triage.highlight_token_run(passage, raw_run)
        highlighted_context = triage.context_excerpt(source, raw_run, radius=650)

        self.assertIn(
            "**Bible's story and theme is essential for every teacher**",
            highlighted_passage,
        )
        self.assertIn(
            "**Bible's story and theme is essential for every teacher**",
            highlighted_context,
        )


if __name__ == "__main__":
    unittest.main()
