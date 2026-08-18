"""LLM propose step for the quote quality pipeline (Settled #29 / Task 4).

Proposes exact substrings + passage-level taxonomy tags. Does not approve,
persist, or score authenticity — those stay in quote_quality (serveability)
and quote_verifier (provenance).

Prompt version is stamped on every proposal batch so a served quote's
propose path is reconstructable later.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional, Set

from app.constants import TAXONOMY_LIST, VALID_TAGS

PROMPT_VERSION = "quote_propose_v1"
DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_CANDIDATES_PER_WINDOW = 3
MAX_TOPIC_IDS = 3

# Rough published Sonnet-class rates used only for dry-run projection.
# Print the live numbers in the CLI header; do not treat as billing truth.
USD_PER_MTOK_INPUT = 3.0
USD_PER_MTOK_OUTPUT = 15.0

# Conservative per-call token guesses for cost projection when we have not
# measured the real prompt yet (taxonomy list dominates the system prompt).
EST_SYSTEM_TOKENS = 3500  # instructions + TAXONOMY_LIST
EST_OUTPUT_TOKENS_PER_CALL = 800


_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ProposedQuote:
    quote_text: str
    char_start: int
    char_end: int
    restated_point: str
    topic_ids: list[str]
    why_quotable: str
    standalone_ok: bool


@dataclass(frozen=True)
class ProposeBatch:
    prompt_version: str
    model: str
    window: str
    candidates: list[ProposedQuote]
    raw_response: str
    parse_errors: list[str]


def filter_topic_ids(
    raw_tags: Iterable[Any],
    *,
    valid_tags: Optional[Set[str]] = None,
    max_tags: int = MAX_TOPIC_IDS,
) -> list[str]:
    """Keep only tags that exist in VALID_TAGS (or an override set). Order preserved; deduped."""
    allowed = VALID_TAGS if valid_tags is None else valid_tags
    out: list[str] = []
    seen: set[str] = set()
    for tag in raw_tags:
        if not isinstance(tag, str):
            continue
        cleaned = tag.strip()
        if not cleaned or cleaned not in allowed or cleaned in seen:
            continue
        out.append(cleaned)
        seen.add(cleaned)
        if len(out) >= max_tags:
            break
    return out


def build_propose_prompt(source_window: str) -> tuple[str, str]:
    """Return (system, user) messages for one source window."""
    system = (
        "You extract standalone quotable passages from Christian teaching text "
        "for a citation-backed study product.\n\n"
        "Return ONLY valid JSON (no markdown fences, no preamble) with this shape:\n"
        "{\n"
        '  "candidates": [\n'
        "    {\n"
        '      "quote_text": "<exact contiguous substring of SOURCE>",\n'
        '      "char_start": <int, inclusive 0-based index into SOURCE>,\n'
        '      "char_end": <int, exclusive end index into SOURCE>,\n'
        '      "restated_point": "<one-sentence paraphrase of the claim>",\n'
        '      "topic_ids": ["<1-3 exact taxonomy tags>"],\n'
        '      "why_quotable": "<short reason this stands alone as a quote>",\n'
        '      "standalone_ok": true\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Propose at most %d candidates. Prefer fewer strong ones over many weak ones.\n"
        "- quote_text MUST be copied exactly from SOURCE; never invent or paraphrase the quote.\n"
        "- char_start/char_end MUST satisfy SOURCE[char_start:char_end] == quote_text.\n"
        "- Prefer 1–3 complete sentences that state a complete thought.\n"
        "- Refuse deictic openers (\"Verse 17…\", \"As I said…\") and mid-argument "
        "connectives that need surrounding context.\n"
        "- Do not span blank-line paragraph breaks.\n"
        "- topic_ids must be copied EXACTLY from the taxonomy below (1–3 tags). "
        "Unknown tags are discarded.\n"
        "- Set standalone_ok to false if the passage only works with surrounding context; "
        "prefer omitting such passages entirely.\n"
        "- If nothing is worth quoting, return {\"candidates\": []}.\n\n"
        "TAXONOMY (use ONLY these exact tags):\n"
        "%s\n\n"
        "prompt_version=%s"
    ) % (MAX_CANDIDATES_PER_WINDOW, TAXONOMY_LIST, PROMPT_VERSION)

    user = "SOURCE:\n%s" % source_window
    return system, user


def _strip_fences(raw: str) -> str:
    text = (raw or "").strip()
    fence = _FENCE_RE.search(text)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_candidates_payload(data: Any) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        cands = data.get("candidates")
        if isinstance(cands, list):
            return cands
    return []


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def parse_propose_response(
    raw: str,
    source_window: str,
    *,
    valid_tags: Optional[Set[str]] = None,
    max_candidates: int = MAX_CANDIDATES_PER_WINDOW,
) -> tuple[list[ProposedQuote], list[str]]:
    """Parse model JSON into ProposedQuote rows; drop invalids with reasons.

    Offset check is strict: window[char_start:char_end] must equal quote_text.
    Unknown taxonomy tags are filtered out; a candidate with zero remaining
    tags is refused.
    """
    errors: list[str] = []
    text = _strip_fences(raw)
    if not text:
        return [], ["empty_response"]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Best-effort: first JSON object/array in the blob.
        obj = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if not obj:
            return [], ["json_decode_failed"]
        try:
            data = json.loads(obj.group(1))
        except json.JSONDecodeError:
            return [], ["json_decode_failed"]

    raw_cands = _extract_candidates_payload(data)
    if not raw_cands:
        if isinstance(data, dict) and data.get("candidates") == []:
            return [], []
        errors.append("no_candidates_array")
        return [], errors

    accepted: list[ProposedQuote] = []
    for i, item in enumerate(raw_cands):
        if len(accepted) >= max_candidates:
            errors.append("candidate_%d_skipped_over_cap" % i)
            continue
        if not isinstance(item, dict):
            errors.append("candidate_%d_not_object" % i)
            continue

        quote_text = item.get("quote_text")
        if not isinstance(quote_text, str) or not quote_text:
            errors.append("candidate_%d_missing_quote_text" % i)
            continue
        # Model must not invent; keep exact text (no strip of internal content).
        # Leading/trailing whitespace-only repair is refused — authenticity
        # wants the exact span the offsets claim.
        try:
            char_start = int(item.get("char_start"))
            char_end = int(item.get("char_end"))
        except (TypeError, ValueError):
            errors.append("candidate_%d_bad_offsets" % i)
            continue

        # Models routinely emit wrong char offsets even when quote_text is an
        # exact copy. Prefer declared offsets when they match; otherwise recover
        # from a unique exact substring match. Ambiguous duplicates refuse —
        # never guess which occurrence was meant.
        if (
            0 <= char_start < char_end <= len(source_window)
            and source_window[char_start:char_end] == quote_text
        ):
            pass  # offsets already authoritative
        else:
            occurrences = source_window.count(quote_text)
            if occurrences == 1:
                char_start = source_window.index(quote_text)
                char_end = char_start + len(quote_text)
                errors.append("candidate_%d_offsets_repaired" % i)
            elif occurrences == 0:
                errors.append("candidate_%d_not_substring" % i)
                continue
            else:
                errors.append("candidate_%d_ambiguous_substring" % i)
                continue

        topic_ids = filter_topic_ids(
            item.get("topic_ids") or [],
            valid_tags=valid_tags,
        )
        if not topic_ids:
            errors.append("candidate_%d_no_valid_topic_ids" % i)
            continue

        restated = item.get("restated_point")
        if not isinstance(restated, str) or not restated.strip():
            errors.append("candidate_%d_missing_restated_point" % i)
            continue

        why = item.get("why_quotable")
        if not isinstance(why, str) or not why.strip():
            errors.append("candidate_%d_missing_why_quotable" % i)
            continue

        standalone_ok = _coerce_bool(item.get("standalone_ok"), default=True)

        accepted.append(
            ProposedQuote(
                quote_text=quote_text,
                char_start=char_start,
                char_end=char_end,
                restated_point=restated.strip(),
                topic_ids=topic_ids,
                why_quotable=why.strip(),
                standalone_ok=standalone_ok,
            )
        )

    return accepted, errors


def estimate_propose_cost_usd(
    *,
    n_windows: int,
    avg_window_chars: int,
    model: str = DEFAULT_MODEL,
    usd_per_mtok_input: float = USD_PER_MTOK_INPUT,
    usd_per_mtok_output: float = USD_PER_MTOK_OUTPUT,
) -> dict[str, float | int | str]:
    """Project $ for a propose pass from window counts (no API call)."""
    # ~4 chars/token rough English estimate for the SOURCE body.
    avg_window_tokens = max(1, int(avg_window_chars / 4))
    input_tokens = n_windows * (EST_SYSTEM_TOKENS + avg_window_tokens)
    output_tokens = n_windows * EST_OUTPUT_TOKENS_PER_CALL
    cost = (input_tokens / 1_000_000.0) * usd_per_mtok_input + (
        output_tokens / 1_000_000.0
    ) * usd_per_mtok_output
    return {
        "model": model,
        "n_windows": n_windows,
        "avg_window_chars": avg_window_chars,
        "est_input_tokens": input_tokens,
        "est_output_tokens": output_tokens,
        "usd_per_mtok_input": usd_per_mtok_input,
        "usd_per_mtok_output": usd_per_mtok_output,
        "est_cost_usd": round(cost, 4),
    }


def propose_from_window(
    source_window: str,
    *,
    model_fn: Optional[Callable[[str, str], str]] = None,
    model: str = DEFAULT_MODEL,
    valid_tags: Optional[Set[str]] = None,
    max_candidates: int = MAX_CANDIDATES_PER_WINDOW,
) -> ProposeBatch:
    """Run propose on one window.

    ``model_fn(system, user) -> raw_text`` is injectable for tests. When
    omitted, calls Anthropic with ``model``.
    """
    system, user = build_propose_prompt(source_window)
    if model_fn is None:
        raw = _default_anthropic_call(system, user, model=model)
    else:
        raw = model_fn(system, user)

    candidates, errors = parse_propose_response(
        raw,
        source_window,
        valid_tags=valid_tags,
        max_candidates=max_candidates,
    )
    return ProposeBatch(
        prompt_version=PROMPT_VERSION,
        model=model,
        window=source_window,
        candidates=candidates,
        raw_response=raw,
        parse_errors=errors,
    )


def _default_anthropic_call(system: str, user: str, *, model: str) -> str:
    import os

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    parts: list[str] = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
