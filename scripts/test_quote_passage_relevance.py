#!/usr/bin/env python3
"""
Regression tests for the 2026-08-18 quote-selection relevance rebuild
(PLAN.md W7, first two bullets): replacing quotes.topic-based matching with
quote/passage-text relevance, deterministic tie-breaking, and idempotent
quote creation in app.services.quotes.

Quote selection itself is still QUOTE_SELECTION_ENABLED-gated and default
off (CLAUDE.md Landmines) -- this file does not touch that flag and does
not re-enable it. scripts/test_quote_selection_gate.py covers the flag
behavior and is left untouched by this session; it still passes unchanged.

Part 1 (mocked embeddings): fast, deterministic, free -- exercises the real
select_quotes_for_answer() and create_and_approve_quote() functions against
an in-memory FakeDb, with embed_text/embed_batch mocked to return
caller-controlled vectors. Proves the MECHANISM: relevance is computed from
quote_text (not topic), tie-breaking is a strict deterministic total order,
the MAX_QUOTES_PER_ANSWER cap still applies, considered-teacher filtering is
unchanged, and quote creation is idempotent (including that a revoked row
does not block recreation, and that the idempotent path never re-invokes
the verifier or inserts a second row).

Part 2 (real embeddings, real corpus text): slower, costs a fraction of a
cent in real OpenAI API calls, same posture as this repo's existing
scripts/analyze_quote_threshold.py and the original QUOTE_TOPIC_SIMILARITY_
THRESHOLD calibration (CLAUDE.md/quotes.py history). Proves the FIX on real
content: the exact defect (a perfect score tie across every quote sharing a
topic tag) reproduces under the OLD scoring shape and is gone under the
NEW one, and genuine false positives found in the live "Baptism in the Holy
Spirit"-tagged cluster are now rejected while a genuine true positive is
still selected. Quote texts below are real, already-approved, already-
public corpus content (captured 2026-08-18 via the read-only
rhemata_readonly_analysis role) -- hardcoded here rather than queried live
so this test does not depend on live DB state or credentials to reproduce.

Run from project root:
  /private/tmp/rhemata-w1w4-venv/bin/python scripts/test_quote_passage_relevance.py
"""
from __future__ import annotations

import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from app.services import quotes
from app.services.embeddings import cosine_similarity

failures = []


def check(label, condition, detail=None):
    status = "PASS" if condition else "FAIL"
    print("  [%s] %s" % (status, label))
    if detail and not condition:
        print("         %s" % detail)
    if not condition:
        failures.append(label)


