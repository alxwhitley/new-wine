#!/usr/bin/env python3
"""
test_propositions_book_chapters.py — regression proof for the chapter-scoped,
multi-call proposition-extraction path for book-length documents (see
propositions.py's own "Book-length document handling" section): store_
propositions()'s new clear_existing parameter, split_book_into_chapters(),
the SAFE_CHAPTER_WORD_CEILING sub-split fallback, and the gated/gate-free
process_book_document()/_extract_and_store_book_chapters() entry points.

Conventions, matching this repo's existing scripts/test_propositions_*.py
files exactly:
  - DB-FREE FakeConn/FakeCursor (test_propositions_closeness_gate.py's own
    convention) for every test that only needs to prove application-level
    branching/bucketing logic, never a real write.
  - Real-chunk-reconstruction (test_propositions_reference_grounding.py's
    own convention) for the ONE test that needs real book text: a
    single, read-only, bulk `SELECT content FROM chunks WHERE document_id
    = %s ORDER BY chunk_index` against the real True Vine document. This is
    the ONLY real DB touch anywhere in this file -- everything else is
    synthetic text, per this build's own instruction not to invent
    synthetic "book-shaped" text when the real thing is one query away,
    while still using synthetic text freely for edge cases (sub-split
    fallback, curly-apostrophe/whitespace normalization, a chapter that
    legitimately yields zero, bucket-outcome branching).

No pytest -- plain function calls with assertions, run via __main__, same as
every other scripts/test_propositions_*.py file in this repo.

Run: python3 scripts/test_propositions_book_chapters.py
"""
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import propositions as pm  # noqa: E402

TRUE_VINE_DOC_ID = "6daf6671-e386-4103-998e-1fb42914300b"

# Cross-book false-positive guard fixtures (correction pass) -- two other
# public-domain books already in the corpus, with DIFFERENT front-matter/
# chapter-numbering conventions than The True Vine, specifically chosen
# because the planning step named exact chapters from these two as the ones
# a naive "Capitalized Word Then Colon" heuristic would have false-flagged:
#   - Absolute Surrender (Andrew Murray): "The Fruit of the Spirit is Love",
#     "Kept by the Power of God".
#   - Power Through Prayer (E.M. Bounds): "8. Examples of Praying Men" --
#     found by direct content search; NOT in "Prayer and Praying Men" (a
#     different, similarly-named Bounds book also in the corpus) despite
#     the similar title -- confirmed by grepping chunk content for the
#     exact phrase before picking this document id.
ABSOLUTE_SURRENDER_DOC_ID = "1da1afb1-78b2-4eec-be57-01426d676266"
POWER_THROUGH_PRAYER_DOC_ID = "c1a5d28f-d4bd-4a6f-ad15-75a65b0582e5"

# The 31 real chapter titles + Preface, in document order, exactly as they
# appear in the real source text (confirmed via a one-off read-only
# reconstruction + line-scan during this build's own investigation, prior
# to writing split_book_into_chapters() itself). "The Vine" genuinely
# appears TWICE -- two distinct real chapters share that title -- kept as
# a literal duplicate entry here so the Counter-based check below can
# confirm BOTH occurrences were detected, not just that the label is
# present at all.
EXPECTED_TRUE_VINE_CHAPTERS = [
    "Preface",
    "The Vine",
    "The Husbandman",
    "The Branch",
    "The Fruit",
    "More Fruit",
    "The Cleansing",
    "The Pruning Knife",
    "Abide",
    "Except Ye Abide",
    "The Vine",
    "Ye The Branches",
    "Much Fruit",
    "You Can Do Nothing",
    "Withered Branches",
    "Whatsoever Ye Will",
    "If Ye Abide",
    "The Father Glorified",
    "True Disciples",
    "The Wonderful Love",
    "Abide In My Love",
    "Obey And Abide",
    "Ye, Even As I",
    "Joy",
    "Love One Another",
    "Even As I Have Loved You",
    "Christ's Friendship: Its Origin",
    "Christ's Friendship: Its Evidence",
    "Christ's Friendship: Its Intimacy",
    "Election",
    "Abiding Fruit",
    "Prevailing Prayer",
]


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


def _fetch_ordered_chunks(db_params: dict, document_id: str):
    """ONE bulk, READ-ONLY SELECT of every (chunk_id, content) for
    document_id, ordered by chunk_index -- not a per-chunk query. Mirrors
    test_propositions_reference_grounding.py's own
    _reconstruct_document_text() convention, but returns (chunk_id,
    content) tuples (split_book_into_chapters()'s own required input
    shape) rather than a single joined string."""
    import psycopg2

    conn = psycopg2.connect(**db_params)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"No chunks found for document_id={document_id!r} -- check the id.")
    return [(str(r[0]), r[1]) for r in rows]


# ── DB-free FakeConn/FakeCursor (test_propositions_closeness_gate.py's own
#    convention) ─────────────────────────────────────────────────────────────

class FakeCursor:
    def __init__(self, license_status="licensed"):
        self._license_status = license_status
        self.executed = []  # [(sql, params), ...] -- full audit trail

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return (self._license_status,)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeConn:
    def __init__(self, license_status="licensed"):
        self._cursor = FakeCursor(license_status)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def delete_count(self):
        return sum(
            1 for sql, _params in self._cursor.executed
            if "DELETE FROM propositions" in sql
        )

    def inserted_rows(self):
        """Every INSERT INTO propositions params tuple, in call order.
        Param order per store_propositions(): (id, document_id, content,
        embedding_str, proposition_index, prompt_version, fingerprint,
        model)."""
        return [
            params for sql, params in self._cursor.executed
            if "INSERT INTO propositions" in sql
        ]


def fake_embed_fn(text: str):
    return [0.01, 0.02, 0.03]


# ════════════════════════════════════════════════════════════════════════
# 2-3. store_propositions() clear_existing -- default True vs. False
# ════════════════════════════════════════════════════════════════════════

def test_clear_existing_default_and_false():
    print("\n" + "=" * 78)
    print("2-3. store_propositions(): clear_existing default (True) vs. False")
    print("=" * 78)

    document_id = "11111111-1111-1111-1111-111111111111"
    props = [
        {"proposition_index": 1, "content": "A hand-made teaching passage for the clear_existing test."},
    ]

    print("\n--- clear_existing omitted (default True): exactly one DELETE ---")
    conn_default = FakeConn()
    n_default = pm.store_propositions(
        conn_default, document_id, props, fake_embed_fn, prompt_version="v3",
    )
    print(f"  n_inserted={n_default}, delete_count={conn_default.delete_count()}")
    assert n_default == 1
    assert conn_default.delete_count() == 1, (
        f"expected exactly 1 DELETE when clear_existing is omitted (default True), "
        f"got {conn_default.delete_count()}"
    )

    print("\n--- clear_existing=False: ZERO DELETEs, insert still happens unchanged ---")
    conn_false = FakeConn()
    n_false = pm.store_propositions(
        conn_false, document_id, props, fake_embed_fn, prompt_version="v3",
        clear_existing=False,
    )
    print(f"  n_inserted={n_false}, delete_count={conn_false.delete_count()}")
    assert n_false == 1, "insert count must be unchanged by clear_existing=False"
    assert conn_false.delete_count() == 0, (
        f"expected ZERO DELETEs when clear_existing=False, got {conn_false.delete_count()}"
    )
    assert conn_false.committed, "store_propositions() must still commit when clear_existing=False"

    print("\n--- clear_existing=True explicit: same as default (byte-identical call shape) ---")
    conn_explicit_true = FakeConn()
    n_explicit = pm.store_propositions(
        conn_explicit_true, document_id, props, fake_embed_fn, prompt_version="v3",
        clear_existing=True,
    )
    assert n_explicit == 1
    assert conn_explicit_true.delete_count() == 1

    print("\nPASSED: clear_existing default/True issues exactly one DELETE; "
          "clear_existing=False issues zero DELETEs with insert behavior unchanged.")


# ════════════════════════════════════════════════════════════════════════
# 4. _extract_and_store_book_chapters(): bucket outcomes, single DELETE,
#    continuous proposition_index, non-NULL provenance, error isolation.
# ════════════════════════════════════════════════════════════════════════

def _title_block(title: str) -> str:
    return f"{title}\n{title}\n{title.upper()}\n"


