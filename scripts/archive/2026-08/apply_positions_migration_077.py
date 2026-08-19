#!/usr/bin/env python3
"""
apply_positions_migration_077.py -- Apply and verify migration 077 (position
versioning + question-time lookup record shape: lineage_id, version,
is_current, supersedes_id, topic_key, requested_teacher_id + the partial
unique lineage-identity index).

Idempotent: detects whether lineage_id already exists and skips the apply if
so. Schema-level + backfill-correctness verification on a FRESH connection
(migration 049 landmine). Also behaviorally proves the partial unique index
collapses NULL requested_teacher_id to the sentinel (two current corpus
positions for the same topic collide).

Usage:
  python3 scripts/apply_positions_migration_077.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(ROOT / "scripts"))

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


def _has_col(cur, col):
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'positions' AND column_name = %s",
        (col,),
    )
    return cur.fetchone() is not None


def main():
    print("\nPosition versioning -- migration 077 apply + verify")
    print("=" * 60)

    conn = get_db_conn()
    cur = conn.cursor()

    if _has_col(cur, "lineage_id"):
        print("Column lineage_id already exists -- skipping apply")
    else:
        migration_sql = (ROOT / "migrations" / "077_positions_versioning.sql").read_text()
        cur.execute(migration_sql)
        conn.commit()
        print("Migration applied OK")
    cur.close()
    conn.close()

    # -- Fresh connection ------------------------------------------------------
    conn2 = get_db_conn()
    cur2 = conn2.cursor()

    for col in ("lineage_id", "version", "is_current", "supersedes_id",
                "topic_key", "requested_teacher_id"):
        check("column %s present" % col, _has_col(cur2, col))

    cur2.execute(
        "SELECT column_name, is_nullable FROM information_schema.columns "
        "WHERE table_name = 'positions' AND column_name IN "
        "('lineage_id','version','is_current','topic_key')"
    )
    nullable = {r[0]: r[1] for r in cur2.fetchall()}
    check("lineage_id NOT NULL", nullable.get("lineage_id") == "NO")
    check("version NOT NULL", nullable.get("version") == "NO")
    check("is_current NOT NULL", nullable.get("is_current") == "NO")
    check("topic_key NOT NULL", nullable.get("topic_key") == "NO")

    # -- Backfill correctness on the pre-existing rows -------------------------
    import positions as pos

    cur2.execute(
        "SELECT id::text, lineage_id::text, version, is_current, topic, topic_key, "
        "source_id::text, requested_teacher_id::text, kind FROM positions "
        "ORDER BY created_at"
    )
    rows = cur2.fetchall()
    check("pre-existing rows still present (>=3)", len(rows) >= 3)
    all_lineage_self = all(r[0] == r[1] for r in rows)
    check("every backfilled row: lineage_id = id (own v1 lineage)", all_lineage_self)
    check("every backfilled row: version = 1", all(r[2] == 1 for r in rows))
    check("every backfilled row: is_current = true", all(r[3] is True for r in rows))
    check(
        "every backfilled row: topic_key = normalize_topic_key(topic)",
        all(r[5] == pos.normalize_topic_key(r[4]) for r in rows),
    )
    check(
        "every teacher row: requested_teacher_id = source_id",
        all(r[7] == r[6] for r in rows if r[8] == "teacher"),
    )

    # -- Indexes present -------------------------------------------------------
    cur2.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'positions'")
    idx = {r[0] for r in cur2.fetchall()}
    check("positions_current_lineage_idx present", "positions_current_lineage_idx" in idx)
    check("positions_lineage_id_idx present", "positions_lineage_id_idx" in idx)

    # -- Behavioral: two CURRENT corpus positions for one topic collide -------
    # (proves the COALESCE-sentinel makes NULL requested_teacher_id collide,
    # not both-allowed). Both inserts rolled back -- proof only.
    import psycopg2

    ins = (
        "INSERT INTO positions (kind, source_id, topic, content, status, "
        "prompt_version, prompt_fingerprint, model, lineage_id, version, "
        "is_current, topic_key, requested_teacher_id) VALUES "
        "('corpus', NULL, 'zzz proof topic 077', 'x', 'draft', 'x', 'x', 'x', "
        "gen_random_uuid(), 1, true, 'zzz proof topic 077', NULL)"
    )
    try:
        cur2.execute(ins)  # first current corpus position -- OK
        cur2.execute(ins)  # second, same topic_key, both current -- must collide
        conn2.rollback()
        check("two current corpus positions on one topic collide", False)
    except psycopg2.errors.UniqueViolation:
        conn2.rollback()
        check("two current corpus positions on one topic collide", True)
    except Exception as exc:
        conn2.rollback()
        print("    (unexpected error: %r)" % exc)
        check("two current corpus positions on one topic collide", False)

    cur2.close()
    conn2.close()

    print()
    print("%d/%d checks passed" % (_pass, _pass + _fail))
    if _fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
