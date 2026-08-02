#!/usr/bin/env python3
"""Live verification of the Phase 2 teacher-name guard (requirements 5 & 6).

Reproduces backend/app/routers/chat.py's REAL retrieval + generation pipeline
offline (same step sequence, same helper functions imported from chat.py, same
system prompt, same model, same author-cap + Cohere rerank + neighbor
expansion + background injection that Phase 0 §0 identified as the fabrication
mechanism), then applies the SHIPPED guard — build_retrieval_grounding() +
verify_references() straight from app.services.reference_verifier, not a
re-implementation. So what is measured here is exactly what runs in production.

Why offline and not the /chat HTTP endpoint (same reason as Phase 0 §0): the
endpoint's metering RPCs (increment_guest_query / increment_user_query) and
_save_conversation are DB WRITES; this is a zero-DB-write session, so the live
endpoint cannot be exercised. Only those writes are omitted; retrieval,
generation, and the guard are identical.

For each generated answer this reports, per attributed teacher: the resolved
source_id (if any), whether it was RETRIEVED for this question (the shipped
grounding predicate), and the guard's verdict (verified link vs denied). It
also prints the full retrieved-author set so a denied name can be adjudicated
as a true block (fabrication) vs a false positive (a genuinely retrieved
teacher wrongly denied).

Requirement 6 (variance): each question runs N times (--runs), because Phase 0
proved fabrication is intermittent (3/12 questions flipped across 4 runs).

Usage:
  python3 scripts/verify_teacher_name_guard_live.py            # default set
  python3 scripts/verify_teacher_name_guard_live.py --runs 4
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

from supabase import create_client

# Real production pieces — imported, never re-implemented.
from app.routers import chat as chatmod
from app.routers.chat import (
    expand_query, hybrid_search_rrf, fetch_neighbor_chunks_batch, _is_citable,
    is_word_study_query, ANSWER_SYSTEM_BLOCKS,
    SOURCE_KIND_FUSION_WEIGHTS, COMMENTARY_CONTEXT_CAP, INCLUDE_COPYRIGHTED_ENV,
)
from app.services.source_filter import get_disabled_filters, is_chunk_disabled
from app.services.position_papers import match_position_paper
from app.services.embeddings import embed_text
from app.services.llm_client import get_anthropic_client
# THE SHIPPED GUARD — exactly what chat.py calls.
from app.services.reference_verifier import (
    build_retrieval_grounding, verify_references, _is_retrieval_grounded,
    verify_teacher_mention, find_occurrences,
)
from app.services.source_resolver import normalize_alias_key, is_source_servable
from app.services.biblical_figures import is_biblical_figure
from app.services.reference_verifier import _link_source_retrieved

SB_URL = os.environ["SUPABASE_URL"]
SB_SVC = os.environ["SUPABASE_SERVICE_KEY"]
db = create_client(SB_URL, SB_SVC)


# ── Question set ──────────────────────────────────────────────────────────
# Fabrication-prone questions from Phase 0 §1/§3 (D2 Wiersbe; S2 Stedman/
# Wilson; S4 Havner/Tozer/Jenkins/Martin) — run extra times to re-trigger the
# intermittent fabrication. Plus legitimate-attribution questions for the
# false-positive measurement (Phase 0 §4a's 0/125). Path split matters: any
# question that routes to the position-paper path names no teachers and is
# skipped from the teacher metric (reported, not scored).
FAB_QUESTIONS = [
    ("D2", "How do believers get free from demonic strongholds?"),
    ("S2", "How do different charismatic teachers understand holiness and sanctification?"),
    ("S4", "Who are the key voices on revival, and what do they teach?"),
]
LEGIT_QUESTIONS = [
    ("P4", "Can a prophetic word be partly wrong but still be from God?"),
    ("G1", "What does it mean to fear the Lord?"),
    ("G3", "What is intercession and how do I practice it?"),
    ("G4", "What is spiritual warfare and how do I engage in it?"),
    ("G6", "What does repentance really mean?"),
    ("E1", "What is hyper-grace and is it biblical?"),
    ("S1", "What do charismatic teachers say about the end times?"),
    ("D1", "What is deliverance ministry?"),
    ("P1", "What is the gift of prophecy today?"),
    ("H2", "Why isn't everyone healed when we pray?"),
    ("TS1", "What does Derek Prince teach about deliverance?"),
    ("D3", "Which teachers address generational curses?"),
]


# ── Faithful reproduction of chat.py's retrieval + context assembly ───────
# Mirrors backend/app/routers/chat.py lines ~619-858 for a FRESH single-turn
# request (no prior messages, no established topics). Only the metering / save
# DB writes are omitted. Kept deliberately close to the source order.
def retrieve(question: str) -> Tuple[List[dict], List[str]]:
    filters = get_disabled_filters()
    include_copyrighted = filters["include_copyrighted"] and INCLUDE_COPYRIGHTED_ENV

    # Background-topic injection (fresh turn => matched topics get full paper).
    chatmod._ensure_background_topics()
    matched_topics = chatmod.match_background_topics(question)
    topic_context_parts = []  # type: List[str]
    injected_doc_ids = set()
    topic_lookup = {t["topic_key"]: t for t in chatmod._background_topics}
    for topic_key in matched_topics:
        topic = topic_lookup.get(topic_key)
        if not topic:
            continue
        try:
            crows = (
                db.table("chunks").select("content").eq("document_id", topic["document_id"])
                .order("chunk_index").limit(3).execute()
            )
            if crows.data:
                body = "\n".join(r["content"] for r in crows.data)
                topic_context_parts.append(
                    "[Background] (citation_mode=silent_context) \"%s\"\n%s" % (topic["title"], body)
                )
                injected_doc_ids.add(topic["document_id"])
        except Exception:
            pass

    # Step 1: query expansion
    variants, keywords = expand_query(question)
    variant_weights = [1.0, 0.7, 0.7]
    FTS_WEIGHT = 1.0

    all_scores = {}  # type: Dict[str, Tuple[float, dict]]

    def _merge(scores, weight):
        for cid, (score, chunk) in scores.items():
            if cid in all_scores:
                all_scores[cid] = (all_scores[cid][0] + score * weight, all_scores[cid][1])
            else:
                all_scores[cid] = (score * weight, chunk)

    with ThreadPoolExecutor(max_workers=4) as ex:
        if keywords:
            variant_futures = [
                ex.submit(hybrid_search_rrf, v, db, include_copyrighted=include_copyrighted, run_fts=False)
                for v in variants
            ]
            fts_future = ex.submit(hybrid_search_rrf, keywords, db, include_copyrighted=include_copyrighted, run_vector=False)
            for i, fut in enumerate(variant_futures):
                w = variant_weights[i] if i < len(variant_weights) else 0.5
                vs, _ = fut.result()
                _merge(vs, w)
            fs, _ = fts_future.result()
            _merge(fs, FTS_WEIGHT)
        else:
            futures = [ex.submit(hybrid_search_rrf, v, db, include_copyrighted=include_copyrighted) for v in variants]
            for i, fut in enumerate(futures):
                w = variant_weights[i] if i < len(variant_weights) else 0.5
                vs, _ = fut.result()
                _merge(vs, w)

    # Step 2.5: disabled-source filter
    all_scores = {cid: (s, c) for cid, (s, c) in all_scores.items() if not is_chunk_disabled(c, filters)}
    # Fix 6: drop injected position-paper docs from the main pool
    if injected_doc_ids:
        all_scores = {cid: (s, c) for cid, (s, c) in all_scores.items() if c.get("document_id") not in injected_doc_ids}
    # Step 2.75: boost + source-kind fusion weights
    all_scores = {
        cid: (s * (c.get("boost_factor") or 1.0)
              * SOURCE_KIND_FUSION_WEIGHTS.get(c.get("source_kind") or c.get("source_type") or "", 1.0), c)
        for cid, (s, c) in all_scores.items()
    }
    # Step 3: document collapse (max 2/doc)
    ranked = sorted(all_scores.items(), key=lambda x: x[1][0], reverse=True)
    doc_counts = {}  # type: Dict[str, int]
    collapsed = []
    for cid, (s, c) in ranked:
        did = c.get("document_id", "")
        doc_counts[did] = doc_counts.get(did, 0) + 1
        if doc_counts[did] <= 2:
            collapsed.append((cid, (s, c)))
    # Step 3a: author cap (max 3/author) — the fabrication-pressure step
    author_counts = {}  # type: Dict[str, int]
    author_capped = []
    for cid, (s, c) in collapsed:
        a = c.get("author") or "Unknown"
        author_counts[a] = author_counts.get(a, 0) + 1
        if author_counts[a] <= 3:
            author_capped.append((cid, (s, c)))
    top_chunks = author_capped[:30]
    chunks = [c for _, (_, c) in top_chunks]
    # Step 3.5: Cohere rerank -> top 8
    co = chatmod._get_cohere()
    if co and chunks:
        try:
            docs = [c.get("content", "") for c in chunks]
            rr = co.rerank(model="rerank-v3.5", query=question, documents=docs, top_n=8)
            chunks = [chunks[r.index] for r in rr.results]
        except Exception:
            chunks = chunks[:8]
    else:
        chunks = chunks[:8]
    # Step 4: neighbor expansion (cap 12)
    seen = {c["id"] for c in chunks}
    for n in fetch_neighbor_chunks_batch(chunks, seen, db):
        if len(chunks) >= 12:
            break
        seen.add(n["id"])
        chunks.append(n)
    # Fix 4: commentary cap
    commentary_seen = 0
    capped = []
    for c in chunks:
        if (c.get("source_kind") or c.get("source_type") or "") == "commentary":
            if commentary_seen >= COMMENTARY_CONTEXT_CAP:
                continue
            commentary_seen += 1
        capped.append(c)
    chunks = capped
    # Step 5: conditional lexicon retrieval
    if is_word_study_query(question):
        try:
            lex = db.rpc("match_lexicon_chunks", {"query_embedding": embed_text(question), "match_count": 5}).execute()
            if lex.data:
                for lc in lex.data:
                    lc["_lexicon"] = True
                chunks.extend(lex.data)
        except Exception:
            pass
    return chunks, topic_context_parts


def build_context(chunks, topic_context_parts):
    regular = [c for c in chunks if not c.get("_lexicon")]
    parts = list(topic_context_parts)
    source_num = 0
    for c in regular:
        if _is_citable(c):
            source_num += 1
            label = "[Source %d]" % source_num
        else:
            label = "[Background]"
        parts.append(
            "%s (source_kind=%s, citation_mode=%s) \"%s\" by %s\n%s" % (
                label, c.get("source_kind") or c.get("source_type", "unknown"),
                c.get("citation_mode", "citable"), c.get("title", "Unknown"),
                c.get("author", "Unknown"), c["content"])
        )
    return "\n\n---\n\n".join(parts)


def generate(question, context):
    history = [{"role": "user", "content": "Sources:\n%s\n\nQuestion: %s" % (context, question)}]
    resp = get_anthropic_client().messages.create(
        model="claude-sonnet-4-5", max_tokens=3000,
        system=ANSWER_SYSTEM_BLOCKS, messages=history, stream=False,
    )
    raw = resp.content[0].text
    a0, a1 = raw.find("<answer>"), raw.find("</answer>")
    answer = raw[a0 + len("<answer>"):a1].strip() if (a0 != -1 and a1 != -1) else raw.strip()
    return answer, raw


# ── Teacher extraction ────────────────────────────────────────────────────
# The guard's LINK action operates ONLY on the model's own <reference_mentions>
# TEACHER lines (exactly what verify_references consumes), so those are scored
# for the link metric. A separate strict prose net finds names the model
# attributed in prose but did NOT self-report — used only to detect fabrications
# that never became links (finding #3: the prose text still stands).
_TEACHER_LINE = re.compile(r"^TEACHER:\s*(.+)$", re.MULTILINE)
_PROSE_ATTR = re.compile(
    r"(?:According to|As)\s+([A-Z][a-zA-Z.\-]+(?:\s+[A-Z][a-zA-Z.\-]+){0,3})"
    r"|([A-Z][a-zA-Z.\-]+(?:\s+[A-Z][a-zA-Z.\-]+){0,3})(?:'s)?\s+"
    r"(?:taught|teaches|writes|wrote|argues|notes|reminds|says|said|observed|explains)"
)


def reference_mention_teachers(raw: str) -> List[str]:
    block = raw[raw.find("<reference_mentions>"):] if "<reference_mentions>" in raw else ""
    return sorted({m.group(1).strip() for m in _TEACHER_LINE.finditer(block)})


def prose_teachers(answer: str) -> List[str]:
    names = set()
    for m in _PROSE_ATTR.finditer(answer):
        nm = (m.group(1) or m.group(2) or "").strip()
        if nm and not is_biblical_figure(nm):
            names.add(nm)
    return sorted(names)


def resolve_source_id(name: str) -> Optional[str]:
    if is_biblical_figure(name):
        return None
    key = normalize_alias_key(name)
    if not key:
        return None
    r = db.table("source_aliases").select("source_id").eq("alias_key", key).limit(1).execute()
    if not r.data:
        return None
    return r.data[0]["source_id"]


def classify_link(name: str, grounding) -> Tuple[str, Optional[str]]:
    """Precise denial-cause attribution for a <reference_mentions> teacher —
    isolates the GUARD's action from pre-existing gates. Returns (class, sid)."""
    sid = resolve_source_id(name)
    if sid is None:
        return "UNRESOLVED", None            # not_in_corpus; pre-existing no-link
    if not is_source_servable(db, sid):
        return "LICENSE-DENIED", sid          # pre-existing license gate, not the guard
    source_arm = sid in grounding.source_ids
    author_arm = normalize_alias_key(name) in grounding.author_keys
    if source_arm:
        return "VERIFIED", sid                # shipped gate grants the link
    if author_arm:
        return "CONSERVATIVE-DENY", sid       # retrieved-by-name but resolved source NOT retrieved
    return "GUARD-BLOCKED", sid               # Tozer-class: resolves+servable but not retrieved at all


