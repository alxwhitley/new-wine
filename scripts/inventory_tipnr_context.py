#!/usr/bin/env python3
"""Compile a canonical, zero-effect inventory for the pinned TIPNR artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Sequence

import parse_tipnr_context as tipnr
from biblical_context_tooling import canonical_json_bytes, canonical_sha256
from preview_biblical_context_tooling import write_new_preview


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_VERSION = "biblical_context_tipnr_inventory.v1"
EMBEDDING_MODEL = "text-embedding-3-small"
PRICE_PER_MILLION_INPUT_TOKENS_USD = Decimal("0.02")
PRICE_SOURCE = (
    "https://developers.openai.com/api/docs/models/text-embedding-3-small"
)
PRICE_REVIEWED_AT = "2026-09-01"
MINIMUM_LATER_APPROVAL_CEILING_USD = Decimal("0.01")


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_CEILING), "f")


def _rendering_projection(
    eligible: Sequence[dict[str, object]],
) -> dict[str, object]:
    rendered_bytes = sum(len(canonical_json_bytes(record)) for record in eligible)
    estimated_tokens = (rendered_bytes + 2) // 3
    estimated_cost = (
        Decimal(estimated_tokens)
        * PRICE_PER_MILLION_INPUT_TOKENS_USD
        / Decimal(1_000_000)
    )
    maximum_cost = max(
        estimated_cost * 2,
        MINIMUM_LATER_APPROVAL_CEILING_USD,
    )
    return {
        "canonical_utf8_bytes": rendered_bytes,
        "conservative_token_estimate": estimated_tokens,
        "embedding_request_count": len(eligible),
        "model": EMBEDDING_MODEL,
        "price_per_million_input_tokens_usd": _money(
            PRICE_PER_MILLION_INPUT_TOKENS_USD
        ),
        "price_source": PRICE_SOURCE,
        "price_reviewed_at": PRICE_REVIEWED_AT,
        "estimated_cost_usd": _money(estimated_cost),
        "maximum_later_approval_ceiling_usd": _money(maximum_cost),
    }


def build_tipnr_inventory(path: Path) -> dict[str, object]:
    """Account for every exact artifact record without external capabilities."""

    payload = tipnr.verify_tipnr_artifact(path)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise tipnr.TipnrSchemaError("artifact_encoding_invalid") from exc

    profiles = tipnr.scan_tipnr_records(text)
    outcomes = tipnr.classify_tipnr_text(
        text,
        artifact_revision=tipnr.TIPNR_ARTIFACT_REVISION,
    )
    if len(profiles) != len(outcomes):
        raise tipnr.TipnrSchemaError("inventory_record_count_mismatch")

    outcome_counts = Counter(
        {
            status: 0
            for status in (
                "eligible",
                "skipped",
                "malformed",
                "duplicate",
                "prohibited",
            )
        }
    )
    outcome_counts.update(outcome.status for outcome in outcomes)
    reason_counts = Counter(outcome.reason for outcome in outcomes)
    eligible_by_type = Counter(
        outcome.entity_type for outcome in outcomes if outcome.status == "eligible"
    )
    eligible = sorted(
        (
            outcome.projection
            for outcome in outcomes
            if outcome.status == "eligible" and outcome.projection is not None
        ),
        key=lambda record: (str(record["entity_id"]), str(record["entity_type"])),
    )
    record_outcomes = sorted(
        (
            {
                "ordinal": outcome.ordinal,
                "identity": outcome.identity,
                "status": outcome.status,
                "reason": outcome.reason,
                "entity_type": outcome.entity_type,
                "outcome_sha256": outcome.outcome_sha256,
            }
            for outcome in outcomes
        ),
        key=lambda record: (str(record["identity"]), int(record["ordinal"])),
    )

    inventory: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "artifact": {
            "revision": tipnr.TIPNR_ARTIFACT_REVISION,
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "database_write_authorized": False,
        "external_model_call_authorized": False,
        "structural_records": len(profiles),
        "entity_records": sum(
            profile.marker_class != "documentation" for profile in profiles
        ),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "eligible_by_type": dict(sorted(eligible_by_type.items())),
        "records": record_outcomes,
        "eligible_checksum": canonical_sha256(eligible),
        "rendering": _rendering_projection(eligible),
    }
    if sum(outcome_counts.values()) != len(profiles):
        raise tipnr.TipnrSchemaError("inventory_reconciliation_failed")
    inventory["payload_sha256"] = canonical_sha256(inventory)
    return inventory


def write_new_inventory(path: Path, payload: bytes) -> None:
    """Write only below ignored local/ with create-new collision semantics."""

    write_new_preview(path, payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compile the exact pinned TIPNR inventory without effects."
    )
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    inventory = build_tipnr_inventory(args.artifact)
    payload = canonical_json_bytes(inventory)
    if args.output is not None:
        write_new_inventory(args.output, payload)
    json.dump(inventory, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
