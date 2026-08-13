#!/usr/bin/env python3
"""
propose_non_teacher_spans.py — READ-ONLY proposal of full non-teacher text
spans for documents flagged by the corpus data-quality sweep (type 5).

Connects ONLY via backend/app/.env.readonly-analysis.
Never loads the main app .env. Never INSERT/UPDATE/DELETE/DDL.
Proposals only — nothing is applied.

Input:  corpus_data_quality_review/findings.jsonl  (type 5 rows)
Output: non_teacher_span_proposals/  (progressive JSONL + regrouped MD)

Priority: Andrew Murray, then Derek Prince, then remaining teachers.
Bias: under-propose at ambiguous boundaries.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
READONLY_ENV_PATH = PROJECT_ROOT / "backend" / "app" / ".env.readonly-analysis"
FINDINGS_JSONL = PROJECT_ROOT / "corpus_data_quality_review" / "findings.jsonl"
REVIEW_DIR = PROJECT_ROOT / "non_teacher_span_proposals"
PROPOSALS_JSONL = REVIEW_DIR / "proposals.jsonl"
PROPOSALS_MD = REVIEW_DIR / "proposals.md"
PROGRESS_PATH = REVIEW_DIR / "progress.json"
RUN_LOG = REVIEW_DIR / "run.log"

ROLE_NAME = "rhemata_readonly_analysis"
PROGRESS_EVERY = 1  # every document (corpus is only ~54 unique docs)
PRIORITY_TEACHERS = ("Andrew Murray", "Derek Prince")

# ---------------------------------------------------------------------------
# Logging / progressive I/O
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = "[%s] %s" % (_utc_now(), msg)
    print(line, flush=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_proposal(p: Dict[str, Any]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with PROPOSALS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(p, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def save_progress(state: Dict[str, Any]) -> None:
    state = dict(state)
    state["updated_at"] = _utc_now()
    tmp = PROGRESS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(PROGRESS_PATH)


def load_progress() -> Dict[str, Any]:
    if not PROGRESS_PATH.exists():
        return {}
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def connect_readonly():
    import psycopg2

    if not READONLY_ENV_PATH.exists():
        raise RuntimeError("Missing %s" % READONLY_ENV_PATH)
    url = None
    for line in READONLY_ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("READONLY_ANALYSIS_DB_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url or ROLE_NAME not in url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL missing or not the analysis role")
    p = urlparse(url)
    user = unquote(p.username or "")
    if ROLE_NAME not in user:
        raise RuntimeError("Username is not the read-only analysis role: %r" % user)
    log("Connecting as %s to %s:%s (timeout 20s, no retry)..." % (
        user[:40], p.hostname, p.port or 5432,
    ))
    try:
        conn = psycopg2.connect(
            host=p.hostname,
            port=p.port or 5432,
            user=user,
            password=unquote(p.password or ""),
            dbname=(p.path or "/postgres").lstrip("/") or "postgres",
            connect_timeout=20,
        )
    except Exception as e:
        log("CONNECTION FAILED immediately: %s: %s" % (type(e).__name__, e))
        raise
    conn.set_session(readonly=True, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT current_user")
    cu = cur.fetchone()[0]
    if ROLE_NAME not in cu:
        conn.close()
        raise RuntimeError("Connected as %r, expected %r" % (cu, ROLE_NAME))
    try:
        cur.execute("UPDATE documents SET title = title WHERE false")
        raise RuntimeError("Write was not rejected")
    except Exception as e:
        if "ReadOnlySqlTransaction" in type(e).__name__ or "read-only" in str(e).lower():
            log("Connected OK as %s; write rejection confirmed (%s)" % (cu, type(e).__name__))
        else:
            log("Connected OK as %s; write rejected (%s)" % (cu, type(e).__name__))
    cur.close()
    return conn


# ---------------------------------------------------------------------------
# Load flagged docs
# ---------------------------------------------------------------------------
def load_flagged_docs() -> List[Dict[str, Any]]:
    """Collapse type-5 findings to one work-item per document."""
    by_doc: Dict[str, Dict[str, Any]] = {}
    if not FINDINGS_JSONL.exists():
        raise RuntimeError("Findings file missing: %s" % FINDINGS_JSONL)
    with FINDINGS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("type") != "5_non_teacher_material":
                continue
            did = row["document_id"]
            if did not in by_doc:
                by_doc[did] = {
                    "document_id": did,
                    "title": row.get("title"),
                    "author": row.get("stored_author"),
                    "source_name": row.get("source_name"),
                    "source_type": row.get("source_type"),
                    "source_kind": row.get("source_kind"),
                    "markers": [],
                    "max_confidence": 0.0,
                    "findings": [],
                }
            entry = by_doc[did]
            marker = (row.get("detail") or "").replace("marker=", "").strip() or "unknown"
            if marker not in entry["markers"]:
                entry["markers"].append(marker)
            entry["max_confidence"] = max(
                entry["max_confidence"], float(row.get("confidence") or 0)
            )
            entry["findings"].append(row)
    return list(by_doc.values())


def teacher_key(doc: Dict[str, Any]) -> str:
    return (doc.get("source_name") or doc.get("author") or "Unknown").strip()


def sort_priority(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Murray first, Prince second, then others; within group by conf desc, title."""
    def key(d):
        t = teacher_key(d)
        if t == "Andrew Murray":
            pri = 0
        elif t == "Derek Prince":
            pri = 1
        else:
            pri = 2
        return (pri, t.lower(), -d["max_confidence"], (d.get("title") or "").lower())
    return sorted(docs, key=key)


