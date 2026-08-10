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
  3. CLAUDE.md Session Routing: denies recognizable production DB write
     commands for guarded agents. This is task-class based, not a stale list of
     allegedly unconverted scripts.

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

2026-07-31 update: the SQL-verb alternative inside BASH_WRITE_INDICATORS (now
split into BASH_WRITE_INDICATORS_ALWAYS and BASH_WRITE_INDICATORS_SQL_VERBS,
see that pair's comment block for detail) is narrowed -- a bare SQL-verb-
shaped word (INSERT/UPDATE/DELETE/UPSERT/ALTER/DROP/MERGE/CREATE) no longer
flags a write when the ENTIRE command is confidently a chain of pure
text-search/display commands (grep/egrep/fgrep/rg/cat/head/tail/less/more/
wc/sort/uniq/echo -- see READ_ONLY_TEXT_COMMANDS) with no command
substitution, process substitution, or backgrounding anywhere in it; any of
those fails closed and the command stays flagged, same as before. This
closes rhemata-status.md's "Known Harness Bugs" last entry -- the real
2026-07-18 `grep ... "ALTER TABLE ..."` incident that fed the SubagentStop
write-accounting loop bug (deterministic_gate.py's fix for that loop
explicitly left this exact classifier narrowing out of scope, for "its own
future, higher-risk session" -- this is that session). Everything else is
UNTOUCHED and deliberately stays exactly as over-inclusive as before:
BASH_WRITE_INDICATORS_ALWAYS' shell-redirection, file-mutating-command
(rm/mv/cp/touch/mkdir/tee/dd/truncate/chmod/chown), and sed -i matches are
not narrowed by anything in this update -- principle 5 (fallible, not
adversarial; broad detection is the safe default) still governs those.
"""
import datetime
import json
import os
import re
import shlex
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

DRY_RUN_FLAG = re.compile(r"(?:^|\s)--(?:dry-run|test)(?=\s|$)")

# Harness sessions are repo-only. Block recognizable non-dry-run production
# data commands by operation class instead of maintaining a list of scripts
# believed to be unconverted. This deliberately over-blocks ambiguous commands;
# the correct route for a real write is a separately authorized plain session.
PRODUCTION_DATA_SCRIPT = re.compile(
    r"(?:^|[\s/])[\w.-]*(?:ingest|backfill|migrate|migration|restore|seed|populate)"
    r"[\w.-]*\.(?:py|js|sh)\b",
    re.IGNORECASE,
)

PRODUCTION_DATA_MODULE = re.compile(
    r"(?:^|\s)-m\s+[\w.]*(?:ingest|backfill|migrate|migration|restore|seed|populate)"
    r"[\w.]*\b",
    re.IGNORECASE,
)

DIRECT_DB_CLIENT = re.compile(
    r"\b(?:psql|psycopg2|execute_sql|apply_migration)\b", re.IGNORECASE
)
MUTATING_SQL_VERB = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|UPSERT|ALTER|DROP|MERGE|CREATE|TRUNCATE)\b",
    re.IGNORECASE,
)

# Session #5.5 Phase 3 piece 1: write-class Bash detection. NEW, first-pass --
# see module docstring for known gaps (can't see inside a script; over-fires
# on some non-writes like bare `2>&1`). Not reused from elsewhere because
# nothing else in this file is a general-purpose write classifier.
#
# 2026-07-31 narrowing (rhemata-status.md "Known Harness Bugs", last entry):
# the single combined regex this used to be over-flagged any Bash command
# that merely CONTAINED an SQL-verb-shaped bare word (INSERT/UPDATE/DELETE/
# UPSERT/ALTER/DROP/MERGE/CREATE) -- including pure text search/display
# commands that touch no database at all (e.g.
# `grep -rl "ALTER TABLE ..." migrations/`, the real 2026-07-18 incident
# referenced above and in deterministic_gate.py's loop-fix comment). Split
# into two pieces so ONLY the SQL-verb alternative can ever be narrowed, and
# only when the ENTIRE command is confidently a chain of pure
# text-search/display commands (see READ_ONLY_TEXT_COMMANDS /
# _is_read_only_text_pipeline below) with no command substitution, process
# substitution, or backgrounding anywhere in it -- any of those fails closed
# (stays flagged). Everything else -- shell redirection, the file-mutating
# command list, sed -i -- is UNTOUCHED and deliberately stays exactly as
# over-inclusive as before; principle 5 (fallible, not adversarial -- broad
# detection is the safe default) still governs those.
BASH_WRITE_INDICATORS_ALWAYS = re.compile(
    r">>?(?!=)(?!&\d)(?!\s*/dev/null)"  # shell redirection to a real target --
    # excludes fd duplication (2>&1) and /dev/null, both confirmed
    # false-positive sources in the 2026-07-11 garble diagnosis; still
    # catches genuine file writes like "> out.txt" or "2> err.log"
    r"|\b(?:rm|mv|cp|touch|mkdir|tee|dd|truncate|chmod|chown)\b"  # file-mutating commands
    r"|\bsed\b[^|;&\n]*-i\b",  # sed -i (in-place edit)
    re.IGNORECASE,
)

BASH_WRITE_INDICATORS_SQL_VERBS = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|UPSERT|ALTER|DROP|MERGE|CREATE)\b",  # SQL mutation verbs
    re.IGNORECASE,
)

# Kept as the union of both pieces above, for reference/back-compat only --
# other files' comments/docstrings mention this name (deterministic_gate.py,
# rhemata-status.md, CLAUDE.md, the harness-selftest README). Confirmed by
# grep (2026-07-31) that nothing in this codebase calls BASH_WRITE_INDICATORS
# itself; is_write_class() below uses the two pieces separately.
BASH_WRITE_INDICATORS = re.compile(
    BASH_WRITE_INDICATORS_ALWAYS.pattern + "|" + BASH_WRITE_INDICATORS_SQL_VERBS.pattern,
    re.IGNORECASE,
)

# 2026-07-31 narrowing continued: a short allowlist of commands that only
# ever display or search text -- none of them can execute SQL or shell code
# found in their own arguments, so a bare SQL-verb-shaped word appearing
# inside a command from this list (a grep search pattern, a displayed
# file's contents, etc) is not itself evidence of a database write.
READ_ONLY_TEXT_COMMANDS = {
    "grep", "egrep", "fgrep", "rg", "cat", "head", "tail", "less", "more",
    "wc", "sort", "uniq", "echo",
}


def _is_read_only_text_pipeline(command: str) -> bool:
    """True only when every stage of `command` invokes a command from
    READ_ONLY_TEXT_COMMANDS -- tools that display or search text and can
    never themselves execute SQL or shell code from their arguments. Used
    ONLY to narrow BASH_WRITE_INDICATORS_SQL_VERBS' bare-word match (a grep
    pattern or displayed file content containing "ALTER"/"DROP"/etc is not
    a database write) -- BASH_WRITE_INDICATORS_ALWAYS is never narrowed by
    this function and stays exactly as over-inclusive as before.

    Shell-quote-aware: uses shlex with punctuation_chars=True so a `|`
    inside a quoted grep pattern (e.g. the real 2026-07-18 incident's
    "ALTER TABLE sources\\|ALTER TABLE source_aliases" command) is not
    mistaken for a pipeline separator -- verified live against that exact
    string before this was written.

    Fails closed (returns False, i.e. stays flagged) on anything not
    confidently parseable as pure text-display/search: command
    substitution ($(...) or backticks), process substitution (<(...)/>(...)),
    backgrounding (&), or a command string shlex can't tokenize cleanly
    (unbalanced quotes etc). This is deliberate -- principle 5 (fallible,
    not adversarial; broad detection is the safe default) means an
    ambiguous case stays flagged, not narrowed."""
    if "$(" in command or "`" in command or "<(" in command or ">(" in command:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False

    stages = [[]]
    for tok in tokens:
        if tok in ("|", ";", "&&", "||"):
            stages.append([])
        elif tok == "&":
            return False
        else:
            stages[-1].append(tok)
    stages = [s for s in stages if s]
    if not stages:
        return False

    for stage in stages:
        idx = 0
        while idx < len(stage) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", stage[idx]):
            idx += 1
        if idx >= len(stage):
            return False
        cmd_name = os.path.basename(stage[idx])
        if cmd_name not in READ_ONLY_TEXT_COMMANDS:
            return False
    return True

# Outside the repo entirely (not .claude/-relative) -- this is live-run-only
# state, consumed once at the same subagent's SubagentStop, not durable
# project data. Avoids needing a .gitignore entry or any risk of ever being
# committed. Keyed by session_id so concurrent/sequential runs don't collide.
WRITE_STATE_DIR = "/tmp/rhemata-harness-writes"

# Session #5.5 Phase 3 piece 2b-i: script-invocation detection. NEW,
# first-pass, note-taking only -- does NOT imply a write happened, only that
# BASH_WRITE_INDICATORS can't see inside this command, so a future gate
# should fall back to checking prose for this run rather than trusting an
# empty write record as proof of no write. Known gaps: misses dynamic
# execution with no visible script path (e.g. piping a script body into an
# interpreter's stdin), misses a script invoked through a wrapper/alias with
# no recognizable extension, misses a script re-invoking itself internally.
# Deliberately over-inclusive in the other direction too: flags read-only
# utility scripts (e.g. discover_sermonindex_playlists.py, documented as
# discovery-only) exactly as readily as write-heavy ones -- fine for a
# fall-back-to-prose marker, would not be fine feeding a block decision
# directly.
SCRIPT_INVOCATION_PATTERN = re.compile(
    r"\b(?:python3?|node|bash|sh|zsh|ruby|perl|php)\s+"
    r"[\w./\-]+\.(?:py|js|sh|rb|pl|php)\b"
    r"|\./[\w./\-]+\.(?:py|js|sh|rb|pl|php)\b",
    re.IGNORECASE,
)

# Piece B (#5.5 exit condition (a), 2026-07-13): known write-capable scripts,
# known write-capable scripts are recorded directly instead of falling into
# the script-invocation blind spot. Recognition is not authorization: real
# production execution remains blocked by check_production_db_boundary().
# so a non-dry-run invocation should be recorded directly as a write instead
# of falling into the "script ran, contents unseen" blind spot. Starts with
# ingest.py (the one converted chokepoint script); extend this set only
# after auditing a script the same way -- an unrecognized script is left
# alone here and stays in deterministic_gate.py's "unverifiable" bucket,
# never silently waved through and never guessed at.
KNOWN_WRITE_SCRIPT_NAMES = {"ingest.py"}


def is_known_write_script_invocation(command: str) -> bool:
    """True only when a known write-capable script is actually being
    INVOKED (python3 scripts/ingest.py, ./scripts/ingest.py, etc) -- reuses
    SCRIPT_INVOCATION_PATTERN's own invocation-detection so a command that
    merely MENTIONS the filename (e.g. `grep ... ingest.py`, `cat
    ingest.py`) is never misclassified as running it. Caught live
    (2026-07-13): an earlier version matched the bare filename anywhere in
    the command and misfired on exactly this kind of read-only mention."""
    for match in SCRIPT_INVOCATION_PATTERN.finditer(command):
        invoked = match.group(0)
        if any(
            invoked == name or invoked.endswith("/" + name)
            for name in KNOWN_WRITE_SCRIPT_NAMES
        ):
            return True
    return False

# Session #5.5 MCP database gate (2026-07-11). Full literal tool_name strings
# only -- the mcp__claude_ai_Supabase__list_tables prefix was verified against
# a real captured PreToolUse payload in the prior session, not inferred.
# Scoped to the Supabase connector specifically; any other MCP connector's
# tools (Notion, Canva, etc.) are untouched by this set and fall through to
# the default allow() below, exactly as they did before this change -- gating
# those connectors is out of scope for this session.
MCP_WRITE_CLASS_TOOLS = {
    "mcp__claude_ai_Supabase__execute_sql",
    "mcp__claude_ai_Supabase__apply_migration",
    "mcp__claude_ai_Supabase__create_branch",
    "mcp__claude_ai_Supabase__create_project",
    "mcp__claude_ai_Supabase__delete_branch",
    "mcp__claude_ai_Supabase__deploy_edge_function",
    "mcp__claude_ai_Supabase__merge_branch",
    "mcp__claude_ai_Supabase__pause_project",
    "mcp__claude_ai_Supabase__rebase_branch",
    "mcp__claude_ai_Supabase__reset_branch",
    "mcp__claude_ai_Supabase__restore_project",
}


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


def check_mcp_write(tool_name: str):
    if tool_name in MCP_WRITE_CLASS_TOOLS:
        return (
            "MCP database write blocked. Governed sessions route DB writes "
            "through the psycopg2/script path, not the Supabase MCP "
            "connector -- this call would mutate data or schema directly "
            "and bypass every script-level check (dedup, source resolution, "
            "propositions gate, etc). Use the documented ingest/migration "
            "scripts, or psycopg2 via SUPABASE_DB_URL, instead."
        )
    return None


def check_production_db_boundary(command: str):
    if DIRECT_DB_CLIENT.search(command) and MUTATING_SQL_VERB.search(command):
        return (
            "CLAUDE.md Session Routing: production database work ('direct DB mutation') "
            "never runs through the repo-only harness. Direct mutating SQL has no "
            "harness dry-run exemption and requires a separately authorized "
            "plain-script session."
        )
    for segment in re.split(r"(?:&&|\|\||(?<!\|)\|(?!\|)|;|\n)", command):
        script = PRODUCTION_DATA_SCRIPT.search(segment)
        module = PRODUCTION_DATA_MODULE.search(segment)
        if (script or module) and not DRY_RUN_FLAG.search(segment):
            target_match = script or module
            target = target_match.group(0).strip()
            return (
                f"CLAUDE.md Session Routing: production database work ('{target}') "
                "never runs through the repo-only harness. A dry run/test may run "
                "here; any real ingest, backfill, migration, seed, restore, or direct "
                "DB mutation requires a separately authorized plain-script session."
            )
    return None


def is_write_class(tool_name: str, tool_input: dict) -> bool:
    """Session #5.5 Phase 3 piece 1: single source of truth for "is this
    call a write." Edit/Write are always write-class by definition. Bash is
    write-class iff BASH_WRITE_INDICATORS_ALWAYS matches (the always-flag
    set -- shell redirection, file-mutating commands, sed -i -- untouched by
    the 2026-07-31 narrowing, still deliberately over-inclusive), OR
    BASH_WRITE_INDICATORS_SQL_VERBS matches AND the command is NOT a pure
    read-only text-search/display pipeline per _is_read_only_text_pipeline()
    (2026-07-31 narrowing -- see that function's docstring and the comment
    block above BASH_WRITE_INDICATORS_ALWAYS for exactly what changed and
    what stayed the same). See module docstring for remaining known gaps."""
    if tool_name in ("Edit", "Write"):
        return True
    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        if BASH_WRITE_INDICATORS_ALWAYS.search(command):
            return True
        if BASH_WRITE_INDICATORS_SQL_VERBS.search(command):
            return not _is_read_only_text_pipeline(command)
        return False
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


def record_script_invocation(payload: dict, command: str) -> None:
    """Session #5.5 Phase 3 piece 2b-i: note that a script ran via Bash,
    contents unseen -- a DISTINCT record kind from record_write_class_call's
    write records, never merged with them. Does not imply a write happened;
    only that BASH_WRITE_INDICATORS can't see inside this command, so a
    future gate (piece 2b-ii) should fall back to checking prose for this run
    rather than trusting an empty write record as proof of no write. Never
    raises -- a recording failure must never change guard behavior."""
    try:
        session_id = payload.get("session_id") or "unknown-session"
        record = {
            "kind": "script_invocation",
            "session_id": session_id,
            "agent_id": payload.get("agent_id") or "unknown-agent",
            "agent_type": payload.get("agent_type"),
            "tool_use_id": payload.get("tool_use_id"),
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "command": command,
        }
        os.makedirs(WRITE_STATE_DIR, exist_ok=True)
        path = os.path.join(WRITE_STATE_DIR, f"{session_id}.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def record_mcp_read_call(payload: dict, tool_name: str) -> None:
    """Session #5.5 MCP-gate build: cheap ground-truth record of an ALLOWED
    MCP read, mirroring record_write_class_call's pattern. Never raises --
    a recording failure must never change guard behavior."""
    try:
        session_id = payload.get("session_id") or "unknown-session"
        record = {
            "kind": "mcp_read",
            "session_id": session_id,
            "agent_id": payload.get("agent_id") or "unknown-agent",
            "agent_type": payload.get("agent_type"),
            "tool_name": tool_name,
            "tool_use_id": payload.get("tool_use_id"),
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
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

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    # MCP database gate (Session #5.5, 2026-07-11): action-keyed, not
    # agent_type-keyed -- applies to ANY subagent call (agent_type present at
    # all), not just the executor/planner-reviewer set the checks below are
    # scoped to. Deliberate: it means the gate already covers executor/
    # planner the moment either gains MCP tool access, with no further code
    # change, and it covers today's actual MCP-capable type (general-purpose)
    # too. Placed ahead of the GUARDED_AGENT_TYPES allowlist check below
    # because that check exists to exempt the trusted MAIN session from every
    # rule in this file, not to narrow MCP coverage down to two subagent
    # types -- main-session calls (agent_type absent from the payload)
    # remain exempt here as everywhere else in this file.
    if payload.get("agent_type") is not None and tool_name.startswith("mcp__"):
        reason = check_mcp_write(tool_name)
        if reason:
            deny(reason)
            return
        record_mcp_read_call(payload, tool_name)
        allow()
        return

    if payload.get("agent_type") not in GUARDED_AGENT_TYPES:
        allow()
        return

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
        for check in (check_destructive_git, check_production_db_boundary):
            reason = check(command)
            if reason:
                deny(reason)
                return
        if is_write_class(tool_name, tool_input):
            record_write_class_call(payload, tool_name, tool_input)
        elif is_known_write_script_invocation(command) and not DRY_RUN_FLAG.search(command):
            # Piece B (#5.5 exit condition (a), 2026-07-13): a known
            # write-capable script invoked for real -- record it directly as
            # a write so deterministic_gate.py's match-check judges it like
            # any other write. `elif` so it's not double-recorded when
            # BASH_WRITE_INDICATORS already caught it independently.
            record_write_class_call(payload, tool_name, tool_input)
        if SCRIPT_INVOCATION_PATTERN.search(command):
            record_script_invocation(payload, command)
        allow()
        return

    allow()


if __name__ == "__main__":
    main()
