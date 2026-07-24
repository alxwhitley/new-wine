#!/usr/bin/env python3
"""
score_corpus_quality.py — Phase 1 read-only corpus quality measurement.

Scores every in-scope document (all documents except the Precept Austin
source, which is already governed by a standing source-level exclusion —
see PRECEPT_AUSTIN_SOURCE_ID) on three independent, countable-signal
dimensions:

  1. Attribution risk   — likelihood the single-teacher attribution is
                           wrong or misleading (guest, panel, multi-voice
                           channel).
  2. Signal density      — teaching content vs. packaging (greetings,
                           CTAs, platform language) vs. scripture density.
  3. Text integrity      — cut-off text, OCR/scan garbage, chunk gaps,
                           near-duplicate content.

No LLM calls. No writes of any kind — read-only against the live DB.

Output:
  docs/audits/corpus_quality_scores_<DATE>.json   — full per-document data
  docs/audits/corpus_quality_report_<DATE>.md      — human-readable report

Neither output is committed by this script. See PLAN.md / session notes for
the commit decision on the script itself.

CLI:
    python3 scripts/score_corpus_quality.py
"""

import argparse
import hashlib
import json
import os
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

_parsed = urlparse(os.environ["SUPABASE_DB_URL"])
DB_PARAMS = {
    "host": _parsed.hostname,
    "port": _parsed.port or 5432,
    "user": unquote(_parsed.username or ""),
    "password": unquote(_parsed.password or ""),
    "dbname": _parsed.path.lstrip("/"),
}

PRECEPT_AUSTIN_SOURCE_ID = "698e0596-a9c6-4890-958d-9199f1b8f762"

RANDOM_SEED = 42

# ── Signal definitions (documented here so the report can restate them) ────

TITLE_GUEST_PATTERNS = [
    r"\bw/\s*[A-Z]",
    r"\bft\.?\s+[A-Z]",
    r"\bfeat\.?\s+[A-Z]",
    r"\binterview\b",
    r"\bpanel\b",
    r"\bq\s*&\s*a\b",
    r"\bconversation\s+with\b",
    r"\bguest\b",
    r"\btalks?\s+with\b",
    r"&\s*[A-Z][a-z]+\s+[A-Z][a-z]+",  # "& Firstname Lastname"
]
TITLE_WITH_NAME_RE = re.compile(r"\bwith\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\b")

OPENING_GUEST_PHRASES = [
    "our guest", "please welcome", "joining me", "joining us",
    "my guest today", "welcome to the show", "welcome back to the podcast",
    "please welcome to the stage", "today's guest", "special guest",
    "welcome to the podcast",
]

PLATFORM_PHRASES = [
    "subscribe", "link in the description", "link below", "hit the bell",
    "like and subscribe", "welcome back", "thanks for watching",
    "let's pray", "before we get started", "don't forget to",
    "follow us on", "check out our", "sign up", "for more information",
    "visit our website", "partner with us", "give online", "donate",
    "merchandise", "click the link", "notification bell", "smash that",
    "turn on notifications", "www.", "http://", "https://",
    "in the show notes", "leave a review", "five-star review",
    "become a partner", "text the word",
]

WORD_RE = re.compile(r"[A-Za-z']+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
NONWORD_CHARS_RE = re.compile(r"[^\w\s.,;:!?'\"()\-—–]")
# Excludes digits deliberately: some sources (e.g. HistoricalChristianFaith's
# internal verse-reference codes like "revelation 5000001") legitimately
# contain long digit runs that are not scan/OCR garbage. Real garbling shows
# up as repeated punctuation/letters (dashes, underscores, "IIIII"-style
# font-recognition failures), not repeated digits.
REPEATED_CHAR_RUN_RE = re.compile(r"([^\d\s])\1{4,}")
TERMINAL_PUNCT = set('.!?"\')]”’')

SHINGLE_SIZE = 5
MAX_SHINGLES_SAMPLED = 4000
MINHASH_K = 48
PRIME31 = (1 << 31) - 1
MASK30 = (1 << 30) - 1

_rng = random.Random(RANDOM_SEED)
_A = np.array([_rng.randrange(1, MASK30) for _ in range(MINHASH_K)], dtype=np.int64)
_B = np.array([_rng.randrange(0, MASK30) for _ in range(MINHASH_K)], dtype=np.int64)


def shingle_hashes(text):
    tokens = text.split()
    if len(tokens) < SHINGLE_SIZE:
        shingles = [text] if text.strip() else []
    else:
        shingles = [
            " ".join(tokens[i : i + SHINGLE_SIZE])
            for i in range(len(tokens) - SHINGLE_SIZE + 1)
        ]
    if len(shingles) > MAX_SHINGLES_SAMPLED:
        step = len(shingles) / MAX_SHINGLES_SAMPLED
        shingles = [shingles[int(i * step)] for i in range(MAX_SHINGLES_SAMPLED)]
    if not shingles:
        return np.array([], dtype=np.int64)
    return np.array(
        [int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16) & MASK30 for s in shingles],
        dtype=np.int64,
    )


