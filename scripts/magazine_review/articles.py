"""Fail-closed, issue-wide magazine article segmentation and review."""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import replace
from typing import Any, Mapping, Protocol

from .ocr import VerifiedIssueTranscript
from .schemas import (
    ArticleManifest,
    ArticleRecord,
    ArtifactValidationError,
    StageIdentity,
)


ARTICLE_MODEL = "openai/gpt-oss-120b"
# Raised from "low" 2026-08-27 (New Wine A2, Issue 02-1973): at low reasoning
# the model proposed a plausible, schema-valid, but incomplete article set
# that silently stopped 54% of the way through a 32-page issue -- not a
# token-budget truncation (it used 1,359 of 65,536 allowed output tokens).
# The review stage, same model at "medium", caught the same class of gap
# correctly.
#
# Raised again, "medium" -> "high", same day, same issue: across live
# validation attempts against this real 32-page/121,011-char issue, "medium"
# reasoning produced an implausibly-large single/few-article segmentation
# (caught deterministically by _MAX_ARTICLE_CHARS) in roughly half of all
# attempts that reached segmentation at all (3 of 6 consecutive attempts,
# 2026-08-27) -- a real, recurring tendency, not one-off noise. This is a
# recorded design decision per Invariant 17's "explicitly unstable"
# model/effort snapshot, not a silent drift.
SEGMENTATION_REASONING = "high"
REVIEW_REASONING = "medium"
SEGMENTATION_INSTRUCTIONS = (
    "Segment every authored article in the complete verified magazine transcript. "
    "Return each article exactly once, in transcript order, with its stable identity, "
    "unique output filename, title, author, and exact transcript span. Do not return "
    "article text or source pages: the pipeline derives them from the verified "
    "transcript after validating each span. Return spans in ascending transcript "
    "order; article spans must never overlap. "
    "Every character of the transcript belongs to exactly one of two things: an "
    "authored article, or non-authored material (an advertisement, the masthead, "
    "the table of contents, a subscription notice, or similar). Account for all of "
    "it: return authored articles in `articles` and everything else as an exact "
    "transcript span in `non_article_spans`, each with a category and a specific "
    "reason. Do not stop partway through a long transcript -- before responding, "
    "verify that your combined `articles` and `non_article_spans` spans, placed in "
    "transcript order, reach the transcript's exact final character with no gap. "
    "A multi-page issue ordinarily contains MANY distinct authored articles and "
    "MANY separate pieces of non-article material -- each advertisement, letter, "
    "notice, or announcement is its own separate span, never merged with another. "
    "Combining multiple distinct pieces of content into one large span, whether "
    "labeled as an article or as non-article material, is wrong even if it "
    "achieves full coverage: full coverage with the wrong granularity is still "
    "wrong. If a span you are about to return covers more than a few pages, stop "
    "and check whether it actually contains multiple distinct pieces that must be "
    "split apart. "
    # Added 2026-08-27, same New Wine A2 investigation, after two standalone
    # diagnostic calls against Issue 02-1973's cached transcript (no CLI, no
    # OCR cost) showed non_article_span_implausibly_large recurring for a
    # reason unrelated to cap size: "Keeping the Unity" (a labeled reprint)
    # and "New Wine Forum" (a reader Q&A column) were consistently filed as
    # other_non_article instead of recognized as articles, in both runs --
    # the same two articles the semantic reviewer already confirmed real
    # back when the model dumped 93% of this issue as "advertisement"
    # (e8ca4a3). A third, unexplained ~3,000-char "reference table" span
    # also recurred at the same transcript position in both runs, immediately
    # after Bible Study -- most likely that article's own supporting content.
    # A follow-up validation call with this addition correctly recognized
    # both articles and folded the reference table into Bible Study's span.
    # Not a reliability fix: three further live samples the same day showed
    # three DIFFERENT failure shapes unrelated to this specific blind spot
    # (a giant lazy non-article dump, an out-of-order article_spans_overlap,
    # a fabricated mega-article merging real content with ads) -- the
    # recurrence is dominated by run-to-run model variance, not one
    # deterministic gap. This addition is kept because it is strictly
    # correct per the established e8ca4a3 precedent and has no downside (it
    # loosens no cap), not because it closes the recurrence.
    "Two content shapes are still authored articles and must never be filed as "
    "non-article material: an article explicitly labeled as reprinted from "
    "another publication, credited with its own author or original source -- "
    "the reprint label does not make it filler; and a recurring reader "
    "question-and-answer or discussion column with substantive original "
    "written content, even when no single person is credited for the whole "
    "column -- use the column's own name, or \"Readers\" if none is given, as "
    "its author. A supporting reference table, chart, or list that is part of "
    "an article's own content belongs inside that article's span, not as a "
    "separate non-article span."
)
REVIEW_INSTRUCTIONS = (
    "Review the complete proposed article set against the complete verified issue in "
    "fresh context. For every article decide whether its beginning is genuine, ending "
    "is coherent, cross-page transitions are intact, content is omitted or duplicated, "
    "adjacent material bleeds into it, and author attribution is correct. Report a "
    "specific reason for every failed field. Also issue one binding whole-issue "
    "coverage verdict and identify every substantive authored article omitted from "
    "the proposed set, with its exact transcript span and a specific reason."
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Non-article content (ads, mastheads, subscription notices) now has an
# explicit home in non_article_spans (added 2026-08-27), so this tolerance no
# longer needs to absorb it -- it's back to a tight bound covering only real
# inter-span whitespace/running-header formatting noise, observed live to top
# out at 18 chars. A genuinely dropped article or continuation runs into the
# thousands (New Wine A2, Issue 02-1973, retry_13: 5,190 and 55,107 chars).
_COVERAGE_GAP_TOLERANCE_CHARS = 50
# "letters_to_editor" added 2026-08-27: a real, recurring magazine section
# (reader mail, no single author) that doesn't fit any other named category.
# A direct diagnostic call against Issue 02-1973 (New Wine A2, high
# reasoning + the strengthened instructions) produced an otherwise-correct
# 11-article segmentation -- full coverage, no gaps, no overlaps, every
# article under the size cap -- rejected only because "Letters to the
# Editor" (3,840 chars) had nowhere to go but the tight "other_non_article"
# bucket. retry_13 (2026-08-25) independently treated the same content as
# its own thing too (a full article, 3,744 chars) -- two independent runs
# agreeing this is a real, distinct category, not noise.
_NON_ARTICLE_CATEGORIES = frozenset(
    {
        "advertisement",
        "masthead",
        "table_of_contents",
        "subscription_notice",
        "letters_to_editor",
        "other_non_article",
    }
)
# Requiring full coverage (above) closed the silent-omission failure mode but
# opened an adjacent one, caught live 2026-08-27 (New Wine A2, Issue 02-1973,
# same-day validation of the coverage fix): rather than correctly identifying
# two real articles ("The Call of Love", "New Wine Forum"), the model dumped
# them into vague "other_non_article" spans of 3,770 and 31,718 chars -- the
# semantic reviewer caught both, but that's a paid call this check can
# preempt.
#
# The first version of this cap applied only to "other_non_article",
# reasoning that a NAMED category (masthead, advertisement, etc.) was an
# affirmative claim deserving more trust -- a real masthead was observed live
# at 4,152 chars. That reasoning did not survive contact with the very next
# live attempt, same day: the model dodged the cap by labeling a 113,294-char
# span (93% of the whole 121,011-char issue, containing SIX real articles --
# "The Nature of Obedience", "Bible Study", "The Call of Love", "The
# Apostle", "Keeping the Unity", "New Wine Forum") as "advertisement" instead
# of "other_non_article". No real 32-page magazine issue is 93% ads. The
# semantic reviewer caught all six again, but the whole point of this
# deterministic layer is to preempt paying for that call.
#
# Both categories are capped, at different thresholds: "other_non_article"
# stays tighter (it's the vaguest, no content claim at all); the named
# categories get more room, comfortably above confirmed-legitimate cases but
# two orders of magnitude below every observed abuse case (3,770 / 31,718 /
# 113,294 chars).
# other_non_article raised 2,000 -> 2,500 same day (New Wine A2, Issue
# 02-1973): a direct diagnostic call otherwise producing a correct 11-article
# segmentation combined "editorial and table of contents" into one
# other_non_article span of 2,410 chars -- a real, plausible pairing (both
# are staff-written, neither has a byline warranting article treatment), not
# abuse, just barely over the old cap.
_OTHER_NON_ARTICLE_MAX_CHARS = 2500
_NAMED_NON_ARTICLE_MAX_CHARS = 5000
# Per-span caps don't stop the model spreading the same abuse across many
# smaller spans that each individually stay under a cap. No real 32-page
# magazine issue is mostly ads. 0.40 sits above the fraction seen in the one
# run with NO missing-article findings (retry_13: effectively 0%) and at/
# below the fraction seen in the two runs that DID have real missing
# articles (New Wine A2, Issue 02-1973, 2026-08-27: 43% with 2 articles
# missing, 93.8% with 6 missing) -- so it would have caught both live
# regressions on its own, independent of the per-span caps above.
_NON_ARTICLE_TOTAL_FRACTION_MAX = 0.40
# All three checks above bound how much can be excluded as non-article. None
# of them stop the inverse abuse: proposing too FEW articles by making one
# article absurdly large. Live evidence, the attempt immediately after
# e8ca4a3 shipped (New Wine A2, Issue 02-1973, 2026-08-27): the model
# proposed exactly ONE "article" -- title "New Wine February 1973 Issue",
# author "Various" -- spanning the ENTIRE 121,011-char/32-page transcript.
# 100% coverage, 0% non-article, so every check above passed trivially, and
# for the first time this session the semantic reviewer approved it too
# (verdict=True, issue_coverage_complete=True, status=passed) -- its
# instructions judge each proposed article's own start/end/transitions/
# attribution, not whether the NUMBER of articles is plausible for an issue
# this long. Without a rate-limit error on the next (proposition) stage,
# this would have silently proceeded as a "passed" issue.
# 30,000 sits well above the longest confirmed-legitimate single article
# seen live so far (20,711 chars, "The Apostle" in Issue 02-1973's
# 2026-08-27 attempt, itself independently verdict=True on its own
# start/end/attribution) and far below the 121,011-char abuse case.
_MAX_ARTICLE_CHARS = 30000
_SEMANTIC_FIELDS = (
    "start_coherent",
    "end_coherent",
    "transitions_ok",
    "omissions",
    "duplications",
    "adjacent_bleed",
    "attribution_ok",
)


class ArticleReviewError(ArtifactValidationError):
    """Raised when article evidence is malformed or fails deterministic checks."""


class StructuredOutputClient(Protocol):
    """Injected, no-policy boundary around one stateless structured model call."""

    def complete(self, request: dict[str, object]) -> Mapping[str, object]:
        """Return output, usage, and cost for exactly one request."""


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ArticleReviewError("article_evidence_not_canonical_json") from exc


def _require_mapping(value: object, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArticleReviewError(reason)
    return value


def _require_exact_keys(value: object, keys: set[str], reason: str) -> Mapping[str, Any]:
    mapping = _require_mapping(value, reason)
    if set(mapping) != keys:
        raise ArticleReviewError(reason)
    return mapping


def _require_nonempty(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArticleReviewError(reason)
    return value


def _require_sha256(value: object, reason: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ArticleReviewError(reason)
    return value


def _require_int(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArticleReviewError(reason)
    return value


def _require_bool(value: object, reason: str) -> bool:
    if not isinstance(value, bool):
        raise ArticleReviewError(reason)
    return value


def _canonical_filename(value: object) -> str:
    suggested = _require_nonempty(value, "article_filename_required")
    stem = suggested.rsplit(".", 1)[0]
    ascii_stem = (
        unicodedata.normalize("NFKD", stem)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_stem).strip("-")
    if not slug:
        raise ArticleReviewError("article_filename_invalid")
    return f"{slug}.txt"


def _require_string_list(value: object, reason: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ArticleReviewError(reason)
    return tuple(value)


def _validate_verified_transcript(transcript: VerifiedIssueTranscript) -> str:
    if not isinstance(transcript, VerifiedIssueTranscript):
        raise ArticleReviewError("verified_issue_transcript_required")
    _require_sha256(transcript.ocr_identity, "ocr_lineage_invalid")
    if not isinstance(transcript.text, str) or not transcript.text:
        raise ArticleReviewError("issue_transcript_required")
    if not isinstance(transcript.pages, tuple) or not transcript.pages:
        raise ArticleReviewError("verified_issue_pages_required")

    expected_numbers = tuple(range(1, len(transcript.pages) + 1))
    if tuple(page.page_number for page in transcript.pages) != expected_numbers:
        raise ArticleReviewError("verified_issue_pages_not_contiguous")
    previous_end = 0
    for page in transcript.pages:
        _require_sha256(page.image_hash, "verified_page_image_hash_invalid")
        start = _require_int(page.transcript_start, "verified_page_span_invalid")
        end = _require_int(page.transcript_end, "verified_page_span_invalid")
        if start < previous_end or start > end or end > len(transcript.text):
            raise ArticleReviewError("verified_page_span_invalid")
        marker = f"=== PAGE {page.page_number} ===\n"
        marker_start = start - len(marker)
        if marker_start < 0 or transcript.text[marker_start:start] != marker:
            raise ArticleReviewError("verified_page_marker_mismatch")
        previous_end = end
    return _fingerprint(transcript.text)


def _page_payload(transcript: VerifiedIssueTranscript) -> list[dict[str, object]]:
    return [
        {
            "page_number": page.page_number,
            "image_hash": page.image_hash,
            "transcript_start": page.transcript_start,
            "transcript_end": page.transcript_end,
        }
        for page in transcript.pages
    ]


def _response_envelope(response: object, reason: str) -> tuple[Mapping[str, Any], Mapping[str, float | int], float]:
    envelope = _require_exact_keys(response, {"output", "usage", "cost_usd"}, reason)
    output = _require_mapping(envelope["output"], reason)
    usage_raw = _require_mapping(envelope["usage"], "article_usage_invalid")
    usage: dict[str, float | int] = {}
    for name, amount in usage_raw.items():
        if (
            not isinstance(name, str)
            or not name
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise ArticleReviewError("article_usage_invalid")
        usage[name] = amount
    cost = envelope["cost_usd"]
    if (
        isinstance(cost, bool)
        or not isinstance(cost, (int, float))
        or not math.isfinite(cost)
        or cost < 0
    ):
        raise ArticleReviewError("article_cost_invalid")
    return output, usage, float(cost)


def _segmentation_config() -> dict[str, object]:
    return {
        "model": ARTICLE_MODEL,
        "reasoning_effort": SEGMENTATION_REASONING,
        "instructions": SEGMENTATION_INSTRUCTIONS,
        "response_format": _segmentation_schema(),
    }


def _review_config() -> dict[str, object]:
    return {
        "model": ARTICLE_MODEL,
        "reasoning_effort": REVIEW_REASONING,
        "fresh_context": True,
        "instructions": REVIEW_INSTRUCTIONS,
        "response_format": _review_schema(),
    }


def _config_fingerprint(config: Mapping[str, object]) -> str:
    return _fingerprint(_canonical_json(config))


def _stage_identity(transcript: VerifiedIssueTranscript, transcript_hash: str) -> StageIdentity:
    durable_config = {
        "segmentation": _segmentation_config(),
        "review": _review_config(),
    }
    identity = StageIdentity(
        schema_version=1,
        input_hashes={
            "ocr_artifact": transcript.ocr_identity,
            "verified_issue_transcript": transcript_hash,
        },
        model=ARTICLE_MODEL,
        prompt_fingerprint=_fingerprint(_canonical_json(durable_config)),
        renderer_settings={
            "page_image_hashes": {
                str(page.page_number): page.image_hash for page in transcript.pages
            }
        },
    )
    identity.validate()
    return identity


def _segmentation_schema() -> dict[str, object]:
    article = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "article_id",
            "filename",
            "title",
            "author",
            "transcript_start",
            "transcript_end",
        ],
        "properties": {
            "article_id": {"type": "string", "minLength": 1},
            "filename": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "author": {"type": "string", "minLength": 1},
            "transcript_start": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Exact inclusive start offset; starts must be ascending and "
                    "article spans non-overlapping."
                ),
            },
            "transcript_end": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Exact exclusive end offset; must not exceed the next article's "
                    "start."
                ),
            },
        },
    }
    non_article_span = {
        "type": "object",
        "additionalProperties": False,
        "required": ["category", "reason", "transcript_start", "transcript_end"],
        "properties": {
            "category": {
                "type": "string",
                "enum": sorted(_NON_ARTICLE_CATEGORIES),
            },
            "reason": {"type": "string", "minLength": 1},
            "transcript_start": {"type": "integer", "minimum": 0},
            "transcript_end": {"type": "integer", "minimum": 1},
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magazine_article_segmentation",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "ocr_identity",
                    "transcript_hash",
                    "articles",
                    "non_article_spans",
                ],
                "properties": {
                    "ocr_identity": {"type": "string"},
                    "transcript_hash": {"type": "string"},
                    "articles": {"type": "array", "minItems": 1, "items": article},
                    "non_article_spans": {
                        "type": "array",
                        "items": non_article_span,
                    },
                },
            },
        },
    }