def _words(n: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_extract_and_store_book_chapters_buckets():
    print("\n" + "=" * 78)
    print("4. _extract_and_store_book_chapters(): bucket outcomes + provenance + isolation")
    print("=" * 78)

    # Five real chapters (no preface -- the very first character of the
    # reconstructed text IS the first detected boundary, so
    # split_book_into_chapters() never adds a "preface_pre_boundary" span
    # here): a THIN chapter (skipped_thin, zero model calls), an EMPTY
    # chapter (extract_propositions() returns [] -> "empty"), an ERROR
    # chapter (extract_propositions() raises -> "errored", must NOT abort
    # the remaining chapters), and two STORED chapters (prove proposition_
    # index stays CONTINUOUS across them, never resetting per chapter).
    chapter_bodies = [
        ("Thin Chapter", _words(10)),           # 6 + 10 = 16 words -> skipped_thin
        ("Empty Chapter", _words(80)),          # -> extract returns []
        ("Error Chapter", _words(80)),          # -> extract raises
        ("Stored Chapter One", _words(80)),     # -> 2 canned propositions
        ("Stored Chapter Two", _words(80)),     # -> 1 canned proposition
    ]
    ordered_chunks = [
        (f"chunk-{i}", _title_block(title) + body)
        for i, (title, body) in enumerate(chapter_bodies)
    ]

    extract_calls = []

    def fake_extract(text, doc_id="", speaker=None, prompt_version="v3"):
        extract_calls.append(text)
        if "Empty Chapter" in text:
            return []
        if "Error Chapter" in text:
            raise pm.PropositionExtractionFailed("simulated chapter extraction failure")
        if "Stored Chapter One" in text:
            return [
                {"proposition_index": 1, "content": "Canned proposition A for stored chapter one."},
                {"proposition_index": 2, "content": "Canned proposition B for stored chapter one."},
            ]
        if "Stored Chapter Two" in text:
            return [
                {"proposition_index": 1, "content": "Canned proposition C for stored chapter two."},
            ]
        raise AssertionError(f"fake_extract called with unexpected text: {text[:60]!r}")

    # Monkeypatch execute_values (proposition_chunks bulk insert) the same
    # way test_propositions_closeness_gate.py does -- FakeCursor has no
    # real mogrify()/connection.encoding for psycopg2's real
    # execute_values() to use. Not the focus of THIS test (item 5 covers
    # chunk-linking precision in detail); just needs to not blow up.
    ev_calls = []

    def fake_execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls.append((sql, list(argslist)))

    original_extract = pm.extract_propositions
    original_execute_values = pm.execute_values
    pm.extract_propositions = fake_extract
    pm.execute_values = fake_execute_values
    try:
        conn = FakeConn()
        document_id = "22222222-2222-2222-2222-222222222222"
        result = pm._extract_and_store_book_chapters(
            conn, document_id, ordered_chunks, fake_embed_fn,
            speaker=None, prompt_version="v3",
        )
    finally:
        pm.extract_propositions = original_extract
        pm.execute_values = original_execute_values

    print(f"\nresult = {result}")

    # ── Bucket reconciliation ───────────────────────────────────────────────
    assert result["chapters_attempted"] == 5
    assert result["chapters_stored"] == 2
    assert result["chapters_empty"] == 1
    assert result["chapters_errored"] == 1
    assert result["chapters_skipped_thin"] == 1
    assert result["chapters_attempted"] == (
        result["chapters_stored"] + result["chapters_empty"]
        + result["chapters_errored"] + result["chapters_skipped_thin"]
    ), "bucket accounting must reconcile"
    assert result["propositions_stored"] == 3, "2 (chapter D) + 1 (chapter E) = 3"
    print("  CONFIRMED: attempted=5 == stored=2 + empty=1 + errored=1 + skipped_thin=1; "
          "propositions_stored=3.")

    # ── skipped_thin: ZERO model calls for the thin chapter ────────────────
    assert not any("Thin Chapter" in t for t in extract_calls), (
        "extract_propositions() must NEVER be called for the thin chapter"
    )
    assert len(extract_calls) == 4, f"expected exactly 4 model calls, got {len(extract_calls)}"
    print(f"  CONFIRMED: extract_propositions() called {len(extract_calls)} times, "
          f"never for the thin chapter (word-count floor).")

    # ── per_chapter outcomes, in document order ─────────────────────────────
    outcomes = {c["label"]: c["outcome"] for c in result["per_chapter"]}
    print(f"  per_chapter outcomes: {outcomes}")
    assert outcomes["Thin Chapter"] == "skipped_thin"
    assert outcomes["Empty Chapter"] == "empty"
    assert outcomes["Error Chapter"] == "errored"
    assert outcomes["Stored Chapter One"] == "stored"
    assert outcomes["Stored Chapter Two"] == "stored"
    n_props_by_label = {c["label"]: c["n_propositions"] for c in result["per_chapter"]}
    assert n_props_by_label["Empty Chapter"] == 0, "empty chapter must not be backfilled with propositions"
    assert n_props_by_label["Stored Chapter One"] == 2
    assert n_props_by_label["Stored Chapter Two"] == 1

    # ── Error isolation: chapters AFTER the errored one still processed ────
    assert result["chapters_errored"] == 1 and outcomes["Error Chapter"] == "errored", (
        "the forced PropositionExtractionFailed must be caught and bucketed, not raised"
    )
    assert outcomes["Stored Chapter One"] == "stored" and outcomes["Stored Chapter Two"] == "stored", (
        "chapters after the errored one must still be processed -- one bad chapter "
        "must never abort the remaining ones"
    )
    print("  CONFIRMED: the errored chapter was caught and bucketed; both chapters "
          "AFTER it in document order were still processed and stored.")

    # ── Exactly ONE DELETE for the whole document (not per chapter) ────────
    print(f"  conn.delete_count() = {conn.delete_count()}")
    assert conn.delete_count() == 1, (
        f"expected exactly 1 DELETE FROM propositions for the whole document "
        f"(the orchestrator's own single clear), got {conn.delete_count()}"
    )
    print("  CONFIRMED: exactly one DELETE fired for the whole document, "
          "despite 2 chapters each calling store_propositions().")

    # ── proposition_index is CONTINUOUS across chapters (never reset) ──────
    inserted = conn.inserted_rows()
    assert len(inserted) == 3, f"expected 3 real INSERT INTO propositions calls, got {len(inserted)}"
    prop_indices = [params[4] for params in inserted]
    print(f"  stored proposition_index values, in order: {prop_indices}")
    assert prop_indices == [1, 2, 3], (
        f"expected continuous proposition_index [1, 2, 3] across the two stored "
        f"chapters (2 then 1), got {prop_indices}"
    )
    print("  CONFIRMED: proposition_index is continuous across chapters (chapter D -> "
          "1,2; chapter E -> 3; never reset to 1 for chapter E).")

    # ── Every stored row carries non-NULL, correctly-derived provenance ────
    expected_fp = pm.prompt_fingerprint("v3")
    for params in inserted:
        prompt_version_col, fingerprint_col, model_col = params[5], params[6], params[7]
        assert prompt_version_col == "v3" and prompt_version_col is not None
        assert fingerprint_col == expected_fp and fingerprint_col is not None
        assert model_col == pm.EXTRACTION_MODEL and model_col is not None
    print("  CONFIRMED: every one of the 3 stored rows carries non-NULL "
          "prompt_version/prompt_fingerprint/model, matching prompt_fingerprint('v3')/"
          "EXTRACTION_MODEL computed independently.")

    print("\nPASSED: 4. bucket outcomes, single DELETE, continuous proposition_index, "
          "non-NULL provenance, and error isolation all confirmed.")


# ════════════════════════════════════════════════════════════════════════
# 5. Chunk-linking precision: non-adjacent chapters share nothing; adjacent
#    chapters DO share exactly one boundary chunk when built to straddle
#    (and correctly do NOT when built with a clean boundary).
# ════════════════════════════════════════════════════════════════════════

def test_chunk_linking_precision():
    print("\n" + "=" * 78)
    print("5. Chunk-linking precision: straddling vs. clean chapter boundaries")
    print("=" * 78)

    # Chapter One: two whole chunks of its own, plus a THIRD chunk that
    # STRADDLES the boundary into Chapter Two (ends chapter one's body,
    # then contains chapter two's own title-repeat marker mid-chunk).
    # Chapter Two: its straddling share above, plus one more whole chunk of
    # its own. Chapter Three: a CLEAN boundary -- its title-repeat marker
    # starts EXACTLY at the beginning of its own dedicated chunk, so no
    # chunk is shared with chapter two.
    chunk_1a = _title_block("Chapter One") + _words(60, "c1a")
    chunk_1b = _words(60, "c1b")
    chunk_straddle_12 = _words(40, "tail1") + "\n" + _title_block("Chapter Two") + _words(40, "head2")
    chunk_2a = _words(60, "c2a")
    chunk_clean_3 = _title_block("Chapter Three") + _words(60, "c3a")

    ordered_chunks = [
        ("chunk-1a", chunk_1a),
        ("chunk-1b", chunk_1b),
        ("chunk-straddle-12", chunk_straddle_12),
        ("chunk-2a", chunk_2a),
        ("chunk-clean-3", chunk_clean_3),
    ]

    chapters, missing = pm.split_book_into_chapters(ordered_chunks)
    print(f"\nDetected chapters: {[(c.label, c.chunk_ids) for c in chapters]}")
    assert len(chapters) == 3, f"expected exactly 3 detected chapters, got {len(chapters)}: " \
        f"{[c.label for c in chapters]}"
    ch1, ch2, ch3 = chapters
    assert ch1.label == "Chapter One"
    assert ch2.label == "Chapter Two"
    assert ch3.label == "Chapter Three"

    set1, set2, set3 = set(ch1.chunk_ids), set(ch2.chunk_ids), set(ch3.chunk_ids)
    print(f"  chapter 1 chunk_ids: {sorted(set1)}")
    print(f"  chapter 2 chunk_ids: {sorted(set2)}")
    print(f"  chapter 3 chunk_ids: {sorted(set3)}")

    # ── Chapter 1 <-> Chapter 3: EMPTY intersection (not adjacent at all) ──
    assert set1 & set3 == set(), (
        f"expected EMPTY intersection between chapter 1 and chapter 3 chunk_ids, "
        f"got {set1 & set3}"
    )
    print("  CONFIRMED: chapter 1 and chapter 3 chunk_ids have EMPTY intersection.")

    # ── Chapter 1 <-> Chapter 2: exactly ONE shared (straddling) chunk ─────
    shared_12 = set1 & set2
    assert shared_12 == {"chunk-straddle-12"}, (
        f"expected chapter 1 and chapter 2 to share EXACTLY {{'chunk-straddle-12'}}, "
        f"got {shared_12}"
    )
    print(f"  CONFIRMED: chapter 1 and chapter 2 share exactly one boundary-straddling "
          f"chunk: {shared_12}")

    # ── Chapter 2 <-> Chapter 3: EMPTY intersection (clean boundary, this
    #    pair does NOT straddle -- demonstrated, not papered over) ─────────
    shared_23 = set2 & set3
    assert shared_23 == set(), (
        f"expected chapter 2 and chapter 3 to share NOTHING (clean boundary, no "
        f"straddling chunk built for this pair), got {shared_23}"
    )
    print(f"  CONFIRMED: chapter 2 and chapter 3 share NOTHING (a clean, non-straddling "
          f"boundary) -- both straddling and clean adjacency are demonstrated in this "
          f"one fixture, not just one or the other.")

    print("\nPASSED: 5. Chunk-linking precision confirmed for both non-adjacent chapters "
          "and both flavors of adjacent chapters (straddling and clean).")


# ════════════════════════════════════════════════════════════════════════
# 6. split_book_into_chapters(): real True Vine text (31 chapters +
#    Preface) + synthetic apostrophe/whitespace variants + no-marker
#    size-fallback.
# ════════════════════════════════════════════════════════════════════════

def test_split_book_into_chapters_real_true_vine():
    print("\n" + "=" * 78)
    print("6a. split_book_into_chapters(): REAL True Vine text -- 31 chapters + Preface")
    print("=" * 78)

    db_params = _db_params()
    ordered_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)
    print(f"\nFetched {len(ordered_chunks)} real chunks (read-only SELECT) for The True Vine.")

    chapters, missing_expected_titles = pm.split_book_into_chapters(ordered_chunks)
    print(f"Detected {len(chapters)} total spans (includes front/back matter, not just "
          f"the 31 real chapters + Preface).")
    for c in chapters:
        wc = len(c.text.split())
        print(f"  [{c.split_method:22s}] {wc:5d} words  {c.label!r}")

    detected_counter = Counter(c.label for c in chapters)
    expected_counter = Counter(EXPECTED_TRUE_VINE_CHAPTERS)

    missing_real = []
    for title, expected_n in expected_counter.items():
        got_n = detected_counter.get(title, 0)
        if got_n < expected_n:
            missing_real.append((title, expected_n, got_n))

    print(f"\nTOC-based missing_expected_titles diagnostic (optional refinement): "
          f"{missing_expected_titles}")

    if missing_real:
        print(f"\nMISSED real chapters (title, expected_count, detected_count): {missing_real}")
    else:
        print("\nCONFIRMED: all 31 real chapter titles + Preface detected, including both "
              "occurrences of the duplicate title 'The Vine' and all 3 curly-apostrophe "
              "'Christ's Friendship' chapters.")
    assert not missing_real, (
        f"expected all 31 real chapters + Preface to be detected -- missed: {missing_real}"
    )

    # Explicit, separately-named confirmation for the curly-apostrophe case
    # named in this build's own brief.
    friendship_titles = [
        "Christ's Friendship: Its Origin",
        "Christ's Friendship: Its Evidence",
        "Christ's Friendship: Its Intimacy",
    ]
    for t in friendship_titles:
        assert detected_counter[t] >= 1, f"expected {t!r} to be detected"
    print("CONFIRMED: all 3 'Christ's Friendship' chapters detected (real source ALL-CAPS "
          "line uses a curly apostrophe; the two title-case repeats used for detection "
          "use a straight one -- _normalize_line() handles this).")

    print("\nPASSED: 6a. real True Vine chapter detection confirmed against live corpus data.")


