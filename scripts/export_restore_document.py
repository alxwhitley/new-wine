#!/usr/bin/env python3
"""
export_restore_document.py — export / restore / delete one document's full
footprint across all 9 corpus tables that key to `documents.id`, for the
export -> delete -> restore -> fingerprint-compare recovery-verification
workflow (Phase 3/4 of the current recovery-drill work).

Scope: documents, chunks, propositions, excerpts, book_quotes, books,
background_topics, feedback, removed_urls. See table notes below for the
FK/trigger/generated-column quirks each function has to respect.

Table quirks this file must not get wrong:
  - documents.fts_weighted, chunks.fts: plain tsvector columns recomputed by
    a BEFORE INSERT/UPDATE trigger. Safe to omit from INSERT column lists
    (any supplied value would be silently overwritten anyway) -- omitted
    here for cleanliness, not because supplying one would error.
  - propositions.fts: a TRUE `GENERATED ALWAYS` column. MUST NOT appear in
    the INSERT column list at all -- naming it errors the whole statement.
  - chunks.embedding / propositions.embedding: plain vector(1536) columns,
    nullable, NO default, NO trigger. Must be explicitly supplied on
    restore or the row silently loses its embedding.
  - background_topics.id: bigint identity via nextval(), not
    gen_random_uuid(). Restoring an explicit id does not advance the
    sequence -- callers of restore() must (and this module does) bump the
    sequence afterward via pg_get_serial_sequence(), never a hardcoded
    sequence name.
  - background_topics.document_id: NOT NULL, ON DELETE NO ACTION (not
    CASCADE). delete_document_cascade() must delete background_topics rows
    for the document BEFORE deleting the documents row, or the documents
    delete raises a foreign key violation.
  - removed_urls: no FK constraint at all (PK is `url`, a text column, not
    a uuid). delete_document_cascade() must delete matching removed_urls
    rows explicitly as an application-logic cascade -- the database will
    not do it for you.
  - books.document_id / feedback.source_document_id: ON DELETE SET NULL,
    not CASCADE. delete_document_cascade() deletes documents, which NULLs
    these FKs but does NOT delete the books/feedback rows themselves --
    they survive the delete with a nulled FK. A plain restore INSERT of
    the original row (same PK) would then collide with that surviving row
    and fail. _insert_table_rows() therefore restores books and feedback
    via INSERT ... ON CONFLICT (id) DO UPDATE SET <every non-PK column>,
    not a plain INSERT: if the row was actually gone, the INSERT path
    fires; if it survived with a nulled FK, the UPDATE path fires and
    resets every column (including the FK) back to the snapshot value,
    re-linking it to the restored document. The other 7 tables keep a
    plain INSERT -- their FK is CASCADE or nonexistent, so nothing survives
    the delete for a restore to collide with.

Every INSERT and DELETE in this module uses parameterized queries (%s
placeholders via psycopg2) -- no raw string interpolation of values, ever.
This operates on live production data.

Batch functions (delete_documents_cascade, restore_many): each covers N
documents in ONE connection / ONE transaction, not N sequential
single-document transactions -- a batch either fully commits or fully rolls
back, so a failure on document 3 of 5 also undoes documents 1-2's work in
the same call. restore_many() inserts table-major across the WHOLE batch
(every snapshot's documents row, then every snapshot's chunks rows, etc.,
following TABLE_ORDER) rather than document-major, and bumps the
background_topics sequence once at the end for the whole batch instead of
once per document. Both batch functions reuse the same per-table helpers
(_insert_table_rows, _bump_background_topics_sequence, TABLE_ORDER, etc.)
as the single-document versions -- no per-table logic is forked.

CLI:
    python3 scripts/export_restore_document.py export <document_id> <output_path>
    python3 scripts/export_restore_document.py restore <snapshot_path>
    python3 scripts/export_restore_document.py delete <document_id>
    python3 scripts/export_restore_document.py delete-batch <document_id> [<document_id> ...]
    python3 scripts/export_restore_document.py restore-batch <snapshot_path> [<snapshot_path> ...]

Created: 2026-07-24.
"""