def _review_schema() -> dict[str, object]:
    string_list = {"type": "array", "items": {"type": "string", "minLength": 1}}
    article = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "article_id",
            "start_coherent",
            "end_coherent",
            "transitions_ok",
            "omissions",
            "duplications",
            "adjacent_bleed",
            "attribution_ok",
            "failure_reasons",
        ],
        "properties": {
            "article_id": {"type": "string", "minLength": 1},
            "start_coherent": {"type": "boolean"},
            "end_coherent": {"type": "boolean"},
            "transitions_ok": {"type": "boolean"},
            "omissions": string_list,
            "duplications": string_list,
            "adjacent_bleed": string_list,
            "attribution_ok": {"type": "boolean"},
            "failure_reasons": {
                "type": "object",
                "additionalProperties": False,
                "required": list(_SEMANTIC_FIELDS),
                "properties": {
                    field: {
                        "anyOf": [
                            {"type": "string", "minLength": 1},
                            {"type": "null"},
                        ]
                    }
                    for field in _SEMANTIC_FIELDS
                },
            },
        },
    }
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magazine_article_completeness_review",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "ocr_identity",
                    "transcript_hash",
                    "article_set_hash",
                    "issue_coverage_complete",
                    "missing_substantive_spans",
                    "missing_articles",
                    "articles",
                ],
                "properties": {
                    "ocr_identity": {"type": "string"},
                    "transcript_hash": {"type": "string"},
                    "article_set_hash": {"type": "string"},
                    "issue_coverage_complete": {"type": "boolean"},
                    "missing_substantive_spans": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["transcript_start", "transcript_end", "reason"],
                            "properties": {
                                "transcript_start": {"type": "integer", "minimum": 0},
                                "transcript_end": {"type": "integer", "minimum": 1},
                                "reason": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "missing_articles": string_list,
                    "articles": {"type": "array", "minItems": 1, "items": article},
                },
            },
        },
    }


