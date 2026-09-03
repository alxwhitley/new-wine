# Claude Code Prompt — Execute the Biblical Context Ingestion Queue

Copy the prompt below into Claude Code from the New Wine terminal checkout.

```text
Work in /Users/alexwhitley/newwine.

Continue the biblical-context ingestion work from the pushed branch
codex/biblical-ingestion-completion-queue. Your governing execution queue is:

docs/superpowers/plans/2026-09-01-biblical-context-ingestion-completion-queue.md

Use the superpowers:executing-plans skill and execute that queue continuously,
in order, one packet at a time. Do as much as can be completed safely without
asking me routine questions. Do not merely summarize the queue: begin with its
read-only diagnostics and then implement, test, verify, and locally commit each
authorized repository-only slice until you reach an explicit ATTENDED GATE or
a fail-closed stop condition in the queue.

Before acting:

1. Run `cd /Users/alexwhitley/newwine && git status --short --branch` and confirm
   the intended branch and tracked state. Preserve all unrelated modified and
   untracked files; never stage them, clean them, move them, or overwrite them.
2. Read AGENTS.md, PLAN.md, rhemata-status.md, the relevant CLAUDE.md invariants,
   docs/roadmap.md A4, both source manifests, the Phase 8 design and implementation
   plans, and the entire ingestion completion queue.
3. Treat the queue's stated starting facts as assertions to verify, not as a
   substitute for fresh repository and read-only production diagnostics.
4. Confirm the branch is based on current origin/main. If origin/main moved,
   inspect and reconcile the drift without discarding any work or weakening any
   invariant.

Autonomy rules:

- Make routine implementation decisions yourself where the queue has already
  fixed the contract. Do not ask me to choose names, ordering, batch sizes,
  fixtures, evidence locations, sampling, retry behavior, or test structure.
- Diagnose and correct in-scope repository failures yourself. Keep exactly one
  critical-path packet active and classify unrelated findings without pursuing
  them.
- Use test-driven development for behavior changes and fresh verification before
  every completion claim or commit.
- Keep build commits and docs/records commits separate. Make small local commits
  as verified save points. Do not amend or squash unrelated history.
- Use only the primary Claude Code session for credentials, paid calls, approval
  handling, database access, deployment, and any live operation. Never delegate
  those operations. A reviewer may inspect repository-only work when the queue
  requires independent review.
- Give me concise progress updates, but do not stop for confirmation unless the
  queue explicitly requires an attended decision or continuing would be unsafe.
- Every terminal command you give me must begin exactly with
  `cd /Users/alexwhitley/newwine &&`.

Hard boundaries:

- Never move, rename, archive, or delete /Users/alexwhitley/rhemata or anything
  inside it.
- BIBLICAL_CONTEXT_ANSWER_ENABLED remains unset/default-off. Keep every biblical
  context source hidden.
- Preserve Phase 4 routing, cache, neighbor, plural, and house-fence boundaries.
- Do not alter protected-source or plural-viewpoint registries, make doctrinal
  assignments, enable the answer feature, run paid live answers, or change source
  visibility.
- Do not infer authorization from earlier Phase 6 or Phase 8 proof/pilot work.
  Those approvals and artifacts do not authorize the remaining TIPNR corpus,
  OpenBible work, a retry, a deployment, or a feature release.
- Do not create an approval artifact before I grant the matching exact approval.
- Do not make paid embedding/provider calls, open a production write connection,
  run even a rollback-only production transaction, write production data, push,
  merge, deploy, or mutate production environment variables unless I separately
  and explicitly approve the exact attended operation presented at the current
  gate.

At an ATTENDED GATE:

Stop once and return one consolidated approval packet. Include the exact git
revision, selection and packet hashes, item/text/byte/token counts, disclosed
payload categories, model and dimensions, maximum request and dollar ceilings,
transaction and row ceilings, rollback behavior, same-day preflight requirements,
fresh reconciliation requirements, merge/deploy target if applicable, and every
excluded authority. State exactly what will happen after approval. Ask one exact
authorization question rather than a sequence of smaller questions.

If a failure occurs before a gate, follow the queue's stop conditions. Continue
through ordinary fixable repository failures; stop only for mixed or uncertain
production state, invariant drift, a required expansion of authority, a
beta-critical blocker, or another explicitly named fail-closed condition. When
stopping, preserve evidence and report the smallest safe next operation.

Start now with Packet 0. Continue automatically through all clean repository-only
work and read-only checks. Do not push this execution branch or perform any
external-effect operation merely because this prompt and queue branch were pushed.
```

Launch from the terminal with:

```bash
cd /Users/alexwhitley/newwine && claude
```
