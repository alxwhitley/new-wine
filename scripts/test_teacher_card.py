#!/usr/bin/env python3
"""
SP4 teacher-card verification: curated-list join, per-teacher document
counts, and the match_teacher_chunks similarity floor's real-world validity.

Run from project root: python3 scripts/test_teacher_card.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from app.services.embeddings import embed_text

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

failures = []


def check(name, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}")
    if not condition:
        failures.append(name)


EXPECTED_NAMES = {
    "Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson",
    "Don Basham", "John Bevere", "Michael Brown", "Jack Deere",
    "Oswald J. Smith",
}

# --- Curated list join ---
result = db.table("teacher_profiles").select("source_id, sources(name)").execute()
rows = result.data or []
check("teacher_profiles has exactly 9 rows", len(rows) == 9)
actual_names = {r["sources"]["name"] for r in rows if r.get("sources")}
check("all 9 expected names present", actual_names == EXPECTED_NAMES)

# --- Bob Mumford's document count matches the pre-build data fix (4 docs) ---
mumford_row = next((r for r in rows if r.get("sources", {}).get("name") == "Bob Mumford"), None)
check("Bob Mumford row found", mumford_row is not None)
if mumford_row:
    mumford_source_id = mumford_row["source_id"]
    docs_result = db.table("documents").select("id, title").eq("source_id", mumford_source_id).execute()
    mumford_docs = docs_result.data or []
    check("Bob Mumford has exactly 4 documents", len(mumford_docs) == 4)

    # --- match_teacher_chunks: on-topic query should surface real content ---
    on_topic_embedding = embed_text("What does Bob Mumford teach about the Kingdom of God?")
    doc_ids = [d["id"] for d in mumford_docs]
    on_topic_result = db.rpc("match_teacher_chunks", {
        "query_embedding": on_topic_embedding,
        "match_count": 15,
        "document_ids": doc_ids,
    }).execute()
    on_topic_chunks = on_topic_result.data or []
    check("on-topic query returns at least 1 chunk", len(on_topic_chunks) > 0)
    on_topic_scores = [c["similarity"] for c in on_topic_chunks]
    if on_topic_scores:
        check(
            f"best on-topic similarity ({max(on_topic_scores):.3f}) clears the 0.3 floor",
            max(on_topic_scores) >= 0.3,
        )

    # --- match_teacher_chunks: off-topic query should NOT clear the floor ---
    off_topic_embedding = embed_text("How do I fix my car's transmission?")
    off_topic_result = db.rpc("match_teacher_chunks", {
        "query_embedding": off_topic_embedding,
        "match_count": 15,
        "document_ids": doc_ids,
    }).execute()
    off_topic_chunks = off_topic_result.data or []
    off_topic_scores = [c["similarity"] for c in off_topic_chunks]
    # match_teacher_chunks itself has no floor -- it will still return rows.
    # What this checks is whether the ENDPOINT's 0.3 floor would correctly
    # exclude them all -- if this fails, 0.3 is the wrong value for this
    # corpus and TEACHER_POSITION_SIMILARITY_FLOOR needs adjusting before
    # this plan is considered done, not after.
    check(
        f"off-topic query's best score ({max(off_topic_scores) if off_topic_scores else 0:.3f}) stays below the 0.3 floor",
        not off_topic_scores or max(off_topic_scores) < 0.3,
    )

print(f"\n{'ALL PASSED' if not failures else f'{len(failures)} FAILURE(S): ' + ', '.join(failures)}")
if failures:
    sys.exit(1)
