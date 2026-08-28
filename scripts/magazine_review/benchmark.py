"""Credential-free, blind evidence capture for selecting an OCR provider."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pymupdf as fitz


FIXTURE_CLASSES = frozenset({"severe_failure", "good_control"})
REQUIRED_SCORING_FIELDS = frozenset(
    {"omissions", "substitutions", "reading_order_errors", "tables_columns"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BenchmarkInputError(ValueError):
    """Raised when immutable benchmark evidence is missing or inconsistent."""


def _reject_nonfinite_json_constant(_value: str) -> None:
    raise ValueError("nonfinite_json_constant")


@dataclass(frozen=True)
class BenchmarkCandidate:
    """The private identity of an OCR candidate (never emitted in blind output)."""

    provider: str
    model: str


@dataclass(frozen=True)
class BenchmarkFixture:
    """One page selected for human-scored comparison."""

    pdf_path: Path
    pdf_sha256: str
    page_number: int
    fixture_class: str
    human_scoring: Mapping[str, Any]


@dataclass(frozen=True)
class OCRResponse:
    """A provider's transcription plus the usage and cost it reported."""

    text: str
    usage: Mapping[str, float | int]
    cost_usd: float


class OCRProvider(Protocol):
    """The injectable boundary around paid OCR providers."""

    candidate: BenchmarkCandidate

    def transcribe(self, fixture: BenchmarkFixture) -> OCRResponse:
        """Return the transcription and measured provider accounting for one page."""


class CallbackOCRProvider:
    """Adapter base for a provider-specific callback supplied by the caller."""

    def __init__(
        self,
        candidate: BenchmarkCandidate,
        transcriber: Callable[[BenchmarkFixture], OCRResponse],
    ) -> None:
        self.candidate = candidate
        self._transcriber = transcriber

    def transcribe(self, fixture: BenchmarkFixture) -> OCRResponse:
        return self._transcriber(fixture)


class GeminiOCRProvider(CallbackOCRProvider):
    """Injectable adapter for either candidate Gemini OCR model."""

    ALLOWED_MODELS = frozenset({"gemini-2.5-flash", "gemini-3.6-flash"})

    def __init__(
        self,
        model: str,
        transcriber: Callable[[BenchmarkFixture], OCRResponse],
    ) -> None:
        if model not in self.ALLOWED_MODELS:
            raise BenchmarkInputError("unsupported_gemini_model")
        super().__init__(BenchmarkCandidate(provider="Gemini", model=model), transcriber)


class EnterpriseDocumentOCRProvider(CallbackOCRProvider):
    """Injectable adapter for a caller-selected Enterprise Document OCR processor."""

    def __init__(
        self,
        processor_id: str,
        transcriber: Callable[[BenchmarkFixture], OCRResponse],
    ) -> None:
        if not isinstance(processor_id, str) or not processor_id.strip():
            raise BenchmarkInputError("document_ocr_processor_id_required")
        super().__init__(
            BenchmarkCandidate(
                provider="Enterprise Document OCR", model=processor_id.strip()
            ),
            transcriber,
        )


@dataclass(frozen=True)
class BenchmarkPageResult:
    """The private candidate/result pair retained until a human scores blind output."""

    candidate: BenchmarkCandidate
    fixture: BenchmarkFixture
    text: str
    usage: Mapping[str, float | int]
    cost_usd: float

    def blind_view(self, label: str) -> dict[str, Any]:
        return {
            "candidate": label,
            "pdf_sha256": self.fixture.pdf_sha256,
            "page_number": self.fixture.page_number,
            "fixture_class": self.fixture.fixture_class,
            "human_scoring": dict(self.fixture.human_scoring),
            "text": self.text,
            "usage": dict(self.usage),
            "cost_usd": self.cost_usd,
        }