def minhash_signature(hashes):
    if hashes.size == 0:
        return None
    combined = (np.outer(hashes, _A) + _B) % PRIME31
    return combined.min(axis=0)


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def distribution(vals):
    if not vals:
        return None
    s = sorted(vals)
    return {
        "n": len(s),
        "min": round(s[0], 2),
        "p10": round(percentile(s, 10), 2),
        "p25": round(percentile(s, 25), 2),
        "median": round(percentile(s, 50), 2),
        "p75": round(percentile(s, 75), 2),
        "p90": round(percentile(s, 90), 2),
        "max": round(s[-1], 2),
        "mean": round(statistics.mean(s), 2),
    }


def fetch_documents(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, d.title, d.author, d.source_name, d.source_type,
               d.source_kind, d.original_title, s.name AS source_display_name
        FROM documents d
        LEFT JOIN sources s ON s.id = d.source_id
        WHERE d.source_id IS DISTINCT FROM %s
        """,
        (PRECEPT_AUSTIN_SOURCE_ID,),
    )
    cols = [c.name for c in cur.description]
    docs = {}
    for row in cur:
        rec = dict(zip(cols, row))
        docs[str(rec["id"])] = rec
    cur.close()
    return docs


def fetch_bible_ref_counts(conn):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, COALESCE(array_length(d.bible_references, 1), 0)
        FROM documents d
        WHERE d.source_id IS DISTINCT FROM %s
        """,
        (PRECEPT_AUSTIN_SOURCE_ID,),
    )
    out = {str(i): n for i, n in cur}
    cur.close()
    return out


def stream_chunks(conn):
    cur = conn.cursor(name="chunk_stream")
    cur.itersize = 5000
    cur.execute(
        """
        SELECT c.document_id, c.chunk_index, c.content
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE d.source_id IS DISTINCT FROM %s
        ORDER BY c.document_id, c.chunk_index
        """,
        (PRECEPT_AUSTIN_SOURCE_ID,),
    )
    current_id = None
    current_rows = []
    for doc_id, chunk_index, content in cur:
        doc_id = str(doc_id)
        if current_id is not None and doc_id != current_id:
            yield current_id, current_rows
            current_rows = []
        current_id = doc_id
        current_rows.append((chunk_index, content or ""))
    if current_id is not None:
        yield current_id, current_rows
    cur.close()


