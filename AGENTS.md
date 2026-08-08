# Agent Quick Orientation

For full architecture, invariants, and roadmap detail, read CLAUDE.md and PLAN.md — this file is a quick-orientation summary, not a replacement for them.

## Read before write

Before making changes for any non-trivial task, read `CLAUDE.md` and `PLAN.md` in full. They are the authoritative source of truth for architecture, invariants, and roadmap state. Do not infer repository conventions from code alone.

## Build and batch discipline

- Run read-only diagnostics before any build, per `PLAN.md` Standing session rule 1.
- Before any full batch, complete a dry run and single-item verification, per rule 2.
- End every batch or backfill with a hard reconciliation count—attempted, stored, errored, and skipped—and check it against the live database, per rule 3.

## Commit and roadmap discipline

- Build commits and docs/records commits are always separate. Never bundle them in one commit; see `PLAN.md` Standing session rule 7.
- Closing a roadmap item replaces its existing entry. Never stack a new paragraph on top of the old one; see Standing session rule 13.

## Session close

When wrapping up a session:

1. Update the relevant `PLAN.md` entry to its final state, replacing rather than stacking.
2. Update the **Current state** section of `rhemata-status.md`; overwrite that session state rather than appending to it.
3. Make one docs-only commit, separate from every code/build commit.

If no records need updating, say so instead of making a cosmetic commit.

## Explicit instruction required

Do not touch any of the following unless Alex explicitly scopes or approves it:

- Database writes outside the agent's own explicitly scoped task.
- Anything on the answer-generation or retrieval path when the task was not scoped to touch it.
- Doctrinal or position-paper content; it requires Alex's direct sign-off and must never be inferred from context.