@dataclass(frozen=True)
class BenchmarkReport:
    """A reconciled set of benchmark results with a serializable blind view."""

    fixtures: tuple[BenchmarkFixture, ...]
    candidates: tuple[BenchmarkCandidate, ...]
    results: tuple[BenchmarkPageResult, ...]
    dry_run: bool = False

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def fixture_count(self) -> int:
        return len(self.fixtures)

    @property
    def result_count(self) -> int:
        return len(self.results)

    @classmethod
    def from_results(
        cls,
        fixtures: Sequence[BenchmarkFixture],
        candidates: Sequence[BenchmarkCandidate],
        results: Sequence[BenchmarkPageResult],
    ) -> "BenchmarkReport":
        report = cls(tuple(fixtures), tuple(candidates), tuple(results))
        report._validate_reconciliation()
        return report

    def _validate_reconciliation(self) -> None:
        expected_count = self.candidate_count * self.fixture_count
        if self.dry_run:
            if self.results:
                raise BenchmarkInputError("dry_run_has_results")
            return
        if self.result_count != expected_count:
            raise BenchmarkInputError("result_count_mismatch")

        expected_pairs = {
            (candidate, fixture.pdf_path, fixture.page_number)
            for candidate in self.candidates
            for fixture in self.fixtures
        }
        actual_pairs = {
            (result.candidate, result.fixture.pdf_path, result.fixture.page_number)
            for result in self.results
        }
        if actual_pairs != expected_pairs:
            raise BenchmarkInputError("candidate_fixture_reconciliation_failed")
        _aggregate_cost(result.cost_usd for result in self.results)
        for candidate in self.candidates:
            _aggregate_cost(
                result.cost_usd
                for result in self.results
                if result.candidate == candidate
            )

    def blind_view(self) -> dict[str, Any]:
        labels = {candidate: chr(ord("A") + index) for index, candidate in enumerate(self.candidates)}
        candidate_summaries = {
            label: {
                "result_count": sum(
                    result.candidate == candidate for result in self.results
                ),
                "total_cost_usd": round(
                    _aggregate_cost(
                        result.cost_usd
                        for result in self.results
                        if result.candidate == candidate
                    ),
                    8,
                ),
            }
            for candidate, label in labels.items()
        }
        return {
            "schema_version": 1,
            "dry_run": self.dry_run,
            "fixture_count": self.fixture_count,
            "candidate_count": self.candidate_count,
            "result_count": self.result_count,
            "total_cost_usd": round(
                _aggregate_cost(result.cost_usd for result in self.results), 8
            ),
            "candidates": candidate_summaries,
            "results": [result.blind_view(labels[result.candidate]) for result in self.results],
        }

    def to_json(self) -> str:
        """Serialize only the anonymous report that a human scorer may review."""
        return json.dumps(
            self.blind_view(), indent=2, sort_keys=True, allow_nan=False
        ) + "\n"


