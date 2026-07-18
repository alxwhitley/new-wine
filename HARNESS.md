# Rhemata — Harness / Agentic-Loop Gate Design

Load for harness/hook sessions only. Not always-loaded.

Covers the supervised agentic-loop harness: `executor` / `planner-reviewer`
subagents, `.claude/hooks/guard_pretooluse.py` (PreToolUse),
`.claude/hooks/deterministic_gate.py` (SubagentStop).

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

---

## Closed

- **Bug #1** — stop-gate judged each finishing agent against the entire session's
  write-state log instead of its own writes. Fixed 2026-07-12.
- **Piece A/B, exit condition (a)** — marker-trust retired; replaced by a
  per-write match-check between recorded actions and the report's description.
  Closed 2026-07-13. Interim garble fix was `5b43332`.
- **Bug #3** — retired 2026-07-13.