def run_question(qid, question, run_idx):
    routed = match_position_paper(question)
    if routed:
        print("  [%s run%d] ROUTED to position-paper pillar '%s' — names no teachers, skipped from teacher metric" % (qid, run_idx, routed))
        return {"qid": qid, "run": run_idx, "position_paper": True}

    chunks, topic_parts = retrieve(question)
    grounding = build_retrieval_grounding(chunks, db)
    context = build_context(chunks, topic_parts)
    answer, raw = generate(question, context)

    verified = verify_references(answer, raw, db, grounding)
    verified_names = {v["raw"] for v in verified if v["type"] == "teacher"}
    retrieved_authors = sorted({(c.get("author") or "?") for c in chunks})

    ref_names = reference_mention_teachers(raw)
    rows = []
    for name in ref_names:
        # Pre-existing SP1 presence guard: verify_references drops any
        # reference_mentions name whose exact string is not literally in the
        # <answer> prose (e.g. the model listed "Derek Prince" but the answer
        # says "Prince"). Model that here so a presence-drop is not miscounted
        # as a grounding-guard mismatch.
        if not find_occurrences(answer, name):
            cls, sid = "PRESENCE-DROP", resolve_source_id(name)
        else:
            cls, sid = classify_link(name, grounding)
        linked = name in verified_names
        # Consistency: shipped verify_references must grant a link iff class==VERIFIED.
        mismatch = (cls == "VERIFIED") != linked
        rows.append({"name": name, "source_id": sid, "class": cls, "linked": linked, "mismatch": mismatch})

    # Prose-only fabrications: named in prose, NOT in reference_mentions, and not
    # grounded — a fabrication that got no link only because it was unreported.
    prose_only = [n for n in prose_teachers(answer) if n not in ref_names]
    prose_fabrications = []
    for n in prose_only:
        sid = resolve_source_id(n)
        if not _is_retrieval_grounded(n, sid, grounding):
            prose_fabrications.append(n)

    print("  [%s run%d] retrieved authors: %s" % (qid, run_idx, retrieved_authors))
    print("             grounding.established=%s |source_ids|=%d |author_keys|=%d"
          % (grounding.established, len(grounding.source_ids), len(grounding.author_keys)))
    for r in rows:
        note = "  *** MISMATCH vs verify_references ***" if r["mismatch"] else ""
        print("             REF %-26s %-16s linked=%s%s" % (r["name"], r["class"], r["linked"], note))
    if prose_fabrications:
        print("             prose-only ungrounded names (no link; prose text stands): %s" % prose_fabrications)

    return {"qid": qid, "run": run_idx, "position_paper": False,
            "retrieved_authors": retrieved_authors, "ref_teachers": rows,
            "prose_fabrications": prose_fabrications,
            "grounding_established": grounding.established}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2, help="runs per legit question")
    ap.add_argument("--fab-runs", type=int, default=4, help="runs per fabrication-prone question")
    args = ap.parse_args()

    all_results = []
    out = Path(__file__).resolve().parent / "teacher_name_guard_live_results.json"

    def flush():
        out.write_text(json.dumps(all_results, indent=2))  # incremental: survives an early kill

    print("=" * 90)
    print("FABRICATION-PRONE QUESTIONS (Phase 0 §1/§3) — %d runs each" % args.fab_runs)
    print("=" * 90)
    for qid, q in FAB_QUESTIONS:
        for i in range(args.fab_runs):
            all_results.append(run_question(qid, q, i + 1))
            flush()
            sys.stdout.flush()

    print("\n" + "=" * 90)
    print("LEGITIMATE-ATTRIBUTION QUESTIONS (false-positive measurement) — %d runs each" % args.runs)
    print("=" * 90)
    for qid, q in LEGIT_QUESTIONS:
        for i in range(args.runs):
            all_results.append(run_question(qid, q, i + 1))
            flush()
            sys.stdout.flush()

    # ── Aggregate ──
    normal = [r for r in all_results if not r.get("position_paper")]
    rows = [(r["qid"], t) for r in normal for t in r.get("ref_teachers", [])]
    by_class = {}  # type: Dict[str, list]
    for qid, t in rows:
        by_class.setdefault(t["class"], []).append((qid, t["name"]))
    mismatches = [(qid, t["name"]) for qid, t in rows if t["mismatch"]]
    failclosed = [r["qid"] for r in normal if not r.get("grounding_established", True)]
    prose_fab = [(r["qid"], n) for r in normal for n in r.get("prose_fabrications", [])]

    def show(cls, label):
        items = by_class.get(cls, [])
        print("  %-18s %d" % (label, len(items)))
        for qid, name in items:
            print("      %s: %s" % (qid, name))

    print("\n" + "=" * 90)
    print("AGGREGATE — %d normal-path answers, %d reference-mention teacher attributions" % (len(normal), len(rows)))
    print("=" * 90)
    show("VERIFIED", "VERIFIED link")
    show("GUARD-BLOCKED", "GUARD-BLOCKED")          # Tozer-class: resolves+servable but NOT retrieved -> the guard's win
    show("CONSERVATIVE-DENY", "CONSERVATIVE-DENY")  # retrieved-by-name, resolved source not retrieved (adjudicate: same-person vs homonym)
    show("LICENSE-DENIED", "LICENSE-DENIED")        # pre-existing license gate, not the guard
    show("PRESENCE-DROP", "PRESENCE-DROP")          # pre-existing SP1 presence guard (name's exact form not in answer)
    show("UNRESOLVED", "UNRESOLVED")                # not_in_corpus, pre-existing no-link
    print("\n  verify_references CONSISTENCY MISMATCHES (must be 0): %d %s" % (len(mismatches), mismatches))
    print("  Link false positives = VERIFIED-should-be denied: 0 by construction unless a mismatch above.")
    print("  Fail-closed events (grounding not established): %d %s" % (len(failclosed), failclosed))
    print("\n  Prose-only ungrounded attributions (no link; prose text stands — finding #3): %d" % len(prose_fab))
    for qid, n in prose_fab:
        print("      %s: %s" % (qid, n))

    out = Path(__file__).resolve().parent / "teacher_name_guard_live_results.json"
    out.write_text(json.dumps(all_results, indent=2))
    print("\nSaved -> %s" % out)


if __name__ == "__main__":
    main()
