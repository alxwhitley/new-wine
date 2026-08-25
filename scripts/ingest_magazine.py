#!/usr/bin/env python3
"""
Magazine Ingestion Script

Reads approved .md articles from sources/magazine/03_approved/{issue_stem}/,
parses frontmatter metadata, chunks body text, and inserts into
Supabase documents + chunks tables.

After successful ingestion, moves the issue folder to sources/magazine/04_ingested/.
"""

import os
import re
import sys
import shutil
import logging
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

# Add backend to path so chunker/embeddings resolve
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from supabase import create_client
from app.services.chunker import chunk_text
from bible_refs import extract_bible_references
from magazine_review.artifacts import load_valid_artifact
from magazine_review.schemas import (
    ApprovedPropositionSet,
    ArticleManifest,
    ArtifactValidationError,
    IssueDecision,
    OCRManifest,
    PropositionReview,
    StageIdentity,
)
from source_resolver import (
    resolve_source_id,
    SENTINEL_SOURCE_ID,
    NEW_WINE_MAGAZINE_SOURCE_ID,
    print_resolution_table,
)
import propositions
import shared_ingest

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

_parsed_db = urlparse(os.environ.get("SUPABASE_DB_URL", ""))
DB_PARAMS = {
    "host":     _parsed_db.hostname,
    "port":     _parsed_db.port or 5432,
    "user":     unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname":   (_parsed_db.path or "").lstrip("/"),
}

# -- CONFIGURATION -----------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
APPROVED_DIR = ROOT / "sources" / "magazine" / "03_approved"
INGESTED_DIR = ROOT / "sources" / "magazine" / "04_ingested"
ARCHIVED_DIR = ROOT / "sources" / "magazine" / "05_archived"
TRACKER_PATH = ROOT / "sources" / "magazine" / "rhemata_tracker.xlsx"

ISSUE_DECISION_NAME = "issue_decision.json"
ARTICLE_MANIFEST_NAME = "article_manifest.json"
OCR_MANIFEST_NAME = "ocr_manifest.json"
PROPOSITION_PREFIX = "proposition_review_"


@dataclass(frozen=True)
class ReviewedIssueApproval:
    decision_hash: str
    issue_hash: str
    approved_by_filename: Mapping[str, ApprovedPropositionSet]

# -- SUPABASE ----------------------------------------------------------------

_db = None


def get_db():
    global _db
    if _db is None:
        _db = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _db


# -- FRONTMATTER PARSING -----------------------------------------------------