def load_all_chunks(conn, document_id: str) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.id::text, c.chunk_index, c.content,
               c.quote_ineligible_reason
        FROM chunks c
        WHERE c.document_id = %s::uuid
        ORDER BY c.chunk_index
        """,
        (document_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "chunk_id": r[0],
            "chunk_index": int(r[1]),
            "content": r[2] or "",
            "quote_ineligible_reason": r[3],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Chunk classification helpers
# ---------------------------------------------------------------------------
RE_CCEL = re.compile(
    r"(?i)(christian classics ethereal library|ccel staff writer|www\.ccel\.org|"
    r"this pdf file is from the christian classics|"
    r"make classic christian books available|"
    r"written permission is required for commercial use|"
    r"all other rights are re-?\s*served|"
    r"scanned and corrected by|"
    r"electronic text note|"
    r"author\(s\):\s*|publisher:\s*grand rapids)"
)
RE_TOC_LIKE = re.compile(
    r"(?i)(table of contents|contents\s*$|indexes?\s*$|"
    r"index of scripture|index of pages of the print|"
    r"index of scripture commentary)"
)
RE_TITLE_PAGE = re.compile(
    r"(?i)(title page|^\s*by\s*$|^\s*rev\.\s|published by|fleming h\. revell|"
    r"isbn\b|copyright\s+\d{4})"
)
RE_TRANSLATOR = re.compile(
    r"(?i)(translator'?s?\s+note|^\s*translated by\b|for author and\s+translator|"
    r"—\s*translator\b|\btranslator\b)"
)
RE_SCRIPTURE_INDEX = re.compile(
    r"(?i)(index of scripture references|index of scripture commentary|"
    r"index of pages of the print edition|^\s*indexes?\s*$)"
)
RE_RELATED = re.compile(
    r"(?i)(related books|you might also enjoy|essentials of prayer|"
    r"abby zwart|ccel staff writer)"
)
RE_ANNOUNCER = re.compile(
    r"(?i)(this is dick leggatt|president of derek prince ministries|"
    r"thrilled to be giving you the introduction|"
    r"never before released message|"
    r"i am thrilled to be able to bring|"
    r"opening remarks by|introduction by\b|"
    r"guest speaker)"
)
RE_EDITOR = re.compile(
    r"(?i)(editor'?s?\s+note|it has been thought of advantage to the reader|"
    r"throughout the preceding pages\s+the author|"
    r"heidelberg catechism|directory of public worship)"
)
RE_TEACHER_START_HINTS = re.compile(
    r"(?i)("
    r"^\s*preface\s*$|^\s*introduction\s*$|^\s*chapter\s+[ivxlc\d]|"
    r"^\s*i\.\s+[A-Z]|^\s*1\.\s+[A-Z]|"
    r"absolute surrender|the deeper christian life|"
    # first-person teaching openers (weak; used only as supporting signal)
    r"\bI (want|wish|have|am|was|pray|believe|remember|long|feel|know)\b|"
    r"\bmy (dear |beloved )?(brethren|friends|reader|hearers)\b|"
    r"what is god'?s solution|"  # known Prince start after Leggatt
    r"^\s*ANDREW MURRAY\b|Wellington,\s*\d"
    r")"
)

# Verse-index body: lines that look like "Genesis" / "3:14" / bare book lists
RE_INDEX_BODY = re.compile(
    r"(?i)^(\s*[1-3]?\s*[A-Za-z]+\s*$|\s*\d+:\d+|\s*[A-Za-z]+\s+\d+:\d+)"
)


def _marker_bucket(markers: List[str]) -> Set[str]:
    """Map raw marker labels into analysis buckets."""
    buckets = set()
    for m in markers:
        m = m.lower()
        if m in ("ccel_staff", "ccel_boilerplate", "scanner_credit", "electronic_text_note",
                 "copyright_boilerplate", "published_by"):
            buckets.add("front_matter")
        elif m in ("scripture_index", "print_index"):
            buckets.add("back_index")
        elif m in ("translator_note", "translator_word", "translated_by"):
            buckets.add("translator")
        elif m in ("related_books_promo",):
            buckets.add("related_books")
        elif m in ("announcer_leggatt", "dpm_introducer", "third_party_intro",
                   "guest_speaker", "introduction_by", "opening_remarks_by"):
            buckets.add("announcer")
        elif m in ("editors_note", "editorial", "heidelberg_catechism",
                   "directory_of_public_worship", "appendix_heading"):
            buckets.add("editor_appendix")
        else:
            buckets.add("other")
    return buckets


def _score_non_teacher_chunk(
    content: str,
    buckets: Set[str],
    chunk_index: int = 0,
    n_chunks: int = 1,
) -> Tuple[str, float]:
    """
    Return (label, confidence) for a single chunk:
      pure_non_teacher | mixed | teacher_or_unknown

    Mid-body chunks need STRONG structural markers. A lone "translator" or
    "translated by" in teaching prose is not enough (Prince Greek lessons,
    Murray body footnotes) — those become mixed/ambiguous, never pure cuts.
    """
    if not content or not content.strip():
        return "teacher_or_unknown", 0.0
    text = content
    n = len(text)
    hits = 0.0
    reasons = []
    strong = False  # structural / apparatus markers safe to cut as pure

    if RE_CCEL.search(text):
        hits += 3
        reasons.append("ccel")
        strong = True
    if re.search(r"(?i)Author\(s\):", text) and re.search(r"(?i)Publisher:", text):
        hits += 2.5
        reasons.append("catalog")
        strong = True
    if RE_TOC_LIKE.search(text) and n < 2500:
        hits += 2
        reasons.append("toc")
        # TOC at head or "Index of..." is strong; bare "contents" mid-body is weaker
        if re.search(r"(?i)index of scripture|index of pages|table of contents", text):
            strong = True
        elif chunk_index <= 3:
            strong = True
    if RE_TITLE_PAGE.search(text) and n < 2000 and chunk_index <= 5:
        hits += 1.5
        reasons.append("title_page")
    # Translator NOTE heading is strong; bare "translator"/"translated by" is weak
    if re.search(r"(?i)translator'?s?\s+note", text):
        hits += 3
        reasons.append("translator_note_heading")
        strong = True
    elif RE_TRANSLATOR.search(text):
        hits += 1.0
        reasons.append("translator_word_weak")
    if RE_SCRIPTURE_INDEX.search(text):
        hits += 3
        reasons.append("index")
        strong = True
    if RE_RELATED.search(text):
        hits += 2.5
        reasons.append("related")
        strong = True
    if RE_ANNOUNCER.search(text):
        hits += 3
        reasons.append("announcer")
        # announcer blocks often share a chunk with teacher speech → mixed default
    if RE_EDITOR.search(text):
        hits += 2.5
        reasons.append("editor")
        if re.search(r"(?i)heidelberg|directory of public worship|appendix", text):
            strong = True

    # Index-like body: high ratio of short reference lines
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if lines:
        indexish = sum(1 for ln in lines if RE_INDEX_BODY.match(ln) or re.match(r"^\s*\d+:\d+", ln))
        if indexish / max(len(lines), 1) > 0.45 and len(lines) >= 5:
            hits += 3
            reasons.append("index_body")
            strong = True

    teacher_hint = bool(RE_TEACHER_START_HINTS.search(text))
    # Substantial first-person teaching density → treat as teacher-ish
    fp = len(re.findall(r"\b(I|my|we|our)\b", text))
    if fp >= 12 and n > 400:
        teacher_hint = True

    at_head = chunk_index <= 5
    at_tail = chunk_index >= max(0, n_chunks - 4)

    # Announcer: almost never pure whole-chunk (handoff is mid-chunk)
    if "announcer" in reasons:
        if teacher_hint or fp >= 4:
            return "mixed", 0.60
        if at_head and hits >= 3:
            return "pure_non_teacher", 0.90
        return "mixed", 0.65

    # Weak translator word alone mid-body: never pure
    if reasons == ["translator_word_weak"] or (
        "translator_word_weak" in reasons and not strong and not at_head
    ):
        return "mixed", 0.45

    # Mid-body pure requires strong structural marker
    if not at_head and not at_tail and not strong:
        if hits >= 2:
            return "mixed", 0.50
        return "teacher_or_unknown", 0.0

    if hits >= 3 and not teacher_hint and strong:
        return "pure_non_teacher", min(0.98, 0.75 + hits * 0.04)
    if hits >= 3 and teacher_hint:
        return "mixed", 0.55
    if hits >= 2.5 and strong and not teacher_hint:
        return "pure_non_teacher", 0.85
    if hits >= 2 and at_head and not teacher_hint:
        return "pure_non_teacher", 0.80
    if hits >= 2 and teacher_hint:
        return "mixed", 0.55
    if hits >= 2:
        return "mixed", 0.55  # under-propose: mid uncertainty → mixed not pure
    return "teacher_or_unknown", 0.0


def _find_split_in_mixed(content: str, buckets: Set[str]) -> Optional[Dict[str, Any]]:
    """
    Try to find a confident cut inside a mixed chunk.
    Returns dict with non_teacher_portion, teacher_portion_start_snippet, method
    or None if no confident cut.
    """
    # Announcer → teacher: look for known Prince-style handoff
    if "announcer" in buckets or RE_ANNOUNCER.search(content):
        # Prefer the earliest high-confidence handoff; non_teacher is ONLY the intro.
        # Apostrophes/quotes may be straight or curly (’ “ ”)
        patterns = [
            (
                re.compile(
                    r"(?is)^(.*?Never before released message called[^\n]*[\.\!\u201d\"']\s*\n+)"
                    r"(What is God.?s solution\?)",
                ),
                0.95,
            ),
            (
                re.compile(
                    r"(?is)^(.*?I[\u2019']m thrilled to be able to bring it to you\.[^\n]*\n+)"
                    r"(What is God.?s solution\?)",
                ),
                0.95,
            ),
            (
                re.compile(
                    r"(?is)^(.*?never before released message called[^\n]*\n+)"
                    r"(What is God.?s solution\?)",
                ),
                0.93,
            ),
            (
                re.compile(
                    r"(?is)^(.*?never before released message called[^\n]*\n+)"
                    r"([A-Z][^\n]{15,})",
                ),
                0.88,
            ),
        ]
        for pat, conf in patterns:
            m = pat.search(content)
            if m:
                non_t = m.group(1)
                rest = content[m.end(1):]
                # Refuse if non_teacher portion still contains teacher opener
                if re.search(r"(?i)what is god.?s solution", non_t):
                    continue
                if len(non_t.strip()) > 40 and len(rest.strip()) > 20:
                    return {
                        "non_teacher_portion": non_t,
                        "after_start": rest.strip()[:120],
                        "method": "announcer_handoff_pattern",
                        "confidence": conf,
                    }

    # Translator note block ending before Preface
    if "translator" in buckets or RE_TRANSLATOR.search(content):
        m = re.search(
            r"(?is)(.*translator'?s?\s+note.*?)((?:Preface|Introduction|Chapter\s+[IVXLC1]|I\.\s+[A-Z]).*)",
            content,
        )
        if m and len(m.group(1).strip()) > 30:
            return {
                "non_teacher_portion": m.group(1),
                "after_start": m.group(2).strip()[:120],
                "method": "translator_before_preface",
                "confidence": 0.92,
            }
        # Signature end of translator note: initials + place + date, then Preface
        m2 = re.search(
            r"(?is)(.*(?:translator|J\.P\.L\.|Abbroath|translated by)[^\n]*\n(?:[^\n]*\n){0,6})"
            r"((?:Preface|Introduction)\b.*)",
            content,
        )
        if m2 and len(m2.group(1).strip()) > 40:
            return {
                "non_teacher_portion": m2.group(1),
                "after_start": m2.group(2).strip()[:120],
                "method": "translator_signature_then_preface",
                "confidence": 0.88,
            }

    # CCEL / title page ending when chapter/preface begins mid-chunk
    if "front_matter" in buckets or RE_CCEL.search(content) or RE_TITLE_PAGE.search(content):
        # Split at first clear chapter/preface after title-page furniture
        m = re.search(
            r"(?is)(.*?)"
            r"(?="
            r"(?:^|\n)(?:Preface|Introduction|Chapter\s+[IVXLC\d]+|"
            r"I\.\s+[A-Z][a-z]|1\.\s+[A-Z][a-z]|"
            r"Absolute Surrender|The New Life|"
            r"In intercourse with young converts|"  # New Life Murray preface
            r"What is God.?s solution)"
            r")",
            content,
        )
        # Prefer splits that leave substantial non-teacher head and teacher tail
        for pat in [
            re.compile(
                r"(?is)(.*?(?:Title Page|BY\s*\n\s*Rev\.\s+[A-Za-z .]+|Fleming H\. Revell|"
                r"Written permission is required for commercial use\.|"
                r"iii|iv|v)\s*\n+)"
                r"((?:Preface|Introduction|Chapter|I\.|1\.|[A-Z][a-z]+ [a-z]+).*)",
            ),
            re.compile(
                r"(?is)(.*christian classics ethereal library.*?)"
                r"((?:Preface|Introduction)\b.*)",
            ),
        ]:
            m = pat.search(content)
            if m and len(m.group(1).strip()) > 50 and len(m.group(2).strip()) > 80:
                # Refuse if the "teacher" side still looks like CCEL catalog
                if RE_CCEL.search(m.group(2)[:200]) and not RE_TEACHER_START_HINTS.search(m.group(2)[:300]):
                    continue
                return {
                    "non_teacher_portion": m.group(1),
                    "after_start": m.group(2).strip()[:120],
                    "method": "front_matter_before_body",
                    "confidence": 0.85,
                }

    # Editor appendix: whole remaining tail often non-teacher once "APPENDIX" hits
    if "editor_appendix" in buckets or RE_EDITOR.search(content):
        m = re.search(
            r"(?is)(.*?)((?:APPENDIX|Heidelberg Catechism|Directory of Public Worship|"
            r"Throughout the preceding pages).*)",
            content,
        )
        if m and len(m.group(2).strip()) > 80:
            # If group1 is short teacher tail-end, only propose group2
            return {
                "non_teacher_portion": m.group(2),
                "after_start": None,
                "method": "appendix_from_heading",
                "confidence": 0.90,
                "prefix_kept_as_teacher": m.group(1)[-80:] if m.group(1).strip() else None,
            }

    return None


def _context_wrap(full_doc_text: str, span: str, pad: int = 40) -> str:
    """Return span with a few words of surrounding context for location."""
    if not span:
        return ""
    # Normalize for find: try exact, then stripped
    idx = full_doc_text.find(span)
    if idx < 0:
        # try first 80 chars
        head = span[:80]
        idx = full_doc_text.find(head)
        if idx < 0:
            return "…%s…" % span[:500]
        end = idx + len(span) if full_doc_text[idx:idx + len(span)] == span else idx + min(len(span), len(full_doc_text) - idx)
    else:
        end = idx + len(span)
    before = full_doc_text[max(0, idx - pad):idx]
    after = full_doc_text[end:end + pad]
    # word-boundary trim of before/after display
    return "%s⟦%s⟧%s" % (before, span, after)


def propose_spans_for_document(
    doc: Dict[str, Any],
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Produce one or more span proposals for a document.
    Under-propose at ambiguous boundaries.
    """
    if not chunks:
        return [{
            "document_id": doc["document_id"],
            "title": doc.get("title"),
            "teacher": teacher_key(doc),
            "author": doc.get("author"),
            "source_name": doc.get("source_name"),
            "kind": "no_chunks",
            "confidence": 0.0,
            "ambiguous": True,
            "problem": "Document has no chunks; cannot propose a span.",
            "span_text": None,
            "chunk_index_start": None,
            "chunk_index_end": None,
            "markers_from_sweep": doc.get("markers"),
        }]

    buckets = _marker_bucket(doc.get("markers") or [])
    # Classify every chunk
    n_chunks = len(chunks)
    labels = []
    for ch in chunks:
        lab, conf = _score_non_teacher_chunk(
            ch["content"], buckets, ch["chunk_index"], n_chunks,
        )
        labels.append((lab, conf, ch))

    full_text = "\n".join(ch["content"] for ch in chunks)
    proposals: List[Dict[str, Any]] = []

    # --- Strategy A: contiguous pure_non_teacher runs (front / middle / back) ---
    i = 0
    n = len(labels)
    while i < n:
        lab, conf, ch = labels[i]
        if lab != "pure_non_teacher":
            i += 1
            continue
        j = i
        min_conf = conf
        while j + 1 < n and labels[j + 1][0] == "pure_non_teacher":
            j += 1
            min_conf = min(min_conf, labels[j][1])
        # Build span from chunks i..j
        span_chunks = chunks[i : j + 1]
        span_text = "\n".join(c["content"] for c in span_chunks)
        kind = _infer_kind(span_text, buckets, span_chunks[0]["chunk_index"], n)
        # Only emit if confidence high enough; refuse mid-body pure runs
        # that look like teaching prose (safety net for scorer misses).
        c0 = span_chunks[0]["chunk_index"]
        c1 = span_chunks[-1]["chunk_index"]
        mid_body = c0 > 8 and c1 < n - 5
        looks_like_teaching = (
            len(re.findall(r"\b(I|my|we|our)\b", span_text)) >= 15
            and not RE_CCEL.search(span_text)
            and not RE_SCRIPTURE_INDEX.search(span_text)
            and not re.search(r"(?i)translator'?s?\s+note", span_text)
            and not RE_ANNOUNCER.search(span_text)
            and not RE_EDITOR.search(span_text)
        )
        if mid_body and looks_like_teaching:
            i = j + 1
            continue
        # Refuse pure spans that still contain clear teacher openers (announcer
        # handoff left in the chunk, index walkback into body, etc.)
        if re.search(r"(?i)what is god.?s solution\?", span_text):
            # keep only text BEFORE that opener if announcer present
            m = re.search(r"(?is)^(.*?Never before released message called[^\n]*\n+)(What is God)", span_text)
            if m and len(m.group(1).strip()) > 40:
                span_text = m.group(1)
                kind = "announcer_introduction"
                min_conf = min(min_conf, 0.90)
            else:
                i = j + 1
                continue
        # Safety: scripture_index spans must begin AT the index heading.
        # Drop any preceding teacher chapter text in the same opening chunk.
        if kind == "scripture_index":
            m = RE_SCRIPTURE_INDEX.search(span_text)
            if not m:
                i = j + 1
                continue
            if m.start() > 40:
                cut_at = m.start()
                span_text = span_text[cut_at:]
                acc = 0
                new_start = c0
                for c in span_chunks:
                    if acc + len(c["content"]) + 1 > cut_at:
                        new_start = c["chunk_index"]
                        break
                    acc += len(c["content"]) + 1
                c0 = new_start
                span_chunks = [c for c in span_chunks if c["chunk_index"] >= c0]
        # Safety: editor_appendix pure runs need a real appendix/catechism marker
        if kind == "editor_appendix":
            if not re.search(
                r"(?i)(appendix|heidelberg catechism|directory of public worship|"
                r"throughout the preceding pages\s+the author)",
                span_text[:800],
            ):
                i = j + 1
                continue
        # Safety: related_books at head of CCEL books is often front matter —
        # rekind if it's really catalog/front matter
        if kind == "related_books_promo" and c0 <= 2 and RE_CCEL.search(span_text):
            kind = "publisher_front_matter"
        if min_conf >= 0.70 and len(span_text.strip()) >= 40:
            proposals.append(_make_proposal(
                doc, c0, c1,
                span_text, kind, min_conf, False, None, full_text,
                [c["chunk_id"] for c in span_chunks],
            ))
        i = j + 1

    # --- Strategy B: mixed boundary chunks — only high-confidence splits ---
    for idx, (lab, conf, ch) in enumerate(labels):
        if lab != "mixed":
            continue
        split = _find_split_in_mixed(ch["content"], buckets)
        if split and float(split.get("confidence") or 0) >= 0.85:
            # Check we aren't double-covering text already in a pure span
            portion = split["non_teacher_portion"]
            if any(portion.strip() and portion.strip() in (p.get("span_text") or "") for p in proposals):
                continue
            if any((p.get("span_text") or "") and (p["span_text"] in portion) for p in proposals):
                # portion supersedes a smaller pure proposal that was only part of mixed — keep both if non-overlap ok
                pass
            proposals.append(_make_proposal(
                doc, ch["chunk_index"], ch["chunk_index"],
                portion, _infer_kind(portion, buckets, ch["chunk_index"], n),
                float(split["confidence"]),
                False,
                "Boundary split method=%s; text after proposed cut begins: %r" % (
                    split.get("method"), (split.get("after_start") or "")[:100],
                ),
                full_text,
                [ch["chunk_id"]],
            ))
        else:
            # Ambiguous mixed — flag, do NOT propose a cut of the whole chunk
            # But if there's a clear pure submarker line, note it
            snippet = ch["content"][:300]
            proposals.append({
                "document_id": doc["document_id"],
                "title": doc.get("title"),
                "teacher": teacher_key(doc),
                "author": doc.get("author"),
                "source_name": doc.get("source_name"),
                "kind": "ambiguous_boundary",
                "confidence": 0.50,
                "ambiguous": True,
                "problem": (
                    "Chunk contains both non-teacher markers and apparent teacher "
                    "or unclassifiable prose. No confident cut proposed (under-propose)."
                ),
                "span_text": None,
                "locator_snippet": snippet.replace("\n", " ")[:240],
                "chunk_index_start": ch["chunk_index"],
                "chunk_index_end": ch["chunk_index"],
                "chunk_ids": [ch["chunk_id"]],
                "markers_from_sweep": doc.get("markers"),
                "note": "Review this chunk manually. Prefer leaving teacher text intact.",
            })

    # --- Strategy C: back index — ONLY from an explicit index heading forward ---
    if "back_index" in buckets:
        start_idx = None
        for k, ch in enumerate(chunks):
            if RE_SCRIPTURE_INDEX.search(ch["content"]):
                # Prefer the last occurrence of an index heading (back matter)
                start_idx = k
        if start_idx is not None and start_idx >= max(0, n - 40):
            # Always begin AT the index heading inside the first index chunk
            first = chunks[start_idx]["content"]
            m = RE_SCRIPTURE_INDEX.search(first)
            if m:
                portion = first[m.start():]
                rest = "\n".join(c["content"] for c in chunks[start_idx + 1 :])
                span_text = portion + (("\n" + rest) if rest else "")
                if len(span_text.strip()) > 30 and not _span_already_covered(
                    proposals, span_text, start_idx, n - 1
                ):
                    proposals.append(_make_proposal(
                        doc, chunks[start_idx]["chunk_index"], chunks[-1]["chunk_index"],
                        span_text, "scripture_index", 0.92, False,
                        "Index span starts at heading; any teacher text before the heading in that chunk is excluded.",
                        full_text,
                        [c["chunk_id"] for c in chunks[start_idx:]],
                    ))
            else:
                span_chunks = chunks[start_idx:]
                span_text = "\n".join(c["content"] for c in span_chunks)
                if len(span_text.strip()) > 30 and not _span_already_covered(
                    proposals, span_text, start_idx, n - 1
                ):
                    proposals.append(_make_proposal(
                        doc, span_chunks[0]["chunk_index"], span_chunks[-1]["chunk_index"],
                        span_text, "scripture_index", 0.88, False, None, full_text,
                        [c["chunk_id"] for c in span_chunks],
                    ))
        elif start_idx is None:
            # No explicit heading — only take pure trailing index_body chunks near end
            k = n - 1
            while k >= max(0, n - 5) and labels[k][0] == "pure_non_teacher":
                if "index" in (chunks[k]["content"] or "").lower() or len(
                    re.findall(r"\d+:\d+", chunks[k]["content"] or "")
                ) >= 5:
                    k -= 1
                    continue
                break
            start_idx2 = k + 1
            if start_idx2 < n:
                span_chunks = chunks[start_idx2:]
                span_text = "\n".join(c["content"] for c in span_chunks)
                if len(span_text.strip()) > 30 and not _span_already_covered(
                    proposals, span_text, start_idx2, n - 1
                ):
                    proposals.append(_make_proposal(
                        doc, span_chunks[0]["chunk_index"], span_chunks[-1]["chunk_index"],
                        span_text, "scripture_index", 0.85, False,
                        "Trailing index-like chunks without explicit heading.",
                        full_text,
                        [c["chunk_id"] for c in span_chunks],
                    ))

    # --- Strategy D: translator multi-chunk block ---
    if "translator" in buckets:
        # Find first chunk with translator note heading
        t_start = None
        for k, ch in enumerate(chunks):
            if re.search(r"(?i)translator'?s?\s+note", ch["content"]):
                t_start = k
                break
            if RE_TRANSLATOR.search(ch["content"]) and k <= 8:
                t_start = k
                break
        if t_start is not None:
            # Extend while still translator-ish / until clear preface by teacher
            t_end = t_start
            for k in range(t_start, min(t_start + 8, n)):
                text = chunks[k]["content"]
                # Stop before a chunk that is pure teacher preface without translator language
                has_tr = bool(RE_TRANSLATOR.search(text))
                has_preface = bool(re.search(r"(?i)\bpreface\b", text))
                if k > t_start and has_preface and not has_tr:
                    # If preface and translator share chunk, handled by mixed split
                    break
                if k > t_start and not has_tr and labels[k][0] == "teacher_or_unknown":
                    break
                t_end = k
                # If this chunk ends translator and starts preface, try split
                if has_tr and has_preface:
                    split = _find_split_in_mixed(text, {"translator"})
                    if split and float(split.get("confidence") or 0) >= 0.85:
                        # emit earlier full chunks + split portion
                        if t_end > t_start:
                            pre = chunks[t_start:t_end]
                            # only chunks before this one fully
                            pre = chunks[t_start:k]
                            if pre and k > t_start:
                                pre = chunks[t_start:k]
                        # Replace with careful emission below
                        span_chunks = chunks[t_start:k]
                        if span_chunks:
                            # full prior chunks + non_teacher portion of k
                            parts = [c["content"] for c in span_chunks]
                            # last is mixed — use portion only
                            if span_chunks[-1]["chunk_index"] == chunks[k]["chunk_index"]:
                                parts[-1] = split["non_teacher_portion"]
                            span_text = "\n".join(parts)
                            if not _span_already_covered(proposals, span_text, t_start, k):
                                proposals.append(_make_proposal(
                                    doc, chunks[t_start]["chunk_index"], chunks[k]["chunk_index"],
                                    span_text, "translators_note",
                                    float(split["confidence"]), False,
                                    "Translator block ending mid-chunk before: %r" % (
                                        (split.get("after_start") or "")[:100],
                                    ),
                                    full_text,
                                    [c["chunk_id"] for c in chunks[t_start : k + 1]],
                                ))
                        t_end = None  # mark handled
                        break
                    else:
                        # ambiguous — don't take the mixed chunk
                        if k > t_start:
                            span_chunks = chunks[t_start:k]
                            span_text = "\n".join(c["content"] for c in span_chunks)
                            if span_text.strip() and not _span_already_covered(
                                proposals, span_text, t_start, k - 1
                            ):
                                proposals.append(_make_proposal(
                                    doc, span_chunks[0]["chunk_index"], span_chunks[-1]["chunk_index"],
                                    span_text, "translators_note", 0.88, False,
                                    "Stopped before mixed chunk %d (ambiguous boundary)." % chunks[k]["chunk_index"],
                                    full_text,
                                    [c["chunk_id"] for c in span_chunks],
                                ))
                            proposals.append({
                                "document_id": doc["document_id"],
                                "title": doc.get("title"),
                                "teacher": teacher_key(doc),
                                "author": doc.get("author"),
                                "source_name": doc.get("source_name"),
                                "kind": "ambiguous_boundary",
                                "confidence": 0.50,
                                "ambiguous": True,
                                "problem": (
                                    "Translator material may continue into chunk %d which also "
                                    "appears to contain teacher preface/body. No cut proposed for that chunk."
                                    % chunks[k]["chunk_index"]
                                ),
                                "span_text": None,
                                "locator_snippet": chunks[k]["content"][:240].replace("\n", " "),
                                "chunk_index_start": chunks[k]["chunk_index"],
                                "chunk_index_end": chunks[k]["chunk_index"],
                                "chunk_ids": [chunks[k]["chunk_id"]],
                                "markers_from_sweep": doc.get("markers"),
                            })
                        t_end = None
                        break
            if t_end is not None:
                span_chunks = chunks[t_start : t_end + 1]
                span_text = "\n".join(c["content"] for c in span_chunks)
                # Only if not already covered
                if not _span_already_covered(proposals, span_text, t_start, t_end):
                    # If any chunk in range is mixed without split, shrink
                    clean = []
                    for c in span_chunks:
                        lab, _, _ = labels[c["chunk_index"] if c["chunk_index"] < n else 0]
                        # use position in chunks list
                    # simpler: require all pure or accept with note
                    all_pure = all(
                        labels[pos][0] == "pure_non_teacher"
                        for pos in range(t_start, t_end + 1)
                    )
                    if all_pure:
                        proposals.append(_make_proposal(
                            doc, span_chunks[0]["chunk_index"], span_chunks[-1]["chunk_index"],
                            span_text, "translators_note", 0.93, False, None, full_text,
                            [c["chunk_id"] for c in span_chunks],
                        ))
                    else:
                        # only take pure prefix
                        pure_end = t_start - 1
                        for pos in range(t_start, t_end + 1):
                            if labels[pos][0] == "pure_non_teacher":
                                pure_end = pos
                            else:
                                break
                        if pure_end >= t_start:
                            span_chunks = chunks[t_start : pure_end + 1]
                            span_text = "\n".join(c["content"] for c in span_chunks)
                            proposals.append(_make_proposal(
                                doc, span_chunks[0]["chunk_index"], span_chunks[-1]["chunk_index"],
                                span_text, "translators_note", 0.90, False,
                                "Under-proposed: stopped before non-pure chunk.",
                                full_text,
                                [c["chunk_id"] for c in span_chunks],
                            ))
                        if pure_end + 1 <= t_end:
                            proposals.append({
                                "document_id": doc["document_id"],
                                "title": doc.get("title"),
                                "teacher": teacher_key(doc),
                                "author": doc.get("author"),
                                "source_name": doc.get("source_name"),
                                "kind": "ambiguous_boundary",
                                "confidence": 0.50,
                                "ambiguous": True,
                                "problem": "Possible further translator material after proposed pure prefix; not cut.",
                                "span_text": None,
                                "locator_snippet": chunks[pure_end + 1]["content"][:240].replace("\n", " "),
                                "chunk_index_start": chunks[pure_end + 1]["chunk_index"],
                                "chunk_index_end": chunks[t_end]["chunk_index"],
                                "chunk_ids": [c["chunk_id"] for c in chunks[pure_end + 1 : t_end + 1]],
                                "markers_from_sweep": doc.get("markers"),
                            })

    # --- Strategy E: announcer from doc start (always try join 0+1) ---
    if "announcer" in buckets and n >= 1:
        joined = chunks[0]["content"]
        end_i = 0
        if n > 1:
            joined = chunks[0]["content"] + "\n" + chunks[1]["content"]
            end_i = 1
        split = _find_split_in_mixed(joined, {"announcer"})
        if split and float(split.get("confidence") or 0) >= 0.85:
            portion = split["non_teacher_portion"]
            # Refuse if portion still contains teacher opener
            if not re.search(r"(?i)what is god.?s solution", portion):
                # Prefer this joined handoff over any earlier partial announcer spans
                # (a shorter pure-chunk span can be a subset of `portion`, which would
                # make _span_already_covered wrongly skip the better full intro).
                proposals[:] = [
                    p for p in proposals
                    if not (
                        p.get("kind") == "announcer_introduction"
                        and not p.get("ambiguous")
                        and p.get("chunk_index_start") is not None
                        and int(p["chunk_index_start"]) <= end_i
                    )
                ]
                # Also drop ambiguous_boundary flags for the same head chunks
                proposals[:] = [
                    p for p in proposals
                    if not (
                        p.get("ambiguous")
                        and p.get("chunk_index_start") is not None
                        and int(p["chunk_index_start"]) <= end_i
                        and p.get("kind") in ("ambiguous_boundary", "announcer_introduction")
                    )
                ]
                proposals.append(_make_proposal(
                    doc, 0, end_i,
                    portion, "announcer_introduction",
                    float(split["confidence"]), False,
                    "Announcer intro; teacher begins: %r" % (
                        (split.get("after_start") or "")[:100],
                    ),
                    full_text,
                    [c["chunk_id"] for c in chunks[: end_i + 1]],
                ))
        else:
            # Only add ambiguous if we have no solid announcer span yet
            if not any(
                p.get("kind") == "announcer_introduction" and not p.get("ambiguous")
                for p in proposals
            ):
                proposals.append({
                    "document_id": doc["document_id"],
                    "title": doc.get("title"),
                    "teacher": teacher_key(doc),
                    "author": doc.get("author"),
                    "source_name": doc.get("source_name"),
                    "kind": "ambiguous_boundary",
                    "confidence": 0.55,
                    "ambiguous": True,
                    "problem": (
                        "Announcer/introducer language present near document start, "
                        "but handoff to teacher is not confidently locatable. No cut proposed."
                    ),
                    "span_text": None,
                    "locator_snippet": chunks[0]["content"][:240].replace("\n", " "),
                    "chunk_index_start": 0,
                    "chunk_index_end": min(1, n - 1),
                    "chunk_ids": [c["chunk_id"] for c in chunks[: min(2, n)]],
                    "markers_from_sweep": doc.get("markers"),
                })

    # Drop pure spans that are supersets of a tighter split (e.g. whole announcer
    # chunk that still contains teacher text when a handoff split also exists).
    tightened = []
    for p in proposals:
        if p.get("ambiguous") or not p.get("span_text"):
            tightened.append(p)
            continue
        st = p["span_text"]
        # If another non-ambiguous proposal is a proper prefix of this one and
        # this one continues into teacher-looking text, drop this one.
        dominated = False
        for q in proposals:
            if q is p or q.get("ambiguous") or not q.get("span_text"):
                continue
            qt = q["span_text"]
            if qt and st.startswith(qt.strip()[:80]) and len(st) > len(qt) + 100:
                # longer span starts the same — prefer the shorter if kinds match announcer
                if p.get("kind") == "announcer_introduction" and q.get("kind") == "announcer_introduction":
                    dominated = True
                    break
            if qt and qt in st and len(st) > len(qt) + 80 and p.get("kind") == q.get("kind") == "announcer_introduction":
                dominated = True
                break
        if not dominated:
            # Final safety: drop any solid span that embeds a teacher handoff
            # AFTER a long announcer block but still includes the teacher words
            if p.get("kind") == "announcer_introduction" and re.search(
                r"(?is)Never before released message.*What is God.?s solution", st
            ):
                m = re.search(
                    r"(?is)^(.*?Never before released message called[^\n]*\n+)What is God",
                    st,
                )
                if m:
                    p = dict(p)
                    p["span_text"] = m.group(1)
                    p["span_char_length"] = len(m.group(1))
                    p["note"] = (p.get("note") or "") + " Trimmed teacher opener from announcer span."
            tightened.append(p)
    proposals = _dedupe_proposals(tightened)

    # If we produced nothing at all, emit a single "needs review" ambiguous entry
    if not proposals:
        proposals.append({
            "document_id": doc["document_id"],
            "title": doc.get("title"),
            "teacher": teacher_key(doc),
            "author": doc.get("author"),
            "source_name": doc.get("source_name"),
            "kind": "needs_manual_review",
            "confidence": 0.40,
            "ambiguous": True,
            "problem": (
                "Sweep flagged markers %r but no high-confidence non-teacher span "
                "could be bounded. Manual review required."
                % (doc.get("markers"),)
            ),
            "span_text": None,
            "locator_snippet": chunks[0]["content"][:240].replace("\n", " "),
            "chunk_index_start": chunks[0]["chunk_index"],
            "chunk_index_end": chunks[0]["chunk_index"],
            "chunk_ids": [chunks[0]["chunk_id"]],
            "markers_from_sweep": doc.get("markers"),
        })

    return proposals


