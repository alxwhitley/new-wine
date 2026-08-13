#!/usr/bin/env python3
"""
Read-only analysis of QUOTE_TOPIC_SIMILARITY_THRESHOLD effects.

Reconstructs the quote-topic / question similarity scores that the live answer
path actually evaluated, using the same embedding model and cosine-similarity
implementation as production. Compares the current 0.40 threshold against lower
alternatives (0.35, 0.30, 0.25) and emits a markdown report.

No DB writes. No change to production behavior or to the threshold constant.

Run from repo root:
    python3 scripts/analyze_quote_threshold.py

Output:
    reports/quote_threshold_analysis_YYYYMMDD_HHMMSS.md
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Dict, List, Optional, Tuple

import psycopg2
from dotenv import load_dotenv

# Make the backend app importable so we reuse the exact embedding functions.
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "backend" / "app"))

from services.embeddings import cosine_similarity, embed_batch, embed_text  # noqa: E402

# Production constants at the time of analysis (kept inline so this script does
# not depend on the full quotes module import tree).
QUOTE_TOPIC_SIMILARITY_THRESHOLD = 0.40
MAX_QUOTES_PER_ANSWER = 3
TEST_THRESHOLDS = [0.40, 0.35, 0.30, 0.25]

REPORT_DIR = repo_root / "reports"


def get_db_url() -> str:
    load_dotenv(repo_root / "backend" / "app" / ".env")
    return os.environ["SUPABASE_DB_URL"]


def fetch_answered_jobs(cur) -> List[dict]:
    cur.execute(
        """
        SELECT id,
               question,
               quote_ids,
               retrieved_chunk_ids,
               outcome,
               finished_at
        FROM answer_jobs
        WHERE status = 'done'
          AND outcome = 'answered'
          AND question IS NOT NULL
          AND question <> ''
        ORDER BY finished_at
        """
    )
    cols = [desc[0] for desc in cur.description]
    rows = []
    for row in cur.fetchall():
        rows.append(dict(zip(cols, row)))
    return rows


def fetch_approved_quotes(cur) -> Dict[str, dict]:
    cur.execute(
        """
        SELECT q.id,
               q.topic,
               q.teacher_source_id,
               q.quote_text,
               s.name AS teacher_name
        FROM quotes q
        JOIN sources s ON s.id = q.teacher_source_id
        WHERE q.status = 'approved'
        """
    )
    quotes = {}
    for quote_id, topic, teacher_source_id, quote_text, teacher_name in cur.fetchall():
        quotes[quote_id] = {
            "id": quote_id,
            "topic": topic,
            "teacher_source_id": teacher_source_id,
            "quote_text": quote_text,
            "teacher_name": teacher_name,
        }
    return quotes


def fetch_considered_teachers(cur, chunk_ids: List[str]) -> set:
    """Return the set of source_ids for documents that contributed chunks."""
    if not chunk_ids:
        return set()
    placeholders = ",".join(["%s"] * len(chunk_ids))
    cur.execute(
        f"""
        SELECT DISTINCT d.source_id
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.id IN ({placeholders})
        """,
        tuple(chunk_ids),
    )
    return {row[0] for row in cur.fetchall() if row[0]}


def embed_all(items: List[str]) -> List[List[float]]:
    """Embed unique texts; returned in input order."""
    if not items:
        return []
    return embed_batch(items)


def select_at_threshold(
    scored: List[Tuple[float, str]], threshold: float, max_n: int
) -> List[str]:
    """Mirror of select_quotes_for_answer's selection logic."""
    qualified = [quote_id for score, quote_id in scored if score >= threshold]
    return qualified[:max_n]


