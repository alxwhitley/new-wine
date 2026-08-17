# Agent Quick Orientation

This file is the always-read operating contract. `CLAUDE.md` owns product
invariants, `PLAN.md` owns the current blocker queue, `docs/roadmap.md` owns
later classified work, and `docs/plan-archive.md` owns history.

## Read before write

Before making changes, read this file, `PLAN.md`, and the specific `CLAUDE.md`
invariants implicated by the task. Load `docs/roadmap.md` only when planning a
later phase, classifying a finding, or checking a trigger. Load
`docs/plan-archive.md` only for historical reasoning. Read `CLAUDE.md` in full
only when changing architecture or governing rules. Do not infer repository
conventions from code alone.

## Beta critical path

A new finding interrupts current work only when credible evidence shows it can
plausibly cause one of these outcomes in the private beta:

- theological error;
- misrepresentation of a teacher;
- data loss;
- a security or privacy breach; or
- failure of the core beta journey.

Discovery is not authorization to investigate or fix. Classify every finding
immediately:

- **Blocker:** must be resolved before beta.
- **Scheduled:** important and assigned to a named later phase.
- **Triggered:** no work until its recorded condition occurs.
- **Parked:** acknowledged; no current work is authorized.

There is no unlabeled open-concern state. Promoting a finding to **Blocker**
requires the concrete failure, evidence, affected beta surface, and smallest
closure condition. When evidence is incomplete, default to **Parked**, not
Blocker.

## Anti-Zeno execution rules

- Every session starts with one outcome, explicit acceptance criteria, and
  named non-goals. Stop when the criteria pass.
- Every audit declares its question, surfaces, time/command budget, and exit
  condition before it begins. Adjacent findings are classified, not pursued.
- Work in progress is limited to one active critical-path item. A new Blocker
  either displaces the current item by Alex's explicit decision or waits.
- The private-beta gate is frozen. A new requirement enters it only through the
  Blocker promotion rule above; improvements do not silently expand the gate.
- Match proof to risk: adversarial multi-round review is for answer integrity,
  identity/data safety, and destructive production operations; ordinary repo
  work gets one coherent verification cycle; records-only work gets a diff and
  consistency check.
- Foundation work ends at the documented ingestion-ready benchmark. After it
  passes, foundation changes require a demonstrated regression or a promoted
  Blocker.
- At session close, record: original outcome achieved or not, discoveries by
  classification, scope changes Alex approved, and the next single item.

Track four lightweight process measures per completed session: original-outcome
completion, unplanned investigations started, findings promoted to Blocker, and
active critical-path item count. The healthy target is: outcome completed,
zero unapproved investigations, rare blocker promotion, and one active item.

## Codex-native agent workflow

Use Codex as the primary working surface. Use native subagents only for bounded,
independent tasks with explicit file ownership and acceptance criteria. An
off-task agent result is classified and parked; it does not redirect the
session. Use a separate reviewer only when the proof tier above calls for one.

The custom multi-provider coordinator and overnight harness are retired from
active development. Their code and history remain for reference, but no task
may extend, commission, or depend on them without Alex explicitly reversing
this decision. Production database writes remain plain, attended,
explicitly-approved operations in the primary Codex session and never run
through a subagent or automated coordinator.

## Build and batch discipline

- Run read-only diagnostics before any build.
- Before any full batch, complete a dry run and single-item verification.
- End every batch or backfill with a hard reconciliation count—attempted,
  stored, errored, and skipped—and check it against the live database.

## Commit and roadmap discipline

- Build commits and docs/records commits are always separate. Never bundle them
  in one commit.
- `PLAN.md` contains Blockers only. Scheduled, Triggered, and Parked work belongs
  in `docs/roadmap.md`; history belongs in `docs/plan-archive.md`.
- Closing an item replaces its existing entry or moves its durable history to
  the archive. Never stack a new correction on top of the old entry.

## Session close

When wrapping up a session:

1. Update the owning record: `PLAN.md` for Blockers or `docs/roadmap.md` for
   later classified work, replacing rather than stacking.
2. Update the **Current state** section of `rhemata-status.md`; overwrite that session state rather than appending to it.
3. Make one docs-only commit, separate from every code/build commit.

If no records need updating, say so instead of making a cosmetic commit.

## Explicit instruction required

Do not touch any of the following unless Alex explicitly scopes or approves it:

- Database writes outside the agent's own explicitly scoped task.
- Anything on the answer-generation or retrieval path when the task was not scoped to touch it.
- Doctrinal or position-paper content; it requires Alex's direct sign-off and must never be inferred from context.
