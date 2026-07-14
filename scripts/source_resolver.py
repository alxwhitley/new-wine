#!/usr/bin/env python3
"""
Source resolver for Rhemata ingest pipeline.

normalize_alias_key() now lives in backend/app/services/source_resolver.py —
the canonical home, shared with the backend's reference-verification code
(see docs/superpowers/plans/2026-07-14-sp1-reference-pointer-backend.md).
Byte-identical relocation proven by scripts/test_source_resolver_relocation.py
before this repoint landed. Do not redefine normalize_alias_key here again —
import it, as below.

Usage from an ingest script:
    from source_resolver import resolve_source_id, SENTINEL_SOURCE_ID
    source_id, norm_key, via = resolve_source_id(db, source_name, author)
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.services.source_resolver import normalize_alias_key

# Protected sentinel — documents with unresolved attribution land here via the
# documents.source_id column DEFAULT.  NEVER pass this UUID to a DELETE.
SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22"

# New Wine Magazine has a fixed source_id.  Use this constant in the live write
# path rather than a DB lookup — the alias is also seeded, but this avoids a
# round-trip for a value that never changes.
NEW_WINE_MAGAZINE_SOURCE_ID = "72b2f583-d7f9-4361-be1c-6d5aebe59fac"


def resolve_source_id(
    db,
    source_name: Optional[str],
    author: Optional[str],
) -> Tuple[str, str, str]:
    """Resolve attribution strings to a source_id via the source_aliases table.

    Resolution order:
      1. normalize(source_name) → alias_key lookup in source_aliases
      2. normalize(author)      → alias_key lookup in source_aliases
      3. SENTINEL + ALIAS_MISS print (grep-able)

    Returns (source_id, matched_key, match_via) where match_via is one of
    'source_name', 'author', or 'MISS'.

    The ALIAS_MISS line is always printed to stdout so it survives piped output
    and is grep-able in run logs:
        grep ALIAS_MISS ingest.log
    """
    for raw, label in [(source_name, "source_name"), (author, "author")]:
        if not raw:
            continue
        key = normalize_alias_key(raw)
        if not key:
            continue
        result = (
            db.table("source_aliases")
            .select("source_id")
            .eq("alias_key", key)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["source_id"], key, label

    print(f"ALIAS_MISS  source_name={source_name!r}  author={author!r}")
    return SENTINEL_SOURCE_ID, normalize_alias_key(source_name or author or ""), "MISS"


# ── Dry-run table printer (shared by both ingest scripts) ─────────────────────

_COL = {
    "file":        28,
    "source_name": 24,
    "author":      22,
    "norm_key":    26,
    "source_id":   36,
    "via":         12,
}


def _trunc(val: Optional[str], width: int) -> str:
    s = str(val) if val is not None else "—"
    return s if len(s) <= width else s[: width - 1] + "…"


def print_resolution_table(rows: List[Dict], label: str = "") -> None:
    """Print the source-resolution table and summary produced by --dry-run-sources."""
    header = (
        f"{'FILE':<{_COL['file']}} "
        f"{'SOURCE_NAME':<{_COL['source_name']}} "
        f"{'AUTHOR':<{_COL['author']}} "
        f"{'NORM_KEY':<{_COL['norm_key']}} "
        f"{'SOURCE_ID':<{_COL['source_id']}} "
        f"VIA"
    )
    sep = "─" * (len(header) + 4)

    heading = f"SOURCE RESOLUTION DRY-RUN — {label}" if label else f"SOURCE RESOLUTION DRY-RUN — {len(rows)} doc(s)"
    print(f"\n{heading}")
    print(sep)
    print(header)
    print(sep)

    misses: List[Dict] = []
    for r in rows:
        via = r["via"]
        flag = "  ← SENTINEL" if via == "MISS" else ""
        print(
            f"{_trunc(r['file'],        _COL['file']):<{_COL['file']}} "
            f"{_trunc(r['source_name'], _COL['source_name']):<{_COL['source_name']}} "
            f"{_trunc(r['author'],      _COL['author']):<{_COL['author']}} "
            f"{_trunc(r['norm_key'],    _COL['norm_key']):<{_COL['norm_key']}} "
            f"{r['source_id']:<{_COL['source_id']}} "
            f"{via}{flag}"
        )
        if via == "MISS":
            misses.append(r)

    print(sep)
    resolved = len(rows) - len(misses)
    print(
        f"SUMMARY  total={len(rows)}  resolved={resolved}  misses={len(misses)}"
    )
    if misses:
        distinct = sorted({(r["source_name"], r["author"]) for r in misses})
        print("  Distinct misses:")
        for sn, au in distinct:
            print(f"    source_name={sn!r}  author={au!r}")
    print()
