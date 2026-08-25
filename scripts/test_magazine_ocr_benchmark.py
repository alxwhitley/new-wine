#!/usr/bin/env python3
"""Credential-free behavior checks for the blind OCR benchmark harness."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import fitz
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
    def __init__(
        self,
        provider: str,
        model: str,
        *,
        cost_usd: float = 0.01,
        usage_value: float = 12,
    ):
        self.candidate = BenchmarkCandidate(provider=provider, model=model)
        self.calls: list[object] = []
        self.cost_usd = cost_usd
        self.usage_value = usage_value

    def transcribe(self, fixture):
        self.calls.append(fixture)
        return OCRResponse(
            text=f"transcript for page {fixture.page_number}",
            usage={"input_tokens": self.usage_value, "output_tokens": 34},
            cost_usd=self.cost_usd,
        )


def write_manifest(
    tmp_path: Path,
    *,
    expected_hash: str | None = None,
    fixture_classes: tuple[str, str] = ("severe_failure", "good_control"),
) -> Path:
    pdf_path = tmp_path / "issue.pdf"
    document = fitz.open()
    for page_number in range(1, 8):
        page = document.new_page()
        page.insert_text((72, 72), f"fixed benchmark page {page_number}")
    document.save(pdf_path)
    document.close()
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
                        "fixture_class": fixture_classes[0],
                        "human_scoring": REQUIRED_SCORING_FIELDS,
                    },
                    {
                        "pdf_path": pdf_path.name,
                        "pdf_sha256": expected_hash
                        or hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                        "page_number": 7,
                        "fixture_class": fixture_classes[1],
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


@pytest.mark.parametrize("fixture_class", ["severe_failure", "good_control"])
def test_manifest_requires_both_fixture_classes_before_provider_call(
    tmp_path, fixture_class
):
    """A benchmark without severe and control evidence cannot make an OCR call."""
    manifest_path = write_manifest(
        tmp_path, fixture_classes=(fixture_class, fixture_class)
    )
    provider = FakeProvider("Gemini", "gemini-2.5-flash")

    with pytest.raises(BenchmarkInputError, match="fixture_class_coverage"):
        run_benchmark(manifest_path, [provider] * 3, tmp_path / "report.json")

    assert provider.calls == []


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rejects_nonfinite_provider_usage(tmp_path, value):
    """Non-finite usage cannot become invalid JSON or a false cost record."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1", usage_value=value),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    with pytest.raises(BenchmarkInputError, match="provider_usage_invalid"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_rejects_nonfinite_provider_cost(tmp_path, value):
    """Non-finite provider cost cannot be emitted in a benchmark report."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1", cost_usd=value),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    with pytest.raises(BenchmarkInputError, match="provider_cost_invalid"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")


def test_rejects_finite_costs_that_overflow_report_aggregation(tmp_path):
    """Finite provider costs must not become an infinite aggregate in JSON output."""
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1", cost_usd=1e308),
        FakeProvider("two", "model-2", cost_usd=1e308),
        FakeProvider("three", "model-3", cost_usd=1e308),
    ]

    with pytest.raises(BenchmarkInputError, match="aggregate_cost_invalid"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")


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


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_manifest_rejects_nonfinite_nested_scoring_before_provider_call(
    tmp_path, constant
):
    manifest_path = write_manifest(tmp_path)
    raw = manifest_path.read_text(encoding="utf-8").replace(
        '"omissions": []', f'"omissions": [{constant}]', 1
    )
    manifest_path.write_text(raw, encoding="utf-8")
    providers = [
        FakeProvider("one", "model-1"),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    with pytest.raises(BenchmarkInputError, match="manifest_invalid_json"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")

    assert all(provider.calls == [] for provider in providers)


def test_manifest_rejects_unknown_nested_scoring_field_before_provider_call(tmp_path):
    manifest_path = write_manifest(tmp_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["fixtures"][0]["human_scoring"]["unreviewed_extra"] = []
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    providers = [
        FakeProvider("one", "model-1"),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    with pytest.raises(BenchmarkInputError, match="human_scoring_fields_invalid"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")

    assert all(provider.calls == [] for provider in providers)


def test_manifest_rejects_out_of_bounds_pdf_page_before_provider_call(tmp_path):
    manifest_path = write_manifest(tmp_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["fixtures"][1]["page_number"] = 8
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    providers = [
        FakeProvider("one", "model-1"),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    with pytest.raises(BenchmarkInputError, match="page_number_out_of_bounds"):
        run_benchmark(manifest_path, providers, tmp_path / "report.json")

    assert all(provider.calls == [] for provider in providers)


def test_cli_loads_configured_provider_factory_without_network(tmp_path):
    manifest_path = write_manifest(tmp_path)
    providers = [
        FakeProvider("one", "model-1"),
        FakeProvider("two", "model-2"),
        FakeProvider("three", "model-3"),
    ]

    exit_code = main(
        ["--manifest", str(manifest_path), "--output", str(tmp_path / "report.json")],
        provider_factory=lambda _manifest: providers,
        environ={},
    )

    assert exit_code == 0
    assert all(len(provider.calls) == 2 for provider in providers)


def test_shell_main_dry_run_uses_environment_factory_and_makes_zero_calls(tmp_path):
    manifest_path = write_manifest(tmp_path)
    factory_module = tmp_path / "offline_benchmark_factory.py"
    factory_module.write_text(
        "from magazine_review.benchmark import BenchmarkCandidate, OCRResponse\n"
        "class Provider:\n"
        "    def __init__(self, name):\n"
        "        self.candidate = BenchmarkCandidate(name, name + '-model')\n"
        "    def transcribe(self, fixture):\n"
        "        raise AssertionError('dry run called provider')\n"
        "def build(manifest):\n"
        "    return [Provider('one'), Provider('two'), Provider('three')]\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "shell-dry-run.json"
    environment = dict(os.environ)
    environment["MAGAZINE_OCR_BENCHMARK_PROVIDER_FACTORY"] = (
        "offline_benchmark_factory:build"
    )
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(tmp_path), str(Path(__file__).resolve().parent)]
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "benchmark_magazine_ocr.py"),
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--dry-run",
        ],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8"))["dry_run"] is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