def build_report(
    jobs: List[dict],
    quotes: Dict[str, dict],
    question_embeddings: Dict[str, List[float]],
    topic_embeddings: Dict[str, List[float]],
) -> str:
    # Pair-level scoring, restricted to quotes whose teacher was considered.
    pairs: List[dict] = []
    by_job: Dict[str, List[dict]] = defaultdict(list)
    for job in jobs:
        question = job["question"]
        served_ids = set(job["quote_ids"] or [])
        chunk_ids = job["retrieved_chunk_ids"] or []
        considered_teachers = job.get("_considered_teachers", set())

        for quote_id, quote in quotes.items():
            if quote["teacher_source_id"] not in considered_teachers:
                continue
            q_vec = question_embeddings[question]
            t_vec = topic_embeddings[quote["topic"]]
            score = cosine_similarity(q_vec, t_vec)
            pair = {
                "job_id": job["id"],
                "question": question,
                "quote_id": quote_id,
                "topic": quote["topic"],
                "quote_text": quote["quote_text"],
                "teacher_name": quote["teacher_name"],
                "score": score,
                "served": quote_id in served_ids,
            }
            pairs.append(pair)
            by_job[job["id"]].append(pair)

    # Sort each job's candidates by score descending, mirroring production.
    for job_id in by_job:
        by_job[job_id].sort(key=lambda x: x["score"], reverse=True)

    # Aggregate statistics.
    served_scores = [p["score"] for p in pairs if p["served"]]
    rejected_scores = [p["score"] for p in pairs if not p["served"]]

    def stats(scores: List[float]) -> dict:
        if not scores:
            return {"count": 0, "min": None, "max": None, "mean": None, "median": None}
        return {
            "count": len(scores),
            "min": min(scores),
            "max": max(scores),
            "mean": mean(scores),
            "median": median(scores),
        }

    served_stats = stats(served_scores)
    rejected_stats = stats(rejected_scores)

    # Threshold comparison: run the selector per job.
    job_selections: Dict[float, Dict[str, List[str]]] = {}
    for threshold in TEST_THRESHOLDS:
        job_selections[threshold] = {}
        for job_id, candidates in by_job.items():
            selected_ids = select_at_threshold(
                [(c["score"], c["quote_id"]) for c in candidates],
                threshold,
                MAX_QUOTES_PER_ANSWER,
            )
            job_selections[threshold][job_id] = selected_ids

    baseline_job_ids_with_quotes: set = set()
    for job_id, selected_ids in job_selections[QUOTE_TOPIC_SIMILARITY_THRESHOLD].items():
        if selected_ids:
            baseline_job_ids_with_quotes.add(job_id)

    threshold_rows: List[dict] = []
    for threshold in TEST_THRESHOLDS:
        selected_pairs: List[dict] = []
        selected_job_ids: set = set()
        for job_id, selected_ids in job_selections[threshold].items():
            if not selected_ids:
                continue
            selected_job_ids.add(job_id)
            for c in by_job[job_id]:
                if c["quote_id"] in selected_ids:
                    selected_pairs.append({**c, "threshold": threshold})

        newly_selected_pairs = []
        newly_selected_job_ids: set = set()
        if threshold != QUOTE_TOPIC_SIMILARITY_THRESHOLD:
            baseline_ids = job_selections[QUOTE_TOPIC_SIMILARITY_THRESHOLD]
            for job_id, selected_ids in job_selections[threshold].items():
                baseline_for_job = set(baseline_ids.get(job_id, []))
                new_ids = set(selected_ids) - baseline_for_job
                if new_ids:
                    if not baseline_for_job:
                        newly_selected_job_ids.add(job_id)
                    for c in by_job[job_id]:
                        if c["quote_id"] in new_ids:
                            newly_selected_pairs.append(c)

        threshold_rows.append(
            {
                "threshold": threshold,
                "pair_count": len(selected_pairs),
                "job_count": len(selected_job_ids),
                "newly_selected_pairs": newly_selected_pairs,
                "newly_selected_job_count": len(newly_selected_job_ids),
            }
        )

    # Jobs where the selector would have picked something but production served nothing.
    qualifying_but_empty = []
    for job in jobs:
        job_id = job["id"]
        selected_at_40 = job_selections[QUOTE_TOPIC_SIMILARITY_THRESHOLD].get(job_id, [])
        if selected_at_40 and not job["quote_ids"]:
            best = by_job[job_id][0]["score"] if by_job[job_id] else None
            qualifying_but_empty.append(
                {"job_id": job_id, "question": job["question"], "count": len(selected_at_40), "best_score": best}
            )

    # Build markdown.
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: List[str] = [
        "# Quote-Topic Similarity Threshold Analysis",
        "",
        f"Generated: {now}",
        f"Script: `scripts/analyze_quote_threshold.py`",
        "",
        "## Scope and method",
        "",
        "This report reconstructs the similarity scores the live answer path used",
        "to decide which approved quotes to attach to served answers. It is",
        "**read-only**: no database writes, no change to `QUOTE_TOPIC_SIMILARITY_THRESHOLD`,",
        "and no change to production quote-serving behavior.",
        "",
        "How the scores were produced:",
        "",
        "1. Pulled every `answer_jobs` row with `status = 'done'` and `outcome = 'answered'`",
        "   that has a non-empty question.",
        "2. Pulled every `quotes` row with `status = 'approved'`.",
        "3. For each answer, determined which teachers' material was actually retrieved",
        "   by resolving `retrieved_chunk_ids` -> `documents.source_id`. Only quotes from",
        "   those teachers were treated as candidates, matching `select_quotes_for_answer()`'s",
        "   `considered_teacher_source_ids` filter.",
        "4. Re-embedded each unique question and each quote topic with the production",
        "   model (`text-embedding-3-small`, 1536 dimensions) using the same",
        "   `app.services.embeddings.embed_text()` / `embed_batch()` functions.",
        "5. Computed cosine similarity with the shared `cosine_similarity()` function.",
        "6. Applied the same top-`MAX_QUOTES_PER_ANSWER` cap the selector uses, per job.",
        "",
        "Caveats:",
        "",
        "- The production selector logs only the IDs it returns, not every candidate score,",
        "  so this report recomputes rather than queries the raw scores. The embedding model",
        "  and math are identical to production.",
        "- `quote_verification_log` records quote *approval* decisions, not selection scores,",
        "  and is not used here.",
        "- Sample quality judgments at the end are plain-text commentary for a human reviewer;",
        "  they are not a model-based verdict.",
        "",
        "## Corpus snapshot",
        "",
        f"- Completed answered jobs analyzed: **{len(jobs)}**",
        f"- Distinct questions among those jobs: **{len({j['question'] for j in jobs})}**",
        f"- Approved quotes in corpus: **{len(quotes)}**",
        f"- Candidate (question, quote) pairs evaluated: **{len(pairs)}**",
        f"- Jobs that actually served at least one quote: **{len([j for j in jobs if j.get('quote_ids')])}**",
        "",
        "### Approved quotes",
        "",
        "| Quote ID | Teacher | Topic | Text |",
        "| --- | --- | --- | --- |",
    ]
    for quote in quotes.values():
        text = quote["quote_text"].replace("\n", " ")
        if len(text) > 120:
            text = text[:117] + "..."
        lines.append(
            f"| {quote['id']} | {quote['teacher_name']} | {quote['topic']} | {text} |"
        )

    lines.extend(
        [
            "",
            "## Distribution at the current 0.40 threshold",
            "",
            "Scores for candidate pairs that were **served** (present in `answer_jobs.quote_ids`)",
            "vs. **rejected** (candidate pairs that scored below 0.40, were pushed out by the",
            "top-3 cap, or were never evaluated because the selector returned no IDs for the job).",
            "",
            f"- Pairs served in production: **{served_stats['count']}**",
            f"- Pairs the selector algorithm would select at 0.40: **{len([p for p in pairs if p['score'] >= QUOTE_TOPIC_SIMILARITY_THRESHOLD])}**",
        ]
    )
    if qualifying_but_empty:
        lines.append(
            f"- Jobs with qualifying candidates but `quote_ids` is NULL/empty: **{len(qualifying_but_empty)}** "
            "(the producer's fail-soft wrapper likely caught an embedding/DB fault for these jobs; "
            "they appear as 'rejected' below because no quote was actually served)."
        )
        for item in qualifying_but_empty:
            q = item["question"].replace("\n", " ")
            if len(q) > 80:
                q = q[:77] + "..."
            lines.append(
                f"  - `{item['job_id']}` | best score {item['best_score']:.4f} | {q}"
            )
    else:
        lines.append("- Jobs with qualifying candidates but `quote_ids` is NULL/empty: **0**")

    lines.extend(
        [
            "",
            "| Group | Count | Min | Max | Mean | Median |",
            "| --- | --- | --- | --- | --- | --- |",
            f"| Served | {served_stats['count']} | {fmt(served_stats['min'])} | {fmt(served_stats['max'])} | {fmt(served_stats['mean'])} | {fmt(served_stats['median'])} |",
            f"| Rejected | {rejected_stats['count']} | {fmt(rejected_stats['min'])} | {fmt(rejected_stats['max'])} | {fmt(rejected_stats['mean'])} | {fmt(rejected_stats['median'])} |",
            "",
        ]
    )

    # Histogram buckets.
    buckets = [0.00, 0.10, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 1.00]
    lines.extend(
        [
            "### Score histogram (all candidate pairs)",
            "",
            "| Range | Count | Served | Rejected |",
            "| --- | --- | --- | --- |",
        ]
    )
    for i in range(len(buckets) - 1):
        lo, hi = buckets[i], buckets[i + 1]
        in_range = [p for p in pairs if lo <= p["score"] < hi]
        if hi == 1.00:
            in_range = [p for p in pairs if lo <= p["score"] <= hi]
        served_count = sum(1 for p in in_range if p["served"])
        lines.append(
            f"| {lo:.2f} - {hi:.2f} | {len(in_range)} | {served_count} | {len(in_range) - served_count} |"
        )

    lines.extend(
        [
            "",
            "## Threshold comparison",
            "",
            "Columns:",
            "",
            "- **Selected pairs**: total (question, quote) pairs that would be selected.",
            "- **Jobs with any quote**: distinct answered jobs receiving at least one quote.",
            "- **New pairs vs 0.40**: pairs that qualify at this threshold but not at 0.40.",
            "- **New jobs vs 0.40**: jobs that would receive a quote for the first time",
            "  at this threshold (i.e., they received none at 0.40 but would receive at least one here).",
            "",
            "| Threshold | Selected pairs | Jobs with any quote | New pairs vs 0.40 | New jobs vs 0.40 |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in threshold_rows:
        new_pairs_count = len(row["newly_selected_pairs"])
        new_jobs_count = row["newly_selected_job_count"]
        lines.append(
            f"| {row['threshold']:.2f} | {row['pair_count']} | {row['job_count']} | {new_pairs_count} | {new_jobs_count} |"
        )

    lines.extend(
        [
            "",
            "## Samples of newly qualifying pairs",
            "",
            "For each threshold below 0.40, every pair that newly qualifies is shown, because the",
            "corpus is small enough to review exhaustively. The 'Verdict' column is a plain-text",
            "first impression for human review, not a model-based label.",
            "",
        ]
    )

    for row in threshold_rows:
        if row["threshold"] == QUOTE_TOPIC_SIMILARITY_THRESHOLD:
            continue
        lines.append(f"### Threshold {row['threshold']:.2f}")
        lines.append("")
        if not row["newly_selected_pairs"]:
            lines.append("_No pairs newly qualify at this threshold._")
            lines.append("")
            continue

        lines.append(
            "| Score | Question | Topic | Teacher | Served at 0.40? | Verdict |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for p in sorted(
            row["newly_selected_pairs"], key=lambda x: x["score"], reverse=True
        ):
            verdict = human_verdict(p["question"], p["topic"])
            question = p["question"].replace("\n", " ")
            if len(question) > 80:
                question = question[:77] + "..."
            lines.append(
                f"| {p['score']:.4f} | {question} | {p['topic']} | {p['teacher_name']} | {'yes' if p['served'] else 'no'} | {verdict} |"
            )
        lines.append("")

    lines.extend(
        [
            "",
            "## Raw candidate pair scores",
            "",
            "Complete list of every (question, quote) candidate pair, sorted by score descending.",
            "Job IDs are shown so duplicate questions can be disambiguated.",
            "",
            "| Score | Job | Question | Topic | Teacher | Served at 0.40? |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for p in sorted(pairs, key=lambda x: x["score"], reverse=True):
        question = p["question"].replace("\n", " ")
        if len(question) > 80:
            question = question[:77] + "..."
        lines.append(
            f"| {p['score']:.4f} | `{p['job_id'][:8]}` | {question} | {p['topic']} | {p['teacher_name']} | {'yes' if p['served'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            "This report presents the evidence; it does **not** recommend a threshold value.",
            "The data above shows how many additional quotes would be served at each lower",
            "threshold and provides concrete question/topic pairs for human sanity-checking.",
            "",
        ]
    )

    return "\n".join(lines)


def fmt(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value:.4f}"


def human_verdict(question: str, topic: str) -> str:
    """Plain-text first impression for the sample table."""
    q = question.lower()
    t = topic.lower()
    if t in q or any(word in q for word in t.split()):
        return "looks like a direct topic match"
    if t == "fasting" and any(word in q for word in ["fast", "fasting", "food", "eat", "abstain"]):
        return "looks like a reasonable topic match"
    if t == "waiting on god" and any(
        word in q
        for word in ["wait", "waiting", "patience", "patient", "god's timing", "timing"]
    ):
        return "looks like a reasonable topic match"
    return "likely false positive"


def main() -> None:
    url = get_db_url()
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            jobs = fetch_answered_jobs(cur)
            quotes = fetch_approved_quotes(cur)

            # Resolve considered teachers for each job.
            for job in jobs:
                chunk_ids = job["retrieved_chunk_ids"] or []
                job["_considered_teachers"] = fetch_considered_teachers(cur, chunk_ids)

            # Deduplicate texts before embedding.
            unique_questions = sorted({job["question"] for job in jobs})
            unique_topics = sorted({q["topic"] for q in quotes.values()})

            question_embeddings = {
                text: vec for text, vec in zip(unique_questions, embed_all(unique_questions))
            }
            topic_embeddings = {
                text: vec for text, vec in zip(unique_topics, embed_all(unique_topics))
            }

        report = build_report(jobs, quotes, question_embeddings, topic_embeddings)

        REPORT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_path = REPORT_DIR / f"quote_threshold_analysis_{timestamp}.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"Report written to {report_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