def load_and_verify_fixtures(manifest_path: Path) -> tuple[BenchmarkFixture, ...]:
    """Load the selected fixture pages and verify every recorded PDF hash first."""
    path = Path(manifest_path)
    try:
        raw = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json_constant,
        )
    except FileNotFoundError as exc:
        raise BenchmarkInputError("manifest_not_found") from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise BenchmarkInputError("manifest_invalid_json") from exc

    try:
        json.dumps(raw, allow_nan=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise BenchmarkInputError("manifest_invalid_json") from exc
    if (
        not isinstance(raw, Mapping)
        or set(raw) != {"fixtures"}
        or not isinstance(raw.get("fixtures"), list)
    ):
        raise BenchmarkInputError("fixtures_required")
    if not raw["fixtures"]:
        raise BenchmarkInputError("fixtures_empty")

    fixtures = tuple(_parse_fixture(item, path.parent) for item in raw["fixtures"])
    if len({(fixture.pdf_path, fixture.page_number) for fixture in fixtures}) != len(fixtures):
        raise BenchmarkInputError("duplicate_fixture_page")
    if {fixture.fixture_class for fixture in fixtures} != FIXTURE_CLASSES:
        raise BenchmarkInputError("fixture_class_coverage_required")

    for fixture in fixtures:
        actual_hash = _sha256_file(fixture.pdf_path)
        if actual_hash != fixture.pdf_sha256:
            raise BenchmarkInputError("pdf_sha256_mismatch")
    page_counts: dict[Path, int] = {}
    for fixture in fixtures:
        if fixture.pdf_path not in page_counts:
            try:
                with fitz.open(str(fixture.pdf_path)) as document:
                    page_counts[fixture.pdf_path] = document.page_count
            except Exception as exc:
                raise BenchmarkInputError("pdf_invalid") from exc
        if fixture.page_number > page_counts[fixture.pdf_path]:
            raise BenchmarkInputError("page_number_out_of_bounds")
    return fixtures


def _parse_fixture(raw: object, manifest_dir: Path) -> BenchmarkFixture:
    fixture_fields = {
        "pdf_path",
        "pdf_sha256",
        "page_number",
        "fixture_class",
        "human_scoring",
    }
    if not isinstance(raw, Mapping) or set(raw) != fixture_fields:
        raise BenchmarkInputError("fixture_invalid")
    pdf_path_raw = raw.get("pdf_path")
    pdf_sha256 = raw.get("pdf_sha256")
    page_number = raw.get("page_number")
    fixture_class = raw.get("fixture_class")
    human_scoring = raw.get("human_scoring")

    if not isinstance(pdf_path_raw, str) or not pdf_path_raw:
        raise BenchmarkInputError("pdf_path_required")
    pdf_path = Path(pdf_path_raw)
    if not pdf_path.is_absolute():
        pdf_path = manifest_dir / pdf_path
    if not pdf_path.is_file():
        raise BenchmarkInputError("pdf_path_not_found")
    if not isinstance(pdf_sha256, str) or not _SHA256_RE.fullmatch(pdf_sha256):
        raise BenchmarkInputError("pdf_sha256_invalid")
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise BenchmarkInputError("page_number_invalid")
    if fixture_class not in FIXTURE_CLASSES:
        raise BenchmarkInputError("fixture_class_invalid")
    if not isinstance(human_scoring, Mapping):
        raise BenchmarkInputError("human_scoring_required")
    if set(human_scoring) != REQUIRED_SCORING_FIELDS:
        raise BenchmarkInputError("human_scoring_fields_invalid")

    return BenchmarkFixture(
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        page_number=page_number,
        fixture_class=fixture_class,
        human_scoring=dict(human_scoring),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _aggregate_cost(costs: Iterable[float]) -> float:
    total = 0.0
    for cost in costs:
        total += cost
        if not math.isfinite(total):
            raise BenchmarkInputError("aggregate_cost_invalid")
    return total


def _validate_candidates(providers: Sequence[OCRProvider]) -> tuple[BenchmarkCandidate, ...]:
    if len(providers) != 3:
        raise BenchmarkInputError("exactly_three_candidates_required")
    candidates = tuple(provider.candidate for provider in providers)
    if not all(isinstance(candidate, BenchmarkCandidate) for candidate in candidates):
        raise BenchmarkInputError("candidate_invalid")
    if len(set(candidates)) != len(candidates):
        raise BenchmarkInputError("candidate_duplicate")
    return candidates


def _result_from_response(
    candidate: BenchmarkCandidate,
    fixture: BenchmarkFixture,
    response: OCRResponse,
) -> BenchmarkPageResult:
    if not isinstance(response, OCRResponse):
        raise BenchmarkInputError("provider_response_invalid")
    if not isinstance(response.text, str):
        raise BenchmarkInputError("provider_text_invalid")
    if not isinstance(response.usage, Mapping) or not response.usage:
        raise BenchmarkInputError("provider_usage_required")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in response.usage.values()
    ):
        raise BenchmarkInputError("provider_usage_invalid")
    if (
        isinstance(response.cost_usd, bool)
        or not isinstance(response.cost_usd, (int, float))
        or not math.isfinite(response.cost_usd)
        or response.cost_usd < 0
    ):
        raise BenchmarkInputError("provider_cost_invalid")
    return BenchmarkPageResult(
        candidate=candidate,
        fixture=fixture,
        text=response.text,
        usage=dict(response.usage),
        cost_usd=float(response.cost_usd),
    )


def run_benchmark(
    manifest_path: Path,
    providers: Sequence[OCRProvider],
    output_path: Path,
) -> BenchmarkReport:
    """Run exactly the verified fixture pages against exactly three injected providers."""
    fixtures = load_and_verify_fixtures(manifest_path)
    candidates = _validate_candidates(providers)
    results = tuple(
        _result_from_response(provider.candidate, fixture, provider.transcribe(fixture))
        for fixture in fixtures
        for provider in providers
    )
    report = BenchmarkReport.from_results(fixtures, candidates, results)
    Path(output_path).write_text(report.to_json(), encoding="utf-8")
    return report


def dry_run_benchmark(
    manifest_path: Path,
    providers: Sequence[OCRProvider],
    output_path: Path,
) -> BenchmarkReport:
    """Verify immutable fixture identity and emit accounting-free blind evidence."""
    fixtures = load_and_verify_fixtures(manifest_path)
    candidates = _validate_candidates(providers)
    report = BenchmarkReport(tuple(fixtures), candidates, (), dry_run=True)
    report._validate_reconciliation()
    Path(output_path).write_text(report.to_json(), encoding="utf-8")
    return report
