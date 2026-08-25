#!/usr/bin/env python3
"""No-network proofs for approved New Wine proposition ingestion."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import ingest_magazine
import propositions
from magazine_review.artifacts import write_artifact
from magazine_review.schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArticleRecord,
    IssueDecision,
    OCRManifest,
    OCRPage,
    PropositionEvidence,
    PropositionReview,
    StageIdentity,
)


ARTICLE_ID = "reviewed-article"
ARTICLE_FILENAME = "reviewed-article.txt"
ARTICLE_BODY = (
    "Ada North teaches that grace is received by faith and practiced through "
    "patient love in the shared life of the church. The reviewed article keeps "
    "developing that claim with enough substantive words to cross the existing "
    "proposition floor while retaining exact bytes for its article hash. It "
    "also explains that prayer forms ordinary disciples over time, and that "
    "faithful service grows from attention to God rather than public acclaim."
)
APPROVED_CONTENT = (
    "Ada North teaches that grace is received by faith.",
    "Patient prayer forms ordinary disciples over  time.\nThis line is retained.",
)


def digest(value: str | bytes) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def identity(label: str, input_hash: str) -> StageIdentity:
    return StageIdentity(
        schema_version=1,
        input_hashes={label: input_hash},
        model="offline-fixture",
        prompt_fingerprint=digest(f"prompt:{label}"),
        renderer_settings={},
    )


def write_reviewed_fixture(tmp_path: Path) -> tuple[Path, Path, IssueDecision]:
    issue_dir = tmp_path / "issue"
    artifact_dir = tmp_path / "artifacts"
    issue_dir.mkdir()
    artifact_dir.mkdir()

    pdf_bytes = b"reviewed issue PDF bytes"
    pdf_hash = digest(pdf_bytes)
    (issue_dir / "reviewed-issue.pdf").write_bytes(pdf_bytes)
    md_text = (
        "---\n"
        "TITLE: Grace in Community\n"
        "AUTHOR: Ada North\n"
        "ISSUE: 1974\n"
        "DATE: 1974\n"
        "TOPIC_TAGS:\n"
        "BIBLE_REFS:\n"
        "---\n\n"
        "# Grace in Community\n"
        "*by Ada North*\n\n"
        f"{ARTICLE_BODY}"
    )
    (issue_dir / "reviewed-article.md").write_text(md_text, encoding="utf-8")

    ocr = OCRManifest(
        identity=identity("issue.pdf", pdf_hash),
        pdf_hash=pdf_hash,
        page_count=1,
        pages=(
            OCRPage(
                page_number=1,
                image_hash=digest("page-image"),
                initial_text=ARTICLE_BODY,
                initial_text_hash=digest(ARTICLE_BODY),
                initial_provider="offline",
                initial_model="offline-ocr",
                initial_prompt_fingerprint=digest("ocr-prompt"),
                initial_usage={"input_tokens": 1},
                initial_cost_usd=0.01,
                initial_timestamp="2026-08-25T00:00:00Z",
                reviewer_model="offline-reviewer",
                reviewer_prompt_fingerprint=digest("ocr-review-prompt"),
                reviewer_complete=True,
                reviewer_reasons=(),
                reviewer_usage={"input_tokens": 1},
                reviewer_cost_usd=0.01,
                reviewer_timestamp="2026-08-25T00:00:01Z",
                repaired_text=None,
                repaired_text_hash=None,
                repair_provider=None,
                repair_model=None,
                repair_prompt_fingerprint=None,
                repair_usage=None,
                repair_cost_usd=None,
                repair_timestamp=None,
                text=ARTICLE_BODY,
                final_text_hash=digest(ARTICLE_BODY),
                transcript_start=0,
                transcript_end=len(ARTICLE_BODY),
            ),
        ),
        usage={"input_tokens": 2},
        cost_usd=0.02,
    )
    ocr_hash = write_artifact(artifact_dir / "ocr_manifest.json", ocr)

    article = ArticleRecord(
        article_id=ARTICLE_ID,
        filename=ARTICLE_FILENAME,
        title="Grace in Community",
        author="Ada North",
        source_pages=(1,),
        transcript_start=0,
        transcript_end=len(ARTICLE_BODY),
        text=ARTICLE_BODY,
        text_hash=digest(ARTICLE_BODY),
        start_coherent=True,
        end_coherent=True,
        transitions_ok=True,
        omissions=(),
        duplications=(),
        adjacent_bleed=(),
        attribution_ok=True,
        verdict=True,
    )
    article_manifest = ArticleManifest(
        identity=identity("ocr", ocr_hash),
        issue_hash=digest(ARTICLE_BODY),
        ocr_artifact_hash=ocr_hash,
        transcript=ARTICLE_BODY,
        articles=(article,),
        segmentation_model="offline-segmenter",
        segmentation_prompt_fingerprint=digest("segment-prompt"),
        segmentation_usage={"input_tokens": 1},
        segmentation_cost_usd=0.01,
        reviewer_model="offline-article-reviewer",
        reviewer_prompt_fingerprint=digest("article-review-prompt"),
        reviewer_usage={"input_tokens": 1},
        reviewer_cost_usd=0.01,
    )
    article_hash = write_artifact(
        artifact_dir / "article_manifest.json", article_manifest
    )

    evidence_text = "grace is received by faith"
    evidence_start = ARTICLE_BODY.index(evidence_text)
    review = PropositionReview(
        identity=identity("article", article_hash),
        article_id=ARTICLE_ID,
        article_hash=article.article_hash,
        article_artifact_hash=article_hash,
        model=propositions.EXTRACTION_MODEL,
        prompt_version="v3.1",
        prompt_fingerprint=propositions.prompt_fingerprint("v3.1"),
        extraction_usage={"input_tokens": 5, "output_tokens": 2},
        extraction_cost_usd=0.01,
        extraction_cost_basis={
            "type": "provider_reported",
            "model": propositions.EXTRACTION_MODEL,
            "currency": "USD",
        },
        grounding_totals={
            "found": 0,
            "grounded": 0,
            "stripped_fabricated": 0,
            "stripped_uncertain": 0,
            "kept_arbitration": 0,
        },
        reviewer_model="offline-proposition-reviewer",
        reviewer_prompt_fingerprint=digest("proposition-review-prompt"),
        reviewer_usage={"input_tokens": 2},
        reviewer_cost_usd=0.01,
        article_text=ARTICLE_BODY,
        propositions=(
            PropositionEvidence(
                proposition_index=1,
                content=APPROVED_CONTENT[0],
                evidence_text=evidence_text,
                evidence_start=evidence_start,
                evidence_end=evidence_start + len(evidence_text),
                evidence_offset_exact=True,
                supported=True,
                missing_qualification=False,
                overstatement=False,
                attribution_ok=True,
                reviewer_reasons=(),
            ),
            PropositionEvidence(
                proposition_index=2,
                content=APPROVED_CONTENT[1],
                evidence_text="prayer forms ordinary disciples over time",
                evidence_start=ARTICLE_BODY.index(
                    "prayer forms ordinary disciples over time"
                ),
                evidence_end=(
                    ARTICLE_BODY.index("prayer forms ordinary disciples over time")
                    + len("prayer forms ordinary disciples over time")
                ),
                evidence_offset_exact=True,
                supported=True,
                missing_qualification=False,
                overstatement=False,
                attribution_ok=True,
                reviewer_reasons=(),
            ),
        ),
    )
    review_name = hashlib.sha256(ARTICLE_ID.encode("utf-8")).hexdigest()[:24]
    proposition_hash = write_artifact(
        artifact_dir / f"proposition_review_{review_name}.json", review
    )
    approved = ApprovedPropositionSet.from_review(review, proposition_hash)
    decision = IssueDecision(
        identity=identity("issue.pdf", pdf_hash),
        issue_hash=pdf_hash,
        state="approved",
        ocr_artifact_hash=ocr_hash,
        article_artifact_hash=article_hash,
        proposition_artifact_hashes={ARTICLE_ID: proposition_hash},
        article_hashes={ARTICLE_ID: article.article_hash},
        totals={"pages": 1, "articles": 1, "propositions": 2},
        usage={"attempted": 3, "passed": 3},
        cost_usd=0.06,
        gate_results={"ocr": True, "articles": True, "propositions": True},
        approved_propositions=(approved,),
    )
    write_artifact(artifact_dir / "issue_decision.json", decision)
    return issue_dir, artifact_dir, decision


def test_reviewed_issue_passes_exact_approved_set_and_never_moves(
    tmp_path: Path, monkeypatch
) -> None:
    """Replacing reviewed content with generated text or moving files is a bug."""
    issue_dir, artifact_dir, decision = write_reviewed_fixture(tmp_path)
    calls = []

    def fake_ingest_document(**kwargs):
        calls.append(kwargs)
        return {
            "status": "processed",
            "reason": None,
            "doc_id": "doc",
            "source_id": "source",
            "chunks": ["chunk"],
            "propositions": "stored:2",
        }

    monkeypatch.setattr(ingest_magazine, "get_db", lambda: object())
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", fake_ingest_document)
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", lambda text: [])
    monkeypatch.setattr(
        ingest_magazine.shutil,
        "move",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("reviewed ingestion must never move files")
        ),
    )

    stats = ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)

    assert stats == {"ingested": 1, "skipped": 0}
    assert len(calls) == 1
    supplied = calls[0]["approved_propositions"]
    assert supplied == decision.approved_propositions[0]
    assert supplied.as_storage_list() == [
        {"proposition_index": 1, "content": APPROVED_CONTENT[0]},
        {"proposition_index": 2, "content": APPROVED_CONTENT[1]},
    ]
    assert issue_dir.is_dir()
    assert (issue_dir / "reviewed-issue.pdf").is_file()


def test_model_drift_refuses_before_database_or_embedding(
    tmp_path: Path, monkeypatch
) -> None:
    """Current-model drift must fail before any external write-side boundary."""
    issue_dir, artifact_dir, decision = write_reviewed_fixture(tmp_path)
    stale = replace(
        decision.approved_propositions[0], model="retired-extraction-model"
    )
    stale_decision = replace(decision, approved_propositions=(stale,))
    write_artifact(artifact_dir / "issue_decision.json", stale_decision)

    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("validation must precede DB and embedding calls")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "chunk_text", forbidden)

    with pytest.raises(propositions.ApprovedArtifactMismatch):
        ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)


def test_issue_decision_pdf_identity_drift_refuses_before_database(
    tmp_path: Path, monkeypatch
) -> None:
    """The decision's own PDF input identity must reconcile to source bytes."""
    issue_dir, artifact_dir, decision = write_reviewed_fixture(tmp_path)
    stale_identity = replace(
        decision.identity,
        input_hashes={**decision.identity.input_hashes, "issue.pdf": "f" * 64},
    )
    write_artifact(
        artifact_dir / "issue_decision.json",
        replace(decision, identity=stale_identity),
    )
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("decision lineage must fail before database access")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", forbidden)

    with pytest.raises(propositions.ApprovedArtifactMismatch):
        ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)


def test_reviewed_dry_run_validates_and_makes_no_database_or_embedding_call(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """Dry run may report approved evidence but may not cross external boundaries."""
    issue_dir, artifact_dir, _decision = write_reviewed_fixture(tmp_path)
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("reviewed dry run must not call DB or embedding")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", lambda text: [])

    stats = ingest_magazine.ingest_reviewed_issue(
        issue_dir, artifact_dir, dry_run=True
    )

    assert stats == {"ingested": 1, "skipped": 0}
    output = capsys.readouterr().out
    assert "approved propositions: 2" in output
    assert "issue decision sha256:" in output


def test_artifact_dir_cli_requires_one_explicit_source_issue(tmp_path: Path) -> None:
    """A reviewed artifact directory must never ambiguously scan legacy queues."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(ingest_magazine.__file__)),
            "--artifact-dir",
            str(artifact_dir),
        ],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 2
    assert "--artifact-dir requires --source-dir" in completed.stderr
