"""Backpressure controls: provider rate-limit reservation + spend ceiling.

Both are horizontally correct -- they coordinate across every worker through
shared DB rows, so raising the worker count never over-runs a ceiling.

Rate limiting is reserve-before / reconcile-after against a rolling per-minute
bucket (provider_rate_usage). A worker reserves an ESTIMATE before calling the
model; if the reservation would breach RPM/ITPM/OTPM it is refused and the job
is deferred (run_after -> next minute) rather than run -- this is both the rate
ceiling and backpressure. After the call it reconciles estimate -> actual.

The spend ceiling is a running SUM(cost_usd) over the configured window vs
config.spend_ceiling_usd, checked BEFORE claiming/generating. When breached,
workers stop claiming and jobs stay queued -- the demonstrable halt in Phase 5.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from typing import Optional

from .config import AsyncAnswerConfig, _window_interval
from .db import dict_cursor

# A conservative default estimate when the caller has no better guess. Sized to
# a normal answer (~4k in / ~1.2k out from the cost audit) so a reservation is
# neither wildly over nor under.
DEFAULT_EST_INPUT_TOKENS = 4000
DEFAULT_EST_OUTPUT_TOKENS = 1500


def reserve_rate(
    db,
    cfg: AsyncAnswerConfig,
    est_input_tokens: int = DEFAULT_EST_INPUT_TOKENS,
    est_output_tokens: int = DEFAULT_EST_OUTPUT_TOKENS,
) -> bool:
    """Atomically reserve one request + estimated tokens against the current
    minute bucket. Returns True if within RPM/ITPM/OTPM (reservation applied),
    False if it would breach any ceiling (nothing reserved -> caller defers).

    NULL ceilings mean unlimited. The whole check-and-increment runs under a row
    lock on the minute bucket so concurrent workers cannot both slip past a
    ceiling."""
    if cfg.rpm_limit is None and cfg.itpm_limit is None and cfg.otpm_limit is None:
        return True  # no rate ceilings configured

    def _reserve(conn):
        with dict_cursor(conn) as cur:
            # Lock (or create) this minute's bucket.
            cur.execute(
                "INSERT INTO provider_rate_usage (bucket_minute) "
                "VALUES (date_trunc('minute', now())) "
                "ON CONFLICT (bucket_minute) DO NOTHING"
            )
            cur.execute(
                "SELECT requests, input_tokens, output_tokens FROM provider_rate_usage "
                "WHERE bucket_minute = date_trunc('minute', now()) FOR UPDATE"
            )
            row = cur.fetchone()
            requests = int(row["requests"])
            in_tok = int(row["input_tokens"])
            out_tok = int(row["output_tokens"])

            if cfg.rpm_limit is not None and requests + 1 > cfg.rpm_limit:
                return False
            if cfg.itpm_limit is not None and in_tok + est_input_tokens > cfg.itpm_limit:
                return False
            if cfg.otpm_limit is not None and out_tok + est_output_tokens > cfg.otpm_limit:
                return False

            cur.execute(
                "UPDATE provider_rate_usage SET requests = requests + 1, "
                "input_tokens = input_tokens + %s, output_tokens = output_tokens + %s, "
                "updated_at = now() WHERE bucket_minute = date_trunc('minute', now())",
                (est_input_tokens, est_output_tokens),
            )
            return True

    return db.run(_reserve)


def reconcile_rate(
    db,
    est_input_tokens: int,
    est_output_tokens: int,
    actual_input_tokens: int,
    actual_output_tokens: int,
) -> None:
    """Adjust the current minute bucket by (actual - estimate) after a call.
    Clamped at zero so a large over-estimate can't drive a counter negative.
    Best-effort: a reconcile failure never fails the job."""
    d_in = actual_input_tokens - est_input_tokens
    d_out = actual_output_tokens - est_output_tokens
    if d_in == 0 and d_out == 0:
        return

    def _reconcile(conn):
        with dict_cursor(conn) as cur:
            cur.execute(
                "UPDATE provider_rate_usage "
                "SET input_tokens = GREATEST(0, input_tokens + %s), "
                "    output_tokens = GREATEST(0, output_tokens + %s), "
                "    updated_at = now() "
                "WHERE bucket_minute = date_trunc('minute', now())",
                (d_in, d_out),
            )

    try:
        db.run(_reconcile)
    except Exception:
        pass


def spend_in_window(db, cfg: AsyncAnswerConfig) -> float:
    """Cumulative cost_usd over the configured spend window."""
    interval = _window_interval(cfg.spend_window)

    def _sum(conn):
        with dict_cursor(conn) as cur:
            if interval is None:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM answer_jobs "
                    "WHERE cost_usd IS NOT NULL"
                )
            else:
                cur.execute(
                    "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM answer_jobs "
                    "WHERE cost_usd IS NOT NULL AND finished_at >= now() - %s::interval",
                    (interval,),
                )
            return cur.fetchone()["s"]

    return float(db.run(_sum))


def spend_ok(db, cfg: AsyncAnswerConfig) -> bool:
    """True if there is spend headroom (or no ceiling configured)."""
    if cfg.spend_ceiling_usd is None:
        return True
    return spend_in_window(db, cfg) < cfg.spend_ceiling_usd