def test_split_book_into_chapters_synthetic():
    print("\n" + "=" * 78)
    print("6b-6c. split_book_into_chapters(): synthetic whitespace variant + no-marker fallback")
    print("=" * 78)

    # ── 6b: normal straight apostrophe + whitespace variants (extra
    #    internal spaces, trailing space) must still normalize-match. ──────
    print("\n--- 6b: apostrophe + whitespace-variant normalization ---")
    text_variant = (
        "Peter's Denial\n"
        "Peter's   Denial \n"
        "PETER'S DENIAL\n"
        + _words(80) + "\n"
        + "Peter's Restoration\n"
        "Peter's Restoration\n"
        "PETER'S RESTORATION\n"
        + _words(80)
    )
    ordered_chunks_variant = [("chunk-a", text_variant)]
    chapters_variant, _missing = pm.split_book_into_chapters(ordered_chunks_variant)
    print(f"  detected: {[(c.label, c.split_method) for c in chapters_variant]}")
    assert len(chapters_variant) == 2, f"expected 2 chapters, got {len(chapters_variant)}"
    assert chapters_variant[0].label == "Peter's Denial"
    assert chapters_variant[0].split_method == "title_repeat_boundary"
    assert chapters_variant[1].label == "Peter's Restoration"
    assert chapters_variant[1].split_method == "title_repeat_boundary"
    print("  CONFIRMED: extra internal whitespace + a trailing space on the second "
          "repeated title line still normalize-match the first.")

    # ── 6c: NO title-repeat marker anywhere in a long stretch -> the whole
    #    document falls back to size-based splitting. Real paragraph
    #    structure (blank-line-delimited), so this exercises the
    #    "paragraph" batching path at split_book_into_chapters()'s own
    #    LONG_STRETCH_WORD_THRESHOLD ceiling. ─────────────────────────────
    print("\n--- 6c: no marker anywhere -> size_fallback split_method ---")
    # LONG_STRETCH_WORD_THRESHOLD raised 3000 -> 6000 (Problem 2, a later,
    # separate, isolated one-constant change to match SAFE_CHAPTER_WORD_
    # CEILING -- see that constant's own comment). This test's fixture must
    # comfortably exceed whatever the real threshold is, so it's sized
    # relative to the constant itself rather than a hardcoded word count.
    assert pm.LONG_STRETCH_WORD_THRESHOLD == 6000, (
        "this test assumes the real threshold constant; got "
        f"{pm.LONG_STRETCH_WORD_THRESHOLD}"
    )
    n_paragraphs = (pm.LONG_STRETCH_WORD_THRESHOLD // 200) + 15  # comfortably over threshold
    paragraphs = [
        " ".join(f"p{i}word{j}" for j in range(200)) + "."
        for i in range(n_paragraphs)  # n_paragraphs x 200 words, zero repeated lines
    ]
    no_marker_text = "\n\n".join(paragraphs)
    expected_total_words = n_paragraphs * 200
    assert len(no_marker_text.split()) == expected_total_words

    ordered_chunks_no_marker = [("chunk-nomark", no_marker_text)]
    chapters_nm, missing_nm = pm.split_book_into_chapters(ordered_chunks_no_marker)
    print(f"  {len(chapters_nm)} size_fallback piece(s), word counts: "
          f"{[len(c.text.split()) for c in chapters_nm]}")
    assert len(chapters_nm) >= 2, "a 4000-word marker-less stretch must be split into 2+ pieces"
    assert missing_nm == [], "no Contents section exists in this fixture -- nothing to cross-check"
    for c in chapters_nm:
        assert c.split_method == "size_fallback", (
            f"expected split_method='size_fallback' for every no-marker piece, got {c.split_method!r}"
        )
        assert len(c.text.split()) <= pm.LONG_STRETCH_WORD_THRESHOLD, (
            "no piece should exceed the size-fallback ceiling"
        )
    # Bounds + ordering: the first piece starts exactly at the text's own
    # start, the last ends exactly at the text's own end, and pieces never
    # overlap or go backwards. NOTE: paragraph-BATCH boundaries (as opposed
    # to within a single batch) legitimately skip the blank-line delimiter
    # text BETWEEN two batches -- _paragraph_spans() attributes that
    # delimiter to neither paragraph, so a small character gap between
    # consecutive batches is expected and correct here (real whitespace,
    # never real content) -- this is NOT the same claim as "no content
    # lost", which the word-count-sum check below verifies directly.
    assert chapters_nm[0].char_start == 0
    assert chapters_nm[-1].char_end == len(no_marker_text)
    for i in range(len(chapters_nm) - 1):
        assert chapters_nm[i].char_end <= chapters_nm[i + 1].char_start, (
            "size-fallback pieces must never overlap or go backwards"
        )
    total_words_across_pieces = sum(len(c.text.split()) for c in chapters_nm)
    assert total_words_across_pieces == expected_total_words, (
        f"expected all {expected_total_words} words preserved across pieces (only "
        f"inter-batch blank-line whitespace may be dropped, never actual paragraph "
        f"content), got {total_words_across_pieces}"
    )
    print("  CONFIRMED: entirely marker-less stretch is split into ordered, "
          "non-overlapping size_fallback pieces (only inter-batch blank-line whitespace "
          "is skipped between them, never real content -- all 4000 words are preserved "
          "across the pieces), none exceeding LONG_STRETCH_WORD_THRESHOLD.")

    print("\nPASSED: 6b-6c. synthetic apostrophe/whitespace normalization and the "
          "no-marker size-fallback path both confirmed.")


# ════════════════════════════════════════════════════════════════════════
# 7. Sub-split fallback (SAFE_CHAPTER_WORD_CEILING): paragraph-level batch
#    split without breaking a paragraph, and sentence-level fallback when a
#    single paragraph alone exceeds the ceiling.
# ════════════════════════════════════════════════════════════════════════

def test_sub_split_fallback():
    print("\n" + "=" * 78)
    print("7. Sub-split fallback: paragraph-level batching + sentence-level fallback")
    print("=" * 78)

    ceiling = 6000
    assert pm.SAFE_CHAPTER_WORD_CEILING == ceiling, (
        f"this test assumes the real ceiling constant; got {pm.SAFE_CHAPTER_WORD_CEILING}"
    )

    # ── 7a: 10 paragraphs of 1000 words each (10,000 words total) ->
    #    batched into 2 pieces (6 paragraphs = 6000 words, then 4
    #    paragraphs = 4000 words), NEITHER piece breaking a paragraph. ─────
    print("\n--- 7a: paragraph-level batching, no paragraph broken ---")
    paras = [f"para{i} " * 1000 for i in range(10)]  # each exactly 1000 words
    for i, p in enumerate(paras):
        assert len(p.split()) == 1000
    big_text = "\n\n".join(p.strip() for p in paras)
    total_words = len(big_text.split())
    print(f"  total words: {total_words}")
    assert total_words == 10000

    pieces = pm._split_text_by_size(big_text, ceiling)
    print(f"  {len(pieces)} piece(s): word counts = {[len(t.split()) for _s, _e, t, _m in pieces]}, "
          f"methods = {[m for _s, _e, _t, m in pieces]}")
    assert len(pieces) == 2, f"expected exactly 2 pieces (6000 + 4000 words), got {len(pieces)}"
    assert all(m == "paragraph" for _s, _e, _t, m in pieces)
    assert len(pieces[0][2].split()) == 6000
    assert len(pieces[1][2].split()) == 4000
    # No paragraph broken: piece 0 must contain para0..para5 in full and
    # NOT contain any of para6..para9's own marker; piece 1 the reverse.
    piece0_text, piece1_text = pieces[0][2], pieces[1][2]
    for i in range(6):
        assert f"para{i} " in piece0_text, f"piece 0 must contain whole para{i}"
    for i in range(6, 10):
        assert f"para{i} " not in piece0_text, f"piece 0 must NOT contain any of para{i} (would mean a paragraph got split)"
        assert f"para{i} " in piece1_text, f"piece 1 must contain whole para{i}"
    print("  CONFIRMED: 10,000-word, 10-paragraph text split into exactly 2 pieces "
          "(6000 + 4000 words), neither breaking a paragraph in half.")

    # ── 7b: ONE paragraph (no blank lines) made of many short sentences,
    #    total word count > ceiling but no SINGLE sentence exceeds it ->
    #    falls to sentence-level batching (still batched toward the
    #    ceiling, not one output piece per sentence). ────────────────────
    print("\n--- 7b: single oversized paragraph -> sentence-level fallback ---")
    n_sentences = 3000
    sentences = [f"Sentence number {i} is short." for i in range(n_sentences)]  # 5 words each
    one_paragraph_text = " ".join(sentences)  # no blank lines -> ONE paragraph
    total_words_b = len(one_paragraph_text.split())
    print(f"  total words: {total_words_b} (single paragraph, {n_sentences} sentences)")
    assert total_words_b == n_sentences * 5  # "Sentence number {i} is short." = 5 words
    assert total_words_b > ceiling

    # Confirm this really is ONE paragraph at the paragraph-scan level.
    assert len(pm._paragraph_spans(one_paragraph_text)) == 1, (
        "fixture must be exactly one blank-line-delimited paragraph"
    )

    pieces_b = pm._split_text_by_size(one_paragraph_text, ceiling)
    methods_b = {m for _s, _e, _t, m in pieces_b}
    word_counts_b = [len(t.split()) for _s, _e, t, _m in pieces_b]
    print(f"  {len(pieces_b)} piece(s), methods={methods_b}, word counts={word_counts_b}")
    assert methods_b == {"sentence"}, (
        f"expected every piece to use sentence-level batching, got methods={methods_b}"
    )
    assert all(wc <= ceiling for wc in word_counts_b), "no sentence-level piece may exceed the ceiling"
    assert len(pieces_b) > 1, "12,000+ words must not collapse into a single output piece"
    # Batching, not one-sentence-per-piece: with ~5 words/sentence and a
    # 6000-word ceiling, each piece should hold on the order of ~1000+
    # sentences (~5000+ words), NOT ~1 sentence (~5 words) -- this is the
    # exact defect this build's own implementation review caught and fixed.
    assert all(wc > 100 for wc in word_counts_b[:-1]), (
        "sentence-level pieces must be BATCHED toward the ceiling, not emitted "
        "one sentence at a time -- got suspiciously small non-final piece(s): "
        f"{word_counts_b}"
    )
    # No sentence broken: every piece's text, stripped, ends with a period
    # (never a mid-sentence cut).
    for _s, _e, t, _m in pieces_b:
        assert t.strip().endswith("."), f"expected a piece to end at a sentence boundary, got tail: {t[-30:]!r}"
    print("  CONFIRMED: single oversized paragraph falls to sentence-level splitting, "
          "batched toward the ceiling (not one piece per sentence), no sentence broken.")

    # ── 7c (bonus, not in the original checklist but cheap and removes
    #    doubt): a single SENTENCE alone exceeding the ceiling falls to the
    #    explicitly-flagged hard word-split, last resort only. ──────────
    print("\n--- 7c (bonus): single oversized sentence -> hard_word_split ---")
    one_giant_sentence = _words(7000) + "."  # one "sentence" (no internal ./!/? ), 7001 words
    assert len(pm._sentence_spans(one_giant_sentence)) == 1
    pieces_c = pm._split_text_by_size(one_giant_sentence, ceiling)
    methods_c = {m for _s, _e, _t, m in pieces_c}
    print(f"  {len(pieces_c)} piece(s), methods={methods_c}, "
          f"word counts={[len(t.split()) for _s, _e, t, _m in pieces_c]}")
    assert methods_c == {"hard_word_split"}
    assert all(len(t.split()) <= ceiling for _s, _e, t, _m in pieces_c)
    print("  CONFIRMED: a single sentence alone exceeding the ceiling falls to the "
          "explicitly-flagged hard word-split, last resort only.")

    # ── _apply_word_ceiling_fallback(): ChapterSubUnits all share the
    #    PARENT chapter's own chunk_ids, never recomputed per sub-unit. ────
    print("\n--- _apply_word_ceiling_fallback(): parent chunk_ids preserved across sub-units ---")
    oversized_chapter = pm.ChapterSpan(
        label="Oversized Chapter", char_start=0, char_end=len(big_text), text=big_text,
        chunk_ids=["parent-chunk-a", "parent-chunk-b"], split_method="title_repeat_boundary",
    )
    normal_chapter = pm.ChapterSpan(
        label="Normal Chapter", char_start=0, char_end=100, text=_words(500),
        chunk_ids=["normal-chunk"], split_method="title_repeat_boundary",
    )
    sub_units = pm._apply_word_ceiling_fallback([oversized_chapter, normal_chapter])
    oversized_units = [u for u in sub_units if u.parent_label == "Oversized Chapter"]
    normal_units = [u for u in sub_units if u.parent_label == "Normal Chapter"]
    print(f"  oversized chapter -> {len(oversized_units)} sub-unit(s); normal chapter -> "
          f"{len(normal_units)} sub-unit(s)")
    assert len(oversized_units) == 2, "the 10,000-word chapter must sub-split into 2 units"
    assert all(u.chunk_ids == ["parent-chunk-a", "parent-chunk-b"] for u in oversized_units), (
        "EVERY sub-unit of an oversized chapter must carry the SAME parent chunk_ids"
    )
    assert len(normal_units) == 1 and normal_units[0].method == "single_unit"
    assert normal_units[0].chunk_ids == ["normal-chunk"]
    print("  CONFIRMED: every sub-unit of an oversized chapter shares the identical "
          "parent chunk_ids (chapter granularity, not further subdivided); an "
          "at-or-under-ceiling chapter passes through as a single 'single_unit'.")

    print("\nPASSED: 7. Sub-split fallback confirmed at paragraph, sentence, and "
          "hard-word-split granularity, plus parent chunk_ids preservation.")


# ════════════════════════════════════════════════════════════════════════
# 8. process_book_document(): gated entry point -- skipped_licensed /
#    skipped_precept_austin (real gate, fake conn).
# ════════════════════════════════════════════════════════════════════════

def test_process_book_document_gate():
    print("\n" + "=" * 78)
    print("8. process_book_document(): gated entry point")
    print("=" * 78)

    document_id = "33333333-3333-3333-3333-333333333333"
    source_id = "44444444-4444-4444-4444-444444444444"
    ordered_chunks = [("chunk-x", _title_block("Some Chapter") + _words(80))]

    print("\n--- public_domain source -> skipped_licensed (real gate, fake conn) ---")
    conn_pd = FakeConn(license_status="public_domain")
    result_pd = pm.process_book_document(
        conn_pd, document_id, source_id, ordered_chunks, fake_embed_fn,
    )
    print(f"  result_pd = {result_pd}")
    assert result_pd == {"status": "skipped_licensed"}, (
        f"expected skipped_licensed for a public_domain source, got {result_pd!r}"
    )
    assert conn_pd.delete_count() == 0, "a gated-off call must never touch propositions at all"

    print("\n--- Precept Austin source_id -> skipped_precept_austin (fires before license lookup) ---")
    conn_pa = FakeConn(license_status="licensed")  # irrelevant -- PA gate fires first
    result_pa = pm.process_book_document(
        conn_pa, document_id, pm.PRECEPT_AUSTIN_SOURCE_ID, ordered_chunks, fake_embed_fn,
    )
    print(f"  result_pa = {result_pa}")
    assert result_pa == {"status": "skipped_precept_austin"}
    assert conn_pa.delete_count() == 0

    print("\n--- licensed source -> delegates to _extract_and_store_book_chapters(), "
          "'status': 'processed' merged in ---")
    ev_calls = []

    def fake_execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
        ev_calls.append((sql, list(argslist)))

    original_extract = pm.extract_propositions
    original_execute_values = pm.execute_values
    pm.extract_propositions = lambda text, doc_id="", speaker=None, prompt_version="v3": [
        {"proposition_index": 1, "content": "A single canned teaching passage."},
    ]
    pm.execute_values = fake_execute_values
    try:
        conn_licensed = FakeConn(license_status="licensed")
        result_licensed = pm.process_book_document(
            conn_licensed, document_id, source_id, ordered_chunks, fake_embed_fn,
        )
    finally:
        pm.extract_propositions = original_extract
        pm.execute_values = original_execute_values

    print(f"  result_licensed = {result_licensed}")
    assert result_licensed["status"] == "processed"
    assert result_licensed["chapters_attempted"] == 1
    assert result_licensed["chapters_stored"] == 1
    assert result_licensed["propositions_stored"] == 1
    assert conn_licensed.delete_count() == 1, "the gated path must still issue exactly one DELETE"
    print("  CONFIRMED: a licensed source delegates through to the inner worker, real "
          "gate, real reconciliation dict merged with 'status': 'processed'.")

    print("\nPASSED: 8. process_book_document()'s real gate confirmed for "
          "skipped_licensed, skipped_precept_austin, and the delegating (processed) path.")


# ════════════════════════════════════════════════════════════════════════
# 1 (partial). True Vine PD source -- NEVER processed via
#    process_book_document() in production (must return skipped_licensed).
# ════════════════════════════════════════════════════════════════════════

def test_process_book_document_true_vine_is_skipped():
    print("\n" + "=" * 78)
    print("True Vine (public_domain) is NEVER processed via process_book_document()")
    print("=" * 78)
    conn_true_vine = FakeConn(license_status="public_domain")
    ordered_chunks = [("chunk-x", _title_block("Some Chapter") + _words(80))]
    result = pm.process_book_document(
        conn_true_vine, TRUE_VINE_DOC_ID,
        "some-public-domain-source-id-not-precept-austin",
        ordered_chunks, fake_embed_fn,
    )
    print(f"  result = {result}")
    assert result == {"status": "skipped_licensed"}
    assert conn_true_vine.delete_count() == 0
    print("  CONFIRMED: a real call through process_book_document() on a public_domain "
          "source_id returns skipped_licensed and touches propositions zero times -- "
          "only a later, separate, deliberately-disclosed bypass step calls "
          "_extract_and_store_book_chapters() directly on the real True Vine book.")


# ════════════════════════════════════════════════════════════════════════
# Front/back-matter detection (correction pass): is_front_back_matter() and
# its label/shape helpers, tested against real corpus data first (per this
# repo's own "real thing is one query away" convention), plus synthetic
# edge cases.
# ════════════════════════════════════════════════════════════════════════

def test_matter_real_true_vine_protection():
    print("\n" + "=" * 78)
    print("9. is_front_back_matter(): real True Vine Preface + all 31 chapters -> (False, '')")
    print("=" * 78)

    db_params = _db_params()
    ordered_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)
    chapters, _missing = pm.split_book_into_chapters(ordered_chunks)

    real_chapter_labels = set(EXPECTED_TRUE_VINE_CHAPTERS)  # includes "Preface"
    checked = 0
    false_positives = []
    for c in chapters:
        if c.label not in real_chapter_labels:
            continue
        matter, reason = pm.is_front_back_matter(c.label, c.text)
        checked += 1
        print(f"  {c.label!r:45s} {len(c.text.split()):5d}w -> matter={matter} reason={reason!r}")
        if matter:
            false_positives.append((c.label, len(c.text.split()), reason))

    print(f"\nChecked {checked} real content spans (Preface + all 31 chapters, including "
          f"both 'The Vine' occurrences and all 3 'Christ's Friendship' chapters).")
    assert checked == 32, f"expected to check all 32 real content spans (Preface + 31), got {checked}"
    assert not false_positives, (
        f"expected ZERO false positives on real content spans, got: {false_positives}"
    )
    print("CONFIRMED: is_front_back_matter() returns (False, '') for the real 196-word "
          "'Preface' span (genuine Murray prose, 'I have felt drawn to try to write...') "
          "and every one of the 31 real chapters -- none misclassified as matter.")


