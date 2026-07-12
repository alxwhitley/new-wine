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

Piece A/B rework (#5.5 exit condition (a), 2026-07-13): both remaining
pieces of prose-trust inside check_recorded_writes() are retired. The
self-declared WORK_TYPE label is no longer read anywhere in that function --
replaced by a per-write match-check between recorded targets and what the
report actually describes (Piece A), blocking only on a write the report
never accounts for. The script-invocation prose bridge is replaced too:
guard_pretooluse.py now recognizes known write-capable scripts directly
(Piece B), and a genuinely unrecognized script is marked visibly
unverifiable instead of falling back to prose. check_reconciliation()
remains wired only as the fail-closed default when the state file itself
can't be resolved or read at all. Independently verifying claimed
reconciliation NUMBERS against the database is explicitly out of scope here
-- noted as adjacent, still open.

Exit 0 with a JSON {"decision":"block","reason":...} on stdout blocks the
subagent from stopping. Exit 0 with no output (or {}) allows it.
"""
import datetime
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


# Piece A (#5.5 exit condition (a), 2026-07-13): extracts specific, nameable
# things a report would need to mention to plausibly be describing a given
# recorded write. Deliberately narrow to concrete referents (a filename, a
# stem) -- no generic operation-word fallback, since a bare operation word
# ("did some updates") is exactly the non-specific case that must NOT count
# as accounting for a write. Matches a path-like or filename-like fragment;
# falls back to the last whitespace-separated token in the record's text if
# no such fragment exists (e.g. a bare "mkdir somedir" with no extension).
_PATH_TOKEN = re.compile(r"[\w./-]+\.\w+|[\w-]+/[\w./-]+")


def _referents_for(record: dict) -> list:
    text = record.get("target") or record.get("command") or ""
    tokens = _PATH_TOKEN.findall(text)
    if not tokens:
        tokens = text.strip().split()[-1:]
    referents = []
    for token in tokens:
        base = os.path.basename(token.strip("'\""))
        if not base:
            continue
        stem = base.rsplit(".", 1)[0] if "." in base else base
        for candidate in (base, stem):
            if len(candidate) >= 4:  # skip trivial/near-universal fragments
                referents.append(candidate.lower())
    return referents


def _write_is_accounted_for(record: dict, message: str) -> bool:
    """Piece A: does the report reference this specific recorded write in
    recognizable terms? Forgiving on FORM (no exact string, no declaration
    line required) but strict on SPECIFICITY (a referent must actually be
    findable and named -- presence with nothing to check against fails
    closed, which is what keeps a generic "did some updates" from counting
    as accounting for any specific write)."""
    referents = _referents_for(record)
    if not referents:
        return False
    lowered = message.lower()
    return any(r in lowered for r in referents)


def record_claimed_but_unrecorded(payload: dict, message: str) -> None:
    """Piece A: the reverse-direction case -- a report uses write-claiming
    language but this agent has no recorded writes to back it up. Not a
    safety failure (principle 5: broad detection for mistakes, not
    adversarial denial) -- over-claiming isn't what this gate blocks on.
    Logged visibly so it isn't silently invisible; same session log,
    distinct kind. Never raises -- a logging failure must never change the
    gate's allow decision."""
    try:
        session_id = payload.get("session_id") or "unknown-session"
        record = {
            "kind": "claimed_but_unrecorded",
            "session_id": session_id,
            "agent_id": payload.get("agent_id") or "unknown-agent",
            "agent_type": payload.get("agent_type"),
            "message_excerpt": message[:500],
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        os.makedirs(WRITE_STATE_DIR, exist_ok=True)
        path = os.path.join(WRITE_STATE_DIR, f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def record_unverifiable_stop(payload: dict, script_records: list) -> None:
    """Piece A/B (#5.5 exit condition (a)): a script ran that
    guard_pretooluse.py's KNOWN_WRITE_SCRIPTS didn't recognize -- no write
    record either way, genuinely unverifiable. Never silently passed as if
    verified, never resolved by falling back to prose (that was the
    original script-invocation prose bridge this exit condition names).
    Logged visibly instead, same session log, distinct kind. Never raises."""
    try:
        session_id = payload.get("session_id") or "unknown-session"
        record = {
            "kind": "unverifiable_stop",
            "session_id": session_id,
            "agent_id": payload.get("agent_id") or "unknown-agent",
            "agent_type": payload.get("agent_type"),
            "commands": [r.get("command") for r in script_records],
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        os.makedirs(WRITE_STATE_DIR, exist_ok=True)
        path = os.path.join(WRITE_STATE_DIR, f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def check_recorded_writes(payload: dict):
    """Piece A/B rework (#5.5 exit condition (a), 2026-07-13): reads
    guard_pretooluse.py's session-keyed state file, scoped to the finishing
    agent's own records (bug #1 fix). Blocks ONLY on a provable mismatch --
    a recorded write this agent's own report does not account for in
    recognizable terms (Piece A). No self-declared WORK_TYPE label is
    consulted anywhere in this function anymore; principle 2 (prose is
    never the trusted signal) is honored for this decision path. Known
    write-capable script invocations (Piece B, guard_pretooluse.py's
    KNOWN_WRITE_SCRIPTS) arrive here as ordinary write records, judged the
    same way. Unrecognized script invocations with no write record are
    marked visibly unverifiable rather than falling back to prose. A report
    that claims write-shaped work with nothing recorded to back it up is
    logged visibly (claimed-but-unrecorded) but never blocked -- that
    direction isn't a safety failure. check_reconciliation() remains wired
    only as a fail-closed default when the state file itself can't be
    resolved or read -- an unreadable state is not trustworthy ground
    truth, a different and much rarer case than "ran but unverified"."""
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

    # Bug #1 fix (2026-07-12): scope to the finishing agent's own records
    # only. The write-state log is one file per SESSION, shared by every
    # agent dispatched in it -- without this filter, a later agent inherits
    # every earlier agent's writes as if they were its own. Confirmed live
    # via a probe (2026-07-12): the SubagentStop payload already carries the
    # finishing agent's own agent_id on every real decision, and every
    # written record already carries the same field (guard_pretooluse.py) --
    # this is a pure filter, no new identity capture needed anywhere.
    agent_id = payload.get("agent_id")
    records = [r for r in records if r.get("agent_id") == agent_id]

    if not records:
        # No records belonging to THIS agent. Piece A (2026-07-13): a report
        # can still SAY it made a write with nothing recorded to back it up
        # -- over-claiming isn't a safety risk, but it shouldn't pass
        # silently either. Log it visibly, then allow either way.
        if WRITE_VOCAB_WORDS.search(message):
            record_claimed_but_unrecorded(payload, message)
        return None

    write_records = [r for r in records if "kind" not in r]
    script_records = [r for r in records if r.get("kind") == "script_invocation"]

    if write_records:
        # Piece A (2026-07-13): block ONLY on a provable mismatch -- a
        # recorded write this report does not account for in recognizable
        # terms. No WORK_TYPE label is read here at all; principle 2 (prose
        # is never the trusted signal) applies to this decision. Checked
        # per-write, not in aggregate: five writes with four accounted for
        # is still a block, naming the fifth.
        unaccounted = [r for r in write_records if not _write_is_accounted_for(r, message)]
        if not unaccounted:
            return None

        items = [
            f"{r.get('tool_name', '?')}: {r.get('target') or r.get('command') or '(unspecified)'}"
            for r in unaccounted
        ]
        return (
            "Piece A (#5.5 exit condition (a)): guard_pretooluse.py's PreToolUse "
            f"recorder observed {len(unaccounted)} of {len(write_records)} real "
            "write-class tool call(s) this run that this report does not account "
            "for in recognizable terms -- " + "; ".join(items) + ". Silent/"
            "undisclosed writes are the one thing this gate blocks on "
            "(principle 1: mismatch-only). Describe what was written -- the "
            "file, or a clearly-named target -- and resubmit. No particular "
            "declaration line is required; the description just has to name "
            "what actually happened."
        )

    if script_records:
        # Piece B (2026-07-13): what's left of the former "script ran,
        # contents unseen" blind spot after guard_pretooluse.py's
        # KNOWN_WRITE_SCRIPTS started recognizing known write-capable
        # scripts directly (those now land in write_records above and never
        # reach here). What remains here is a genuinely UNRECOGNIZED script
        # -- no proof either way. Per principle 2 this no longer falls back
        # to check_reconciliation() (that WAS the original
        # script-invocation prose bridge this exit condition named). Per
        # principle 5 (fallible, not adversarial; hard denial only for the
        # genuinely irreversible), an unproven ambiguity is not a reason to
        # block. Marked visibly instead of guessed at either way.
        record_unverifiable_stop(payload, script_records)
        return None

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
