"""The async answer path's control plane -- the one-row `async_answer_config`.

Every dial (pause, backpressure ceiling, reuse TTL, provider rate ceilings,
spend ceiling, lease length) lives in a single DB row so a change applies
across the whole worker fleet without a redeploy. Read fresh each poll; there
is no in-process cache to go stale.

Also holds the per-answer cost model. `claude-sonnet-4-5` (the model the live
path uses, unchanged here) is Sonnet-tier: $3 / MTok input, $15 / MTok output,
cache reads ~0.1x input, cache writes ~1.25x input. These are OVERRIDABLE
constants, not a hardcoded truth -- the measured per-answer median of $0.039
(docs/audits/per_answer_cost_measurement_2026-08-03.md) is the ground-truth
sanity check.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .db import dict_cursor

# ---- cost model (per million tokens, USD) --------------------------------
# Overridable; keep in sync with the answer-generation model in chat.py.
COST_MODEL = "claude-sonnet-4-5"
USD_PER_MTOK_INPUT = 3.0
USD_PER_MTOK_OUTPUT = 15.0
CACHE_READ_MULTIPLIER = 0.1   # cache_read_input_tokens billed ~0.1x input
CACHE_WRITE_MULTIPLIER = 1.25  # cache_creation_input_tokens billed ~1.25x input


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Cost of one generation from its token usage. `input_tokens` is the
    uncached remainder (matches the Anthropic usage object: total prompt =
    input + cache_read + cache_write)."""
    return (
        (input_tokens / 1_000_000.0) * USD_PER_MTOK_INPUT
        + (output_tokens / 1_000_000.0) * USD_PER_MTOK_OUTPUT
        + (cache_read_tokens / 1_000_000.0) * USD_PER_MTOK_INPUT * CACHE_READ_MULTIPLIER
        + (cache_write_tokens / 1_000_000.0) * USD_PER_MTOK_INPUT * CACHE_WRITE_MULTIPLIER
    )


@dataclass
class AsyncAnswerConfig:
    paused: bool = False
    max_queue_depth: int = 5000
    reuse_ttl_seconds: int = 0
    rpm_limit: Optional[int] = None
    itpm_limit: Optional[int] = None
    otpm_limit: Optional[int] = None
    spend_ceiling_usd: Optional[float] = None
    spend_window: str = "rolling_24h"
    lease_seconds: int = 300


def load_config(db) -> AsyncAnswerConfig:
    """Read the singleton config row (id=1). Returns defaults if the row is
    somehow absent -- fail toward conservative behaviour, never crash a worker
    on a missing dial."""
    def _read(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "SELECT paused, max_queue_depth, reuse_ttl_seconds, rpm_limit, "
                "itpm_limit, otpm_limit, spend_ceiling_usd, spend_window, "
                "lease_seconds FROM async_answer_config WHERE id = 1"
            )
            return cur.fetchone()

    row = db.run(_read)
    if not row:
        return AsyncAnswerConfig()
    return AsyncAnswerConfig(
        paused=bool(row["paused"]),
        max_queue_depth=int(row["max_queue_depth"]),
        reuse_ttl_seconds=int(row["reuse_ttl_seconds"]),
        rpm_limit=row["rpm_limit"],
        itpm_limit=row["itpm_limit"],
        otpm_limit=row["otpm_limit"],
        spend_ceiling_usd=(
            float(row["spend_ceiling_usd"]) if row["spend_ceiling_usd"] is not None else None
        ),
        spend_window=row["spend_window"],
        lease_seconds=int(row["lease_seconds"]),
    )


def _window_interval(spend_window: str) -> Optional[str]:
    """SQL interval string for a spend window, or None for 'total'."""
    if spend_window == "rolling_24h":
        return "24 hours"
    if spend_window == "rolling_1h":
        return "1 hour"
    return None
