#!/usr/bin/env python3
"""
test_teacher_card_bio_redaction.py -- permanent regression coverage for two
GET /study/teacher/{source_id} (get_teacher_card()) fixes shipped
2026-08-15, ported from this session's scratchpad verification so a future
change can't silently reopen either hole with nothing in CI to catch it.

  1. Bio-redaction (Issue 1, redone after an independent reviewer
     reproduced a real hole in the first version): a teacher's bio may
     legitimately name another real corpus teacher (e.g. "trained under
     Reinhard Bonnke"). `_redact_bio_for_prompt()` strips every OTHER
     corpus teacher's name out of the COPY of the bio sent to the model,
     before the model ever sees it, so it cannot echo a specific other-
     teacher name into `position` merely because the bio mentioned him.
     The `bio` value returned in the API response stays original and
     unredacted -- real user-facing bibliography content.

     THE CRITICAL CHECK (test_check2_*) is the reviewer's exact
     reproduction: a bio mentions a real teacher (redacted from the
     prompt), but the model's generated `position` text independently
     contains a FABRICATED claim attributed to that same teacher --
     material that was never retrieved for this question. The guard
     (reference_verifier.ungrounded_prose_teachers), completely
     unmodified by this fix, must still catch it and the card must
     regenerate once then refuse. This is what proves the earlier
     pre-grounding approach's hole (blanket-granting a bio-mentioned name
     for the WHOLE answer, not just the specific bio fact) is closed.

  2. Candidate-document-limit decoupling (Issue 2): the bibliography
     ("works") display window and the document pool the commentary/
     word_study exclusion (Guard 2) draws candidates from are decoupled
     via TEACHER_CARD_WORKS_LIMIT (20) / TEACHER_CARD_CANDIDATE_DOC_LIMIT
     (200), so a commentary/word_study-heavy teacher's real candidates no
     longer compete with filtered-out documents for the same small
     20-slot budget.

     scripts/test_teacher_card_guards.py's existing fake DB ignores
     `.limit()` entirely and so CANNOT prove this fix on its own (flagged
     by the independent reviewer) -- this file's `_LimitAwareFakeQuery`
     genuinely truncates results at whatever `.limit(n)` is called with,
     the same way the real Supabase/PostgREST client would.

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions, `main()` + `sys.exit(1)`
on failure. No live DB / Anthropic / OpenAI calls anywhere in this file --
every dependency is faked, same posture as scripts/test_teacher_card_guards.py.

Run: python3 scripts/test_teacher_card_bio_redaction.py
"""
import asyncio
import os
import sys
import types
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_BACKEND = _SCRIPTS.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "dummy-openai-key")

from app.routers import study  # noqa: E402
from app.services import answer_toolbox  # noqa: E402
from app.services.reference_verifier import (  # noqa: E402
    build_retrieval_grounding,
    build_name_universe,
    ungrounded_prose_teachers,
)

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print("  %s: %s" % (status, label))
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Fakes -- Supabase-shaped DB, Anthropic-shaped client
# ═══════════════════════════════════════════════════════════════════════════

class _FakeResult:
    def __init__(self, data):
        self.data = data


class _LimitAwareFakeQuery:
    """Same chained `.select().eq().order().limit().in_().execute()` shape
    as scripts/test_teacher_card_guards.py's `_FakeQuery`, with ONE
    deliberate difference: `.limit(n)` genuinely truncates the canned rows
    to the first `n`, the same way the real Supabase/PostgREST client
    does. Required to prove the Issue 2 candidate-limit fix -- a fake that
    ignores `.limit()` (as test_teacher_card_guards.py's does) cannot
    distinguish the old `.limit(20)` behavior from the new
    `.limit(TEACHER_CARD_CANDIDATE_DOC_LIMIT)` behavior."""

    def __init__(self, data):
        self._data = data
        self._limit = None

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n, *_a, **_k):
        self._limit = n
        return self

    def execute(self):
        data = self._data
        if self._limit is not None:
            data = data[: self._limit]
        return _FakeResult(data)