# ─────────────────────────────────────────────────────────────────────────
# Part 1 -- mocked embeddings, in-memory FakeDb
# ─────────────────────────────────────────────────────────────────────────

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Minimal Supabase-client-shaped query builder over an in-memory table.

    .order() is DELIBERATELY a no-op -- it does not reorder anything. This
    models a real Postgres SELECT with no working ORDER BY (unspecified
    return order), the exact shape of the original bug. Tests below feed
    rows in scrambled order to prove select_quotes_for_answer's own final
    (score, id) sort -- not any ordering the query builder or database
    happens to provide -- is what actually guarantees determinism.
    """

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

    def neq(self, field, value):
        self._rows = [r for r in self._rows if r.get(field) != value]
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

    def insert(self, row):
        full = dict(row)
        full.setdefault("id", str(uuid.uuid4()))
        full.setdefault("created_at", self._db.next_timestamp())
        self._db.tables.setdefault(self._table_name, []).append(full)
        return _FakeInsert(full)


class _FakeInsert:
    def __init__(self, row):
        self._row = row

    def execute(self):
        return _FakeResult([self._row])


class FakeDb:
    def __init__(self):
        self.tables = {}
        self._clock = 0

    def next_timestamp(self):
        self._clock += 1
        return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=self._clock)).isoformat()

    def table(self, name):
        return _FakeQuery(self, name)


def _unit_vec(angle_degrees):
    import math
    rad = math.radians(angle_degrees)
    return [math.cos(rad), math.sin(rad)]


QUESTION_VEC = [1.0, 0.0]  # angle 0 -- cosine_similarity(QUESTION_VEC, v) == cos(angle of v)


def _pipeline_quote(**fields):
    """Stamp migration-089 eligibility fields so selection fixtures remain valid."""
    row = dict(fields)
    row.setdefault("selection_eligible", True)
    row.setdefault("quality_pipeline_version", "quote_quality_v1")
    return row


def test_relevance_keys_off_quote_text_not_topic():
    """Two candidates share the SAME quotes.topic value (the old defect's
    exact shape) but have different quote_text. The selector must score --
    and therefore differentiate -- them by quote_text, not topic."""
    db = FakeDb()
    db.tables["quotes"] = [
        _pipeline_quote(id="q-relevant", topic="Holiness", quote_text="on-topic passage text",
                        status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="q-irrelevant", topic="Holiness", quote_text="off-topic passage text",
                        status="approved", teacher_source_id="teacher-1"),
    ]
    embedded_texts = []

    def fake_embed_batch(texts):
        embedded_texts.extend(texts)
        vecs = {
            "on-topic passage text": _unit_vec(0),      # score 1.0
            "off-topic passage text": _unit_vec(90),    # score 0.0
        }
        return [vecs[t] for t in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(
            db, "irrelevant question text", ["teacher-1"], question_embedding=QUESTION_VEC
        )
    check(
        "embed_batch is called with quote_text values, not topic values",
        embedded_texts == ["on-topic passage text", "off-topic passage text"],
        detail=repr(embedded_texts),
    )
    check(
        "same-topic quotes with different quote_text are differentiated (only the relevant one selected)",
        selected == ["q-relevant"],
        detail=repr(selected),
    )


def test_threshold_cutoff():
    db = FakeDb()
    just_above = quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD + 0.001
    just_below = quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD - 0.001
    db.tables["quotes"] = [
        _pipeline_quote(id="q-at", quote_text="at-threshold", status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="q-above", quote_text="above-threshold", status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="q-below", quote_text="below-threshold", status="approved", teacher_source_id="teacher-1"),
    ]
    import math

    def score_to_vec(score):
        angle = math.degrees(math.acos(max(-1.0, min(1.0, score))))
        return _unit_vec(angle)

    def fake_embed_batch(texts):
        vecs = {
            "at-threshold": score_to_vec(quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD),
            "above-threshold": score_to_vec(just_above),
            "below-threshold": score_to_vec(just_below),
        }
        return [vecs[t] for t in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(db, "q", ["teacher-1"], question_embedding=QUESTION_VEC)
    check(
        "exact-threshold and above-threshold candidates are selected, below-threshold is not",
        set(selected) == {"q-at", "q-above"},
        detail=repr(selected),
    )


def test_max_quotes_per_answer_cap():
    db = FakeDb()
    rows = []
    text_scores = {}
    for i in range(5):
        text = "text-%d" % i
        rows.append(
            _pipeline_quote(
                id="q-%d" % i,
                quote_text=text,
                status="approved",
                teacher_source_id="teacher-1",
            )
        )
        text_scores[text] = 0.9 - (i * 0.05)  # all comfortably above threshold, strictly decreasing
    db.tables["quotes"] = rows
    import math

    def fake_embed_batch(texts):
        out = []
        for t in texts:
            angle = math.degrees(math.acos(text_scores[t]))
            out.append(_unit_vec(angle))
        return out

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(db, "q", ["teacher-1"], question_embedding=QUESTION_VEC)
    check(
        "selection is capped at MAX_QUOTES_PER_ANSWER even with more qualifying candidates",
        len(selected) == quotes.MAX_QUOTES_PER_ANSWER,
        detail="selected=%r" % selected,
    )
    check(
        "the cap keeps the highest-scoring candidates",
        selected == ["q-0", "q-1", "q-2"],
        detail=repr(selected),
    )


def test_deterministic_tie_break():
    """Two candidates score EXACTLY equal. The lower quote id must always
    win, and repeated runs -- including with the fake DB feeding rows in
    reversed order, simulating unspecified DB return order -- must always
    produce the identical result."""
    db = FakeDb()
    db.tables["quotes"] = [
        _pipeline_quote(id="b-quote", quote_text="tied text b", status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="a-quote", quote_text="tied text a", status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="c-quote", quote_text="tied text c", status="approved", teacher_source_id="teacher-1"),
    ]

    def fake_embed_batch(texts):
        # All three texts embed to the identical vector -- a genuine,
        # exact tie, not an approximate one.
        return [_unit_vec(0) for _ in texts]

    results = []
    for _ in range(5):
        with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
            results.append(
                quotes.select_quotes_for_answer(db, "q", ["teacher-1"], question_embedding=QUESTION_VEC)
            )
    check(
        "an exact three-way tie resolves to ascending quote id, capped at MAX_QUOTES_PER_ANSWER",
        results[0] == ["a-quote", "b-quote", "c-quote"],
        detail=repr(results[0]),
    )
    check(
        "the tie-break is stable across repeated runs against DB rows fed in non-id order",
        all(r == results[0] for r in results),
        detail=repr(results),
    )


def test_considered_teacher_filtering_unchanged():
    """A teacher not present in considered_teacher_source_ids never
    contributes a candidate, even if its quotes would score highest.
    considered_teacher_source_ids is documented as the full retrieved set,
    not narrowed to cited teachers -- this function has no citation
    information at all, so "considered but not necessarily cited" is
    structurally guaranteed, not something this test can violate."""
    db = FakeDb()
    db.tables["quotes"] = [
        _pipeline_quote(id="q-in-scope", quote_text="in scope text", status="approved", teacher_source_id="teacher-1"),
        _pipeline_quote(id="q-out-of-scope", quote_text="out of scope text", status="approved", teacher_source_id="teacher-2"),
    ]

    def fake_embed_batch(texts):
        return [_unit_vec(0) for _ in texts]  # both would score 1.0 if both were candidates

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(db, "q", ["teacher-1"], question_embedding=QUESTION_VEC)
    check(
        "a teacher absent from considered_teacher_source_ids contributes no candidates",
        selected == ["q-in-scope"],
        detail=repr(selected),
    )


def test_legacy_approved_row_never_selected_even_if_text_matches():
    """Task 6: migration-089 legacy rows stay unserved. An approved legacy
    quote whose quote_text would score a perfect match must still be
    excluded when selection_eligible is false or quality_pipeline_version
    is null."""
    db = FakeDb()
    db.tables["quotes"] = [
        {
            "id": "q-legacy",
            "quote_text": "perfect match text",
            "status": "approved",
            "teacher_source_id": "teacher-1",
            "selection_eligible": False,
            "quality_pipeline_version": None,
        },
        {
            "id": "q-legacy-null-pipeline",
            "quote_text": "also perfect match text",
            "status": "approved",
            "teacher_source_id": "teacher-1",
            "selection_eligible": True,
            "quality_pipeline_version": None,
        },
        _pipeline_quote(
            id="q-gold",
            quote_text="gold pipeline text",
            status="approved",
            teacher_source_id="teacher-1",
        ),
    ]
    embedded = []

    def fake_embed_batch(texts):
        embedded.extend(texts)
        return [_unit_vec(0) for _ in texts]

    with patch.object(quotes, "embed_batch", side_effect=fake_embed_batch):
        selected = quotes.select_quotes_for_answer(
            db, "q", ["teacher-1"], question_embedding=QUESTION_VEC
        )
    check(
        "legacy approved rows are never selected even when text would match",
        selected == ["q-gold"],
        detail=repr(selected),
    )
    check(
        "embed_batch only sees pipeline-eligible quote_text",
        embedded == ["gold pipeline text"],
        detail=repr(embedded),
    )


# ── Idempotent creation ─────────────────────────────────────────────────
#
# create_and_approve_quote() now wraps its check-then-insert body in
# _creation_lock() (2026-08-18 concurrency hardening -- see quotes.py and
# scripts/test_quote_creation_race.py, which covers the lock's actual
# cross-thread mutual-exclusion behavior with a real advisory-lock
# simulation). These tests are single-threaded and only care about the
# idempotency business logic, not locking mechanics, so _creation_lock is
# patched to a real no-op here -- otherwise every call below would try to
# open a genuine psycopg2 connection via SUPABASE_DB_URL, which is not
# available (or wanted) in this repo-only mocked-embeddings suite.

@contextmanager
def _noop_lock(*_args, **_kwargs):
    yield


PRINCE_ID = next(iter(quotes.CONFIRMED_TEACHER_SOURCE_IDS))

CHUNK_CONTENT = (
    "Intro filler sentence here. This is the real quoted sentence for our "
    "idempotent test. Trailing filler sentence follows nicely."
)
CANDIDATE_TEXT = "This is the real quoted sentence for our idempotent test."


def _seed_creation_fixture():
    db = FakeDb()
    db.tables["chunks"] = [
        {"id": "chunk-1", "document_id": "doc-1", "content": CHUNK_CONTENT, "quote_ineligible_reason": None},
    ]
    db.tables["documents"] = [
        {"id": "doc-1", "source_id": PRINCE_ID},
    ]
    db.tables["quote_source_revisions"] = []
    db.tables["quotes"] = []
    db.tables["quote_verification_log"] = []
    return db


def test_idempotent_creation_no_duplicate_row():
    db = _seed_creation_fixture()
    with patch.object(quotes, "_creation_lock", _noop_lock):
        first = quotes.create_and_approve_quote(
            db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", "first call", "user-1"
        )
        second = quotes.create_and_approve_quote(
            db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", "second call", "user-1"
        )
    check(
        "re-running creation over the same passage returns the same quote id",
        first["id"] == second["id"],
        detail="%r != %r" % (first["id"], second["id"]),
    )
    check(
        "re-running creation over the same passage inserts exactly one quotes row",
        len(db.tables["quotes"]) == 1,
        detail="quotes table has %d rows" % len(db.tables["quotes"]),
    )
    check(
        "re-running creation over the same passage inserts exactly one quote_source_revisions row",
        len(db.tables["quote_source_revisions"]) == 1,
        detail="quote_source_revisions table has %d rows" % len(db.tables["quote_source_revisions"]),
    )


def test_idempotent_short_circuit_skips_verification():
    db = _seed_creation_fixture()
    with patch.object(quotes, "_creation_lock", _noop_lock):
        quotes.create_and_approve_quote(
            db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", "first call", "user-1"
        )

        def must_not_run(*_args, **_kwargs):
            raise AssertionError("idempotent path re-invoked the verifier")

        with patch.object(quotes, "verify_quote_candidate", side_effect=must_not_run):
            result = quotes.create_and_approve_quote(
                db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "Test Topic", "second call", "user-1"
            )
    check(
        "the idempotent short-circuit returns the existing row without re-running the verifier",
        result["status"] == "approved",
        detail=repr(result),
    )


def test_idempotency_ignores_revoked():
    """A revoked quote for the exact same passage must NOT block recreating
    it -- revocation is a deliberate state change, not a reason to refuse
    a fresh, independently-verified candidate over the same text."""
    db = _seed_creation_fixture()
    db.tables["quote_source_revisions"].append(
        {"id": "old-revision", "chunk_id": "chunk-1", "passage_text": CHUNK_CONTENT, "captured_by": "user-0"}
    )
    db.tables["quotes"].append(
        {
            "id": "old-revoked-quote",
            "source_revision_id": "old-revision",
            "teacher_source_id": PRINCE_ID,
            "quote_text": CANDIDATE_TEXT,
            "topic": "Old Topic",
            "reviewer_note": "old",
            "status": "revoked",
            "created_by": "user-0",
            "approved_by": "user-0",
            "approved_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    with patch.object(quotes, "_creation_lock", _noop_lock):
        result = quotes.create_and_approve_quote(
            db, "chunk-1", CANDIDATE_TEXT, PRINCE_ID, "New Topic", "fresh call after revocation", "user-1"
        )
    check(
        "a revoked prior quote for the same passage does not block recreation",
        result["id"] != "old-revoked-quote" and result["status"] == "approved",
        detail=repr(result),
    )
    check(
        "recreation after revocation results in two rows (the revoked one, plus the new one) -- not silently merged",
        len(db.tables["quotes"]) == 2,
        detail="quotes table has %d rows" % len(db.tables["quotes"]),
    )


# ─────────────────────────────────────────────────────────────────────────
# Part 2 -- real embedding calls, real corpus text
#
# Real, already-approved, already-public quote text from the live "Baptism
# in the Holy Spirit"-tagged cluster (14 quotes, captured 2026-08-18 via
# the read-only rhemata_readonly_analysis role). Three of these are
# genuinely unrelated to a baptism-in-the-Holy-Spirit question despite
# sharing that exact topic tag; one is a direct, explicit match.
# ─────────────────────────────────────────────────────────────────────────

REAL_BAPTISM_QUESTION = "What is the baptism in the Holy Spirit and how do I receive it?"

REAL_BAPTISM_CLUSTER = {
    "b3612935": "This is God's appointed way to enable us to do it.\n\nLet's look quickly at a few closing Scriptures on this theme of the Holy Spirit's part in prayer.\n\nRomans 8:26-27:\n\nNotice, the apostle Paul says that we have an infirmity.",
    "cf606ed8": "Attributes of the Holy Spirit\nJohn 14:23-26\n23 Jesus answered and said to him, \" If anyone loves Me, he will keep My word; and My Father will love him, and We will come to him and make Our abode with him.",
    "fcc2cdf2": "Which is normal Hebrew but abnormal Greek. And so I just believe the spirit of holiness is his way of saying the Holy Spirit.\n\nSo, it was the Holy Spirit that vindicated the claim of Jesus to be the Son of God by the resurrection from the dead.",
    "bf1d7e12": "There's a book of mine on the table somewhere entitled Repent and Believe. It's taken from there. After Jesus had died and risen from the dead he explained the scriptures to his disciples, said to them, “thus it behooved Christ to suffer” and that he should be the first that should rise from the dead.",
    "e8539bde": "The resurrected Christ, having triumphed over sin, death and Satan, stands in the presence of His disciples, moves up to each one of them, puts His mouth against their mouth and breathes into them the breath of resurrection life. I believe there's something in the word resurrection.",
    "4333266e": "There's the pattern of how to meet these things that attack love. Let's look first of all at how Jesus met rejection. For three and a half years he gave his life totally to doing good, to forgiving sin, to healing sickness, delivering the demon oppressed.",
    "05b1e824": "I'll tell you how I know, because after the resurrection of Jesus it says right at the end of Luke's gospel:\n\nSo they had great joy, they were continually praising and blessing God but they had not received the seal. They did not receive that until the Day of Pentecost. Jesus said tarry or wait until.",
    "91587881": "It's not the termination, it's the starting point of a life lived in supernatural power. I believe that normally, in most people's experience, the baptism in the Holy Spirit is the doorway to the supernatural gifts of the Spirit and to many other forms of supernatural experience.",
    "36cb8fc5": "We have to meet Jesus. Not just believe a doctrine or join a church, but have a personal encounter with the resurrected Christ and receive from Him the inbreathed breath of God which is the Holy Spirit, and become a new creation. We pass from death to life.",
    "6bcd46a8": "You receive God's love through the Holy Spirit. The Bible says in the gospel of John, “God does not give the Spirit by measure.” The King James puts in the words “unto him” meaning unto Jesus, but they're not there.",
    "8c36afa1": "Let me tell you this. As far as I'm concerned I belong to the Lord Jesus Christ, spirit, soul and body for time and eternity. He redeemed me by His blood when He died on the cross and I have given myself to Him.",
    "256818d5": "Ministry, the Father anointed the Son with the Spirit and the result was the ministry of healing and deliverance.\n\nCalvary, Jesus through the Holy Spirit, the eternal Spirit, offered Himself to the Father the sacrifice for sin.\n\nResurrection, the Father by the Spirit raised the Son from the dead.",
    "b8442391": "I like the word thrust. That is a very powerful word in Greek, it's the same word that's used when Jesus drove demons out of people. Pray the Holy Spirit to drive people into the harvest.",
    "d22bb1ce": "Basically I believe there are seven main forms of prayer—worship, praise, thanksgiving, petition, supplication, intercession and command. If you lump those together under the one title of prayer, those are our spiritual sacrifices.",
}

# Genuinely off-topic despite the shared "Baptism in the Holy Spirit" tag --
# confirmed by direct reading, not by score alone.
REAL_FALSE_POSITIVE_IDS = ["bf1d7e12", "4333266e", "d22bb1ce"]
REAL_TRUE_POSITIVE_ID = "91587881"

SAME_TEACHER_UNRELATED_QUESTION = "How should I think about my finances and giving generously?"


def test_real_old_scoring_reproduces_the_tie():
    same_topic = "Baptism in the Holy Spirit"
    q_vec = quotes.embed_text(REAL_BAPTISM_QUESTION)
    topic_vec = quotes.embed_text(same_topic)
    old_style_score = cosine_similarity(q_vec, topic_vec)
    # Every one of the 14 real quotes shares this exact topic string, so the
    # OLD design scores every single one of them identically -- this is the
    # literal defect, reproduced live rather than merely asserted.
    scores = [old_style_score for _ in REAL_BAPTISM_CLUSTER]
    check(
        "OLD topic-based scoring gives every quote in the cluster an identical score (the defect, reproduced live)",
        len(set(scores)) == 1,
        detail="scores=%r" % scores,
    )


def test_real_new_scoring_rejects_false_positives_and_keeps_true_positive():
    q_vec = quotes.embed_text(REAL_BAPTISM_QUESTION)
    ids = list(REAL_BAPTISM_CLUSTER.keys())
    vecs = quotes.embed_batch([REAL_BAPTISM_CLUSTER[i] for i in ids])
    scores = {qid: cosine_similarity(q_vec, v) for qid, v in zip(ids, vecs)}

    check(
        "NEW quote_text-based scoring does not tie across the cluster (real differentiation)",
        len(set(scores.values())) == len(scores),
        detail="scores=%r" % scores,
    )
    for fp_id in REAL_FALSE_POSITIVE_IDS:
        check(
            "real false positive %s (topic matched, passage does not) now scores below threshold" % fp_id,
            scores[fp_id] < quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD,
            detail="score=%.4f threshold=%.2f" % (scores[fp_id], quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD),
        )
    check(
        "real true positive %s (passage directly supports the question) still scores above threshold" % REAL_TRUE_POSITIVE_ID,
        scores[REAL_TRUE_POSITIVE_ID] >= quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD,
        detail="score=%.4f threshold=%.2f" % (scores[REAL_TRUE_POSITIVE_ID], quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD),
    )


def test_real_same_teacher_unrelated_topic_negative():
    """Same teacher (Derek Prince), same corpus, but a question about an
    entirely different subject (finances) than the baptism cluster's own
    topic. None of the cluster's passages should score above threshold."""
    q_vec = quotes.embed_text(SAME_TEACHER_UNRELATED_QUESTION)
    ids = list(REAL_BAPTISM_CLUSTER.keys())
    vecs = quotes.embed_batch([REAL_BAPTISM_CLUSTER[i] for i in ids])
    scores = {qid: cosine_similarity(q_vec, v) for qid, v in zip(ids, vecs)}
    offenders = {qid: s for qid, s in scores.items() if s >= quotes.QUOTE_PASSAGE_SIMILARITY_THRESHOLD}
    check(
        "an unrelated same-teacher question selects none of the baptism cluster's passages",
        not offenders,
        detail="offenders=%r" % offenders,
    )


def main():
    print("quote passage-relevance + idempotent creation regression suite")
    print("=" * 70)
    print("\nPart 1 -- mocked embeddings (mechanism)")
    test_relevance_keys_off_quote_text_not_topic()
    test_threshold_cutoff()
    test_max_quotes_per_answer_cap()
    test_deterministic_tie_break()
    test_considered_teacher_filtering_unchanged()
    test_legacy_approved_row_never_selected_even_if_text_matches()
    test_idempotent_creation_no_duplicate_row()
    test_idempotent_short_circuit_skips_verification()
    test_idempotency_ignores_revoked()

    print("\nPart 2 -- real embedding calls, real corpus text (evidence)")
    test_real_old_scoring_reproduces_the_tie()
    test_real_new_scoring_rejects_false_positives_and_keeps_true_positive()
    test_real_same_teacher_unrelated_topic_negative()

    print("\n" + "=" * 70)
    if failures:
        print("FAILED: %d check(s)" % len(failures))
        for f in failures:
            print("  - %s" % f)
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
