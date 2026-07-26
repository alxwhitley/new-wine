#!/usr/bin/env python3
"""
validate_closeness_check.py -- Phase 2/3 validation harness for
closeness_check.py (PLAN.md #45).

READ-ONLY. Every DB access in this file is a SELECT against sources,
source_aliases, documents, chunks, propositions. No table is written to.
Does not edit closeness_check.py, propositions.py, shared_ingest.py, or any
pipeline file -- it only imports closeness_check and measures.

Purpose: build a should-pass validation bucket (real proposition/source
pairs from the live corpus) and a should-flag validation bucket (real
source text, mechanically edited at known rates -- explicitly permitted for
floor derivation, see module docstring below), classify every pair through
closeness_check.classify(), and report distributions so a provisional
CONTAINMENT_FLOOR / RESIDUAL_TOO_LITTLE_CUTOFF can be derived empirically.
Does NOT edit those placeholder constants in closeness_check.py itself --
this script only measures and reports.

--------------------------------------------------------------------------
Source-text reconstruction -- the one hard requirement from review
--------------------------------------------------------------------------
Reconstructs a document's source text by concatenating chunks.content
(never chunks.rewritten_content -- that is a separate copyright-paraphrase
field written only by scripts/rewrite_sermons.py, and confirmed live in
this run to be NULL for every chunk belonging to the three teachers used
here) in chunk_index order. See main()'s printed spot-check for the
verbatim-source confirmation on one real document.

--------------------------------------------------------------------------
Should-flag bucket construction (Phase 2 spec)
--------------------------------------------------------------------------
R0/R1/R2 edit ladder: a FIXED, DETERMINISTIC, reproducible word-level edit
procedure (see apply_word_edits() below) -- never an LLM rewrite. R1 targets
a ~15% word-edit rate, R2 targets ~35%, both applied independently to the
same R0 (verbatim) span, not cumulatively.

R-run adversarial items: take a genuine should-pass pair already measured as
LOW containment (a real system-quality paraphrase, not a fresh LLM call --
no Groq extraction is performed anywhere in this file) and mechanically
splice one real, contiguous, largely non-exempt ~14-word run lifted
verbatim from that SAME document's source text onto the end of the
proposition text. Tests whether longest_common_run (the secondary signal)
catches what trigram containment, by construction, should still mostly
pass.

--------------------------------------------------------------------------
Constraints honored
--------------------------------------------------------------------------
Python 3.9 syntax (Optional[str], never str | None -- Invariant 1). SELECT
only, zero writes anywhere. Does not touch TEACHER_POSITION_SIMILARITY_FLOOR.
Does not call the Groq extractor or resume statement generation. Deterministic
throughout -- a fixed random.Random(SEED) is the only source of "randomness",
used solely for sampling which real DB rows to draw, never for the edit
ladder itself (which is 100% rate/stride-derived, no RNG at all).
"""

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import closeness_check as cc  # noqa: E402

SEED = 20260726  # today's date -- fixed, reported, reproducible

MAIN_TEACHER = "Vlad Savchuk"
AFORIST_TEACHER = "Leonard Ravenhill"

# Full-batch targets (Phase 2 spec). --smoke overrides these to a tiny
# single-digit run for the pre-full-batch mechanics check (Rule 2).
TARGET_MAIN_N = 50
TARGET_RAVENHILL_N = 15
TARGET_FLAG_SPANS = 15
TARGET_RUN_ITEMS = 5

SMOKE_MAIN_N = 3
SMOKE_RAVENHILL_N = 2
SMOKE_FLAG_SPANS = 2
SMOKE_RUN_ITEMS = 1

SPAN_TARGET_WORDS = 100
SPAN_MIN_RESIDUAL_FRACTION = 0.6  # >=60% of the span must survive exemption
RUN_TARGET_WORDS = 14  # >=12 required by spec; 14 raw words gives buffer
RUN_MIN_RESIDUAL_FRACTION = 0.7


# ── DB plumbing (mirrors test_closeness_check_unit_proof.py's convention) ──

def db_params() -> dict:
    db_url = __import__("os").environ.get("SUPABASE_DB_URL")
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


def connect():
    import psycopg2

    conn = psycopg2.connect(**db_params())
    conn.set_session(readonly=True, autocommit=True)
    return conn


# ── Bulk fetch (no N+1 -- one query per teacher for docs, one for chunks,
#    one for propositions; reconstruction happens once per document) ───────