class _FakeRPCQuery:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResult(self._data)


class _FakeDB:
    """`table_responses`: dict of table name -> canned rows returned for
    EVERY query against that table (filters ignored, `.limit()` honored
    via `_LimitAwareFakeQuery`). `rpc_responses`: dict of rpc name ->
    canned rows. `rpc_calls`: every (name, params) tuple passed to
    `.rpc()`, in order."""

    def __init__(self, table_responses, rpc_responses=None):
        self._table_responses = table_responses
        self._rpc_responses = rpc_responses or {}
        self.rpc_calls = []

    def table(self, name):
        return _LimitAwareFakeQuery(self._table_responses.get(name, []))

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _FakeRPCQuery(self._rpc_responses.get(name, []))


class _FakeAnthropicResponse:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(text=text)]


class _FakeMessages:
    def __init__(self, texts):
        self._texts = list(texts)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self._texts.pop(0) if self._texts else "(no more canned responses)"
        return _FakeAnthropicResponse(text)


class _FakeAnthropicClient:
    def __init__(self, texts):
        self.messages = _FakeMessages(texts)


class _Patch:
    """Restore-in-finally module-attribute monkeypatch, same pattern as
    scripts/test_teacher_card_guards.py's `_Patch`."""

    def __init__(self, obj, name, value):
        self._obj = obj
        self._name = name
        self._value = value
        self._had = hasattr(obj, name)
        self._orig = getattr(obj, name, None)

    def __enter__(self):
        setattr(self._obj, self._name, self._value)
        return self

    def __exit__(self, *_exc):
        if self._had:
            setattr(self._obj, self._name, self._orig)
        else:
            delattr(self._obj, self._name)


def _base_table_responses(documents_rows, bio):
    return {
        "teacher_profiles": [{"bio": bio, "sources": {"name": "Derek Prince"}}],
        "propositions": [{"id": "prop-1"}],
        "documents": documents_rows,
    }


_BIO_TEXT = "Derek Prince trained under Reinhard Bonnke early in his ministry."
_NAME_UNIVERSE = frozenset({"Derek Prince", "Reinhard Bonnke"})
_DOC_ROW = {"id": "doc-1", "title": "Sermon On Grace", "source_kind": "sermon_transcript",
            "source_type": "sermon", "source_id": "src-derek"}


# ═══════════════════════════════════════════════════════════════════════════
# Check 1 -- false-positive-resolved: bio mentions another teacher, model
# does not fabricate, card renders normally (no false refusal).
# ═══════════════════════════════════════════════════════════════════════════

