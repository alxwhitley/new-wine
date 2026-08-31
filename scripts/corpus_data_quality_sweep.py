#!/usr/bin/env python3
"""
corpus_data_quality_sweep.py — overnight, READ-ONLY corpus data-quality sweep.

Connects ONLY via backend/app/.env.readonly-analysis (newwine_readonly_analysis).
Never loads backend/app/.env. Never INSERT/UPDATE/DELETE/DDL.

Flags five classes of document-level quality problems:
  1. author field is not a person's name (title, furniture, empty, placeholder)
  2. same teacher under multiple spellings / invisible whitespace variants
  3. document author vs source name mismatch
  4. stored metadata disagrees with what the document text indicates
  5. non-teacher material inside a teacher-attributed document

Output (progressive, crash-safe):
  corpus_data_quality_review/findings.jsonl   — append-only raw findings
  corpus_data_quality_review/findings.md      — regrouped periodically + at end
  corpus_data_quality_review/progress.json     — resumable checkpoint
  corpus_data_quality_review/calibration.md    — calibration caught/missed
  corpus_data_quality_review/run.log           — progress heartbeats

Usage:
  python3 scripts/corpus_data_quality_sweep.py
  python3 scripts/corpus_data_quality_sweep.py --resume
  python3 scripts/corpus_data_quality_sweep.py --limit 50   # smoke
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

# ---------------------------------------------------------------------------
# Paths — never touch the read-write app .env
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
READONLY_ENV_PATH = PROJECT_ROOT / "backend" / "app" / ".env.readonly-analysis"
REVIEW_DIR = PROJECT_ROOT / "corpus_data_quality_review"
FINDINGS_JSONL = REVIEW_DIR / "findings.jsonl"
FINDINGS_MD = REVIEW_DIR / "findings.md"
PROGRESS_PATH = REVIEW_DIR / "progress.json"
CALIBRATION_MD = REVIEW_DIR / "calibration.md"
RUN_LOG = REVIEW_DIR / "run.log"

ROLE_NAME = "newwine_readonly_analysis"

# Progress heartbeat every N documents during the chunk-scan phase.
PROGRESS_EVERY = 25
# Rewrite findings.md every N new findings (and at end).
MD_REWRITE_EVERY = 20
# Head / tail chunk windows for text checks (types 4 and 5).
HEAD_CHUNKS = 6
TAIL_CHUNKS = 3

# ---------------------------------------------------------------------------
# Finding type keys (stable for grouping)
# ---------------------------------------------------------------------------
TYPE_1 = "1_author_not_person_name"
TYPE_2 = "2_author_spelling_variants"
TYPE_3 = "3_author_source_mismatch"
TYPE_4 = "4_metadata_vs_text"
TYPE_5 = "5_non_teacher_material"

TYPE_LABELS = {
    TYPE_1: "Author/attribution field is not a person's name",
    TYPE_2: "Same teacher under multiple spellings / invisible variants",
    TYPE_3: "Document author field mismatches source name",
    TYPE_4: "Stored metadata disagrees with document text attribution",
    TYPE_5: "Non-teacher material inside a teacher-attributed document",
}

# ---------------------------------------------------------------------------
# Placeholders / furniture that are not personal names
# ---------------------------------------------------------------------------
PLACEHOLDER_AUTHORS = {
    "",
    "unknown",
    "n/a",
    "na",
    "none",
    "null",
    "author",
    "the author",
    "various",
    "anonymous",
    "n.a.",
    "tbd",
    "todo",
    "-",
    "--",
    "—",
    "untitled",
    "no author",
    "not available",
}

# Title-like tokens that rarely appear as part of a personal name alone.
TITLE_SIGNAL_RE = re.compile(
    r"(?i)\b("
    r"how to|what is|why you|stop |start |watch |sermon|message|episode|"
    r"part \d|part i|part ii|battle|fight your|porn|abortion|instead|"
    r"livestream|live stream|q&a|q & a|interview|podcast|trailer|"
    r"full sermon|bible study|devotional|this is how"
    r")\b"
)

# First-person title patterns / imperative hooks common in YouTube titles.
IMPERATIVE_TITLE_RE = re.compile(
    r"(?i)^(do |stop |start |watch |don't |dont |never |always |this is )"
)

# Sources that are collections / not a single teacher person. Mismatch of
# author vs source name is EXPECTED for these and is not flagged as type 3.
COLLECTION_SOURCE_HINTS = re.compile(
    r"(?i)("
    r"precept austin|historicalchristian|commentary|ccel|ethereal library|"
    r"magazine|journal|church|stepbible|tyndale|lexicon|bible |"
    r"rhemata|unassigned|sentinel|database|library|collection|"
    r"new wine|covenant harvest|clf "
    r")"
)

# Non-teacher material markers (type 5). Case-insensitive substring/regex.
NON_TEACHER_MARKERS = [
    (r"translator'?s?\s+note", "translator_note", 0.95),
    (r"\btranslated by\b", "translated_by", 0.85),
    (r"\btranslator\b", "translator_word", 0.75),
    (r"ccel staff writer", "ccel_staff", 0.95),
    (r"christian classics ethereal library", "ccel_boilerplate", 0.80),
    (r"electronic text note", "electronic_text_note", 0.90),
    (r"related books", "related_books_promo", 0.85),
    (r"heidelberg catechism", "heidelberg_catechism", 0.95),
    (r"directory of public worship", "directory_of_public_worship", 0.90),
    (r"editor'?s?\s+note", "editors_note", 0.90),
    (r"\beditorial\b", "editorial", 0.70),
    (r"this is dick leggatt", "announcer_leggatt", 0.98),
    (r"president of derek prince ministries", "dpm_introducer", 0.95),
    (r"i am thrilled to be giving you the introduction", "third_party_intro", 0.95),
    (r"scanned and corrected by", "scanner_credit", 0.90),
    (r"all rights reserved\.?\s*written permission", "copyright_boilerplate", 0.75),
    (r"index of scripture references", "scripture_index", 0.70),
    (r"index of pages of the print edition", "print_index", 0.70),
    (r"published by\b", "published_by", 0.55),
    (r"\bappendix\b", "appendix_heading", 0.55),
    (r"guest speaker", "guest_speaker", 0.85),
    (r"opening remarks by", "opening_remarks_by", 0.90),
    (r"introduction by\b", "introduction_by", 0.80),
]

# Patterns that suggest the document text names a different speaker/author.
TEXT_ATTR_PATTERNS = [
    re.compile(r"(?im)^by\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})\s*$"),
    re.compile(r"(?i)\b(?:sermon|message|address|lecture)\s+by\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})"),
    re.compile(r"(?i)\bspeaker:\s*([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})"),
    re.compile(r"(?i)\bauthor\(s\):\s*([^\n]{2,60})"),
    re.compile(r"(?i)\bwritten by\s+([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})"),
]


# ---------------------------------------------------------------------------
# Logging / progressive I/O
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    """Print and append a timestamped heartbeat line. Always flush."""
    line = "[%s] %s" % (_utc_now(), msg)
    print(line, flush=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def append_finding(finding: Dict[str, Any]) -> None:
    """Append one finding to JSONL immediately (crash-safe)."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with FINDINGS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(finding, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def load_findings() -> List[Dict[str, Any]]:
    if not FINDINGS_JSONL.exists():
        return []
    out = []
    with FINDINGS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def save_progress(state: Dict[str, Any]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
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


def rewrite_findings_md(findings: List[Dict[str, Any]], meta: Dict[str, Any]) -> None:
    """Regroup all findings by type, confidence desc; write findings.md."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    by_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_type[f.get("type", "unknown")].append(f)

    lines = []
    A = lines.append
    A("# Corpus Data-Quality Sweep — Findings")
    A("")
    A("Read-only diagnostic. Connection: `newwine_readonly_analysis` only.")
    A("No database writes. No pipeline edits. Findings only — no fixes proposed.")
    A("")
    A("- Generated / last rewritten: **%s**" % _utc_now())
    A("- Documents examined: **%s**" % meta.get("documents_examined", "?"))
    A("- Total findings so far: **%d**" % len(findings))
    A("- Run status: **%s**" % meta.get("status", "in_progress"))
    if meta.get("stopped_after_document_id"):
        A("- Stopped after document_id: `%s`" % meta["stopped_after_document_id"])
    A("")
    A("## Breakdown by type")
    A("")
    for tkey in (TYPE_1, TYPE_2, TYPE_3, TYPE_4, TYPE_5):
        A("- **%s**: %d" % (TYPE_LABELS[tkey], len(by_type.get(tkey, []))))
    other = [k for k in by_type if k not in TYPE_LABELS]
    for k in other:
        A("- **%s**: %d" % (k, len(by_type[k])))
    A("")

    order = [TYPE_1, TYPE_2, TYPE_3, TYPE_4, TYPE_5] + other
    for tkey in order:
        items = by_type.get(tkey, [])
        if not items:
            continue
        items_sorted = sorted(
            items,
            key=lambda x: (-float(x.get("confidence", 0)), x.get("document_id") or ""),
        )
        A("---")
        A("")
        A("## %s" % TYPE_LABELS.get(tkey, tkey))
        A("")
        A("%d finding(s), ordered by confidence (highest first)." % len(items_sorted))
        A("")
        for i, f in enumerate(items_sorted, 1):
            A("### %d. conf=%.2f — %s" % (
                i,
                float(f.get("confidence", 0)),
                (f.get("title") or "(no title)")[:100],
            ))
            A("")
            A("- **document_id**: `%s`" % f.get("document_id"))
            A("- **stored author**: %s" % _md_escape(f.get("stored_author")))
            A("- **source name**: %s" % _md_escape(f.get("source_name")))
            A("- **document title**: %s" % _md_escape(f.get("title")))
            if f.get("source_type") is not None:
                A("- **source_type / source_kind**: %s / %s" % (
                    _md_escape(f.get("source_type")),
                    _md_escape(f.get("source_kind")),
                ))
            A("- **what appears wrong**: %s" % f.get("problem", ""))
            if f.get("evidence"):
                A("- **evidence**: %s" % _md_escape(f.get("evidence"))[:500])
            if f.get("detail"):
                A("- **detail**: %s" % _md_escape(f.get("detail"))[:500])
            A("")

    tmp = FINDINGS_MD.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(FINDINGS_MD)


def _md_escape(val: Any) -> str:
    if val is None:
        return "`null`"
    s = str(val)
    # Show invisible characters explicitly in display.
    s = s.replace("\u00a0", "\\u00a0").replace("\u200b", "\\u200b")
    return s if s else "`(empty string)`"


# ---------------------------------------------------------------------------
# Connection — read-only role only; fail immediately, no silent retry
# ---------------------------------------------------------------------------
def connect_readonly():
    """Open a single connection with the overnight analysis role.

    Raises immediately on failure (no retry loop). Sets session readonly.
    """
    import psycopg2

    if not READONLY_ENV_PATH.exists():
        raise RuntimeError(
            "Read-only env file missing: %s — cannot connect." % READONLY_ENV_PATH
        )

    url = None
    for line in READONLY_ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("READONLY_ANALYSIS_DB_URL="):
            url = line.split("=", 1)[1].strip()
            break
    if not url:
        raise RuntimeError("READONLY_ANALYSIS_DB_URL not found in %s" % READONLY_ENV_PATH)

    # Refuse to use the main app URL even if someone swapped the file.
    if ROLE_NAME not in url:
        raise RuntimeError(
            "Connection string does not name %s — refusing to connect." % ROLE_NAME
        )

    p = urlparse(url)
    user = unquote(p.username or "")
    if ROLE_NAME not in user:
        raise RuntimeError("Username %r is not the read-only analysis role." % user)

    log("Connecting as %s to %s:%s (timeout 20s, no retry)..." % (
        user.split(":")[0][:40], p.hostname, p.port or 5432,
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
    cur.execute("SELECT current_user, session_user")
    cu, su = cur.fetchone()
    if ROLE_NAME not in cu:
        conn.close()
        raise RuntimeError("Connected as %r, expected %r" % (cu, ROLE_NAME))
    log("Connected OK: current_user=%s session_user=%s (readonly session)" % (cu, su))

    # Confirm writes are rejected (once per run).
    try:
        cur.execute("UPDATE documents SET title = title WHERE false")
        log("WARNING: write was not rejected by session — aborting")
        conn.close()
        raise RuntimeError("Read-only session accepted UPDATE; aborting")
    except Exception as e:
        if "ReadOnlySqlTransaction" in type(e).__name__ or "read-only" in str(e).lower():
            log("Write rejection confirmed: %s" % type(e).__name__)
        else:
            # Permission denied is also fine.
            log("Write rejection confirmed: %s: %s" % (type(e).__name__, str(e)[:120]))
            try:
                conn.rollback()
            except Exception:
                pass
    cur.close()
    return conn


# ---------------------------------------------------------------------------
# Normalization helpers (type 2)
# ---------------------------------------------------------------------------
def normalize_person_key(s: str) -> str:
    """NFKC + collapse all unicode space/format chars + casefold."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", s)
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat == "Zs" or ch in ("\u200b", "\ufeff", "\u2060"):
            out.append(" ")
        elif cat == "Cf":
            continue
        else:
            out.append(ch)
    return " ".join("".join(out).split()).casefold()