def fetch_eligible_docs(conn, teacher_name: str, exclude_title_ilike: Optional[str] = None) -> List[Tuple[str, str]]:
    """One query. Returns [(document_id, title), ...] for docs with >=1
    chunk AND >=1 proposition, confirmed live (not trusted from any .md)."""
    with conn.cursor() as cur:
        sql = """
            SELECT d.id, d.title
            FROM documents d
            JOIN sources s ON s.id = d.source_id
            WHERE s.name = %s
              AND EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)
              AND EXISTS (SELECT 1 FROM propositions pr WHERE pr.document_id = d.id)
        """
        params = [teacher_name]
        if exclude_title_ilike:
            sql += " AND d.title NOT ILIKE %s"
            params.append(exclude_title_ilike)
        sql += " ORDER BY d.id"
        cur.execute(sql, params)
        return [(r[0], r[1]) for r in cur.fetchall()]


def fetch_chunks_bulk(conn, doc_ids: List[str]) -> Dict[str, List[str]]:
    """One query for ALL doc_ids. Returns document_id -> [content, ...] in
    chunk_index order. Reads chunks.content ONLY -- never rewritten_content."""
    if not doc_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT document_id, chunk_index, content, rewritten_content
               FROM chunks WHERE document_id = ANY(%s::uuid[])
               ORDER BY document_id, chunk_index""",
            (doc_ids,),
        )
        rows = cur.fetchall()
    by_doc: Dict[str, List[Tuple[int, str]]] = {}
    rewritten_nonnull = 0
    for doc_id, chunk_index, content, rewritten_content in rows:
        by_doc.setdefault(doc_id, []).append((chunk_index, content or ""))
        if rewritten_content is not None:
            rewritten_nonnull += 1
    if rewritten_nonnull:
        print(
            "WARNING: {0} chunk rows among sampled docs carry non-NULL "
            "rewritten_content (unused by this script; content column is "
            "still what was read).".format(rewritten_nonnull)
        )
    out: Dict[str, List[str]] = {}
    for doc_id, pairs in by_doc.items():
        pairs.sort(key=lambda t: t[0])
        out[doc_id] = [c for _, c in pairs]
    return out


def fetch_propositions_bulk(conn, doc_ids: List[str]) -> Dict[str, List[Tuple[str, int, str]]]:
    """One query for ALL doc_ids. Returns document_id -> [(id, proposition_index, content), ...]."""
    if not doc_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """SELECT document_id, id, proposition_index, content
               FROM propositions WHERE document_id = ANY(%s::uuid[])
               ORDER BY document_id, proposition_index""",
            (doc_ids,),
        )
        rows = cur.fetchall()
    out: Dict[str, List[Tuple[str, int, str]]] = {}
    for doc_id, prop_id, prop_index, content in rows:
        out.setdefault(doc_id, []).append((prop_id, prop_index, content))
    return out


def reconstruct_source_text(chunk_contents: List[str]) -> str:
    """chunks.content concatenated in chunk_index order -- the ONLY column
    read for source-text reconstruction (see module docstring)."""
    return "\n\n".join(c for c in chunk_contents if c)


# ── Pair records ────────────────────────────────────────────────────────────

class Pair(NamedTuple):
    bucket: str            # "should_pass_main" | "should_pass_ravenhill"
    document_id: str
    proposition_id: str
    proposition_content: str
    result: "cc.ClosenessResult"          # NEW -- post scripture-wording-fix (verse_lookup supplied)
    old_result: "cc.ClosenessResult"      # OLD -- pre-fix, citation-only masking (verse_lookup=None)
    quote_masking_fired: bool             # True if the fix masked >=1 extra span beyond citation-only
    source_word_count: int


class FlagItem(NamedTuple):
    bucket: str            # "should_flag_R0" | "R1" | "R2" | "R_run"
    document_id: str
    span_label: str
    text: str
    result: "cc.ClosenessResult"


# ── Should-pass sampling (deterministic, seeded; reconciliation-tracked) ───

def _quote_masking_fired(content: str, source_text: str, name_pattern, verse_lookup: Dict[str, str]) -> bool:
    """True if the scripture-wording fix masked at least one extra span
    (beyond citation-only masking) in EITHER the proposition or the source
    text, detected by comparing SENTINEL_SCRIPTURE occurrence counts between
    the OLD (verse_lookup=None) and NEW (verse_lookup supplied) exemption
    passes -- more sentinel occurrences under NEW means _find_quote_span
    matched and masked real verse wording that citation-only masking
    missed."""
    old_p = cc.exempt_for_containment(content, name_pattern, None)
    new_p = cc.exempt_for_containment(content, name_pattern, verse_lookup)
    old_s = cc.exempt_for_containment(source_text, name_pattern, None)
    new_s = cc.exempt_for_containment(source_text, name_pattern, verse_lookup)
    old_ct = old_p.count(cc.SENTINEL_SCRIPTURE) + old_s.count(cc.SENTINEL_SCRIPTURE)
    new_ct = new_p.count(cc.SENTINEL_SCRIPTURE) + new_s.count(cc.SENTINEL_SCRIPTURE)
    return new_ct > old_ct


def sample_should_pass(
    conn, teacher_name: str, doc_pool: List[Tuple[str, str]], target_n: int,
    max_per_doc: int, name_pattern, rng: random.Random, source_text_cache: Dict[str, str],
    verse_lookup: Dict[str, str],
) -> Tuple[List[Pair], Dict[str, int]]:
    """Bulk-fetches chunks+propositions ONCE for the whole doc_pool, then
    draws a seeded-shuffled sample of (doc, proposition) candidates until
    target_n are successfully measured or the pool is exhausted. Tracks
    skip/error reasons for the reconciliation count. Classifies each
    candidate TWICE -- once under the NEW (fixed) exemption (verse_lookup
    supplied, stored as .result, the bucket's primary/reported result) and
    once under the OLD (pre-fix, citation-only) exemption (verse_lookup=
    None, stored as .old_result) -- so Step 2's before/after scripture-
    confound comparison has real per-item numbers, not an inference."""
    doc_ids = [d for d, _ in doc_pool]
    chunks_by_doc = fetch_chunks_bulk(conn, doc_ids)
    props_by_doc = fetch_propositions_bulk(conn, doc_ids)

    # Reconstruct each document's source text ONCE, reused across all of
    # that document's propositions (no per-proposition re-reconstruction).
    for doc_id in doc_ids:
        if doc_id not in source_text_cache:
            source_text_cache[doc_id] = reconstruct_source_text(chunks_by_doc.get(doc_id, []))

    # Build the full candidate list: (doc_id, prop_id, prop_content), capped
    # at max_per_doc per document, then seeded-shuffled for diversity across
    # documents rather than draining one document first.
    candidates: List[Tuple[str, str, str]] = []
    for doc_id in doc_ids:
        props = props_by_doc.get(doc_id, [])
        for prop_id, _idx, content in props[:max_per_doc]:
            candidates.append((doc_id, prop_id, content))
    rng.shuffle(candidates)

    pairs: List[Pair] = []
    counters = {"attempted": 0, "measured": 0, "skipped_too_little": 0,
                "skipped_no_source_text": 0, "errored": 0}
    bucket_name = "should_pass_main" if teacher_name == MAIN_TEACHER else "should_pass_ravenhill"

    for doc_id, prop_id, content in candidates:
        if len(pairs) >= target_n:
            break
        counters["attempted"] += 1
        source_text = source_text_cache.get(doc_id, "")
        if not source_text.strip():
            counters["skipped_no_source_text"] += 1
            continue
        if len(content.split()) < 5:
            counters["skipped_too_little"] += 1
            continue
        try:
            result = cc.classify(content, source_text, name_pattern, verse_lookup)
            old_result = cc.classify(content, source_text, name_pattern, None)
            quote_fired = _quote_masking_fired(content, source_text, name_pattern, verse_lookup)
        except Exception as exc:  # noqa: BLE001 -- measurement harness, report don't crash
            counters["errored"] += 1
            print("ERROR classifying doc={0} prop={1}: {2}".format(doc_id, prop_id, exc))
            continue
        counters["measured"] += 1
        pairs.append(Pair(
            bucket=bucket_name, document_id=doc_id, proposition_id=prop_id,
            proposition_content=content, result=result, old_result=old_result,
            quote_masking_fired=quote_fired,
            source_word_count=len(source_text.split()),
        ))
    return pairs, counters


# ── Deterministic edit ladder (NO randomness -- pure rate/stride) ──────────

def apply_word_edits(words: List[str], target_rate: float) -> Tuple[List[str], int]:
    """Fixed, deterministic, reproducible word-level edit procedure.

    stride = round(1 / target_rate). Every stride-th ORIGINAL word position
    (i.e. original index i where (i+1) % stride == 0) is an edit position.
    Edits alternate DELETE / ADJACENT-SWAP by edit count (edit #0, #2, #4...
    = delete the word; edit #1, #3, #5... = swap it with the next word,
    falling back to delete if there is no next word). This is a mechanical
    procedure over fixed positions -- no dictionary, no LLM, no randomness.
    Returns (edited_words, edit_count). actual_rate = edit_count / len(words).
    """
    stride = max(1, round(1.0 / target_rate))
    out: List[str] = []
    edit_count = 0
    i = 0
    n = len(words)
    while i < n:
        is_edit_pos = (i + 1) % stride == 0
        if is_edit_pos:
            if edit_count % 2 == 0:
                edit_count += 1
                i += 1  # DELETE: word i dropped
                continue
            else:
                if i + 1 < n:
                    out.append(words[i + 1])
                    out.append(words[i])
                    edit_count += 1
                    i += 2  # SWAP: words i, i+1 exchanged
                    continue
                else:
                    edit_count += 1
                    i += 1  # no partner to swap with -- fall back to delete
                    continue
        out.append(words[i])
        i += 1
    return out, edit_count


def find_substantial_span(
    raw_text: str, name_pattern, target_words: int, min_residual_fraction: float,
    verse_lookup: Dict[str, str], stride: int = 25,
) -> Optional[Tuple[str, int, float]]:
    """Scans raw_text (whitespace-split, ORIGINAL case/punctuation preserved
    -- this produces the actual verbatim text used in the flag bucket, not
    a tokenized/lowercased reconstruction) for the FIRST contiguous window
    of target_words words whose residual-token fraction (post-exemption,
    NEW fixed exemption -- verse_lookup supplied) meets min_residual_fraction.
    Deterministic given fixed text/stride. Returns (span_text,
    start_word_index, residual_fraction) or None."""
    words = raw_text.split()
    n = len(words)
    if n < target_words:
        return None
    for start in range(0, n - target_words + 1, stride):
        span_words = words[start:start + target_words]
        span_text = " ".join(span_words)
        masked = cc.exempt_for_containment(span_text, name_pattern, verse_lookup)
        residual = cc.residual_token_count(cc.tokenize(masked))
        fraction = residual / float(target_words)
        if fraction >= min_residual_fraction:
            return span_text, start, fraction
    return None


def build_should_flag_bucket(
    doc_pool: List[Tuple[str, str]], source_text_cache: Dict[str, str], name_pattern,
    target_spans: int, rng: random.Random, verse_lookup: Dict[str, str],
) -> Tuple[List[FlagItem], Dict[str, object]]:
    """Picks target_spans documents (seeded-shuffled, distinct from the
    should-pass sample where possible), finds one ~100-word substantial
    span per document, builds R0/R1/R2 for each, classifies all three under
    the NEW (fixed) exemption."""
    pool = list(doc_pool)
    rng.shuffle(pool)
    items: List[FlagItem] = []
    ladder_log = []
    used = 0
    scanned = 0
    for doc_id, title in pool:
        if used >= target_spans:
            break
        scanned += 1
        source_text = source_text_cache.get(doc_id)
        if source_text is None:
            continue
        found = find_substantial_span(
            source_text, name_pattern, SPAN_TARGET_WORDS, SPAN_MIN_RESIDUAL_FRACTION, verse_lookup,
        )
        if found is None:
            continue
        span_text, start_idx, residual_fraction = found
        used += 1
        span_label = "{0}::w{1}".format(doc_id, start_idx)

        r0_words = span_text.split()
        r0_result = cc.classify(span_text, source_text, name_pattern, verse_lookup)
        items.append(FlagItem("should_flag_R0", doc_id, span_label, span_text, r0_result))

        r1_words, r1_edits = apply_word_edits(r0_words, 0.15)
        r1_text = " ".join(r1_words)
        r1_result = cc.classify(r1_text, source_text, name_pattern, verse_lookup)
        items.append(FlagItem("should_flag_R1", doc_id, span_label, r1_text, r1_result))

        r2_words, r2_edits = apply_word_edits(r0_words, 0.35)
        r2_text = " ".join(r2_words)
        r2_result = cc.classify(r2_text, source_text, name_pattern, verse_lookup)
        items.append(FlagItem("should_flag_R2", doc_id, span_label, r2_text, r2_result))

        ladder_log.append({
            "doc_id": doc_id, "title": title, "span_label": span_label,
            "span_start_word": start_idx, "span_residual_fraction": round(residual_fraction, 3),
            "r0_word_count": len(r0_words),
            "r1_edit_count": r1_edits, "r1_actual_rate": round(r1_edits / len(r0_words), 4),
            "r2_edit_count": r2_edits, "r2_actual_rate": round(r2_edits / len(r0_words), 4),
        })
    meta = {"docs_scanned": scanned, "docs_used": used, "ladder_log": ladder_log}
    return items, meta


def build_r_run_items(
    should_pass_pairs: List[Pair], source_text_cache: Dict[str, str], name_pattern,
    target_n: int, verse_lookup: Dict[str, str],
) -> Tuple[List[FlagItem], List[FlagItem]]:
    """Picks the N lowest-containment should-pass pairs (genuine, already-
    measured reword text -- no fresh LLM call; ranked by the NEW post-fix
    containment), splices one real ~14-word verbatim run from that SAME
    document's source text onto the end of the proposition text, and
    returns both the ORIGINAL (pre-splice) and the SPLICED item for direct
    before/after comparison, both classified under the NEW exemption."""
    ranked = sorted(should_pass_pairs, key=lambda p: p.result.containment)
    originals: List[FlagItem] = []
    spliced: List[FlagItem] = []
    n_taken = 0
    for pair in ranked:
        if n_taken >= target_n:
            break
        source_text = source_text_cache.get(pair.document_id, "")
        found = find_substantial_span(
            source_text, name_pattern, RUN_TARGET_WORDS, RUN_MIN_RESIDUAL_FRACTION, verse_lookup, stride=10,
        )
        if found is None:
            continue
        run_text, start_idx, _frac = found
        n_taken += 1
        label = "{0}::prop{1}::runw{2}".format(pair.document_id, pair.proposition_id, start_idx)

        orig_result = cc.classify(pair.proposition_content, source_text, name_pattern, verse_lookup)
        originals.append(FlagItem("R_run_original", pair.document_id, label, pair.proposition_content, orig_result))

        spliced_text = pair.proposition_content.rstrip(". ") + ". " + run_text + "."
        spliced_result = cc.classify(spliced_text, source_text, name_pattern, verse_lookup)
        spliced.append(FlagItem("R_run_spliced", pair.document_id, label, spliced_text, spliced_result))
    return originals, spliced


# ── Theology-stoplist isolation (reuses cc's own masking primitives; does
#    not fork/reimplement masking logic -- just composes two of its three
#    steps to isolate the third's marginal effect) ──────────────────────────

def _containment_without_theology(
    paraphrase_text: str, source_text: str, name_pattern, verse_lookup: Dict[str, str],
) -> float:
    import unicodedata

    def exempt_no_theology(text: str) -> str:
        text = unicodedata.normalize("NFKC", text)
        text = cc._mask_scripture(text, cc._constant_factory(cc.SENTINEL_SCRIPTURE), verse_lookup)
        text = cc._mask_names(text, name_pattern, cc._constant_factory(cc.SENTINEL_NAME))
        return text

    p_tokens = cc.tokenize(exempt_no_theology(paraphrase_text))
    s_tokens = cc.tokenize(exempt_no_theology(source_text))
    containment, _tri_ct = cc.containment_score(p_tokens, s_tokens)
    return containment


# ── Stats helpers (stdlib only) ─────────────────────────────────────────────

def percentile(sorted_vals: List[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def dist_summary(vals: List[float]) -> Dict[str, Optional[float]]:
    if not vals:
        return {"n": 0, "min": None, "median": None, "p95": None, "max": None}
    s = sorted(vals)
    return {
        "n": len(vals), "min": s[0], "median": statistics.median(s),
        "p95": percentile(s, 0.95), "max": s[-1],
    }


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return 0.0
    return cov / ((vx ** 0.5) * (vy ** 0.5))


def fmt(v: Optional[float], nd: int = 4) -> str:
    return "None" if v is None else "{0:.{1}f}".format(v, nd)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke", action="store_true",
        help="Tiny single-digit run (mechanics check) instead of the full Phase 2 batch.",
    )
    args = parser.parse_args()

    if args.smoke:
        target_main_n, target_ravenhill_n = SMOKE_MAIN_N, SMOKE_RAVENHILL_N
        target_flag_spans, target_run_items = SMOKE_FLAG_SPANS, SMOKE_RUN_ITEMS
    else:
        target_main_n, target_ravenhill_n = TARGET_MAIN_N, TARGET_RAVENHILL_N
        target_flag_spans, target_run_items = TARGET_FLAG_SPANS, TARGET_RUN_ITEMS

    rng = random.Random(SEED)
    conn = connect()
    scratch_dir = Path(
        "/private/tmp/claude-501/-Users-alexwhitley-rhemata/"
        "089de4dc-bced-40ff-98c1-e156d293aed9/scratchpad"
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("validate_closeness_check.py -- Phase 2/3 validation run{0}".format(
        " [SMOKE MODE -- tiny targets, mechanics check only]" if args.smoke else ""))
    print("SEED = {0}".format(SEED))
    print("Main teacher (should-pass, ~50 pairs): {0}".format(MAIN_TEACHER))
    print("Aphorist teacher (should-pass, ~15 pairs, reported separately): {0}".format(AFORIST_TEACHER))
    print("=" * 78)

    name_set = cc.build_name_set(db_params())
    print("\nLive name_set size (deduped via normalize_alias_key): {0}".format(len(name_set)))
    name_pattern = cc.build_name_pattern(name_set)

    verse_lookup = cc.build_verse_lookup(db_params())
    verse_translations_check = {}
    with conn.cursor() as cur:
        cur.execute("SELECT translation, count(*) FROM verses GROUP BY translation")
        verse_translations_check = dict(cur.fetchall())
    print("Live verse_lookup size (build_verse_lookup, full `verses` table): {0}".format(len(verse_lookup)))
    print("Live verses.translation breakdown (confirms WEB-only ground truth): {0}".format(verse_translations_check))

    # ── Eligibility (live-confirmed, not trusted from any .md) ─────────────
    main_pool = fetch_eligible_docs(conn, MAIN_TEACHER)
    ravenhill_pool = fetch_eligible_docs(conn, AFORIST_TEACHER, exclude_title_ilike="%compilation%")
    print("\n{0}: {1} documents with >=1 chunk AND >=1 proposition (live-confirmed)".format(MAIN_TEACHER, len(main_pool)))
    print("{0} (excl. '(Compilation)' titles): {1} documents with >=1 chunk AND >=1 proposition (live-confirmed)".format(
        AFORIST_TEACHER, len(ravenhill_pool)))

    source_text_cache: Dict[str, str] = {}

    # ── should-pass sampling ────────────────────────────────────────────────
    main_pairs, main_counters = sample_should_pass(
        conn, MAIN_TEACHER, main_pool, target_main_n, max_per_doc=2,
        name_pattern=name_pattern, rng=rng, source_text_cache=source_text_cache,
        verse_lookup=verse_lookup,
    )
    ravenhill_pairs, ravenhill_counters = sample_should_pass(
        conn, AFORIST_TEACHER, ravenhill_pool, target_ravenhill_n, max_per_doc=1,
        name_pattern=name_pattern, rng=rng, source_text_cache=source_text_cache,
        verse_lookup=verse_lookup,
    )

    print("\n--- Should-pass sampling reconciliation ---")
    print("{0}: {1}".format(MAIN_TEACHER, main_counters))
    print("{0}: {1}".format(AFORIST_TEACHER, ravenhill_counters))
    print("{0} pairs drawn (target {1}); {2} pairs drawn (target {3})".format(
        len(main_pairs), target_main_n, len(ravenhill_pairs), target_ravenhill_n))

    # ── spot-check: chunks.content is verbatim source text, not a rewrite ──
    spot_doc_id, spot_title = main_pool[0]
    spot_chunks = fetch_chunks_bulk(conn, [spot_doc_id])
    spot_text = reconstruct_source_text(spot_chunks.get(spot_doc_id, []))
    print("\n--- Spot-confirmation: chunks.content is verbatim source (not rewritten_content) ---")
    print("Document: {0!r} ({1})".format(spot_title, spot_doc_id))
    print("First 400 chars of reconstructed source text:")
    print(repr(spot_text[:400]))

    # ── length confound (main bucket) ───────────────────────────────────────
    main_containments = [p.result.containment for p in main_pairs]
    main_lengths = [p.source_word_count for p in main_pairs]
    corr = pearson(main_containments, main_lengths)

    # ── theology-stoplist effect (every pair, main + ravenhill) ─────────────
    theo_deltas_main = []
    for p in main_pairs:
        src = source_text_cache[p.document_id]
        no_theo = _containment_without_theology(p.proposition_content, src, name_pattern, verse_lookup)
        theo_deltas_main.append(no_theo - p.result.containment)
    theo_deltas_raven = []
    for p in ravenhill_pairs:
        src = source_text_cache[p.document_id]
        no_theo = _containment_without_theology(p.proposition_content, src, name_pattern, verse_lookup)
        theo_deltas_raven.append(no_theo - p.result.containment)

    # ── too-little cutoff: bin should-pass (main) by residual token count ──
    bins = [(0, 3), (4, 7), (8, 11), (12, 15), (16, 20), (21, 10 ** 6)]
    print("\n--- Too-little cutoff: containment variance by residual-token bin (main bucket) ---")
    for lo, hi in bins:
        in_bin = [p.result.containment for p in main_pairs if lo <= p.result.residual_tokens <= hi]
        if in_bin:
            v = statistics.pstdev(in_bin) if len(in_bin) > 1 else 0.0
            print("  residual [{0}-{1}]: n={2} containments={3} stdev={4}".format(
                lo, hi if hi < 10**6 else "inf", len(in_bin),
                [round(c, 3) for c in in_bin], round(v, 4)))
        else:
            print("  residual [{0}-{1}]: n=0".format(lo, hi if hi < 10**6 else "inf"))

    below_placeholder_cutoff_main = sum(1 for p in main_pairs if p.result.residual_tokens < cc.RESIDUAL_TOO_LITTLE_CUTOFF)
    below_placeholder_cutoff_raven = sum(1 for p in ravenhill_pairs if p.result.residual_tokens < cc.RESIDUAL_TOO_LITTLE_CUTOFF)
    print("Pairs with residual < placeholder cutoff ({0}): main={1}/{2}, ravenhill={3}/{4}".format(
        cc.RESIDUAL_TOO_LITTLE_CUTOFF, below_placeholder_cutoff_main, len(main_pairs),
        below_placeholder_cutoff_raven, len(ravenhill_pairs)))

    # ── should-flag ladder ──────────────────────────────────────────────────
    flag_pool = [d for d in main_pool if d[0] not in {p.document_id for p in main_pairs}]
    flag_items, flag_meta = build_should_flag_bucket(
        flag_pool, source_text_cache, name_pattern, target_flag_spans, rng, verse_lookup,
    )
    print("\n--- Should-flag ladder construction ---")
    print("Docs scanned: {0}, docs used (found substantial span): {1}".format(
        flag_meta["docs_scanned"], flag_meta["docs_used"]))
    for row in flag_meta["ladder_log"]:
        print("  {0}".format(row))

    r0_c = [i.result.containment for i in flag_items if i.bucket == "should_flag_R0"]
    r1_c = [i.result.containment for i in flag_items if i.bucket == "should_flag_R1"]
    r2_c = [i.result.containment for i in flag_items if i.bucket == "should_flag_R2"]

    # ── R-run adversarial items ─────────────────────────────────────────────
    r_run_orig, r_run_spliced = build_r_run_items(
        main_pairs, source_text_cache, name_pattern, target_run_items, verse_lookup,
    )
    print("\n--- R-run adversarial items (genuine low-containment reword + spliced 12-14w verbatim run) ---")
    for orig, spl in zip(r_run_orig, r_run_spliced):
        print("  doc={0}".format(orig.document_id))
        print("    BEFORE splice: containment={0} longest_run={1}".format(
            round(orig.result.containment, 4), orig.result.longest_run_words))
        print("    AFTER  splice: containment={0} longest_run={1} run_tokens={2}".format(
            round(spl.result.containment, 4), spl.result.longest_run_words, spl.result.longest_run_tokens))

    # ── Step 4 (PLAN.md #45 Phase 4) before/after scripture-fix analysis ────
    # For every should-pass pair, .result is the NEW (post-fix) classify()
    # output and .old_result is the OLD (pre-fix, citation-only) output --
    # both already computed once per pair in sample_should_pass, not
    # recomputed here. quote_masking_fired distinguishes "the fix actually
    # masked extra verse wording for this item" from "no scripture quote was
    # involved at all".
    combined_pairs = main_pairs + ravenhill_pairs
    print("\n" + "=" * 78)
    print("STEP 2: before/after scripture-wording-fix analysis (should-pass bucket)")
    print("=" * 78)

    top20_by_old = sorted(combined_pairs, key=lambda p: p.old_result.containment, reverse=True)[:20]
    print("\n--- Top 20 should-pass pairs by OLD (pre-fix) containment -- before/after + quote_masking_fired ---")
    for rank, p in enumerate(top20_by_old, start=1):
        print("  rank={0} doc={1} prop={2} bucket={3}".format(rank, p.document_id, p.proposition_id, p.bucket))
        print("    OLD containment={0}  NEW containment={1}  delta={2}  quote_masking_fired={3}  longest_run_words={4}".format(
            round(p.old_result.containment, 4), round(p.result.containment, 4),
            round(p.old_result.containment - p.result.containment, 4), p.quote_masking_fired,
            p.result.longest_run_words))

    # Dump full text (proposition + source) for every should-pass pair whose
    # NEW (post-fix) containment is still notably elevated (>=0.30) OR whose
    # OLD containment was notably elevated but the fix changed it --
    # everything needed to hand-classify sub-groups (a)/(b)/(c) below, per
    # the same hand-read method the prior review used (no automated
    # "genuine paraphrase vs. genuine violation" classifier exists or is in
    # scope here -- PLAN.md's own landmine log records that a similarity-
    # based automated version of exactly this judgment was tried and
    # rejected corpus-wide on 2026-07-24).
    review_candidates = [
        p for p in combined_pairs
        if p.result.containment >= 0.30 or p.old_result.containment >= 0.30
    ]
    review_candidates.sort(key=lambda p: max(p.result.containment, p.old_result.containment), reverse=True)
    print("\n--- {0} should-pass pairs dumped to scratchpad for hand-classification into (a)/(b)/(c) ---".format(
        len(review_candidates)))
    dumped_files = []
    for rank, p in enumerate(review_candidates, start=1):
        fname = scratch_dir / "review{0:02d}_{1}_{2}.txt".format(rank, p.bucket, p.proposition_id)
        src = source_text_cache[p.document_id]
        with open(fname, "w") as f:
            f.write(
                "bucket={0} doc_id={1} prop_id={2}\n"
                "OLD containment={3} NEW containment={4} delta={5} quote_masking_fired={6}\n"
                "residual_tokens={7} longest_run_words={8} longest_run_tokens={9}\n\n".format(
                    p.bucket, p.document_id, p.proposition_id,
                    p.old_result.containment, p.result.containment,
                    round(p.old_result.containment - p.result.containment, 4), p.quote_masking_fired,
                    p.result.residual_tokens, p.result.longest_run_words, p.result.longest_run_tokens,
                )
            )
            f.write("=== PROPOSITION ===\n{0}\n\n".format(p.proposition_content))
            f.write("=== FULL RECONSTRUCTED SOURCE TEXT ===\n{0}\n".format(src))
        dumped_files.append(str(fname))
        print("  rank={0} OLD={1} NEW={2} quote_fired={3} bucket={4} doc={5} -> {6}".format(
            rank, round(p.old_result.containment, 4), round(p.result.containment, 4),
            p.quote_masking_fired, p.bucket, p.document_id, fname))

    # ── longest_common_run distribution, should-pass bucket (first report) ──
    main_runs = [float(p.result.longest_run_words) for p in main_pairs]
    raven_runs = [float(p.result.longest_run_words) for p in ravenhill_pairs]
    print("\n--- should-pass longest_common_run distribution (words; first reported this run) ---")
    print("  main ({0}, n={1}): {2}".format(MAIN_TEACHER, len(main_runs), dist_summary(main_runs)))
    print("  ravenhill (n={0}): {1}".format(len(raven_runs), dist_summary(raven_runs)))
    all_runs = sorted(main_runs + raven_runs)
    print("  combined (n={0}): {1}".format(len(all_runs), dist_summary(all_runs)))

    # ── distribution summaries ──────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("DISTRIBUTION SUMMARY")
    print("=" * 78)
    print("should-pass MAIN ({0}, n={1}) containment: {2}".format(MAIN_TEACHER, len(main_pairs), dist_summary(main_containments)))
    raven_containments = [p.result.containment for p in ravenhill_pairs]
    print("should-pass RAVENHILL (n={0}) containment: {1}".format(len(ravenhill_pairs), dist_summary(raven_containments)))
    print("should-flag R0 (verbatim, n={0}) containment: {1}".format(len(r0_c), dist_summary(r0_c)))
    print("should-flag R1 (~15% edits, n={0}) containment: {1}".format(len(r1_c), dist_summary(r1_c)))
    print("should-flag R2 (~35% edits, n={0}) containment: {1}".format(len(r2_c), dist_summary(r2_c)))

    print("\nLength confound (main bucket): pearson(containment, source_word_count) = {0}  n={1}".format(
        fmt(corr), len(main_pairs)))

    print("\nTheology-stoplist effect (no-theology-mask containment MINUS actual containment):")
    print("  main:      {0}".format(dist_summary(theo_deltas_main)))
    print("  ravenhill: {0}".format(dist_summary(theo_deltas_raven)))

    # ── reconciliation vs live DB ───────────────────────────────────────────
    sampled_prop_ids = [p.proposition_id for p in combined_pairs]
    sampled_doc_ids = list({p.document_id for p in combined_pairs})
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM propositions WHERE id = ANY(%s::uuid[])", (sampled_prop_ids,))
        live_prop_count = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM documents WHERE id = ANY(%s::uuid[])", (sampled_doc_ids,))
        live_doc_count = cur.fetchone()[0]
    print("\n--- Live DB reconciliation ---")
    print("Sampled proposition_ids: {0}, confirmed live in propositions table: {1}".format(
        len(sampled_prop_ids), live_prop_count))
    print("Sampled document_ids: {0}, confirmed live in documents table: {1}".format(
        len(sampled_doc_ids), live_doc_count))

    # dump full JSON for downstream reading
    dump = {
        "seed": SEED,
        "main_teacher": MAIN_TEACHER,
        "main_counters": main_counters,
        "ravenhill_counters": ravenhill_counters,
        "main_pairs": [
            {"doc_id": p.document_id, "prop_id": p.proposition_id, "containment": p.result.containment,
             "old_containment": p.old_result.containment, "quote_masking_fired": p.quote_masking_fired,
             "residual_tokens": p.result.residual_tokens, "longest_run_words": p.result.longest_run_words,
             "source_word_count": p.source_word_count, "verdict": p.result.verdict}
            for p in main_pairs
        ],
        "ravenhill_pairs": [
            {"doc_id": p.document_id, "prop_id": p.proposition_id, "containment": p.result.containment,
             "old_containment": p.old_result.containment, "quote_masking_fired": p.quote_masking_fired,
             "residual_tokens": p.result.residual_tokens, "longest_run_words": p.result.longest_run_words,
             "source_word_count": p.source_word_count, "verdict": p.result.verdict}
            for p in ravenhill_pairs
        ],
        "flag_ladder_log": flag_meta["ladder_log"],
        "flag_items": [
            {"bucket": i.bucket, "doc_id": i.document_id, "span_label": i.span_label,
             "containment": i.result.containment, "residual_tokens": i.result.residual_tokens,
             "longest_run_words": i.result.longest_run_words, "verdict": i.result.verdict}
            for i in flag_items
        ],
        "r_run_before": [
            {"doc_id": i.document_id, "containment": i.result.containment, "longest_run_words": i.result.longest_run_words}
            for i in r_run_orig
        ],
        "r_run_after": [
            {"doc_id": i.document_id, "containment": i.result.containment, "longest_run_words": i.result.longest_run_words,
             "run_tokens": i.result.longest_run_tokens}
            for i in r_run_spliced
        ],
    }
    dump_path = scratch_dir / "validation_run_dump.json"
    with open(dump_path, "w") as f:
        json.dump(dump, f, indent=2, default=list)
    print("\nFull JSON dump written to: {0}".format(dump_path))

    conn.close()
    print("\nDone. Zero writes performed anywhere in this run.")


if __name__ == "__main__":
    main()
