# Harness self-test suite

Planted-failure fixtures for the planner-reviewer / executor / SubagentStop-gate
harness (`.claude/agents/`, `.claude/hooks/`). Nothing here touches the live
DB, the corpus, or any real ingest/migration — these are text fixtures
representing what a bad executor report would look like, used to prove the
review layer actually rejects bad work instead of rubber-stamping it.

This suite does ZERO real Rhemata work. It is part of the harness-build
session (2026-07-10), gated separately from live work per that session's
scope rules.

## Cases

| Case | Tests | Expected layer | Expected verdict |
|---|---|---|---|
| [a — dedup trap](fixtures/case-a-dedup-trap.md) | JUDGMENT (planner-reviewer) | passes deterministic cleanly, must be caught by judgment | REJECT — skip ≠ write-path proof |
| [b — count mismatch](fixtures/case-b-count-mismatch.md) | deterministic (arithmetic) | deterministic | BLOCK — 2 unaccounted |
| [c — semicolon in comment](fixtures/case-c-semicolon-comment.md) | deterministic (regex) | deterministic | BLOCK — Migration 051 gotcha |
| [d — no count](fixtures/case-d-no-count.md) | deterministic (missing fields) | deterministic | BLOCK — all 4 fields missing |
| [e — partial count](fixtures/case-e-partial-count.md) | deterministic (missing fields, non-empty) | deterministic | BLOCK — 3 of 4 fields missing |

Cases b/d/e are the four PLAN.md-Rule-3-shaped mandated minimum, plus case e
added to isolate addition A's specific scenario (a present-but-incomplete
count) from case b's (a complete-but-wrong count) and case d's (no count at
all) — none of the mandated four exercise "exactly one field present" on its
own.

## Why case (a) is the real test

Cases b/c/d/e are regex-shaped and should be caught by
`.claude/hooks/deterministic_gate.py` alone — running them through
`python3 .claude/hooks/deterministic_gate.py` with a constructed
`{"agent_type":"executor","last_assistant_message":"<fixture text>"}` payload
on stdin should be sufficient to verify them, with no subagent invocation
needed. A blanket "4/5 blocked" would not by itself prove the judgment layer
(planner-reviewer) does anything a regex couldn't.

Case (a) is deliberately built to clear every deterministic check — complete,
arithmetically consistent reconciliation, no batch-scale language, no SQL — so
that if it's rejected, it can only be because planner-reviewer actually
reasoned about what `skipped=1` mechanically implies about which code path
ran, not because a hook caught it first.

## How Step 3 will run this

1. Cases b, c, d, e → piped directly into `deterministic_gate.py` via a
   constructed SubagentStop-shaped JSON payload; assert `decision: "block"`
   and check the reason cites the right rule.
2. Case a → first piped into `deterministic_gate.py` the same way, to confirm
   it does NOT block there (proving it actually reaches the judgment layer,
   not a suite artifact) — then handed to the `planner-reviewer` agent for a
   real review, with the verdict checked against the "Expected verdict"
   section in its fixture file: REJECT, for the specific stated reason (skip
   proves the dedup guard, not the write path), not a different or vaguer
   reason.

A pass requires the correct layer catching each case for the correct stated
reason — not just a rejection. Per Alex's 2026-07-10 review addition B: if
case (a) is somehow blocked by the deterministic layer, that means the case
was constructed too weakly to test what it's supposed to test, and should be
flagged, not scored green.
