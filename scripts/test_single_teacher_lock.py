#!/usr/bin/env python3
"""
test_single_teacher_lock.py -- regression tests for Project 2 phase 1 step 2's
retrieval-time single-teacher lock (backend/app/services/single_teacher_lock.py,
backend/app/services/dominance.py) and its wiring into chat.py's retrieval
pipeline (and producer.py's mirror, backend/app/services/async_answers/producer.py).

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions, a `main()` that runs
everything.

Tier A (deterministic, no DB/network): apply_single_teacher_lock() against a
fake db stub -- lock fires on a confirmed settled topic with a dominant
teacher; no-lock on a debate topic, an ordinary/default topic, evidence
below DOMINANCE_THRESHOLD, unresolvable source_id, and empty input.

Tier B (live, real DB + embeddings + Cohere): runs producer.py's own
`_retrieve()` -- the exact retrieval pipeline chat.py mirrors, now including
the lock -- against three real questions (a tongues/settled question, a
confirmed debate-topic question, an ordinary question that defaults to
debate) and captures single_teacher_lock's own INFO log line to observe
whether the lock actually fired, rather than inferring it indirectly.

Also checks the specific "no live effect yet" question this build's own
task raised: whether position_papers.py's match_position_paper() intercepts
a generic tongues question BEFORE this retrieval path (and thus this lock)
ever runs, AND separately tests a teacher-named tongues question (which
position_papers.py's own _mentions_named_teacher gate deliberately excludes
from house-voice interception), to see whether the lock actually engages on
that path today.

Run: python3 scripts/test_single_teacher_lock.py
"""
import logging
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_BACKEND / "app" / ".env")

from app.services.single_teacher_lock import apply_single_teacher_lock  # noqa: E402
from app.services import single_teacher_lock as stl_module  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Tier A -- apply_single_teacher_lock() against a fake db stub
# ═══════════════════════════════════════════════════════════════════════════

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *a):
        return self

    def in_(self, *a):
        return self

    def execute(self):
        return _FakeResult(self.rows)


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _FakeTable(self.rows)


def _entry(cid, score, document_id):
    return (cid, (score, {"document_id": document_id}))


def test_lock_fires_on_settled_dominant():
    print("\n" + "=" * 78)
    print("Tier A: settled topic + dominant teacher (2/3 >= 0.60) -> LOCK")
    print("=" * 78)
    collapsed = [_entry("c1", 0.9, "d1"), _entry("c2", 0.8, "d2"), _entry("c3", 0.7, "d3")]
    db = _FakeDB([
        {"id": "d1", "source_id": "teacherA"},
        {"id": "d2", "source_id": "teacherA"},
        {"id": "d3", "source_id": "teacherB"},
    ])
    chunks, locked = apply_single_teacher_lock("What does it mean to speak in tongues?", collapsed, db)
    _check("locked is True", locked is True)
    _check("only teacherA's chunks remain", [c[0] for c in chunks] == ["c1", "c2"])


def test_no_lock_on_debate_topic():
    print("\n" + "=" * 78)
    print("Tier A: confirmed debate topic -> never locks, regardless of dominance")
    print("=" * 78)
    collapsed = [_entry("c1", 0.9, "d1"), _entry("c2", 0.8, "d2"), _entry("c3", 0.7, "d3")]
    db = _FakeDB([
        {"id": "d1", "source_id": "teacherA"},
        {"id": "d2", "source_id": "teacherA"},
        {"id": "d3", "source_id": "teacherA"},
    ])  # 100% one teacher -- would lock if this were a settled topic
    chunks, locked = apply_single_teacher_lock(
        "Will the rapture happen before or after the tribulation?", collapsed, db
    )
    _check("locked is False", locked is False)
    _check("collapsed returned unchanged", chunks == collapsed)


def test_no_lock_on_default_topic():
    print("\n" + "=" * 78)
    print("Tier A: unmatched/default-to-debate topic -> never locks")
    print("=" * 78)
    collapsed = [_entry("c1", 0.9, "d1"), _entry("c2", 0.8, "d2")]
    db = _FakeDB([
        {"id": "d1", "source_id": "teacherA"},
        {"id": "d2", "source_id": "teacherA"},
    ])  # 100% one teacher -- would lock if this were a settled topic
    chunks, locked = apply_single_teacher_lock("What is deliverance?", collapsed, db)
    _check("locked is False", locked is False)
    _check("collapsed returned unchanged", chunks == collapsed)


def test_no_lock_below_dominance_threshold():
    print("\n" + "=" * 78)
    print("Tier A: settled topic, but no teacher clears DOMINANCE_THRESHOLD -> no lock")
    print("=" * 78)
    collapsed = [_entry("c1", 0.9, "d1"), _entry("c2", 0.8, "d2")]
    db = _FakeDB([
        {"id": "d1", "source_id": "teacherA"},
        {"id": "d2", "source_id": "teacherB"},
    ])  # 1/2 = 0.50 < 0.60
    chunks, locked = apply_single_teacher_lock("What does it mean to speak in tongues?", collapsed, db)
    _check("locked is False", locked is False)
    _check("collapsed returned unchanged", chunks == collapsed)


