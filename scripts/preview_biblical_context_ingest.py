#!/usr/bin/env python3
"""Preview the Phase 6 Aaron proof without database or model capability."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from biblical_context_ingest_contract import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MAX_SPEND_USD,
    build_aaron_projection,
    projection_report,
)
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preview_biblical_context_tooling import PreviewPathError, write_new_preview


ROOT = Path(__file__).resolve().parent.parent


def build_preview(root: Path) -> dict[str, object]:
    """Return the canonical zero-effect proof preview."""

    proof = build_aaron_projection(root)
    report: dict[str, object] = {
        "schema_version": "biblical_context_phase6_ingest_preview.v1",
        "database_write_authorized": False,
        "external_model_call_authorized": False,
        "proof": projection_report(proof),
        "counts": {
            "sources": 1,
            "aliases": 1,
            "documents": 1,
            "chunks": 1,
            "policy_rows": 1,
        },
        "embedding": {
            "model": EMBEDDING_MODEL,
            "dimensions": EMBEDDING_DIMENSIONS,
            "request_count": 1,
            "maximum_spend_usd": MAX_SPEND_USD,
            "input_utf8_bytes": len(proof.text.encode("utf-8")),
        },
        "reconciliation": {
            "attempted": 1,
            "stored": 0,
            "errored": 0,
            "skipped": 1,
            "reason": "preview_only",
        },
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview the pinned Phase 6 Aaron ingestion proof."
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="use only the pinned Phase 2 fixture",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optionally create an immutable report under local/",
    )
    args = parser.parse_args(argv)
    if not args.fixtures:
        parser.error("--fixtures is required; live discovery is not supported")

    payload = canonical_json_bytes(build_preview(ROOT))
    if args.output is not None:
        write_new_preview(args.output, payload)
    sys.stdout.write(payload.decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
