#!/usr/bin/env python3
"""
apply_migration_085.py -- Apply and verify migration 085 (quote rail:
remove the human-approval gate, add the speaker-confirmation gate, add
quote_verification_log).

Every check that mutates runs inside a transaction with autocommit=False;
dry-run checks call conn.rollback() and never conn.commit(). Only the
migration DDL itself and the two real read-only verification SELECTs at the
end are exempt from that pattern.

Real chunk fixtures reused from scripts/test_quote_verifier.py (same
document, "The New Life" front matter is NOT used -- these are genuine
Murray Preface text, chunk_index 6/7, outside the excluded zone):
  MURRAY_CHUNK_6 = 00b5623f-12a7-43bb-9bb7-af72d898ec73
  (document source_id = d26f77e7-6ce0-4311-991b-03d9900a6045, Andrew Murray)

Usage:
  python3 scripts/apply_migration_085.py
"""
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

MURRAY_CHUNK_6 = "00b5623f-12a7-43bb-9bb7-af72d898ec73"
MURRAY_SOURCE_ID = "d26f77e7-6ce0-4311-991b-03d9900a6045"
PRINCE_SOURCE_ID = "17be391b-d025-4178-8543-3e84da675c5d"  # wrong-teacher fixture for gate 2 test
NON_ADMIN_USER_ID = "1ea99425-08ec-40f2-9ed3-588b88122a82"  # role='user' in user_roles -- proves gate 1 is gone
MURRAY_QUOTE_TEXT = "While writing this book I have had a second wish abiding with me."

_pass = 0
_fail = 0


def check(label, passed, detail=None):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if detail:
        print("         %s" % detail)
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_conn():
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    conn = psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )
    conn.autocommit = False
    return conn


def apply_migration():
    conn = get_conn()
    cur = conn.cursor()
    migration_sql = (ROOT / "migrations" / "085_quote_rail_remove_human_approval.sql").read_text()
    cur.execute(migration_sql)
    conn.commit()
    print("Migration 085 applied OK (table + trigger function replaced)")
    cur.close()
    conn.close()


def _insert_test_revision(cur, chunk_id):
    revision_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO quote_source_revisions (id, chunk_id, passage_text, captured_by) "
        "SELECT %s, %s, content, %s FROM chunks WHERE id = %s",
        (revision_id, chunk_id, NON_ADMIN_USER_ID, chunk_id),
    )
    return revision_id


def verify_gate1_removed_nonadmin_can_approve():
    """A non-admin (role='user') approved_by must now succeed -- proves the
    admin-role trigger check (old Gate 1) is gone. Rolled back, never committed."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        revision_id = _insert_test_revision(cur, MURRAY_CHUNK_6)
        cur.execute(
            "INSERT INTO quotes (source_revision_id, teacher_source_id, quote_text, topic, "
            "reviewer_note, status, created_by, approved_by, approved_at) "
            "VALUES (%s, %s, %s, 'test-topic', 'test-note', 'approved', %s, %s, now())",
            (revision_id, MURRAY_SOURCE_ID, MURRAY_QUOTE_TEXT, NON_ADMIN_USER_ID, NON_ADMIN_USER_ID),
        )
        check("non-admin approved_by (role='user') now succeeds -- Gate 1 removed", True)
    except Exception as e:
        check("non-admin approved_by (role='user') now succeeds -- Gate 1 removed", False, "%r" % e)
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def verify_gate_speaker_confirmation_rejects_mismatch():
    """Attributing a Murray-document chunk to Prince's source_id must be
    rejected -- the new speaker-confirmation gate. Rolled back."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        revision_id = _insert_test_revision(cur, MURRAY_CHUNK_6)
        cur.execute(
            "INSERT INTO quotes (source_revision_id, teacher_source_id, quote_text, topic, "
            "reviewer_note, status, created_by, approved_by, approved_at) "
            "VALUES (%s, %s, %s, 'test-topic', 'test-note', 'approved', %s, %s, now())",
            (revision_id, PRINCE_SOURCE_ID, MURRAY_QUOTE_TEXT, NON_ADMIN_USER_ID, NON_ADMIN_USER_ID),
        )
        check("mismatched teacher_source_id (Prince) on a Murray chunk REJECTED", False,
              "write unexpectedly SUCCEEDED")
    except Exception as e:
        ok = "speaker not positively confirmed" in str(e)
        check("mismatched teacher_source_id (Prince) on a Murray chunk REJECTED", ok, "%r" % e)
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def verify_gate_correct_speaker_still_succeeds():
    """Sanity check: the correct teacher_source_id for this chunk's real
    document must still pass the new gate (not just the removed one)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        revision_id = _insert_test_revision(cur, MURRAY_CHUNK_6)
        cur.execute(
            "INSERT INTO quotes (source_revision_id, teacher_source_id, quote_text, topic, "
            "reviewer_note, status, created_by, approved_by, approved_at) "
            "VALUES (%s, %s, %s, 'test-topic', 'test-note', 'approved', %s, %s, now())",
            (revision_id, MURRAY_SOURCE_ID, MURRAY_QUOTE_TEXT, NON_ADMIN_USER_ID, NON_ADMIN_USER_ID),
        )
        check("correct teacher_source_id (Murray) on a Murray chunk still succeeds", True)
    except Exception as e:
        check("correct teacher_source_id (Murray) on a Murray chunk still succeeds", False, "%r" % e)
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def verify_quote_verification_log_writable():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO quote_verification_log (chunk_id, document_id, teacher_source_id, "
            "candidate_quote_text, decision, rule, reason, submitted_by) "
            "VALUES (%s, NULL, %s, 'test candidate', 'refused', 'test_rule', 'test reason', %s)",
            (MURRAY_CHUNK_6, MURRAY_SOURCE_ID, NON_ADMIN_USER_ID),
        )
        check("quote_verification_log accepts an insert", True)
    except Exception as e:
        check("quote_verification_log accepts an insert", False, "%r" % e)
    finally:
        conn.rollback()
        cur.close()
        conn.close()


def verify_existing_approved_quotes_unaffected():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT id, status FROM quotes WHERE status = 'approved' ORDER BY created_at")
    rows = cur.fetchall()
    check("2 pre-existing approved quotes still readable, status unchanged", len(rows) == 2,
          "found %d: %s" % (len(rows), rows))
    cur.close()
    conn.close()


def verify_readwrite_connection_unaffected():
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT current_user;")
    u = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM documents;")
    n = cur.fetchone()[0]
    check("existing read-write connection (SUPABASE_DB_URL) still works", True,
          "current_user=%s, documents visible=%d" % (u, n))
    cur.close()
    conn.close()


def main():
    print("\nquote rail -- migration 085 apply + verify")
    print("=" * 68)

    apply_migration()

    print()
    print("Verification (fresh connections, all dry-run inserts rolled back):")
    verify_gate1_removed_nonadmin_can_approve()
    verify_gate_speaker_confirmation_rejects_mismatch()
    verify_gate_correct_speaker_still_succeeds()
    verify_quote_verification_log_writable()
    verify_existing_approved_quotes_unaffected()
    verify_readwrite_connection_unaffected()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