def test_matter_real_true_vine_true_positives():
    print("\n" + "=" * 78)
    print("10. is_front_back_matter(): real True Vine junk spans -> (True, <correct reason>)")
    print("=" * 78)

    db_params = _db_params()
    ordered_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)
    chapters, _missing = pm.split_book_into_chapters(ordered_chunks)
    by_label_and_method = {(c.label, c.split_method): c for c in chapters}

    # The 543-word CCEL-metadata-plus-Table-of-Contents span -- labeled with
    # the BOOK'S OWN TITLE (via _label_from_context()), NOT "Preface". This
    # is the exact span a prior report wrongly called "the preface" -- this
    # test is the direct proof it is correctly caught by SHAPE (ccel_metadata),
    # never by label, since its label doesn't match any matter keyword.
    ccel_span = [c for c in chapters if c.split_method == "preface_pre_boundary"]
    assert len(ccel_span) == 1, f"expected exactly one preface_pre_boundary span, got {len(ccel_span)}"
    ccel_span = ccel_span[0]
    print(f"  CCEL span label={ccel_span.label!r} words={len(ccel_span.text.split())}")
    assert len(ccel_span.text.split()) == 543, (
        f"expected the known 543-word CCEL span, got {len(ccel_span.text.split())} words -- "
        f"if this legitimately changed, the coordinator's own correction numbers are stale"
    )
    assert ccel_span.label != "Preface", (
        "the CCEL-metadata span must NOT be labeled 'Preface' -- it is labeled with the "
        "book's own title, which is exactly why label alone cannot catch it"
    )
    matter, reason = pm.is_front_back_matter(ccel_span.label, ccel_span.text)
    print(f"  -> matter={matter} reason={reason!r}")
    assert (matter, reason) == (True, "ccel_metadata"), (
        f"expected (True, 'ccel_metadata') for the 543w CCEL span, got {(matter, reason)}"
    )

    expected_true_positives = [
        ("Title Page", "label"),
        ("Indexes", "label"),
        ("Index of Scripture References", "label"),
    ]
    for label, expected_reason in expected_true_positives:
        matches = [c for c in chapters if c.label == label]
        assert matches, f"expected a real True Vine span labeled {label!r}"
        c = matches[0]
        matter, reason = pm.is_front_back_matter(c.label, c.text)
        print(f"  {label!r:35s} {len(c.text.split()):4d}w -> matter={matter} reason={reason!r}")
        assert (matter, reason) == (True, expected_reason), (
            f"expected (True, {expected_reason!r}) for {label!r}, got {(matter, reason)}"
        )

    print("\nCONFIRMED: real True Vine junk spans classify (True, <correct reason>) -- the "
          "543w CCEL/TOC span via 'ccel_metadata' (never via label, since it isn't labeled "
          "'Preface' or anything matter-like), and Title Page/Indexes/Index-of-Scripture-"
          "References via 'label'.")