def _source_pages_for_span(
    transcript: VerifiedIssueTranscript, start: int, end: int
) -> tuple[int, ...]:
    return tuple(
        page.page_number
        for page in transcript.pages
        if start < page.transcript_end and end > page.transcript_start
    )


def segment_articles(
    transcript: VerifiedIssueTranscript, client: StructuredOutputClient
) -> ArticleManifest:
    """Propose every article, then reject any mechanically unsafe segmentation."""

    transcript_hash = _validate_verified_transcript(transcript)
    request: dict[str, object] = {
        "stage": "article_segmentation",
        "model": ARTICLE_MODEL,
        "reasoning_effort": SEGMENTATION_REASONING,
        "instructions": SEGMENTATION_INSTRUCTIONS,
        "ocr_identity": transcript.ocr_identity,
        "transcript_hash": transcript_hash,
        "issue_transcript": transcript.text,
        "pages": _page_payload(transcript),
        "response_format": _segmentation_schema(),
    }
    output, usage, cost = _response_envelope(
        client.complete(request), "segmentation_response_invalid"
    )
    output = _require_exact_keys(
        output,
        {"ocr_identity", "transcript_hash", "articles", "non_article_spans"},
        "segmentation_output_invalid",
    )
    if output["ocr_identity"] != transcript.ocr_identity:
        raise ArticleReviewError("ocr_lineage_mismatch")
    if output["transcript_hash"] != transcript_hash:
        raise ArticleReviewError("transcript_lineage_mismatch")
    raw_articles = output["articles"]
    if not isinstance(raw_articles, list) or not raw_articles:
        raise ArticleReviewError("articles_required")
    raw_non_article_spans = output["non_article_spans"]
    if not isinstance(raw_non_article_spans, list):
        raise ArticleReviewError("non_article_spans_required")

    seen_ids: set[str] = set()
    seen_filenames: set[str] = set()
    articles: list[ArticleRecord] = []
    previous_end = 0
    article_keys = {
        "article_id",
        "filename",
        "title",
        "author",
        "transcript_start",
        "transcript_end",
    }
    # Sort by transcript_start before checking overlap, rather than trusting
    # the model's own return order -- found live 2026-08-27 (New Wine A2,
    # Issue 02-1973): three of four real segmentation calls against this
    # issue returned a genuinely non-overlapping article ("Editorial") after
    # a later article in list order, which this check (comparing only to the
    # PREVIOUS article in raw list order) mistook for a real overlap every
    # time. The instructions ask for ascending order, but nothing enforced
    # it. The coverage check further below already sorts by start before
    # comparing, for the same reason -- this makes the article-only check
    # match that pattern. A malformed entry (non-mapping, missing/non-int
    # start) sorts first so the per-article validation below still raises
    # its own precise error instead of a sort-time crash.
    def _sort_key(raw: object) -> int:
        start = raw.get("transcript_start") if isinstance(raw, Mapping) else None
        return start if isinstance(start, int) and not isinstance(start, bool) else -1

    raw_articles = sorted(raw_articles, key=_sort_key)
    for raw in raw_articles:
        proposed = _require_exact_keys(raw, article_keys, "segmentation_article_invalid")
        article_id = _require_nonempty(proposed["article_id"], "article_id_required")
        filename = _canonical_filename(proposed["filename"])
        normalized_id = article_id.casefold()
        normalized_filename = filename.casefold()
        if normalized_id in seen_ids:
            raise ArticleReviewError("article_id_duplicate")
        if normalized_filename in seen_filenames:
            raise ArticleReviewError("article_filename_duplicate")

        start = _require_int(proposed["transcript_start"], "article_span_invalid")
        end = _require_int(proposed["transcript_end"], "article_span_invalid")
        if start < 0 or start >= end or end > len(transcript.text):
            raise ArticleReviewError("article_span_invalid")
        if end - start > _MAX_ARTICLE_CHARS:
            raise ArticleReviewError("article_implausibly_long")
        if start < previous_end:
            raise ArticleReviewError("article_spans_overlap")
        source_pages = _source_pages_for_span(transcript, start, end)
        if not source_pages:
            raise ArticleReviewError("article_source_pages_required")
        text = transcript.text[start:end]

        record = ArticleRecord(
            article_id=article_id,
            filename=filename,
            title=_require_nonempty(proposed["title"], "article_title_required"),
            author=_require_nonempty(proposed["author"], "article_author_required"),
            source_pages=source_pages,
            transcript_start=start,
            transcript_end=end,
            text=text,
            text_hash=_fingerprint(text),
            start_coherent=False,
            end_coherent=False,
            transitions_ok=False,
            omissions=(),
            duplications=(),
            adjacent_bleed=(),
            attribution_ok=False,
            verdict=False,
            failure_reasons={
                "start_coherent": "semantic_review_required",
                "end_coherent": "semantic_review_required",
                "transitions_ok": "semantic_review_required",
                "attribution_ok": "semantic_review_required",
            },
            reasons=(
                "semantic_review_required",
                "semantic_review_required",
                "semantic_review_required",
                "semantic_review_required",
            ),
        )
        record.validate(transcript.text)
        articles.append(record)
        seen_ids.add(normalized_id)
        seen_filenames.add(normalized_filename)
        previous_end = end

    non_article_span_keys = {"category", "reason", "transcript_start", "transcript_end"}
    non_article_spans: list[tuple[int, int, str, str]] = []
    for raw in raw_non_article_spans:
        proposed = _require_exact_keys(
            raw, non_article_span_keys, "non_article_span_invalid"
        )
        category = proposed["category"]
        if category not in _NON_ARTICLE_CATEGORIES:
            raise ArticleReviewError("non_article_span_invalid")
        reason = _require_nonempty(proposed["reason"], "non_article_span_invalid")
        start = _require_int(proposed["transcript_start"], "non_article_span_invalid")
        end = _require_int(proposed["transcript_end"], "non_article_span_invalid")
        if start < 0 or start >= end or end > len(transcript.text):
            raise ArticleReviewError("non_article_span_invalid")
        span_max_chars = (
            _OTHER_NON_ARTICLE_MAX_CHARS
            if category == "other_non_article"
            else _NAMED_NON_ARTICLE_MAX_CHARS
        )
        if end - start > span_max_chars:
            raise ArticleReviewError("non_article_span_implausibly_large")
        non_article_spans.append((start, end, category, reason))

    # Per-span caps (above) don't stop the model from spreading the same
    # abuse across many smaller spans that each individually stay under the
    # cap. This aggregate check closes that -- see
    # _NON_ARTICLE_TOTAL_FRACTION_MAX's definition for the reasoning.
    non_article_total_chars = sum(end - start for start, end, _, _ in non_article_spans)
    if non_article_total_chars > _NON_ARTICLE_TOTAL_FRACTION_MAX * len(transcript.text):
        raise ArticleReviewError("non_article_total_fraction_implausible")

    # Unified coverage check across BOTH articles and non_article_spans --
    # merged and sorted, the whole transcript must be accounted for with no
    # overlap and no gap past a small formatting-noise tolerance. Real
    # inter-span whitespace/running-header gaps observed live top out at 18
    # chars; a genuinely dropped article or continuation runs into the
    # thousands (New Wine A2, Issue 02-1973, retry_13: 5,190 and 55,107
    # chars). Non-article content (ads, mastheads, subscription notices) no
    # longer needs a wide fudge factor -- it now has an explicit home in
    # non_article_spans, so this tolerance is tight again.
    covered = sorted(
        [(a.transcript_start, a.transcript_end) for a in articles]
        + [(s, e) for s, e, _, _ in non_article_spans]
    )
    cursor = 0
    for start, end in covered:
        if start < cursor:
            raise ArticleReviewError("coverage_spans_overlap")
        if start - cursor > _COVERAGE_GAP_TOLERANCE_CHARS:
            raise ArticleReviewError("article_coverage_incomplete")
        cursor = max(cursor, end)
    if len(transcript.text) - cursor > _COVERAGE_GAP_TOLERANCE_CHARS:
        raise ArticleReviewError("article_coverage_incomplete")

    manifest = ArticleManifest(
        identity=_stage_identity(transcript, transcript_hash),
        issue_hash=transcript_hash,
        ocr_artifact_hash=transcript.ocr_identity,
        transcript=transcript.text,
        articles=tuple(articles),
        non_article_spans=tuple(non_article_spans),
        segmentation_model=ARTICLE_MODEL,
        segmentation_prompt_fingerprint=_config_fingerprint(_segmentation_config()),
        segmentation_usage=usage,
        segmentation_cost_usd=cost,
        reviewer_model=ARTICLE_MODEL,
        reviewer_prompt_fingerprint=_config_fingerprint(_review_config()),
        reviewer_usage={},
        reviewer_cost_usd=0.0,
        issue_coverage_complete=False,
        status="quarantined",
        quarantine_reasons=("semantic_review_required",),
    )
    manifest.validate()
    return manifest


