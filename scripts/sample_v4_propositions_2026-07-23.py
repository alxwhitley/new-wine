#!/usr/bin/env python3
"""
sample_v4_propositions_2026-07-23.py — one-shot sample checkpoint.

Runs the v4 proposition-extraction prompt (propositions.py::EXTRACTION_PROMPT_V4)
against a hand-picked sample of 15 documents across 5 teachers who currently have
ZERO propositions, to stress-test the re-tuned prompt across voices before any
full backfill decision. Writes real rows to the real `propositions` table via
the same store_propositions() every ingest script uses -- this is a sample of
WHERE it runs, not a different, lesser code path.

Throwaway / standalone: does not touch ingest.py, shared_ingest.py,
propositions.py, or the propositions table schema. Not meant to be reused for
the eventual full backfill (#17) -- that will be its own script per this
project's standing session rules (dry-run + reconciliation, its own commit).

Usage:
    python3 scripts/sample_v4_propositions_2026-07-23.py            # run for real
    python3 scripts/sample_v4_propositions_2026-07-23.py --dry-run  # resolve + print text lengths, no Groq call, no writes
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services.embeddings import embed_text  # noqa: E402
import propositions  # noqa: E402

_parsed = urlparse(os.environ["SUPABASE_DB_URL"])
DB_PARAMS = {
    "host": _parsed.hostname,
    "port": _parsed.port or 5432,
    "user": unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname": _parsed.path.lstrip("/"),
}

# Hand-picked per the session brief: 5 teachers, stylistically distinct from
# each other and from Ravenhill (already validated separately), 2-3 docs each
# pulled from different points in each teacher's corpus -- not the shortest/
# easiest items. All confirmed via diagnostic query to currently have ZERO
# propositions anywhere in their corpus (source-level, not just these docs).
SAMPLE = [
    # Derek Prince -- systematic/doctrinal Bible teacher. 495-doc corpus;
    # spread across an early deliverance sermon, a mid-corpus expository
    # chapter study, and a later practical/financial teaching.
    {
        "teacher": "Derek Prince",
        "source_id": "17be391b-d025-4178-8543-3e84da675c5d",
        "document_id": "e2c25797-4e70-460e-accd-1f61acdc5816",
        "title": "Deliverance And Demonology",
    },
    {
        "teacher": "Derek Prince",
        "source_id": "17be391b-d025-4178-8543-3e84da675c5d",
        "document_id": "66857430-d245-47fb-8e75-3a2804b03128",
        "title": "Analysis of Hebrews: Chapter 5",
    },
    {
        "teacher": "Derek Prince",
        "source_id": "17be391b-d025-4178-8543-3e84da675c5d",
        "document_id": "59952e8f-ee8b-4332-adbb-4f0b334dae27",
        "title": "The Christian And His Money",
    },
    # Daniel Kolenda -- polemical evangelist, an 11-part "Cessationism" attack
    # series. Sampled opening / middle / near-end of the series arc.
    {
        "teacher": "Daniel Kolenda",
        "source_id": "656d6590-de62-4c8e-8c84-7587545582c9",
        "document_id": "db3104d5-c86f-4b4c-96ff-b1b4368476a1",
        "title": "The Heresy of Cessationism 1 (The Scriptures)",
    },
    {
        "teacher": "Daniel Kolenda",
        "source_id": "656d6590-de62-4c8e-8c84-7587545582c9",
        "document_id": "a93d2ec2-e75d-427d-b47a-6ad08e86eeec",
        "title": "Cessationism 5 (Gifts of Healings)",
    },
    {
        "teacher": "Daniel Kolenda",
        "source_id": "656d6590-de62-4c8e-8c84-7587545582c9",
        "document_id": "ab12e068-c2cc-4842-a5c8-127a0b7dc523",
        "title": "Cessationism 10 (The Godfather)",
    },
    # Jack Deere -- testimonial/experiential charismatic teacher (former
    # cessationist). Personal testimony, direct teaching, and Q&A formats.
    {
        "teacher": "Jack Deere",
        "source_id": "8e23ab9f-5caa-4b9d-92d3-44af372234ea",
        "document_id": "2b70819e-2bba-4fd1-86b4-79108ee3cea0",
        "title": "Dr Jack Deere Shares About Encountering the Power, Presence & Love of God",
    },
    {
        "teacher": "Jack Deere",
        "source_id": "8e23ab9f-5caa-4b9d-92d3-44af372234ea",
        "document_id": "c702800e-6cf6-4b62-9c2b-eb6be1384001",
        "title": "Jack Deere -- Hearing God's Voice",
    },
    {
        "teacher": "Jack Deere",
        "source_id": "8e23ab9f-5caa-4b9d-92d3-44af372234ea",
        "document_id": "a15c878f-cd39-4593-951f-76fcde4ded04",
        "title": "Jack Deere -- Responding to Common Questions About Healing",
    },
    # Doug Kreighbaum -- written books/papers/manuals, not spoken transcripts.
    # A book, a paper, and (for internal contrast) his one sermon.
    {
        "teacher": "Doug Kreighbaum",
        "source_id": "f872b446-ce49-4b00-96c7-deb807b5a438",
        "document_id": "b419a622-2742-4f1b-a468-beabf51e9d4a",
        "title": "Ministry of God's Word: Speaking, Preaching and Teaching",
    },
    {
        "teacher": "Doug Kreighbaum",
        "source_id": "f872b446-ce49-4b00-96c7-deb807b5a438",
        "document_id": "f08b540c-2ad7-4254-a96a-56a6c98eec88",
        "title": "Leadership in the House of God",
    },
    {
        "teacher": "Doug Kreighbaum",
        "source_id": "f872b446-ce49-4b00-96c7-deb807b5a438",
        "document_id": "e0e7e95c-e04a-4397-b3dd-27d9706e16c5",
        "title": "Shepherding in God's House",
    },
    # Charles Simpson -- relational/covenant pastoral voice (shepherding
    # movement). Skips "Breaking of Bread" (2 chunks -- too thin to be
    # representative).
    {
        "teacher": "Charles Simpson",
        "source_id": "c39c4e62-59f3-4a51-9f86-6d1fbcdc6758",
        "document_id": "6d43fa49-6f07-4bd6-9686-eaa6494f94a2",
        "title": "A Holy Nation",
    },
    {
        "teacher": "Charles Simpson",
        "source_id": "c39c4e62-59f3-4a51-9f86-6d1fbcdc6758",
        "document_id": "978fa7c2-ee76-46b3-925d-3cd88c7fdcc5",
        "title": "Covenant Love",
    },
    {
        "teacher": "Charles Simpson",
        "source_id": "c39c4e62-59f3-4a51-9f86-6d1fbcdc6758",
        "document_id": "5acfe936-8ae4-41f6-9662-97de43befa5e",
        "title": "The Birth Process",
    },
]


def fetch_doc_text(conn, doc_id: str) -> str:
    """Concatenate chunks in chunk_index order -- same convention already used
    by extract_bible_refs.py and the study.py router's fallback path."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (doc_id,),
        )
        return "\n\n".join(row[0] or "" for row in cur.fetchall())


