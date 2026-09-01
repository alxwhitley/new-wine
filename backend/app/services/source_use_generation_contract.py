"""Writer-facing source-use contract for default-off biblical context.

This module receives only a finalized Phase 4 route and already-eligible
chunks. It does not route, retrieve, query storage, call a model, or admit new
evidence. Its checks prove visible source structure and direct-copy boundaries,
not theological truth or semantic faithfulness.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import product
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.source_use_policy import PresentationStance, QueryPolicy


SOURCE_USE_PRESENTATION_FAILURE = (
    "New Wine could not reliably present the available sources under this "
    "question's required source boundaries."
)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "source_use_generation_prompt.txt"
_PROMPT_TEXT = _PROMPT_PATH.read_text()
SOURCE_USE_PROMPT_FINGERPRINT = "source_use_prompt_" + hashlib.sha256(
    _PROMPT_TEXT.encode("utf-8")
).hexdigest()[:12]

_SECTION_RE = re.compile(r"^\[([a-z_]+)\]\s*$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_HOUSE_COPY_WORDS = 12
_MAX_DISPLAY_IDENTITY_LENGTH = 160


class SourceUseContractError(ValueError):
    """The finalized route cannot be represented safely for the writer."""


@dataclass(frozen=True)
class ViewpointLane:
    display_identity: str
    source_id: str
    chunk_ids: Tuple[str, ...]


@dataclass(frozen=True)
class SourceUseGenerationContract:
    question: str
    source_boundary: str
    presentation_stance: str
    issue_key: Optional[str]
    reference_identities: Tuple[str, ...]
    viewpoint_lanes: Tuple[ViewpointLane, ...]
    doctrinal_chunk_ids: Tuple[str, ...]
    independent_evidence_texts: Tuple[str, ...]
    house_fence_text: Optional[str]


def _prompt_sections() -> Dict[str, str]:
    matches = list(_SECTION_RE.finditer(_PROMPT_TEXT))
    sections = {}  # type: Dict[str, str]
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(_PROMPT_TEXT)
        sections[match.group(1)] = _PROMPT_TEXT[start:end].strip()
    required = {
        "base",
        PresentationStance.SHARED_CHRISTIAN.value,
        PresentationStance.PLURAL.value,
        PresentationStance.HOUSE_POSITION.value,
        PresentationStance.UNCERTAIN.value,
    }
    if set(sections) != required:
        raise RuntimeError("source-use generation prompt sections are incomplete")
    return sections


_PROMPT_SECTIONS = _prompt_sections()


def _clean_identity(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _display_identity(value: object) -> str:
    identity = _clean_identity(value)
    if not identity:
        return ""
    if (
        any(ord(character) < 32 for character in identity)
        or len(identity) > _MAX_DISPLAY_IDENTITY_LENGTH
    ):
        raise SourceUseContractError(
            "display identities must be bounded single-line grounded text"
        )
    return identity


def _reference_identity(chunk: dict) -> str:
    return _display_identity(chunk.get("author")) or _display_identity(chunk.get("title"))


def _plural_display_identities(selected: Sequence[dict]) -> Tuple[str, ...]:
    authors = tuple(_display_identity(chunk.get("author")) for chunk in selected)
    if all(authors) and len(set(value.casefold() for value in authors)) == len(authors):
        return authors

    titles = tuple(_display_identity(chunk.get("title")) for chunk in selected)
    if all(titles) and len(set(value.casefold() for value in titles)) == len(titles):
        return titles
    raise SourceUseContractError(
        "plural generation requires distinct grounded display identities"
    )


def _select_plural_chunks(
    by_slot: Dict[str, List[dict]]
) -> Tuple[Tuple[dict, ...], Tuple[str, ...]]:
    slots = tuple(by_slot)
    if len(slots) < 2:
        raise SourceUseContractError("plural generation requires at least two viewpoint slots")

    candidates = []  # type: List[Tuple[dict, ...]]
    for slot in slots:
        first_by_source = {}  # type: Dict[str, dict]
        for chunk in by_slot[slot]:
            source_id = _clean_identity(chunk.get("_source_id"))
            if not source_id:
                raise SourceUseContractError("plural evidence is missing a source ID")
            first_by_source.setdefault(source_id, chunk)
        candidates.append(tuple(first_by_source.values()))

    found_distinct_sources = False
    for selection in product(*candidates):
        source_ids = tuple(_clean_identity(chunk.get("_source_id")) for chunk in selection)
        if len(set(source_ids)) == len(source_ids):
            found_distinct_sources = True
            try:
                identities = _plural_display_identities(selection)
            except SourceUseContractError:
                continue
            return tuple(selection), identities
    if found_distinct_sources:
        raise SourceUseContractError(
            "plural generation requires distinct grounded display identities"
        )
    raise SourceUseContractError("plural generation requires distinct registered source IDs")


def build_generation_contract(
    question: str,
    query_policy: QueryPolicy,
    chunks: Iterable[dict],
    house_fence_text: Optional[str] = None,
) -> SourceUseGenerationContract:
    """Build a writer contract from a finalized route and eligible chunks."""

    if not isinstance(query_policy, QueryPolicy):
        raise SourceUseContractError("source-use generation requires a finalized query policy")

    material = tuple(chunks)
    doctrinal = []  # type: List[dict]
    references = []  # type: List[dict]
    by_slot = {}  # type: Dict[str, List[dict]]
    for chunk in material:
        role = chunk.get("_source_use_role")
        if role == "doctrinal":
            doctrinal.append(chunk)
        elif role == "reference":
            references.append(chunk)
        elif role == "viewpoint":
            slot = _clean_identity(chunk.get("_viewpoint_slot"))
            if not slot:
                raise SourceUseContractError("viewpoint evidence is missing its registered slot")
            by_slot.setdefault(slot, []).append(chunk)
        else:
            raise SourceUseContractError("eligible chunk is missing one source-use role")

    reference_identities = []  # type: List[str]
    for chunk in references:
        identity = _reference_identity(chunk)
        if not identity:
            raise SourceUseContractError("reference evidence is missing a grounded identity")
        if identity.casefold() not in {item.casefold() for item in reference_identities}:
            reference_identities.append(identity)

    lanes = []  # type: List[ViewpointLane]
    if query_policy.presentation_stance is PresentationStance.PLURAL:
        selected, identities = _select_plural_chunks(by_slot)
        for chunk, identity in zip(selected, identities):
            source_id = _clean_identity(chunk.get("_source_id"))
            slot = _clean_identity(chunk.get("_viewpoint_slot"))
            chunk_ids = tuple(
                str(item.get("id"))
                for item in by_slot[slot]
                if _clean_identity(item.get("_source_id")) == source_id
            )
            lanes.append(ViewpointLane(identity, source_id, chunk_ids))
    elif by_slot:
        raise SourceUseContractError("viewpoint evidence reached a non-plural writer route")

    return SourceUseGenerationContract(
        question=question,
        source_boundary=query_policy.source_boundary.value,
        presentation_stance=query_policy.presentation_stance.value,
        issue_key=query_policy.issue_key,
        reference_identities=tuple(reference_identities),
        viewpoint_lanes=tuple(lanes),
        doctrinal_chunk_ids=tuple(str(chunk.get("id")) for chunk in doctrinal),
        independent_evidence_texts=tuple(
            str(chunk.get("content") or "") for chunk in material
        ),
        house_fence_text=house_fence_text,
    )


def _render_evidence_lanes(contract: SourceUseGenerationContract) -> str:
    lines = ["Evidence lanes supplied by the server:"]
    if contract.doctrinal_chunk_ids:
        lines.append("- Doctrinal source lane: present")
    for identity in contract.reference_identities:
        lines.append("- Reference source: %s" % identity)
    for index, lane in enumerate(contract.viewpoint_lanes, 1):
        lines.append("- Viewpoint lane %d: %s" % (index, lane.display_identity))
    if contract.house_fence_text:
        lines.append("- House fence: present as silent context only")
    return "\n".join(lines)


def render_generation_prompt(contract: SourceUseGenerationContract) -> str:
    base = _PROMPT_SECTIONS["base"].format(
        source_boundary=contract.source_boundary,
        presentation_stance=contract.presentation_stance,
        issue_key=contract.issue_key or "none",
        evidence_lanes=_render_evidence_lanes(contract),
    )
    stance = _PROMPT_SECTIONS[contract.presentation_stance]
    return base + "\n\n" + stance


def _heading_sections(answer: str) -> Tuple[Tuple[str, str], ...]:
    headings = list(re.finditer(r"(?im)^##\s+([^\n]+)\s*$", answer or ""))
    sections = []  # type: List[Tuple[str, str]]
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(answer or "")
        sections.append((heading.group(1).strip(), (answer or "")[heading.end():end]))
    return tuple(sections)


def _normalized_words(text: str) -> Tuple[str, ...]:
    return tuple(_WORD_RE.findall((text or "").casefold()))


def _shingles(text: str, width: int = _HOUSE_COPY_WORDS) -> set:
    words = _normalized_words(text)
    return {
        tuple(words[index:index + width])
        for index in range(max(0, len(words) - width + 1))
    }


def _copied_house_wording(answer: str, contract: SourceUseGenerationContract) -> bool:
    if not contract.house_fence_text:
        return False
    shared = _shingles(contract.question)
    for evidence in contract.independent_evidence_texts:
        shared.update(_shingles(evidence))
    distinctive_paper = _shingles(contract.house_fence_text).difference(shared)
    return bool(_shingles(answer).intersection(distinctive_paper))


def validate_generated_answer(
    answer: str, contract: SourceUseGenerationContract
) -> Tuple[str, ...]:
    failures = []  # type: List[str]
    sections = _heading_sections(answer)

    if contract.reference_identities:
        reference_sections = [
            body for heading, body in sections if heading.casefold() == "reference context"
        ]
        if not reference_sections:
            failures.append("missing_reference_context_heading")
        elif not any(
            identity.casefold() in body.casefold()
            for body in reference_sections
            for identity in contract.reference_identities
        ):
            failures.append("missing_reference_context_identity")

    for lane in contract.viewpoint_lanes:
        if not any(
            lane.display_identity.casefold() in heading.casefold()
            for heading, _body in sections
        ):
            failures.append("missing_plural_heading:%s" % lane.display_identity)

    if _copied_house_wording(answer, contract):
        failures.append("copied_house_position_wording")
    return tuple(failures)


def render_retry_constraint(failures: Iterable[str]) -> str:
    lines = ["SOURCE-USE RETRY REQUIREMENTS (this is the only retry):"]
    for failure in failures:
        if failure == "missing_reference_context_heading":
            lines.append(
                "- Add a ## Reference context section naming an eligible reference source."
            )
        elif failure == "missing_reference_context_identity":
            lines.append(
                "- Name a supplied grounded reference identity under ## Reference context."
            )
        elif failure.startswith("missing_plural_heading:"):
            identity = failure.split(":", 1)[1]
            lines.append(
                "- Add a separate ## heading containing this grounded viewpoint source: %s"
                % identity
            )
        elif failure == "copied_house_position_wording":
            lines.append(
                "- Remove wording copied from the silent house-position fence; use only independent evidence phrasing."
            )
        else:
            lines.append("- Satisfy the source-use contract requirement: %s" % failure)
    lines.append(
        "Do not add evidence, sources, viewpoints, or claims that were not supplied."
    )
    return "\n".join(lines)