import argparse
import datetime
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, unquote

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_REPEATABLE_READ
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

# ── Table metadata ───────────────────────────────────────────────────────────
# Restore insert order: documents first (parent), then every table that
# references it (order among these seven does not matter -- none of them
# reference each other, only documents), then removed_urls (no FK, order
# irrelevant). This same list order is reused for export/fingerprint so
# snapshot and fingerprint JSON always presents tables in one fixed,
# readable order.
TABLE_ORDER = [
    "documents",
    "chunks",
    "propositions",
    "excerpts",
    "book_quotes",
    "books",
    "background_topics",
    "feedback",
    "removed_urls",
]

# Column used to select "every row attached to this document" per table.
# documents itself is matched on its own `id`; feedback is matched on
# `source_document_id`, NOT `document_id` -- there is no `document_id`
# column on feedback.
FK_COLUMN = {
    "documents": "id",
    "chunks": "document_id",
    "propositions": "document_id",
    "excerpts": "document_id",
    "book_quotes": "document_id",
    "books": "document_id",
    "background_topics": "document_id",
    "feedback": "source_document_id",
    "removed_urls": "document_id",
}

# Primary key column per table, used both for deterministic ORDER BY and as
# the stable row identifier in fingerprint diffs. removed_urls has no uuid
# `id` -- its PK is the `url` text column.
PK_COLUMN = {
    "documents": "id",
    "chunks": "id",
    "propositions": "id",
    "excerpts": "id",
    "book_quotes": "id",
    "books": "id",
    "background_topics": "id",
    "feedback": "id",
    "removed_urls": "url",
}

# Columns that are trigger-maintained or GENERATED ALWAYS tsvector columns.
# Excluded from every INSERT column list on restore. Also excluded from the
# "must match" hash computation in fingerprint_document.py (they're derived
# from other columns already covered by the hash, not primary data).
EXCLUDED_TSVECTOR_COLUMNS = {
    "documents": {"fts_weighted"},
    "chunks": {"fts"},
    "propositions": {"fts"},
}

# Tables whose FK back to documents is ON DELETE SET NULL (not CASCADE), so
# a row can survive delete_document_cascade() with its FK nulled out. A
# plain restore INSERT of the same PK would collide with that surviving
# row, so these two restore via INSERT ... ON CONFLICT (pk) DO UPDATE
# instead -- see the module docstring's table-quirks note above.
UPSERT_ON_RESTORE = {"books", "feedback"}


def connect():
    """Plain read/write connection, default isolation, autocommit off."""
    return psycopg2.connect(**DB_PARAMS)


def connect_consistent_readonly():
    """Connection for export/fingerprint: REPEATABLE READ + read-only, set
    before any query runs, so every one of the 9 per-table SELECTs in a
    single export or fingerprint call sees one consistent snapshot of the
    document's data rather than 9 independent reads that could straddle a
    concurrent write. read-only is also a belt-and-suspenders guard against
    an accidental write in what must stay a read-only code path.
    """
    conn = connect()
    conn.set_session(isolation_level=ISOLATION_LEVEL_REPEATABLE_READ, readonly=True)
    return conn


# ── Value normalization (shared by export() and fingerprint_document.py) ────

