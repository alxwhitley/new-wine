#!/usr/bin/env python3
"""
Regression test for the 2026-07-18 SubagentStop write-detection infinite
loop (rhemata-status.md -> "Known Harness Bugs" -> "Executor loop,
2026-07-18 diagnostic"). Root-caused in the same-dated diagnostic session:
a benign `grep` for a bare SQL-verb-shaped pattern (e.g. "ALTER TABLE ...")
against a directory-only target got recorded as a write (a real, known,
UNCHANGED gap in BASH_WRITE_INDICATORS -- see guard_pretooluse.py's module
docstring; out of scope for this fix on purpose), and the gate's referent
extraction produced an EMPTY list for that record, so it could never be
"accounted for" by any report text, ever -- combined with the write-state
log being re-read cumulatively-but-per-single-message on every
SubagentStop with no dedup, a retry that re-ran the same benign action
just piled up more copies of the same unsatisfiable record forever.

This suite drives the REAL, unmodified `guard_pretooluse.py` and
`deterministic_gate.py` modules (imported, not reimplemented) against the
literal grep command recorded in the real surviving 2026-07-18 write-state
log (read-only reference, never modified), through a monkeypatched
WRITE_STATE_DIR pointed at a fresh tempfile.mkdtemp() -- the real
/tmp/rhemata-harness-writes directory is never touched by this suite.

2026-07-31 update (see .claude/harness-selftest/test_sql_verb_narrowing.py
and guard_pretooluse.py's own 2026-07-31 module-docstring entry): the
BASH_WRITE_INDICATORS gap named above -- a benign grep matching a bare
SQL-verb-shaped word getting recorded as a write -- was itself narrowed
that session, specifically for pure text-search/display commands like the
grep_cmd used in scenario_a() below. That means grep_cmd no longer
produces a write record at all; only the accompanying rm_cmd does. Before
that narrowing, scenario_a()'s check A5 asserted that 4 retries of "the
same 2 actions" deduped to 2 distinct write records -- an assumption that
depended on grep_cmd itself being write-class, which was exactly the bug
the narrowing session fixed. A5 now expects 1 (rm_cmd only). This does not
touch or weaken what A1-A4 prove about loop convergence, cumulative
disclosure, or dedup mechanics -- those checks and the underlying gate
logic are unaffected by the 2026-07-31 narrowing.

Manual check()/sys.exit(1) pattern, matching this repo's existing ad hoc
scripts/test_*.py convention (no test framework is installed).

Run: python3 .claude/harness-selftest/test_write_accounting_loop_fix.py
"""
import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, ".claude", "hooks"))

import deterministic_gate as gate  # noqa: E402
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
    gate.WRITE_STATE_DIR = d
    guard.WRITE_STATE_DIR = d
    return d


def run_pretooluse(scratch_dir, payload):
    """Drives the real guard_pretooluse.py decision path for one Bash call
    (the only tool kind these scenarios need), exactly like main() does,
    minus the stdin/stdout/exit plumbing -- returns True if allowed."""
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
        for c in (guard.check_destructive_git, guard.check_production_db_boundary):
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


def run_subagentstop(session_id, agent_id, agent_type, last_assistant_message):
    payload = {
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type,
        "last_assistant_message": last_assistant_message,
    }
    return gate.check_recorded_writes(payload)  # None == allow, str == block reason


