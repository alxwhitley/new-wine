#!/usr/bin/env python3
"""
Regression/verification test for the 2026-07-31 BASH_WRITE_INDICATORS
SQL-verb narrowing (rhemata-status.md "Known Harness Bugs", last entry;
CLAUDE.md's Session Routing hard rule references the same over-flagging
issue). Root cause: the pre-2026-07-31 single combined
BASH_WRITE_INDICATORS regex flagged ANY Bash command merely CONTAINING a
bare SQL-verb-shaped word (INSERT/UPDATE/DELETE/UPSERT/ALTER/DROP/MERGE/
CREATE), including pure text search/display commands that touch no
database at all -- e.g. the real 2026-07-18 incident,
`grep -rl "ALTER TABLE ..." migrations/`, which is also the scenario (A)
command in test_write_accounting_loop_fix.py's own scenario_a().

guard_pretooluse.py now splits that regex into BASH_WRITE_INDICATORS_ALWAYS
(untouched -- redirection, file-mutating commands, sed -i, still
deliberately over-inclusive) and BASH_WRITE_INDICATORS_SQL_VERBS (narrowed
via _is_read_only_text_pipeline() -- a bare SQL-verb word only stops
counting as a write indicator when the ENTIRE command is confidently a
chain of pure text-search/display commands with no command substitution,
process substitution, or backgrounding anywhere in it).

This suite drives the REAL, unmodified `guard_pretooluse.py` module
(imported, not reimplemented) -- both at the is_write_class() function
level AND through the real PreToolUse decision path (run_pretooluse(),
mirroring test_write_accounting_loop_fix.py's helper of the same name) so
the proof for the "no longer recorded as a write" claims is an actual
write-state file with zero/nonzero matching records, not just a bare
function-call assertion. Uses a monkeypatched WRITE_STATE_DIR pointed at a
fresh tempfile.mkdtemp() -- the real /tmp/rhemata-harness-writes directory
is never touched by this suite.

Manual check()/sys.exit(1) pattern, matching this repo's existing ad hoc
scripts/test_*.py convention and test_write_accounting_loop_fix.py exactly
(no test framework is installed).

Run: python3 .claude/harness-selftest/test_sql_verb_narrowing.py
"""
import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, ".claude", "hooks"))

import guard_pretooluse as guard  # noqa: E402

FAILURES = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)
    return condition


def fresh_state_dir():
    d = tempfile.mkdtemp(prefix="rhemata-harness-writes-test-")
    guard.WRITE_STATE_DIR = d
    return d


def run_pretooluse(scratch_dir, payload):
    """Drives the real guard_pretooluse.py decision path for one Bash call,
    exactly like main() does, minus the stdin/stdout/exit plumbing --
    returns True if allowed. Mirrors test_write_accounting_loop_fix.py's
    helper of the same name."""
    tool_name = payload["tool_name"]
    tool_input = payload["tool_input"]

    if tool_name in ("Edit", "Write"):
        reason = guard.check_governed_file_write(tool_input)
        if reason:
            return False
        if guard.is_write_class(tool_name, tool_input):
            guard.record_write_class_call(payload, tool_name, tool_input)
        return True

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        for c in (guard.check_destructive_git, guard.check_rule_10_freeze):
            if c(command):
                return False
        if guard.is_write_class(tool_name, tool_input):
            guard.record_write_class_call(payload, tool_name, tool_input)
        elif guard.is_known_write_script_invocation(command) and not guard.DRY_RUN_FLAG.search(command):
            guard.record_write_class_call(payload, tool_name, tool_input)
        if guard.SCRIPT_INVOCATION_PATTERN.search(command):
            guard.record_script_invocation(payload, command)
        return True

    return True


def read_records(scratch_dir, session_id):
    path = os.path.join(scratch_dir, f"{session_id}.jsonl")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def write_class_record_count(scratch_dir, session_id):
    """Number of recorded write-class records (kind absent -- 'kind' is
    only set on the OTHER record types: script_invocation, mcp_read) for
    this session's state file."""
    records = read_records(scratch_dir, session_id)
    return len([r for r in records if "kind" not in r])


# ---------------------------------------------------------------------------
# (A) Historical incident -- the real 2026-07-18 command -- no longer
# recorded as a write.
# ---------------------------------------------------------------------------
def scenario_a():
    print("\n=== (A) Historical 2026-07-18 incident: no longer flagged or recorded ===")
    scratch = fresh_state_dir()
    session_id = "test-A-historical"
    agent_id = "executor-A"

    # Literal command, copied verbatim from
    # test_write_accounting_loop_fix.py's scenario_a().
    grep_cmd = (
        'grep -rl "ALTER TABLE sources\\|ALTER TABLE source_aliases" '
        '/Users/alexwhitley/rhemata/migrations/ | sort -V'
    )

    check("A1: is_write_class() is False for the literal 2026-07-18 grep command",
          guard.is_write_class("Bash", {"command": grep_cmd}) is False)

    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Bash", "tool_input": {"command": grep_cmd},
    })
    n = write_class_record_count(scratch, session_id)
    check("A2: real PreToolUse path records ZERO write-class records for this call",
          n == 0, detail=f"got {n} write-class record(s)")

    shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# (B) Zero regression on true positives -- each must still be flagged