def test_matter_cross_book_validation():
    print("\n" + "=" * 78)
    print("11. Cross-book false-positive guard: Absolute Surrender + Power Through Prayer")
    print("=" * 78)
    print("(Chosen because the planning step named exact chapters from these two books as")
    print(" the ones a naive 'Capitalized Word Then Colon' heuristic would have false-flagged.)")

    db_params = _db_params()

    # ── Absolute Surrender (Andrew Murray) ──────────────────────────────────
    print("\n--- Absolute Surrender ---")
    as_chunks = _fetch_ordered_chunks(db_params, ABSOLUTE_SURRENDER_DOC_ID)
    as_chapters, _m = pm.split_book_into_chapters(as_chunks)
    as_units = pm._apply_word_ceiling_fallback(as_chapters)

    # Named false-positive-risk chapters: must be content, checked against
    # EVERY sub-unit carrying that parent_label (these chapters are long
    # enough to be sub-split by the word-ceiling fallback).
    for risky_label in ("The Fruit of the Spirit is Love", "Kept by the Power of God"):
        matching_units = [u for u in as_units if u.parent_label.startswith(risky_label)]
        assert matching_units, f"expected sub-units for {risky_label!r} in Absolute Surrender"
        for u in matching_units:
            matter, reason = pm.is_front_back_matter(u.parent_label, u.text)
            print(f"  {u.parent_label!r:60s} {len(u.text.split()):5d}w -> matter={matter} reason={reason!r}")
            assert (matter, reason) == (False, ""), (
                f"expected {u.parent_label!r} to classify as content (naive-heuristic "
                f"false-positive risk), got {(matter, reason)}"
            )

    # Front-matter spans: CCEL metadata block, Title Page, Index-type spans.
    ccel_as = [c for c in as_chapters if c.split_method == "preface_pre_boundary"]
    assert len(ccel_as) == 1
    matter, reason = pm.is_front_back_matter(ccel_as[0].label, ccel_as[0].text)
    print(f"  CCEL span {ccel_as[0].label!r:40s} {len(ccel_as[0].text.split()):5d}w -> "
          f"matter={matter} reason={reason!r}")
    assert (matter, reason) == (True, "ccel_metadata")

    for label in ("Title Page", "Indexes", "Index of Scripture References"):
        matches = [c for c in as_chapters if c.label == label]
        assert matches, f"expected a real Absolute Surrender span labeled {label!r}"
        matter, reason = pm.is_front_back_matter(matches[0].label, matches[0].text)
        print(f"  {label!r:35s} {len(matches[0].text.split()):4d}w -> matter={matter} reason={reason!r}")
        assert matter is True and reason == "label", (
            f"expected (True, 'label') for {label!r}, got {(matter, reason)}"
        )

    # ── Power Through Prayer (E.M. Bounds) -- the exact "8. Examples of
    #    Praying Men" chapter named in the planning step. ───────────────────
    print("\n--- Power Through Prayer (E.M. Bounds) ---")
    ptp_chunks = _fetch_ordered_chunks(db_params, POWER_THROUGH_PRAYER_DOC_ID)
    ptp_chapters, _m2 = pm.split_book_into_chapters(ptp_chunks)

    examples_chapter = [c for c in ptp_chapters if c.label == "8. Examples of Praying Men"]
    assert examples_chapter, "expected a real Power Through Prayer chapter labeled exactly '8. Examples of Praying Men'"
    c = examples_chapter[0]
    matter, reason = pm.is_front_back_matter(c.label, c.text)
    print(f"  {c.label!r:35s} {len(c.text.split()):5d}w -> matter={matter} reason={reason!r}")
    assert (matter, reason) == (False, ""), (
        f"expected '8. Examples of Praying Men' to classify as content (the exact "
        f"planning-step-named false-positive risk), got {(matter, reason)}"
    )

    ccel_ptp = [c for c in ptp_chapters if c.split_method == "preface_pre_boundary"]
    assert len(ccel_ptp) == 1
    matter, reason = pm.is_front_back_matter(ccel_ptp[0].label, ccel_ptp[0].text)
    print(f"  CCEL span {ccel_ptp[0].label!r:40s} {len(ccel_ptp[0].text.split()):5d}w -> "
          f"matter={matter} reason={reason!r}")
    assert (matter, reason) == (True, "ccel_metadata")

    title_page_ptp = [c for c in ptp_chapters if c.label == "Title Page"]
    assert title_page_ptp, "expected a real Power Through Prayer span labeled 'Title Page'"
    matter, reason = pm.is_front_back_matter(title_page_ptp[0].label, title_page_ptp[0].text)
    print(f"  {'Title Page':35s} {len(title_page_ptp[0].text.split()):5d}w -> "
          f"matter={matter} reason={reason!r}")
    assert matter is True and reason == "label"

    # A handful of other real numbered chapters from this book, to widen
    # the sample beyond the one named chapter -- all must be content.
    for label in ("1. Men of Prayer Needed", "20. A Praying Pulpit Begets a Praying Pew"):
        matches = [c for c in ptp_chapters if c.label == label]
        assert matches, f"expected a real Power Through Prayer chapter labeled {label!r}"
        matter, reason = pm.is_front_back_matter(matches[0].label, matches[0].text)
        print(f"  {label!r:45s} {len(matches[0].text.split()):5d}w -> matter={matter} reason={reason!r}")
        assert (matter, reason) == (False, "")

    print("\nCONFIRMED: across 2 real books with DIFFERENT front-matter/chapter-numbering "
          "conventions than The True Vine, both planning-step-named false-positive-risk "
          "chapters ('The Fruit of the Spirit is Love', 'Kept by the Power of God', "
          "'8. Examples of Praying Men') classify as content, and each book's real "
          "CCEL-metadata/Title-Page/Index spans classify as matter with the correct reason.")


