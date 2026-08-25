#!/usr/bin/env python3
"""No-network proofs for approved New Wine proposition ingestion."""

from __future__ import annotations

import hashlib
import inspect
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import fitz
import pytest

import ingest_magazine
import propositions
import review_magazine_issue as review_runner
from magazine_review.articles import (
    ARTICLE_MODEL,
    _config_fingerprint as article_config_fingerprint,
    _review_config as article_review_config,
    _segmentation_config as article_segmentation_config,
    _stage_identity as article_stage_identity,
)
from magazine_review.artifacts import write_artifact
from magazine_review.ocr import VerifiedIssueTranscript
from magazine_review.proposition_review import (
    REVIEW_MODEL,
    REVIEW_PROMPT_FINGERPRINT,
    expected_proposition_review_identity,
)
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
from test_review_magazine_issue import (
    TEXT as ORCHESTRATOR_ARTICLE_TEXT,
    install_passing_stages,
    review_config,
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
SECOND_ARTICLE_BODY = (
    "Ben Vale teaches that humble service grows through attention to ordinary "
    "neighbors and through steady participation in the gathered church. This "
    "second reviewed article contains enough substantive language to exercise "
    "a genuine two-article retry while keeping every source byte deterministic. "
    "It explains that unnoticed work can form patience, deepen mutual trust, "
    "and redirect ambition toward care for other people. The conclusion returns "
    "to shared worship as the setting where faithful habits mature over time."
)
SECOND_APPROVED_CONTENT = "Ben Vale teaches that humble service forms patience."


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


def write_reviewed_fixture(
    tmp_path: Path, *, article_count: int = 1
) -> tuple[Path, Path, IssueDecision]:
    issue_dir = tmp_path / "issue"
    artifact_dir = tmp_path / "artifacts"
    issue_dir.mkdir()
    artifact_dir.mkdir()

    pdf_bytes = b"reviewed issue PDF bytes"
    pdf_hash = digest(pdf_bytes)
    (issue_dir / "reviewed-issue.pdf").write_bytes(pdf_bytes)
    specs = [
        {
            "article_id": ARTICLE_ID,
            "filename": ARTICLE_FILENAME,
            "title": "Grace in Community",
            "author": "Ada North",
            "body": ARTICLE_BODY,
            "propositions": (
                (APPROVED_CONTENT[0], "grace is received by faith"),
                (
                    APPROVED_CONTENT[1],
                    "prayer forms ordinary disciples over time",
                ),
            ),
        },
        {
            "article_id": "reviewed-article-two",
            "filename": "reviewed-article-two.txt",
            "title": "Humble Service",
            "author": "Ben Vale",
            "body": SECOND_ARTICLE_BODY,
            "propositions": (
                (SECOND_APPROVED_CONTENT, "humble service grows"),
            ),
        },
    ][:article_count]
    if len(specs) != article_count:
        raise ValueError("fixture supports one or two articles")
    page_text = "\n\n".join(str(spec["body"]) for spec in specs)
    for spec in specs:
        md_text = (
            "---\n"
            f"TITLE: {spec['title']}\n"
            f"AUTHOR: {spec['author']}\n"
            "ISSUE: 1974\n"
            "DATE: 1974\n"
            "TOPIC_TAGS:\n"
            "BIBLE_REFS:\n"
            "---\n\n"
            f"# {spec['title']}\n"
            f"*by {spec['author']}*\n\n"
            f"{spec['body']}"
        )
        (issue_dir / Path(str(spec["filename"])).with_suffix(".md")).write_text(
            md_text, encoding="utf-8"
        )

    ocr = OCRManifest(
        identity=identity("issue.pdf", pdf_hash),
        pdf_hash=pdf_hash,
        page_count=1,
        pages=(
            OCRPage(
                page_number=1,
                image_hash=digest("page-image"),
                initial_text=page_text,
                initial_text_hash=digest(page_text),
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
                text=page_text,
                final_text_hash=digest(page_text),
                transcript_start=0,
                transcript_end=len(page_text),
            ),
        ),
        usage={"input_tokens": 2},
        cost_usd=0.02,
    )
    ocr_hash = write_artifact(artifact_dir / "ocr_manifest.json", ocr)

    transcript = VerifiedIssueTranscript.from_manifest(ocr)
    article_records = []
    search_start = 0
    for spec in specs:
        body = str(spec["body"])
        article_start = transcript.text.index(body, search_start)
        article_records.append(
            ArticleRecord(
                article_id=str(spec["article_id"]),
                filename=str(spec["filename"]),
                title=str(spec["title"]),
                author=str(spec["author"]),
                source_pages=(1,),
                transcript_start=article_start,
                transcript_end=article_start + len(body),
                text=body,
                text_hash=digest(body),
                start_coherent=True,
                end_coherent=True,
                transitions_ok=True,
                omissions=(),
                duplications=(),
                adjacent_bleed=(),
                attribution_ok=True,
                verdict=True,
            )
        )
        search_start = article_start + len(body)
    transcript_hash = digest(transcript.text)
    article_manifest = ArticleManifest(
        identity=article_stage_identity(transcript, transcript_hash),
        issue_hash=transcript_hash,
        ocr_artifact_hash=ocr.identity.digest,
        transcript=transcript.text,
        articles=tuple(article_records),
        segmentation_model=ARTICLE_MODEL,
        segmentation_prompt_fingerprint=article_config_fingerprint(
            article_segmentation_config()
        ),
        segmentation_usage={"input_tokens": 1},
        segmentation_cost_usd=0.01,
        reviewer_model=ARTICLE_MODEL,
        reviewer_prompt_fingerprint=article_config_fingerprint(
            article_review_config()
        ),
        reviewer_usage={"input_tokens": 1},
        reviewer_cost_usd=0.01,
    )
    article_hash = write_artifact(
        artifact_dir / "article_manifest.json", article_manifest
    )

    proposition_hashes = {}
    approved_sets = []
    for spec, article in zip(specs, article_records):
        evidence = []
        for index, (content, evidence_text) in enumerate(
            spec["propositions"], start=1
        ):
            evidence_start = article.text.index(evidence_text)
            evidence.append(
                PropositionEvidence(
                    proposition_index=index,
                    content=content,
                    evidence_text=evidence_text,
                    evidence_start=evidence_start,
                    evidence_end=evidence_start + len(evidence_text),
                    evidence_offset_exact=True,
                    supported=True,
                    missing_qualification=False,
                    overstatement=False,
                    attribution_ok=True,
                    reviewer_reasons=(),
                )
            )
        review = PropositionReview(
            identity=identity("article", article_hash),
            article_id=article.article_id,
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
            reviewer_model=REVIEW_MODEL,
            reviewer_prompt_fingerprint=REVIEW_PROMPT_FINGERPRINT,
            reviewer_usage={"input_tokens": 2},
            reviewer_cost_usd=0.01,
            article_text=article.text,
            propositions=tuple(evidence),
        )
        review = replace(
            review,
            identity=expected_proposition_review_identity(
                review,
                article_hash=article.article_hash,
                article_artifact_hash=article_hash,
                extractor_model=propositions.EXTRACTION_MODEL,
            ),
        )
        review_name = hashlib.sha256(
            article.article_id.encode("utf-8")
        ).hexdigest()[:24]
        proposition_hash = write_artifact(
            artifact_dir / f"proposition_review_{review_name}.json", review
        )
        proposition_hashes[article.article_id] = proposition_hash
        approved_sets.append(
            ApprovedPropositionSet.from_review(review, proposition_hash)
        )
    decision = IssueDecision(
        identity=identity("issue.pdf", pdf_hash),
        issue_hash=pdf_hash,
        state="approved",
        ocr_artifact_hash=ocr_hash,
        article_artifact_hash=article_hash,
        proposition_artifact_hashes=proposition_hashes,
        article_hashes={
            article.article_id: article.article_hash for article in article_records
        },
        totals={
            "pages": 1,
            "articles": len(article_records),
            "propositions": sum(len(item.propositions) for item in approved_sets),
        },
        usage={"attempted": 3, "passed": 3},
        cost_usd=0.06,
        gate_results={"ocr": True, "articles": True, "propositions": True},
        approved_propositions=tuple(approved_sets),
    )
    write_artifact(artifact_dir / "issue_decision.json", decision)
    return issue_dir, artifact_dir, decision


def test_task6_canonical_artifacts_validate_without_any_write_boundary(
    tmp_path: Path, monkeypatch
) -> None:
    """Task 6's real artifact semantics must feed Task 7 without reshaping."""
    issue_dir = tmp_path / "canonical-issue"
    artifact_dir = tmp_path / "canonical-artifacts"
    issue_dir.mkdir()
    pdf_path = issue_dir / "NewWineMagazine_Issue_02-1974.pdf"
    document = fitz.open()
    page = document.new_page(width=288, height=432)
    page.insert_text((36, 72), ORCHESTRATOR_ARTICLE_TEXT)
    document.save(pdf_path)
    document.close()

    install_passing_stages(monkeypatch, pdf_path)
    decision = review_runner.review_issue(
        pdf_path, artifact_dir, review_config(pdf_path)
    )
    (issue_dir / "grace-by-faith.md").write_text(
        "---\n"
        "TITLE: Grace by Faith\n"
        "AUTHOR: Ada North\n"
        "ISSUE: 1974\n"
        "DATE: 1974\n"
        "---\n\n"
        "# Grace by Faith\n"
        "*by Ada North*\n\n"
        f"{ORCHESTRATOR_ARTICLE_TEXT}",
        encoding="utf-8",
    )

    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("validation must not cross a DB or embedding boundary")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "chunk_text", forbidden)

    approval = ingest_magazine.validate_reviewed_issue(issue_dir, artifact_dir)

    assert decision.state == "approved"
    assert approval.issue_hash == decision.issue_hash
    assert {article.snapshot.path.name for article in approval.articles} == {
        "grace-by-faith.md"
    }


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

    assert stats == {"attempted": 1, "stored": 1, "errored": 0, "skipped": 0}
    assert len(calls) == 1
    supplied = calls[0]["_reviewed_propositions"]
    assert not isinstance(supplied, ApprovedPropositionSet)
    assert supplied.as_storage_list(
        text=ARTICLE_BODY, speaker="Ada North", prompt_version="v3.1"
    ) == [
        {"proposition_index": 1, "content": APPROVED_CONTENT[0]},
        {"proposition_index": 2, "content": APPROVED_CONTENT[1]},
    ]
    assert calls[0]["skip_dedup"] is False
    assert calls[0]["filename"] == calls[0]["file_path"]
    assert decision.issue_hash in calls[0]["file_path"]
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


