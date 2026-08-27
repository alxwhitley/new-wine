"""Post-answer-completion search-question classification and corpus-gap
bookkeeping.

Runs as a separate, retryable pass AFTER an answer_jobs row reaches
status='done' -- never inline in the answer path, so a classification
failure or slow LLM call can never affect the answer, its latency, or
retrieval/citations (CLAUDE.md: nothing here touches producer.py).

Classifies each DISTINCT job_id exactly once and fans the result out to
every search_occurrences row sharing that job -- two occurrences sharing
one single-flight-collapsed generation get the same topic/outcome, one
classifier call, not two.

Gap bookkeeping:
  - outcome == 'no_material' and origin == 'user' -> create ONE new gap
    row, storing the REDACTED question only.
  - an admin_retest occurrence's outcome (whatever it is) updates the
    EXISTING gap's retest_outcome instead of ever creating a second gap
    row -- a retest is never itself a fresh content gap.

Never reads or writes answer_jobs.answer/citations/verified_references --
only .status/.outcome/.question, and only via SELECT.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict

from .classifier import ClassificationFailedError, classify_topic as _default_classify
from .redaction import REDACTION_VERSION, redact_question as _default_redact


def finalize_ready_jobs(
    db,
    classify_fn: Callable = _default_classify,
    redact_fn: Callable = _default_redact,
    limit: int = 50,
) -> Dict[str, int]:
    """One finalization pass. Returns counts for observability/tests.
    `db.run(fn)` is called with an object exposing this module's expected
    query surface -- a real psycopg2 connection in production (wrapped by
    PostgresTables below), or a test double exposing the same shape."""

    counts = {
        "jobs_classified": 0,
        "occurrences_finalized": 0,
        "gaps_created": 0,
        "gaps_updated": 0,
        "failed": 0,
    }

    def _run(tables):
        job_ids = tables.pending_job_ids()[:limit]
        for job_id in job_ids:
            job = tables.answer_jobs.get(job_id)
            if not job:
                continue
            occurrences = tables.occurrences_for_job(job_id)
            if not occurrences:
                continue

            try:
                classification = classify_fn(job["question"] or "")
            except ClassificationFailedError:
                counts["failed"] += 1
                continue

            counts["jobs_classified"] += 1
            outcome = job.get("outcome")
            finalized_at = datetime.now(timezone.utc).isoformat()

            for occ in occurrences:
                occ["primary_topic"] = classification.topic
                occ["outcome"] = outcome
                occ["classification_status"] = "classified"
                occ["classifier_version"] = classification.prompt_version
                occ["classifier_model"] = classification.model
                occ["classifier_prompt_version"] = classification.prompt_version
                occ["classifier_confidence"] = classification.confidence
                occ["finalized_at"] = finalized_at
                counts["occurrences_finalized"] += 1

                if occ["origin"] == "admin_retest":
                    linked_gap = tables.gap_for_retest_occurrence(occ["id"])
                    if linked_gap is not None:
                        linked_gap["retest_outcome"] = outcome
                        counts["gaps_updated"] += 1
                    continue

                if outcome == "no_material":
                    existing_gap = tables.gap_for_occurrence(occ["id"])
                    if existing_gap is not None:
                        continue
                    redaction = redact_fn(job["question"] or "")
                    tables.create_gap(
                        occ["id"], redaction.text, redaction.status, REDACTION_VERSION,
                    )
                    counts["gaps_created"] += 1

    db.run(_run)
    return counts


class PostgresTables:
    """Real-connection adapter matching the duck-typed surface
    finalize_ready_jobs() expects, backed by direct SQL against a live
    psycopg2 connection (via async_answers.db.dict_cursor)."""

    def __init__(self, conn, limit: int = 50):
        self._conn = conn
        # 2026-08-27 privacy review, additional observation: this SQL-side
        # cap must match (or exceed) finalize_ready_jobs()'s own Python-side
        # `[:limit]` slice, or a caller passing a larger limit would
        # silently be under-served by a smaller hardcoded database LIMIT.
        self._limit = limit
        self.answer_jobs = _AnswerJobsView(conn)
        self.occurrences = _OccurrencesView(conn)

    def pending_job_ids(self):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "SELECT DISTINCT o.job_id FROM search_occurrences o "
                "JOIN answer_jobs j ON j.id = o.job_id "
                "WHERE o.classification_status = 'pending' AND j.status = 'done' "
                "LIMIT %s",
                (self._limit,),
            )
            return [r["job_id"] for r in cur.fetchall()]

    def occurrences_for_job(self, job_id):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "SELECT * FROM search_occurrences "
                "WHERE job_id = %s AND classification_status = 'pending'",
                (job_id,),
            )
            return [_MutableRow(self._conn, "search_occurrences", "id", dict(r)) for r in cur.fetchall()]

    def gap_for_occurrence(self, occurrence_id):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "SELECT * FROM search_gap_details WHERE occurrence_id = %s",
                (occurrence_id,),
            )
            row = cur.fetchone()
            return _MutableRow(self._conn, "search_gap_details", "id", dict(row)) if row else None

    def gap_for_retest_occurrence(self, occurrence_id):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "SELECT * FROM search_gap_details WHERE retest_occurrence_id = %s",
                (occurrence_id,),
            )
            row = cur.fetchone()
            return _MutableRow(self._conn, "search_gap_details", "id", dict(row)) if row else None

    def create_gap(self, occurrence_id, redacted_text, redaction_status, redaction_version):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "INSERT INTO search_gap_details "
                "(occurrence_id, redacted_question, redaction_status, redaction_version) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (occurrence_id, redacted_text, redaction_status, redaction_version),
            )
            return cur.fetchone()["id"]


class _MutableRow(dict):
    """A dict-shaped occurrence/gap row that writes each __setitem__
    straight back to its own row via UPDATE -- lets finalize_ready_jobs()'s
    plain `occ["primary_topic"] = ...` assignments (proven against the
    in-memory fake above) work unchanged against a real connection."""

    _COLUMN_ALLOWLIST = {
        "search_occurrences": {
            "primary_topic", "outcome", "classification_status",
            "classifier_version", "classifier_model", "classifier_prompt_version",
            "classifier_confidence", "finalized_at",
        },
        "search_gap_details": {"retest_outcome"},
    }

    def __init__(self, conn, table, id_column, data):
        super().__init__(data)
        self._conn = conn
        self._table = table
        self._id_column = id_column

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key not in self._COLUMN_ALLOWLIST.get(self._table, set()):
            return
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "UPDATE %s SET %s = %%s WHERE %s = %%s" % (self._table, key, self._id_column),
                (value, self[self._id_column]),
            )


class _AnswerJobsView:
    def __init__(self, conn):
        self._conn = conn

    def get(self, job_id, default=None):
        from app.services.async_answers.db import dict_cursor
        with dict_cursor(self._conn) as cur:
            cur.execute(
                "SELECT status, outcome, question FROM answer_jobs WHERE id = %s",
                (job_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else default


class _OccurrencesView:
    """Present only so PostgresTables shares its attribute names with the
    in-memory fake; unused directly by finalize_ready_jobs()."""

    def __init__(self, conn):
        self._conn = conn


def run_finalizer_once(db, limit: int = 50) -> dict:
    """Real-connection entry point: db.run(fn) hands `fn` a live psycopg2
    connection (async_answers.db.Db's contract) -- wrap it in
    PostgresTables before delegating to the pure logic above. `limit` is
    threaded through to BOTH the SQL-side cap (PostgresTables) and the
    Python-side slice (finalize_ready_jobs) so the two always agree."""

    def _wrapped(conn):
        tables = PostgresTables(conn, limit=limit)
        return finalize_ready_jobs(_SingleRunDb(tables), limit=limit)

    return db.run(_wrapped)


class _SingleRunDb:
    """Adapts a single already-open PostgresTables into the db.run(fn)
    shape finalize_ready_jobs() expects, without opening a second
    transaction."""

    def __init__(self, tables):
        self._tables = tables

    def run(self, fn):
        return fn(self._tables)
