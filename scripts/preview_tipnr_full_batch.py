#!/usr/bin/env python3
"""Zero-effect preview of the complete remaining TIPNR batch operation.

Imports no network, database, OpenAI, or write dependency. Accepts only the
pinned artifact and an optional ignored-local output path. There is no
`--apply`, selection, limit, offset, URL, or entity override.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preview_biblical_context_tooling import write_new_preview
from tipnr_full_batch_contract import (
    BATCH_COUNT,
    EXPECTED_ROW_TOTAL,
    REMAINING_COUNT,
    build_full_batch_packet,
    full_batch_summary,
)


ROOT = Path(__file__).resolve().parent.parent

# Exactly what leaves this machine for each embedding request, and what never
# does. Every retained category is an approved Phase 0/2 structural field.
DISCLOSED_PAYLOAD_CATEGORIES = (
    "dataset_name",
    "artifact_revision",
    "entity_id",
    "entity_type",
    "dstrong_identifier",
    "estrong_identifier",
    "source_script_form",
    "osis_references",
)
EXCLUDED_PAYLOAD_CATEGORIES = (
    "generated_prose",
    "translated_name_comparisons",
    "ambiguity_prose",
    "relationships_and_relatives",
    "summaries",
    "map_urls",
    "english_gloss_labels",
)


def build_full_batch_preview(root: Path, artifact_path: Path) -> dict[str, object]:
    """Return the frozen operation plus an explicit zero-effect reconciliation."""

    packet = build_full_batch_packet(root, artifact_path)
    summary = full_batch_summary(packet)
    samples = {
        item.entity_id: {
            "entity_type": item.entity_type,
            "document_id": item.document["id"],
            "chunk_id": item.chunk["id"],
            "rendered_sha256": item.rendered_sha256,
            "osis_reference_count": len(item.document["bible_references"]),
            "rendered_bytes": len(item.text.encode("utf-8")),
            "text": item.text,
        }
        for item in packet.items
        if item.entity_id in set(packet.sample_ids)
    }
    report: dict[str, object] = {
        "schema_version": "biblical_context_tipnr_full_batch_preview.v1",
        "database_write_authorized": False,
        "external_model_call_authorized": False,
        "deployment_authorized": False,
        "visibility_change_authorized": False,
        "feature_enablement_authorized": False,
        "packet": summary,
        "counts": {
            "items": REMAINING_COUNT,
            "documents": REMAINING_COUNT,
            "chunks": REMAINING_COUNT,
            "policy_rows": REMAINING_COUNT,
            "embedding_requests": REMAINING_COUNT,
            "transactions": BATCH_COUNT,
            "rows_total": EXPECTED_ROW_TOTAL,
        },
        "payload_categories": {
            "disclosed": list(DISCLOSED_PAYLOAD_CATEGORIES),
            "excluded": list(EXCLUDED_PAYLOAD_CATEGORIES),
        },
        "samples": samples,
        "reconciliation": {
            "attempted": REMAINING_COUNT,
            "stored": 0,
            "errored": 0,
            "skipped": REMAINING_COUNT,
            "reason": "preview_only",
        },
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def _resolve_artifact(value: Path | None) -> Path:
    if value is not None:
        return value
    env = os.environ.get("TIPNR_TEST_ARTIFACT")
    if not env:
        raise SystemExit(
            "the pinned artifact is required: pass --artifact or set TIPNR_TEST_ARTIFACT"
        )
    return Path(env)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview the complete remaining TIPNR batch without any effect."
    )
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = canonical_json_bytes(
        build_full_batch_preview(ROOT, _resolve_artifact(args.artifact))
    )
    if args.output is not None:
        write_new_preview(args.output, payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
