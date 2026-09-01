"""Deterministic source-use policy contracts for biblical-depth work.

Phase 1 only: this module is intentionally not imported by retrieval or answer
generation. It defines the fail-closed policy vocabulary and pure query routing
fixtures without network, model, database, or filesystem access.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Optional, Tuple
from uuid import UUID


class SourceBoundary(str, Enum):
    PROTECTED_SPIRIT_FILLED = "protected_spirit_filled"
    GENERAL = "general"


class PresentationStance(str, Enum):
    HOUSE_POSITION = "house_position"
    PLURAL = "plural"
    SHARED_CHRISTIAN = "shared_christian"
    UNCERTAIN = "uncertain"


class PassagePolicy(str, Enum):
    GENERAL_CONTEXT = "general_context"
    ORTHODOX_VIEWPOINT = "orthodox_viewpoint"
    PROTECTED_SPIRIT_FILLED = "protected_spirit_filled"
    MIXED = "mixed"
    UNCERTAIN = "uncertain"


PROTECTED_TOPIC_KEYS = (
    "continuation_of_gifts",
    "tongues",
    "baptism_holy_spirit",
    "divine_healing",
    "healing_mechanics",
    "apostolic_authority",
    "modern_apostles_and_prophets",
    "prophetic_accountability",
    "deliverance_spiritual_warfare",
    "anointing_impartation_manifestations",
    "hearing_god_and_revelation",
    "revival_signs_and_wonders",
)

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _require_canonical_key(value: str, label: str) -> None:
    if not isinstance(value, str) or _KEY_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical lower_snake_case key")


def _require_canonical_uuid(value: str, label: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a UUID string")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be a canonical UUID") from exc
    if str(parsed) != value:
        raise ValueError(f"{label} must be a canonical lowercase UUID")

# A value here permits HOUSE_POSITION only after the existing matcher supplies
# a real position-paper match. This module never performs or substitutes for
# that match.
APPROVED_HOUSE_TOPIC_KEYS = frozenset(
    {
        "baptism_holy_spirit",
        "speaking_in_tongues",
        "deliverance_and_spiritual_warfare",
        "prosperity_and_faith_teaching",
        "divine_healing",
        "prophecy_and_the_prophetic",
        "five_fold_ministry",
        "gifts_of_the_spirit_overview",
    }
)


@dataclass(frozen=True)
class QueryPolicy:
    source_boundary: SourceBoundary
    presentation_stance: PresentationStance
    protected_topic_keys: Tuple[str, ...] = ()
    issue_key: Optional[str] = None
    house_topic_key: Optional[str] = None
    reason_codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class IssuePolicy:
    """One issue-scoped comparison contract; never a teacher classification."""

    issue_key: str
    source_boundary: SourceBoundary
    viewpoint_slots: Tuple[str, ...] = ()
    protected_topic_keys: Tuple[str, ...] = ()
    registered_source_ids_by_slot: Tuple[Tuple[str, frozenset[str]], ...] = ()
    query_phrases: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_canonical_key(self.issue_key, "issue_key")
        for slot in self.viewpoint_slots:
            _require_canonical_key(slot, "viewpoint slot")
        if len(set(self.viewpoint_slots)) != len(self.viewpoint_slots):
            raise ValueError("viewpoint slots must be unique")
        if len(set(self.protected_topic_keys)) != len(self.protected_topic_keys):
            raise ValueError("protected topic keys must be unique")
        if any(key not in PROTECTED_TOPIC_KEYS for key in self.protected_topic_keys):
            raise ValueError("issue contains an unapproved protected topic key")
        if self.source_boundary is SourceBoundary.GENERAL and self.protected_topic_keys:
            raise ValueError("general issues cannot claim protected topic keys")
        registered_slots = []
        for slot, source_ids in self.registered_source_ids_by_slot:
            _require_canonical_key(slot, "registered viewpoint slot")
            if slot not in self.viewpoint_slots:
                raise ValueError("registered source mapping uses an unknown viewpoint slot")
            if not isinstance(source_ids, frozenset):
                raise TypeError("registered viewpoint source IDs must be a frozenset")
            for source_id in source_ids:
                _require_canonical_uuid(source_id, "registered viewpoint source_id")
            registered_slots.append(slot)
        if len(set(registered_slots)) != len(registered_slots):
            raise ValueError("registered viewpoint source mappings must be unique")
        if any(not isinstance(phrase, str) or not phrase.strip() for phrase in self.query_phrases):
            raise ValueError("query phrases must be non-empty strings")

    def registered_source_ids_for(self, viewpoint_slot: str) -> frozenset[str]:
        for slot, source_ids in self.registered_source_ids_by_slot:
            if slot == viewpoint_slot:
                return source_ids
        return frozenset()

    def matches_query(self, normalized_question: str) -> bool:
        return any(
            _contains_phrase(normalized_question, _normalize(phrase))
            for phrase in self.query_phrases
        )


@dataclass(frozen=True)
class ViewpointEvidence:
    viewpoint_slot: str
    source_id: str

    def __post_init__(self) -> None:
        _require_canonical_key(self.viewpoint_slot, "viewpoint slot")
        _require_canonical_uuid(self.source_id, "viewpoint evidence source_id")


class IssueRegistry:
    def __init__(self, entries: Iterable[IssuePolicy]) -> None:
        entries_tuple = tuple(entries)
        by_key = {entry.issue_key: entry for entry in entries_tuple}
        if len(by_key) != len(entries_tuple):
            raise ValueError("issue keys must be unique")
        self._entries = entries_tuple
        self._by_key = MappingProxyType(by_key)

    @property
    def entries(self) -> Tuple[IssuePolicy, ...]:
        return self._entries

    def get(self, issue_key: str) -> Optional[IssuePolicy]:
        return self._by_key.get(issue_key)

    def require(self, issue_key: str) -> IssuePolicy:
        issue = self.get(issue_key)
        if issue is None:
            raise KeyError(issue_key)
        return issue


ISSUE_REGISTRY = IssueRegistry(
    (
        IssuePolicy(
            "healing_mechanics",
            SourceBoundary.PROTECTED_SPIRIT_FILLED,
            protected_topic_keys=("healing_mechanics",),
        ),
        IssuePolicy(
            "prophetic_accountability",
            SourceBoundary.PROTECTED_SPIRIT_FILLED,
            protected_topic_keys=("prophetic_accountability",),
        ),
        IssuePolicy(
            "apostolic_authority",
            SourceBoundary.PROTECTED_SPIRIT_FILLED,
            protected_topic_keys=("apostolic_authority",),
        ),
        IssuePolicy("eschatological_timing", SourceBoundary.GENERAL),
    )
)


class ApprovedProtectedSourceRegistry:
    """Topic-scoped source IDs; multi-topic queries use the safe intersection."""

    def __init__(self, source_ids_by_topic: Mapping[str, frozenset[str]]) -> None:
        unknown_topics = set(source_ids_by_topic).difference(PROTECTED_TOPIC_KEYS)
        if unknown_topics:
            raise ValueError(f"unapproved protected topic keys: {sorted(unknown_topics)}")
        normalized = {}
        for topic_key, source_ids in source_ids_by_topic.items():
            if not isinstance(source_ids, frozenset):
                raise TypeError("approved source IDs must be provided as a frozenset")
            for source_id in source_ids:
                _require_canonical_uuid(source_id, "approved protected source_id")
            normalized[topic_key] = source_ids
        self._source_ids_by_topic = MappingProxyType(normalized)

    def allowed_source_ids(self, topic_keys: Iterable[str]) -> frozenset[str]:
        keys = tuple(dict.fromkeys(topic_keys))
        if not keys or any(key not in self._source_ids_by_topic for key in keys):
            return frozenset()
        allowed = self._source_ids_by_topic[keys[0]]
        for key in keys[1:]:
            allowed = allowed.intersection(self._source_ids_by_topic[key])
        return frozenset(allowed)


_PROTECTED_TOPIC_PHRASES = {
    "continuation_of_gifts": (
        "gifts of the holy spirit cease",
        "gifts of the spirit cease",
        "spiritual gifts cease",
        "spiritual gifts still for today",
        "gifts of the spirit for today",
        "cessationism",
        "cessationist",
        "continuationism",
        "continuationist",
        "miracles for today",
        "miracles continue today",
        "words of knowledge today",
        "word of knowledge today",
        "words of wisdom today",
        "word of wisdom today",
        "discernment of spirits today",
        "discerning of spirits today",
        "prophecy continue",
        "prophecy in churches today",
        "gift of prophecy today",
    ),
    "tongues": (
        "speaking in tongues",
        "speak in tongues",
        "gift of tongues",
        "praying in tongues",
        "pray in tongues",
        "prayer language",
        "interpretation of tongues",
        "unknown tongues",
        "supernatural languages in private prayer",
    ),
    "baptism_holy_spirit": (
        "baptism in the holy spirit",
        "baptism of the holy spirit",
        "baptized in the holy spirit",
        "baptised in the holy spirit",
        "spirit baptism",
        "receiving power from on high after conversion",
        "separate experience of the holy spirit",
        "subsequent work of the holy spirit",
        "receive the spirit at conversion",
        "receiving the spirit at conversion",
        "receive the holy spirit after conversion",
        "filled with the spirit after conversion",
        "sealed with the holy spirit",
        "sealing of the holy spirit",
        "subsequence of spirit baptism",
    ),
    "divine_healing": (
        "divine healing",
        "gift of healing",
        "gifts of healing",
        "healing ministry",
        "does god still heal",
        "healing for today",
    ),
    "healing_mechanics": (
        "healing in the atonement",
        "healed in the atonement",
        "atonement provides healing",
        "why does god heal some",
        "why am i not healed",
        "why wasn t i healed",
        "does god always heal",
        "always god s will to heal",
        "by his stripes we are healed",
    ),
    "apostolic_authority": (
        "apostolic authority",
        "apostolic accountability",
        "office of apostle",
        "office of an apostle",
        "apostles still have authority",
        "apostolic succession",
        "new apostolic reformation",
    ),
    "modern_apostles_and_prophets": (
        "modern apostles and prophets",
        "apostles and prophets today",
        "five fold ministry",
        "fivefold ministry",
        "five fold ministry today",
        "fivefold ministry today",
        "five fold ministries continue",
    ),
    "prophetic_accountability": (
        "test a prophecy",
        "test a prophetic word",
        "weigh a prophetic word",
        "judge a prophecy",
        "false prophecy",
        "false prophet",
        "prophetic accountability",
        "prophetic authority",
        "hold the person accountable",
        "office of a prophet",
        "prophets active in the church today",
        "prophets active today",
        "are there prophets today",
        "prophets today",
    ),
    "deliverance_spiritual_warfare": (
        "deliverance ministry",
        "need deliverance",
        "christian be demonized",
        "christian be demonised",
        "cast out demons today",
        "demonic oppression of believers",
        "spiritual warfare today",
    ),
    "anointing_impartation_manifestations": (
        "receive an anointing",
        "impartation through laying on of hands",
        "spiritual impartation",
        "manifestations of the holy spirit",
        "manifestations of the spirit today",
        "laying on of hands impart spiritual gifts",
    ),
    "hearing_god_and_revelation": (
        "hear god today",
        "god still speaks today",
        "dreams and visions today",
        "god still guide believers through dreams",
        "contemporary revelation",
        "personal prophetic guidance",
    ),
    "revival_signs_and_wonders": (
        "revival signs and wonders",
        "signs and wonders today",
        "supernatural revival",
        "expect miracles in revival",
        "signs and wonders in revival",
    ),
}

# These patterns prove that clearly historical/contextual neighbors can remain
# general without making every lexical non-match general. Everything outside
# an explicit protected, issue, house-compatible, or general-context match
# takes the protected/uncertain safe path in Phase 1.
_GENERAL_CONTEXT_PHRASES = (
    "who were the twelve apostles",
    "literary role does prophecy play in isaiah",
    "where did jesus heal",
    "what happened when the disciples laid hands on the sick in acts",
    "where was corinth",
)

_ESCHATOLOGICAL_TIMING_PHRASES = (
    "premillennial",
    "postmillennial",
    "amillennial",
    "pre tribulation",
    "post tribulation",
    "mid tribulation",
    "rapture before",
    "rapture after",
    "timing of the rapture",
)

_ISSUE_BY_PROTECTED_TOPIC = {
    "healing_mechanics": "healing_mechanics",
    "prophetic_accountability": "prophetic_accountability",
    "apostolic_authority": "apostolic_authority",
}

_HOUSE_COMPATIBLE_PROTECTED_TOPICS = {
    "baptism_holy_spirit": frozenset({"baptism_holy_spirit"}),
    "speaking_in_tongues": frozenset({"tongues"}),
    "deliverance_and_spiritual_warfare": frozenset({"deliverance_spiritual_warfare"}),
    "divine_healing": frozenset({"divine_healing"}),
    "prophecy_and_the_prophetic": frozenset(
        {"continuation_of_gifts", "hearing_god_and_revelation"}
    ),
    "five_fold_ministry": frozenset({"modern_apostles_and_prophets"}),
    "gifts_of_the_spirit_overview": frozenset({"continuation_of_gifts"}),
}

_GENERAL_HOUSE_TOPIC_PHRASES = {
    "prosperity_and_faith_teaching": (
        "prosperity gospel",
        "prosperity teaching",
        "word of faith teaching",
    ),
}


def _normalize(text: object) -> str:
    if not isinstance(text, str):
        return ""
    lowered = text.casefold().replace("’", "'").replace("-", " ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", lowered).split())


def _contains_phrase(normalized_question: str, phrase: str) -> bool:
    return f" {phrase} " in f" {normalized_question} "


def detect_protected_topics(question: object) -> Tuple[str, ...]:
    """Return explicit protected-topic matches in canonical registry order."""

    normalized = _normalize(question)
    return tuple(
        topic_key
        for topic_key in PROTECTED_TOPIC_KEYS
        if any(
            _contains_phrase(normalized, _normalize(phrase))
            for phrase in _PROTECTED_TOPIC_PHRASES[topic_key]
        )
    )


def _is_explicit_general_context(normalized_question: str) -> bool:
    return any(
        _contains_phrase(normalized_question, _normalize(phrase))
        for phrase in _GENERAL_CONTEXT_PHRASES
    )


def _house_topic_is_compatible(
    pillar_key: str,
    protected_topics: Tuple[str, ...],
    normalized_question: str,
) -> bool:
    compatible_topics = _HOUSE_COMPATIBLE_PROTECTED_TOPICS.get(pillar_key)
    if compatible_topics is not None:
        return bool(compatible_topics.intersection(protected_topics))
    return any(
        _contains_phrase(normalized_question, _normalize(phrase))
        for phrase in _GENERAL_HOUSE_TOPIC_PHRASES.get(pillar_key, ())
    )


def _infer_issue_key(question: str, protected_topics: Tuple[str, ...]) -> Optional[str]:
    protected_issues = {
        _ISSUE_BY_PROTECTED_TOPIC[key]
        for key in protected_topics
        if key in _ISSUE_BY_PROTECTED_TOPIC
    }
    if len(protected_issues) == 1:
        return next(iter(protected_issues))
    if protected_issues:
        return None
    normalized = _normalize(question)
    if any(_contains_phrase(normalized, _normalize(phrase)) for phrase in _ESCHATOLOGICAL_TIMING_PHRASES):
        return "eschatological_timing"
    return None


PositionPaperMatcher = Callable[[str], Optional[str]]


def classify_query(
    question: object,
    *,
    position_paper_matcher: Optional[PositionPaperMatcher] = None,
    issue_key: Optional[str] = None,
    viewpoint_evidence: Iterable[ViewpointEvidence] = (),
    issue_registry: IssueRegistry = ISSUE_REGISTRY,
) -> QueryPolicy:
    """Classify a query without importing retrieval or an answer-path matcher.

    A Phase 4 adapter may supply the existing position-paper matcher. Calling
    that matcher here binds its result to this exact question; a caller cannot
    assert a bare house key. With no explicit deterministic match, the default
    is protected/uncertain rather than general/shared.
    """

    normalized_question = _normalize(question)
    if not normalized_question:
        return QueryPolicy(
            source_boundary=SourceBoundary.PROTECTED_SPIRIT_FILLED,
            presentation_stance=PresentationStance.UNCERTAIN,
            reason_codes=("invalid_or_empty_question",),
        )
    if issue_key is not None and (
        not isinstance(issue_key, str) or _KEY_RE.fullmatch(issue_key) is None
    ):
        return QueryPolicy(
            source_boundary=SourceBoundary.PROTECTED_SPIRIT_FILLED,
            presentation_stance=PresentationStance.UNCERTAIN,
            reason_codes=("invalid_explicit_issue_key",),
        )

    protected_topics = detect_protected_topics(question)
    inferred_issue_key = _infer_issue_key(normalized_question, protected_topics)

    explicit_general = _is_explicit_general_context(normalized_question)
    inferred_issue = (
        issue_registry.get(inferred_issue_key) if inferred_issue_key is not None else None
    )
    baseline_boundary = (
        SourceBoundary.PROTECTED_SPIRIT_FILLED
        if protected_topics
        else SourceBoundary.GENERAL
        if (
            inferred_issue is not None
            and inferred_issue.source_boundary is SourceBoundary.GENERAL
        )
        or explicit_general
        else SourceBoundary.PROTECTED_SPIRIT_FILLED
    )

    if issue_key is not None and inferred_issue_key is not None and issue_key != inferred_issue_key:
        return QueryPolicy(
            source_boundary=baseline_boundary,
            presentation_stance=PresentationStance.UNCERTAIN,
            protected_topic_keys=protected_topics,
            issue_key=issue_key,
            reason_codes=("explicit_issue_conflicts_with_detected_issue",),
        )

    resolved_issue_key = issue_key or inferred_issue_key
    issue = issue_registry.get(resolved_issue_key) if resolved_issue_key else None
    issue_query_compatible = issue is not None and (
        inferred_issue_key == resolved_issue_key
        or issue.matches_query(normalized_question)
    )
    if issue_key is not None and not issue_query_compatible:
        return QueryPolicy(
            source_boundary=baseline_boundary,
            presentation_stance=PresentationStance.UNCERTAIN,
            protected_topic_keys=protected_topics,
            issue_key=issue_key,
            reason_codes=("explicit_issue_not_query_compatible",),
        )
    source_boundary = (
        issue.source_boundary
        if issue_key is not None and issue_query_compatible and not protected_topics
        else baseline_boundary
    )

    # Registered debates take precedence over every house-paper result. This
    # preserves the three protected debates and general eschatological timing.
    if resolved_issue_key is not None:
        if issue is None:
            return QueryPolicy(
                source_boundary=source_boundary,
                presentation_stance=PresentationStance.UNCERTAIN,
                protected_topic_keys=protected_topics,
                issue_key=resolved_issue_key,
                reason_codes=("unregistered_issue",),
            )
        if issue.source_boundary is not source_boundary:
            return QueryPolicy(
                source_boundary=source_boundary,
                presentation_stance=PresentationStance.UNCERTAIN,
                protected_topic_keys=protected_topics,
                issue_key=resolved_issue_key,
                reason_codes=("issue_boundary_mismatch",),
            )
        if source_boundary is SourceBoundary.PROTECTED_SPIRIT_FILLED and (
            set(issue.protected_topic_keys) != set(protected_topics)
        ):
            return QueryPolicy(
                source_boundary=source_boundary,
                presentation_stance=PresentationStance.UNCERTAIN,
                protected_topic_keys=protected_topics,
                issue_key=resolved_issue_key,
                reason_codes=("issue_protected_topics_mismatch",),
            )
        try:
            evidence = tuple(viewpoint_evidence)
        except TypeError:
            evidence = ()
        if not all(isinstance(item, ViewpointEvidence) for item in evidence):
            evidence = ()
        evidenced_slots = {item.viewpoint_slot for item in evidence}
        evidenced_sources = {item.source_id for item in evidence}
        registered_slots = set(issue.viewpoint_slots)
        sources_are_registered = all(
            item.source_id in issue.registered_source_ids_for(item.viewpoint_slot)
            for item in evidence
        )
        if (
            len(evidenced_slots) >= 2
            and len(evidenced_sources) >= 2
            and evidenced_slots.issubset(registered_slots)
            and sources_are_registered
        ):
            stance = PresentationStance.PLURAL
            reasons = ("two_registered_viewpoints_and_sources_evidenced",)
        else:
            stance = PresentationStance.UNCERTAIN
            reasons = ("insufficient_registered_viewpoint_evidence",)
        return QueryPolicy(
            source_boundary=source_boundary,
            presentation_stance=stance,
            protected_topic_keys=protected_topics,
            issue_key=resolved_issue_key,
            reason_codes=reasons,
        )

    matched_house_topic = None
    matcher_failed = False
    if position_paper_matcher is not None:
        try:
            matched_house_topic = position_paper_matcher(str(question))
        except Exception:
            matcher_failed = True
    if (
        isinstance(matched_house_topic, str)
        and matched_house_topic in APPROVED_HOUSE_TOPIC_KEYS
        and _house_topic_is_compatible(
            matched_house_topic,
            protected_topics,
            normalized_question,
        )
    ):
        return QueryPolicy(
            source_boundary=source_boundary,
            presentation_stance=PresentationStance.HOUSE_POSITION,
            protected_topic_keys=protected_topics,
            house_topic_key=matched_house_topic,
            reason_codes=("query_bound_compatible_house_match",),
        )

    if source_boundary is SourceBoundary.GENERAL:
        return QueryPolicy(
            source_boundary=source_boundary,
            presentation_stance=PresentationStance.SHARED_CHRISTIAN,
            reason_codes=(
                "general_context_with_incompatible_house_match"
                if matched_house_topic is not None
                else "general_shared_christian",
            ),
        )

    return QueryPolicy(
        source_boundary=source_boundary,
        presentation_stance=PresentationStance.UNCERTAIN,
        protected_topic_keys=protected_topics,
        reason_codes=(
            "position_paper_matcher_failed"
            if matcher_failed
            else "protected_or_unclassified_without_approved_policy_evidence",
        ),
    )
