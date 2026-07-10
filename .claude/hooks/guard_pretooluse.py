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
"""
import json
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
        allow()
        return

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        for check in (check_destructive_git, check_rule_10_freeze):
            reason = check(command)
            if reason:
                deny(reason)
                return
        allow()
        return

    allow()


if __name__ == "__main__":
    main()
