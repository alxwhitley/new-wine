"""Shared pytest fixtures for the scripts/ test suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_magazine_review_ocr_page_cache(tmp_path, monkeypatch):
    """Redirect the OCR page cache to an isolated tmp path for every test.

    Without this, review_issue_ocr() (magazine_review/ocr.py) reads and
    writes a real, persistent, gitignored file under local/ -- including
    from fixture-driven fake-provider tests. That would pollute real local
    state with test data, and a stale cache hit from a prior test run could
    silently skip a call a test expects to happen.
    """
    try:
        from magazine_review import ocr as _ocr_module
    except ImportError:
        return
    monkeypatch.setattr(
        _ocr_module, "_PAGE_CACHE_PATH", tmp_path / "ocr_page_cache_test.json"
    )