def _article_set_hash(articles: tuple[ArticleRecord, ...]) -> str:
    return _fingerprint(
        _canonical_json([_article_review_payload(article) for article in articles])
    )


def _article_review_payload(article: ArticleRecord) -> dict[str, object]:
    """Return source proposal evidence without placeholder review judgments."""

    return {
        "article_id": article.article_id,
        "filename": article.filename,
        "title": article.title,
        "author": article.author,
        "source_pages": list(article.source_pages),
        "transcript_start": article.transcript_start,
        "transcript_end": article.transcript_end,
        "text": article.text,
        "text_hash": article.text_hash,
    }


def _validate_manifest_lineage(
    transcript: VerifiedIssueTranscript,
    transcript_hash: str,
    manifest: ArticleManifest,
) -> None:
    try:
        manifest.validate()
    except ArtifactValidationError as exc:
        raise ArticleReviewError(str(exc)) from exc
    if manifest.ocr_artifact_hash != transcript.ocr_identity:
        raise ArticleReviewError("manifest_ocr_lineage_mismatch")
    if manifest.issue_hash != transcript_hash or manifest.transcript != transcript.text:
        raise ArticleReviewError("manifest_transcript_lineage_mismatch")
    if manifest.segmentation_model != ARTICLE_MODEL:
        raise ArticleReviewError("manifest_segmentation_model_mismatch")
    if manifest.segmentation_prompt_fingerprint != _config_fingerprint(_segmentation_config()):
        raise ArticleReviewError("manifest_segmentation_prompt_mismatch")
    if manifest.reviewer_model != ARTICLE_MODEL:
        raise ArticleReviewError("manifest_review_model_mismatch")
    if manifest.reviewer_prompt_fingerprint != _config_fingerprint(_review_config()):
        raise ArticleReviewError("manifest_review_prompt_mismatch")
    expected_identity = _stage_identity(transcript, transcript_hash)
    if manifest.identity != expected_identity:
        raise ArticleReviewError("manifest_identity_mismatch")


