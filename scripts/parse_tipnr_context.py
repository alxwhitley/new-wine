#!/usr/bin/env python3
"""Parse the approved TIPNR Phase 2 people/place projection without writes."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Sequence

from biblical_context_tooling import canonical_sha256


_MARKER_RE = re.compile(r"^\$=+\s*(PERSON\(s\)|PERSONS?|PLACE|OTHER)\s*$")
_STRONG_RE = re.compile(r"^[HG]\d{4}[A-Z]?$", re.IGNORECASE)
_OSIS_RE = re.compile(r"^(?:[1-4])?[A-Za-z]{2,5}\.\d+\.\d+[a-z]?$", re.IGNORECASE)
_DIRECTIVES = ("@Briefest=", "@Brief=", "@Short=", "@Article=")
_SIGNIFICANCE = frozenset(
    {
        "Named",
        "Name combined",
        "Spelled",
        "Spelled combined",
        "Aramaic",
        "Aramaic combined",
        "Greek",
        "LXX addition",
        "(same form as previous)",
        "(same ref[s] with Alt Tags)",
        "(same ref[s] with Variant)",
        "Form (verb)",
        "Form (adjective)",
        "Mentioned",
    }
)
_ZERO_COUNTS = {
    "attempted": 0,
    "previewed": 0,
    "malformed": 0,
    "duplicate": 0,
    "skipped": 0,
    "prohibited": 0,
}


class TipnrSchemaError(ValueError):
    """The pinned TIPNR grammar changed or an unknown field appeared."""


class TipnrItemError(ValueError):
    """One structurally recognized TIPNR entity is malformed."""


def _entity_type(marker: str) -> str:
    match = _MARKER_RE.fullmatch(marker.strip())
    if match is None:
        raise TipnrSchemaError("unknown_entity_marker")
    value = match.group(1).upper()
    if value.startswith("PERSON"):
        return "person"
    if value == "PLACE":
        return "place"
    return "other"


def _parse_references(value: str) -> list[str]:
    if re.search(r"\bff\b|ff(?:[.;,]|$)", value, re.IGNORECASE):
        raise TipnrItemError("abbreviated_reference")
    references = [item.strip() for item in value.split(";") if item.strip()]
    if not references or any(_OSIS_RE.fullmatch(item) is None for item in references):
        raise TipnrItemError("osis_reference_invalid")
    return references


def _parse_form(line: str) -> dict[str, object] | None:
    columns = line.split("\t")
    significance = columns[0].removeprefix("–").strip() if columns else ""
    if significance == "Total":
        if len(columns) not in {4, 5}:
            raise TipnrSchemaError("row_shape_changed")
        return None
    if len(columns) != 6:
        raise TipnrSchemaError("row_shape_changed")
    if significance not in _SIGNIFICANCE:
        raise TipnrSchemaError("unknown_significance")

    identity = columns[2]
    if identity.count("«") != 1 or identity.count("=") != 1:
        raise TipnrItemError("form_identity_invalid")
    dstrong, remainder = identity.split("«", 1)
    estrong, source_script_form = remainder.split("=", 1)
    if (
        _STRONG_RE.fullmatch(dstrong) is None
        or _STRONG_RE.fullmatch(estrong) is None
        or not source_script_form.strip()
    ):
        raise TipnrItemError("form_identity_invalid")

    return {
        "dstrong": dstrong,
        "estrong": estrong,
        "source_script_form": source_script_form,
        "osis_references": _parse_references(columns[5]),
    }


def parse_tipnr_entity(
    lines: Sequence[str], *, artifact_revision: str
) -> dict[str, object]:
    """Parse one marker-delimited TIPNR record into approved fields only."""

    if len(lines) < 3:
        raise TipnrItemError("entity_record_incomplete")
    entity_type = _entity_type(lines[0])
    primary_columns = lines[1].split("\t")
    if len(primary_columns) != 9:
        raise TipnrSchemaError("row_shape_changed")

    entity_identity = primary_columns[0]
    if "=" not in entity_identity:
        raise TipnrItemError("entity_identity_invalid")
    entity_id = entity_identity.rsplit("=", 1)[1]
    if _STRONG_RE.fullmatch(entity_id) is None:
        raise TipnrItemError("entity_identity_invalid")

    forms: list[dict[str, object]] = []
    for line in lines[2:]:
        if not line.strip():
            continue
        if line.startswith(_DIRECTIVES):
            continue
        if line.startswith("@"):
            raise TipnrSchemaError("unknown_directive")
        if line.startswith("–"):
            form = _parse_form(line)
            if form is not None:
                forms.append(form)
            continue
        raise TipnrSchemaError("row_shape_changed")
    if not forms:
        raise TipnrItemError("entity_forms_missing")

    record: dict[str, object] = {
        "dataset_id": "stepbible_tipnr",
        "artifact_revision": artifact_revision,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "original_language_forms": forms,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def _split_records(lines: Sequence[str]) -> list[list[str]]:
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
    if not records:
        raise TipnrSchemaError("entity_markers_missing")
    return records


def parse_tipnr_file(path: Path, *, artifact_revision: str) -> dict[str, object]:
    """Parse an explicit TIPNR fixture and reconcile every entity outcome."""

    counts = dict(_ZERO_COUNTS)
    reasons: Counter[str] = Counter()
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for lines in _split_records(path.read_text(encoding="utf-8").splitlines()):
        counts["attempted"] += 1
        try:
            record = parse_tipnr_entity(lines, artifact_revision=artifact_revision)
        except TipnrItemError as exc:
            counts["malformed"] += 1
            reasons[str(exc)] += 1
            continue

        entity_id = str(record["entity_id"])
        if entity_id in seen_ids:
            counts["duplicate"] += 1
            reasons["duplicate_entity_id"] += 1
            continue
        seen_ids.add(entity_id)

        if record["entity_type"] == "other":
            counts["skipped"] += 1
            reasons["not_v1_entity_type"] += 1
            continue
        records.append(record)
        counts["previewed"] += 1

    return {
        "counts": counts,
        "reason_counts": dict(sorted(reasons.items())),
        "records": records,
        "checksum": canonical_sha256(records),
    }