# exactly as before.
# ---------------------------------------------------------------------------
def scenario_b():
    print("\n=== (B) Zero regression on true positives ===")

    # B1: a genuine SQL execution via psql.
    scratch = fresh_state_dir()
    session_id = "test-B1-psql"
    agent_id = "executor-B1"
    psql_cmd = 'psql "$SUPABASE_DB_URL" -c "ALTER TABLE sources ADD COLUMN retrievable boolean;"'
    check("B1a: is_write_class() is True for a genuine psql ALTER TABLE execution",
          guard.is_write_class("Bash", {"command": psql_cmd}) is True)
    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Bash", "tool_input": {"command": psql_cmd},
    })
    n = write_class_record_count(scratch, session_id)
    check("B1b: real PreToolUse path records this psql call as a write",
          n == 1, detail=f"got {n} write-class record(s)")
    shutil.rmtree(scratch, ignore_errors=True)

    # B2: a known write-capable script invocation -- untouched, out of scope.
    scratch = fresh_state_dir()
    session_id = "test-B2-known-script"
    agent_id = "executor-B2"
    script_cmd = "python3 scripts/ingest.py"
    check("B2a: is_known_write_script_invocation() is still True for `python3 scripts/ingest.py`",
          guard.is_known_write_script_invocation(script_cmd) is True)
    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Bash", "tool_input": {"command": script_cmd},
    })
    n = write_class_record_count(scratch, session_id)
    check("B2b: real PreToolUse path still records this known write-script invocation as a write",
          n == 1, detail=f"got {n} write-class record(s)")
    shutil.rmtree(scratch, ignore_errors=True)

    # B3: narrowing can't be used as a bypass -- a genuine mutating
    # indicator (redirection) alongside an otherwise-narrowable SQL verb.
    redirect_cmd = 'echo "ALTER TABLE sources ADD COLUMN x text;" > /tmp/patch.sql'
    check("B3: is_write_class() is True for echo+redirect even though the SQL-verb "
          "portion alone would narrow (BASH_WRITE_INDICATORS_ALWAYS still catches "
          "the redirection independently)",
          guard.is_write_class("Bash", {"command": redirect_cmd}) is True)

    # B4: command-substitution edge case must fail closed.
    cmdsub_cmd = 'grep "$(echo ALTER)" file.txt'
    check("B4: is_write_class() is True for a command-substitution edge case "
          "(fails closed even though the outer command is grep)",
          guard.is_write_class("Bash", {"command": cmdsub_cmd}) is True)

    # B5: a genuine mutating command chained with an otherwise-narrowable one.
    rm_and_grep_cmd = "rm foo.txt && grep ALTER bar.txt"
    check("B5: is_write_class() is True for `rm foo.txt && grep ALTER bar.txt` "
          "(via the rm match in BASH_WRITE_INDICATORS_ALWAYS)",
          guard.is_write_class("Bash", {"command": rm_and_grep_cmd}) is True)


# ---------------------------------------------------------------------------
# (C) Additional benign cases, structurally different from (A).
# ---------------------------------------------------------------------------
def scenario_c():
    print("\n=== (C) Additional benign cases (structurally different from A) ===")

    # (A)'s matched text is inside a quoted grep SEARCH PATTERN. This case's
    # matched text is inside FILE CONTENT being displayed/searched via a
    # pipeline of two allowlisted commands (cat | grep).
    scratch = fresh_state_dir()
    session_id = "test-C-cat-grep"
    agent_id = "executor-C1"
    cat_grep_cmd = 'cat CLAUDE.md ARCHITECTURE.md | grep -i "DELETE\\|UPDATE"'
    check("C1a: is_write_class() is False for `cat ... | grep -i \"DELETE\\|UPDATE\"`",
          guard.is_write_class("Bash", {"command": cat_grep_cmd}) is False)
    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Bash", "tool_input": {"command": cat_grep_cmd},
    })
    n = write_class_record_count(scratch, session_id)
    check("C1b: real PreToolUse path records ZERO write-class records for the cat|grep pipeline",
          n == 0, detail=f"got {n} write-class record(s)")
    shutil.rmtree(scratch, ignore_errors=True)

    # A `;`-chained pure-grep case, proving semicolon-stage-splitting also
    # narrows correctly (distinct chaining operator from A/C1's pipe).
    semicolon_cmd = 'grep -n "DROP TABLE" a.sql; grep -n "CREATE TABLE" b.sql'
    check("C2: is_write_class() is False for a `;`-chained pure-grep command",
          guard.is_write_class("Bash", {"command": semicolon_cmd}) is False)


if __name__ == "__main__":
    scenario_a()
    scenario_b()
    scenario_c()

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s) failed:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)
