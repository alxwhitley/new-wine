#!/usr/bin/env python3
"""Retire the stale Phase 6 fixture Aaron policy by demoting it, never deleting it.

Phase 6 ingested Aaron (`H0175`) from the reduced parser fixture, storing 4 of
his 352 OSIS references. The pinned artifact's Aaron projection is ingested
separately as an ordinary batch item. This module retires the superseded
fixture row the only way migration 097 permits: flipping `is_current` from true
to false with every other column unchanged.

Deletion is structurally impossible and is not attempted. The policy table's
`append_only` trigger raises on DELETE, and its `chunk_id` foreign key is
ON DELETE RESTRICT, so the chunk and document cannot be removed either. After
demotion the fixture document remains as an inert row carrying no current
policy, which keeps it out of every policy-gated path.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preview_biblical_context_tooling import write_new_preview
from tipnr_full_batch_contract import build_full_batch_packet


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIRECTORY = ROOT / "local" / "2026-09"


class FixtureDemotionError(RuntimeError):
    """The stale fixture policy is not in the exact expected demotable state."""


def stale_fixture_identity() -> dict[str, str]:
    """Return the exact document, chunk, and record identity being retired."""

    from biblical_context_ingest_contract import build_aaron_projection

    proof = build_aaron_projection(ROOT)
    return {
        "document_id": str(proof.document["id"]),
        "chunk_id": str(proof.chunks[0]["id"]),
        "record_sha256": str(proof.record["record_sha256"]),
        "osis_reference_count": str(len(proof.document["bible_references"])),
    }


def _current_policy(cursor, chunk_id: str):
    cursor.execute(
        """/* demote:current_policy */
        SELECT id, chunk_id, policy_class, is_current
        FROM source_passage_policy_versions
        WHERE chunk_id = %s::uuid AND is_current""",
        (chunk_id,),
    )
    return cursor.fetchall()


def demote_stale_policy(
    connection_factory: Callable[[str], object],
    *,
    approved: bool,
    commit: bool = False,
) -> dict[str, object]:
    """Demote exactly one current fixture policy row inside one transaction."""

    if not approved:
        raise FixtureDemotionError("demotion_not_authorized")

    identity = stale_fixture_identity()
    chunk_id = identity["chunk_id"]

    connection = connection_factory("write")
    connection.autocommit = False
    committed = False
    rolled_back = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")

            before = _current_policy(cursor, chunk_id)
            if len(before) != 1:
                raise FixtureDemotionError("stale_policy_not_uniquely_current")
            policy_id = str(before[0][0])
            if before[0][2] != "general_context":
                raise FixtureDemotionError("stale_policy_class_unexpected")

            cursor.execute(
                """/* demote:set_not_current */
                UPDATE source_passage_policy_versions
                SET is_current = false
                WHERE id = %s::uuid AND chunk_id = %s::uuid AND is_current""",
                (policy_id, chunk_id),
            )
            if cursor.rowcount != 1:
                raise FixtureDemotionError("stale_policy_update_row_count")

            after = _current_policy(cursor, chunk_id)
            if after:
                raise FixtureDemotionError("stale_policy_still_current")

            cursor.execute(
                """/* demote:history_preserved */
                SELECT count(*) FROM source_passage_policy_versions
                WHERE chunk_id = %s::uuid""",
                (chunk_id,),
            )
            if int(cursor.fetchone()[0]) != 1:
                raise FixtureDemotionError("stale_policy_history_changed")

        if commit:
            connection.commit()
            committed = True
        else:
            connection.rollback()
            rolled_back = True
    except Exception:
        try:
            connection.rollback()
            rolled_back = True
        finally:
            connection.close()
        raise
    connection.close()

    report = {
        "schema_version": "biblical_context_stale_fixture_demotion.v1",
        "status": "committed" if committed else "rolled_back",
        "operation": "demote_is_current_true_to_false",
        "deletion_attempted": False,
        "identity": identity,
        "policy_id": policy_id,
        "rows_updated": 1,
        "history_rows_preserved": 1,
        "transactions": {
            "opened": 1,
            "committed": 1 if committed else 0,
            "rolled_back": 1 if rolled_back else 0,
        },
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def _load_write_factory():
    sys.path.insert(0, str(ROOT / "backend"))
    import os

    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / "app" / ".env", override=True)
    import psycopg2

    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise FixtureDemotionError("write_url_missing")

    def connection_factory(mode: str):
        if mode != "write":
            raise ValueError("demotion_connection_mode_invalid")
        return psycopg2.connect(url)

    return connection_factory


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demote the stale Phase 6 fixture Aaron policy (never delete)."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--approval-file", required=True, type=Path)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)

    from apply_tipnr_full_batch import validate_approval

    packet = build_full_batch_packet(ROOT, args.artifact)
    approval = validate_approval(args.approval_file, packet, date.today())
    if approval.get("fixture_policy_demotion_authorized") is not True:
        raise FixtureDemotionError("demotion_not_authorized")
    if approval.get("fixture_policy_chunk_id") != stale_fixture_identity()["chunk_id"]:
        raise FixtureDemotionError("demotion_chunk_identity_mismatch")

    report = demote_stale_policy(
        _load_write_factory(), approved=True, commit=args.commit
    )
    payload = canonical_json_bytes(report)
    write_new_preview(
        EVIDENCE_DIRECTORY / f"stale_fixture_demotion_{report['payload_sha256']}.json",
        payload,
    )
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
