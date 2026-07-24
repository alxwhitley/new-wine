#!/usr/bin/env python3
"""
fingerprint_document.py — deterministic content signature for one
document's full footprint across all 9 corpus tables, queried live (never
from a snapshot file). Companion to export_restore_document.py for the
export -> delete -> restore -> fingerprint-compare recovery-verification
workflow: fingerprint before the drill, fingerprint after restore, compare
the two, and get an itemized diff if anything doesn't match instead of a
bare "different".

Design (settled earlier this session, restated here so it isn't re-derived
differently next time this file is touched):
  - The 3 trigger/generated tsvector columns (documents.fts_weighted,
    chunks.fts, propositions.fts) are EXCLUDED from the load-bearing hash.
    They're derived from other columns this fingerprint already covers
    (chunks.content, documents.title/author/source_name/bible_references,
    propositions.content) -- raw-comparing those source columns is what
    actually catches a real regression. Recomputing-and-diffing the
    tsvector itself only proves internal self-consistency of the trigger,
    not fidelity of a restore, so it must not be able to make an otherwise-
    identical row register as "different." Each row still carries an
    optional, clearly-labeled tsvector_sanity hash for the excluded
    column(s) -- informational only, never consulted by compare() to
    decide identical vs. different.
  - Hashing is per-field, not just per-row, so compare() can report exactly
    which column changed on a given row, not just that the row differs.

Reuses export_restore_document.py's table metadata and value normalization
(TABLE_ORDER, PK_COLUMN, EXCLUDED_TSVECTOR_COLUMNS, connect_consistent_readonly,
fetch_table_rows) rather than forking a second copy -- one normalization
path for both the snapshot writer and the fingerprinter.

CLI:
    python3 scripts/fingerprint_document.py fingerprint <document_id> [--output PATH]
    python3 scripts/fingerprint_document.py compare <fingerprint_a.json> <fingerprint_b.json>

compare exits 0 if identical, 1 if any difference was found (so it's usable
as a pass/fail step in a shell pipeline).

Created: 2026-07-24.
"""

import argparse
import hashlib
import json
import sys

from export_restore_document import (
    TABLE_ORDER,
    PK_COLUMN,
    EXCLUDED_TSVECTOR_COLUMNS,
    connect_consistent_readonly,
    fetch_table_rows,
)


