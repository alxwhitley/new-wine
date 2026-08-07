#!/usr/bin/env python3
"""
Retrieval pipeline diagnostic for Rhemata chat.
Uses real production code paths — no reimplementation.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── 1. Load env before any app imports ────────────────────────────────────────
_env_path = Path(__file__).parent.parent / "backend" / "app" / ".env"
with open(_env_path) as _f:
    for _line in _f:
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ── 2. Add backend/ to sys.path so `app.*` imports resolve ────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# ── 3. Real production imports ────────────────────────────────────────────────
from app.db.supabase import get_supabase
from app.services.embeddings import embed_text
from app.services.source_filter import get_disabled_filters, is_chunk_disabled
from app.routers.chat import (
    expand_query,
    hybrid_search_rrf,
    fetch_neighbor_chunks_batch,
    _is_citable,
    match_background_topics,
    _ensure_background_topics,
    _get_cohere,
    SOURCE_KIND_FUSION_WEIGHTS,
    is_commentary_chunk,
    exclude_commentary_chunks,
    _NEIGHBOR_SKIP_KINDS,
)

# ── 4. Test queries ────────────────────────────────────────────────────────────
FAIL_QUERIES = [
    "Give me quotes from the corpus about revival",
    "What does the corpus teach about territorial spirits",
    "What do the church fathers say about John 3:16?",
    "What is the Holy Spirit?",
]
SUCCESS_QUERIES = [
    "Is the baptism of the Holy Spirit a separate experience from salvation?",
]
ALL_QUERIES = FAIL_QUERIES + SUCCESS_QUERIES


# ── 5. Diagnostic runner ───────────────────────────────────────────────────────

def run_diagnostic(question: str, db, filters: dict) -> dict:
    """Run every pipeline stage for one query, printing as we go."""
    print("\n" + "=" * 80)
    print(f"QUERY: {question}")
    print("=" * 80)

    # Stage 0.5 — background topic injection
    _ensure_background_topics()
    matched_topics = match_background_topics(question)
    topic_context_parts: List[str] = []          # fresh convo → nothing established
    print(f"\n[Stage 0.5] Background topics matched: {matched_topics or '(none)'}")

    # Stage 1 — query expansion
    print("\n[Stage 1] Query expansion")
    try:
        variants, keywords = expand_query(question)
        for i, v in enumerate(variants):
            label = "(original)" if i == 0 else f"(paraphrase {i})"
            print(f"  variant[{i}] {label}: {v}")
        print(f"  FTS keywords: {keywords!r}")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        variants, keywords = [question], None

    include_copyrighted = filters["include_copyrighted"]
    variant_weights = [1.0, 0.7, 0.7]
    FTS_WEIGHT = 1.0

    # Stage 2 — per-arm search (FTS isolated, vector isolated)
    # We run isolated passes for reporting, then build all_scores exactly as production does.
    print("\n[Stage 2] Per-arm search counts")
    all_scores: Dict[str, Tuple[float, dict]] = {}
    first_embedding: Optional[List[float]] = None

    def _merge(scores: dict, weight: float) -> None:
        for cid, (score, chunk) in scores.items():
            weighted = score * weight
            if cid in all_scores:
                all_scores[cid] = (all_scores[cid][0] + weighted, all_scores[cid][1])
            else:
                all_scores[cid] = (weighted, chunk)

    total_fts_hits = 0
    total_vector_hits = 0

    if keywords:
        # Production path: vector-only per variant + single FTS on keywords
        print(f"  [keyword routing active → FTS text: {keywords!r}]")
        for i, variant in enumerate(variants):
            weight = variant_weights[i] if i < len(variant_weights) else 0.5
            try:
                v_scores, embedding = hybrid_search_rrf(
                    variant, db,
                    include_copyrighted=include_copyrighted,
                    run_fts=False, run_vector=True,
                )
                if i == 0:
                    first_embedding = embedding
                total_vector_hits += len(v_scores)
                print(f"  variant[{i}] vector: {len(v_scores)} hits  (weight={weight})")
                _merge(v_scores, weight)
            except Exception as exc:
                print(f"  variant[{i}] vector ERROR: {exc}")

        try:
            fts_scores, _ = hybrid_search_rrf(
                keywords, db,
                include_copyrighted=include_copyrighted,
                run_fts=True, run_vector=False,
            )
            total_fts_hits = len(fts_scores)
            print(f"  FTS on keywords: {total_fts_hits} hits  (weight={FTS_WEIGHT})")
            _merge(fts_scores, FTS_WEIGHT)
        except Exception as exc:
            print(f"  FTS on keywords ERROR: {exc}")

    else:
        # Production path: full hybrid per variant
        print("  [no keyword routing → full hybrid (vector+FTS) per variant]")
        for i, variant in enumerate(variants):
            weight = variant_weights[i] if i < len(variant_weights) else 0.5
            try:
                # Get combined scores (what production uses)
                v_scores, embedding = hybrid_search_rrf(
                    variant, db,
                    include_copyrighted=include_copyrighted,
                    run_fts=True, run_vector=True,
                )
                if i == 0:
                    first_embedding = embedding
                _merge(v_scores, weight)

                # Isolated arms for reporting only
                v_vec, _ = hybrid_search_rrf(
                    variant, db,
                    include_copyrighted=include_copyrighted,
                    run_fts=False, run_vector=True,
                    precomputed_embedding=embedding,
                )
                v_fts, _ = hybrid_search_rrf(
                    variant, db,
                    include_copyrighted=include_copyrighted,
                    run_fts=True, run_vector=False,
                )
                total_vector_hits += len(v_vec)
                total_fts_hits += len(v_fts)
                print(f"  variant[{i}]  vector={len(v_vec)}  fts={len(v_fts)}  (weight={weight})")
            except Exception as exc:
                print(f"  variant[{i}] ERROR: {exc}")

    # Stage 2.5 — source filter
    pre = len(all_scores)
    all_scores = {
        cid: (s, c) for cid, (s, c) in all_scores.items()
        if not is_chunk_disabled(c, filters)
    }
    print(f"\n[Stage 2.5] Source filter: {pre} → {len(all_scores)} chunks remaining")

    # Stage 2.6 — hard-exclude commentary (Settled decision #5)
    pre_c = len(all_scores)
    all_scores = {
        cid: (s, c) for cid, (s, c) in all_scores.items()
        if not is_commentary_chunk(c)
    }
    print(f"\n[Stage 2.6] Commentary exclude (decision #5): {pre_c} → {len(all_scores)}")

    # Stage 2.75 — boost_factor + source-kind fusion weights
    all_scores = {
        cid: (
            s
            * (c.get("boost_factor") or 1.0)
            * SOURCE_KIND_FUSION_WEIGHTS.get(
                c.get("source_kind") or c.get("source_type") or "", 1.0
            ),
            c,
        )
        for cid, (s, c) in all_scores.items()
    }

    # Stage 3 — doc-collapse + author-cap → top 30 pool (Fix 1)
    ranked = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)
    doc_counts: Dict[str, int] = {}
    collapsed = []
    for cid, (s, c) in ranked:
        did = c.get("document_id", "")
        doc_counts[did] = doc_counts.get(did, 0) + 1
        if doc_counts[did] <= 2:
            collapsed.append((cid, (s, c)))

    author_counts: Dict[str, int] = {}
    author_capped = []
    for cid, (s, c) in collapsed:
        author = c.get("author") or "Unknown"
        author_counts[author] = author_counts.get(author, 0) + 1
        if author_counts[author] <= 3:
            author_capped.append((cid, (s, c)))

    top30 = author_capped[:30]
    top30_chunks = [c for _, (_, c) in top30]

    # Show top 15 for readability (full 30 would be too verbose)
    display_n = min(15, len(top30))
    print(f"\n[Stage 3] Post-RRF top {len(top30)} pool  (doc-collapse + author-cap + source-kind weights applied)")
    print(f"  (showing top {display_n})")
    hdr = f"  {'#':<3} {'title':<45} {'author':<22} {'source_kind':<22} {'cit_mode':<12} score"
    print(hdr)
    print("  " + "-" * 115)
    for i, (cid, (s, c)) in enumerate(top30[:display_n]):
        title  = (c.get("title") or "—")[:44]
        author = (c.get("author") or "—")[:21]
        sk     = (c.get("source_kind") or c.get("source_type") or "—")[:21]
        cm     = (c.get("citation_mode") or "—")[:11]
        print(f"  {i+1:<3} {title:<45} {author:<22} {sk:<22} {cm:<12} {s:.5f}")

    # Stage 3.5 — Cohere rerank top 30 → top 8 (Fix 1)
    print(f"\n[Stage 3.5] Cohere rerank  ({len(top30_chunks)} → 8)")
    co = _get_cohere()
    reranked: List[dict] = list(top30_chunks)
    if co and top30_chunks:
        try:
            docs = [c.get("content", "") for c in top30_chunks]
            rr = co.rerank(
                model="rerank-v3.5",
                query=question,
                documents=docs,
                top_n=8,
            )
            reranked = [top30_chunks[r.index] for r in rr.results]
            hdr2 = f"  {'#':<3} {'title':<45} {'author':<22} {'source_kind':<22} {'cit_mode':<12} cohere_score"
            print(hdr2)
            print("  " + "-" * 120)
            for i, (r, c) in enumerate(zip(rr.results, reranked)):
                title  = (c.get("title") or "—")[:44]
                author = (c.get("author") or "—")[:21]
                sk     = (c.get("source_kind") or c.get("source_type") or "—")[:21]
                cm     = (c.get("citation_mode") or "—")[:11]
                print(f"  {i+1:<3} {title:<45} {author:<22} {sk:<22} {cm:<12} {r.relevance_score:.4f}")
        except Exception as exc:
            print(f"  Cohere rerank ERROR: {exc}")
            reranked = top30_chunks[:8]  # Fix 1: fallback takes 8
    else:
        reranked = top30_chunks[:8]      # Fix 1: fallback takes 8
        print("  (Cohere unavailable — using RRF top 8)")

    # ── THE fallback signal: citable count from post-Cohere, pre-neighbor ──────
    citable_count = sum(1 for c in reranked if _is_citable(c))
    print(f"\n  >>> citable_count (THE fallback signal, counted here): {citable_count}")

    # Stage 4 — neighbor expansion
    print(f"\n[Stage 4] Neighbor chunk expansion")
    seen_ids = {c["id"] for c in reranked}
    # Fix 4: commentary/lexicon parents skipped inside fetch_neighbor_chunks_batch
    skipped_kinds = [c.get("source_kind") or "" for c in reranked if (c.get("source_kind") or "") in _NEIGHBOR_SKIP_KINDS]
    print(f"  Skipping neighbor expansion for {len(skipped_kinds)} commentary/lexicon chunks")
    try:
        neighbors = fetch_neighbor_chunks_batch(reranked, seen_ids, db)
        expanded = list(reranked)
        for n in neighbors:
            if len(expanded) >= 12:
                break
            seen_ids.add(n["id"])
            expanded.append(n)
        print(f"  {len(reranked)} reranked → {len(expanded)} after adding {len(neighbors)} neighbors (cap=12)")
    except Exception as exc:
        print(f"  Neighbor expansion ERROR: {exc}")
        expanded = reranked

    # Defense-in-depth: hard-exclude commentary after neighbor expansion
    pre_ex = len(expanded)
    expanded = exclude_commentary_chunks(expanded)
    if len(expanded) < pre_ex:
        print(f"  Commentary hard-exclude (decision #5): {pre_ex} → {len(expanded)} chunks")

    # Final composition breakdown
    citable_final  = [c for c in expanded if _is_citable(c)]
    silent_final   = [c for c in expanded if not _is_citable(c)]
    citable_by_kind = Counter(c.get("source_kind") or c.get("source_type") or "unknown" for c in citable_final)
    silent_by_kind  = Counter(c.get("source_kind") or c.get("source_type") or "unknown" for c in silent_final)

    print(f"\n[Stage 4 — Final composition]")
    print(f"  total={len(expanded)}  |  citable={len(citable_final)}  |  silent_context={len(silent_final)}")
    print(f"  citable by source_kind : {dict(citable_by_kind)}")
    print(f"  silent  by source_kind : {dict(silent_by_kind)}")

    # Fallback trigger
    fallback_fired = citable_count < 2 and not topic_context_parts
    print(f"\n[Fallback trigger]")
    print(f"  citable_count={citable_count}  |  citable_count < 2 → {citable_count < 2}")
    print(f"  topic_context_parts (position paper injected?) → {bool(topic_context_parts)}")
    fires_label = 'YES  ⚠  <- returns "no strong material"' if fallback_fired else 'NO  ✓'
    print(f"  FIRES: {fires_label}")

    return {
        "query": question[:54],
        "fts_hits": total_fts_hits,
        "vector_hits": total_vector_hits,
        "citable_in_reranked": citable_count,
        "fallback_fired": fallback_fired,
    }


def main():
    db = get_supabase()
    filters = get_disabled_filters()

    print("\nRhemata retrieval diagnostic")
    print(f"Source filter state: disabled_kinds={filters['source_kinds']}, "
          f"disabled_names={filters['source_names']}, "
          f"include_copyrighted={filters['include_copyrighted']}")

    rows = []
    for q in ALL_QUERIES:
        try:
            row = run_diagnostic(q, db, filters)
        except Exception as exc:
            import traceback
            print(f"\nFATAL for '{q}': {exc}")
            traceback.print_exc()
            row = {"query": q[:54], "fts_hits": "ERR", "vector_hits": "ERR",
                   "citable_in_reranked": "ERR", "fallback_fired": "ERR"}
        rows.append(row)

    # Summary table
    W = 110
    print("\n\n" + "=" * W)
    print("SUMMARY TABLE")
    print("=" * W)
    print(f"{'Query':<56} {'FTS hits':>10} {'Vec hits':>10} {'Citable@rerank':>16} {'Fallback?':>10}")
    print("-" * W)
    for r in rows:
        ff = ("YES ⚠" if r["fallback_fired"] is True
              else "NO ✓" if r["fallback_fired"] is False
              else str(r["fallback_fired"]))
        print(f"{r['query']:<56} {str(r['fts_hits']):>10} {str(r['vector_hits']):>10} "
              f"{str(r['citable_in_reranked']):>16} {ff:>10}")
    print("=" * W)


if __name__ == "__main__":
    main()
