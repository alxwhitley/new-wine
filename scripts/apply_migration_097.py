#!/usr/bin/env python3
"""Validate, apply, or verify migration 097 under explicit safety gates.

``--dry-run`` is entirely local and imports no database client. ``--apply`` is
the separately approved production-write path. ``--verify`` uses only the
dedicated read-only analysis connection and must run on a fresh connection.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "migrations" / "097_source_passage_policy.sql"
TABLE = "source_passage_policy_versions"


class MigrationValidationError(ValueError):
    """The migration cannot be safely handed to PostgreSQL."""


def _split_statements(sql: str) -> tuple[str, ...]:
    """Split SQL at top-level semicolons while respecting strings and $$ blocks."""

    statements: list[str] = []
    current: list[str] = []
    index = 0
    quote: str | None = None
    dollar_quoted = False
    line_comment = False
    while index < len(sql):
        char = sql[index]
        pair = sql[index : index + 2]
        if line_comment:
            current.append(char)
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if quote is None and not dollar_quoted and pair == "--":
            line_comment = True
            current.extend(pair)
            index += 2
            continue
        if quote is None and pair == "$$":
            dollar_quoted = not dollar_quoted
            current.extend(pair)
            index += 2
            continue
        if not dollar_quoted and char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                if index + 1 < len(sql) and sql[index + 1] == char:
                    current.extend((char, char))
                    index += 2
                    continue
                quote = None
        if char == ";" and quote is None and not dollar_quoted:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1

    if quote is not None or dollar_quoted:
        raise MigrationValidationError("unterminated_quoted_section")
    if "".join(current).strip():
        raise MigrationValidationError("missing_final_semicolon")
    return tuple(statements)


def validate_migration(sql: str) -> tuple[str, ...]:
    statements = _split_statements(sql)
    for line in sql.splitlines():
        marker = line.find("--")
        if marker >= 0 and ";" in line[marker + 2 :]:
            raise MigrationValidationError("semicolon_in_line_comment")
    normalized = " ".join(sql.lower().split())
    required = (
        "create table source_passage_policy_versions",
        "references chunks (id) on delete restrict",
        "policy_class in ('general_context', 'orthodox_viewpoint', 'protected_spirit_filled', 'mixed', 'uncertain')",
        "classifier_kind in ('deterministic', 'model')",
        "classifier_kind = 'deterministic' and model is null and prompt_fingerprint is null",
        "classifier_kind = 'model' and model is not null and btrim(model) <> '' and prompt_fingerprint is not null and btrim(prompt_fingerprint) <> ''",
        "create unique index source_passage_policy_versions_one_current_idx",
        "where is_current",
        "and old.is_current and not new.is_current",
        "raise exception 'source_passage_policy_versions history rows are append-only'",
        "before update or delete on source_passage_policy_versions",
        "enable row level security",
        "revoke all on source_passage_policy_versions from anon, authenticated",
        "revoke all on source_passage_policy_versions from service_role",
        "grant select, insert, update on source_passage_policy_versions to service_role",
        "grant select on source_passage_policy_versions to newwine_readonly_analysis",
    )
    missing = [fragment for fragment in required if fragment not in normalized]
    if missing:
        raise MigrationValidationError(f"missing_contract={missing[0]}")
    if not statements:
        raise MigrationValidationError("no_sql_statements")
    return statements


def dry_run() -> int:
    sql = MIGRATION.read_text(encoding="utf-8")
    statements = validate_migration(sql)
    print(f"migration={MIGRATION.name}")
    print("status=valid")
    print("database_connection=none")
    print(f"statement_count={len(statements)}")
    print(f"sha256={hashlib.sha256(sql.encode('utf-8')).hexdigest()}")
    print(
        "apply_command=cd /Users/alexwhitley/newwine && "
        "python3.12 scripts/apply_migration_097.py --apply"
    )
    return 0


def database_environment(mode: str) -> tuple[Path, str]:
    """Return the only environment file and URL key allowed for a DB mode."""

    if mode == "apply":
        return ROOT / "backend" / "app" / ".env", "SUPABASE_DB_URL"
    if mode == "verify":
        return (
            ROOT / "backend" / "app" / ".env.readonly-analysis",
            "READONLY_ANALYSIS_DB_URL",
        )
    raise ValueError("database_mode_invalid")


def _load_database_dependencies(mode: str) -> tuple[object, str]:
    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv

    environment_path, url_key = database_environment(mode)
    load_dotenv(environment_path, override=True)
    import psycopg2

    database_url = os.environ.get(url_key)
    if not database_url:
        raise RuntimeError(f"{url_key} is not set")
    return psycopg2, database_url


def apply_migration() -> int:
    psycopg2, database_url = _load_database_dependencies("apply")
    sql = MIGRATION.read_text(encoding="utf-8")
    validate_migration(sql)
    connection = psycopg2.connect(database_url)
    connection.autocommit = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.source_passage_policy_versions')")
            if cursor.fetchone()[0] is not None:
                raise RuntimeError("migration_097_already_present_refusing_apply")
            cursor.execute(sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print("migration=097_source_passage_policy.sql")
    print("status=applied")
    return 0


def verify_migration() -> int:
    psycopg2, database_url = _load_database_dependencies("verify")
    connection = psycopg2.connect(database_url)
    connection.set_session(readonly=True, autocommit=True)
    checks: list[tuple[str, bool]] = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]
            checks.append(("readonly_role", role == "newwine_readonly_analysis"))
            cursor.execute("SELECT to_regclass(%s)", (f"public.{TABLE}",))
            table_exists = cursor.fetchone()[0] is not None
            checks.append(("table_exists", table_exists))
            if not table_exists:
                for label, passed in checks:
                    print(f"check={label} status={'pass' if passed else 'fail'}")
                return 1
            cursor.execute(
                "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass",
                (f"public.{TABLE}",),
            )
            checks.append(("rls_enabled", cursor.fetchone()[0] is True))
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass",
                (f"public.{TABLE}",),
            )
            constraint_names = {row[0] for row in cursor.fetchall()}
            expected_constraints = {
                f"{TABLE}_pkey",
                f"{TABLE}_chunk_id_fkey",
                f"{TABLE}_policy_class_check",
                f"{TABLE}_classifier_kind_check",
                f"{TABLE}_classifier_metadata_check",
                f"{TABLE}_rule_version_check",
                f"{TABLE}_reason_codes_check",
                f"{TABLE}_protected_topics_check",
                f"{TABLE}_issue_key_check",
                f"{TABLE}_viewpoint_key_check",
                f"{TABLE}_policy_metadata_check",
            }
            checks.append(
                ("closed_set_and_coupling_constraints", expected_constraints <= constraint_names)
            )
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND indexname = 'source_passage_policy_versions_one_current_idx'"
            )
            index_row = cursor.fetchone()
            index_definition = index_row[0].lower() if index_row else ""
            checks.append(
                (
                    "one_current_partial_unique_index",
                    "create unique index" in index_definition
                    and "where is_current" in index_definition,
                )
            )
            cursor.execute(
                "SELECT count(*) FROM pg_trigger WHERE tgrelid = %s::regclass "
                "AND tgname = 'source_passage_policy_versions_append_only' "
                "AND NOT tgisinternal",
                (f"public.{TABLE}",),
            )
            checks.append(("append_only_trigger", cursor.fetchone()[0] == 1))
            all_table_privileges = [
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
                "REFERENCES",
                "TRIGGER",
            ]
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM unnest(%s::text[]) AS roles(role_name) "
                "CROSS JOIN unnest(%s::text[]) AS privileges(privilege_name) "
                "WHERE has_table_privilege(role_name::name, %s, privilege_name)"
                ")",
                (["anon", "authenticated"], all_table_privileges, f"public.{TABLE}"),
            )
            checks.append(("no_anon_or_authenticated_grants", cursor.fetchone()[0] is False))
            cursor.execute(
                "SELECT EXISTS ("
                "SELECT 1 FROM unnest(%s::text[]) AS privileges(privilege_name) "
                "WHERE has_table_privilege('service_role', %s, privilege_name)"
                ")",
                (["DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"], f"public.{TABLE}"),
            )
            checks.append(("service_role_cannot_delete_or_truncate", cursor.fetchone()[0] is False))
            cursor.execute(
                f"SELECT policy_class, count(*) FROM {TABLE} "
                "GROUP BY policy_class ORDER BY policy_class"
            )
            rows = cursor.fetchall()
    finally:
        connection.close()
    print("migration=097_source_passage_policy.sql")
    print("database_connection=newwine_readonly_analysis")
    for label, passed in checks:
        print(f"check={label} status={'pass' if passed else 'fail'}")
    print(f"classification_counts={rows}")
    passed = all(result for _label, result in checks)
    print(f"status={'verified' if passed else 'failed'}")
    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migration 097 safety-gated runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if args.apply:
        return apply_migration()
    return verify_migration()


if __name__ == "__main__":
    raise SystemExit(main())
