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

Interim tightening (2026-07-10, Approach A -- read deterministic_gate.py's
module docstring in git history / rhemata-status.md for the full writeup):
rule 1 previously fired on ANY completion-word match regardless of whether a
write actually happened, so an ordinary read-only diagnostic report ("done,"
"successfully found") got held to write-reconciliation rules it can't and
shouldn't satisfy. Fix: a report may declare `WORK_TYPE: read-only` to skip
rule 1/2 entirely, but ONLY if no independent write-indicating vocabulary
appears anywhere in the message -- label and content must agree, or the
exemption doesn't apply and full reconciliation rules run exactly as before.
No marker, an explicit `WORK_TYPE: write` marker, or a label/content
disagreement all fail closed into unchanged behavior.

This is self-attested (prose declaring itself, prose cross-checked against
more prose) and does NOT close the false-negative gap the way real
tool-invocation tracking would (Approach B: read what guard_pretooluse.py
actually observed via PreToolUse, deferred). Acceptable now because no write
work runs through this loop yet; NOT acceptable once the chokepoint band
(#6-13) starts writing to the corpus through it -- Approach B is a hard
prerequisite before that point, not an optional hardening.

Approach B, piece 2b-ii (2026-07-11): check_reconciliation()'s prose check
is no longer the primary decision -- check_recorded_writes() is. It reads
guard_pretooluse.py's session-keyed state file at SubagentStop and decides
from what was actually observed via PreToolUse, not from what the executor
said about itself. Record-primary: any real write record halts directly,
naming what was written, and check_reconciliation() never runs for that
case. check_reconciliation() now only fires as a scoped fallback (a script
ran, contents unseen, no write record either way) or as a fail-closed
default (session_id or the state file itself couldn't be resolved/read).
Two exit conditions remain before this bridge retires and the gate
collapses to record-only -- see check_recorded_writes()'s docstring and
PLAN.md #5.5.

Exit 0 with a JSON {"decision":"block","reason":...} on stdout blocks the
subagent from stopping. Exit 0 with no output (or {}) allows it.
"""
import json
import os
import re
import sys


def block(reason: str) -> None:
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def allow() -> None:
    sys.exit(0)


# Piece 2b-ii (#5.5): must match guard_pretooluse.py's WRITE_STATE_DIR
# exactly -- these are two independent standalone hook scripts with no
# shared module, so this string is duplicated, not imported. If one changes,
# the other must change too; nothing enforces that automatically. Flagged
# as a real (small) maintenance risk, not hidden.
WRITE_STATE_DIR = "/tmp/rhemata-harness-writes"


COMPLETION_WORDS = re.compile(
    r"\b(stored|inserted|ingested|wrote|written|backfilled|completed|complete|"
    r"succeeded|success|successfully|done)\b",
    re.IGNORECASE,
)

# Interim tightening (Approach A, 2026-07-10): an executor report may declare
# its own work type. Must be its own line (not just the substring anywhere in
# running prose) to count as a real declaration rather than an incidental
# mention.
WORK_TYPE_MARKER = re.compile(
    r"^\s*WORK_TYPE:\s*(read-only|write)\s*$", re.IGNORECASE | re.MULTILINE
)

# Independent of COMPLETION_WORDS on purpose -- this is what a `WORK_TYPE:
# read-only` label is cross-checked against. If a "read-only" report actually
# describes a write, one of these should be present; a report that mislabels
# itself doesn't get to skip reconciliation just by asserting it.
WRITE_VOCAB_WORDS = re.compile(
    r"\b(insert(?:ed|ing)?|updat(?:e|ed|ing)|delet(?:e|ed|ing)|"
    r"migrat(?:e|ed|ing|ion)|ingest(?:ed|ing)?|backfill(?:ed|ing)?|"
    r"upsert(?:ed|ing)?|stored?|row(?:s)?\s+(?:added|created)|"
    r"wrote\s+to\s+(?:the\s+)?(?:db|database)|"
    r"written\s+to\s+(?:the\s+)?(?:db|database))\b",
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
    """Rules 1 and 2: all-four-present, and arithmetic consistency.

    Interim tightening (Approach A): `WORK_TYPE: read-only` exempts a report
    from this check, but only when no independent write-indicating vocabulary
    contradicts the label -- see module docstring for the full rationale and
    the Approach B follow-up this defers to."""
    if not COMPLETION_WORDS.search(message):
        return None  # no completion claim in this report -- nothing to check

    marker = WORK_TYPE_MARKER.search(message)
    if (
        marker
        and marker.group(1).lower() == "read-only"
        and not WRITE_VOCAB_WORDS.search(message)
    ):
        return None  # declared read-only, nothing in the message contradicts it

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


def check_recorded_writes(payload: dict):
    """Piece 2b-ii (#5.5): the new primary decision. Reads
    guard_pretooluse.py's session-keyed state file instead of trusting
    check_reconciliation()'s prose check. Record-primary: a real write
    record halts directly and check_reconciliation() never runs for that
    case -- the record alone decides. Falls back to check_reconciliation()
    only when a script ran and produced no write record (the recorder can't
    see inside a script), or when session_id/the state file itself can't be
    resolved or read at all (an unreadable state is not trustworthy ground
    truth -- fail closed to prose rather than silently treat it as clean).
    A missing or empty file is NOT a failure: no records means no writes
    happened, so that case stays quiet without consulting prose at all."""
    session_id = payload.get("session_id")
    message = payload.get("last_assistant_message") or ""

    if not session_id:
        # Can't even identify which state file belongs to this run --
        # don't trust a read we couldn't attempt. Fail closed to prose.
        return check_reconciliation(message)

    path = os.path.join(WRITE_STATE_DIR, f"{session_id}.jsonl")
    if not os.path.exists(path):
        # No file at all -- nothing was ever recorded for this run. Clean.
        return None

    try:
        with open(path) as f:
            lines = [line.strip() for line in f if line.strip()]
        records = [json.loads(line) for line in lines]
    except Exception:
        # File exists but couldn't be opened/parsed cleanly -- a corrupted
        # or unreadable state is not trustworthy ground truth. Fail closed
        # to prose rather than silently treat garbage as "no writes."
        return check_reconciliation(message)

    if not records:
        # File exists but is empty -- same as missing: no writes happened.
        return None

    write_records = [r for r in records if "kind" not in r]
    script_records = [r for r in records if r.get("kind") == "script_invocation"]

    if write_records:
        # Record-primary: an observed write beats any prose claim. Do NOT
        # run check_reconciliation() here -- the record alone decides, even
        # if a script marker also exists for this run (e.g.
        # `python3 ingest.py > log.txt` produces both; the write wins).
        items = [
            f"{r.get('tool_name', '?')}: {r.get('target') or r.get('command') or '(unspecified)'}"
            for r in write_records
        ]
        return (
            "Approach B (#5.5 piece 2b-ii): guard_pretooluse.py's PreToolUse "
            f"recorder observed {len(write_records)} real write-class tool "
            "call(s) this run -- " + "; ".join(items) + ". This halts on an "
            "observed fact, not a self-reported claim -- prose (WORK_TYPE, "
            "reconciliation counts) is not consulted for this decision."
        )

    if script_records:
        # TEMPORARY BRIDGE (#5.5 piece 2b-ii), not permanent: the recorder
        # cannot see inside a script invocation (guard_pretooluse.py's
        # BASH_WRITE_INDICATORS has no visibility into what a script does
        # internally), so when a script ran and produced no write record,
        # fall back to the prose-based check_reconciliation() for THIS run
        # only. This bridge retires once a script allowlist (like
        # check_rule_10_freeze's named scripts, in guard_pretooluse.py)
        # lets the recorder positively identify write-capable scripts --
        # at that point the gate collapses to record-only and this branch
        # goes away.
        return check_reconciliation(message)

    # No write record, no script marker for this run -- ground truth is
    # clean. NOTE: this is ground truth only for Bash/Edit/Write tool
    # calls. MCP write tools (e.g. Supabase execute_sql, apply_migration)
    # are NOT recorded by the current PreToolUse wiring -- settings.json's
    # PreToolUse matcher only covers Edit|Write and Bash -- so an MCP write
    # bypasses this gate entirely today. Closing that is a separate
    # recorder-side exit condition for #5.5, not yet built.
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

    # Piece 2b-ii (#5.5): the primary decision now comes from recorded tool
    # invocations, not the executor's self-reported prose. check_reconciliation()
    # only runs indirectly, as check_recorded_writes()'s scoped fallback/fail-closed
    # path -- it is no longer called unconditionally here.
    reason = check_recorded_writes(payload)
    if reason:
        block(reason)
        return

    message = payload.get("last_assistant_message") or ""
    for check in (
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
