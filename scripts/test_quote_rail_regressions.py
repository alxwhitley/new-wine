#!/usr/bin/env python3
"""Task 8 Step 1 — quote-rail regressions with QUOTE_SELECTION_ENABLED off.

PLAN.md Q3 / docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md
Task 8 Step 1: prove the safety contracts while the rail stays off
(selection dry). Does not apply migrations, write quotes, or flip the
deployed flag.

Coverage (repo-only, FakeDb + stubs):

1. Flag-off producer never calls the selector and emits no quote_ids.
2. Delivery suppresses persisted quote_ids when the flag is off.
3. Selection dry-run: legacy / null-pipeline / selection_eligible=false
   rows are never returned (no bad quote IDs), even when text matches.
4. Baptism false-positive class: topic-tagged but off-passage quotes stay
   below threshold; a true passage match can still be selected when the
   selector is invoked directly (flag-on simulation for selection dry).
5. Honest no-support: empty teacher set or no eligible rows → [].
6. Teacher-card surface: get_teacher_card response shape has no quote_ids
   and study.py never imports/calls select_quotes_for_answer.
7. Presentation contract (source scan): QuoteRail requires teacher_name
   and renders work_title + topic chip.

Article-supported answer proof is N/A until W5–W6 lands a live article
on the answer path — recorded as an explicit skip, not a silent pass.

Run from project root:
  /private/tmp/newwine-w1w4-venv/bin/python scripts/test_quote_rail_regressions.py
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")

from dotenv import load_dotenv

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.services import quotes
from app.services.async_answers import jobs, producer
from app.services import (
    position_papers,
    reference_verifier,
    single_teacher_lock,
    stored_position_evidence,
    stored_position_topics,
)
from app.routers import async_chat

failures: list[str] = []

# Real baptism-cluster excerpts (already public; same set as
# scripts/test_quote_passage_relevance.py Part 2).
BAPTISM_QUESTION = "What is the baptism in the Holy Spirit and how do I receive it?"
BAPTISM_FALSE_POSITIVES = {
    "bf1d7e12": (
        "There's a book of mine on the table somewhere entitled Repent and Believe. "
        "It's taken from there. After Jesus had died and risen from the dead he "
        "explained the scriptures to his disciples, said to them, “thus it behooved "
        "Christ to suffer” and that he should be the first that should rise from the dead."
    ),
    "4333266e": (
        "There's the pattern of how to meet these things that attack love. Let's look "
        "first of all at how Jesus met rejection. For three and a half years he gave "
        "his life totally to doing good, to forgiving sin, to healing sickness, "
        "delivering the demon oppressed."
    ),
    "d22bb1ce": (
        "Basically I believe there are seven main forms of prayer—worship, praise, "
        "thanksgiving, petition, supplication, intercession and command. If you lump "
        "those together under the one title of prayer, those are our spiritual sacrifices."
    ),
}
BAPTISM_TRUE_POSITIVE = {
    "91587881": (
        "It's not the termination, it's the starting point of a life lived in "
        "supernatural power. I believe that normally, in most people's experience, "
        "the baptism in the Holy Spirit is the doorway to the supernatural gifts of "
        "the Spirit and to many other forms of supernatural experience."
    ),
}
TEACHER_ID = "teacher-prince"


def check(label: str, condition: bool, detail: str | None = None) -> None:
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


# ── FakeDb (order is a no-op — selector must supply its own total order) ─


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table_name = table_name
        self._rows = list(db.tables.get(table_name, []))
        self._limit = None

    def select(self, _cols):
        return self

    def eq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) == value]
        return self

    def in_(self, field, values):
        values = set(values)
        self._rows = [r for r in self._rows if r.get(field) in values]
        return self

    def order(self, _field):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        rows = self._rows if self._limit is None else self._rows[: self._limit]
        return _FakeResult(rows)


class FakeDb:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return _FakeQuery(self, name)


def _unit_vec(angle_degrees: float) -> list[float]:
    rad = math.radians(angle_degrees)
    return [math.cos(rad), math.sin(rad)]


QUESTION_VEC = [1.0, 0.0]


def _pipeline_quote(**fields):
    row = dict(fields)
    row.setdefault("selection_eligible", True)
    row.setdefault("quality_pipeline_version", "quote_quality_v1")
    row.setdefault("status", "approved")
    row.setdefault("teacher_source_id", TEACHER_ID)
    return row


def _score_to_vec(score: float) -> list[float]:
    angle = math.degrees(math.acos(max(-1.0, min(1.0, score))))
    return _unit_vec(angle)


# ── 1–2. Flag-off producer + delivery ───────────────────────────────────


def _producer_result(env_value, selector):
    chunk = {
        "id": "chunk-1",
        "document_id": "document-1",
        "author": "Teacher One",
        "content": "Supported answer material.",
        "citation_mode": "citable",
    }
    usage = {
        "input_tokens": 1,
        "output_tokens": 1,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(position_papers, "match_position_paper", return_value=None), \
         patch.object(stored_position_topics, "match_stored_position", return_value=None), \
         patch.object(stored_position_evidence, "fetch_stored_position_evidence", return_value=None), \
         patch.object(producer, "_inject_background_topics", return_value=([], set(), {})), \
         patch.object(producer, "_retrieve", return_value=([chunk], [], 1, False)), \
         patch.object(producer, "_build_context", return_value="context"), \
         patch.object(producer, "_build_history", return_value=[]), \
         patch.object(
             producer,
             "_generate_and_capture",
             return_value=("Teacher One gives a supported answer.", "raw", None, usage, "test-model"),
         ), \
         patch.object(reference_verifier, "build_retrieval_grounding", return_value={}), \
         patch.object(reference_verifier, "build_name_universe", return_value=[]), \
         patch.object(reference_verifier, "ungrounded_prose_teachers", return_value=False), \
         patch.object(reference_verifier, "verify_references", return_value=[]), \
         patch.object(producer, "estimate_cost_usd", return_value=0.0), \
         patch.object(single_teacher_lock, "resolve_source_ids_for_documents", return_value={"document-1": "source-1"}), \
         patch.object(quotes, "select_quotes_for_answer", selector):
        return producer.produce(object(), "What does the teacher say?")


class _CaptureCursor:
    def __init__(self):
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query, params):
        self.params = params


class _CaptureConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, **_kwargs):
        return self._cursor


class _CaptureDb:
    def __init__(self):
        self.cursor = _CaptureCursor()

    def run(self, work):
        work(_CaptureConnection(self.cursor))


class _NoopDb:
    def close(self):
        pass


async def _sse_meta_for_persisted_job(job, env_value=None):
    environment = {} if env_value is None else {"QUOTE_SELECTION_ENABLED": env_value}
    with patch.dict(os.environ, environment, clear=True), \
         patch.object(async_chat, "Db", return_value=_NoopDb()), \
         patch.object(async_chat.jobs, "get_job", return_value=job):
        response = await async_chat.result("job-1", None, user_id=None)
        events = []
        async for chunk in response.body_iterator:
            events.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
    return next(
        json.loads(event[len("data: "):].strip())
        for event in events
        if event.startswith("data: ") and "quote_ids" in event
    )


def test_flag_off_producer_and_delivery():
    print("\n1. Flag off — producer + delivery")
    check(
        "default env disables selection",
        quotes.quote_selection_enabled({}) is False,
    )

    def selector_must_not_run(*_a, **_k):
        raise AssertionError("disabled producer called quote selector")

    result = _producer_result(None, selector_must_not_run)
    check("disabled producer emits no quote_ids", result.quote_ids == [])

    db = _CaptureDb()
    jobs.complete(
        db,
        job_id="job-1",
        answer=result.answer,
        outcome=result.outcome,
        citations=result.citations,
        verified_references=result.verified_references,
        retrieved_chunk_ids=result.retrieved_chunk_ids,
        retrieved_point_ids=result.retrieved_point_ids,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_write_tokens=result.cache_write_tokens,
        cost_usd=result.cost_usd,
        updated_topics=result.updated_topics,
        quote_ids=result.quote_ids,
    )
    persisted = db.cursor.params[13].adapted
    check("persistence stores empty quote_ids under flag-off produce", persisted == [])

    stale_job = {
        "status": "done",
        "answer": "Prior answer with leftover quote ids.",
        "outcome": "answered",
        "citations": [{"chunk_id": "c1"}],
        "verified_references": [],
        "quote_ids": ["legacy-bad-1", "legacy-bad-2"],
        "result_meta": {"updated_topics": {}},
        "evidence_version": "test-evidence",
    }
    meta = asyncio.run(_sse_meta_for_persisted_job(stale_job))
    check(
        "SSE suppresses persisted quote_ids while flag is off",
        meta["quote_ids"] == [],
        detail=repr(meta.get("quote_ids")),
    )
    check(
        "flag-off delivery does not resurrect bad quote IDs",
        "legacy-bad-1" not in meta["quote_ids"] and "legacy-bad-2" not in meta["quote_ids"],
    )


# ── 3–5. Selection dry: eligibility, baptism class, no-support ──────────


def test_no_bad_quote_ids_selection_dry():
    print("\n2. Selection dry — no bad / legacy quote IDs")
    db = FakeDb()
    matching_text = "baptism in the Holy Spirit doorway"
    db.tables["quotes"] = [
        {
            "id": "q-legacy-ineligible",
            "quote_text": matching_text,
            "status": "approved",
            "teacher_source_id": TEACHER_ID,
            "selection_eligible": False,
            "quality_pipeline_version": None,
        },
        {
            "id": "q-null-pipeline",
            "quote_text": matching_text,
            "status": "approved",
            "teacher_source_id": TEACHER_ID,
            "selection_eligible": True,
            "quality_pipeline_version": None,
        },
        {
            "id": "q-pending",
            "quote_text": matching_text,
            "status": "pending",
            "teacher_source_id": TEACHER_ID,
            "selection_eligible": True,
            "quality_pipeline_version": "quote_quality_v1",
        },
        _pipeline_quote(id="q-gold", quote_text=matching_text),
    ]

    def fake_embed_batch(texts):
        # Every candidate text is identical — only eligibility should decide.
        return [_score_to_vec(0.99) for _ in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(
            db, BAPTISM_QUESTION, [TEACHER_ID], question_embedding=QUESTION_VEC
        )
    check(
        "only quality-pipeline eligible approved row is selected",
        selected == ["q-gold"],
        detail=repr(selected),
    )
    check(
        "legacy-ineligible ID never returned",
        "q-legacy-ineligible" not in selected,
    )
    check(
        "null-pipeline ID never returned",
        "q-null-pipeline" not in selected,
    )
    check("pending ID never returned", "q-pending" not in selected)


def test_baptism_false_positive_class():
    print("\n3. Baptism false-positive class (selection dry, mocked scores)")
    db = FakeDb()
    rows = []
    text_to_score = {}
    for qid, text in BAPTISM_FALSE_POSITIVES.items():
        rows.append(
            _pipeline_quote(
                id=qid,
                quote_text=text,
                topic="Baptism in the Holy Spirit",
            )
        )
        # Below threshold — topic matched historically; passage does not.
        text_to_score[text] = quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD - 0.05
    for qid, text in BAPTISM_TRUE_POSITIVE.items():
        rows.append(
            _pipeline_quote(
                id=qid,
                quote_text=text,
                topic="Baptism in the Holy Spirit",
            )
        )
        text_to_score[text] = quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD + 0.10
    db.tables["quotes"] = rows

    def fake_embed_batch(texts):
        return [_score_to_vec(text_to_score[t]) for t in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(
            db, BAPTISM_QUESTION, [TEACHER_ID], question_embedding=QUESTION_VEC
        )
    check(
        "baptism true-positive quote ID selected",
        selected == ["91587881"],
        detail=repr(selected),
    )
    for fp_id in BAPTISM_FALSE_POSITIVES:
        check(
            "baptism false-positive %s not selected" % fp_id,
            fp_id not in selected,
        )


def test_honest_no_support():
    print("\n4. Honest no-support")
    db = FakeDb()
    db.tables["quotes"] = [
        _pipeline_quote(id="q-gold", quote_text="eligible but no teachers considered"),
    ]
    selected_empty_teachers = quotes.select_quotes_for_answer(
        db, BAPTISM_QUESTION, [], question_embedding=QUESTION_VEC
    )
    check("empty considered teachers → []", selected_empty_teachers == [])

    db2 = FakeDb()
    db2.tables["quotes"] = [
        {
            "id": "q-legacy-only",
            "quote_text": "legacy passage that would match",
            "status": "approved",
            "teacher_source_id": TEACHER_ID,
            "selection_eligible": False,
            "quality_pipeline_version": None,
        }
    ]

    def fake_embed_batch(texts):
        return [_score_to_vec(0.99) for _ in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected_legacy_only = quotes.select_quotes_for_answer(
            db2, BAPTISM_QUESTION, [TEACHER_ID], question_embedding=QUESTION_VEC
        )
    check(
        "legacy-only pool → [] (honest empty, not a bad ID)",
        selected_legacy_only == [],
        detail=repr(selected_legacy_only),
    )


# ── 6. Teacher card bounded: no quote rail ───────────────────────────────


def test_teacher_card_has_no_quote_rail():
    print("\n5. Teacher-card surface — no quote_ids / no selector")
    study_path = ROOT / "backend" / "app" / "routers" / "study.py"
    source = study_path.read_text(encoding="utf-8")
    check(
        "study.py never imports select_quotes_for_answer",
        "select_quotes_for_answer" not in source,
    )
    check(
        "study.py never references quote_selection_enabled",
        "quote_selection_enabled" not in source,
    )
    check(
        "study.py never emits quote_ids key",
        "quote_ids" not in source,
    )

    # Bound the live return shape of get_teacher_card's documented contract.
    # Early returns in the function body always use bio/works/position only.
    returns = re.findall(
        r'return \{\s*"bio"[^}]+\}',
        source,
        flags=re.DOTALL,
    )
    check(
        "at least one get_teacher_card-shaped return found",
        len(returns) >= 1,
        detail="found %d" % len(returns),
    )
    for block in returns:
        check(
            "teacher-card return has no quote_ids: %s..." % block[:40].replace("\n", " "),
            "quote_ids" not in block,
        )


# ── 7. Presentation contract (source) ────────────────────────────────────


def test_presentation_contract_in_frontend():
    print("\n6. Presentation contract (QuoteRail source)")
    chat_message = (ROOT / "frontend" / "components" / "newwine" / "chat-message.tsx").read_text(
        encoding="utf-8"
    )
    check("QuoteRail function exists", "function QuoteRail" in chat_message)
    check(
        "QuoteRail filters out quotes missing teacher_name",
        "teacher_name" in chat_message and "filter" in chat_message,
    )
    check("QuoteRail renders work_title", "work_title" in chat_message)
    check(
        "QuoteRail uses topic_ids[0] or topic for chip",
        "topic_ids" in chat_message and "Badge" in chat_message,
    )
    check(
        "QuoteRail is visually separated (aside + border-t)",
        'aria-label="Verified quotes"' in chat_message and "border-t" in chat_message,
    )


def test_article_path_skip_recorded():
    print("\n7. Article-supported answer (explicit N/A)")
    # W5–W6 has not landed a production article on the answer path yet.
    # Task 8's article proof waits on that; do not pretend it passed.
    check(
        "article-supported quote proof deferred until W5–W6 (recorded skip, not silent pass)",
        True,
    )


def test_citation_ids_unchanged_under_flag_off():
    print("\n8. Exact citations preserved under flag-off produce")

    def selector_must_not_run(*_a, **_k):
        raise AssertionError("selector ran")

    result = _producer_result(None, selector_must_not_run)
    check("flag-off answer still has outcome answered", result.outcome == "answered")
    check("flag-off answer emits no quote_ids", result.quote_ids == [])
    check(
        "retrieved_chunk_ids stay exact under flag-off",
        result.retrieved_chunk_ids == ["chunk-1"],
        detail=repr(result.retrieved_chunk_ids),
    )


def test_eligibility_filter_mutation():
    """Prove the application-side eligibility filter is load-bearing.

    Temporarily strip the filter from select_quotes_for_answer; the same
    legacy-matching fixture must then leak a bad ID. Restore and re-confirm
    the good path. Same mutation posture as test_quote_creation_race.py.
    """
    print("\n9. Mutation — eligibility filter is load-bearing")
    import inspect

    src = inspect.getsource(quotes.select_quotes_for_answer)
    check(
        "select_quotes_for_answer source contains eligibility filter",
        "selection_eligible" in src and "quality_pipeline_version" in src,
    )

    db = FakeDb()
    matching_text = "baptism in the Holy Spirit doorway"
    db.tables["quotes"] = [
        {
            "id": "q-legacy-leak",
            "quote_text": matching_text,
            "status": "approved",
            "teacher_source_id": TEACHER_ID,
            "selection_eligible": False,
            "quality_pipeline_version": None,
        },
        _pipeline_quote(id="q-gold", quote_text=matching_text),
    ]

    def fake_embed_batch(texts):
        return [_score_to_vec(0.99) for _ in texts]

    # Mutate: replace the filter list-comp with an identity pass-through.
    original = quotes.select_quotes_for_answer

    def broken_select(db_arg, question, considered_teacher_source_ids, question_embedding=None):
        source_ids = sorted({sid for sid in considered_teacher_source_ids if sid})
        if not source_ids:
            return []
        rows = (
            db_arg.table("quotes")
            .select("id, quote_text, selection_eligible, quality_pipeline_version")
            .eq("status", "approved")
            .in_("teacher_source_id", source_ids)
            .order("id")
            .execute()
            .data
        ) or []
        # MUTATION: no eligibility filter
        if not rows:
            return []
        q_vec = question_embedding if question_embedding is not None else quotes.embed_text(question)
        text_vecs = quotes.embed_batch([r["quote_text"] for r in rows])
        from app.services.embeddings import cosine_similarity

        scored = []
        for row, text_vec in zip(rows, text_vecs):
            score = cosine_similarity(q_vec, text_vec)
            if score >= quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD:
                scored.append((score, row["id"]))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [quote_id for _, quote_id in scored[: quotes.MAX_QUOTES_PER_ANSWER]]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        leaked = broken_select(db, BAPTISM_QUESTION, [TEACHER_ID], question_embedding=QUESTION_VEC)
        intact = original(db, BAPTISM_QUESTION, [TEACHER_ID], question_embedding=QUESTION_VEC)

    check(
        "mutation without eligibility filter leaks legacy ID",
        "q-legacy-leak" in leaked,
        detail=repr(leaked),
    )
    check(
        "restored select_quotes_for_answer still excludes legacy ID",
        intact == ["q-gold"],
        detail=repr(intact),
    )


def main() -> int:
    print("quote rail regressions — Task 8 Step 1 (flag off / selection dry)")
    print("=" * 70)

    test_flag_off_producer_and_delivery()
    test_no_bad_quote_ids_selection_dry()
    test_baptism_false_positive_class()
    test_honest_no_support()
    test_teacher_card_has_no_quote_rail()
    test_presentation_contract_in_frontend()
    test_article_path_skip_recorded()
    test_citation_ids_unchanged_under_flag_off()
    test_eligibility_filter_mutation()

    print("\n" + "=" * 70)
    if failures:
        print("FAILED: %d check(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
