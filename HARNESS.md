# Rhemata — Harness / Agentic-Loop Gate Design

Load for harness/hook sessions only. Not always-loaded.

Covers the supervised agentic-loop harness: `executor` / `planner-reviewer`
subagents, `.Codex/hooks/guard_pretooluse.py` (PreToolUse), and
`.Codex/hooks/deterministic_gate.py` (SubagentStop). `CLAUDE.md` Session
Routing determines when the harness is eligible; `PLAN.md` defines the current
Opus/Kimi/Sonnet/Grok execution model and packet contract.

These are the design constitution, not a claim that current code fully conforms.
Where it doesn't, say so inline rather than gloss.

**Eviction rule:** a closed bug gets one line and a commit SHA, the moment it's
verified closed. Full diagnostics live in the commit message, not here.

---

## Principles

1. **Mismatch-only rule.** The stop-gate blocks ONLY when the agent's claimed
   work and the recorded tool-calls disagree — never on the presence of a write
   alone. A recorded write with a matching honest report must pass.

2. **Prose is the subject, never the signal.** The agent's self-report is the
   thing being audited. The gate must never trust a self-declared work-type or
   scan prose for write-flavored words to decide. *Conformance: DONE
   (2026-07-13).* Nothing in the decision path trusts a self-declared label
   anymore.

3. **Agent identity is first-class.** Every recorded action and gate decision
   carries "whose action was this" as a required field, not an enrichment. The
   stop-gate evaluates only the finishing agent's own records, never the whole
   session's.

4. **The machinery is invisible to itself.** The harness's own bookkeeping
   (report-saves, log-writes) happens off the monitored path, so the enforcement
   layer can never observe — or trip on — its own writes.

5. **Fallible, not adversarial.** Subagents are prone to honest error and drift,
   not deceit. Broad detection catches mistakes; hard denial (not detection)
   makes the few genuinely irreversible operations impossible. Do not grow this
   harness toward defeating a deliberate adversary.

---

## Standing decisions

**Repo-only, no production DB writes** (settled in `CLAUDE.md` Session
Routing). The harness may build and test scripts against fixtures, run dry runs,
and perform read-only diagnostics needed by a repo build. It never applies a
migration or runs a production ingest/backfill/write. Those actions use a
separately authorized plain-script session. This is a task-class boundary, not
a script-name freeze.

**Judgment authority: Claude Opus 5.** Opus plans bounded packets and returns
exactly one of `ACCEPT`, `REVISE`, `QUARANTINE`, or `HUMAN_REQUIRED`. Worker
command success is not acceptance. If Opus performs implementation itself, a
separate Opus review session or Alex must judge it.

**Worker routing.** Kimi through OpenCode Go is the primary implementation
worker for eligible packets. Confirmed provider quota/rate-limit exhaustion
checkpoints and requeues an eligible packet to Claude Sonnet 5. Ordinary test,
code, permission, or output failures do not trigger fallback. Grok handles
bounded research, inventories, log/test analysis, and mechanical verification;
it has no architectural, theological, licensing, production-write, or launch
judgment authority.

**Isolation and ownership.** Every write-capable packet names an isolated
worktree and writable file allowlist. Parallel packets require disjoint file
ownership and no unresolved dependency. Workers never clean, overwrite, stage,
commit, push, merge, or resolve conflicts in the user's working tree.

**Governed records.** Workers never edit `CLAUDE.md`, `PLAN.md`,
`POSITIONING.md`, `DESIGN.md`, or `rhemata-status.md`. They propose changes;
the orchestrating session applies approved record updates separately from build
commits.

**Subagent scope: SCRIPT-ONLY** (Alex, 2026-07-12). No MCP or external-tool
access for `executor` or `planner-reviewer`. Every roadmap task is expressible as
a script; building write-detection for ungranted tool access is speculative
scope. *Revisit trigger:* only when a queued task genuinely cannot be expressed
as a script. Not preemptively.

**Report-to-disk: DROPPED, not deferred** (Alex, 2026-07-12). Nothing in the
codebase reads the saved report, and the mechanical write-state record
(Approach B) already survives report-garbling. This removes the
report-save/read-only write-collision bug by deleting its cause. If a readable
report is genuinely needed later, principle 4 is the blueprint for rebuilding it
off the monitored path — not a reason to resurrect this implementation.

## Current packet minimum

Until the machine-readable schema in PLAN O2 exists, the orchestrator must put
these fields directly in every packet. A missing field means do not dispatch:

- packet ID, objective, dependencies, assigned worker, and starting revision;
- isolated worktree, writable file allowlist, and forbidden surfaces;
- required context and explicit acceptance criteria;
- exact verification commands and expected evidence;
- turn, wall-clock, retry, and cost/allowance limits;
- checkpoint artifacts, rollback method, and human-stop conditions;
- whether Kimi-to-Sonnet reassignment is allowed.

## Current hard stops

Return `HUMAN_REQUIRED` for production DB writes, migration application,
deployment, destructive filesystem or Git actions, governed-record edits,
doctrinal content, licensing determinations, material scope expansion, or any
conflict whose resolution could overwrite another lane's work.

The harness must never loop against depleted provider allowance. Until O3/O5
automate classification and budgets, the orchestrator is responsible for one
bounded retry, checkpointing, and stopping or reassigning the packet.

## Local activation note

The active `.Codex/agents/*.toml` and `.Codex/hooks/*.py` are untracked local
configuration and therefore do not appear in ordinary Git worktrees. O1
refreshed them in the primary checkout and added
`.claude/harness-selftest/test_current_routing_contract.py` as the regression
contract. The test proves the obsolete name-specific freeze is gone while a
broader repo-only gate blocks recognizable real ingest, backfill, migration,
seed, restore, and direct mutating-SQL commands. A fresh machine must install
or generate equivalent local configuration before using the harness.

---

## Closed

- **Bug #1** — stop-gate judged each finishing agent against the entire session's
  write-state log instead of its own writes. Fixed 2026-07-12.
- **Piece A/B, exit condition (a)** — marker-trust retired; replaced by a
  per-write match-check between recorded actions and the report's description.
  Closed 2026-07-13. Interim garble fix was `5b43332`.
- **Bug #3** — retired 2026-07-13.
