#!/usr/bin/env python3
"""
PreToolUse hook, wired in .claude/settings.json for the Edit|Write and Bash
matchers. Single shared source of truth for the harness's three hard
constraints -- deliberately not duplicated into each agent's own frontmatter,
since redundant-and-drifting copies are themselves a silent-failure vector.

Scope: only acts when the calling agent's agent_type is "executor" or
"planner-reviewer" (subagent tool calls). The main session (no agent_type, or
an agent_type outside this set) is never blocked by this hook -- Alex's
explicit chat approval is the only gate on the orchestrator's own commits and
governed-file edits, same as it's always been.

Enforces:
  1. Never commits without Alex's explicit yes: denies git commit / git push /
     git reset --hard / git checkout -- for the two subagents, unconditionally.
  2. Read-and-propose only on the five governed files: denies Edit/Write whose
     target is CLAUDE.md, PLAN.md, POSITIONING.md, DESIGN.md, or
     rhemata-status.md, for the two subagents, unconditionally.
  3. PLAN.md Standing Rule 10 freeze: denies real (non-dry-run/non-test)
     invocation of the five PLAN.md-roadmap-#8-13 unconverted ingest scripts
     for the executor.

Session #5.5, Phase 3 piece 1 (2026-07-10) -- Approach B recording, NOT
gating yet: on every ALLOWED write-class call from a guarded agent, append a
record to a per-session state file keyed by agent_id. deterministic_gate.py
does not read this yet (piece 2). Recording never affects allow/deny --
wrapped in try/except, only ever called just before an allow() return, never
on a deny() path (a blocked write didn't happen, so it doesn't belong in a
ground-truth record). Write-class Bash detection (BASH_WRITE_INDICATORS) is
a NEW, first-pass, syntax-level heuristic -- flagged in code, not hidden:
it cannot see what a write-capable Python script does internally (e.g.
`python3 scripts/ingest.py` shows no SQL or redirection on its command
line), so real writes routed through an unflagged script will currently go
unrecorded. It also over-triggers on some non-writes (e.g. bare `2>&1`, or
the SQL verbs -- esp. CREATE/DROP/DELETE -- matching as bare words anywhere
in a command, so a read-only command that merely mentions one of those words
in English prose or in a file path will over-record too) -- deliberately
biased toward over-recording, since piece 1 only feeds a downstream gate
(piece 2), and over-recording is the safe direction of error here, not a
silent one.
"""
import datetime
import json
import os
import re
import sys

GOVERNED_FILES = {
    "CLAUDE.md",
    "PLAN.md",
    "POSITIONING.md",
    "DESIGN.md",
    "rhemata-status.md",
}

GUARDED_AGENT_TYPES = {"executor", "planner-reviewer"}

DESTRUCTIVE_GIT = re.compile(
    r"\bgit\s+(commit\b|push\b|reset\s+--hard\b|checkout\s+--\b)"
)

# PLAN.md roadmap #8-13 is authoritative (2026-07-10 call: supersedes the older
# 4-script list in CLAUDE.md's propositions-per-script section, which is stale).
UNCONVERTED_INGEST_SCRIPTS = re.compile(
    r"\b(ingest_magazine\.py|ingest_preceptaustin\.py|ingest_lexicon\.py|"
    r"ingest_commentaries\.py|ingest_helloao\.py)\b"
)

DRY_RUN_FLAG = re.compile(r"--dry-run|--test\b")

# Session #5.5 Phase 3 piece 1: write-class Bash detection. NEW, first-pass --
# see module docstring for known gaps (can't see inside a script; over-fires
# on some non-writes like bare `2>&1`). Not reused from elsewhere because
# nothing else in this file is a general-purpose write classifier.
BASH_WRITE_INDICATORS = re.compile(
    r">>?(?!=)"  # shell redirection (>, >>), not >=
    r"|\b(?:rm|mv|cp|touch|mkdir|tee|dd|truncate|chmod|chown)\b"  # file-mutating commands
    r"|\bsed\b[^|;&\n]*-i\b"  # sed -i (in-place edit)
    r"|\b(?:INSERT|UPDATE|DELETE|UPSERT|ALTER|DROP|MERGE|CREATE)\b",  # SQL mutation verbs
    re.IGNORECASE,
)

