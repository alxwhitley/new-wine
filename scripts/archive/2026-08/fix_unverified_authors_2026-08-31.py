#!/usr/bin/env python3.12
"""
fix_unverified_authors_2026-08-31.py — one-off attended repair.

Clears seven `documents.author` values that are title fragments or partial
names, not people. All seven are citation_mode='citable' under the Vlad
Savchuk source, so each currently enters the permitted-name set that
reference_verifier builds — the set of names the answer writer is told it may
attribute claims to.

Found by: docs/audits/2026-08/author_attribution_audit_2026-08-31.md
Root cause fixed forward in: scripts/youtube_ingest.py (_verified_speaker),
commit fe0718a, with scripts/test_youtube_speaker_attribution.py.

Disposition: set author = NULL, NOT 'Vlad Savchuk'. NULL is the state of the
119 healthy Savchuk documents, where citation correctly falls back to the
source name. Writing a per-document string is what CLAUDE.md warns against and
is how this defect arose in the first place.

Safety:
  - dry run by default; --apply is required to write
  - single transaction; ROLLBACK unless exactly 7 rows update
  - in-transaction verification before COMMIT
  - post-commit reconciliation from a FRESH connection

Usage:
    python3.12 scripts/archive/2026-08/fix_unverified_authors_2026-08-31.py
    python3.12 scripts/archive/2026-08/fix_unverified_authors_2026-08-31.py --apply
"""
import sys

import psycopg2

ENV = "/Users/alexwhitley/newwine/backend/app/.env"

DOC_IDS = [
    "0b63f2c9-fe7d-4e7f-bd7d-97da0d684389",  # Day Abortion
    "628ee0f5-f3f1-4f5c-a93f-3022f410ff1f",  # Do This Instead
    "c6a50e07-6558-4149-b0d1-1aff8211e30e",  # Pastor Vlad
    "5ec75980-3378-4734-8bd5-d20666d8ea6e",  # This Is How You Should Fight...
    "51b8ccc7-ba33-45af-b6b2-efda25a7ee51",  # Vlad
    "842a7df5-5cc4-4ad3-a99a-d65e13e1ae69",  # Watch Message
    "da11f1d3-63a6-4830-9f2c-bedca8f910df",  # Your Porn Battle Plan
]
EXPECTED = 7


def load_db_url():
    with open(ENV) as fh:
        for line in fh:
            if line.strip().startswith("SUPABASE_DB_URL="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("SUPABASE_DB_URL not found")


def show_state(cur, header):
    cur.execute(
        """
        SELECT id, author, citation_mode
        FROM documents
        WHERE id = ANY(%s::uuid[])
        ORDER BY author NULLS LAST
        """,
        (DOC_IDS,),
    )
    rows = cur.fetchall()
    print("\n%s" % header)
    for doc_id, author, mode in rows:
        print("  %s  author=%-44r mode=%s" % (str(doc_id)[:8], author, mode))
    return rows


def main():
    apply_mode = "--apply" in sys.argv
    url = load_db_url()

    conn = psycopg2.connect(url)
    conn.autocommit = False
    cur = conn.cursor()

    before = show_state(cur, "BEFORE:")
    if len(before) != EXPECTED:
        conn.rollback()
        conn.close()
        raise SystemExit("ABORT: expected %d target rows, found %d" % (EXPECTED, len(before)))

    non_null = [r for r in before if r[1] is not None]
    print("\n  rows currently carrying a non-NULL author: %d" % len(non_null))

    if not apply_mode:
        conn.rollback()
        conn.close()
        print("\nDRY RUN — nothing written. Re-run with --apply to execute.")
        return 0

    print("\nAPPLYING...")
    cur.execute(
        "UPDATE documents SET author = NULL WHERE id = ANY(%s::uuid[])",
        (DOC_IDS,),
    )
    affected = cur.rowcount
    print("  UPDATE affected %d row(s)" % affected)

    if affected != EXPECTED:
        conn.rollback()
        conn.close()
        raise SystemExit("ROLLED BACK: expected %d rows, got %d" % (EXPECTED, affected))

    # Verify inside the transaction, before committing.
    cur.execute(
        "SELECT count(*) FROM documents WHERE id = ANY(%s::uuid[]) AND author IS NOT NULL",
        (DOC_IDS,),
    )
    remaining = cur.fetchone()[0]
    if remaining != 0:
        conn.rollback()
        conn.close()
        raise SystemExit("ROLLED BACK: %d target rows still carry an author" % remaining)

    conn.commit()
    print("  COMMITTED")
    cur.close()
    conn.close()

    # Reconciliation from a genuinely fresh connection.
    conn2 = psycopg2.connect(url)
    conn2.set_session(readonly=True, autocommit=True)
    cur2 = conn2.cursor()
    show_state(cur2, "AFTER (fresh connection):")

    cur2.execute(
        """
        SELECT count(*) FROM documents
        WHERE citation_mode = 'citable'
          AND btrim(coalesce(author, '')) = ANY(ARRAY[
            'Day Abortion','Do This Instead','Watch Message',
            'Your Porn Battle Plan','This Is How You Should Fight Your Battles',
            'Vlad','Pastor Vlad'])
        """
    )
    print("\n  citable rows still carrying any target string: %d" % cur2.fetchone()[0])
    cur2.close()
    conn2.close()
    print("\nDONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
