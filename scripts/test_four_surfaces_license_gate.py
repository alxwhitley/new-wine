#!/usr/bin/env python3
"""
Regression coverage for the 2026-08-15 license/visibility gate added to four
surfaces confirmed to have been serving corpus content with no gate at all:

  1. backend/app/routers/document.py                -- get_document(), get_article()
  2. backend/app/routers/library.py                  -- get_book_excerpts()
  3. backend/app/services/async_answers/producer.py  -- _inject_background_topics()
  4. backend/app/services/position_papers.py         -- _ensure_body() / get_paper_body()

Each surface is proven to both SERVE content for a real servable document and
REFUSE/skip content for a real non-servable one, using is_source_servable()
(backend/app/services/source_resolver.py) -- the same function, same
predicate (Invariant 2), reused unmodified by all four call sites and by
this test. No new gate logic is invented here; this only exercises what the
production code paths actually do.

Fixtures (real, live, confirmed 2026-08-15):
  SERVABLE_DOC_ID   -- a Matthew Henry commentary document; its source is
                       license_status='public_domain', visibility='shown'.
  UNSERVABLE_DOC_ID -- "So Great a Salvation", a document whose source_id
                       resolves to the sentinel source
                       (267a09ac-76f3-43fb-901f-3015aef88e22,
                       license_status='unlicensed', visibility='hidden' --
                       CLAUDE.md Invariant 3).

producer.py and position_papers.py use monkeypatched fixtures for their
refusal-case checks specifically: as of this writing, no real seeded
background_topics row and no real registered position-paper pillar points at
a non-servable document -- all are Rhemata-owned (license_status='owned',
visibility='shown'), so there is no real non-servable row today that would
exercise that branch. The monkeypatch substitutes a fake topic dict / pillar
dict pointing at UNSERVABLE_DOC_ID and calls the real, unmodified production
function against it -- the gate logic under test is never mocked, only the
input row that would otherwise have to come from a seeded table that
currently has no non-servable member.

Run from project root: python3 scripts/test_four_surfaces_license_gate.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client
from fastapi import HTTPException

# Real, live, known-state fixtures (read-only; confirmed 2026-08-15).
SERVABLE_DOC_ID = "079d77f3-5489-4748-bb30-dc07fc6dedbc"       # Matthew Henry commentary, source public_domain/shown
UNSERVABLE_DOC_ID = "9b9dbc39-b28b-4472-9434-167dddb2a2df"     # "So Great a Salvation", source = sentinel (unlicensed/hidden)
SERVABLE_TOPIC_DOC_ID = "a3884084-46f8-40be-929f-e34cb63ba8ac"  # real background_topics doc ("Baptism of the Holy Spirit"), Rhemata-owned, servable

results = []  # type: list


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print("[" + status + "] " + name + " " + detail)


async def _run_document_tests():
    import app.routers.document as document_router

    result = await document_router.get_document(SERVABLE_DOC_ID, user_id="test-user")
    check("document.get_document servable serves content",
          result["document"]["id"] == SERVABLE_DOC_ID and len(result["chunks"]) > 0,
          "chunks=" + str(len(result["chunks"])))

    result = await document_router.get_article(SERVABLE_DOC_ID, version="original", user_id="test-user")
    check("document.get_article servable serves content",
          result["id"] == SERVABLE_DOC_ID and len(result["content"]) > 0,
          "content_len=" + str(len(result["content"])))

    try:
        await document_router.get_document(UNSERVABLE_DOC_ID, user_id="test-user")
        check("document.get_document unservable refuses", False, "did not raise")
    except HTTPException as e:
        check("document.get_document unservable refuses", e.status_code == 404,
              "status=" + str(e.status_code) + " detail=" + str(e.detail))

    try:
        await document_router.get_article(UNSERVABLE_DOC_ID, version="original", user_id="test-user")
        check("document.get_article unservable refuses", False, "did not raise")
    except HTTPException as e:
        check("document.get_article unservable refuses", e.status_code == 404,
              "status=" + str(e.status_code) + " detail=" + str(e.detail))


async def _run_library_tests():
    import app.routers.library as library_router

    result = await library_router.get_book_excerpts(SERVABLE_DOC_ID, user_id="test-user")
    has_content = bool(result.get("quotes") or result.get("chunks"))
    check("library.get_book_excerpts servable serves content",
          result["document"]["id"] == SERVABLE_DOC_ID and has_content and "source_id" not in result["document"],
          "keys=" + str(list(result["document"].keys())))

    try:
        await library_router.get_book_excerpts(UNSERVABLE_DOC_ID, user_id="test-user")
        check("library.get_book_excerpts unservable refuses", False, "did not raise")
    except HTTPException as e:
        check("library.get_book_excerpts unservable refuses", e.status_code == 404,
              "status=" + str(e.status_code) + " detail=" + str(e.detail))


def _run_producer_tests(db):
    from app.services import answer_toolbox
    from app.services.async_answers import producer as producer_module

    # See module docstring: no real background_topics row points at a
    # non-servable document today, so a fake servable/unservable topic pair
    # is substituted onto the module's own cache, matching the real row
    # shape (_ensure_background_topics only ever selects topic_key,
    # document_id, aliases, title). _inject_background_topics() itself runs
    # completely unmodified against this fixture.
    topic_a = {"topic_key": "test_servable_topic", "document_id": SERVABLE_TOPIC_DOC_ID, "aliases": [], "title": "TEST-SERVABLE-TOPIC"}
    topic_b = {"topic_key": "test_unservable_topic", "document_id": UNSERVABLE_DOC_ID, "aliases": [], "title": "TEST-UNSERVABLE-TOPIC"}
    answer_toolbox._background_topics_loaded = True
    answer_toolbox._background_topics = [topic_a, topic_b]
    answer_toolbox.match_background_topics = lambda question: ["test_servable_topic", "test_unservable_topic"]

    topic_context_parts, injected_doc_ids, updated_topics = producer_module._inject_background_topics(
        db, "irrelevant question text", [], {}
    )
    found_servable_text = any("TEST-SERVABLE-TOPIC" in p for p in topic_context_parts)
    found_unservable_text = any("TEST-UNSERVABLE-TOPIC" in p for p in topic_context_parts)
    served_servable = found_servable_text and (SERVABLE_TOPIC_DOC_ID in injected_doc_ids)
    blocked_unservable = (not found_unservable_text) and (UNSERVABLE_DOC_ID not in injected_doc_ids)
    check("producer._inject_background_topics servable topic injected", served_servable,
          "parts=" + str(len(topic_context_parts)) + " injected=" + str(injected_doc_ids))
    check("producer._inject_background_topics unservable topic blocked", blocked_unservable,
          "found_unservable_text=" + str(found_unservable_text))


def _run_position_papers_tests():
    from app.services import position_papers

    # A real, currently-registered pillar (Rhemata-owned, confirmed
    # servable) -- proves the gate does not break the normal, passing path.
    real_body = position_papers.get_paper_body("baptism_holy_spirit")
    real_body_len = len(real_body) if real_body else 0
    check("position_papers.get_paper_body real servable pillar returns text",
          bool(real_body) and real_body_len > 100, "len=" + str(real_body_len))

    # See module docstring: no real registered pillar points at a
    # non-servable document today (all 8 are Rhemata-owned/shown) --
    # construct a fake pillar dict pointing at the real non-servable
    # document and call _ensure_body() directly (the same function every
    # real pillar goes through; get_paper_body()'s own _PILLARS_BY_KEY
    # lookup only knows the 8 real registered pillars, so this is the only
    # way to reach the refusal branch with a real non-servable row).
    fake_pillar = {"pillar_key": "test_fake_unservable_pillar", "document_id": UNSERVABLE_DOC_ID}
    position_papers._ensure_body(fake_pillar)
    cached = position_papers._body_cache.get("test_fake_unservable_pillar")
    cached_ok = cached is None or not cached.get("loaded")
    check("position_papers._ensure_body unservable pillar leaves cache empty", cached_ok, "cached=" + str(cached))


def main():
    db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    asyncio.run(_run_document_tests())
    asyncio.run(_run_library_tests())
    _run_producer_tests(db)
    _run_position_papers_tests()

    print("")
    print("=" * 70)
    failed = [r for r in results if r[0] == "FAIL"]
    passed_count = len(results) - len(failed)
    print(str(passed_count) + "/" + str(len(results)) + " passed")
    if failed:
        print("FAILURES:")
        for status, name, detail in failed:
            print("  - " + name + ": " + detail)
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
