#!/usr/bin/env python3
"""
apply_positions_migration_076.py -- Apply and verify migration 076 (lift the
corpus-wide position ban: widen positions.kind CHECK to ('teacher','corpus'),
make source_id NULLABLE, add the scope/source coupling CHECK).

Idempotent: detects whether the widened CHECK is already present and skips the
apply if so. Schema-level verification only, on a FRESH connection per
migration 049's known landmine (a stale connection can report state that
isn't really committed).

Usage:
  python3 scripts/apply_positions_migration_076.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

_pass = 0
_fail = 0


def check(label, passed):
    global _pass, _fail
    tag = "PASS" if passed else "FAIL"
    print("  [%s] %s" % (tag, label))
    if passed:
        _pass += 1
    else:
        _fail += 1


def get_db_conn():
    import psycopg2

    db_url = os.environ["SUPABASE_DB_URL"]
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname,
        port=p.port or 5432,
        user=unquote(p.username or ""),
        password=unquote(p.password or ""),
        dbname=p.path.lstrip("/"),
    )


def _kind_check_def(cur):
    cur.execute(
        "SELECT pg_get_constraintdef(con.oid) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = 'positions' AND con.conname = 'positions_kind_check'"
    )
    row = cur.fetchone()
    return row[0] if row else None


def main():
    print("\nLift corpus-wide position ban -- migration 076 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    current_def = _kind_check_def(cur)
    already_applied = current_def is not None and "corpus" in current_def
    if already_applied:
        print("kind CHECK already includes 'corpus' -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "076_positions_lift_corpus_ban.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection: confirm everything is really there -----------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    kind_def = _kind_check_def(cur2)
    check("positions_kind_check still exists (not dropped)", kind_def is not None)
    check("kind CHECK now allows 'teacher'", kind_def is not None and "teacher" in kind_def)
    check("kind CHECK now allows 'corpus'", kind_def is not None and "corpus" in kind_def)

    cur2.execute(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'positions' AND column_name = 'source_id'"
    )
    check("source_id is now NULLABLE", cur2.fetchone()[0] == "YES")

    cur2.execute(
        "SELECT pg_get_constraintdef(con.oid) "
        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
        "WHERE c.relname = 'positions' AND con.conname = 'positions_scope_source_coupling'"
    )
    coupling = cur2.fetchone()
    check("scope/source coupling CHECK present", coupling is not None)

    # -- Behavioral proof the coupling actually rejects the two illegal shapes.
    # A corpus row with a source_id (would be an averaged-but-attributed-to-one
    # position) and a teacher row with NULL source_id (an unattributed teacher
    # position) must both be rejected. Rolled back -- proof only, no write kept.
    import psycopg2

    for label, kind, src_sql in (
        ("corpus row WITH source_id is rejected", "corpus",
         "(SELECT id FROM sources LIMIT 1)"),
        ("teacher row WITHOUT source_id is rejected", "teacher", "NULL"),
    ):
        try:
            cur2.execute(
                "INSERT INTO positions (kind, source_id, topic, content, "
                "prompt_version, prompt_fingerprint, model) VALUES "
                "(%s, " + src_sql + ", 'x', 'x', 'x', 'x', 'x')",
                (kind,),
            )
            conn2.rollback()
            check(label, False)  # insert should NOT have succeeded
        except psycopg2.errors.CheckViolation:
            conn2.rollback()
            check(label, True)
        except Exception as exc:
            conn2.rollback()
            print("    (unexpected error: %r)" % exc)
            check(label, False)

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
