#!/usr/bin/env python3
"""
test_propositions_reference_grounding.py — proof that the always-on
reference-grounding fix (PLAN.md #45, 2026-07-28) actually fires INSIDE
extract_propositions() itself, not merely that the predicate module works
in isolation (see test_reference_grounding_unit_proof.py for that). Per
CLAUDE.md: "verify by grepping/testing the real call site -- comments and
docstrings lie."

MOCKED Groq client -- NO real API call anywhere in this file, generation
stays stopped. os.environ["GROQ_API_KEY"] is never read because
propositions._get_groq is monkeypatched out entirely before
extract_propositions() runs; the Groq SDK's real HTTP client is never
constructed.

Source text is REAL, reconstructed via one bulk SELECT from the Ravenhill
document's chunks (same document as test_reference_grounding_unit_proof.py)
-- only the model's MOCKED response content (the two proposition dicts) is
hand-constructed, since there's no other way to control which reference is
genuine vs. fabricated in a "model output" without a real Groq call.

Run: python3 scripts/test_propositions_reference_grounding.py
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propositions as pm  # noqa: E402

RAVENHILL_DOC_ID = "c19ad18c-ea97-4841-8fa0-e60afc273521"


def _db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _reconstruct_document_text(db_params: dict, document_id: str) -> str:
    """ONE bulk SELECT of every chunk for document_id, ordered by
    chunk_index -- not a per-chunk query (N+1 lesson)."""
    import psycopg2

    conn = psycopg2.connect(**db_params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"No chunks found for document_id={document_id!r} -- check the id.")
    return "\n".join(r[0] for r in rows)


# ── Fake Groq client (no network, no API key ever read) ────────────────────

class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, raw_json: str):
        self._raw_json = raw_json
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return _FakeResponse(self._raw_json)


class _FakeChat:
    def __init__(self, raw_json: str):
        self.completions = _FakeCompletions(raw_json)


class _FakeGroqClient:
    def __init__(self, raw_json: str):
        self.chat = _FakeChat(raw_json)


def main() -> None:
    print("=" * 78)
    print("test_propositions_reference_grounding.py")
    print("=" * 78)

    db_params = _db_params()
    source_text = _reconstruct_document_text(db_params, RAVENHILL_DOC_ID)
    print(f"\nReconstructed Ravenhill source text: {len(source_text)} chars")

    grounded_content = (
        "Ravenhill grounds this exhortation about suffering and purpose "
        "explicitly in Romans 8:28, tying it to God's larger design."
    )
    fabricated_content = (
        "Ravenhill also urges believers to dwell often on Philippians 4:8-9 "
        "in their daily walk."
    )
    mock_response_json = json.dumps([
        {"proposition_index": 1, "content": grounded_content},
        {"proposition_index": 2, "content": fabricated_content},
    ])

    fake_client = _FakeGroqClient(mock_response_json)

    # Point the review-file constants at a scratch path so this run never
    # touches (or is contaminated by) the real reference_grounding_review/
    # directory.
    scratch_dir = Path(
        "/private/tmp/claude-501/-Users-alexwhitley-rhemata/"
        "947652e0-7a9a-4bf5-9c8c-badd1f72dc29/scratchpad"
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_review_path = scratch_dir / "test_grounding_review.jsonl"
    if scratch_review_path.exists():
        scratch_review_path.unlink()

    original_get_groq = pm._get_groq
    original_review_dir = pm.GROUNDING_REVIEW_DIR
    original_review_path = pm.GROUNDING_REVIEW_PATH
    pm._get_groq = lambda: fake_client
    pm.GROUNDING_REVIEW_DIR = scratch_dir
    pm.GROUNDING_REVIEW_PATH = scratch_review_path

    try:
        result = pm.extract_propositions(source_text, doc_id=RAVENHILL_DOC_ID)
    finally:
        pm._get_groq = original_get_groq
        pm.GROUNDING_REVIEW_DIR = original_review_dir
        pm.GROUNDING_REVIEW_PATH = original_review_path

    print(f"\nMocked Groq .create() call count: {fake_client.chat.completions.calls}")
    assert fake_client.chat.completions.calls == 1, "expected exactly one mocked model call"

    print("\n--- extract_propositions() result ---")
    for prop in result:
        print(f"  [{prop['proposition_index']}] {prop['content']!r}")

    # ── Proof 1: no proposition dropped -- same count, same indices. ───────
    assert len(result) == 2, f"expected 2 propositions returned, got {len(result)}"
    by_index = {p["proposition_index"]: p for p in result}
    assert set(by_index.keys()) == {1, 2}

    # ── Proof 2: the GROUNDED reference (Romans 8:28, genuinely printed in
    #    Ravenhill's source) survives byte-identical. ───────────────────────
    assert by_index[1]["content"] == grounded_content, (
        "grounded reference's proposition content must be untouched"
    )

    # ── Proof 3: the FABRICATED reference is stripped from `content`, but
    #    the proposition itself is still present (not dropped), and the
    #    surrounding text survives (minus the removed span + seam cleanup). ─
    stripped_content = by_index[2]["content"]
    assert "Philippians 4:8-9" not in stripped_content, (
        "fabricated reference must be stripped from content"
    )
    expected_stripped = (
        "Ravenhill also urges believers to dwell often on in their daily walk."
    )
    assert stripped_content == expected_stripped, (
        f"expected {expected_stripped!r}, got {stripped_content!r}"
    )

    # ── Proof 4: the strip was logged to the review file with correct
    #    provenance (document_id, proposition_index, the stripped
    #    reference, a reason). ───────────────────────────────────────────
    assert scratch_review_path.exists(), "expected the grounding review file to have been written"
    review_lines = [
        json.loads(line) for line in scratch_review_path.read_text().splitlines() if line.strip()
    ]
    print(f"\n--- Grounding review-file records ({len(review_lines)}) ---")
    for rec in review_lines:
        print(f"  {rec}")
    assert len(review_lines) == 1, f"expected exactly 1 review record, got {len(review_lines)}"
    rec = review_lines[0]
    assert rec["document_id"] == RAVENHILL_DOC_ID
    assert rec["proposition_index"] == 2
    assert rec["reference"] == "Philippians 4:8-9"
    assert rec["reason"] in ("fabricated", "uncertain")

    print("\n" + "=" * 78)
    print("All assertions passed -- grounding fires INSIDE extract_propositions() itself.")
    print("=" * 78)


if __name__ == "__main__":
    main()