# ---------------------------------------------------------------------------
# Scenario (A): loop convergence -- the real recorded Jul-18 command.
# ---------------------------------------------------------------------------
def scenario_a():
    print("\n=== (A) LOOP GONE: harmless-search retry scenario ===")
    scratch = fresh_state_dir()
    session_id = "test-A-loop"
    agent_id = "executor-A"

    # The literal command from the real surviving 2026-07-18 write-state
    # log (/tmp/rhemata-harness-writes/f117e483-....jsonl, read-only
    # reference) -- directory-only grep target, bare SQL-verb match.
    grep_cmd = (
        'grep -rl "ALTER TABLE sources\\|ALTER TABLE source_aliases" '
        '/Users/alexwhitley/rhemata/migrations/ | sort -V'
    )
    rm_cmd = "rm scratch_diagnostic.txt"

    def do_one_retry(report_text):
        run_pretooluse(scratch, {
            "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
            "tool_name": "Bash", "tool_input": {"command": grep_cmd},
        })
        run_pretooluse(scratch, {
            "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
            "tool_name": "Bash", "tool_input": {"command": rm_cmd},
        })
        return run_subagentstop(session_id, agent_id, "executor", report_text)

    vague = "Ran a search, found nothing relevant, and cleaned up my scratchpad."
    specific = (
        "Searched migrations/ for ALTER TABLE mentions touching sources or "
        "source_aliases -- no matches. Also removed scratch_diagnostic.txt "
        "from my scratchpad. No repo or DB writes this turn."
    )

    results = []
    turn1 = do_one_retry(vague)
    results.append(("turn 1 (vague, first disclosure)", turn1))
    turn2 = do_one_retry(specific)
    results.append(("turn 2 (retry, specific disclosure)", turn2))
    turn3 = do_one_retry(vague)
    results.append(("turn 3 (retry, reverts to vague)", turn3))
    turn4 = do_one_retry(vague)
    results.append(("turn 4 (retry, still vague)", turn4))

    for label, r in results:
        print(f"  {label}: {'BLOCK -- ' + r if r else 'ALLOW'}")

    check("A1: turn 1 correctly BLOCKS on genuinely vague disclosure (not a rubber stamp)",
          turn1 is not None)
    check("A2: turn 2 ALLOWS once the same records are named specifically",
          turn2 is None, detail=str(turn2))
    check("A3: turn 3 stays ALLOWED even though its own message is vague again "
          "(cumulative disclosure persists -- no oscillation)",
          turn3 is None, detail=str(turn3))
    check("A4: turn 4 stays ALLOWED -- stable convergence, not regression",
          turn4 is None, detail=str(turn4))

    # Prove no unbounded growth: count how many DISTINCT write records the
    # gate is reasoning about after 4 retries of the *same two* actions.
    #
    # 2026-07-31 update: after that session's SQL-verb narrowing (see
    # test_sql_verb_narrowing.py), grep_cmd above is a pure text-search
    # command and correctly produces ZERO write records on its own -- only
    # rm_cmd is genuinely write-class. So 4 retries of grep_cmd+rm_cmd now
    # produce 4 raw write records total (rm_cmd only, once per retry),
    # deduping to exactly 1 distinct write record -- not 8 raw / 2 deduped,
    # which was this check's expectation before the narrowing (when the
    # phantom-recorded grep call counted as a second distinct write
    # action, the exact bug that narrowing session fixed). Still proves
    # the same thing this check always existed to prove: no unbounded
    # growth across retries of the same action.
    with open(os.path.join(scratch, f"{session_id}.jsonl")) as f:
        records = [json.loads(l) for l in f if l.strip()]
    write_records = [r for r in records if r.get("agent_id") == agent_id and "kind" not in r]
    deduped = gate._dedup_write_records(write_records)
    print(f"  raw write records logged: {len(write_records)}  |  deduped distinct actions: {len(deduped)}")
    check("A5: 4 retries of grep_cmd+rm_cmd dedup to exactly 1 distinct write "
          "record (rm_cmd only -- the narrowed grep_cmd is correctly not "
          "write-class as of 2026-07-31)",
          len(deduped) == 1, detail=f"got {len(deduped)}")

    shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scenario (B): a real, undisclosed write must still BLOCK.
# ---------------------------------------------------------------------------
def scenario_b():
    print("\n=== (B) REAL CATCH STILL FIRES: undisclosed write ===")
    scratch = fresh_state_dir()
    session_id = "test-B-real-catch"
    agent_id = "executor-B"

    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Edit",
        "tool_input": {"file_path": "backend/app/routers/study.py", "old_string": "x", "new_string": "y"},
    })

    undisclosed_report = (
        "Reviewed the propositions backfill target and confirmed the 810 "
        "figure against a live query. No files touched, read-only session."
    )
    result = run_subagentstop(session_id, agent_id, "executor", undisclosed_report)
    print(f"  gate result: {'BLOCK -- ' + result if result else 'ALLOW'}")
    check("B1: an Edit to study.py never mentioned in the report is BLOCKED",
          result is not None)

    shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scenario (C): a real, disclosed write must ALLOW (principle 1, mismatch-only).
# ---------------------------------------------------------------------------
def scenario_c():
    print("\n=== (C) HONEST WRITE STILL PASSES ===")
    scratch = fresh_state_dir()
    session_id = "test-C-honest"
    agent_id = "executor-C"

    run_pretooluse(scratch, {
        "session_id": session_id, "agent_id": agent_id, "agent_type": "executor",
        "tool_name": "Edit",
        "tool_input": {"file_path": "backend/app/routers/study.py", "old_string": "x", "new_string": "y"},
    })

    disclosed_report = (
        "Fixed the source_kind_filter bug in backend/app/routers/study.py -- "
        "the sermon-query block wasn't guarded the same way as the "
        "commentary block. Verified live against three real verses."
    )
    result = run_subagentstop(session_id, agent_id, "executor", disclosed_report)
    print(f"  gate result: {'BLOCK -- ' + result if result else 'ALLOW'}")
    check("C1: an Edit to study.py that IS named in the report is ALLOWED",
          result is None, detail=str(result))

    shutil.rmtree(scratch, ignore_errors=True)


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