def review_articles_against_issue(
    transcript: VerifiedIssueTranscript,
    manifest: ArticleManifest,
    client: StructuredOutputClient,
) -> ArticleManifest:
    """Run a separate, fresh-context semantic review over the whole issue."""

    transcript_hash = _validate_verified_transcript(transcript)
    _validate_manifest_lineage(transcript, transcript_hash, manifest)
    article_set_hash = _article_set_hash(manifest.articles)
    request_articles = [_article_review_payload(article) for article in manifest.articles]
    request: dict[str, object] = {
        "stage": "article_completeness_review",
        "model": ARTICLE_MODEL,
        "reasoning_effort": REVIEW_REASONING,
        "fresh_context": True,
        "instructions": REVIEW_INSTRUCTIONS,
        "ocr_identity": transcript.ocr_identity,
        "transcript_hash": transcript_hash,
        "article_set_hash": article_set_hash,
        "issue_transcript": transcript.text,
        "pages": _page_payload(transcript),
        "articles": request_articles,
        "response_format": _review_schema(),
    }
    output, usage, cost = _response_envelope(
        client.complete(request), "article_review_response_invalid"
    )
    output = _require_exact_keys(
        output,
        {
            "ocr_identity",
            "transcript_hash",
            "article_set_hash",
            "issue_coverage_complete",
            "missing_substantive_spans",
            "missing_articles",
            "articles",
        },
        "article_review_output_invalid",
    )
    if output["ocr_identity"] != transcript.ocr_identity:
        raise ArticleReviewError("review_ocr_lineage_mismatch")
    if output["transcript_hash"] != transcript_hash:
        raise ArticleReviewError("review_transcript_lineage_mismatch")
    if output["article_set_hash"] != article_set_hash:
        raise ArticleReviewError("review_article_set_lineage_mismatch")
    issue_coverage_complete = _require_bool(
        output["issue_coverage_complete"], "article_issue_coverage_invalid"
    )
    missing_articles = _require_string_list(
        output["missing_articles"], "article_missing_articles_invalid"
    )
    raw_missing_spans = output["missing_substantive_spans"]
    if not isinstance(raw_missing_spans, list):
        raise ArticleReviewError("article_missing_spans_invalid")
    missing_spans: list[tuple[int, int, str]] = []
    for raw_span in raw_missing_spans:
        span = _require_exact_keys(
            raw_span,
            {"transcript_start", "transcript_end", "reason"},
            "article_missing_spans_invalid",
        )
        start = _require_int(span["transcript_start"], "article_missing_spans_invalid")
        end = _require_int(span["transcript_end"], "article_missing_spans_invalid")
        reason = _require_nonempty(span["reason"], "article_missing_spans_invalid")
        if start < 0 or end <= start or end > len(transcript.text):
            raise ArticleReviewError("article_missing_spans_invalid")
        missing_spans.append((start, end, reason))
    if issue_coverage_complete != (not missing_spans and not missing_articles):
        raise ArticleReviewError("article_issue_coverage_inconsistent")
    raw_reviews = output["articles"]
    if not isinstance(raw_reviews, list):
        raise ArticleReviewError("review_articles_invalid")
    expected_ids = [article.article_id for article in manifest.articles]
    review_ids = [
        raw.get("article_id") if isinstance(raw, Mapping) else None for raw in raw_reviews
    ]
    if review_ids != expected_ids:
        raise ArticleReviewError("review_article_reconciliation_failed")

    review_keys = {
        "article_id",
        "start_coherent",
        "end_coherent",
        "transitions_ok",
        "omissions",
        "duplications",
        "adjacent_bleed",
        "attribution_ok",
        "failure_reasons",
    }
    reviewed_articles: list[ArticleRecord] = []
    quarantine_reasons: list[str] = []
    for missing_article in missing_articles:
        quarantine_reasons.append(f"missing_article:{missing_article}")
    for start, end, reason in missing_spans:
        quarantine_reasons.append(
            f"missing_substantive_span:{start}:{end}:{reason}"
        )
    for article, raw in zip(manifest.articles, raw_reviews):
        review = _require_exact_keys(raw, review_keys, "article_review_invalid")
        start_coherent = _require_bool(review["start_coherent"], "article_review_invalid")
        end_coherent = _require_bool(review["end_coherent"], "article_review_invalid")
        transitions_ok = _require_bool(review["transitions_ok"], "article_review_invalid")
        omissions = _require_string_list(review["omissions"], "article_review_invalid")
        duplications = _require_string_list(review["duplications"], "article_review_invalid")
        adjacent_bleed = _require_string_list(review["adjacent_bleed"], "article_review_invalid")
        attribution_ok = _require_bool(review["attribution_ok"], "article_review_invalid")
        raw_failure_reasons = _require_mapping(
            review["failure_reasons"], "article_failure_reasons_invalid"
        )
        verdict = (
            start_coherent
            and end_coherent
            and transitions_ok
            and not omissions
            and not duplications
            and not adjacent_bleed
            and attribution_ok
        )
        failed_fields = {
            field
            for field, failed in (
                ("start_coherent", not start_coherent),
                ("end_coherent", not end_coherent),
                ("transitions_ok", not transitions_ok),
                ("omissions", bool(omissions)),
                ("duplications", bool(duplications)),
                ("adjacent_bleed", bool(adjacent_bleed)),
                ("attribution_ok", not attribution_ok),
            )
            if failed
        }
        if any(field not in _SEMANTIC_FIELDS for field in raw_failure_reasons):
            raise ArticleReviewError("article_failure_reasons_invalid")
        failure_reasons = {
            field: _require_nonempty(
                raw_failure_reasons[field], "article_failure_reasons_invalid"
            )
            for field in _SEMANTIC_FIELDS
            if field in raw_failure_reasons and raw_failure_reasons[field] is not None
        }
        if set(failure_reasons) != failed_fields:
            raise ArticleReviewError("article_failure_reasons_invalid")
        reasons = tuple(failure_reasons.values())
        reviewed = replace(
            article,
            start_coherent=start_coherent,
            end_coherent=end_coherent,
            transitions_ok=transitions_ok,
            omissions=omissions,
            duplications=duplications,
            adjacent_bleed=adjacent_bleed,
            attribution_ok=attribution_ok,
            verdict=verdict,
            failure_reasons=failure_reasons,
            reasons=reasons,
        )
        reviewed.validate(transcript.text)
        reviewed_articles.append(reviewed)
        if not verdict:
            for reason in reasons:
                if reason not in quarantine_reasons:
                    quarantine_reasons.append(reason)

    status = "quarantined" if quarantine_reasons else "passed"
    reviewed_manifest = replace(
        manifest,
        articles=tuple(reviewed_articles),
        reviewer_model=ARTICLE_MODEL,
        reviewer_prompt_fingerprint=_config_fingerprint(_review_config()),
        reviewer_usage=usage,
        reviewer_cost_usd=cost,
        issue_coverage_complete=issue_coverage_complete,
        missing_substantive_spans=tuple(missing_spans),
        missing_articles=missing_articles,
        status=status,
        quarantine_reasons=tuple(quarantine_reasons),
    )
    reviewed_manifest.validate()
    return reviewed_manifest
