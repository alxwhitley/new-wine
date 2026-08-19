#!/usr/bin/env python3
"""
PLAN.md W7 second bullet -- legacy quote audit.

Read-only. Connects ONLY via backend/app/.env.readonly-analysis
(READONLY_ANALYSIS_DB_URL, rhemata_readonly_analysis role) for every SELECT.
Makes real OpenAI embedding calls (small, single-pass, reported below) but
never writes to any table -- no status change, no delete, no new row.

Every existing approved/pending quote is treated as untrusted legacy data
(CLAUDE.md quote-containment Landmines entry): quotes.topic is typically the
source DOCUMENT's own first topic_tags entry, not anything specific to the
individual quoted passage (see quotes.py's QUOTE_PASSAGE_SIMILARITY_THRESHOLD
module comment) -- so a quote's CURRENT topic label is not evidence the quote
actually supports that topic. This script re-scores every quote's own
quote_text against its own currently-assigned topic label, using exactly the
methodology already reviewed and shipped in
scripts/test_quote_passage_relevance.py's Part 2 (real-embedding evidence):
embed the topic string once, embed each quote's quote_text once, score
cosine_similarity(topic_vec, quote_vec), and compare against the real,
already-calibrated QUOTE_PASSAGE_SIMILARITY_THRESHOLD from quotes.py. A score
below threshold means: the OLD document-tag design would have made this quote
eligible for selection under any question resembling its topic label (every
quote sharing a topic scored identically under that design -- a pure tie, not
a relevance judgment); the NEW passage-level design would not.

This does not require or assume any particular past question -- it measures
whether a quote's own text actually supports the label already attached to
it, which is the only fixed piece of legacy metadata to audit against.

Single pass, no iteration against the corpus: one embedding call per unique
topic, one batched set of calls over every quote_text, using the same
embed_batch() the production code already uses.

Run from project root:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/audit_quote_legacy_relevance.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

from app.services import quotes  # noqa: E402  (needs sys.path set first)
from app.services import embeddings as embeddings_module  # noqa: E402

READONLY_ENV_PATH = PROJECT_ROOT / "backend" / "app" / ".env.readonly-analysis"
ROLE_NAME = "rhemata_readonly_analysis"
OUT_PATH = PROJECT_ROOT / "docs" / "audits" / "quote_legacy_relevance_audit_2026-08-18.md"

# OpenAI text-embedding-3-small pricing, as already documented in
# docs/audits/per_answer_cost_measurement_2026-08-03.md.
PRICE_PER_MTOK_USD = 0.02
COST_CEILING_USD = 50.0


def connect_readonly():
    import psycopg2

    if not READONLY_ENV_PATH.exists():
        raise RuntimeError("Missing %s" % READONLY_ENV_PATH)
    url = None
    for line in READONLY_ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("READONLY_ANALYSIS_DB_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url or ROLE_NAME not in url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL missing or not the analysis role")
    p = urlparse(url)
    user = unquote(p.username or "")
    if ROLE_NAME not in user:
        raise RuntimeError("Username is not the read-only analysis role: %r" % user)
    conn = psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=user,
        password=unquote(p.password or ""),
        dbname=(p.path or "/postgres").lstrip("/") or "postgres",
        connect_timeout=20,
    )
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT current_user")
    cu = cur.fetchone()[0]
    if ROLE_NAME not in cu:
        conn.close()
        raise RuntimeError("Connected as %r, expected %r" % (cu, ROLE_NAME))
    print("Connected read-only as %s" % cu)
    cur.close()
    return conn


def fetch_scope(conn):
    """Every approved/pending quote plus enough joined context (teacher,
    document title, source_kind) to report concentration. Revoked quotes are
    out of scope -- they are not currently servable under any design."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          q.id, q.quote_text, q.topic, q.teacher_source_id, q.status,
          q.created_at, d.id AS document_id, d.title AS document_title
        FROM quotes q
        JOIN quote_source_revisions sr ON sr.id = q.source_revision_id
        JOIN chunks c ON c.id = sr.chunk_id
        JOIN documents d ON d.id = c.document_id
        WHERE q.status IN ('approved', 'pending')
        ORDER BY q.id
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    cur.close()
    return rows