def _span_already_covered(proposals, span_text, start_i, end_i) -> bool:
    if not span_text or not span_text.strip():
        return False
    st = span_text.strip()
    for p in proposals:
        if p.get("ambiguous"):
            continue
        existing = (p.get("span_text") or "").strip()
        if not existing:
            continue
        if st in existing or existing in st:
            return True
        if (
            p.get("chunk_index_start") is not None
            and p.get("chunk_index_end") is not None
            and p["chunk_index_start"] <= start_i
            and p["chunk_index_end"] >= end_i
        ):
            return True
    return False


def _infer_kind(span_text: str, buckets: Set[str], first_idx: int, n_chunks: int) -> str:
    t = span_text.lower()
    if RE_ANNOUNCER.search(span_text):
        return "announcer_introduction"
    if RE_TRANSLATOR.search(span_text):
        return "translators_note"
    if RE_SCRIPTURE_INDEX.search(span_text) or (
        first_idx >= max(0, n_chunks - 5) and len(re.findall(r"\d+:\d+", span_text)) >= 5
    ):
        return "scripture_index"
    if RE_RELATED.search(span_text):
        return "related_books_promo"
    if RE_EDITOR.search(span_text):
        return "editor_appendix"
    if RE_CCEL.search(span_text) or re.search(r"(?i)author\(s\):", span_text):
        if first_idx <= 5:
            return "publisher_front_matter"
        return "publisher_boilerplate"
    if "scanner" in t or "scanned and corrected" in t:
        return "scanner_credit"
    if first_idx <= 3:
        return "publisher_front_matter"
    if first_idx >= n_chunks - 3:
        return "back_matter"
    return "non_teacher_other"


