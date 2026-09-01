#!/usr/bin/env python3
"""Parse approved OpenBible ancient-place fields without database access."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Mapping

from biblical_context_tooling import canonical_sha256


_ROOT_FIELDS = frozenset(
    {
        "comment",
        "extra",
        "friendly_id",
        "geojson_file",
        "geometry_credit",
        "id",
        "identification_sources",
        "identifications",
        "kml_file",
        "linked_data",
        "media",
        "modern_associations",
        "preceding_article",
        "translation_name_counts",
        "types",
        "url_slug",
        "verses",
    }
)
_VERSE_FIELDS = frozenset(
    {
        "alternate_roots",
        "alternate_verses",
        "instance_types",
        "osis",
        "readable",
        "sort",
        "translations",
        "usx",
    }
)
_ASSOCIATION_FIELDS = frozenset(
    {"identification_ids", "name", "score", "url_slug"}
)
_ZERO_COUNTS = {
    "attempted": 0,
    "previewed": 0,
    "malformed": 0,
    "duplicate": 0,
    "skipped": 0,
    "prohibited": 0,
}


class OpenBibleSchemaError(ValueError):
    """The pinned OpenBible JSON schema gained an unknown field."""


class OpenBibleItemError(ValueError):
    """One structurally recognized OpenBible place is malformed."""


def _nonempty_string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenBibleItemError(reason)
    return value


def _string_list(value: object, reason: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise OpenBibleItemError(reason)
    return [_nonempty_string(item, reason) for item in value]


def parse_openbible_place(
    value: Mapping[str, object], *, artifact_revision: str
) -> dict[str, object]:
    """Project one complete ancient.jsonl object through the approved allowlist."""

    unknown_root = set(value) - _ROOT_FIELDS
    if unknown_root:
        raise OpenBibleSchemaError("unknown_root_field")

    place_id = _nonempty_string(value.get("id"), "place_id_invalid")
    place_name = _nonempty_string(value.get("friendly_id"), "place_name_invalid")
    place_types = _string_list(value.get("types"), "place_types_invalid")

    raw_verses = value.get("verses")
    if not isinstance(raw_verses, list) or not raw_verses:
        raise OpenBibleItemError("verses_invalid")
    references: list[str] = []
    for raw_verse in raw_verses:
        if not isinstance(raw_verse, Mapping):
            raise OpenBibleItemError("verse_invalid")
        if set(raw_verse) - _VERSE_FIELDS:
            raise OpenBibleSchemaError("unknown_verse_field")
        references.append(
            _nonempty_string(raw_verse.get("osis"), "verse_osis_invalid")
        )

    raw_associations = value.get("modern_associations")
    if raw_associations is None:
        associations: Mapping[str, object] = {}
    elif isinstance(raw_associations, Mapping):
        associations = raw_associations
    else:
        raise OpenBibleItemError("modern_associations_invalid")

    candidates: list[dict[str, object]] = []
    for association_key in sorted(associations):
        raw_association = associations[association_key]
        if not isinstance(raw_association, Mapping):
            raise OpenBibleItemError("modern_association_invalid")
        if set(raw_association) - _ASSOCIATION_FIELDS:
            raise OpenBibleSchemaError("unknown_association_field")
        modern_id = _nonempty_string(
            association_key, "candidate_modern_id_invalid"
        )
        name = _nonempty_string(
            raw_association.get("name"), "candidate_name_invalid"
        )
        score = raw_association.get("score")
        if isinstance(score, bool) or not isinstance(score, int):
            raise OpenBibleItemError("confidence_score_invalid")
        candidates.append(
            {
                "modern_id": modern_id,
                "name": name,
                "confidence_score": score,
            }
        )

    record: dict[str, object] = {
        "dataset_id": "openbible_structured_data",
        "artifact_revision": artifact_revision,
        "place_id": place_id,
        "place_name": place_name,
        "place_types": place_types,
        "osis_references": references,
        "candidate_identifications": candidates,
    }
    record["record_sha256"] = canonical_sha256(record)
    return record


def parse_openbible_file(path: Path, *, artifact_revision: str) -> dict[str, object]:
    """Parse an explicit ancient.jsonl fixture and reconcile every line."""

    counts = dict(_ZERO_COUNTS)
    reasons: Counter[str] = Counter()
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        counts["attempted"] += 1
        try:
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise OpenBibleItemError("place_not_mapping")
            record = parse_openbible_place(value, artifact_revision=artifact_revision)
        except json.JSONDecodeError:
            counts["malformed"] += 1
            reasons["invalid_json"] += 1
            continue
        except OpenBibleItemError as exc:
            counts["malformed"] += 1
            reasons[str(exc)] += 1
            continue

        place_id = str(record["place_id"])
        if place_id in seen_ids:
            counts["duplicate"] += 1
            reasons["duplicate_place_id"] += 1
            continue
        seen_ids.add(place_id)
        records.append(record)
        counts["previewed"] += 1

    return {
        "counts": counts,
        "reason_counts": dict(sorted(reasons.items())),
        "records": records,
        "checksum": canonical_sha256(records),
    }