# Outside the repo entirely (not .claude/-relative) -- this is live-run-only
# state, consumed once at the same subagent's SubagentStop, not durable
# project data. Avoids needing a .gitignore entry or any risk of ever being
# committed. Keyed by session_id so concurrent/sequential runs don't collide.
WRITE_STATE_DIR = "/tmp/rhemata-harness-writes"


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def allow() -> None:
    sys.exit(0)


def check_governed_file_write(tool_input: dict):
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    for governed in GOVERNED_FILES:
        if path.endswith(governed):
            return (
                f"Governed file ({governed}) -- per CLAUDE.md's Project Knowledge "
                "Read Contract, chat/subagents never edit these five files "
                "directly. Propose the change as text in your report; the "
                "orchestrator relays it to Alex for approval and the terminal "
                "session applies it."
            )
    return None


def check_destructive_git(command: str):
    if DESTRUCTIVE_GIT.search(command):
        return (
            "Destructive/commit git command blocked for subagents. The loop "
            "never commits or pushes without Alex's explicit yes on a shown "
            "diff -- that step only ever happens from the orchestrating main "
            "session."
        )
    return None


def check_rule_10_freeze(command: str):
    m = UNCONVERTED_INGEST_SCRIPTS.search(command)
    if m and not DRY_RUN_FLAG.search(command):
        return (
            f"PLAN.md Standing Rule 10 freeze: '{m.group(1)}' is one of the five "
            "PLAN.md roadmap #8-13 scripts not yet converted through "
            "shared_ingest.py. New-source ingests through unconverted scripts "
            "are frozen until the chokepoint band clears. Re-run with "
            "--dry-run/--test, or stop and report the blocker instead."
        )
    return None


def is_write_class(tool_name: str, tool_input: dict) -> bool:
    """Session #5.5 Phase 3 piece 1: single source of truth for "is this
    call a write." Edit/Write are always write-class by definition; Bash is
    write-class iff BASH_WRITE_INDICATORS matches its command. See module
    docstring and BASH_WRITE_INDICATORS' comment for known gaps."""
    if tool_name in ("Edit", "Write"):
        return True
    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        return bool(BASH_WRITE_INDICATORS.search(command))
    return False


def record_write_class_call(payload: dict, tool_name: str, tool_input: dict) -> None:
    """Session #5.5 Phase 3 piece 1: append-only ground-truth record of a
    write-class call that was actually ALLOWED to run, keyed by agent_id, so
    a future deterministic_gate.py (piece 2) can read real tool-invocation
    evidence instead of trusting the executor's self-reported prose. Never
    raises -- a recording failure must never change guard behavior."""
    try:
        session_id = payload.get("session_id") or "unknown-session"
        record = {
            "session_id": session_id,
            "agent_id": payload.get("agent_id") or "unknown-agent",
            "agent_type": payload.get("agent_type"),
            "tool_name": tool_name,
            "tool_use_id": payload.get("tool_use_id"),
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if tool_name in ("Edit", "Write"):
            record["target"] = tool_input.get("file_path") or tool_input.get("path")
        elif tool_name == "Bash":
            record["command"] = tool_input.get("command")
        os.makedirs(WRITE_STATE_DIR, exist_ok=True)
        path = os.path.join(WRITE_STATE_DIR, f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        allow()
        return

    if payload.get("agent_type") not in GUARDED_AGENT_TYPES:
        allow()
        return

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name in ("Edit", "Write"):
        reason = check_governed_file_write(tool_input)
        if reason:
            deny(reason)
            return
        if is_write_class(tool_name, tool_input):
            record_write_class_call(payload, tool_name, tool_input)
        allow()
        return

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        for check in (check_destructive_git, check_rule_10_freeze):
            reason = check(command)
            if reason:
                deny(reason)
                return
        if is_write_class(tool_name, tool_input):
            record_write_class_call(payload, tool_name, tool_input)
        allow()
        return

    allow()


if __name__ == "__main__":
    main()