def estimate_tokens(char_count: int) -> int:
    # Same rough char/4 heuristic already used informally elsewhere in this
    # repo's cost estimates; conservative (rounds up).
    return (char_count // 4) + 1


def main() -> int:
    conn = connect_readonly()
    try:
        rows = fetch_scope(conn)
    finally:
        conn.close()

    total_quotes = len(rows)
    unique_topics = sorted({r["topic"] for r in rows})
    topic_char_total = sum(len(t) for t in unique_topics)
    quote_char_total = sum(len(r["quote_text"]) for r in rows)

    topic_tokens = estimate_tokens(topic_char_total)
    quote_tokens = estimate_tokens(quote_char_total)
    total_tokens = topic_tokens + quote_tokens
    est_cost_usd = (total_tokens / 1_000_000.0) * PRICE_PER_MTOK_USD

    embed_calls = (
        (len(unique_topics) + embeddings_module.EMBED_BATCH_SIZE - 1) // embeddings_module.EMBED_BATCH_SIZE
        + (total_quotes + embeddings_module.EMBED_BATCH_SIZE - 1) // embeddings_module.EMBED_BATCH_SIZE
    )

    print("=" * 70)
    print("SCOPE / COST ESTIMATE (before any embedding call)")
    print("=" * 70)
    print("Quotes in scope (approved + pending): %d" % total_quotes)
    print("Distinct topic labels among them:     %d" % len(unique_topics))
    print("Estimated embedding tokens:            %d (topics %d + quotes %d)" % (
        total_tokens, topic_tokens, quote_tokens))
    print("Estimated OpenAI API calls:            %d (batched at %d texts/call)" % (
        embed_calls, embeddings_module.EMBED_BATCH_SIZE))
    print("Estimated cost @ $%.2f/MTok:            $%.4f" % (PRICE_PER_MTOK_USD, est_cost_usd))
    print("Hard ceiling:                          $%.2f" % COST_CEILING_USD)

    if est_cost_usd > COST_CEILING_USD:
        print("\nESTIMATE EXCEEDS CEILING -- stopping without making any embedding call.")
        return 1

    print("\nEstimate is well under the ceiling -- proceeding with a single pass.\n")

    # ── Single pass: one embedding per unique topic, one batch over all quote_texts ──
    topic_vecs = dict(zip(unique_topics, quotes.embed_batch(unique_topics)))
    quote_vecs = quotes.embed_batch([r["quote_text"] for r in rows])

    threshold = quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD
    teacher_names = quotes.CONFIRMED_TEACHER_SOURCE_IDS

    scored = []
    for row, qvec in zip(rows, quote_vecs):
        tvec = topic_vecs[row["topic"]]
        score = quotes.cosine_similarity(tvec, qvec)
        scored.append({**row, "score": score, "affected": score < threshold})

    affected = [r for r in scored if r["affected"]]
    scored_sorted = sorted(scored, key=lambda r: (r["score"], r["id"]))

    # Concentration by TOPIC -- the direct evidence of the document-tag-
    # inheritance defect: how many distinct documents share one topic label.
    by_topic = defaultdict(lambda: {"total": 0, "affected": 0, "documents": set()})
    for r in scored:
        t = by_topic[r["topic"]]
        t["total"] += 1
        t["affected"] += 1 if r["affected"] else 0
        t["documents"].add(r["document_id"])

    # Concentration by source document.
    by_doc = defaultdict(lambda: {"total": 0, "affected": 0, "topics": set(), "teacher": None, "title": None})
    for r in scored:
        d = by_doc[r["document_id"]]
        d["total"] += 1
        d["affected"] += 1 if r["affected"] else 0
        d["topics"].add(r["topic"])
        d["teacher"] = teacher_names.get(r["teacher_source_id"], r["teacher_source_id"])
        d["title"] = r["document_title"]

    # Concentration by teacher.
    by_teacher = defaultdict(lambda: {"total": 0, "affected": 0, "documents": set(), "topics": set()})
    for r in scored:
        t = by_teacher[teacher_names.get(r["teacher_source_id"], r["teacher_source_id"])]
        t["total"] += 1
        t["affected"] += 1 if r["affected"] else 0
        t["documents"].add(r["document_id"])
        t["topics"].add(r["topic"])

    # ── Write report ──
    L = []
    A = L.append
    A("# Legacy quote relevance audit — approved/pending quotes vs. current passage-level logic")
    A("")
    A("Generated %s. Read-only, `rhemata_readonly_analysis` role only. No row" % (
        datetime.now(timezone.utc).strftime("%Y-%m-%d")))
    A("was flagged, revoked, or modified by this script — this report is the")
    A("deliverable; what to do about the affected rows is Alex's call.")
    A("")
    A("Methodology: every approved/pending quote is scored against its OWN")
    A("currently-assigned `topic` label using the exact passage-level logic")
    A("`select_quotes_for_answer()` uses in production today (commit `82ec0f5`) —")
    A("`cosine_similarity(embed(topic), embed(quote_text))` against the real,")
    A("already-calibrated `QUOTE_PASSAGE_SIMILARITY_THRESHOLD = %.2f`. A quote's" % threshold)
    A("topic label is the only fixed piece of legacy metadata there is to audit")
    A("against; under the OLD (retired) design every quote sharing a topic label")
    A("scored an identical, meaningless tie for any question resembling that")
    A("label, so a score below threshold here means: the OLD design would have")
    A("made this quote eligible to be served on that topic; the CURRENT design")
    A("would not.")
    A("")
    A("## Scope and cost")
    A("")
    A("- Quotes audited: **%d** (%d approved, %d pending; revoked excluded)" % (
        total_quotes,
        sum(1 for r in rows if r["status"] == "approved"),
        sum(1 for r in rows if r["status"] == "pending"),
    ))
    A("- Distinct topic labels: **%d**" % len(unique_topics))
    A("- Embedding calls made: %d (batched, single pass)" % embed_calls)
    A("- Estimated cost: $%.4f (ceiling was $%.2f)" % (est_cost_usd, COST_CEILING_USD))
    A("")
    A("## Headline finding")
    A("")
    A("**%d of %d quotes in scope (%.1f%%) score below the current relevance" % (
        len(affected), total_quotes, 100.0 * len(affected) / total_quotes if total_quotes else 0.0))
    A("threshold against their own topic label** — meaning the old document-tag")
    A("design would have made all %d eligible for selection on that topic; the" % len(affected))
    A("current passage-level design would reject every one of them.")
    A("")
    A("## Worst offenders (lowest relevance to their own topic label)")
    A("")
    A("Top 30 by ascending score — least-supported quotes first.")
    A("")
    A("| score | teacher | topic | document | quote_text (truncated) |")
    A("|---|---|---|---|---|")
    for r in scored_sorted[:30]:
        teacher = teacher_names.get(r["teacher_source_id"], r["teacher_source_id"])
        text = r["quote_text"].replace("|", "/").replace("\n", " ")
        if len(text) > 90:
            text = text[:87] + "..."
        topic = r["topic"].replace("|", "/")
        title = (r["document_title"] or "").replace("|", "/")
        A("| %.4f | %s | %s | %s | %s |" % (r["score"], teacher, topic, title, text))
    A("")
    A("## Concentration by topic (the direct evidence of the defect)")
    A("")
    A("The document-tag-inheritance defect means one topic label gets stamped")
    A("onto every quote pulled from a given document — so the real signature of")
    A("the defect is how many DIFFERENT documents share one topic label, not")
    A("how many quotes any single document contributes. Sorted by distinct")
    A("documents sharing the label, descending.")
    A("")
    A("| topic | quotes | affected | distinct documents sharing this label |")
    A("|---|---|---|---|")
    topic_rows = sorted(by_topic.items(), key=lambda kv: (-len(kv[1]["documents"]), -kv[1]["affected"]))
    for topic, t in topic_rows:
        if len(t["documents"]) < 2:
            continue
        A("| %s | %d | %d | %d |" % (topic.replace("|", "/"), t["total"], t["affected"], len(t["documents"])))
    single_doc_topics = [t for t in by_topic.values() if len(t["documents"]) < 2]
    A("")
    A("%d additional topic labels are used by only one document each (not shown — no" % len(single_doc_topics))
    A("cross-document tag-sharing to report for those)." )
    A("")
    A("## Concentration by source document")
    A("")
    A("Top 25 documents by number of affected (below-threshold) quotes contributed.")
    A("")
    A("| document | teacher | quotes | affected | topics used |")
    A("|---|---|---|---|---|")
    doc_rows = sorted(by_doc.items(), key=lambda kv: -kv[1]["affected"])
    shown_docs = [(doc_id, d) for doc_id, d in doc_rows if d["affected"] > 0][:25]
    for doc_id, d in shown_docs:
        A("| %s | %s | %d | %d | %d |" % (
            (d["title"] or str(doc_id)).replace("|", "/"), d["teacher"], d["total"], d["affected"], len(d["topics"])))
    remaining_docs = [d for _, d in doc_rows if d["affected"] > 0][25:]
    remaining_single = sum(1 for d in remaining_docs if d["affected"] == 1)
    A("")
    A("%d further documents each contribute affected quotes not shown above (%d of" % (
        len(remaining_docs), remaining_single))
    A("those contribute exactly 1 affected quote each) — %d distinct documents contain" % (
        len(by_doc)))
    A("at least one affected quote in total, out of %d distinct documents in scope." % len(by_doc))
    A("")
    A("## Concentration by teacher")
    A("")
    A("| teacher | quotes | affected | distinct documents | distinct topics |")
    A("|---|---|---|---|---|")
    for teacher, t in sorted(by_teacher.items(), key=lambda kv: -kv[1]["affected"]):
        A("| %s | %d | %d | %d | %d |" % (
            teacher, t["total"], t["affected"], len(t["documents"]), len(t["topics"])))
    A("")
    A("## What this does and does not show")
    A("")
    A("- This measures a quote's text against the topic label ALREADY attached")
    A("  to it, not against any real historical question — there is no stored")
    A("  question history to audit against. A quote scoring above threshold")
    A("  here is not thereby proven a good match for any real future question;")
    A("  it only means it is not a clear document-tag-inheritance false")
    A("  positive by this specific test.")
    A("- No row's status was changed. No revocation happened. Nothing here")
    A("  gates future quote selection — `QUOTE_SELECTION_ENABLED` is untouched")
    A("  and this script does not read or write it.")
    A("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("Wrote %s" % OUT_PATH)
    print("Affected: %d / %d (%.1f%%)" % (
        len(affected), total_quotes, 100.0 * len(affected) / total_quotes if total_quotes else 0.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
