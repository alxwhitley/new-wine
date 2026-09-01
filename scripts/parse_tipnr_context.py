#!/usr/bin/env python3
"""Parse the approved TIPNR Phase 2 people/place projection without writes."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from biblical_context_tooling import canonical_sha256


TIPNR_ARTIFACT_REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"
TIPNR_ARTIFACT_BYTES = 7_916_469
TIPNR_ARTIFACT_SHA256 = (
    "69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e"
)

_MARKER_RE = re.compile(r"^\$=+\s*(PERSON\(s\)|PERSONS?|PLACE|OTHER)\s*$")
_STRONG_RE = re.compile(r"^[HG]\d{4}[A-Z]?$", re.IGNORECASE)
_OSIS_RE = re.compile(r"^(?:[1-4])?[A-Za-z]{2,5}\.\d+\.\d+[a-z]?$", re.IGNORECASE)
_DIRECTIVES = ("@Briefest=", "@Brief=", "@Short=", "@Article=")
_STRUCTURAL_DIRECTIVE_KEYS = frozenset(
    {"@Briefest", "@Brief", "@Short", "@Article", "@Ambiguity"}
)
_MARKER_SHAPES = {
    "$==========PERSON(s)": ("person_no_space", "documentation"),
    "$==========PLACE": ("place_no_space", "documentation"),
    "$==========OTHER": ("other_no_space", "documentation"),
    "$========== PERSON(s)": ("person_spaced", "person"),
    "$========== PLACE": ("place_spaced", "place"),
    "$========== OTHER": ("other_spaced", "other"),
    "$========== EXCLUDED OTHER": ("excluded_other_spaced", "excluded_other"),
    "$========== PERSON+PLACE": ("person_place_spaced", "person+place"),
}
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
_ENTITY_FORM_SHAPES = frozenset(
    {(value, 5) for value in (*_SIGNIFICANCE, "Group")} | {("Total", 5)}
)
_DOCUMENTATION_MARKERS = {
    1: "person_no_space",
    2: "place_no_space",
    3: "other_no_space",
}
_ENTITY_PRIMARY_WIDTHS = {
    "person": 9,
    "place": 8,
    "other": 9,
    "excluded_other": 9,
    "person+place": 8,
}
_NON_FORM_PROFILE_SHA256 = {
    792: "ed9a433402f87429c3a7ebebf4577bff9be457c950b5ded9937ff1d010951476",
    869: "740777776f0137825d2a8c835b42d8b934e4d9da77bb39227887b6d784765cf3",
    1471: "f66a959397aa3de422ff44c10d9c55788ab51a10ce72aa9c0f73044f62f38466",
    1472: "33fa58b33ace2262c7be732be4b2ba536efa873f67058402db941c1160113720",
    4250: "3e4a8d3d49976ec84fb780ac6e491620f754bcd479759c84c1c6d5b19c727795",
    4262: "ba36ebfc8060084783dd313fc0808c324fa47e9ec57b42523d9fbc931a9064ee",
}
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


@dataclass(frozen=True)
class TipnrStructuralRecord:
    """A source-text-free structural profile for one marker-delimited record."""

    ordinal: int
    marker_shape: str
    marker_class: str
    primary_width: int
    form_shapes: tuple[tuple[str, int], ...]
    directive_keys: tuple[str, ...]
    line_shape_codes: tuple[str, ...]


def verify_tipnr_artifact(path: Path) -> bytes:
    """Return only the exact approved upstream artifact bytes."""

    payload = path.read_bytes()
    if len(payload) != TIPNR_ARTIFACT_BYTES:
        raise TipnrSchemaError("artifact_size_mismatch")
    if hashlib.sha256(payload).hexdigest() != TIPNR_ARTIFACT_SHA256:
        raise TipnrSchemaError("artifact_sha256_mismatch")
    return payload


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


def _meaningful_columns(line: str) -> list[str]:
    columns = line.split("\t")
    while columns and not columns[-1]:
        columns.pop()
    return columns


def _parse_form(line: str) -> dict[str, object] | None:
    columns = _meaningful_columns(line)
    significance = columns[0].removeprefix("–").strip() if columns else ""
    if significance == "Total":
        if len(columns) != 5:
            raise TipnrSchemaError("row_shape_changed")
        return None
    if len(columns) != 5:
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
        "osis_references": _parse_references(columns[4]),
    }


def parse_tipnr_entity(
    lines: Sequence[str], *, artifact_revision: str
) -> dict[str, object]:
    """Parse one marker-delimited TIPNR record into approved fields only."""

    if len(lines) < 3:
        raise TipnrItemError("entity_record_incomplete")
    entity_type = _entity_type(lines[0])
    primary_columns = _meaningful_columns(lines[1])
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


def split_tipnr_records(text: str) -> tuple[tuple[str, ...], ...]:
    """Split every marker-delimited record without normalizing its contents."""

    records: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
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
    return tuple(tuple(record) for record in records)


def _split_records(lines: Sequence[str]) -> list[list[str]]:
    """Compatibility wrapper for the Phase 2 list-based parser API."""

    records = split_tipnr_records("\n".join(lines))
    return [list(record) for record in records]


def _validate_structural_profile(profile: TipnrStructuralRecord) -> None:
    if profile.marker_class == "documentation":
        if _DOCUMENTATION_MARKERS.get(profile.ordinal) != profile.marker_shape:
            raise TipnrSchemaError("documentation_record_sequence_changed")
        return

    if profile.line_shape_codes:
        expected = _NON_FORM_PROFILE_SHA256.get(profile.ordinal)
        if expected is None or canonical_sha256(asdict(profile)) != expected:
            raise TipnrSchemaError("unknown_line_shape")
        return

    expected_width = _ENTITY_PRIMARY_WIDTHS[profile.marker_class]
    width_is_known_malformed = (
        profile.ordinal == 3099
        and profile.marker_class == "person"
        and profile.primary_width == 13
    )
    if profile.primary_width != expected_width and not width_is_known_malformed:
        raise TipnrSchemaError("row_shape_changed")

    for shape in profile.form_shapes:
        shape_is_known_malformed = (
            profile.ordinal == 3624
            and profile.marker_class == "place"
            and shape == ("Named", 6)
        )
        if shape not in _ENTITY_FORM_SHAPES and not shape_is_known_malformed:
            raise TipnrSchemaError("unknown_significance")


def scan_tipnr_records(text: str) -> tuple[TipnrStructuralRecord, ...]:
    """Return closed structural profiles without retaining excluded values."""

    profiles: list[TipnrStructuralRecord] = []
    for ordinal, lines in enumerate(split_tipnr_records(text), start=1):
        normalized_marker = lines[0].rstrip("\t ")
        marker = _MARKER_SHAPES.get(normalized_marker)
        if marker is None:
            raise TipnrSchemaError("unknown_entity_marker")

        form_shapes: list[tuple[str, int]] = []
        directive_keys: list[str] = []
        line_shape_codes: list[str] = []
        for line in lines[2:]:
            if not line.strip():
                continue
            if line.startswith("@"):
                key = line.split("=", 1)[0]
                if key not in _STRUCTURAL_DIRECTIVE_KEYS:
                    raise TipnrSchemaError("unknown_directive")
                directive_keys.append(key)
                continue
            if line.startswith("–"):
                columns = _meaningful_columns(line)
                significance = columns[0].removeprefix("–").strip()
                form_shapes.append((significance, len(columns)))
                continue
            columns = _meaningful_columns(line)
            line_shape_codes.append(f"u{ord(line[0]):04x}:{len(columns)}")

        profile = TipnrStructuralRecord(
                ordinal=ordinal,
                marker_shape=marker[0],
                marker_class=marker[1],
                primary_width=(
                    len(_meaningful_columns(lines[1])) if len(lines) > 1 else 0
                ),
                form_shapes=tuple(form_shapes),
                directive_keys=tuple(directive_keys),
                line_shape_codes=tuple(line_shape_codes),
            )
        _validate_structural_profile(profile)
        profiles.append(profile)
    return tuple(profiles)


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