def parse_embedding(value):
    """Normalize a pgvector value to a JSON-native list of full-precision
    floats. psycopg2 hands back pgvector columns as a string like
    '[0.1,0.2,...]' in this codebase (no vector adapter is registered
    anywhere -- confirmed live before writing this). Also tolerates an
    already-list-like value in case that ever changes.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        if not s:
            return []
        return [float(x) for x in s.split(",")]
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    if hasattr(value, "tolist"):
        return [float(x) for x in value.tolist()]
    raise TypeError(f"Unrecognized embedding value type: {type(value)!r}")


def normalize_value(col_name, value):
    """Convert one raw psycopg2 column value into a JSON-serializable,
    round-trippable Python value. Shared by export() (writes the snapshot)
    and fingerprint_document.py (hashes live values) so both see identical
    normalization -- one implementation, not two that can drift apart.
    """
    if value is None:
        return None
    if col_name == "embedding":
        return parse_embedding(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, list):
        return [normalize_value(col_name, v) for v in value]
    return value  # str / int / float / bool already JSON-safe; tsvector already str


def fetch_table_rows(cur, table, document_id):
    """SELECT * for every row attached to document_id in `table`, in a
    stable deterministic order (by that table's primary key -- never
    unordered result order), normalized to JSON-safe values.

    Returns (column_names_in_order, list_of_row_dicts).
    """
    fk_col = FK_COLUMN[table]
    pk_col = PK_COLUMN[table]
    query = f"SELECT * FROM {table} WHERE {fk_col} = %s ORDER BY {pk_col}"
    cur.execute(query, (document_id,))
    col_names = [d[0] for d in cur.description]
    raw_rows = cur.fetchall()
    rows = []
    for raw in raw_rows:
        row = {}
        for col_name, value in zip(col_names, raw):
            row[col_name] = normalize_value(col_name, value)
        rows.append(row)
    return col_names, rows


# ── export ────────────────────────────────────────────────────────────────

def export(document_id, output_path):
    """Read every row across all 9 tables attached to document_id in one
    consistent transaction and write a single self-contained JSON snapshot
    to output_path. Raises ValueError if no documents row exists for
    document_id (refuses to write a snapshot for a document that doesn't
    exist). Returns the snapshot's _meta dict.
    """
    conn = connect_consistent_readonly()
    try:
        cur = conn.cursor()

        _, doc_rows = fetch_table_rows(cur, "documents", document_id)
        if not doc_rows:
            raise ValueError(f"No document found with id={document_id!r} -- refusing to write an empty/invalid snapshot")

        tables = {"documents": doc_rows}
        row_counts = {"documents": len(doc_rows)}

        for table in TABLE_ORDER:
            if table == "documents":
                continue
            _, rows = fetch_table_rows(cur, table, document_id)
            tables[table] = rows
            row_counts[table] = len(rows)

        conn.commit()  # read-only txn; commit just closes it cleanly
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    snapshot = {
        "_meta": {
            "document_id": document_id,
            "exported_at": datetime.datetime.now().isoformat(),
            "table_row_counts": row_counts,
        },
        "tables": tables,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    return snapshot["_meta"]


# ── restore ───────────────────────────────────────────────────────────────

def _insert_table_rows(cur, table, rows):
    """INSERT every row for one table, explicit column list and values,
    excluding only the trigger/generated tsvector column for that table (if
    any). embedding columns get an explicit ::vector cast in the
    placeholder, matching the rest of this codebase's insert convention
    (shared_ingest.py, propositions.py) -- an unqualified %s parameter does
    not implicitly cast to vector.

    For `books` and `feedback` (see UPSERT_ON_RESTORE / module docstring),
    the plain INSERT is upgraded to INSERT ... ON CONFLICT (pk) DO UPDATE
    SET <every non-PK column>, because their FK to documents is ON DELETE
    SET NULL rather than CASCADE and a row can survive
    delete_document_cascade() with its FK nulled out, colliding with a
    plain restore INSERT on the same PK. The other 7 tables are untouched
    by this and keep a plain INSERT.
    """
    if not rows:
        return 0

    exclude = EXCLUDED_TSVECTOR_COLUMNS.get(table, set())
    expected_keys = set(rows[0].keys())
    for row in rows:
        if set(row.keys()) != expected_keys:
            raise ValueError(
                f"Inconsistent column set across {table!r} rows in snapshot -- "
                f"refusing to guess which columns to insert"
            )

    columns = [c for c in rows[0].keys() if c not in exclude]
    placeholders = ["%s::vector" if c == "embedding" else "%s" for c in columns]
    query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

    if table in UPSERT_ON_RESTORE:
        pk_col = PK_COLUMN[table]
        update_cols = [c for c in columns if c != pk_col]
        if update_cols:
            set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
            query += f" ON CONFLICT ({pk_col}) DO UPDATE SET {set_clause}"
        else:
            query += f" ON CONFLICT ({pk_col}) DO NOTHING"

    for row in rows:
        values = []
        for c in columns:
            v = row[c]
            if c == "embedding" and v is not None:
                v = "[" + ",".join(str(x) for x in v) + "]"
            values.append(v)
        cur.execute(query, values)

    return len(rows)


def _bump_background_topics_sequence(cur):
    """After restoring explicit background_topics.id values, advance the
    backing sequence to at least the current max id so a future normal
    insert (which calls nextval()) can't collide. Looks the sequence name
    up via pg_get_serial_sequence() -- never hardcoded.
    """
    cur.execute("SELECT pg_get_serial_sequence('background_topics', 'id')")
    row = cur.fetchone()
    seq_name = row[0] if row else None
    if not seq_name:
        return
    cur.execute("SELECT MAX(id) FROM background_topics")
    (max_id,) = cur.fetchone()
    if max_id is None:
        return
    cur.execute("SELECT setval(%s, %s)", (seq_name, max_id))


def restore(snapshot_path):
    """Read a snapshot written by export() and re-insert every row into
    every table, in FK-safe order, inside ONE transaction. If any row fails
    to insert for any reason, the whole restore rolls back completely and
    raises -- no partial completion. Returns {table: rows_inserted}.
    """
    with open(snapshot_path) as f:
        snapshot = json.load(f)

    tables = snapshot["tables"]
    conn = connect()
    try:
        cur = conn.cursor()
        counts = {}
        for table in TABLE_ORDER:
            rows = tables.get(table, [])
            counts[table] = _insert_table_rows(cur, table, rows)

        if counts.get("background_topics", 0) > 0:
            _bump_background_topics_sequence(cur)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return counts


def restore_many(snapshot_paths):
    """Batch version of restore(): reads every snapshot in snapshot_paths and
    inserts all rows for the entire batch inside ONE connection / ONE
    transaction (not one transaction per snapshot). Insert order is
    table-major across the WHOLE batch -- every snapshot's `documents` row
    first, then every snapshot's `chunks` rows, then every snapshot's
    `propositions` rows, and so on through TABLE_ORDER -- rather than
    document-major (all of snapshot A's tables, then all of snapshot B's).
    This is the same FK-safe table order restore() already uses for one
    document, just extended across N so a partially-inserted batch never
    leaves a child row pointing at a not-yet-inserted parent even
    transiently. Reuses _insert_table_rows() and TABLE_ORDER unchanged --
    no per-table insert logic is duplicated here.

    background_topics.id sequence is bumped exactly once at the end, after
    every snapshot's background_topics rows are inserted, if any document in
    the batch had background_topics rows -- not once per document.

    If any row in any snapshot fails to insert, the whole batch rolls back
    completely and raises -- no partial completion for any document.
    Returns {document_id: {table: rows_inserted}}, one entry per snapshot,
    keyed by each snapshot's own _meta.document_id.
    """
    snapshots = []
    for snapshot_path in snapshot_paths:
        with open(snapshot_path) as f:
            snapshot = json.load(f)
        snapshots.append(snapshot)

    conn = connect()
    try:
        cur = conn.cursor()
        counts = {snapshot["_meta"]["document_id"]: {} for snapshot in snapshots}
        any_background_topics = False

        for table in TABLE_ORDER:
            for snapshot in snapshots:
                document_id = snapshot["_meta"]["document_id"]
                rows = snapshot["tables"].get(table, [])
                inserted = _insert_table_rows(cur, table, rows)
                counts[document_id][table] = inserted
                if table == "background_topics" and inserted > 0:
                    any_background_topics = True

        if any_background_topics:
            _bump_background_topics_sequence(cur)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return counts


# ── delete ────────────────────────────────────────────────────────────────

def delete_document_cascade(document_id):
    """Delete one document and every row attached to it, in one
    transaction: background_topics and removed_urls are deleted explicitly
    (background_topics because its FK is NO ACTION, not CASCADE --
    deleting documents first would raise a foreign key violation;
    removed_urls because it has no FK at all, so nothing cascades to it
    automatically). Then deletes the documents row itself, which CASCADEs
    chunks/propositions/excerpts/book_quotes and SET NULLs books/feedback.
    Commits only if every statement succeeds; rolls back entirely on any
    failure. Returns row-count deleted per explicit statement.
    """
    conn = connect()
    try:
        cur = conn.cursor()

        cur.execute("DELETE FROM background_topics WHERE document_id = %s", (document_id,))
        background_topics_deleted = cur.rowcount

        cur.execute("DELETE FROM removed_urls WHERE document_id = %s", (document_id,))
        removed_urls_deleted = cur.rowcount

        cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        documents_deleted = cur.rowcount

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "background_topics_deleted": background_topics_deleted,
        "removed_urls_deleted": removed_urls_deleted,
        "documents_deleted": documents_deleted,
    }


def delete_documents_cascade(document_ids):
    """Batch version of delete_document_cascade(): deletes every document in
    document_ids inside ONE connection / ONE transaction (not one
    transaction per document), in list order. For each document_id, runs
    the exact same three steps delete_document_cascade() runs for one
    document -- delete background_topics rows, delete removed_urls rows,
    delete the documents row (which CASCADEs chunks/propositions/excerpts/
    book_quotes and SET NULLs books/feedback) -- in that order, for the same
    FK reasons documented on delete_document_cascade() and in the module
    docstring's table-quirks notes.

    Commits once, only if every document's deletes succeed. Rolls back the
    ENTIRE batch on any single failure -- if document 3 of 5 fails,
    documents 1-2's deletes are undone too, not left partially applied.

    Returns {document_id: {"background_topics_deleted": n,
    "removed_urls_deleted": n, "documents_deleted": n}}, same per-document
    shape as delete_document_cascade()'s return value, one entry per
    document_id.
    """
    conn = connect()
    try:
        cur = conn.cursor()
        results = {}

        for document_id in document_ids:
            cur.execute("DELETE FROM background_topics WHERE document_id = %s", (document_id,))
            background_topics_deleted = cur.rowcount

            cur.execute("DELETE FROM removed_urls WHERE document_id = %s", (document_id,))
            removed_urls_deleted = cur.rowcount

            cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
            documents_deleted = cur.rowcount

            results[document_id] = {
                "background_topics_deleted": background_topics_deleted,
                "removed_urls_deleted": removed_urls_deleted,
                "documents_deleted": documents_deleted,
            }

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return results


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Export / restore / delete one document's full footprint across all 9 corpus tables"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Export one document to a JSON snapshot")
    p_export.add_argument("document_id")
    p_export.add_argument("output_path")

    p_restore = sub.add_parser("restore", help="Restore a JSON snapshot into the live tables")
    p_restore.add_argument("snapshot_path")

    p_delete = sub.add_parser("delete", help="Delete one document and its dependent rows")
    p_delete.add_argument("document_id")

    p_delete_batch = sub.add_parser(
        "delete-batch", help="Delete multiple documents and their dependent rows in ONE transaction"
    )
    p_delete_batch.add_argument("document_ids", nargs="+")

    p_restore_batch = sub.add_parser(
        "restore-batch", help="Restore multiple JSON snapshots into the live tables in ONE transaction"
    )
    p_restore_batch.add_argument("snapshot_paths", nargs="+")

    args = parser.parse_args()

    if args.command == "export":
        meta = export(args.document_id, args.output_path)
        print(json.dumps(meta, indent=2))
    elif args.command == "restore":
        counts = restore(args.snapshot_path)
        print(json.dumps(counts, indent=2))
    elif args.command == "delete":
        result = delete_document_cascade(args.document_id)
        print(json.dumps(result, indent=2))
    elif args.command == "delete-batch":
        result = delete_documents_cascade(args.document_ids)
        print(json.dumps(result, indent=2))
    elif args.command == "restore-batch":
        counts = restore_many(args.snapshot_paths)
        print(json.dumps(counts, indent=2))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