def score_document(doc, chunk_rows, bible_ref_count):
    title = doc.get("title") or ""
    full_text = "\n\n".join(c for _, c in chunk_rows)
    full_text_lower = full_text.lower()
    char_count = len(full_text)
    words = WORD_RE.findall(full_text)
    word_count = len(words)

    # ── Attribution risk ────────────────────────────────────────────────
    title_guest_hit = any(re.search(p, title, re.I) for p in TITLE_GUEST_PATTERNS)
    title_with_name_hit = bool(TITLE_WITH_NAME_RE.search(title)) and not title_guest_hit
    opening_text = full_text_lower[:2000]
    opening_guest_hits = sum(1 for p in OPENING_GUEST_PHRASES if p in opening_text)
    attribution_score = (
        (3 if title_guest_hit else 0)
        + (2 if title_with_name_hit else 0)
        + min(opening_guest_hits, 3) * 2
    )
    # multi-voice-channel bonus added in a second pass (needs source-level stats)

    # ── Signal density ───────────────────────────────────────────────────
    platform_hit_count = sum(full_text_lower.count(p) for p in PLATFORM_PHRASES)
    platform_density = platform_hit_count / max(word_count, 1) * 1000
    scripture_density = bible_ref_count / max(word_count, 1) * 1000

    sentences = [s.strip().lower() for s in SENTENCE_SPLIT_RE.split(full_text) if s.strip()]
    long_sentences = [s for s in sentences if len(s.split()) >= 4]
    dup_sentences = len(long_sentences) - len(set(long_sentences))
    repetition_rate = dup_sentences / max(len(long_sentences), 1)

    packaging_score = platform_density + 40 * repetition_rate - min(scripture_density, 15)

    # ── Text integrity ──────────────────────────────────────────────────
    trimmed = full_text.rstrip()
    ends_mid_sentence = (not trimmed) or (trimmed[-1] not in TERMINAL_PUNCT)

    nonword_matches = len(NONWORD_CHARS_RE.findall(full_text))
    nonword_ratio = nonword_matches / max(char_count, 1)

    indices = sorted(idx for idx, _ in chunk_rows if idx is not None)
    gap_count = 0
    if indices:
        expected = set(range(indices[0], indices[-1] + 1))
        gap_count = len(expected - set(indices))

    chunk_lengths = [len(c) for _, c in chunk_rows]
    near_empty = sum(1 for l in chunk_lengths if l < 40)
    near_empty_ratio = near_empty / max(len(chunk_lengths), 1)

    repeated_char_runs = len(REPEATED_CHAR_RUN_RE.findall(full_text))
    # Rate, not raw count — a raw count scales with document length and lets
    # the corpus's handful of 1-2 million-word documents (encyclopedic
    # HistoricalChristianFaith/book entries) dominate purely by being long.
    # Floored denominator (2000 chars) so a couple of incidental matches in a
    # 150-char stub entry don't produce a huge rate from sample-size noise.
    repeated_char_run_rate = repeated_char_runs / max(char_count, 2000) * 10000

    integrity_score = (
        (25 if ends_mid_sentence else 0)
        + nonword_ratio * 400
        + gap_count * 6
        + near_empty_ratio * 30
        + repeated_char_run_rate * 3
    )

    sig = minhash_signature(shingle_hashes(full_text_lower))

    return {
        "word_count": word_count,
        "char_count": char_count,
        "chunk_count": len(chunk_rows),
        "title_guest_hit": title_guest_hit,
        "title_with_name_hit": title_with_name_hit,
        "opening_guest_hits": opening_guest_hits,
        "attribution_score_base": attribution_score,
        "platform_hit_count": platform_hit_count,
        "platform_density": round(platform_density, 3),
        "scripture_density": round(scripture_density, 3),
        "repetition_rate": round(repetition_rate, 4),
        "dup_sentences": dup_sentences,
        "long_sentence_count": len(long_sentences),
        "packaging_score": round(packaging_score, 3),
        "ends_mid_sentence": ends_mid_sentence,
        "nonword_ratio": round(nonword_ratio, 5),
        "gap_count": gap_count,
        "near_empty_chunks": near_empty,
        "near_empty_ratio": round(near_empty_ratio, 4),
        "repeated_char_runs": repeated_char_runs,
        "repeated_char_run_rate": round(repeated_char_run_rate, 3),
        "integrity_score": round(integrity_score, 3),
        "last_120_chars": trimmed[-120:],
        "_minhash": sig,
    }


def classify_sources(docs):
    """Per-source multi-voice-channel vs single-teacher-archive classification."""
    by_source = defaultdict(list)
    for doc_id, doc in docs.items():
        by_source[doc["source_display_name"] or "(unassigned)"].append(doc)

    classification = {}
    for source_name, doclist in by_source.items():
        n = len(doclist)
        authors = [d["author"].strip().lower() for d in doclist if d.get("author")]
        distinct_authors = set(authors)
        match_count = sum(
            1
            for d in doclist
            if d.get("author") and d["author"].strip().lower() == source_name.strip().lower()
        )
        match_rate = match_count / n if n else 0
        source_type_mode = statistics.mode([d["source_type"] for d in doclist]) if doclist else None

        if n >= 3 and len(distinct_authors) >= 3 and match_rate < 0.5:
            label = "multi_voice_channel"
        elif match_rate >= 0.8 or source_type_mode == "book":
            label = "single_teacher_archive"
        else:
            label = "ambiguous"

        classification[source_name] = {
            "label": label,
            "doc_count": n,
            "distinct_authors": len(distinct_authors),
            "author_match_rate": round(match_rate, 3),
        }
    return classification