def main():
    parser = argparse.ArgumentParser(description="Sample checkpoint: v4 propositions across 5 teachers")
    parser.add_argument("--dry-run", action="store_true", help="Resolve text only -- no Groq call, no writes")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)

    print(f"\n{'═' * 72}")
    print(f"v4 PROPOSITIONS SAMPLE — {len(SAMPLE)} documents / {len({s['teacher'] for s in SAMPLE})} teachers")
    print(f"{'═' * 72}")

    results = []
    for item in SAMPLE:
        teacher, doc_id, title = item["teacher"], item["document_id"], item["title"]
        print(f"\n── {teacher} — {title[:70]}")
        print(f"   doc_id={doc_id}")

        text = fetch_doc_text(conn, doc_id)
        word_count = len(text.split())
        print(f"   source text: {word_count} words")

        if args.dry_run:
            results.append({"teacher": teacher, "title": title, "doc_id": doc_id, "status": "dry-run"})
            continue

        try:
            props = propositions.extract_propositions(
                text, doc_id=doc_id, speaker=teacher, prompt_version="v4"
            )
        except propositions.PropositionExtractionFailed as exc:
            print(f"   ⛔ EXTRACTION FAILED: {exc}")
            results.append({"teacher": teacher, "title": title, "doc_id": doc_id, "status": "error", "error": str(exc)})
            continue

        if not props:
            print("   (no propositions extracted)")
            results.append({"teacher": teacher, "title": title, "doc_id": doc_id, "status": "empty"})
            continue

        count = propositions.store_propositions(conn, doc_id, props, embed_text)
        lengths = [len(p["content"].split()) for p in props]
        print(f"   stored {count} propositions — word counts: {lengths}")
        for p in props:
            preview = p["content"][:200].replace("\n", " ")
            print(f"     [{p['proposition_index']}] {preview}...")

        results.append({
            "teacher": teacher, "title": title, "doc_id": doc_id,
            "status": "stored", "count": count, "lengths": lengths,
        })

    conn.close()

    print(f"\n{'═' * 72}")
    print("RECONCILIATION")
    print(f"{'═' * 72}")
    stored = [r for r in results if r["status"] == "stored"]
    print(f"  Documents attempted : {len(results)}")
    print(f"  Stored              : {len(stored)}")
    print(f"  Empty               : {sum(1 for r in results if r['status'] == 'empty')}")
    print(f"  Errored             : {sum(1 for r in results if r['status'] == 'error')}")
    print(f"  Total propositions written : {sum(r.get('count', 0) for r in stored)}")
    print(f"  Teachers covered    : {sorted({r['teacher'] for r in results})}")


if __name__ == "__main__":
    main()