def parse_frontmatter(text: str) -> tuple:
    """Parse --- frontmatter --- block. Returns (metadata_dict, body_text)."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    meta_block = match.group(1)
    body = match.group(2)

    meta = {}
    for line in meta_block.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip()

    return meta, body


def _article_metadata_and_body(md_path: Path) -> tuple:
    text = md_path.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL)
    meta, body = parse_frontmatter(text)
    body = re.sub(r"^#\s+.*?\n\*by .*?\*\s*\n*", "", body, count=1)
    return meta, body.strip()


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise propositions.ApprovedArtifactMismatch("approved_artifact_unreadable") from exc


def _load_artifact(path: Path, expected_type):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        identity = StageIdentity.from_dict(raw["identity"])
        value = load_valid_artifact(Path(path), identity)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ArtifactValidationError) as exc:
        reason = str(exc).strip() or "approved_artifact_invalid"
        raise propositions.ApprovedArtifactMismatch(reason) from exc
    if not isinstance(value, expected_type):
        raise propositions.ApprovedArtifactMismatch("approved_artifact_type_mismatch")
    return value


def _proposition_review_path(artifact_dir: Path, article_id: str) -> Path:
    stable_name = hashlib.sha256(article_id.encode("utf-8")).hexdigest()[:24]
    return Path(artifact_dir) / f"{PROPOSITION_PREFIX}{stable_name}.json"


def validate_reviewed_issue(
    issue_dir: Path, artifact_dir: Path
) -> ReviewedIssueApproval:
    """Reconcile every approval artifact and source byte before DB access."""
    issue_path = Path(issue_dir)
    evidence_path = Path(artifact_dir)
    if not issue_path.is_dir() or not evidence_path.is_dir():
        raise propositions.ApprovedArtifactMismatch("reviewed_issue_path_invalid")

    decision_path = evidence_path / ISSUE_DECISION_NAME
    decision = _load_artifact(decision_path, IssueDecision)
    if decision.state != "approved":
        raise propositions.ApprovedArtifactMismatch("issue_decision_not_approved")
    if decision.identity.input_hashes.get("issue.pdf") != decision.issue_hash:
        raise propositions.ApprovedArtifactMismatch(
            "issue_decision_pdf_identity_mismatch"
        )
    decision_hash = _sha256_file(decision_path)

    ocr_path = evidence_path / OCR_MANIFEST_NAME
    article_path = evidence_path / ARTICLE_MANIFEST_NAME
    ocr = _load_artifact(ocr_path, OCRManifest)
    articles = _load_artifact(article_path, ArticleManifest)
    if _sha256_file(ocr_path) != decision.ocr_artifact_hash:
        raise propositions.ApprovedArtifactMismatch("ocr_artifact_hash_mismatch")
    if _sha256_file(article_path) != decision.article_artifact_hash:
        raise propositions.ApprovedArtifactMismatch("article_artifact_hash_mismatch")
    if ocr.status != "passed" or articles.status != "passed":
        raise propositions.ApprovedArtifactMismatch("reviewed_stage_not_passed")
    if ocr.pdf_hash != decision.issue_hash:
        raise propositions.ApprovedArtifactMismatch("issue_pdf_hash_mismatch")
    if articles.ocr_artifact_hash != decision.ocr_artifact_hash:
        raise propositions.ApprovedArtifactMismatch("article_ocr_hash_mismatch")
    if decision.totals["pages"] != ocr.page_count:
        raise propositions.ApprovedArtifactMismatch("issue_page_total_mismatch")

    pdf_files = sorted(issue_path.glob("*.pdf"))
    matching_pdfs = [path for path in pdf_files if _sha256_file(path) == decision.issue_hash]
    if len(pdf_files) != 1 or len(matching_pdfs) != 1:
        raise propositions.ApprovedArtifactMismatch("reviewed_issue_pdf_mismatch")

    article_by_id = {article.article_id: article for article in articles.articles}
    approved_by_id = {
        approved.article_id: approved for approved in decision.approved_propositions
    }
    expected_ids = set(article_by_id)
    if (
        set(approved_by_id) != expected_ids
        or set(decision.article_hashes) != expected_ids
        or set(decision.proposition_artifact_hashes) != expected_ids
    ):
        raise propositions.ApprovedArtifactMismatch("reviewed_article_ids_mismatch")

    md_files = sorted(issue_path.glob("*.md"))
    md_by_review_filename = {
        path.with_suffix(".txt").name: path
        for path in md_files
        if "flagged" not in str(path)
    }
    if set(md_by_review_filename) != {
        article.filename for article in articles.articles
    }:
        raise propositions.ApprovedArtifactMismatch("reviewed_article_files_mismatch")

    approved_by_filename: Dict[str, ApprovedPropositionSet] = {}
    for article_id, article in article_by_id.items():
        md_path = md_by_review_filename[article.filename]
        _meta, body = _article_metadata_and_body(md_path)
        if body != article.text or hashlib.sha256(body.encode("utf-8")).hexdigest() != article.article_hash:
            raise propositions.ApprovedArtifactMismatch("approved_article_hash_mismatch")

        review_path = _proposition_review_path(evidence_path, article_id)
        recorded_review_hash = _sha256_file(review_path)
        if recorded_review_hash != decision.proposition_artifact_hashes[article_id]:
            raise propositions.ApprovedArtifactMismatch("proposition_artifact_hash_mismatch")
        review = _load_artifact(review_path, PropositionReview)
        try:
            review.validate(article.text)
        except ArtifactValidationError as exc:
            raise propositions.ApprovedArtifactMismatch(str(exc)) from exc
        if (
            review.status != "passed"
            or review.article_id != article_id
            or review.article_hash != article.article_hash
            or review.article_artifact_hash != decision.article_artifact_hash
        ):
            raise propositions.ApprovedArtifactMismatch("proposition_review_lineage_mismatch")

        expected_approved = ApprovedPropositionSet.from_review(
            review, recorded_review_hash
        )
        approved = approved_by_id[article_id]
        if approved != expected_approved:
            raise propositions.ApprovedArtifactMismatch("approved_proposition_set_mismatch")
        propositions.validate_approved_propositions(
            approved,
            article.text,
            "v3.1",
            speaker=article.author,
        )
        approved_by_filename[md_path.name] = approved

    return ReviewedIssueApproval(
        decision_hash=decision_hash,
        issue_hash=decision.issue_hash,
        approved_by_filename=approved_by_filename,
    )


# -- INGESTION ---------------------------------------------------------------

def ingest_article(
    md_path: Path,
    issue_stem: str,
    dry_run: bool = False,
    approved_artifact: Optional[ApprovedPropositionSet] = None,
) -> Tuple[str, object]:
    """Ingest a single .md article file into Supabase.

    Returns (status, reason) using shared_ingest.ingest_document()'s status
    vocabulary ("processed" / "skipped" / "failed"), plus a magazine-specific
    ("skipped", "body_too_short") case for the pre-chunking quality gate below.

    dry_run=True previews chunk content and the embed/stored-content header
    asymmetry (see header comment below) without touching the database.
    """
    meta, body = _article_metadata_and_body(md_path)

    title = meta.get("TITLE", md_path.stem)
    author = meta.get("AUTHOR", "")
    issue = meta.get("ISSUE", "")
    date = meta.get("DATE", "")
    topic_tags_raw = meta.get("TOPIC_TAGS", "")
    topic_tags = [t.strip() for t in topic_tags_raw.split(",") if t.strip()] if topic_tags_raw else []
    frontmatter_refs_raw = meta.get("BIBLE_REFS", "")
    frontmatter_refs = [r.strip() for r in frontmatter_refs_raw.split(",") if r.strip()] if frontmatter_refs_raw else []

    # Clean author: truncate at parenthesis
    if "(" in author:
        author = author[:author.index("(")].rstrip()

    # Parse year from issue or date
    year = None
    year_match = re.search(r"(\d{4})", issue or date)
    if year_match:
        year = int(year_match.group(1))

    if not body or len(body) < 100:
        logger.warning("Skipping %s — body too short (%d chars)", md_path.name, len(body))
        return ("skipped", "body_too_short")

    # Extract Bible references from body (non-fatal — returns [] on failure)
    # Merge with any refs already extracted by regex during Pass 2
    bible_refs = extract_bible_references(body)
    if frontmatter_refs:
        seen = set(bible_refs)
        for r in frontmatter_refs:
            if r not in seen:
                bible_refs.append(r)
                seen.add(r)
    if bible_refs:
        print(f"  Bible refs: {len(bible_refs)} found ({', '.join(bible_refs[:5])}{'...' if len(bible_refs) > 5 else ''})")

    header = f"[New Wine | {date} | {title} by {author}]"

    if approved_artifact is not None:
        propositions.validate_approved_propositions(
            approved_artifact,
            body,
            "v3.1",
            speaker=author,
        )

    if dry_run:
        chunks = chunk_text(body)
        preview = chunks[:3]
        print(f"\n  [DRY RUN] Previewing first {len(preview)} of {len(chunks)} chunks:")
        for idx, chunk_content in enumerate(preview):
            embed_note = "WITH header (chunk 0 only)" if idx == 0 else "WITHOUT header"
            print(f"  ── Chunk {idx + 1} | embed input {embed_note} | stored content always WITH header ──")
            print(f"  Header: {header}")
            print(f"  Content: {chunk_content[:300]}{'...' if len(chunk_content) > 300 else ''}")
            print()
        print("  [DRY RUN] No data written to Supabase.")
        if approved_artifact is not None:
            print(f"  [DRY RUN] approved propositions: {len(approved_artifact.propositions)}")
        return ("processed", None)

    db = get_db()

    # Chunk-header asymmetry, reproduced exactly from the pre-conversion script:
    # the header is prepended to the STORED content of every chunk, but only
    # fed into the EMBEDDING input for chunk 0 -- every other chunk embeds
    # plain text. Getting this backwards silently changes what gets embedded.
    def _embed_with_header_idx0_only(idx, chunk_text_):
        return f"{header}\n\n{chunk_text_}" if idx == 0 else chunk_text_

    def _content_always_with_header(idx, chunk_text_):
        return f"{header}\n\n{chunk_text_}"

    result = shared_ingest.ingest_document(
        db=db,
        db_params=DB_PARAMS,
        title=title,
        body_text=body,
        filename=md_path.name,
        author=author or None,
        year=year,
        issue=issue or None,
        source_name="New Wine Magazine",
        source_type="magazine_article",
        source_kind="magazine_article",
        citation_mode="citable",
        is_copyrighted=True,
        topic_tags=topic_tags if topic_tags else None,
        bible_references=bible_refs,
        # Resolved HERE (not pre-resolved and passed as source_id) so that
        # shared_ingest's strict-mode SilentSentinelRefused guard -- which only
        # guards the resolve_from path -- actually applies to this script.
        resolve_from=("New Wine Magazine", author or None),
        # No DB-level dedup exists in this pipeline today -- the issue-folder
        # move to 04_ingested/ is the real guard. The default dedup key
        # (url/file_path) is never set on magazine documents, so it would
        # never fire anyway; skip_dedup=True makes that explicit instead of
        # relying on an accidental no-op.
        skip_dedup=True,
        embed_text_fn=_embed_with_header_idx0_only,
        content_fn=_content_always_with_header,
        approved_propositions=approved_artifact,
    )

    if result["status"] == "processed":
        print(f"  Ingested: {title} ({len(result['chunks'])} chunks)")
    return (result["status"], result["reason"])


def ingest_issue(
    issue_dir: Path,
    dry_run: bool = False,
    move_when_done: bool = True,
    approved_artifacts: Optional[Mapping[str, ApprovedPropositionSet]] = None,
) -> Dict:
    """Ingest all .md files in an issue directory. Returns stats.

    dry_run=True previews every article's chunks with no DB writes and no
    folder moves. move_when_done=False skips the PDF-archive + folder-move
    step even for a real (non-dry-run) ingest -- used by --source-dir so an
    isolated/scratch test folder is left untouched and the real 03_approved/
    queue state never changes.
    """
    issue_stem = issue_dir.name
    md_files = sorted(issue_dir.glob("*.md"))

    # Skip flagged subfolder
    md_files = [f for f in md_files if "flagged" not in str(f)]

    if approved_artifacts is not None:
        move_when_done = False
        if set(approved_artifacts) != {path.name for path in md_files}:
            raise propositions.ApprovedArtifactMismatch(
                "reviewed_article_files_mismatch"
            )

    if not md_files:
        print(f"  No .md files found in {issue_dir}")
        return {"ingested": 0, "skipped": 0}

    label = "[DRY RUN] " if dry_run else ""
    print(f"\n{label}Ingesting issue: {issue_stem} ({len(md_files)} articles)")

    ingested = 0
    skipped = 0

    for md_path in md_files:
        try:
            status, reason = ingest_article(
                md_path,
                issue_stem,
                dry_run=dry_run,
                approved_artifact=(
                    approved_artifacts[md_path.name]
                    if approved_artifacts is not None
                    else None
                ),
            )
        except shared_ingest.SilentSentinelRefused as e:
            skipped += 1
            print(f"\n{'!'*60}")
            print(f"  SKIPPED — silent sentinel refused: {md_path.name}")
            print(f"  title={e.title!r}  source_name={e.source_name!r}  author={e.author!r}")
            print(f"{'!'*60}\n")
            continue
        except Exception:
            logger.exception("Failed to ingest %s", md_path.name)
            skipped += 1
            continue
        if status == "processed":
            ingested += 1
        else:
            skipped += 1

    if dry_run or not move_when_done:
        return {"ingested": ingested, "skipped": skipped}

    # Archive any PDF(s) in the issue folder before moving .md files to ingested
    pdf_files = sorted(issue_dir.glob("*.pdf"))
    if pdf_files:
        ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
        for pdf_path in pdf_files:
            archive_dest = ARCHIVED_DIR / pdf_path.name
            shutil.move(str(pdf_path), str(archive_dest))
            print(f"  PDF archived to: {archive_dest}")

    # Move to ingested
    INGESTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = INGESTED_DIR / issue_stem
    if dest.exists():
        shutil.rmtree(dest)
    shutil.move(str(issue_dir), str(dest))
    print(f"  Moved to: {dest}")

    return {"ingested": ingested, "skipped": skipped}


def ingest_reviewed_issue(
    issue_dir: Path, artifact_dir: Path, dry_run: bool = False
) -> Dict:
    """Ingest one fully approved issue without promoting or moving sources."""
    approval = validate_reviewed_issue(issue_dir, artifact_dir)
    proposition_count = sum(
        len(approved.propositions)
        for approved in approval.approved_by_filename.values()
    )
    print(f"  issue decision sha256: {approval.decision_hash}")
    print(f"  issue PDF sha256: {approval.issue_hash}")
    print(f"  approved articles: {len(approval.approved_by_filename)}")
    print(f"  approved propositions: {proposition_count}")
    stats = ingest_issue(
        Path(issue_dir),
        dry_run=dry_run,
        move_when_done=False,
        approved_artifacts=approval.approved_by_filename,
    )
    print("  Source promotion remains a separate explicit operation; no files moved.")
    return stats


# -- MAIN --------------------------------------------------------------------

def run():
    """Scan 03_approved/ and ingest all issue folders."""
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)

    issue_dirs = sorted([d for d in APPROVED_DIR.iterdir() if d.is_dir()])
    if not issue_dirs:
        print(f"No issue folders found in {APPROVED_DIR}")
        return

    print(f"Found {len(issue_dirs)} issue folder(s) to ingest")

    total_ingested = 0
    total_skipped = 0

    for issue_dir in issue_dirs:
        stats = ingest_issue(issue_dir)
        total_ingested += stats["ingested"]
        total_skipped += stats["skipped"]

    print(f"\n{'='*60}")
    print(f"Done. {total_ingested} ingested, {total_skipped} skipped.")


def dry_run_sources_magazine() -> None:
    """Resolve attribution for every pending article in 03_approved/ and print
    a table.  No DB writes, no chunking, no embeddings.  The source_name is
    always 'New Wine Magazine' for this pipeline; resolution is via the
    source_aliases table so the same resolver path is exercised as ingest.py."""
    db = get_db()

    md_files = sorted(APPROVED_DIR.rglob("*.md"))
    # Mirror the ingest_issue filter — skip flagged subfolders
    md_files = [f for f in md_files if "flagged" not in str(f)]

    if not md_files:
        print(f"No .md files found under {APPROVED_DIR}")
        return

    print(f"[DRY-RUN-SOURCES] Found {len(md_files)} article(s) — resolving attribution only")

    rows = []
    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        # Strip QA comments (mirrors ingest_article)
        text = re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL)
        meta, _ = parse_frontmatter(text)

        author = meta.get("AUTHOR", "") or ""
        if "(" in author:
            author = author[: author.index("(")].rstrip()

        # Magazine source_name is always fixed; still route through resolver so
        # miss-logging fires correctly for any unexpected alias gaps.
        source_name = "New Wine Magazine"
        source_id, norm_key, via = resolve_source_id(db, source_name, author or None)

        rows.append({
            "file":        md_path.name,
            "source_name": source_name,
            "author":      author or None,
            "norm_key":    norm_key,
            "source_id":   source_id,
            "via":         via,
        })

    print_resolution_table(rows, label=f"{len(md_files)} article(s) in 03_approved/")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rhemata magazine ingestion")
    parser.add_argument(
        "--dry-run-sources",
        action="store_true",
        help="Resolve attribution strings and print source_id table — no DB writes, no chunking",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview chunk content and the embed/stored-content header asymmetry — no DB writes",
    )
    parser.add_argument(
        "--source-dir",
        type=str,
        default=None,
        help="Ingest a single issue-shaped directory of .md files instead of scanning 03_approved/. "
             "Never archives PDFs or moves the folder to 04_ingested/ — for isolated testing only.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default=None,
        help="Consume one approved review artifact directory; requires --source-dir and never moves sources.",
    )
    args = parser.parse_args()

    if args.artifact_dir and not args.source_dir:
        parser.error("--artifact-dir requires --source-dir")

    if args.dry_run_sources:
        dry_run_sources_magazine()
    elif args.source_dir and args.artifact_dir:
        source_dir = Path(args.source_dir)
        artifact_dir = Path(args.artifact_dir)
        if not source_dir.is_dir():
            print(f"ERROR: {source_dir} is not a directory")
            sys.exit(1)
        if not artifact_dir.is_dir():
            print(f"ERROR: {artifact_dir} is not a directory")
            sys.exit(1)
        try:
            stats = ingest_reviewed_issue(
                source_dir, artifact_dir, dry_run=args.dry_run
            )
        except propositions.ApprovedArtifactMismatch as exc:
            print(f"ERROR: reviewed artifact mismatch: {exc}", file=sys.stderr)
            sys.exit(2)
        print(f"\n{'='*60}")
        print(f"Done. {stats['ingested']} ingested, {stats['skipped']} skipped.")
    elif args.source_dir:
        source_dir = Path(args.source_dir)
        if not source_dir.is_dir():
            print(f"ERROR: {source_dir} is not a directory")
            sys.exit(1)
        stats = ingest_issue(source_dir, dry_run=args.dry_run, move_when_done=False)
        print(f"\n{'='*60}")
        print(f"Done. {stats['ingested']} ingested, {stats['skipped']} skipped.")
    elif args.dry_run:
        APPROVED_DIR.mkdir(parents=True, exist_ok=True)
        issue_dirs = sorted([d for d in APPROVED_DIR.iterdir() if d.is_dir()])
        if not issue_dirs:
            print(f"No issue folders found in {APPROVED_DIR}")
        else:
            print(f"[DRY RUN] Found {len(issue_dirs)} issue folder(s) to preview")
            total_ingested = total_skipped = 0
            for issue_dir in issue_dirs:
                stats = ingest_issue(issue_dir, dry_run=True, move_when_done=False)
                total_ingested += stats["ingested"]
                total_skipped += stats["skipped"]
            print(f"\n{'='*60}")
            print(f"[DRY RUN] Done. {total_ingested} previewed, {total_skipped} skipped.")
    else:
        run()