def test_check1_bio_mention_does_not_cause_false_refusal():
    print("\n" + "=" * 78)
    print("Check 1: bio mentions another teacher, model doesn't fabricate -> renders normally")
    print("=" * 78)

    db = _FakeDB(
        table_responses={
            **_base_table_responses([_DOC_ROW], _BIO_TEXT),
            "sources": [{"name": "Derek Prince"}, {"name": "Reinhard Bonnke"}],
            "source_aliases": [],
        },
        rpc_responses={
            "match_teacher_chunks": [
                {"id": "chunk-1", "document_id": "doc-1", "content": "Grace transforms giving.",
                 "chunk_index": 0, "similarity": 0.9, "title": "Sermon On Grace", "author": "Derek Prince"},
            ],
        },
    )
    clean_response_text = (
        "Derek Prince taught that grace transforms how believers approach giving, "
        "emphasizing that generosity flows from a transformed heart rather than obligation."
    )
    client = _FakeAnthropicClient(texts=[clean_response_text])

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-derek", "What does grace mean for giving?", user_id="test"))

    _check("exactly 1 Anthropic call was made (no regeneration triggered)", len(client.messages.calls) == 1)
    _check("served position is the model's original text, verbatim", result.get("position") == clean_response_text)
    _check("served position is NOT the attribution-refusal string",
           result.get("position") != answer_toolbox._ATTRIBUTION_REFUSAL)

    sent_prompt_content = client.messages.calls[0]["messages"][0]["content"]
    _check("the ACTUAL prompt sent to the model does NOT contain Reinhard Bonnke",
           "Reinhard Bonnke" not in sent_prompt_content)
    _check("the ACTUAL prompt sent to the model DOES contain the redaction placeholder",
           study._BIO_REDACTION_PLACEHOLDER in sent_prompt_content)
    _check(
        "the ACTUAL prompt sent to the model still contains the card's OWN teacher name "
        "INSIDE THE BIO BODY (not over-redacted) -- checks a bio-body-specific phrase, not "
        "just the separate 'Teacher: {name}' label line, which would contain the name "
        "regardless of whether exclude_name actually works",
        "Derek Prince trained under" in sent_prompt_content,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Check 2 -- THE CRITICAL CHECK. Bio mentions a teacher (redacted from the
# prompt), but the model's generated position independently contains a
# FABRICATED claim attributed to that same teacher (material never
# retrieved). The unmodified guard must still catch it and refuse.
# ═══════════════════════════════════════════════════════════════════════════

# The reviewer's exact reproduction text.
_FABRICATED_TEXT = (
    "Reinhard Bonnke taught that physical healing is guaranteed in the atonement "
    "for every believer without exception."
)


def test_check2_mechanism_fabricated_claim_still_flagged():
    print("\n" + "=" * 78)
    print("Check 2a (mechanism): fabricated Bonnke claim is STILL flagged by the unmodified guard")
    print("=" * 78)

    chunks = [{"document_id": "doc-1", "author": "Derek Prince", "content": "x", "title": "t"}]

    class _DocsOnlyDB:
        def table(self, name):
            if name == "documents":
                return _LimitAwareFakeQuery([{"id": "doc-1", "source_id": "src-derek"}])
            return _LimitAwareFakeQuery([])

    grounding = build_retrieval_grounding(chunks, _DocsOnlyDB())
    flags = ungrounded_prose_teachers(_FABRICATED_TEXT, _NAME_UNIVERSE, grounding, _DocsOnlyDB())
    _check("Reinhard Bonnke IS flagged as ungrounded on the fabricated claim (the hole is closed)",
           "Reinhard Bonnke" in flags)


def test_check2_end_to_end_regenerates_then_refuses():
    print("\n" + "=" * 78)
    print("Check 2b (end to end): get_teacher_card() still regenerates once then refuses")
    print("=" * 78)

    db = _FakeDB(
        table_responses={
            **_base_table_responses([_DOC_ROW], _BIO_TEXT),
            "sources": [{"name": "Derek Prince"}, {"name": "Reinhard Bonnke"}],
            "source_aliases": [],
        },
        rpc_responses={
            "match_teacher_chunks": [
                {"id": "chunk-1", "document_id": "doc-1", "content": "Grace transforms giving.",
                 "chunk_index": 0, "similarity": 0.9, "title": "Sermon On Grace", "author": "Derek Prince"},
            ],
        },
    )
    # Both the first AND the regenerated response fabricate the same claim,
    # attributed to Bonnke -- simulating the model's own parametric
    # knowledge surfacing unprompted (it was never shown this name), which
    # must still be caught on both passes, ending in a clean refusal.
    client = _FakeAnthropicClient(texts=[_FABRICATED_TEXT, _FABRICATED_TEXT])

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-derek", "What does grace mean for giving?", user_id="test"))

    _check("exactly 2 Anthropic calls were made (1 first-try + 1 regeneration)", len(client.messages.calls) == 2)
    _check("served position IS the attribution-refusal string (hole closed, not silently served)",
           result.get("position") == answer_toolbox._ATTRIBUTION_REFUSAL)
    _check("the fabricated Bonnke claim was NEVER served as the position",
           result.get("position") != _FABRICATED_TEXT)


# ═══════════════════════════════════════════════════════════════════════════
# Check 3 -- candidate-document-limit decoupling, using a fake DB whose
# `.limit()` genuinely truncates (proves the fix; the existing
# test_teacher_card_guards.py fake CANNOT, since it ignores `.limit()`).
# ═══════════════════════════════════════════════════════════════════════════

def test_check3_commentary_heavy_candidate_count_before_after():
    print("\n" + "=" * 78)
    print("Check 3: commentary-heavy document set -- before/after candidate count (limit-aware fake)")
    print("=" * 78)

    commentary_docs = [
        {"id": "doc-ws-%d" % i, "title": "Word Study %d" % i, "source_kind": "word_study",
         "source_type": "background", "source_id": "src-heavy"}
        for i in range(22)
    ]
    real_docs = [
        {"id": "doc-real-%d" % i, "title": "Real Sermon %d" % i, "source_kind": "sermon_transcript",
         "source_type": "sermon", "source_id": "src-heavy"}
        for i in range(3)
    ]
    all_docs_ordered = commentary_docs + real_docs  # 25 total, real ones LAST (oldest)

    db = _FakeDB(
        table_responses={
            **_base_table_responses(all_docs_ordered, "A commentary-heavy teacher."),
            "sources": [{"name": "Derek Prince"}],
            "source_aliases": [],
        },
        rpc_responses={"match_teacher_chunks": []},
    )
    client = _FakeAnthropicClient(texts=[])  # must never be called either way

    # BEFORE: patch the candidate-doc limit back to the pre-fix value (20).
    with _Patch(study, "TEACHER_CARD_CANDIDATE_DOC_LIMIT", 20), \
         _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result_before = asyncio.run(study.get_teacher_card("src-heavy", "What does this teacher say?", user_id="test"))
    rpc_calls_before = list(db.rpc_calls)
    db.rpc_calls = []

    # AFTER: real, current code (TEACHER_CARD_CANDIDATE_DOC_LIMIT = 200, as shipped).
    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result_after = asyncio.run(study.get_teacher_card("src-heavy", "What does this teacher say?", user_id="test"))
    rpc_calls_after = list(db.rpc_calls)

    before_ids = rpc_calls_before[0][1].get("document_ids") if rpc_calls_before else []
    after_ids = rpc_calls_after[0][1].get("document_ids") if rpc_calls_after else []
    print("  BEFORE (limit=20)  -> RPC calls: %d, candidate document_ids: %r" % (len(rpc_calls_before), before_ids))
    print("  AFTER  (limit=%d) -> RPC calls: %d, candidate document_ids: %r" %
          (study.TEACHER_CARD_CANDIDATE_DOC_LIMIT, len(rpc_calls_after), after_ids))

    _check("BEFORE fix: zero RPC calls (all 20 fetched docs were word_study, none survived the filter)",
           len(rpc_calls_before) == 0)
    _check("AFTER fix: exactly 1 RPC call made", len(rpc_calls_after) == 1)
    _check("AFTER fix: all 3 real (non-commentary) documents reached the candidate set",
           set(after_ids) == {"doc-real-0", "doc-real-1", "doc-real-2"})
    _check("AFTER fix: works (bibliography) still capped at the original 20-item window, unchanged",
           len(result_after.get("works", [])) == 20)
    _check("BEFORE fix: works (bibliography) was also the same 20-item window (unaffected either way)",
           len(result_before.get("works", [])) == 20)


def main():
    print("#" * 78)
    print("test_teacher_card_bio_redaction.py")
    print("#" * 78)

    test_check1_bio_mention_does_not_cause_false_refusal()
    test_check2_mechanism_fabricated_claim_still_flagged()
    test_check2_end_to_end_regenerates_then_refuses()
    test_check3_commentary_heavy_candidate_count_before_after()

    print("\n" + "#" * 78)
    if failures:
        print("%d FAILURE(S): %s" % (len(failures), ", ".join(failures)))
    else:
        print("All assertions passed.")
    print("#" * 78)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