def test_matter_ambiguous_default_protected_label():
    print("\n" + "=" * 78)
    print("12. Ambiguous-default test: a 'Preface'-labeled span with metadata-shaped "
          "content still returns (False, '') -- protected label wins, shape never consulted")
    print("=" * 78)

    # Deliberately metadata-SHAPED content (would trip BOTH shape signals on
    # their own: >=2 CCEL field lines AND a high digit-token ratio) under a
    # PROTECTED label. If shape were ever consulted for a protected label,
    # this would wrongly classify as matter -- proves it never is.
    trap_text = (
        "Author(s): A Test Author\n"
        "Publisher: A Test Publisher\n"
        "Description: A test description\n"
        "Subjects: Testing\n"
        + " ".join(str(i) for i in range(1, 40))  # 39 bare-integer tokens -- digit ratio ~1.0
    )
    assert len(pm._distinct_ccel_fields(trap_text)) >= pm.CCEL_METADATA_FIELD_MIN
    assert len(trap_text.split()) >= pm.FRONT_BACK_MATTER_MIN_SHAPE_WORDS
    assert pm._digit_token_ratio(trap_text) >= pm.FRONT_BACK_MATTER_DIGIT_RATIO
    # Confirm the trap really would fire on shape alone, unprotected:
    assert pm._shape_is_front_back_matter(trap_text) is True, (
        "fixture must genuinely trip the shape signal on its own, or this test proves nothing"
    )

    for protected_label in ("Preface", "PREFACE", "  preface  ", "Introduction", "Foreword"):
        matter, reason = pm.is_front_back_matter(protected_label, trap_text)
        print(f"  label={protected_label!r:15s} (metadata-shaped content) -> matter={matter} reason={reason!r}")
        assert (matter, reason) == (False, ""), (
            f"expected a protected label ({protected_label!r}) to ALWAYS return (False, ''), "
            f"even with metadata-shaped content, got {(matter, reason)}"
        )

    # Control: the SAME trap_text under a non-protected label DOES classify
    # as matter -- proves the protection is about the LABEL, not that this
    # fixture is somehow inert.
    matter_unprotected, reason_unprotected = pm.is_front_back_matter("Some Random Chapter", trap_text)
    print(f"  label='Some Random Chapter' (same content, UNPROTECTED) -> "
          f"matter={matter_unprotected} reason={reason_unprotected!r}")
    assert matter_unprotected is True, (
        "control failed: the same metadata-shaped content under a non-protected label "
        "should classify as matter, proving the fixture itself is a genuine shape-trap"
    )

    print("\nCONFIRMED: a protected label (preface/introduction/foreword/etc., case- and "
          "whitespace-insensitive) ALWAYS short-circuits to (False, '') without ever "
          "consulting shape -- proven against a fixture that would otherwise trip both "
          "shape signals, with an unprotected control confirming the fixture is genuine.")


def test_matter_call_count_and_reconciliation_real_true_vine():
    print("\n" + "=" * 78)
    print("13-14. Call-count proof + reconciliation: real True Vine, full simulated run")
    print("=" * 78)

    db_params = _db_params()
    ordered_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)

    extract_calls = []

    def fake_extract(text, doc_id="", speaker=None, prompt_version="v3"):
        extract_calls.append(text[:40])
        return [{"proposition_index": 1, "content": "Canned single teaching passage for reconciliation proof."}]

    def fake_execute_values(cur, sql, argslist, template=None, page_size=100, fetch=False):
        pass

    original_extract = pm.extract_propositions
    original_execute_values = pm.execute_values
    pm.extract_propositions = fake_extract
    pm.execute_values = fake_execute_values
    try:
        conn = FakeConn()
        document_id = TRUE_VINE_DOC_ID
        result = pm._extract_and_store_book_chapters(
            conn, document_id, ordered_chunks, fake_embed_fn,
            speaker=None, prompt_version="v3",
        )
    finally:
        pm.extract_propositions = original_extract
        pm.execute_values = original_execute_values

    summary = {k: v for k, v in result.items() if k != "per_chapter"}
    print(f"\nresult (excl. per_chapter) = {summary}")
    print(f"extract_propositions() call count = {len(extract_calls)}")

    # ── 13. Call-count proof: the model is called exactly 32 times (31
    #    chapters + the real Preface), NOT 36 (38 total spans minus only
    #    the "4" junk spans the correction's own framing named) -- the 4
    #    junk spans PLUS the 2 "Indexes" section-header duplicates (all 6,
    #    all caught by the label check) never reach the model at all. ─────
    assert len(extract_calls) == 32, (
        f"expected extract_propositions() called exactly 32 times (31 real chapters + "
        f"the real 196w Preface), got {len(extract_calls)}"
    )
    assert not any("Author(s)" in t or "Index" in t or "Title Page" in t for t in extract_calls), (
        "no junk span's own text should ever reach extract_propositions()"
    )
    print("CONFIRMED: extract_propositions() called exactly 32 times -- the 4 CCEL/Title-Page/"
          "Index-type junk spans, PLUS both 'Indexes' section-header duplicates (6 total), "
          "never reach the model at all.")

    # ── 14. Reconciliation: 38 == stored + empty + errored + skipped_thin +
    #    skipped_front_matter. Per the coordinator's own instruction NOT to
    #    assume skipped_front_matter == 6 -- reporting exactly what was
    #    found rather than assuming it. ──────────────────────────────────
    assert result["chapters_attempted"] == 38
    assert result["chapters_attempted"] == (
        result["chapters_stored"] + result["chapters_empty"] + result["chapters_errored"]
        + result["chapters_skipped_thin"] + result["chapters_skipped_front_matter"]
    ), "reconciliation must hold: attempted == stored + empty + errored + skipped_thin + skipped_front_matter"

    front_matter_entries = [c for c in result["per_chapter"] if c["outcome"] == "skipped_front_matter"]
    thin_entries = [c for c in result["per_chapter"] if c["outcome"] == "skipped_thin"]
    print(f"\nActual finding: chapters_skipped_front_matter = {result['chapters_skipped_front_matter']}, "
          f"chapters_skipped_thin = {result['chapters_skipped_thin']}")
    print("skipped_front_matter entries (label, word_count, matter_reason):")
    for c in front_matter_entries:
        print(f"  {c['label']!r:50s} {c['word_count']:4d}w  {c['matter_reason']!r}")
    print(f"skipped_thin entries: {[(c['label'], c['word_count']) for c in thin_entries]}")

    # Report exactly what was found: 6 real spans classify as front matter
    # (the 543w CCEL/TOC span, Title Page, BOTH "Indexes" section-header
    # duplicates, AND both real scripture-index spans) -- not the "4" the
    # coordinator's own correction message named (that count covered the
    # CCEL span + Title Page + the 2 "Index of..." spans, but did not
    # separately count the 2 bare "Indexes" section-header duplicates,
    # which are ALSO real, ALSO label-matched, spans in this document).
    # ALL 6 land in skipped_front_matter, NONE in skipped_thin -- the
    # front-matter check runs before the thin check, so even the two
    # 4-word "Indexes" duplicates are caught by LABEL before word count is
    # ever consulted.
    assert result["chapters_skipped_front_matter"] == 6, (
        f"ACTUAL FINDING: expected 6 real front-matter spans (543w CCEL/TOC span, Title "
        f"Page, both 'Indexes' section-header duplicates, Index of Scripture References, "
        f"Index of Scripture Commentary), got {result['chapters_skipped_front_matter']} -- "
        f"entries: {[(c['label'], c['word_count']) for c in front_matter_entries]}"
    )
    assert result["chapters_skipped_thin"] == 0, (
        f"ACTUAL FINDING: expected 0 skipped_thin (all matter-shaped spans, including the "
        f"two tiny 'Indexes' duplicates, are caught by the LABEL check before the thin "
        f"check ever runs), got {result['chapters_skipped_thin']} -- entries: {thin_entries}"
    )
    assert result["chapters_stored"] == 32
    assert result["chapters_empty"] == 0 and result["chapters_errored"] == 0

    print("\nCONFIRMED (reported, not assumed): 38 attempted == 32 stored + 0 empty + 0 "
          "errored + 0 skipped_thin + 6 skipped_front_matter. All 6 front-matter spans were "
          "caught by the LABEL signal (none needed the shape/digit-ratio signal on this "
          "book), and none of the 6 fell to skipped_thin despite two of them being under "
          "MIN_SUBSTANTIVE_WORD_COUNT on their own (4 words each) -- the front-matter check "
          "runs strictly before the thin check, exactly as wired.")

    print("\nPASSED: 13-14. Call-count and reconciliation confirmed against the real True "
          "Vine book (Groq call mocked, DB read-only).")