def _make_proposal(
    doc, c_start, c_end, span_text, kind, confidence, ambiguous, note, full_text, chunk_ids
) -> Dict[str, Any]:
    # Build locator: a few words before/after using first 200 chars of span as anchor
    anchor = span_text[:120]
    idx = full_text.find(anchor) if anchor else -1
    if idx >= 0:
        before = full_text[max(0, idx - 35):idx]
        # after end of full span if possible
        end_idx = full_text.find(span_text) 
        if end_idx >= 0:
            after = full_text[end_idx + len(span_text): end_idx + len(span_text) + 35]
        else:
            after = full_text[idx + len(anchor): idx + len(anchor) + 35]
        locator = "%s⟦…span of %d chars…⟧%s" % (
            before.replace("\n", " "),
            len(span_text),
            after.replace("\n", " "),
        )
    else:
        locator = "⟦start⟧%s…" % span_text[:80].replace("\n", " ")

    # For human review, include full span but cap extremely long ones with clear note
    MAX = 12000
    if len(span_text) > MAX:
        display = span_text[:6000] + "\n\n… [TRUNCATED FOR REVIEW FILE — full span is %d chars across chunks %d–%d; see chunk_ids] …\n\n" % (
            len(span_text), c_start, c_end,
        ) + span_text[-3000:]
        truncated = True
    else:
        display = span_text
        truncated = False

    return {
        "document_id": doc["document_id"],
        "title": doc.get("title"),
        "teacher": teacher_key(doc),
        "author": doc.get("author"),
        "source_name": doc.get("source_name"),
        "kind": kind,
        "confidence": round(float(confidence), 2),
        "ambiguous": bool(ambiguous),
        "problem": "Non-teacher material (%s) proposed for exclusion from teacher-attributed content." % kind,
        "span_text": display,
        "span_char_length": len(span_text),
        "span_truncated_in_file": truncated,
        "locator_context": locator,
        "chunk_index_start": c_start,
        "chunk_index_end": c_end,
        "chunk_ids": chunk_ids,
        "markers_from_sweep": doc.get("markers"),
        "note": note,
        "proposed_at": _utc_now(),
    }


