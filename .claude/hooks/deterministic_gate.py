#!/usr/bin/env python3
"""
SubagentStop hook, scoped (via .claude/settings.json's matcher) to agent_type
"executor". Cheap, deterministic checks only -- no judgment. Anything these
checks can't decide passes through and escalates to the planner-reviewer agent,
which the orchestrator invokes separately once this hook allows the stop.

Rules enforced here, each traceable to a specific repo lesson:
  1. Any write/batch completion claim must state ALL FOUR reconciliation numbers
     (attempted/stored/errored/skipped) explicitly -- PLAN.md Standing Rule 3,
     strengthened per Alex's 2026-07-10 review: a partial count (e.g. "stored: 8,
     no errors") is exactly the failure mode a weak executor produces and must
     block, not pass.
  2. If all four numbers are present, they must be arithmetically consistent:
     stored + errored + skipped == attempted. PLAN.md Standing Rule 3.
  3. A full-batch/backfill claim without a preceding dry-run/single-item mention
     is blocked. PLAN.md Standing Rule 2.
  4. A semicolon inside a `--` SQL comment line is blocked. CLAUDE.md's
     Migration 051 gotcha.

Exit 0 with a JSON {"decision":"block","reason":...} on stdout blocks the
subagent from stopping. Exit 0 with no output (or {}) allows it.
"""
import json
import re
import sys


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def allow() -> None:
    sys.exit(0)


COMPLETION_WORDS = re.compile(
    r"\b(stored|inserted|ingested|wrote|written|backfilled|completed|complete|"
    r"succeeded|success|successfully|done)\b",
    re.IGNORECASE,
)

RECONCILIATION_FIELDS = {
    "attempted": re.compile(r"\battempted[:\s]+(\d+)", re.IGNORECASE),
    "stored": re.compile(r"\bstored[:\s]+(\d+)", re.IGNORECASE),
    "errored": re.compile(r"\berrored[:\s]+(\d+)", re.IGNORECASE),
    "skipped": re.compile(r"\bskipped[:\s]+(\d+)", re.IGNORECASE),
}

BATCH_SCALE_WORDS = re.compile(
    r"\b(full batch|backfill|bulk|all\s+\d+\s+documents|entire corpus)\b",
    re.IGNORECASE,
)

DRY_RUN_WORDS = re.compile(
    r"\b(dry[\s-]?run|single[\s-]?item|pilot batch|one[\s-]?item)\b",
    re.IGNORECASE,
)

# A `--` SQL comment that also contains a literal semicolon on the same line.
SEMICOLON_IN_COMMENT = re.compile(r"--[^\n]*;")


def check_reconciliation(message: str):
    """Rules 1 and 2: all-four-present, and arithmetic consistency."""
    if not COMPLETION_WORDS.search(message):
        return None  # no completion claim in this report -- nothing to check

    found = {}
    for field, pattern in RECONCILIATION_FIELDS.items():
        m = pattern.search(message)
        if m:
            found[field] = int(m.group(1))

    missing = [f for f in RECONCILIATION_FIELDS if f not in found]
    if missing:
        return (
            "Rule 3 (PLAN.md:27): a write/batch completion claim must state ALL "
            "FOUR of attempted/stored/errored/skipped explicitly -- missing: "
            + ", ".join(missing)
            + ". A 'success' with no count (or a partial count) is not a success."
        )

    attempted, stored, errored, skipped = (
        found["attempted"],
        found["stored"],
        found["errored"],
        found["skipped"],
    )
    if stored + errored + skipped != attempted:
        return (
            "Rule 3 (PLAN.md:27): reconciliation arithmetic mismatch -- "
            f"stored({stored}) + errored({errored}) + skipped({skipped}) = "
            f"{stored + errored + skipped}, but attempted = {attempted}. "
            f"{attempted - (stored + errored + skipped)} item(s) unaccounted for."
        )
    return None


def check_dry_run_before_batch(message: str):
    """Rule 2: full-batch claims need a preceding dry-run/single-item step."""
    if BATCH_SCALE_WORDS.search(message) and not DRY_RUN_WORDS.search(message):
        return (
            "Rule 2 (PLAN.md:26): 'Dry-run + single-item verification before any "
            "full batch.' This report claims batch/backfill-scale work with no "
            "dry-run or single-item verification mentioned."
        )
    return None


def check_semicolon_in_sql_comment(message: str):
    """Migration 051 gotcha: semicolon inside a `--` comment breaks multi-
    statement runners via silent rollback."""
    m = SEMICOLON_IN_COMMENT.search(message)
    if m:
        return (
            "Migration 051 gotcha (CLAUDE.md:343): a `--` SQL comment contains a "
            "literal semicolon ('" + m.group(0).strip() + "'), which naive "
            "multi-statement runners (incl. text.split(';')) treat as a statement "
            "terminator -- silent rollback risk. Never put a semicolon inside a "
            "SQL comment in a migration file."
        )
    return None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()
        return

    if payload.get("agent_type") != "executor":
        allow()
        return

    message = payload.get("last_assistant_message") or ""
    if not message:
        allow()
        return

    for check in (
        check_reconciliation,
        check_dry_run_before_batch,
        check_semicolon_in_sql_comment,
    ):
        reason = check(message)
        if reason:
            block(reason)
            return

    allow()


if __name__ == "__main__":
    main()