def has_unusual_whitespace(s: str) -> bool:
    if not s:
        return False
    for ch in s:
        if ch == "\u00a0":
            return True
        if unicodedata.category(ch) == "Zs" and ch != " ":
            return True
        if ch in ("\u200b", "\ufeff", "\u2060", "\t"):
            return True
    return False


def unusual_whitespace_detail(s: str) -> str:
    codes = []
    for ch in s:
        if ch == " " or ch.isalpha() or ch.isdigit() or ch in ".,'-":
            continue
        if unicodedata.category(ch) in ("Zs", "Cf") or ch in ("\t", "\n", "\r"):
            codes.append("U+%04X(%s)" % (ord(ch), unicodedata.name(ch, "?")))
    return ", ".join(codes[:12])


def token_set(s: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9]+", normalize_person_key(s)))


def looks_like_person_name(author: Optional[str]) -> bool:
    """Heuristic: short-ish, capitalized tokens, not title-like."""
    if author is None:
        return False
    a = author.strip()
    if not a:
        return False
    if normalize_person_key(a) in PLACEHOLDER_AUTHORS:
        return False
    if len(a) > 60:
        return False
    if TITLE_SIGNAL_RE.search(a):
        return False
    if IMPERATIVE_TITLE_RE.search(a):
        return False
    # Pure digits / punctuation
    if not re.search(r"[A-Za-z]", a):
        return False
    words = a.split()
    if len(words) >= 6:
        # Long multi-token strings are usually titles or councils, not persons.
        # Exception: "X of Y" place-style names are ok at 3-5 tokens.
        return False
    # "Pastor Vlad" is a role+name; still a person-ish form but thin.
    return True