def find_near_duplicates(docs, scores):
    by_source = defaultdict(list)
    for doc_id, doc in docs.items():
        by_source[doc["source_display_name"] or "(unassigned)"].append(doc_id)

    pairs = []
    for source_name, doc_ids in by_source.items():
        sigs = []
        valid_ids = []
        for doc_id in doc_ids:
            sig = scores[doc_id].get("_minhash")
            if sig is not None:
                sigs.append(sig)
                valid_ids.append(doc_id)
        if len(valid_ids) < 2:
            continue
        mat = np.stack(sigs)  # (n, K)
        n = mat.shape[0]
        # pairwise equality fraction via broadcasting
        eq = (mat[:, None, :] == mat[None, :, :]).mean(axis=2)  # (n, n)
        for i in range(n):
            for j in range(i + 1, n):
                sim = float(eq[i, j])
                if sim >= 0.5:
                    pairs.append((valid_ids[i], valid_ids[j], source_name, round(sim, 3)))
    pairs.sort(key=lambda p: -p[3])
    return pairs


def rank_percentile(values_by_id, doc_ids):
    """Return {doc_id: percentile_rank_0_100} where higher raw value -> higher rank."""
    ordered = sorted(doc_ids, key=lambda i: values_by_id[i])
    n = len(ordered)
    ranks = {}
    for idx, doc_id in enumerate(ordered):
        ranks[doc_id] = idx / max(n - 1, 1) * 100
    return ranks


def describe_worst(doc, m):
    obs = []
    if m["ends_mid_sentence"]:
        obs.append((30, f"ends without terminal punctuation at ~{m['word_count']} words"))
    if m["nonword_ratio"] > 0.015:
        obs.append((m["nonword_ratio"] * 1000, f"{m['nonword_ratio']*100:.1f}% non-word/garbled characters"))
    if m["gap_count"] > 0:
        obs.append((m["gap_count"] * 6, f"{m['gap_count']} missing chunk-index gap(s) out of {m['chunk_count']} chunks"))
    if m["near_empty_ratio"] > 0.15:
        obs.append((m["near_empty_ratio"] * 30, f"{m['near_empty_chunks']}/{m['chunk_count']} chunks are near-empty (<40 chars)"))
    if m["repeated_char_run_rate"] > 3:
        obs.append((m["repeated_char_run_rate"], f"{m['repeated_char_runs']} runs of a repeated non-digit character across the document (scan/OCR artifact pattern)"))
    if m["title_guest_hit"]:
        obs.append((20, "title contains a guest/second-speaker indicator"))
    elif m["title_with_name_hit"]:
        obs.append((12, "title contains \"with <Full Name>\""))
    if m["opening_guest_hits"] > 0:
        obs.append((m["opening_guest_hits"] * 10, f"opening text has guest-introduction language ({m['opening_guest_hits']} phrase(s))"))
    if m.get("multi_voice_bonus", 0) > 0:
        obs.append((15, "attributed to a multi-voice channel, not a single-teacher archive"))
    if m["platform_density"] > 12:
        obs.append((m["platform_density"], f"~{m['platform_density']:.0f} platform/CTA phrases per 1000 words"))
    if m["repetition_rate"] > 0.12:
        obs.append((m["repetition_rate"] * 50, f"{m['repetition_rate']*100:.0f}% of sentences are exact repeats"))
    if m["scripture_density"] < 0.5 and m["word_count"] > 300 and m["packaging_score"] > 5:
        obs.append((5, "near-zero scripture references"))

    if not obs:
        return f"No strong flags; {m['word_count']}-word document, composite score driven by mild cumulative signal."
    obs.sort(key=lambda o: -o[0])
    top = [o[1] for o in obs[:3]]
    return "; ".join(top).capitalize() + "."


def describe_best(doc, m):
    positives = []
    if not m["ends_mid_sentence"]:
        positives.append("ends cleanly")
    if m["platform_density"] < 2:
        positives.append("near-zero platform/CTA language")
    if m["scripture_density"] > 3:
        positives.append(f"{m['scripture_density']:.1f} scripture refs/1000w")
    if m["gap_count"] == 0:
        positives.append("no chunk-index gaps")
    if m["nonword_ratio"] < 0.005:
        positives.append("clean text, no scan artifacts")
    if m.get("multi_voice_bonus", 0) == 0 and not m["title_guest_hit"]:
        positives.append("single-teacher attribution")
    if not positives:
        positives.append("no flags fired on any of the three dimensions")
    return f"{m['word_count']}-word document: " + ", ".join(positives) + "."