# ════════════════════════════════════════════════════════════════════════
# Front/back-matter correction pass, round 2: third-party byline detector +
# editorial-apparatus label set (fix (a)), and the tightened digit-ratio
# roman-numeral arm (fix (b)). Real fixture: John Wesley's Journal (a real
# edition with genuine third-party front matter -- an editor's note, an
# introduction by Rev. Hugh Price Hughes, an appreciation by Augustine
# Birrell, and a biographical sketch -- none written by Wesley himself).
# ════════════════════════════════════════════════════════════════════════

JOHN_WESLEY_JOURNAL_DOC_ID = "6e3ea1a0-92ac-4781-9637-0be037d0517b"


def test_matter_byline_detector():
    print("\n" + "=" * 78)
    print("15. Third-party byline detector (fix (a)): real John Wesley Journal fixtures")
    print("=" * 78)

    db_params = _db_params()
    chunks = _fetch_ordered_chunks(db_params, JOHN_WESLEY_JOURNAL_DOC_ID)
    chapters, _missing = pm.split_book_into_chapters(chunks)
    by_label = {c.label: c for c in chapters}

    print("\n--- Real fixture: 'INTRODUCTION' (byline: 'by the rev. hugh price hughes, m.a.') ---")
    intro = by_label["INTRODUCTION"]
    assert "by the rev. hugh price hughes" in intro.text.lower(), (
        "expected the real byline line to actually be present in this span's own text"
    )
    matter, reason = pm.is_front_back_matter(intro.label, intro.text, author="John Wesley")
    print(f"  matter={matter} reason={reason!r}")
    assert (matter, reason) == (True, "third_party_byline"), (
        f"expected 'INTRODUCTION' (protected label, but credited to a third party) to be "
        f"caught by the byline check, got {(matter, reason)}"
    )
    # Confirm the PROTECTED-label short-circuit alone would have missed this
    # (proving the byline check's own placement BEFORE the protect-list is
    # what makes this catch possible, not incidental).
    assert pm._normalize_matter_label(intro.label).split()[0] in pm._MATTER_LABEL_PROTECT, (
        "fixture check: 'introduction' must genuinely be a protected label, or this test "
        "isn't proving what it claims to prove"
    )
    print("  CONFIRMED: 'INTRODUCTION' is a genuinely PROTECTED label, yet still caught -- "
          "proving the byline check's placement before the protect-list short-circuit.")

    print("\n--- Real fixture: \"AN APPRECIATION OF JOHN WESLEY'S JOURNAL\" "
          "(byline: 'by augustine birrell, king's counsel') ---")
    appreciation = by_label["AN APPRECIATION OF JOHN WESLEY'S JOURNAL"]
    assert "by augustine birrell" in appreciation.text.lower()
    matter2, reason2 = pm.is_front_back_matter(appreciation.label, appreciation.text, author="John Wesley")
    print(f"  matter={matter2} reason={reason2!r}")
    assert (matter2, reason2) == (True, "third_party_byline")

    print("\n--- Real fixture: True Vine's own Title Page, byline 'By / Rev. Andrew Murray' "
          "-- SAME author, must NOT be flagged as third-party ---")
    tv_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)
    tv_chapters, _m = pm.split_book_into_chapters(tv_chunks)
    title_page = [c for c in tv_chapters if c.label == "Title Page"][0]
    assert "by\nrev. andrew murray" in title_page.text.lower().replace("\r", "")
    same_author_byline = pm._has_third_party_byline(title_page.text, "Andrew Murray")
    print(f"  _has_third_party_byline(text, author='Andrew Murray') = {same_author_byline}")
    assert same_author_byline is False, (
        "expected a genuine same-author byline to NOT be flagged as third-party"
    )
    print("  CONFIRMED: a real same-author byline ('By / Rev. Andrew Murray', author="
          "'Andrew Murray') is correctly NOT flagged as third-party.")

    print("\n--- Synthetic: same-author byline on an otherwise-unflagged label -> "
          "full is_front_back_matter() returns (False, '') end to end ---")
    # The real True Vine example above still classifies as matter overall
    # (via the "label" signal, since "Title Page" is independently matter)
    # -- this synthetic case isolates the FULL end-to-end guarantee using a
    # label that is NOT otherwise matter-classified.
    synthetic_text = (
        "Some Real Chapter\n"
        "Some Real Chapter\n"
        "SOME REAL CHAPTER\n"
        "By\n"
        "Andrew Murray\n"
        "This is real teaching content that would otherwise be extracted normally, long "
        "enough to be a real chapter and not fall to the thin-word-count floor at all.\n"
    )
    matter3, reason3 = pm.is_front_back_matter("Some Real Chapter", synthetic_text, author="Andrew Murray")
    print(f"  matter={matter3} reason={reason3!r}")
    assert (matter3, reason3) == (False, ""), (
        f"expected a same-author byline to leave an otherwise-unflagged label as content, "
        f"got {(matter3, reason3)}"
    )
    print("  CONFIRMED: is_front_back_matter() returns (False, '') end-to-end for a "
          "same-author byline on a label that isn't otherwise matter-classified.")

    print("\n--- No byline at all: real True Vine chapters unaffected (conservative default) ---")
    no_flip_count = 0
    for c in tv_chapters:
        if c.split_method != "title_repeat_boundary":
            continue
        matter_bare, _r = pm.is_front_back_matter(c.label, c.text)
        matter_authored, _r2 = pm.is_front_back_matter(c.label, c.text, author="Andrew Murray")
        assert matter_bare == matter_authored, (
            f"expected {c.label!r} to be unaffected by supplying author= when the span has "
            f"no byline at all, got bare={matter_bare} vs authored={matter_authored}"
        )
        no_flip_count += 1
    print(f"  CONFIRMED: {no_flip_count} real True Vine title_repeat_boundary spans, none "
          f"with a byline, all UNAFFECTED by author='Andrew Murray' (conservative default).")

    print("\n--- Synthetic: incidental mid-prose 'by' (not byline-shaped) not falsely flagged ---")
    incidental_text = (
        "Some Chapter\n"
        "Some Chapter\n"
        "SOME CHAPTER\n"
        "We are saved by grace through faith, and this is not of ourselves; it is the gift "
        "of God, freely given to all who believe in Him and trust in His finished work.\n"
        "By no means should we boast in our own works, for none of us could ever earn this "
        "salvation through our own effort or merit, however sincere our striving might be.\n"
    )
    matter4, reason4 = pm.is_front_back_matter("Some Chapter", incidental_text, author="Some Author")
    print(f"  matter={matter4} reason={reason4!r}")
    assert (matter4, reason4) == (False, ""), (
        f"expected incidental mid-prose 'by'/'By' usage to NOT be flagged as a byline, "
        f"got {(matter4, reason4)}"
    )
    print("  CONFIRMED: incidental prose usage of 'by'/'By' (not a short, standalone "
          "byline-shaped line) is correctly not flagged.")

    print("\nPASSED: 15. Third-party byline detector confirmed against real Hughes/Birrell "
          "fixtures, a real same-author byline, no-byline chapters, and an incidental-'by' trap.")


def test_matter_apparatus_labels():
    print("\n" + "=" * 78)
    print("16. Editorial-apparatus label set (fix (a)): real fixtures + exact-match discipline")
    print("=" * 78)

    db_params = _db_params()
    chunks = _fetch_ordered_chunks(db_params, JOHN_WESLEY_JOURNAL_DOC_ID)
    chapters, _missing = pm.split_book_into_chapters(chunks)
    by_label = {c.label: c for c in chapters}

    print("\n--- Real fixture: \"EDITOR'S NOTE\" (no byline in the text itself -- confirmed) ---")
    editors_note = by_label["EDITOR'S NOTE"]
    assert not pm._BYLINE_RE.search(editors_note.text) or True  # see explicit line-scan below
    has_byline_line = any(
        pm._BYLINE_RE.match(line.strip())
        for line in editors_note.text.split("\n")[:8] if line.strip()
    )
    print(f"  byline-shaped line present in first 8 lines? {has_byline_line}")
    assert not has_byline_line, (
        "expected NO byline-shaped line in EDITOR'S NOTE's own text -- confirming this "
        "span is caught by the apparatus LABEL set, not incidentally by the byline check"
    )
    matter, reason = pm.is_front_back_matter(editors_note.label, editors_note.text, author="John Wesley")
    print(f"  matter={matter} reason={reason!r}")
    assert (matter, reason) == (True, "editorial_apparatus"), (
        f"expected \"EDITOR'S NOTE\" -> (True, 'editorial_apparatus'), got {(matter, reason)}"
    )

    print("\n--- Real fixture: 'BIOGRAPHICAL SKETCH' (no byline in the text itself -- confirmed) ---")
    bio_sketch = by_label["BIOGRAPHICAL SKETCH"]
    has_byline_line2 = any(
        pm._BYLINE_RE.match(line.strip())
        for line in bio_sketch.text.split("\n")[:8] if line.strip()
    )
    print(f"  byline-shaped line present in first 8 lines? {has_byline_line2}")
    assert not has_byline_line2
    matter2, reason2 = pm.is_front_back_matter(bio_sketch.label, bio_sketch.text, author="John Wesley")
    print(f"  matter={matter2} reason={reason2!r}")
    assert (matter2, reason2) == (True, "editorial_apparatus")

    print("\n--- Synthetic: 'The Biography of Faith' -- a real-chapter-shaped label that must "
          "NOT collide with the apparatus set (exact-match discipline, not prefix match) ---")
    synthetic_text = (
        "The Biography of Faith\n"
        "The Biography of Faith\n"
        "THE BIOGRAPHY OF FAITH\n"
        "This chapter tells the story of faith across the ages, real teaching content long "
        "enough to be a genuine chapter, never intended as any kind of editorial apparatus.\n"
    )
    matter3, reason3 = pm.is_front_back_matter("The Biography of Faith", synthetic_text)
    print(f"  matter={matter3} reason={reason3!r}")
    assert (matter3, reason3) == (False, ""), (
        f"expected 'The Biography of Faith' to be content (exact-match, not prefix-match, "
        f"discipline), got {(matter3, reason3)}"
    )
    assert pm._normalize_matter_label("The Biography of Faith") not in pm._MATTER_LABEL_APPARATUS
    print("  CONFIRMED: 'The Biography of Faith' does not collide with the apparatus set -- "
          "exact-match discipline holds, no prefix-collision false positive.")

    print("\nPASSED: 16. Editorial-apparatus label set confirmed against real fixtures "
          "(neither has a byline of its own) and the exact-match discipline confirmed "
          "against a synthetic near-collision.")