def test_no_lock_when_source_id_unresolvable():
    print("\n" + "=" * 78)
    print("Tier A: settled topic, but documents lookup returns nothing -> no lock (fail soft)")
    print("=" * 78)
    collapsed = [_entry("c1", 0.9, "d1"), _entry("c2", 0.8, "d2")]
    db = _FakeDB([])  # simulates a failed/empty lookup
    chunks, locked = apply_single_teacher_lock("What does it mean to speak in tongues?", collapsed, db)
    _check("locked is False", locked is False)
    _check("collapsed returned unchanged", chunks == collapsed)


def test_no_lock_on_empty_collapsed():
    print("\n" + "=" * 78)
    print("Tier A: empty retrieval -> no lock, no crash")
    print("=" * 78)
    db = _FakeDB([{"id": "d1", "source_id": "teacherA"}])
    chunks, locked = apply_single_teacher_lock("What does it mean to speak in tongues?", [], db)
    _check("locked is False", locked is False)
    _check("empty list returned", chunks == [])


# ═══════════════════════════════════════════════════════════════════════════
# Tier B -- live retrieval through producer._retrieve(), the exact pipeline
# chat.py mirrors, now including the lock. Log capture observes whether it
# actually fired for each real question.
# ═══════════════════════════════════════════════════════════════════════════

class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(self.format(record))


def _retrieve_with_lock_observation(db, question, matched_pillar_key=None):
    """Runs producer._retrieve() (chat.py's mirrored pipeline) against a real
    question and returns (chunks, citations, fired: bool, log_lines).

    matched_pillar_key: as of the position-papers-as-fence build (2026-08-06),
    _retrieve() takes a 4th param and returns a 4th value
    (fallback_to_paper_voice) -- position-paper interception no longer
    short-circuits before retrieval, so retrieval (and this lock) now
    genuinely runs for position-paper-matched questions too, unlike when
    this test was first written."""
    from app.services.async_answers import producer

    handler = _LogCapture()
    handler.setFormatter(logging.Formatter("%(message)s"))
    stl_module.logger.addHandler(handler)
    stl_module.logger.setLevel(logging.INFO)
    try:
        chunks, citations, citable_count, _fallback = producer._retrieve(
            db, question, matched_pillar_key=matched_pillar_key,
        )
    finally:
        stl_module.logger.removeHandler(handler)

    fired = any("LOCKED to source_id" in line for line in handler.records)
    return chunks, citations, fired, handler.records


def _run_tier_b():
    print("\n" + "=" * 78)
    print("Tier B: live retrieval through producer._retrieve() (real DB + embeddings)")
    print("=" * 78)

    from app.db.supabase import get_supabase
    from app.services.position_papers import match_position_paper

    db = get_supabase()

    cases = [
        ("tongues (generic)", "What does it mean to speak in tongues?"),
        ("tongues (teacher-named)", "What does Derek Prince believe about speaking in tongues?"),
        ("debate topic (eschatological timing)", "Will the rapture happen before or after the tribulation?"),
        ("ordinary/default", "What does the Bible say about tithing?"),
    ]

    for label, question in cases:
        print(f"\n  -- {label}: {question!r} --")
        pillar = match_position_paper(question)
        print(f"     match_position_paper -> {pillar!r}")
        if pillar:
            print("     (a matched position paper is now constraining silent context, "
                  "not a served answer -- retrieval runs normally, so this lock genuinely "
                  "reaches this question too; see scripts/test_position_paper_fence.py "
                  "for the position-paper-specific behavior this build added)")
        chunks, citations, fired, log_lines = _retrieve_with_lock_observation(db, question, matched_pillar_key=pillar)
        authors = sorted({c.get("author") for c in citations if c.get("author")})
        print(f"     lock fired: {fired} | citable authors in result: {authors}")
        for line in log_lines:
            print(f"     [single_teacher_lock] {line}")
        if label.startswith("debate topic") or label == "ordinary/default":
            _check(f"[{label}] lock never fires (not a confirmed settled topic)", fired is False)


def main():
    print("#" * 78)
    print("test_single_teacher_lock.py")
    print("#" * 78)

    test_lock_fires_on_settled_dominant()
    test_no_lock_on_debate_topic()
    test_no_lock_on_default_topic()
    test_no_lock_below_dominance_threshold()
    test_no_lock_when_source_id_unresolvable()
    test_no_lock_on_empty_collapsed()

    print("\n" + "#" * 78)
    if failures:
        print(f"Tier A: {len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("Tier A: all assertions passed.")
    print("#" * 78)

    print(
        "\nTier B below makes live embedding/Cohere/DB calls against the real "
        "corpus. See scripts/test_debate_topics.py for the same disclosure pattern."
    )
    _run_tier_b()

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S) TOTAL: " + ", ".join(failures))
    else:
        print("All assertions passed (Tier A + Tier B).")
    print("#" * 78)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
