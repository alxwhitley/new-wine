#!/usr/bin/env python3
"""Build a canonical Phase 8 TIPNR pilot preview with zero external capability."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preview_biblical_context_tooling import write_new_preview
from tipnr_hidden_pilot_contract import build_pilot_packet, pilot_packet_report


ROOT = Path(__file__).resolve().parent.parent


def build_pilot_preview(root: Path, artifact_path: Path) -> dict[str, object]:
    """Return the exact pilot packet plus an explicit no-effect reconciliation."""

    packet = build_pilot_packet(root, artifact_path)
    report: dict[str, object] = {
        "schema_version": "biblical_context_tipnr_hidden_pilot_preview.v1",
        "database_write_authorized": False,
        "external_model_call_authorized": False,
        "packet": pilot_packet_report(packet),
        "counts": {
            "items": 20,
            "documents": 20,
            "chunks": 20,
            "policy_rows": 20,
            "embedding_requests": 20,
        },
        "maximum_spend_usd": packet.maximum_spend_usd,
        "sample_ids": list(packet.sample_ids),
        "reconciliation": {
            "attempted": 20,
            "stored": 0,
            "errored": 0,
            "skipped": 20,
            "reason": "preview_only",
        },
    }
    report["payload_sha256"] = canonical_sha256(report)
    return report


def write_new_pilot_preview(path: Path, payload: bytes) -> None:
    """Publish only under ignored local/ with collision-safe semantics."""

    write_new_preview(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview the exact balanced TIPNR pilot without external effects."
    )
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    payload = canonical_json_bytes(build_pilot_preview(ROOT, args.artifact))
    if args.output is not None:
        write_new_pilot_preview(args.output, payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
