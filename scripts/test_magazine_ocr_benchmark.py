#!/usr/bin/env python3
"""Credential-free behavior checks for the blind OCR benchmark harness."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from magazine_review.benchmark import (
    BenchmarkCandidate,
    BenchmarkInputError,
    OCRResponse,
    run_benchmark,
)
from benchmark_magazine_ocr import main


REQUIRED_SCORING_FIELDS = {
    "omissions": [],
    "substitutions": [],
    "reading_order_errors": [],
    "tables_columns": [],
}


class FakeProvider:
    def __init__(self, provider: str, model: str, *, cost_usd: float = 0.01):
        self.candidate = BenchmarkCandidate(provider=provider, model=model)
        self.calls: list[object] = []
        self.cost_usd = cost_usd

    def transcribe(self, fixture):
        self.calls.append(fixture)
        return OCRResponse(
            text=f"transcript for page {fixture.page_number}",
            usage={"input_tokens": 12, "output_tokens": 34},
            cost_usd=self.cost_usd,
        )


def write_manifest(tmp_path: Path, *, expected_hash: str | None = None) -> Path:
    pdf_path = tmp_path / "issue.pdf"
    pdf_path.write_bytes(b"fixed benchmark page")
    manifest_path = tmp_path / "fixtures.json"
    manifest_path.write_text(
        json.dumps(
            {
                "fixtures": [
                    {
                        "pdf_path": pdf_path.name,
                        "pdf_sha256": expected_hash
                        or hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "page_number": 2,
                        "fixture_class": "severe_failure",
                        "human_scoring": REQUIRED_SCORING_FIELDS,
                    },
                    {
                        "pdf_path": pdf_path.name,
                        "pdf_sha256": expected_hash
                        or hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "page_number": 7,
                        "fixture_class": "good_control",
                        "human_scoring": REQUIRED_SCORING_FIELDS,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_fixture_hash_mismatch_stops_before_provider_call(tmp_path):
    """Changing a PDF after fixture selection must prevent every OCR call."""
    manifest_path = write_manifest(tmp_path, expected_hash="0" * 64)
    provider = FakeProvider("Gemini", "gemini-2.5-flash")

    with pytest.raises(BenchmarkInputError, match="pdf_sha256"):
        run_benchmark(manifest_path, [provider] * 3, tmp_path / "report.json")

    assert provider.calls == []


def test_blind_report_hides_provider_names(tmp_path):
    """A scorer sees anonymous candidates, not models or provider brands."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("Gemini", "gemini-2.5-flash"),
        FakeProvider("Enterprise Document AI", "processor-123"),
        FakeProvider("Gemini", "gemini-3.6-flash"),
    ]

    report = run_benchmark(manifest_path, providers, tmp_path / "report.json")
    encoded = json.dumps(report.blind_view())

    assert "gemini" not in encoded.lower()
    assert "document ai" not in encoded.lower()
    assert set(report.blind_view()["candidates"]) == {"A", "B", "C"}
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8")) == report.blind_view()


def test_reconciles_every_candidate_fixture_pair_and_captures_cost(tmp_path):
    """Missing a provider/page pair or usage/cost data makes the evidence incomplete."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1", cost_usd=0.01),
        FakeProvider("two", "model-2", cost_usd=0.02),
        FakeProvider("three", "model-3", cost_usd=0.03),
    ]

    report = run_benchmark(manifest_path, providers, tmp_path / "report.json")

    assert report.candidate_count * report.fixture_count == report.result_count == 6
    assert all(result.usage for result in report.results)
    assert all(result.cost_usd is not None for result in report.results)
    assert report.blind_view()["total_cost_usd"] == pytest.approx(0.12)


def test_cli_dry_run_verifies_fixture_identity_without_provider_calls(tmp_path):
    """Dry run is safe for the attended checkpoint because it cannot invoke OCR."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1"),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]
    output_path = tmp_path / "dry-run.json"

    exit_code = main(
        ["--manifest", str(manifest_path), "--output", str(output_path), "--dry-run"],
        providers=providers,
    )

    assert exit_code == 0
    assert all(provider.calls == [] for provider in providers)
    dry_run = json.loads(output_path.read_text(encoding="utf-8"))
    assert dry_run["dry_run"] is True
    assert dry_run["fixture_count"] == 2
    assert dry_run["result_count"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
