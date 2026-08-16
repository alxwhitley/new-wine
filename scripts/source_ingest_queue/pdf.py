"""Child-process PDF extraction with hard time and resource bounds."""

from __future__ import annotations

import contextlib
import multiprocessing
import os
from dataclasses import dataclass
from io import BytesIO
from typing import Callable


_HARD_MAX_PAGES = 2_000
_HARD_MAX_CHARS = 10_000_000


def _bounded_detail(detail: str) -> str:
    return " ".join(str(detail).split())[:240]


@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    page_count: int


class PdfRejected(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = _bounded_detail(detail)
        super().__init__("%s: %s" % (code, self.detail))


class _ChildFailure(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _extract_in_child(content: bytes, output) -> None:
    try:
        with open(os.devnull, "w") as sink, contextlib.redirect_stdout(
            sink
        ), contextlib.redirect_stderr(sink):
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            page_count = len(reader.pages)
            if page_count > _HARD_MAX_PAGES:
                output.send(("error", "pdf_page_limit", 0))
                return

            parts = []
            char_count = 0
            for page in reader.pages:
                page_text = page.extract_text()
                if not page_text:
                    continue
                parts.append(page_text)
                char_count += len(page_text) + 1
                if char_count <= _HARD_MAX_CHARS:
                    continue
                output.send(("error", "pdf_text_limit", 0))
                return

            text = "\n".join(parts).strip()
            output.send(("ok", text, page_count))
    except BaseException:
        try:
            output.send(("error", "pdf_parse_failure", 0))
        except BaseException:
            pass
    finally:
        output.close()


def _run_extractor_child(content: bytes, timeout_seconds: float):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_extract_in_child, args=(content, send))
    process.daemon = True
    process.start()
    send.close()
    try:
        if not receive.poll(timeout_seconds):
            process.terminate()
            process.join()
            raise TimeoutError("PDF extraction exceeded its deadline")
        try:
            payload = receive.recv()
        except EOFError as exc:
            raise _ChildFailure("pdf_parse_failure") from exc
    finally:
        receive.close()
        if process.is_alive():
            process.terminate()
        process.join()

    if (
        not isinstance(payload, tuple)
        or len(payload) != 3
        or payload[0] not in ("ok", "error")
    ):
        raise _ChildFailure("pdf_parse_failure")
    if payload[0] == "error":
        code = payload[1]
        if code not in ("pdf_page_limit", "pdf_text_limit", "pdf_parse_failure"):
            code = "pdf_parse_failure"
        raise _ChildFailure(code)
    return payload[1], payload[2]


def extract_pdf_bounded(
    content: bytes,
    *,
    timeout_seconds: float = 60.0,
    max_pages: int = 2_000,
    max_chars: int = 10_000_000,
    runner: Callable = _run_extractor_child,
) -> ExtractedPdf:
    """Extract text without allowing parser faults or stalls into the worker."""
    if timeout_seconds <= 0 or max_pages <= 0 or max_chars <= 0:
        raise ValueError("PDF extraction limits must be positive")
    try:
        text, page_count = runner(content, timeout_seconds)
    except TimeoutError as exc:
        raise PdfRejected(
            "pdf_extract_timeout", "PDF extraction timed out"
        ) from exc
    except _ChildFailure as exc:
        raise PdfRejected(exc.code, "PDF extraction was rejected") from exc
    except Exception as exc:
        raise PdfRejected("pdf_parse_failure", "PDF parsing failed") from exc

    if not isinstance(text, str) or isinstance(page_count, bool) or not isinstance(
        page_count, int
    ):
        raise PdfRejected("pdf_parse_failure", "PDF parser returned invalid data")
    if page_count < 0:
        raise PdfRejected("pdf_parse_failure", "PDF parser returned invalid data")
    if page_count > max_pages:
        raise PdfRejected("pdf_page_limit", "PDF exceeds page limit")
    if len(text) > max_chars:
        raise PdfRejected("pdf_text_limit", "PDF exceeds text limit")
    if not text.strip():
        raise PdfRejected("pdf_empty", "PDF contains no extractable text")
    return ExtractedPdf(text=text, page_count=page_count)