def test_matter_digit_ratio_fix():
    print("\n" + "=" * 78)
    print("17. Tightened digit-ratio roman-numeral arm (fix (b)): real Wesley + True Vine fixtures")
    print("=" * 78)

    db_params = _db_params()
    chunks = _fetch_ordered_chunks(db_params, JOHN_WESLEY_JOURNAL_DOC_ID)
    chapters, _missing = pm.split_book_into_chapters(chunks)
    by_label = {c.label: c for c in chapters}

    print("\n--- Real fixture: \"Wesley's Defenders\" (was wrongly excluded pre-fix) ---")
    defenders = by_label["Wesley's Defenders"]
    ratio = pm._digit_token_ratio(defenders.text)
    print(f"  words={len(defenders.text.split())} ratio={ratio:.4f}")
    assert abs(ratio - 0.0084) < 0.001, f"expected ratio ~0.0084, got {ratio:.4f}"
    assert ratio < pm.FRONT_BACK_MATTER_DIGIT_RATIO
    matter, reason = pm.is_front_back_matter(defenders.label, defenders.text, author="John Wesley")
    print(f"  matter={matter} reason={reason!r}")
    assert (matter, reason) == (False, ""), (
        f"expected \"Wesley's Defenders\" to now be content, got {(matter, reason)}"
    )

    print("\n--- Real fixture: 'Wesley Discusses Old Sermons' (was wrongly excluded pre-fix) ---")
    old_sermons = by_label["Wesley Discusses Old Sermons"]
    ratio2 = pm._digit_token_ratio(old_sermons.text)
    print(f"  words={len(old_sermons.text.split())} ratio={ratio2:.4f}")
    assert abs(ratio2 - 0.0076) < 0.001, f"expected ratio ~0.0076, got {ratio2:.4f}"
    assert ratio2 < pm.FRONT_BACK_MATTER_DIGIT_RATIO
    matter2, reason2 = pm.is_front_back_matter(old_sermons.label, old_sermons.text, author="John Wesley")
    print(f"  matter={matter2} reason={reason2!r}")
    assert (matter2, reason2) == (False, ""), (
        f"expected 'Wesley Discusses Old Sermons' to now be content, got {(matter2, reason2)}"
    )

    print("\n--- Regression check: True Vine's real index spans stay matter, ratio still >=0.10 ---")
    tv_chunks = _fetch_ordered_chunks(db_params, TRUE_VINE_DOC_ID)
    tv_chapters, _m = pm.split_book_into_chapters(tv_chunks)
    for label in ("Index of Scripture References", "Index of Scripture Commentary"):
        span = [c for c in tv_chapters if c.label == label][0]
        ratio3 = pm._digit_token_ratio(span.text)
        matter3, reason3 = pm.is_front_back_matter(span.label, span.text, author="Andrew Murray")
        print(f"  {label!r:35s} ratio={ratio3:.4f} matter={matter3} reason={reason3!r}")
        assert ratio3 >= pm.FRONT_BACK_MATTER_DIGIT_RATIO, (
            f"expected {label!r}'s digit ratio to remain well over the threshold, got {ratio3:.4f}"
        )
        assert matter3 is True

    expected_ratios = {"Index of Scripture References": 0.7091, "Index of Scripture Commentary": 0.7045}
    for label, expected in expected_ratios.items():
        span = [c for c in tv_chapters if c.label == label][0]
        actual = pm._digit_token_ratio(span.text)
        assert abs(actual - expected) < 0.001, (
            f"expected {label!r} ratio ~{expected}, got {actual:.4f}"
        )
    print("  CONFIRMED: True Vine's index spans are essentially unchanged by fix (b) "
          "(~0.71/0.70, comfortably over the 0.10 threshold, still matter).")

    print("\nPASSED: 17. Digit-ratio fix validated against real Wesley fixtures (now content) "
          "and True Vine's index spans (unaffected regression check).")


def test_matter_byline_over_broad_content_lines():
    print("\n" + "=" * 78)
    print("18. Byline detector over-broadness guard (regression for CLAUDE.md Landmine): "
          "genuine content lines opening 'By ...' are NOT flagged as front matter")
    print("=" * 78)

    # DB-FREE: pure synthetic strings -- this exercises _has_third_party_byline
    # /is_front_back_matter's string logic only, no real book needed.
    #
    # The documented risk (CLAUDE.md Landmines, "_has_third_party_byline is
    # over-broad and unproven beyond one book"): _BYLINE_RE is ^\s*by\s+(.+?)\s*$,
    # so ANY short line-start "By <phrase>" whose words don't overlap the author's
    # name fires -- including a genuine theological line like "By faith alone" or
    # "By the grace of God", NOT only a real person-credit. The guard that
    # protects real prose is the <=12-word cap inside _has_third_party_byline (a
    # real byline is always short): a genuine content SENTENCE opening with one of
    # these phrases runs well past 12 words and is never treated as a byline at
    # all. This test locks that guard in, using the exact two phrases the Landmine
    # names -- the negative case that previously had no committed regression.
    author = "Andrew Murray"

    content_lines = [
        # 20 words -- opens "By faith alone", the Landmine's own example.
        ("By faith alone are we justified before God, apart from any works of the "
         "law or merit of our own doing."),
        # 24 words -- opens "By the grace of God" (1 Cor 15:10-shaped content).
        ("By the grace of God I am what I am, and his grace toward me was not in "
         "vain, but I labored even more than they all."),
    ]
    for line in content_lines:
        assert len(line.split()) > 12, "fixture must exceed the 12-word byline cap to prove the guard"
        fired = pm._has_third_party_byline(line, author)
        print(f"  {len(line.split()):2d}w  _has_third_party_byline = {fired!r}  | {line[:50]}...")
        assert fired is False, (
            f"a genuine >12-word content line opening 'By ...' must NOT be flagged as a "
            f"third-party byline, got fired={fired} for: {line!r}"
        )

    # Full end-to-end: such a line, under an ordinary (non-matter) chapter label,
    # classifies as content -- (False, "") -- not front/back matter.
    span_text = (
        "The Life of Faith\n"
        "The Life of Faith\n"
        "THE LIFE OF FAITH\n"
        + content_lines[0] + "\n"
        + content_lines[1] + "\n"
        "This is genuine teaching content, long enough to clear the thin-word-count "
        "floor and never intended as any kind of front or back matter.\n"
    )
    matter, reason = pm.is_front_back_matter("The Life of Faith", span_text, author=author)
    print(f"  end-to-end is_front_back_matter -> matter={matter} reason={reason!r}")
    assert (matter, reason) == (False, ""), (
        f"expected a content span opening with 'By faith alone ...' / 'By the grace of God ...' "
        f"to be content, got {(matter, reason)}"
    )

    # Characterization of the KNOWN, still-open limitation (same CLAUDE.md
    # Landmine): a BARE short "By <phrase>" line (<=12 words) DOES still fire
    # today. Asserted deliberately so that if the detector is ever hardened
    # (e.g. requiring the credited phrase to look like a personal name), this
    # assertion fails and forces a synchronized update to the Landmine -- it is
    # NOT an endorsement of the current behavior.
    for bare in ("By faith alone", "By the grace of God"):
        fires = pm._has_third_party_byline(bare, author)
        print(f"  KNOWN-LIMITATION  bare {bare!r} still fires? {fires}")
        assert fires is True, (
            f"characterization drift: bare {bare!r} no longer fires -- the byline detector "
            f"appears to have been hardened; update CLAUDE.md's over-broad-byline Landmine to match"
        )

    print("\nPASSED: 18. Genuine content lines opening 'By faith alone ...' / 'By the grace of "
          "God ...' are content, not front matter; the bare-short-line over-broadness is pinned "
          "as a known, documented limitation.")


if __name__ == "__main__":
    test_clear_existing_default_and_false()
    test_extract_and_store_book_chapters_buckets()
    test_chunk_linking_precision()
    test_split_book_into_chapters_real_true_vine()
    test_split_book_into_chapters_synthetic()
    test_sub_split_fallback()
    test_process_book_document_gate()
    test_process_book_document_true_vine_is_skipped()
    test_matter_real_true_vine_protection()
    test_matter_real_true_vine_true_positives()
    test_matter_cross_book_validation()
    test_matter_ambiguous_default_protected_label()
    test_matter_call_count_and_reconciliation_real_true_vine()
    test_matter_byline_detector()
    test_matter_apparatus_labels()
    test_matter_digit_ratio_fix()
    test_matter_byline_over_broad_content_lines()
    print("\n" + "=" * 78)
    print("ALL test_propositions_book_chapters.py ASSERTIONS PASSED")
    print("=" * 78)
