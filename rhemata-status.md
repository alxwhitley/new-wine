# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.** Remote `main`
remains at `12cb253`. Biblical-depth Phases 0–3 are on
`codex/biblical-depth-phases-0-3` in PR #3 and are not merged.

---

## Current state

**Biblical-depth Phases 0–3 are complete in repository scope.** PR #3 contains
11 commits (`c5ee5e0` through `35beb5f`) covering the approved rights and
provenance manifests, source-use policy, hidden zero-write TIPNR/OpenBible
preview tooling, deterministic passage classification, and migration 097.

The governing boundary remains unchanged:

- protected Spirit-filled/charismatic topics use only Alex-approved house
  material;
- general biblical/history context may use narrowly approved structured
  fields;
- other orthodox disputes require registered plural presentation rather than
  corpus-majority inference;
- model passage classification is refused in V1;
- mixed, uncertain, absent, prohibited, and unknown passage classifications
  fail closed.

**Migration 097 is committed but unapplied.** It creates the internal
`source_passage_policy_versions` table with closed-set and metadata-coupling
constraints, one current row per chunk, append-only history, RLS, and no
`anon`/`authenticated` access. The service role is limited to
SELECT/INSERT/UPDATE and cannot DELETE or TRUNCATE policy history. Applying the
migration remains a separate attended production-write approval, followed by
fresh verification through `newwine_readonly_analysis`.

**Verification passed with zero database connection or write:** 4/4 manifests,
16/16 Phase 1 policy tests, 24/24 Phase 2 parser/tooling tests, and 7/7 Phase 3
classification/migration-contract tests. Migration dry run parsed 15 statements
with checksum `7bbe9f431fc3da07c3062fa1c22e590425e2ca6c7810a783bb7be2ecdc87d375`.
The approved TIPNR single item classified `general_context`; the prohibited
Tyndale single item classified `uncertain` and answer-ineligible.

**No source registration, ingestion, visibility change, classification batch,
retrieval/answer-path wiring, production database write, or manual production
deployment occurred.** GitHub reports one automatic branch-preview deployment
for PR #3; no deployment command was run and `main` was not changed.

User-owned modified and untracked files already present in the shared worktree
were left untouched and remain outside PR #3.

---

## Session outcome and measures

- Original outcome: **completed** — hidden source-registration/ingestion
  tooling and deterministic versioned passage policy through Phase 3.
- Acceptance: **passed** — dry run and single-item proof preceded any future
  batch, and all pinned positive/negative fixtures passed.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0**.
- Scope changes approved by Alex: migration renumbered from occupied 096 to
  097; append-only history uses `ON DELETE RESTRICT`; internal table access is
  service-write/read-only-analysis only.

---

## Next single item

**Phase 4 — query routing and retrieval contracts.** Start with read-only
diagnostics and a bounded design. Do not edit retrieval or answer-generation
code until Alex explicitly approves that Phase 4 design. The required result is
structural enforcement that protected routes receive only approved protected
sources, general routes admit only eligible context, and registered plural
issues require two distinct evidenced viewpoint slots. No deployment, source
visibility change, or production database write is part of Phase 4.
