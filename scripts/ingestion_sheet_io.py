#!/usr/bin/env python3
"""ingestion_sheet_io.py -- shared plain-text (TSV) read/write for the four
tabs that used to live in docs/ingestion/master_ingestion_queue.xlsx
(replaced 2026-08-26 so git shows line-level diffs instead of an opaque
binary blob).

One file per former tab, all in docs/ingestion/:
  master_ingestion_queue_read_me.tsv
  master_ingestion_queue_discovery.tsv
  master_ingestion_queue_queue.tsv
  master_ingestion_queue_approved_sites.tsv

Format: tab-delimited, one row per physical line, UTF-8, header row first.
No csv-module quoting is used -- a survey of the real data (2026-08-26)
found no field anywhere containing a literal tab character, so tab is a
safe delimiter that never needs quoting. Two Queue notes fields DO contain
literal embedded newlines, so every string value is escaped before being
written (backslash, real newline, real CR, real tab -> \\\\, \\n, \\r, \\t)
and unescaped on read -- this guarantees "one row per line" even for
free-text note fields, at the cost of storing control characters as
visible two-character sequences rather than raw. Escaping backslash first
means every backslash in the escaped output is always the first half of a
recognised two-character pair, so the single-pass unescape regex below is
unambiguous.

This module is intentionally the ONLY place that knows this encoding --
every script that reads or writes one of these four files must go through
read_tab()/write_tab() (or parse_bool_cell() for typed access), the same
"one shared implementation is the contract" discipline this repo already
applies to normalize_alias_key (Invariant 6) and is_commentary_chunk.

Python 3.12 (Invariant 1).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
INGESTION_DIR = ROOT / "docs" / "ingestion"

# Former xlsx tab name -> its replacement file. Kept keyed by the original
# tab name (not a bare variable per tab) so callers that used to say
# wb[SHEET_TAB] can now say TAB_FILES[SHEET_TAB] with a one-line change.
TAB_FILES = {
    "Read Me": INGESTION_DIR / "master_ingestion_queue_read_me.tsv",
    "Discovery": INGESTION_DIR / "master_ingestion_queue_discovery.tsv",
    "Queue": INGESTION_DIR / "master_ingestion_queue_queue.tsv",
    "Approved Sites": INGESTION_DIR / "master_ingestion_queue_approved_sites.tsv",
}

_UNESCAPE_RE = re.compile(r"\\(.)")
_UNESCAPE_MAP = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\"}


def escape_cell(value) -> str:
    """None -> "". bool -> "TRUE"/"FALSE" (matches this data's own existing
    convention -- Approved Sites' `approved` column was already a plain
    "TRUE" string, never a real Excel boolean). Everything else -> str(value)
    with backslash/newline/CR/tab escaped so the result can never contain a
    raw newline or tab, regardless of what free text a notes field holds."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    s = str(value)
    s = s.replace("\\", "\\\\")  # must run first -- see module docstring
    s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return s


def unescape_cell(s: str) -> str:
    if s == "":
        return ""
    return _UNESCAPE_RE.sub(lambda m: _UNESCAPE_MAP.get(m.group(1), "\\" + m.group(1)), s)


def parse_bool_cell(value) -> Optional[bool]:
    """Tri-state TRUE/FALSE/blank, matching how this data has always used
    these columns. A real Python bool passes straight through unchanged --
    so code exercised with literal True/False test fixtures behaves
    identically whether the value actually came from a TSV read or a
    hand-written dict."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().upper()
    if s == "":
        return None
    if s == "TRUE":
        return True
    if s == "FALSE":
        return False
    return None


def read_tab(path: Path, *, skip_blank_rows: bool = True) -> tuple[list[str], list[dict]]:
    """Returns (headers, rows). Every value is a plain str ("" for blank) --
    callers coerce to bool/int themselves (parse_bool_cell / int()), same
    division of responsibility the old openpyxl-based readers already had.

    skip_blank_rows=True (the default) drops a fully-empty row, matching the
    old openpyxl reader's "if all(v is None): continue" -- defensive against
    a stray blank line from a hand edit, and correct for every tabular tab
    (Discovery/Queue/Approved Sites) where a blank row carries no meaning.
    Pass False for a tab where a blank row IS meaningful content (the
    single-column Read Me tab uses blank lines as paragraph separators) --
    without it, those separators would silently disappear on every read."""
    if not path.exists():
        raise SystemExit(f"Ingestion sheet file not found: {path}")
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]  # trailing newline from the final written row
    if not lines:
        raise SystemExit(f"{path} is empty -- expected at least a header row")
    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        raw = line.split("\t")
        if skip_blank_rows and all(cell == "" for cell in raw):
            continue  # fully-blank row (incl. an all-tabs line)
        if len(raw) < len(headers):
            raw = raw + [""] * (len(headers) - len(raw))
        rows.append({h: unescape_cell(v) for h, v in zip(headers, raw)})
    return headers, rows


def write_tab(path: Path, headers: list[str], rows: list[dict]) -> None:
    """Atomic write: build full content in memory, write to a temp file in
    the same directory, then os.replace() it over the target -- a crash
    mid-write can never leave a half-written file in place of a good one.
    (This is per-FILE atomicity only. A caller writing two files, e.g.
    Discovery + Approved Sites together, does NOT get cross-file atomicity
    this way -- see review_discovery_candidates.py's own docstring for how
    it orders its two writes to make a crash between them recoverable
    rather than silently lossy.)"""
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join(escape_cell(row.get(h)) for h in headers))
    content = "\n".join(lines) + "\n"
    tmp_path = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)