def test_current_proposition_review_identity_drift_refuses_before_database(
    tmp_path: Path, monkeypatch
) -> None:
    """A self-consistent artifact cannot nominate its own stale stage identity."""
    issue_dir, artifact_dir, decision = write_reviewed_fixture(tmp_path)
    review_path = ingest_magazine._proposition_review_path(artifact_dir, ARTICLE_ID)
    review = ingest_magazine._load_artifact(review_path, PropositionReview)
    stale_identity = replace(
        review.identity,
        renderer_settings={
            **review.identity.renderer_settings,
            "reasoning_effort": "low",
        },
    )
    stale_review = replace(review, identity=stale_identity)
    stale_review_hash = write_artifact(review_path, stale_review)
    stale_approved = ApprovedPropositionSet.from_review(
        stale_review, stale_review_hash
    )
    write_artifact(
        artifact_dir / "issue_decision.json",
        replace(
            decision,
            proposition_artifact_hashes={ARTICLE_ID: stale_review_hash},
            approved_propositions=(stale_approved,),
        ),
    )
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("identity drift must fail before DB and embedding calls")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "chunk_text", forbidden)

    with pytest.raises(
        propositions.ApprovedArtifactMismatch,
        match="proposition_review_identity_mismatch",
    ):
        ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("TITLE: Grace in Community", "TITLE: Grace Somewhere Else"),
        ("AUTHOR: Ada North", "AUTHOR: Ada South"),
    ],
)
def test_reviewed_metadata_drift_refuses_before_database_or_embedding(
    tmp_path: Path, monkeypatch, old: str, new: str
) -> None:
    """Approved attribution is immutable just like the approved body bytes."""
    issue_dir, artifact_dir, _decision = write_reviewed_fixture(tmp_path)
    md_path = issue_dir / "reviewed-article.md"
    md_path.write_text(
        md_path.read_text(encoding="utf-8").replace(old, new),
        encoding="utf-8",
    )
    forbidden = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("metadata drift must fail before DB and embedding calls")
    )
    monkeypatch.setattr(ingest_magazine, "get_db", forbidden)
    monkeypatch.setattr(ingest_magazine.shared_ingest, "ingest_document", forbidden)
    monkeypatch.setattr(ingest_magazine, "chunk_text", forbidden)

    with pytest.raises(propositions.ApprovedArtifactMismatch):
        ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)