def describe_middle(doc, m):
    bits = []
    if m["platform_density"] > 5:
        bits.append(f"moderate platform/CTA density (~{m['platform_density']:.0f}/1000w)")
    if m["scripture_density"] > 0:
        bits.append(f"{m['scripture_density']:.1f} scripture refs/1000w")
    if m["gap_count"] > 0:
        bits.append(f"{m['gap_count']} chunk gap(s)")
    if not bits:
        bits.append("no notable flags on any dimension")
    return f"{m['word_count']}-word document; " + ", ".join(bits) + "."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-24")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_PARAMS)
    print("Connected. Fetching in-scope document metadata...")
    docs = fetch_documents(conn)
    bible_ref_counts = fetch_bible_ref_counts(conn)
    print(f"In-scope documents (excl. Precept Austin): {len(docs)}")

    print("Streaming chunk content and scoring (this pulls ~260MB of text)...")
    scores = {}
    processed = 0
    for doc_id, chunk_rows in stream_chunks(conn):
        if doc_id not in docs:
            continue
        m = score_document(docs[doc_id], chunk_rows, bible_ref_counts.get(doc_id, 0))
        scores[doc_id] = m
        processed += 1
        if processed % 250 == 0:
            print(f"  scored {processed}/{len(docs)}...")
    conn.close()
    print(f"Scored {processed} documents with >=1 chunk.")

    missing = set(docs) - set(scores)
    if missing:
        print(f"WARNING: {len(missing)} in-scope documents had zero chunks and were not scored: {sorted(missing)[:10]}...")

    print("Classifying sources (multi-voice channel vs single-teacher archive)...")
    source_classification = classify_sources(docs)
    for doc_id, m in scores.items():
        source_name = docs[doc_id]["source_display_name"] or "(unassigned)"
        cls = source_classification[source_name]
        bonus = 3 if cls["label"] == "multi_voice_channel" else 0
        m["multi_voice_bonus"] = bonus
        m["attribution_score"] = m["attribution_score_base"] + bonus

    print("Finding near-duplicates (within-source MinHash comparison)...")
    dup_pairs = find_near_duplicates(docs, scores)
    print(f"  found {len(dup_pairs)} candidate pairs at similarity >= 0.5")

    for m in scores.values():
        m.pop("_minhash", None)

    doc_ids = list(scores.keys())
    attribution_ranks = rank_percentile({i: scores[i]["attribution_score"] for i in doc_ids}, doc_ids)
    packaging_ranks = rank_percentile({i: scores[i]["packaging_score"] for i in doc_ids}, doc_ids)
    integrity_ranks = rank_percentile({i: scores[i]["integrity_score"] for i in doc_ids}, doc_ids)
    for doc_id in doc_ids:
        composite = (attribution_ranks[doc_id] + packaging_ranks[doc_id] + integrity_ranks[doc_id]) / 3
        scores[doc_id]["attribution_pctl"] = round(attribution_ranks[doc_id], 2)
        scores[doc_id]["packaging_pctl"] = round(packaging_ranks[doc_id], 2)
        scores[doc_id]["integrity_pctl"] = round(integrity_ranks[doc_id], 2)
        scores[doc_id]["composite"] = round(composite, 2)

    out_dir = ROOT / "docs" / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_records = []
    for doc_id in doc_ids:
        d = docs[doc_id]
        m = scores[doc_id]
        json_records.append(
            {
                "id": doc_id,
                "title": d["title"],
                "author": d["author"],
                "source_name": d["source_display_name"],
                "source_type": d["source_type"],
                "source_kind": d["source_kind"],
                **m,
            }
        )

    json_path = out_dir / f"corpus_quality_scores_{args.date}.json"
    with open(json_path, "w") as f:
        json.dump(
            {
                "scope_count": len(docs),
                "scored_count": len(scores),
                "source_classification": source_classification,
                "duplicate_pairs": [
                    {
                        "doc_id_a": a,
                        "title_a": docs[a]["title"],
                        "doc_id_b": b,
                        "title_b": docs[b]["title"],
                        "source": src,
                        "similarity": sim,
                    }
                    for a, b, src, sim in dup_pairs
                ],
                "documents": json_records,
            },
            f,
            indent=2,
            default=str,
        )
    print(f"Wrote {json_path}")

    print("\nDone. Run build_corpus_quality_report.py (or inspect the JSON) to render the grouped report.")


if __name__ == "__main__":
    main()