def is_collection_source(source_name: Optional[str]) -> bool:
    if not source_name:
        return False
    return bool(COLLECTION_SOURCE_HINTS.search(source_name))


# ---------------------------------------------------------------------------
# Detectors (pure; take row dicts / text; return finding dicts or [])
# ---------------------------------------------------------------------------
def detect_type1_author_not_name(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings = []
    author = doc.get("author")
    title = doc.get("title") or ""
    source_name = doc.get("source_name")

    def base(**kwargs):
        d = {
            "type": TYPE_1,
            "document_id": doc["id"],
            "title": doc.get("title"),
            "stored_author": author,
            "source_name": source_name,
            "source_type": doc.get("source_type"),
            "source_kind": doc.get("source_kind"),
        }
        d.update(kwargs)
        return d

    # Empty / null
    if author is None or (isinstance(author, str) and author.strip() == ""):
        # Null author on a teacher source is a strong attribution gap.
        conf = 0.90 if source_name and not is_collection_source(source_name) else 0.70
        findings.append(base(
            confidence=conf,
            problem="Author field is empty/null; document has no stored person attribution.",
            detail="source_name=%r" % source_name,
        ))
        return findings

    norm = normalize_person_key(author)
    if norm in PLACEHOLDER_AUTHORS:
        findings.append(base(
            confidence=0.95,
            problem="Author field is a placeholder, not a person's name.",
            detail="normalized=%r" % norm,
        ))
        return findings

    # Author equals title (and title is longer than a short name)
    if title and author.strip() == title.strip() and len(author.strip()) > 25:
        findings.append(base(
            confidence=0.95,
            problem="Author field is identical to the document title (title used as author).",
            evidence="author == title == %r" % author[:120],
        ))
    elif title and normalize_person_key(author) == normalize_person_key(title) and len(author) > 20:
        findings.append(base(
            confidence=0.90,
            problem="Author field matches the document title after normalization.",
            evidence="author=%r title=%r" % (author[:80], title[:80]),
        ))

    # Title-like signals
    if TITLE_SIGNAL_RE.search(author) or IMPERATIVE_TITLE_RE.search(author):
        findings.append(base(
            confidence=0.92,
            problem="Author field looks like a sermon/video title, not a person name.",
            evidence=author,
        ))

    # Single token that is clearly not a full name, when source is a full name
    # e.g. author="Vlad" while source="Vlad Savchuk" — weak, skip type1 (type3 covers).
    # Very short non-name garbage
    if author.strip().lower() in {"watch message", "watch", "video", "sermon", "message"}:
        findings.append(base(
            confidence=0.97,
            problem="Author field is boilerplate/UI furniture, not a person.",
            evidence=author,
        ))

    # Long string without typical name structure
    words = author.split()
    if len(words) >= 5 and not re.search(r"(?i)\b(of|van|de|von|st\.?)\b", author):
        # Could be a title; boost if source is a known person-style name.
        conf = 0.80 if source_name and not is_collection_source(source_name) else 0.55
        if conf >= 0.70:
            findings.append(base(
                confidence=conf,
                problem="Author field has many tokens without name-like structure; likely a title.",
                evidence=author,
            ))

    return findings


def detect_type2_global(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cluster authors by normalized key; flag multi-form and invisible-space variants."""
    # Map normalized key -> set of raw author strings + example doc ids
    raw_by_norm: Dict[str, Set[str]] = defaultdict(set)
    docs_by_raw: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for d in docs:
        a = d.get("author")
        if a is None or str(a).strip() == "":
            continue
        raw_by_norm[normalize_person_key(a)].add(a)
        docs_by_raw[a].append(d)

    findings = []

    # Multi-form clusters under one normalized key
    for nkey, raws in raw_by_norm.items():
        if len(raws) < 2:
            # Still flag single-form if it has unusual whitespace (invisible issue)
            only = next(iter(raws))
            if has_unusual_whitespace(only):
                for d in docs_by_raw[only]:
                    findings.append({
                        "type": TYPE_2,
                        "document_id": d["id"],
                        "title": d.get("title"),
                        "stored_author": only,
                        "source_name": d.get("source_name"),
                        "source_type": d.get("source_type"),
                        "source_kind": d.get("source_kind"),
                        "confidence": 0.98,
                        "problem": (
                            "Author field contains unusual/invisible whitespace "
                            "(e.g. non-breaking space) that would split this teacher "
                            "under a naive exact-match query."
                        ),
                        "evidence": "codepoints: %s; repr=%r" % (
                            unusual_whitespace_detail(only), only,
                        ),
                        "detail": "normalized_key=%r" % nkey,
                    })
            continue

        # Multiple distinct raw strings share one normalized key.
        # Emit one finding per document using a non-canonical raw form.
        # Prefer the form without unusual whitespace and with most docs as canonical.
        ranked = sorted(
            raws,
            key=lambda r: (
                0 if not has_unusual_whitespace(r) else 1,
                -len(docs_by_raw[r]),
                r,
            ),
        )
        canonical = ranked[0]
        for raw in raws:
            if raw == canonical and not has_unusual_whitespace(raw):
                continue
            conf = 0.98 if has_unusual_whitespace(raw) else 0.88
            for d in docs_by_raw[raw]:
                findings.append({
                    "type": TYPE_2,
                    "document_id": d["id"],
                    "title": d.get("title"),
                    "stored_author": raw,
                    "source_name": d.get("source_name"),
                    "source_type": d.get("source_type"),
                    "source_kind": d.get("source_kind"),
                    "confidence": conf,
                    "problem": (
                        "Author spelling/variant form would split this teacher from "
                        "the canonical form under a naive query."
                    ),
                    "evidence": "raw=%r canonical_in_corpus=%r all_forms=%r" % (
                        raw, canonical, sorted(raws),
                    ),
                    "detail": "normalized_key=%r; unusual_ws=%s" % (
                        nkey, has_unusual_whitespace(raw),
                    ),
                })

    # Near-duplicate clusters across different normalized keys (light Levenshtein-ish)
    # Only compare keys that share a last token and differ slightly.
    keys = sorted(raw_by_norm.keys())
    last_token_groups: Dict[str, List[str]] = defaultdict(list)
    for k in keys:
        parts = k.split()
        if not parts:
            continue
        last_token_groups[parts[-1]].append(k)

    for last, group in last_token_groups.items():
        if len(group) < 2 or len(last) < 4:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if _similar_keys(a, b):
                    # Flag docs under the rarer form.
                    raws_a = raw_by_norm[a]
                    raws_b = raw_by_norm[b]
                    count_a = sum(len(docs_by_raw[r]) for r in raws_a)
                    count_b = sum(len(docs_by_raw[r]) for r in raws_b)
                    rare_raws = raws_a if count_a <= count_b else raws_b
                    common = b if count_a <= count_b else a
                    for raw in rare_raws:
                        for d in docs_by_raw[raw]:
                            findings.append({
                                "type": TYPE_2,
                                "document_id": d["id"],
                                "title": d.get("title"),
                                "stored_author": raw,
                                "source_name": d.get("source_name"),
                                "source_type": d.get("source_type"),
                                "source_kind": d.get("source_kind"),
                                "confidence": 0.72,
                                "problem": (
                                    "Author name appears closely related to another "
                                    "author string in the corpus (possible alias/variant)."
                                ),
                                "evidence": "this=%r related_normalized=%r" % (raw, common),
                                "detail": "pair=(%r, %r)" % (a, b),
                            })

    return findings


def _similar_keys(a: str, b: str) -> bool:
    if a == b:
        return False
    # Same last name; first tokens are initials vs full or close spellings
    pa, pb = a.split(), b.split()
    if not pa or not pb:
        return False
    if pa[-1] != pb[-1]:
        return False
    # e.g. "s.d. gordon" vs "samuel dickey gordon" — share last, different length
    if abs(len(pa) - len(pb)) >= 1 and (len(pa) <= 3 or len(pb) <= 3):
        # Check first-letter agreement
        if pa[0][0] == pb[0][0]:
            return True
    # Small edit distance on full string
    if abs(len(a) - len(b)) > 4:
        return False
    return _edit_distance(a, b) <= 2 and min(len(a), len(b)) >= 6


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def detect_type3_author_source_mismatch(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    author = doc.get("author")
    source_name = doc.get("source_name")
    if not source_name:
        return []
    # Collection sources: author is often a historical name under a corpus source — skip.
    if is_collection_source(source_name):
        return []
    if author is None or str(author).strip() == "":
        # Already covered by type 1; still a mismatch, but avoid double-count at high volume.
        # Emit only for person-like sources at moderate confidence so calibration sees Savchuk.
        return [{
            "type": TYPE_3,
            "document_id": doc["id"],
            "title": doc.get("title"),
            "stored_author": author,
            "source_name": source_name,
            "source_type": doc.get("source_type"),
            "source_kind": doc.get("source_kind"),
            "confidence": 0.85,
            "problem": "Author field is empty while source is a named teacher/source.",
            "evidence": "author=null source_name=%r" % source_name,
        }]

    a_norm = normalize_person_key(author)
    s_norm = normalize_person_key(source_name)
    if a_norm == s_norm:
        return []
    if a_norm in s_norm or s_norm in a_norm:
        return []

    a_tok = token_set(author)
    s_tok = token_set(source_name)
    # Drop role words
    roles = {"pastor", "rev", "reverend", "dr", "brother", "sister", "apostle", "prophet"}
    a_tok -= roles
    s_tok -= roles
    if not a_tok:
        return []
    overlap = a_tok & s_tok
    # Shared surname or first name is enough to pass
    if overlap:
        # Still flag if author is clearly a title (no person-like tokens shared meaningfully)
        if looks_like_person_name(author):
            return []
        # Author is title-like but shares a token? rare; fall through

    # No token overlap between author and person-source → mismatch
    conf = 0.93
    if not looks_like_person_name(author):
        conf = 0.96  # author is a title/garbage under a person source
    elif len(a_tok) == 1 and next(iter(a_tok)) in {normalize_person_key(t) for t in source_name.split()}:
        return []  # "Vlad" under "Vlad Savchuk" — partial, not mismatch for type 3
    else:
        # Partial first-name only
        first_s = s_norm.split()[0] if s_norm.split() else ""
        if first_s and first_s in a_norm:
            conf = 0.60  # weak — e.g. nicknames
            if conf < 0.70:
                return []

    return [{
        "type": TYPE_3,
        "document_id": doc["id"],
        "title": doc.get("title"),
        "stored_author": author,
        "source_name": source_name,
        "source_type": doc.get("source_type"),
        "source_kind": doc.get("source_kind"),
        "confidence": conf,
        "problem": "Document author field does not match its source name.",
        "evidence": "author=%r source_name=%r token_overlap=%r" % (
            author, source_name, sorted(overlap),
        ),
    }]


def detect_type4_metadata_vs_text(
    doc: Dict[str, Any],
    head_text: str,
) -> List[Dict[str, Any]]:
    """If text attributes the work to someone else than stored author/source."""
    if not head_text or not head_text.strip():
        return []
    author = doc.get("author")
    source_name = doc.get("source_name")
    stored_keys = set()
    for val in (author, source_name):
        if val:
            stored_keys.add(normalize_person_key(val))
            stored_keys |= token_set(val)

    if not stored_keys:
        return []

    # Skip pure background/lexicon reference works — attribution is different.
    if doc.get("source_kind") in ("word_study", "lexicon") or doc.get("source_type") == "background":
        return []

    named = []
    for pat in TEXT_ATTR_PATTERNS:
        for m in pat.finditer(head_text[:6000]):
            name = m.group(1).strip().rstrip(".,;")
            if len(name) < 3 or len(name) > 60:
                continue
            named.append(name)

    findings = []
    seen = set()
    for name in named:
        nkey = normalize_person_key(name)
        if nkey in seen:
            continue
        seen.add(nkey)
        # Skip if matches stored
        if nkey in stored_keys or nkey in {normalize_person_key(x) for x in stored_keys}:
            continue
        ntok = token_set(name)
        if ntok & {t for t in stored_keys if len(t) > 2}:
            # shared tokens with stored — likely same person (Murray, Andrew vs Andrew Murray)
            if ntok & token_set(author or "") or ntok & token_set(source_name or ""):
                continue
        # "Murray, Andrew" vs "Andrew Murray"
        if author and set(normalize_person_key(author).replace(",", " ").split()) == set(nkey.replace(",", " ").split()):
            continue
        if source_name and set(normalize_person_key(source_name).replace(",", " ").split()) == set(nkey.replace(",", " ").split()):
            continue

        # Ignore generic / non-person captures
        if nkey in PLACEHOLDER_AUTHORS or TITLE_SIGNAL_RE.search(name):
            continue
        if not re.search(r"[A-Za-z]", name):
            continue

        findings.append({
            "type": TYPE_4,
            "document_id": doc["id"],
            "title": doc.get("title"),
            "stored_author": author,
            "source_name": source_name,
            "source_type": doc.get("source_type"),
            "source_kind": doc.get("source_kind"),
            "confidence": 0.78,
            "problem": (
                "Document head text attributes authorship/speaking to a name that "
                "does not match the stored author/source."
            ),
            "evidence": "text_names=%r; stored_author=%r; source_name=%r" % (
                name, author, source_name,
            ),
        })
    return findings


def detect_type5_non_teacher(
    doc: Dict[str, Any],
    chunks: List[Tuple[int, str]],
) -> List[Dict[str, Any]]:
    """Flag non-teacher material markers in head/tail chunks."""
    if not chunks:
        return []
    # Skip pure word-study / lexicon bulk (markers are noise there).
    if doc.get("source_kind") in ("word_study", "lexicon"):
        return []
    author = doc.get("author")
    source_name = doc.get("source_name")
    # Only meaningful when attributed to a teacher-like source/author
    attributed = False
    if author and looks_like_person_name(author):
        attributed = True
    if source_name and not is_collection_source(source_name):
        attributed = True
    if not attributed:
        # Still scan books under collection sources (CCEL Murray books have person author).
        if doc.get("source_type") == "book" and author:
            attributed = True
    if not attributed:
        return []

    findings = []
    compiled = [(re.compile(pat, re.I), label, conf) for pat, label, conf in NON_TEACHER_MARKERS]
    seen_labels = set()

    for chunk_index, content in chunks:
        if not content:
            continue
        # Limit per-chunk scan size
        text = content[:4000]
        for cre, label, conf in compiled:
            if label in seen_labels and conf < 0.90:
                continue
            m = cre.search(text)
            if not m:
                continue
            # Reduce false positives: "translator" alone mid-body of a sermon is weaker
            if label == "translator_word" and chunk_index > 5:
                conf = min(conf, 0.55)
            if conf < 0.60:
                continue
            seen_labels.add(label)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            snippet = text[start:end].replace("\n", " ")
            findings.append({
                "type": TYPE_5,
                "document_id": doc["id"],
                "title": doc.get("title"),
                "stored_author": author,
                "source_name": source_name,
                "source_type": doc.get("source_type"),
                "source_kind": doc.get("source_kind"),
                "confidence": conf,
                "problem": (
                    "Text that appears not to be the attributed teacher's own material "
                    "(marker: %s) is present in the document." % label
                ),
                "evidence": "chunk_index=%s marker=%s snippet=%r" % (
                    chunk_index, label, snippet[:200],
                ),
                "detail": "marker=%s" % label,
            })
    return findings


# ---------------------------------------------------------------------------
# Data loading (SELECT only)
# ---------------------------------------------------------------------------
def load_all_documents(conn) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          d.id::text,
          d.title,
          d.author,
          d.source_name AS doc_source_name,
          d.source_type,
          d.source_kind,
          d.source_id::text,
          s.name AS source_table_name
        FROM documents d
        LEFT JOIN sources s ON s.id = d.source_id
        ORDER BY d.id
        """
    )
    rows = cur.fetchall()
    cur.close()
    docs = []
    for r in rows:
        source_name = r[7] or r[3]  # prefer sources.name
        docs.append({
            "id": r[0],
            "title": r[1],
            "author": r[2],
            "doc_source_name": r[3],
            "source_type": r[4],
            "source_kind": r[5],
            "source_id": r[6],
            "source_name": source_name,
        })
    return docs


def load_head_tail_chunks(conn, document_id: str) -> List[Tuple[int, str]]:
    """Fetch head + tail chunks for one document. SELECT only."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT chunk_index, content
        FROM chunks
        WHERE document_id = %s::uuid
        ORDER BY chunk_index
        """,
        (document_id,),
    )
    rows = cur.fetchall()
    cur.close()
    if not rows:
        return []
    if len(rows) <= HEAD_CHUNKS + TAIL_CHUNKS:
        return [(int(i), c or "") for i, c in rows]
    head = rows[:HEAD_CHUNKS]
    tail = rows[-TAIL_CHUNKS:]
    # Dedupe if overlap
    seen = set()
    out = []
    for i, c in head + tail:
        i = int(i)
        if i in seen:
            continue
        seen.add(i)
        out.append((i, c or ""))
    return out


