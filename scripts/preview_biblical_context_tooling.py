#!/usr/bin/env python3
"""Build a canonical, zero-database-write Phase 2 fixture preview."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Sequence

from biblical_context_tooling import (
    canonical_json_bytes,
    canonical_sha256,
    compile_ingestion_policies,
    compile_registration_preview,
    load_approved_manifests,
)
from parse_openbible_context import parse_openbible_file, parse_openbible_place
from parse_tipnr_context import parse_tipnr_entity, parse_tipnr_file


ROOT = Path(__file__).resolve().parent.parent
_COUNT_KEYS = (
    "attempted",
    "previewed",
    "malformed",
    "duplicate",
    "skipped",
    "prohibited",
)
_PROHIBITED_COUNTS = {
    "attempted": 1,
    "previewed": 0,
    "malformed": 0,
    "duplicate": 0,
    "skipped": 0,
    "prohibited": 1,
}


class PreviewPathError(ValueError):
    """A requested preview path is outside the local artifact boundary."""


class PreviewCollisionError(FileExistsError):
    """An existing preview path is unsafe or contains different bytes."""


class PreviewContractError(ValueError):
    """Pinned single-item or aggregate preview evidence is inconsistent."""


def _tipnr_records(lines: list[str]) -> list[list[str]]:
    records: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if line.startswith("$=========="):
            if current is not None:
                records.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        records.append(current)
    return records


def _prohibited_result() -> dict[str, object]:
    return {
        "counts": dict(_PROHIBITED_COUNTS),
        "reason_counts": {"prohibited_in_v1": 1},
        "records": [],
        "checksum": canonical_sha256([]),
    }


def build_fixture_preview(root: Path) -> dict[str, object]:
    """Compile registrations and parse only the two approved pinned fixtures."""

    manifest_dir = root / "docs" / "ingestion" / "source_manifests"
    fixture_dir = root / "scripts" / "fixtures" / "biblical_context"
    manifests = load_approved_manifests(manifest_dir)
    registration_rows = compile_registration_preview(manifests)
    policies = compile_ingestion_policies(manifests)

    tipnr_meta = json.loads(
        (fixture_dir / "tipnr_minimal.meta.json").read_text(encoding="utf-8")
    )
    openbible_meta = json.loads(
        (fixture_dir / "openbible_ancient_minimal.meta.json").read_text(
            encoding="utf-8"
        )
    )
    tipnr_path = fixture_dir / "tipnr_minimal.txt"
    openbible_path = fixture_dir / "openbible_ancient_minimal.jsonl"

    tipnr_lines = tipnr_path.read_text(encoding="utf-8").splitlines()
    tipnr_single = parse_tipnr_entity(
        _tipnr_records(tipnr_lines)[0], artifact_revision=tipnr_meta["revision"]
    )
    openbible_first = json.loads(
        openbible_path.read_text(encoding="utf-8").splitlines()[0]
    )
    openbible_single = parse_openbible_place(
        openbible_first, artifact_revision=openbible_meta["revision"]
    )
    if tipnr_single.get("entity_id") != "H0175":
        raise PreviewContractError("tipnr_single_item_identity_changed")
    if openbible_single.get("place_id") != "aea17b7":
        raise PreviewContractError("openbible_single_item_identity_changed")

    datasets: dict[str, dict[str, object]] = {
        "stepbible_tipnr": parse_tipnr_file(
            tipnr_path, artifact_revision=tipnr_meta["revision"]
        ),
        "openbible_structured_data:bible_geocoding": parse_openbible_file(
            openbible_path, artifact_revision=openbible_meta["revision"]
        ),
    }
    for dataset_key, policy in policies.items():
        if policy["ingestion_policy"] == "prohibited_in_v1":
            datasets[dataset_key] = _prohibited_result()

    totals = {key: 0 for key in _COUNT_KEYS}
    for result in datasets.values():
        counts = result["counts"]
        if not isinstance(counts, dict) or set(counts) != set(_COUNT_KEYS):
            raise PreviewContractError("dataset_count_contract_changed")
        for key in _COUNT_KEYS:
            totals[key] += int(counts[key])

    preview: dict[str, object] = {
        "schema_version": "biblical_context_phase2_preview.v1",
        "database_write_authorized": False,
        "registration_rows": list(registration_rows),
        "ingestion_policies": policies,
        "single_item_verification": {
            "stepbible_tipnr": "passed",
            "openbible_geocoding": "passed",
        },
        "datasets": dict(sorted(datasets.items())),
        "totals": totals,
    }
    preview["payload_sha256"] = canonical_sha256(preview)
    return preview


def write_new_preview(path: Path, payload: bytes) -> None:
    """Publish local preview bytes without replacing different or unsafe data."""

    local_root = (ROOT / "local").resolve()
    target = path if path.is_absolute() else (Path.cwd() / path)
    resolved_parent = target.parent.resolve()
    resolved_target = resolved_parent / target.name
    if not resolved_target.is_relative_to(local_root):
        raise PreviewPathError("outside_local")
    resolved_parent.mkdir(parents=True, exist_ok=True)

    try:
        descriptor = os.open(
            resolved_target,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        details = os.lstat(resolved_target)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise PreviewCollisionError("not_regular")
        if resolved_target.read_bytes() != payload:
            raise PreviewCollisionError("different_bytes")
        return

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        resolved_target.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview pinned biblical-context fixtures without any database write."
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="compile only the pinned Phase 2 fixtures",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="optionally create an immutable JSON preview under local/",
    )
    args = parser.parse_args(argv)
    if not args.fixtures:
        parser.error("--fixtures is required; live discovery is not supported")

    payload = canonical_json_bytes(build_fixture_preview(ROOT))
    if args.output is not None:
        write_new_preview(args.output, payload)
    sys.stdout.buffer.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