def test_reviewed_markdown_is_read_once_and_snapshot_is_carried_to_writer(
    tmp_path: Path, monkeypatch
) -> None:
    """Validation and writing must share one immutable markdown byte snapshot."""
    issue_dir, artifact_dir, _decision = write_reviewed_fixture(tmp_path)
    md_path = issue_dir / "reviewed-article.md"
    original_open = Path.open
    markdown_reads = []

    def tracking_open(self, *args, **kwargs):
        if self == md_path:
            markdown_reads.append(args[0] if args else kwargs.get("mode", "r"))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr(ingest_magazine, "get_db", lambda: object())
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", lambda text: [])
    monkeypatch.setattr(
        ingest_magazine.shared_ingest,
        "ingest_document",
        lambda **kwargs: {
            "status": "processed",
            "reason": None,
            "chunks": ["chunk"],
        },
    )

    stats = ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)

    assert stats["stored"] == 1
    assert markdown_reads == ["rb"]


def test_reviewed_retry_after_partial_failure_is_idempotent_and_reconciled(
    tmp_path: Path, monkeypatch
) -> None:
    """A committed article skips on retry while the failed article can store."""
    issue_dir, artifact_dir, _decision = write_reviewed_fixture(
        tmp_path, article_count=2
    )
    persisted = set()
    inserted = []
    fail_second_once = {"active": True}

    def fake_atomic_writer(**kwargs):
        stable_path = kwargs["file_path"]
        assert kwargs["filename"] == stable_path
        assert kwargs["skip_dedup"] is False
        if stable_path in persisted:
            return {"status": "skipped", "reason": "already_ingested", "chunks": []}
        if "reviewed-article-two" in stable_path and fail_second_once["active"]:
            fail_second_once["active"] = False
            raise RuntimeError("simulated second-article writer failure")
        persisted.add(stable_path)
        inserted.append(stable_path)
        return {"status": "processed", "reason": None, "chunks": ["chunk"]}

    monkeypatch.setattr(ingest_magazine, "get_db", lambda: object())
    monkeypatch.setattr(ingest_magazine, "extract_bible_references", lambda text: [])
    monkeypatch.setattr(
        ingest_magazine.shared_ingest, "ingest_document", fake_atomic_writer
    )

    first = ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)
    second = ingest_magazine.ingest_reviewed_issue(issue_dir, artifact_dir)

    assert first == {"attempted": 2, "stored": 1, "errored": 1, "skipped": 0}
    assert second == {"attempted": 2, "stored": 1, "errored": 0, "skipped": 1}
    assert len(inserted) == 2
    assert len(set(inserted)) == 2
    assert len(persisted) == 2


def test_bare_approved_sets_are_not_accepted_by_any_ingest_entry_point() -> None:
    """Only the private full-issue validated capability may bypass generation."""
    assert "approved_artifact" not in inspect.signature(
        ingest_magazine.ingest_article
    ).parameters
    assert "approved_artifacts" not in inspect.signature(
        ingest_magazine.ingest_issue
    ).parameters
    assert "approved_propositions" not in inspect.signature(
        propositions.process_document
    ).parameters
    assert "approved_propositions" not in inspect.signature(
        ingest_magazine.shared_ingest.ingest_document
    ).parameters


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

    assert stats == {"attempted": 1, "stored": 0, "errored": 0, "skipped": 1}
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