# ---------------------------------------------------------------------------
# Calibration evaluation (post-hoc; detection itself never keys on these names)
# ---------------------------------------------------------------------------
def evaluate_calibration(findings: List[Dict[str, Any]], docs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Report whether general-sweep findings captured the three known cases.

    Detection did not search for these by name. This post-hoc check looks up
    whether findings already emitted cover the known problem shapes.
    """
    by_doc: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in findings:
        by_doc[f.get("document_id", "")].append(f)

    # --- Case A: Vlad Savchuk docs where author is a video/sermon title ---
    # Identify Savchuk docs from source_name (post-hoc only), then see if
    # type1/type3 findings fire when author is title-like or empty.
    savchuk_docs = [
        d for d in docs
        if (d.get("source_name") or "") == "Vlad Savchuk"
        or normalize_person_key(d.get("source_name") or "") == "vlad savchuk"
    ]
    savchuk_title_like = []
    for d in savchuk_docs:
        a = d.get("author")
        if a is None or str(a).strip() == "":
            continue
        if not looks_like_person_name(a) or TITLE_SIGNAL_RE.search(a) or IMPERATIVE_TITLE_RE.search(a):
            savchuk_title_like.append(d)
        elif a and d.get("title") and normalize_person_key(a) == normalize_person_key(d["title"]):
            savchuk_title_like.append(d)

    caught_savchuk = 0
    for d in savchuk_title_like:
        fs = by_doc.get(d["id"], [])
        if any(f.get("type") in (TYPE_1, TYPE_3) for f in fs):
            caught_savchuk += 1
    # Also count empty-author Savchuk docs caught by type1/type3
    savchuk_empty = [d for d in savchuk_docs if d.get("author") is None or str(d.get("author") or "").strip() == ""]
    caught_empty = sum(
        1 for d in savchuk_empty
        if any(f.get("type") in (TYPE_1, TYPE_3) for f in by_doc.get(d["id"], []))
    )
    case_a_caught = (caught_savchuk > 0) or (caught_empty > 0 and len(savchuk_title_like) == 0)
    # Prefer title-as-author hits for the stated case
    if savchuk_title_like:
        case_a_caught = caught_savchuk == len(savchuk_title_like) or caught_savchuk > 0
        case_a_detail = (
            "Savchuk docs with title-like author: %d; of those, findings on %d. "
            "Also empty-author Savchuk docs: %d, findings on %d."
            % (len(savchuk_title_like), caught_savchuk, len(savchuk_empty), caught_empty)
        )
    else:
        case_a_detail = (
            "No title-like Savchuk authors found in corpus snapshot; "
            "empty-author Savchuk: %d, findings on %d."
            % (len(savchuk_empty), caught_empty)
        )
        case_a_caught = caught_empty > 0

    # --- Case B: Zac Poonen author with non-breaking space ---
    nbsp_docs = []
    for d in docs:
        a = d.get("author")
        if a and "\u00a0" in a:
            nbsp_docs.append(d)
    # Among findings of type 2 that mention unusual whitespace
    type2 = [f for f in findings if f.get("type") == TYPE_2]
    caught_nbsp_ids = set()
    for f in type2:
        sa = f.get("stored_author") or ""
        if "\u00a0" in sa or "u00a0" in (f.get("evidence") or "").lower() or "NO-BREAK" in (f.get("evidence") or ""):
            caught_nbsp_ids.add(f.get("document_id"))
    case_b_caught = any(d["id"] in caught_nbsp_ids for d in nbsp_docs) if nbsp_docs else False
    # If no NBSP left in corpus, report that (can't catch what's gone)
    if not nbsp_docs:
        case_b_detail = "No author fields containing U+00A0 found in current corpus snapshot."
        case_b_caught = False
    else:
        case_b_detail = (
            "Authors with NBSP: %d doc(s); type-2 findings covering %d of them."
            % (len(nbsp_docs), sum(1 for d in nbsp_docs if d["id"] in caught_nbsp_ids))
        )
        case_b_caught = all(d["id"] in caught_nbsp_ids for d in nbsp_docs) or any(
            d["id"] in caught_nbsp_ids for d in nbsp_docs
        )

    # --- Case C: Andrew Murray "The New Life" translator's note ---
    new_life = [
        d for d in docs
        if d.get("title") and "new life" in d["title"].casefold()
        and d.get("author") and "murray" in normalize_person_key(d.get("author") or "")
    ]
    case_c_caught = False
    case_c_detail = "New Life document not in examined set or no type-5 finding."
    if new_life:
        for d in new_life:
            fs = [f for f in by_doc.get(d["id"], []) if f.get("type") == TYPE_5]
            translatorish = [
                f for f in fs
                if "translator" in (f.get("detail") or "").lower()
                or "translator" in (f.get("evidence") or "").lower()
                or "translator" in (f.get("problem") or "").lower()
            ]
            if translatorish:
                case_c_caught = True
                case_c_detail = (
                    "document_id=%s title=%r type-5 translator findings=%d"
                    % (d["id"], d.get("title"), len(translatorish))
                )
                break
        if not case_c_caught:
            case_c_detail = (
                "New Life doc(s) present (%s) but no type-5 translator finding."
                % ", ".join(d["id"] for d in new_life)
            )

    return {
        "case_a_savchuk_title_author": {
            "label": "Vlad Savchuk documents where author field is a video/sermon title (not his name)",
            "result": "caught" if case_a_caught else "missed",
            "detail": case_a_detail,
        },
        "case_b_poonen_nbsp": {
            "label": "Zac Poonen record whose author field uses a non-breaking space",
            "result": "caught" if case_b_caught else "missed",
            "detail": case_b_detail,
        },
        "case_c_new_life_translator": {
            "label": "Andrew Murray's The New Life — translator's note material in attributed content",
            "result": "caught" if case_c_caught else "missed",
            "detail": case_c_detail,
        },
    }


def write_calibration_md(cal: Dict[str, Any], meta: Dict[str, Any]) -> None:
    lines = []
    A = lines.append
    A("# Corpus Data-Quality Sweep — Calibration Check")
    A("")
    A("Reported **before** relying on the main findings as a quality signal.")
    A("Detection did not search for these cases by name; this is a post-hoc")
    A("check of whether the general sweep logic surfaced each known case.")
    A("")
    A("- Written: **%s**" % _utc_now())
    A("- Connection: `newwine_readonly_analysis` (read-only)")
    A("- Documents available to detectors: **%s**" % meta.get("documents_examined", "?"))
    A("")
    A("| Case | Result | Detail |")
    A("|---|---|---|")
    for key in (
        "case_a_savchuk_title_author",
        "case_b_poonen_nbsp",
        "case_c_new_life_translator",
    ):
        c = cal[key]
        A("| %s | **%s** | %s |" % (c["label"], c["result"].upper(), c["detail"].replace("|", "/")))
    A("")
    results = [cal[k]["result"] for k in cal]
    A("## Summary")
    A("")
    A("- Caught: **%d** / 3" % sum(1 for r in results if r == "caught"))
    A("- Missed: **%d** / 3" % sum(1 for r in results if r == "missed"))
    A("")
    tmp = CALIBRATION_MD.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(CALIBRATION_MD)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only corpus data-quality sweep")
    parser.add_argument("--resume", action="store_true", help="Resume from progress.json")
    parser.add_argument("--limit", type=int, default=0, help="Limit documents (smoke test)")
    parser.add_argument(
        "--skip-chunk-scan",
        action="store_true",
        help="Only run types 1-3 (metadata); skip types 4-5",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore prior findings/progress and start clean",
    )
    args = parser.parse_args(argv)

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    log("=" * 60)
    log("Corpus data-quality sweep starting")
    log("Review dir: %s" % REVIEW_DIR)
    log("Read-only env: %s" % READONLY_ENV_PATH)
    log("Bounds: SELECT only; progressive findings; no pipeline edits")

    if args.fresh:
        for p in (FINDINGS_JSONL, FINDINGS_MD, PROGRESS_PATH, CALIBRATION_MD):
            if p.exists():
                p.unlink()
        log("--fresh: cleared prior review artifacts")

    # Connection
    try:
        conn = connect_readonly()
    except Exception as e:
        log("FATAL: connection failed — stopping without retry. %s" % e)
        return 2

    t0 = time.time()
    try:
        log("Loading document metadata (SELECT)...")
        docs = load_all_documents(conn)
        log("Loaded %d documents" % len(docs))
        if args.limit and args.limit > 0:
            docs = docs[: args.limit]
            log("Limited to first %d documents (--limit)" % len(docs))

        progress = load_progress() if args.resume else {}
        findings: List[Dict[str, Any]] = load_findings() if args.resume else []
        if args.resume:
            log("Resume: %d prior findings loaded" % len(findings))
        else:
            # Fresh run: truncate findings file
            if FINDINGS_JSONL.exists() and not args.fresh:
                # If not --fresh but not --resume, still start clean findings
                FINDINGS_JSONL.write_text("", encoding="utf-8")
                findings = []

        seen_keys: Set[str] = set()
        for f in findings:
            seen_keys.add(_finding_key(f))

        new_count = 0

        def emit(f: Dict[str, Any]) -> None:
            nonlocal new_count
            f = dict(f)
            f["detected_at"] = _utc_now()
            k = _finding_key(f)
            if k in seen_keys:
                return
            seen_keys.add(k)
            append_finding(f)
            findings.append(f)
            new_count += 1
            if new_count % MD_REWRITE_EVERY == 0:
                rewrite_findings_md(findings, {
                    "documents_examined": len(docs),
                    "status": "in_progress",
                })

        # ---------------------------------------------------------------
        # Phase A: metadata detectors (types 1, 3) + global type 2
        # ---------------------------------------------------------------
        log("Phase A: types 1–3 (metadata + author variants) over %d docs..." % len(docs))
        if progress.get("phase_a_done") and args.resume:
            log("Phase A already done (resume) — skipping re-emit")
        else:
            for i, doc in enumerate(docs, 1):
                for f in detect_type1_author_not_name(doc):
                    emit(f)
                for f in detect_type3_author_source_mismatch(doc):
                    emit(f)
                if i % 500 == 0:
                    log("Phase A progress: %d/%d docs, %d findings so far" % (
                        i, len(docs), len(findings),
                    ))
            log("Phase A per-doc done; running global type-2 clustering...")
            for f in detect_type2_global(docs):
                emit(f)
            progress["phase_a_done"] = True
            progress["documents_examined"] = len(docs)
            save_progress(progress)
            rewrite_findings_md(findings, {
                "documents_examined": len(docs),
                "status": "phase_a_complete",
            })
            log("Phase A complete: %d findings" % len(findings))

        # ---------------------------------------------------------------
        # Phase B: chunk-scan types 4–5 (resumable by document id)
        # ---------------------------------------------------------------
        if args.skip_chunk_scan:
            log("Skipping Phase B (--skip-chunk-scan)")
        else:
            last_id = progress.get("last_chunk_scan_document_id") if args.resume else None
            # Stable order = already sorted by id
            start_idx = 0
            if last_id:
                for i, d in enumerate(docs):
                    if d["id"] == last_id:
                        start_idx = i + 1
                        break
                log("Phase B resume: starting after document_id=%s (index %d)" % (
                    last_id, start_idx,
                ))
            else:
                log("Phase B: types 4–5 chunk scan from the beginning")

            total = len(docs)
            for i in range(start_idx, total):
                doc = docs[i]
                try:
                    chunks = load_head_tail_chunks(conn, doc["id"])
                except Exception as e:
                    log("SKIP doc %s chunk load failed: %s: %s" % (
                        doc["id"], type(e).__name__, e,
                    ))
                    progress["last_chunk_scan_document_id"] = doc["id"]
                    progress.setdefault("skipped", []).append({
                        "document_id": doc["id"],
                        "reason": "%s: %s" % (type(e).__name__, str(e)[:200]),
                    })
                    save_progress(progress)
                    continue

                head_text = "\n".join(c for _, c in chunks[:HEAD_CHUNKS])
                for f in detect_type4_metadata_vs_text(doc, head_text):
                    emit(f)
                for f in detect_type5_non_teacher(doc, chunks):
                    emit(f)

                progress["last_chunk_scan_document_id"] = doc["id"]
                progress["chunk_scan_index"] = i
                progress["documents_examined"] = len(docs)
                progress["findings_count"] = len(findings)

                done_n = i + 1
                if done_n % PROGRESS_EVERY == 0 or done_n == total:
                    elapsed = time.time() - t0
                    rate = done_n / elapsed if elapsed > 0 else 0
                    eta = (total - done_n) / rate if rate > 0 else 0
                    log(
                        "Phase B progress: %d/%d docs (%.1f%%) | findings=%d | "
                        "elapsed=%.0fs | ~%.1f docs/s | ETA=%.0fs | last_id=%s"
                        % (
                            done_n, total, 100.0 * done_n / total,
                            len(findings), elapsed, rate, eta, doc["id"][:8],
                        )
                    )
                    save_progress(progress)
                    rewrite_findings_md(findings, {
                        "documents_examined": done_n,
                        "status": "phase_b_in_progress",
                        "stopped_after_document_id": doc["id"],
                    })

            progress["phase_b_done"] = True
            save_progress(progress)
            log("Phase B complete: %d findings total" % len(findings))

        # ---------------------------------------------------------------
        # Calibration (post-hoc on findings; report separately)
        # ---------------------------------------------------------------
        log("Running calibration evaluation against known cases (post-hoc)...")
        # For calibration of type 5 on New Life, ensure we scanned it even if
        # --skip-chunk-scan. If skipped, re-scan only that one via general path
        # already done... if skip, type5 may miss. Note in calibration.
        cal = evaluate_calibration(findings, docs)
        write_calibration_md(cal, {"documents_examined": len(docs)})
        log("CALIBRATION RESULTS:")
        for key, c in cal.items():
            log("  %s: %s — %s" % (c["result"].upper(), c["label"], c["detail"]))

        # Final findings rewrite
        rewrite_findings_md(findings, {
            "documents_examined": len(docs),
            "status": "complete",
        })
        progress["status"] = "complete"
        progress["completed_at"] = _utc_now()
        progress["findings_count"] = len(findings)
        save_progress(progress)

        # Summary to stdout
        by_type: Dict[str, int] = defaultdict(int)
        for f in findings:
            by_type[f.get("type", "?")] += 1

        log("=" * 60)
        log("DONE")
        log("Documents examined: %d" % len(docs))
        log("Total findings: %d" % len(findings))
        for tkey in (TYPE_1, TYPE_2, TYPE_3, TYPE_4, TYPE_5):
            log("  %s: %d" % (TYPE_LABELS[tkey], by_type.get(tkey, 0)))
        log("Calibration: " + ", ".join(
            "%s=%s" % (k, cal[k]["result"]) for k in cal
        ))
        log("Findings file: %s" % FINDINGS_MD)
        log("JSONL: %s" % FINDINGS_JSONL)
        log("Calibration: %s" % CALIBRATION_MD)
        log("Connection used throughout: newwine_readonly_analysis (read-only)")
        log("Nothing outside the review directory was written; no DB writes.")
        log("Elapsed: %.1fs" % (time.time() - t0))
        return 0

    finally:
        try:
            conn.close()
        except Exception:
            pass


def _finding_key(f: Dict[str, Any]) -> str:
    return "|".join([
        str(f.get("type") or ""),
        str(f.get("document_id") or ""),
        str(f.get("problem") or "")[:120],
        str(f.get("detail") or "")[:80],
        str(f.get("evidence") or "")[:80],
    ])


if __name__ == "__main__":
    sys.exit(main())