def _canonical_json(obj) -> str:
    """Stable, sorted-key, no-whitespace JSON string for hashing. `default=str`
    is a defensive fallback only -- every value reaching this point has
    already been passed through normalize_value() and should already be a
    JSON-native type.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def fingerprint(document_id) -> dict:
    """Query the live database (never a snapshot) and produce a
    deterministic signature of document_id's full state across all 9
    tables, including embeddings, excluding the 3 tsvector columns from the
    load-bearing hash (see module docstring).

    Returns:
        {
          "document_id": ...,
          "generated_at": iso timestamp (informational only, not hashed),
          "tables": {
            table_name: {
              "row_count": int,
              "hash": <sha256 of this table's rows, in PK order>,
              "rows": [
                {
                  "pk": <that row's primary key value>,
                  "row_hash": <sha256 of this row's field_hashes>,
                  "field_hashes": {column: sha256(canonical(value)), ...},
                  "tsvector_sanity": {column: sha256(canonical(value)), ...}
                      # present only for tables with an excluded tsvector
                      # column; secondary/non-load-bearing, see docstring.
                },
                ...
              ]
            },
            ...
          },
          "overall": <sha256 combining every table's hash, in TABLE_ORDER>
        }
    """
    import datetime

    conn = connect_consistent_readonly()
    try:
        cur = conn.cursor()
        tables_out = {}
        table_hashes_in_order = []

        for table in TABLE_ORDER:
            _, rows = fetch_table_rows(cur, table, document_id)
            excluded = EXCLUDED_TSVECTOR_COLUMNS.get(table, set())
            pk_col = PK_COLUMN[table]

            row_entries = []
            for row in rows:
                field_hashes = {}
                for col, value in row.items():
                    if col in excluded:
                        continue
                    field_hashes[col] = _sha256(_canonical_json(value))

                row_hash = _sha256(_canonical_json(field_hashes))
                entry = {
                    "pk": row[pk_col],
                    "row_hash": row_hash,
                    "field_hashes": field_hashes,
                }

                tsvector_sanity = {
                    col: _sha256(_canonical_json(row[col]))
                    for col in excluded
                    if col in row
                }
                if tsvector_sanity:
                    entry["tsvector_sanity"] = tsvector_sanity

                row_entries.append(entry)

            table_hash = _sha256("|".join(e["row_hash"] for e in row_entries))
            tables_out[table] = {
                "row_count": len(row_entries),
                "hash": table_hash,
                "rows": row_entries,
            }
            table_hashes_in_order.append(table_hash)

        overall = _sha256("|".join(table_hashes_in_order))
        conn.commit()  # read-only txn; commit just closes it cleanly
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "document_id": document_id,
        "generated_at": datetime.datetime.now().isoformat(),
        "tables": tables_out,
        "overall": overall,
    }


def compare(fingerprint_a: dict, fingerprint_b: dict) -> dict:
    """Itemized diff between two fingerprint() results. Returns:
        {"identical": True, "differences": []}
    or
        {"identical": False, "differences": [ ...itemized entries... ]}

    Entry shapes:
        {"table": t, "type": "table_missing", "present_in_a": bool, "present_in_b": bool}
        {"table": t, "type": "row_count_mismatch", "count_a": int, "count_b": int}
        {"table": t, "type": "row_removed", "pk": ...}   # present in A, missing in B
        {"table": t, "type": "row_added", "pk": ...}     # present in B, missing in A
        {"table": t, "type": "row_changed", "pk": ..., "fields": [col, ...]}

    Never returns a bare boolean -- always the itemized structure above,
    even when identical (empty differences list).
    """
    differences = []
    tables_a = fingerprint_a.get("tables", {})
    tables_b = fingerprint_b.get("tables", {})
    all_tables = sorted(set(tables_a) | set(tables_b))

    for table in all_tables:
        in_a = table in tables_a
        in_b = table in tables_b
        if not in_a or not in_b:
            differences.append({
                "table": table,
                "type": "table_missing",
                "present_in_a": in_a,
                "present_in_b": in_b,
            })
            continue

        t_a = tables_a[table]
        t_b = tables_b[table]
        if t_a["hash"] == t_b["hash"]:
            continue  # this table is identical; nothing to itemize

        if t_a["row_count"] != t_b["row_count"]:
            differences.append({
                "table": table,
                "type": "row_count_mismatch",
                "count_a": t_a["row_count"],
                "count_b": t_b["row_count"],
            })

        map_a = {row["pk"]: row for row in t_a["rows"]}
        map_b = {row["pk"]: row for row in t_b["rows"]}
        pks_a, pks_b = set(map_a), set(map_b)

        for pk in sorted(pks_a - pks_b, key=str):
            differences.append({"table": table, "type": "row_removed", "pk": pk})
        for pk in sorted(pks_b - pks_a, key=str):
            differences.append({"table": table, "type": "row_added", "pk": pk})

        for pk in sorted(pks_a & pks_b, key=str):
            entry_a = map_a[pk]
            entry_b = map_b[pk]
            if entry_a["row_hash"] == entry_b["row_hash"]:
                continue
            fields_a = entry_a.get("field_hashes", {})
            fields_b = entry_b.get("field_hashes", {})
            changed_fields = sorted(
                f for f in set(fields_a) | set(fields_b)
                if fields_a.get(f) != fields_b.get(f)
            )
            differences.append({
                "table": table,
                "type": "row_changed",
                "pk": pk,
                "fields": changed_fields,
            })

    return {
        "identical": len(differences) == 0,
        "differences": differences,
    }


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Compute or compare a deterministic content fingerprint for one document across all 9 corpus tables"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_fp = sub.add_parser("fingerprint", help="Compute a live fingerprint for one document")
    p_fp.add_argument("document_id")
    p_fp.add_argument("--output", help="Write fingerprint JSON to this path (default: stdout)")

    p_cmp = sub.add_parser("compare", help="Compare two saved fingerprint JSON files")
    p_cmp.add_argument("fingerprint_a")
    p_cmp.add_argument("fingerprint_b")

    args = parser.parse_args()

    if args.command == "fingerprint":
        fp = fingerprint(args.document_id)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(fp, f, indent=2)
            print(f"Wrote fingerprint to {args.output}")
        else:
            print(json.dumps(fp, indent=2))
    elif args.command == "compare":
        with open(args.fingerprint_a) as f:
            fp_a = json.load(f)
        with open(args.fingerprint_b) as f:
            fp_b = json.load(f)
        result = compare(fp_a, fp_b)
        print(json.dumps(result, indent=2))
        if not result["identical"]:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
