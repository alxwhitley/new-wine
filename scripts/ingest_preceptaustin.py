#!/usr/bin/env python3
"""
Rhemata Precept Austin Word Study Ingestion Script

Reads extracted word study .txt files from sources/precept_austin/raw/,
chunks with tiktoken, embeds with OpenAI, and inserts into Supabase.

Converted (#9) to route through shared_ingest.ingest_document() with
insert_mode="psycopg2_batch" -- resolve/insert/chunk/embed/propositions is
the shared writer's job now; this script keeps only what's genuinely
Precept-Austin-specific: filename parsing, index.json gloss lookup, the
hardcoded is_copyrighted/citation_mode attribution, and the excerpt-keyed
reuse/skip guard (title match + excerpts.excerpt_type='word_study_article').
That guard's known hole -- it checks for an existing excerpt, not existing
chunks, so a re-run against a document that has no excerpt yet re-chunks
and re-inserts -- is UNCHANGED here by design; it's #11's fix, not this
conversion's. The new chunks(document_id, chunk_index) UNIQUE constraint
(migration 061) now backstops that hole loudly (a raised error) instead of
silently duplicating.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import psycopg2
from supabase import create_client
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.services.chunker import chunk_text, token_len
import shared_ingest

# ── Config ────────────────────────────────────────────────────────────────────

# Language flag: --language hebrew|greek (default: greek). Parsed manually
# from raw sys.argv, same as before conversion -- SOURCES_DIR/RAW_DIR/
# INDEX_FILE are module-level constants that depend on it, computed before
# main()'s argparse (for --dry-run/--source-dir, added this session) runs.
_lang = "greek"
for _i, _a in enumerate(sys.argv[1:], 1):
    if _a == "--language" and _i < len(sys.argv) - 1:
        _lang = sys.argv[_i + 1].lower()

LANG_SUBDIRS = {"greek": "precept_austin", "hebrew": "precept_austin_hebrew"}
if _lang not in LANG_SUBDIRS:
    print("ERROR: --language must be 'greek' or 'hebrew'")
    sys.exit(1)

SOURCES_DIR = PROJECT_ROOT / "sources" / LANG_SUBDIRS[_lang]
RAW_DIR = SOURCES_DIR / "raw"
INDEX_FILE = SOURCES_DIR / "index.json"

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    print("ERROR: SUPABASE_DB_URL is not set in backend/app/.env")
    print("Set it to your Supabase direct connection string, e.g.:")
    print("  SUPABASE_DB_URL=postgresql://user:password@host:5432/dbname")
    sys.exit(1)

_parsed_db = urlparse(SUPABASE_DB_URL)
DB_PARAMS = {
    "host": _parsed_db.hostname,
    "port": _parsed_db.port or 5432,
    "user": unquote(_parsed_db.username or ""),
    "password": unquote(_parsed_db.password or ""),
    "dbname": _parsed_db.path.lstrip("/"),
}

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_index():
    # type: () -> Dict[str, Dict[str, str]]
    """Load index.json and return a dict keyed by strongs_number."""
    if not INDEX_FILE.exists():
        print("ERROR: index.json not found. Run scrape_preceptaustin.py first.")
        sys.exit(1)
    with open(INDEX_FILE) as f:
        entries = json.load(f)
    return {e["strongs_number"]: e for e in entries}


def _parse_filename(filepath):
    # type: (Path) -> Optional[Tuple[str, str]]
    """Returns (strongs_number, transliteration) or None if the filename
    doesn't match the expected `G1459_egkataleipo` shape."""
    parts = filepath.stem.split("_", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def ingest_file(filepath, index_lookup, dry_run=False):
    # type: (Path, Dict[str, Dict[str, str]], bool) -> bool
    """Ingest a single word study .txt file into Supabase.

    dry_run=True previews the parsed filename/index-lookup/title and the
    first few chunks with zero DB reads or writes -- it returns before the
    existing-document/excerpt lookup runs at all.
    """
    parsed = _parse_filename(filepath)
    if parsed is None:
        print("  SKIP {}: unexpected filename format".format(filepath.stem))
        return False
    strongs_number, transliteration = parsed

    # Look up english_word from index
    index_entry = index_lookup.get(strongs_number)
    english_word = index_entry["english_word"] if index_entry else transliteration

    title = "Word Study: {} ({}, {})".format(english_word, transliteration, strongs_number)

    if dry_run:
        content = filepath.read_text(encoding="utf-8").strip()
        if not content:
            print("  SKIP {}: empty file".format(strongs_number))
            return False
        chunks = chunk_text(content, chunk_target=550, overlap=80)
        preview = chunks[:3]
        print(f"\n  [DRY RUN] {title}")
        print(f"  strongs={strongs_number}  transliteration={transliteration}  english_word={english_word}")
        print("  is_copyrighted=True  citation_mode=silent_context  source_name='Precept Austin'  author='Precept Austin'")
        print(f"  [DRY RUN] Previewing first {len(preview)} of {len(chunks)} chunks ({len(chunks)} total):")
        for idx, chunk_content in enumerate(preview):
            tokens = token_len(chunk_content)
            print(f"  ── Chunk {idx + 1} | {tokens} tokens ──")
            print(f"  Content: {chunk_content[:300]}{'...' if len(chunk_content) > 300 else ''}")
        print("  [DRY RUN] No data written to Supabase.")
        return True

    # Check if excerpt already exists for this word study. UNCHANGED reuse/
    # skip guard, preserved exactly as it was pre-conversion: keys on
    # excerpts.excerpt_type='word_study_article', not on chunk state. Its
    # known hole is #11's fix, not this session's.
    doc_result = supabase.table("documents").select("id").eq("title", title).limit(1).execute()
    doc_id_existing = doc_result.data[0]["id"] if doc_result.data else None
    if doc_id_existing:
        excerpt_result = (
            supabase.table("excerpts")
            .select("id")
            .eq("document_id", doc_id_existing)
            .eq("excerpt_type", "word_study_article")
            .limit(1)
            .execute()
        )
        if excerpt_result.data:
            print("  SKIP {}: excerpt already exists".format(strongs_number))
            return False

    content = filepath.read_text(encoding="utf-8").strip()
    if not content:
        print("  SKIP {}: empty file".format(strongs_number))
        return False

    def _find_existing():
        # Reuse-by-identity hook: returns the id found above, or None if no
        # document with this title exists yet. Same title-keyed lookup PA
        # always used -- just handed to the shared writer via its
        # find_existing_fn hook instead of branching on it locally.
        return doc_id_existing

    result = shared_ingest.ingest_document(
        db=supabase,
        db_params=DB_PARAMS,
        title=title,
        body_text=content,
        filename=filepath.name,
        author="Precept Austin",
        source_name="Precept Austin",
        source_type="background",
        source_kind="word_study",
        citation_mode="silent_context",
        is_copyrighted=True,
        topic_tags=[],
        bible_references=[],
        # PA's dedup is the title+excerpt check above, not the generic
        # url/file_path key (PA documents have never set either) --
        # skip_dedup=True makes that explicit instead of relying on an
        # accidental no-op from an always-empty file_path.
        skip_dedup=True,
        find_existing_fn=_find_existing,
        on_existing="reuse",
        insert_mode="psycopg2_batch",
    )

    if result["status"] == "processed":
        print("  OK {} ({}): {} chunks".format(strongs_number, english_word, len(result["chunks"])))
        return True
    else:
        print("  SKIPPED {} ({}): {}".format(strongs_number, english_word, result["reason"]))
        return False


# ── Interim survivability guard (NOT #11) ────────────────────────────────────
#
# ingest_preceptaustin.py's excerpt-keyed reuse guard has a known hole (it
# checks for an existing excerpt, not existing chunks -- see the module
# docstring above and rhemata-status.md/PLAN.md #11): a re-run against a
# document that has no excerpt yet reuses the doc_id and attempts to
# re-insert chunks at chunk_index values already present. Since #9 wired PA
# through the shared writer's psycopg2_batch insert mode, and migration 061
# added UNIQUE(document_id, chunk_index) on `chunks`, that reuse attempt now
# raises psycopg2.errors.UniqueViolation instead of silently duplicating --
# correct, but with no per-file handling one rejected doc used to kill the
# entire batch (main()'s loop had no try/except at all).
#
# This guard makes that SURVIVABLE, not CORRECT: a colliding doc is skipped
# and logged, the run continues -- it is NOT retried, updated, or fixed.
# The excerpt-vs-chunks mismatch underneath is unchanged and stays #11's job.
#
# Connection-state check (done, not assumed): _insert_chunks_psycopg2_batch
# opens its own psycopg2 connection per call and closes it in a `finally`
# block regardless of success or failure (shared_ingest.py, unmodified this
# session); _run_propositions does the same. Neither is shared across loop
# iterations, so there is no connection left aborted/poisoned for the next
# document to inherit -- verified by reading that code path, and empirically
# by this session's synthetic proof (fresh docs after a collision still
# process correctly in the same run).

def _is_chunk_index_collision(exc):
    # type: (Exception) -> bool
    """True iff exc is a UniqueViolation specifically on migration 061's
    chunks_document_id_chunk_index_key constraint -- matched on the
    constraint name, not just the exception class, so an unrelated unique
    violation (present or future) is never mistaken for this one expected,
    benign case."""
    return (
        isinstance(exc, psycopg2.errors.UniqueViolation)
        and getattr(exc.diag, "constraint_name", None) == "chunks_document_id_chunk_index_key"
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Rhemata Precept Austin Word Study Ingestion")
    parser.add_argument("--dry-run", action="store_true",
                         help="Preview parsed metadata and chunk content — no DB reads or writes")
    parser.add_argument("--source-dir", type=str, default=None,
                         help="Ingest .txt files from this directory instead of the default raw/ folder "
                              "— for isolated testing only")
    # parse_known_args: --language is already consumed above via raw
    # sys.argv scanning (unchanged from pre-conversion) -- ignore it here
    # rather than erroring on an "unrecognized" argument.
    args, _unknown = parser.parse_known_args()

    print("Rhemata Precept Austin Word Study Ingestion ({})".format(_lang))
    print("=" * 60)

    index_lookup = load_index()
    print("Loaded {} entries from index.json".format(len(index_lookup)))

    if args.source_dir:
        scan_dir = Path(args.source_dir)
        if not scan_dir.is_dir():
            print(f"ERROR: {scan_dir} is not a directory")
            sys.exit(1)
    else:
        scan_dir = RAW_DIR
    print("Source dir: {}".format(scan_dir))

    txt_files = sorted(scan_dir.glob("*.txt"))
    if not txt_files:
        print("No .txt files found in {}".format(scan_dir))
        return

    label = "[DRY RUN] " if args.dry_run else ""
    print("{}Found {} word study files to ingest\n".format(label, len(txt_files)))

    processed = 0
    skipped_duplicate = 0
    skipped_other = 0
    duplicate_files = []  # type: List[str]

    for i, filepath in enumerate(txt_files):
        try:
            if ingest_file(filepath, index_lookup, dry_run=args.dry_run):
                processed += 1
            else:
                skipped_other += 1
        except psycopg2.errors.UniqueViolation as e:
            # Narrow catch: only the specific, expected, benign case (this
            # document's chunks are already present) is swallowed. Anything
            # else -- including a unique violation on a DIFFERENT constraint
            # -- re-raises and stops the run. See the guard block above.
            if not _is_chunk_index_collision(e):
                raise
            skipped_duplicate += 1
            duplicate_files.append(filepath.name)
            print("  SKIP {}: already ingested — chunks present ({})".format(
                filepath.name, e.diag.constraint_name
            ))

        if (i + 1) % 10 == 0:
            print("\n  Progress: {}/{} seen ({} processed, {} skipped-duplicate, {} skipped-other)\n".format(
                i + 1, len(txt_files), processed, skipped_duplicate, skipped_other
            ))

    print("\n" + "=" * 60)
    print("{}SUMMARY".format(label))
    print("  Total files seen:       {}".format(len(txt_files)))
    print("  Processed (real writes): {}".format(processed))
    print("  Skipped (already present — chunks exist): {}".format(skipped_duplicate))
    print("  Skipped (other — bad filename / empty file / excerpt already exists): {}".format(skipped_other))
    if duplicate_files:
        shown = duplicate_files[:20]
        suffix = "" if len(duplicate_files) <= 20 else ", showing first 20"
        print("  Skipped-duplicate files ({}{}):".format(len(duplicate_files), suffix))
        for name in shown:
            print("    • {}".format(name))
        if len(duplicate_files) > 20:
            print("    ... and {} more".format(len(duplicate_files) - 20))
    print("=" * 60)


if __name__ == "__main__":
    main()
