#!/usr/bin/env python3
"""
test_teacher_card_guards.py -- regression tests for the two guards added to
GET /study/teacher/{source_id} (backend/app/routers/study.py::get_teacher_card)
this session:

  1. Guard 1 (citation grounding): the same regenerate-once-then-refuse check
     the main answer path runs (reference_verifier.ungrounded_prose_teachers),
     applied to the teacher-card synthesis. Proves the REAL guard function is
     wired in and actually drives control flow -- not just imported.
  2. Guard 2 (commentary/word_study exclusion): match_teacher_chunks carries
     no source_kind/source_type, so the filter runs at the document level,
     before the RPC call. Proves the RPC is invoked with only the surviving
     (non-commentary) document_ids, and that the bibliography (`works`) stays
     built from the FULL unfiltered document set regardless.

Mirrors this repo's ad hoc scripts/test_*.py convention -- no pytest,
hand-built `_check(label, condition)` assertions, `main()` + `sys.exit(1)` on
failure. Follows the constructed/injected-fake pattern from
scripts/test_reference_verifier.py (_FakeResult/_FakeQuery/_FakeDB) and the
restore-in-finally module-attribute monkeypatch pattern from
scripts/test_position_paper_fence.py -- get_teacher_card()'s dependencies
(get_supabase, get_anthropic_client, embed_text, is_source_servable) are all
imported into study.py via `from X import Y`, so they are monkeypatchable
module attributes on `study` itself, same as that file's approach.

No live DB / Anthropic / OpenAI calls anywhere in this file -- every
dependency is faked, so this runs with no .env and no network access
required (unlike scripts/test_teacher_card.py / scripts/test_debate_topics.py,
which both need real credentials for their Tier B live sections).

Run: python3 scripts/test_teacher_card_guards.py
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

# get_teacher_card()'s import chain (app.auth) reads SUPABASE_JWT_JWKS_URL /
# SUPABASE_URL at MODULE IMPORT time (PyJWKClient construction, auth.py:15/22)
# -- dummy values only, never used for a real network call in this file since
# every DB/Anthropic dependency is monkeypatched below before any request is
# made. setdefault() so a real backend/app/.env (if present) still wins.
os.environ.setdefault("SUPABASE_JWT_JWKS_URL", "https://example.invalid/.well-known/jwks.json")
os.environ.setdefault("SUPABASE_URL", "https://example.invalid")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "dummy-service-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "dummy-openai-key")

from app.routers import study  # noqa: E402
from app.services import answer_toolbox  # noqa: E402

failures = []


def _check(label, condition):
    status = "OK" if condition else "FAIL"
    print(f"  {status}: {label}")
    if not condition:
        failures.append(label)


# ═══════════════════════════════════════════════════════════════════════════
# Fakes -- Supabase-shaped DB, Anthropic-shaped client
# ═══════════════════════════════════════════════════════════════════════════

class _FakeResult:
    """Mimics the `.data` attribute the real Supabase client's `.execute()`
    call returns."""

    def __init__(self, data):
        self.data = data


class _FakeQuery:
    """Mimics the chained `.select().eq().order().limit().in_().execute()`
    call -- each chain method just returns self; `.execute()` returns the
    canned rows for whichever table this chain was built for. Ignores filter
    arguments, same convention as scripts/test_reference_verifier.py's
    _FakeQuery (extended here with `.order()`/`.in_()`, which
    get_teacher_card()'s docs_result query and build_retrieval_grounding()'s
    documents lookup respectively need)."""

    def __init__(self, data):
        self._data = data

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _FakeResult(self._data)


class _FakeRPCQuery:
    def __init__(self, data):
        self._data = data

    def execute(self):
        return _FakeResult(self._data)


class _FakeDB:
    """Minimal stand-in for the real Supabase client. `table_responses`:
    dict of table name -> canned rows returned for EVERY query against that
    table (filters are ignored, same as test_reference_verifier.py).
    `rpc_responses`: dict of rpc name -> canned rows. `rpc_calls`: every
    (name, params) tuple passed to `.rpc()`, in order -- lets a test assert
    exactly what was sent (Guard 2's document_ids narrowing)."""

    def __init__(self, table_responses, rpc_responses=None):
        self._table_responses = table_responses
        self._rpc_responses = rpc_responses or {}
        self.rpc_calls = []

    def table(self, name):
        return _FakeQuery(self._table_responses.get(name, []))

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _FakeRPCQuery(self._rpc_responses.get(name, []))


class _FakeAnthropicResponse:
    def __init__(self, text):
        self.content = [types.SimpleNamespace(text=text)]


class _FakeMessages:
    """Records every `.create(**kwargs)` call (so a test can inspect the
    `system` blocks sent on the retry call) and returns canned response
    texts in order, one per call."""

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


def _base_table_responses(documents_rows):
    """Shared scaffolding every get_teacher_card() call needs to clear the
    zero-point gate and license/visibility gate (the latter bypassed
    directly below via is_source_servable monkeypatch, not exercised here --
    out of scope for this file, unrelated to the two guards under test)."""
    return {
        "teacher_profiles": [{"bio": "A curated teacher bio.", "sources": {"name": "Derek Prince"}}],
        "propositions": [{"id": "prop-1"}],
        "documents": documents_rows,
    }


class _Patch:
    """Restore-in-finally module-attribute monkeypatch, mirroring
    scripts/test_position_paper_fence.py's `_run_fallback_case` pattern."""

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


# ═══════════════════════════════════════════════════════════════════════════
# Guard 1 -- citation grounding (regenerate-once-then-refuse)
# ═══════════════════════════════════════════════════════════════════════════

def test_guard1_ungrounded_regenerates_then_refuses():
    print("\n" + "=" * 78)
    print("Guard 1: first attempt ungrounded -> regenerate -> still ungrounded -> refusal")
    print("=" * 78)

    db = _FakeDB(
        table_responses={
            **_base_table_responses([
                {"id": "doc-1", "title": "Sermon On Grace", "source_kind": "sermon_transcript",
                 "source_type": "sermon", "source_id": "src-derek"},
            ]),
            # name_universe: Derek Prince (retrieved, real) + Wallace Fenwick
            # (a fictional name never retrieved for this question).
            "sources": [{"name": "Derek Prince"}, {"name": "Wallace Fenwick"}],
            "source_aliases": [],
        },
        rpc_responses={
            "match_teacher_chunks": [
                {"id": "chunk-1", "document_id": "doc-1", "content": "Grace fulfills what the law required.",
                 "chunk_index": 0, "similarity": 0.9, "title": "Sermon On Grace", "author": "Derek Prince"},
            ],
        },
    )
    # 1st response credits an out-of-corpus teacher; 2nd (post-regeneration)
    # response STILL credits the same ungrounded name -- must end in refusal.
    client = _FakeAnthropicClient(texts=[
        "Derek Prince taught that grace fulfills the law's true intent, much like "
        "Wallace Fenwick's own teaching on grace-based giving.",
        "Wallace Fenwick's teaching on grace-based giving still applies to believers today.",
    ])

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-derek", "What does grace mean for giving?", user_id="test"))

    _check("exactly 2 Anthropic calls were made (1 first-try + 1 regeneration)", len(client.messages.calls) == 2)
    retry_call = client.messages.calls[1] if len(client.messages.calls) >= 2 else {}
    retry_system_texts = [b.get("text", "") for b in retry_call.get("system", [])]
    _check(
        "retry call's system blocks include the STRICT ATTRIBUTION CONSTRAINT",
        any("STRICT ATTRIBUTION CONSTRAINT" in t for t in retry_system_texts),
    )
    _check(
        "retry constraint names the one permitted (retrieved) teacher, Derek Prince",
        any("Derek Prince" in t for t in retry_system_texts),
    )
    _check(
        "served position is answer_toolbox._ATTRIBUTION_REFUSAL, VERBATIM (not the model's text)",
        result.get("position") == answer_toolbox._ATTRIBUTION_REFUSAL,
    )
    _check(
        "the model's actual (still-ungrounded) regenerated text was NOT served",
        result.get("position") != "Wallace Fenwick's teaching on grace-based giving still applies to believers today.",
    )


def test_guard1_grounded_response_passes_through_unchanged():
    print("\n" + "=" * 78)
    print("Guard 1: grounded response (only the retrieved teacher named) -> no regeneration")
    print("=" * 78)

    db = _FakeDB(
        table_responses={
            **_base_table_responses([
                {"id": "doc-1", "title": "Sermon On Grace", "source_kind": "sermon_transcript",
                 "source_type": "sermon", "source_id": "src-derek"},
            ]),
            "sources": [{"name": "Derek Prince"}],
            "source_aliases": [],
        },
        rpc_responses={
            "match_teacher_chunks": [
                {"id": "chunk-1", "document_id": "doc-1", "content": "Grace fulfills what the law required.",
                 "chunk_index": 0, "similarity": 0.9, "title": "Sermon On Grace", "author": "Derek Prince"},
            ],
        },
    )
    grounded_text = (
        "Derek Prince taught that grace fulfills the heart of what the law required, "
        "particularly regarding generosity toward others."
    )
    client = _FakeAnthropicClient(texts=[grounded_text])

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-derek", "What does grace mean for giving?", user_id="test"))

    _check("exactly 1 Anthropic call was made (no regeneration triggered)", len(client.messages.calls) == 1)
    _check("served position is the model's original text, unchanged", result.get("position") == grounded_text)


def test_guard1_no_teacher_named_passes_through_unchanged():
    print("\n" + "=" * 78)
    print("Guard 1: response naming no teacher at all -> no regeneration")
    print("=" * 78)

    db = _FakeDB(
        table_responses={
            **_base_table_responses([
                {"id": "doc-1", "title": "Sermon On Grace", "source_kind": "sermon_transcript",
                 "source_type": "sermon", "source_id": "src-derek"},
            ]),
            "sources": [{"name": "Derek Prince"}],
            "source_aliases": [],
        },
        rpc_responses={
            "match_teacher_chunks": [
                {"id": "chunk-1", "document_id": "doc-1", "content": "Grace fulfills what the law required.",
                 "chunk_index": 0, "similarity": 0.9, "title": "Sermon On Grace", "author": "Derek Prince"},
            ],
        },
    )
    untitled_text = "Grace fulfills the heart of what the law required, particularly regarding generosity."
    client = _FakeAnthropicClient(texts=[untitled_text])

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-derek", "What does grace mean for giving?", user_id="test"))

    _check("exactly 1 Anthropic call was made (no regeneration triggered)", len(client.messages.calls) == 1)
    _check("served position is the model's original text, unchanged", result.get("position") == untitled_text)


# ═══════════════════════════════════════════════════════════════════════════
# Guard 2 -- commentary/word_study exclusion (document-level, pre-RPC)
# ═══════════════════════════════════════════════════════════════════════════

def test_guard2_commentary_document_excluded_from_rpc_call():
    print("\n" + "=" * 78)
    print("Guard 2: mixed document set -> RPC called with only the non-commentary id")
    print("=" * 78)

    ordinary_doc = {"id": "doc-ordinary", "title": "A Real Sermon", "source_kind": "sermon_transcript",
                     "source_type": "sermon", "source_id": "src-teacher"}
    commentary_doc = {"id": "doc-commentary", "title": "A Word Study", "source_kind": "word_study",
                       "source_type": "background", "source_id": "src-teacher"}

    db = _FakeDB(
        table_responses={
            **_base_table_responses([ordinary_doc, commentary_doc]),
            "sources": [{"name": "Derek Prince"}],
            "source_aliases": [],
        },
        rpc_responses={"match_teacher_chunks": []},  # empty -> short-circuits before generation, fine for this check
    )
    client = _FakeAnthropicClient(texts=[])  # must never be called -- empty top_chunks short-circuits first

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-teacher", "What does this teacher say?", user_id="test"))

    _check("exactly 1 RPC call to match_teacher_chunks was made", len(db.rpc_calls) == 1)
    if db.rpc_calls:
        sent_document_ids = db.rpc_calls[0][1].get("document_ids")
        _check("RPC document_ids contains ONLY the non-commentary doc", sent_document_ids == ["doc-ordinary"])
        _check("RPC document_ids does NOT contain the word_study doc", "doc-commentary" not in (sent_document_ids or []))
    _check(
        "bibliography (`works`) still includes BOTH documents, unfiltered",
        {w["id"] for w in result.get("works", [])} == {"doc-ordinary", "doc-commentary"},
    )
    _check("no Anthropic call was made (empty top_chunks short-circuited first)", len(client.messages.calls) == 0)


def test_guard2_all_documents_commentary_falls_back_to_no_works_shape():
    print("\n" + "=" * 78)
    print("Guard 2: EVERY document is commentary-kind -> existing no-works fallback shape, unfiltered works")
    print("=" * 78)

    commentary_only_doc = {"id": "doc-only-commentary", "title": "Only A Word Study", "source_kind": "word_study",
                            "source_type": "background", "source_id": "src-commentary-only"}

    db = _FakeDB(
        table_responses={
            **_base_table_responses([commentary_only_doc]),
            "sources": [],
            "source_aliases": [],
        },
        rpc_responses={},
    )
    client = _FakeAnthropicClient(texts=[])  # must never be called

    with _Patch(study, "get_supabase", lambda: db), \
         _Patch(study, "get_anthropic_client", lambda: client), \
         _Patch(study, "embed_text", lambda q: [0.0] * 1536), \
         _Patch(study, "is_source_servable", lambda _db, _sid: True):
        result = asyncio.run(study.get_teacher_card("src-commentary-only", "What does this teacher say?", user_id="test"))

    _check("zero RPC calls were made (filtering emptied document_ids before the RPC)", len(db.rpc_calls) == 0)
    _check("zero Anthropic calls were made", len(client.messages.calls) == 0)
    _check("position is None (the existing no-content fallback shape)", result.get("position") is None)
    _check(
        "works still contains the (sole, commentary-kind) document -- bibliography stays unfiltered",
        [w["id"] for w in result.get("works", [])] == ["doc-only-commentary"],
    )


def main():
    print("#" * 78)
    print("test_teacher_card_guards.py")
    print("#" * 78)

    test_guard1_ungrounded_regenerates_then_refuses()
    test_guard1_grounded_response_passes_through_unchanged()
    test_guard1_no_teacher_named_passes_through_unchanged()
    test_guard2_commentary_document_excluded_from_rpc_call()
    test_guard2_all_documents_commentary_falls_back_to_no_works_shape()

    print("\n" + "#" * 78)
    if failures:
        print(f"{len(failures)} FAILURE(S): " + ", ".join(failures))
    else:
        print("All assertions passed.")
    print("#" * 78)

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
