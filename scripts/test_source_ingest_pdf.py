#!/usr/bin/env python3
"""Behavior checks for isolated, bounded queued-PDF extraction."""

import contextlib
import io
import unittest

from source_ingest_queue.pdf import (
    ExtractedPdf,
    PdfRejected,
    _extract_in_child,
    extract_pdf_bounded,
)


class ExtractPdfBoundedTests(unittest.TestCase):
    def test_returns_extracted_text_and_page_count(self):
        result = extract_pdf_bounded(
            b"pdf",
            timeout_seconds=1.0,
            runner=lambda content, deadline: ("Body text", 12),
        )

        self.assertIsInstance(result, ExtractedPdf)
        self.assertEqual(result.text, "Body text")
        self.assertEqual(result.page_count, 12)

    def test_rejects_empty_page_and_text_limit_outcomes(self):
        cases = (
            (
                "pdf_empty",
                lambda content, deadline: (" \n\t", 1),
                {},
            ),
            (
                "pdf_page_limit",
                lambda content, deadline: ("Body", 2_001),
                {"max_pages": 2_000},
            ),
            (
                "pdf_text_limit",
                lambda content, deadline: ("x" * 10_000_001, 1),
                {"max_chars": 10_000_000},
            ),
        )

        for code, runner, limits in cases:
            with self.subTest(code=code):
                with self.assertRaises(PdfRejected) as raised:
                    extract_pdf_bounded(b"pdf", runner=runner, **limits)
                self.assertEqual(raised.exception.code, code)

    def test_maps_timeout_and_parser_fault_without_raw_details(self):
        def timeout_runner(content, deadline):
            raise TimeoutError("private timeout detail")

        def parser_runner(content, deadline):
            raise ValueError("private parser detail")

        for code, runner in (
            ("pdf_extract_timeout", timeout_runner),
            ("pdf_parse_failure", parser_runner),
        ):
            with self.subTest(code=code):
                with self.assertRaises(PdfRejected) as raised:
                    extract_pdf_bounded(b"pdf", runner=runner)
                self.assertEqual(raised.exception.code, code)
                self.assertNotIn("private", raised.exception.detail)

    def test_rejects_malformed_child_payload(self):
        with self.assertRaises(PdfRejected) as raised:
            extract_pdf_bounded(
                b"pdf", runner=lambda content, deadline: ("Body", "one")
            )

        self.assertEqual(raised.exception.code, "pdf_parse_failure")

    def test_default_runner_contains_invalid_pdf_failure(self):
        with self.assertRaises(PdfRejected) as raised:
            extract_pdf_bounded(b"not a PDF", timeout_seconds=5.0)

        self.assertEqual(raised.exception.code, "pdf_parse_failure")
        self.assertNotIn("EOF", raised.exception.detail)

    def test_child_suppresses_raw_parser_output(self):
        class Output:
            def __init__(self):
                self.payloads = []

            def send(self, payload):
                self.payloads.append(payload)

            def close(self):
                pass

        output = Output()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            _extract_in_child(b"not a PDF", output)

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(output.payloads, [("error", "pdf_parse_failure", 0)])


if __name__ == "__main__":
    unittest.main()