def _dedupe_proposals(proposals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen_spans = []
    for p in proposals:
        st = (p.get("span_text") or "").strip()
        if p.get("ambiguous") and not st:
            # keep ambiguous flags; dedupe by chunk range
            key = (p.get("document_id"), p.get("chunk_index_start"), p.get("chunk_index_end"), p.get("kind"))
            if any(
                (q.get("document_id"), q.get("chunk_index_start"), q.get("chunk_index_end"), q.get("kind")) == key
                for q in out
            ):
                continue
            out.append(p)
            continue
        if not st:
            out.append(p)
            continue
        skip = False
        for prev in seen_spans:
            if st == prev or (len(st) > 80 and st in prev) or (len(prev) > 80 and prev in st):
                skip = True
                break
        if skip:
            continue
        seen_spans.append(st)
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Markdown rewrite
# ---------------------------------------------------------------------------
def rewrite_proposals_md(proposals: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    by_teacher: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in proposals:
        by_teacher[p.get("teacher") or "Unknown"].append(p)

    # Teacher order: priority first, then alpha
    teachers = sorted(
        by_teacher.keys(),
        key=lambda t: (
            0 if t == "Andrew Murray" else 1 if t == "Derek Prince" else 2,
            t.lower(),
        ),
    )

    lines = []
    A = lines.append
    A("# Non-Teacher Material — Span Proposals (for human review)")
    A("")
    A("Read-only proposal run. Connection: `rhemata_readonly_analysis` only.")
    A("**Nothing applied.** Bias: under-propose at ambiguous boundaries.")
    A("")
    A("- Last rewritten: **%s**" % _utc_now())
    A("- Documents processed: **%s**" % meta.get("documents_processed", "?"))
    A("- Proposal entries: **%d**" % len(proposals))
    A("- Ambiguous / no-cut flags: **%d**" % sum(1 for p in proposals if p.get("ambiguous")))
    A("- Status: **%s**" % meta.get("status", "in_progress"))
    A("")
    A("## Breakdown by teacher")
    A("")
    for t in teachers:
        items = by_teacher[t]
        amb = sum(1 for p in items if p.get("ambiguous"))
        solid = len(items) - amb
        A("- **%s**: %d entries (%d proposed spans, %d ambiguous/no-cut)" % (
            t, len(items), solid, amb,
        ))
    A("")

    for t in teachers:
        items = sorted(
            by_teacher[t],
            key=lambda p: (
                0 if not p.get("ambiguous") else 1,
                -float(p.get("confidence") or 0),
                p.get("title") or "",
                p.get("chunk_index_start") or 0,
            ),
        )
        A("---")
        A("")
        A("## %s" % t)
        A("")
        for i, p in enumerate(items, 1):
            tag = "AMBIGUOUS" if p.get("ambiguous") else "PROPOSE"
            A("### %d. [%s] conf=%.2f — %s" % (
                i, tag, float(p.get("confidence") or 0), (p.get("title") or "?")[:90],
            ))
            A("")
            A("- **document_id**: `%s`" % p.get("document_id"))
            A("- **kind**: %s" % p.get("kind"))
            A("- **chunks**: %s–%s" % (p.get("chunk_index_start"), p.get("chunk_index_end")))
            if p.get("chunk_ids"):
                A("- **chunk_ids**: %s" % ", ".join("`%s`" % c for c in (p.get("chunk_ids") or [])[:12]))
            A("- **sweep markers**: %s" % ", ".join(p.get("markers_from_sweep") or []))
            A("- **what**: %s" % (p.get("problem") or ""))
            if p.get("note"):
                A("- **note**: %s" % p["note"])
            if p.get("locator_context"):
                A("- **locator**: %s" % _md_safe(p["locator_context"])[:300])
            if p.get("locator_snippet") and not p.get("span_text"):
                A("- **locator snippet**: %s" % _md_safe(p["locator_snippet"])[:300])
            if p.get("span_text"):
                A("- **span length**: %s chars%s" % (
                    p.get("span_char_length") or len(p["span_text"]),
                    " (truncated in this file)" if p.get("span_truncated_in_file") else "",
                ))
                A("")
                A("**Proposed non-teacher span (verbatim):**")
                A("")
                A("```")
                A(p["span_text"])
                A("```")
            else:
                A("- **proposed span**: *(none — ambiguous; do not cut)*")
            A("")

    tmp = PROPOSALS_MD.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(PROPOSALS_MD)


def _md_safe(s: str) -> str:
    return (s or "").replace("\n", " ")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max docs (smoke)")
    parser.add_argument(
        "--only-priority",
        action="store_true",
        help="Only Andrew Murray + Derek Prince",
    )
    args = parser.parse_args(argv)

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log("Non-teacher span proposal run starting")
    log("Review dir: %s" % REVIEW_DIR)

    if args.fresh:
        for p in (PROPOSALS_JSONL, PROPOSALS_MD, PROGRESS_PATH):
            if p.exists():
                p.unlink()
        log("--fresh: cleared prior proposal artifacts")

    try:
        conn = connect_readonly()
    except Exception as e:
        log("FATAL: connection failed — stopping. %s" % e)
        return 2

    t0 = time.time()
    try:
        docs = load_flagged_docs()
        log("Loaded %d unique documents from type-5 findings (150 markers collapsed)" % len(docs))
        docs = sort_priority(docs)
        if args.only_priority:
            docs = [d for d in docs if teacher_key(d) in PRIORITY_TEACHERS]
            log("--only-priority: %d docs (Murray+Prince)" % len(docs))
        if args.limit:
            docs = docs[: args.limit]
            log("--limit %d" % args.limit)

        progress = load_progress() if args.resume else {}
        done_ids: Set[str] = set(progress.get("completed_document_ids") or [])
        proposals: List[Dict[str, Any]] = []
        if args.resume and PROPOSALS_JSONL.exists():
            with PROPOSALS_JSONL.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        proposals.append(json.loads(line))
            log("Resume: %d prior proposals, %d docs done" % (len(proposals), len(done_ids)))
        elif not args.resume:
            PROPOSALS_JSONL.write_text("", encoding="utf-8")

        # Ensure priority teachers complete first even if interrupted
        murray = [d for d in docs if teacher_key(d) == "Andrew Murray"]
        prince = [d for d in docs if teacher_key(d) == "Derek Prince"]
        rest = [d for d in docs if teacher_key(d) not in PRIORITY_TEACHERS]
        ordered = murray + prince + rest
        log("Order: Murray=%d, Prince=%d, rest=%d" % (len(murray), len(prince), len(rest)))

        for i, doc in enumerate(ordered, 1):
            did = doc["document_id"]
            if did in done_ids:
                log("[%d/%d] skip already done %s (%s)" % (
                    i, len(ordered), (doc.get("title") or "")[:50], teacher_key(doc),
                ))
                continue

            log("[%d/%d] %s — %s | markers=%s" % (
                i, len(ordered), teacher_key(doc), (doc.get("title") or "")[:60],
                ",".join(doc.get("markers") or []),
            ))
            try:
                chunks = load_all_chunks(conn, did)
            except Exception as e:
                log("  SKIP chunk load failed: %s: %s" % (type(e).__name__, e))
                err = {
                    "document_id": did,
                    "title": doc.get("title"),
                    "teacher": teacher_key(doc),
                    "kind": "load_error",
                    "confidence": 0.0,
                    "ambiguous": True,
                    "problem": "Failed to load chunks: %s" % e,
                    "span_text": None,
                    "markers_from_sweep": doc.get("markers"),
                }
                append_proposal(err)
                proposals.append(err)
                done_ids.add(did)
                progress["completed_document_ids"] = sorted(done_ids)
                save_progress(progress)
                continue

            log("  %d chunks loaded; expanding spans..." % len(chunks))
            doc_proposals = propose_spans_for_document(doc, chunks)
            for p in doc_proposals:
                append_proposal(p)
                proposals.append(p)
            solid = sum(1 for p in doc_proposals if not p.get("ambiguous") and p.get("span_text"))
            amb = sum(1 for p in doc_proposals if p.get("ambiguous"))
            log("  → %d proposal(s): %d span(s), %d ambiguous" % (
                len(doc_proposals), solid, amb,
            ))

            done_ids.add(did)
            progress["completed_document_ids"] = sorted(done_ids)
            progress["documents_processed"] = len(done_ids)
            progress["proposals_count"] = len(proposals)
            # Track priority completion
            murray_done = all(
                d["document_id"] in done_ids for d in murray
            )
            prince_done = all(
                d["document_id"] in done_ids for d in prince
            )
            progress["murray_complete"] = murray_done
            progress["prince_complete"] = prince_done
            save_progress(progress)
            rewrite_proposals_md(proposals, {
                "documents_processed": len(done_ids),
                "status": "in_progress",
            })

            if i % 5 == 0 or teacher_key(doc) in PRIORITY_TEACHERS:
                log("Progress: %d/%d docs | proposals=%d | elapsed=%.0fs | Murray done=%s Prince done=%s" % (
                    len(done_ids), len(ordered), len(proposals), time.time() - t0,
                    murray_done, prince_done,
                ))

        rewrite_proposals_md(proposals, {
            "documents_processed": len(done_ids),
            "status": "complete",
        })
        progress["status"] = "complete"
        progress["completed_at"] = _utc_now()
        save_progress(progress)

        # Summary
        by_t: Dict[str, Dict[str, int]] = defaultdict(lambda: {"docs": 0, "spans": 0, "amb": 0})
        docs_per_t: Dict[str, Set[str]] = defaultdict(set)
        for p in proposals:
            t = p.get("teacher") or "?"
            docs_per_t[t].add(p.get("document_id") or "")
            if p.get("ambiguous"):
                by_t[t]["amb"] += 1
            elif p.get("span_text"):
                by_t[t]["spans"] += 1
        for t in docs_per_t:
            by_t[t]["docs"] = len(docs_per_t[t])

        log("=" * 60)
        log("DONE")
        log("Documents processed: %d" % len(done_ids))
        log("Proposal entries: %d" % len(proposals))
        log("  solid spans: %d" % sum(1 for p in proposals if p.get("span_text") and not p.get("ambiguous")))
        log("  ambiguous/no-cut: %d" % sum(1 for p in proposals if p.get("ambiguous")))
        log("Breakdown by teacher:")
        for t in sorted(by_t.keys(), key=lambda x: (
            0 if x == "Andrew Murray" else 1 if x == "Derek Prince" else 2, x.lower()
        )):
            log("  %s: docs=%d spans=%d ambiguous=%d" % (
                t, by_t[t]["docs"], by_t[t]["spans"], by_t[t]["amb"],
            ))
        log("Murray complete: %s | Prince complete: %s" % (
            progress.get("murray_complete"), progress.get("prince_complete"),
        ))
        log("Proposals: %s" % PROPOSALS_MD)
        log("Connection: rhemata_readonly_analysis throughout; no DB writes; proposals only.")
        log("Elapsed: %.1fs" % (time.time() - t0))
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
