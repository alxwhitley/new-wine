# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.**
`origin/main` is `fa952da`. Biblical-depth PR #3 is reconciled with that main
line at integration merge `c3fc8e3`; it is not merged. Deployment state was not
rechecked in this session, and the integration branch itself was not deployed.

---

## Current state

**Biblical-depth Phases 0–5 are complete in repository scope.** PR #3 now
contains the approved rights/provenance manifests, canonical source-use policy,
hidden zero-write TIPNR/OpenBible preview tooling, deterministic passage
classification, migration 097, default-off routing/retrieval, and the Phase 5
prompt/generation contract. The Phase 5 implementation preserves the single
existing retry budget and deterministically validates reference separation,
plural lane identity, direct house-paper copying, permitted names, quotations,
citations, and references before serving.

The governing boundary remains unchanged:

- protected Spirit-filled/charismatic topics admit only exact source IDs from
  Alex-approved topic-scoped registries;
- general biblical/history context must remain separately labeled and may use
  only current eligible structured-reference passages;
- other orthodox disputes require two distinct registered and evidenced source
  slots, never corpus-majority inference or adjudication;
- every neighbor is rechecked, cache identities isolate effective policy state,
  and a house paper remains fence-only on the enabled path;
- mixed, uncertain, absent, malformed, stale, prohibited, and unknown passage
  classifications fail closed.

**Migration 097 is applied and verified in production.** The attended runner
applied exactly `097_source_passage_policy.sql` in one transaction. A fresh
`newwine_readonly_analysis` connection verified the table, RLS, closed-set and
metadata-coupling constraints, one-current partial unique index, append-only
trigger, no `anon`/`authenticated` grants, and no service-role DELETE/TRUNCATE
privilege. `classification_counts=[]`: the table contains zero policy rows.

**The feature remains inactive.** `BIBLICAL_CONTEXT_ANSWER_ENABLED` still
defaults to false, so production retains the existing blanket commentary
exclusion and does not read migration 097 on the answer path. Protected-source
and plural-viewpoint registries remain empty. No source was registered or
ingested, no classification batch ran, no visibility changed, no live answer
was requested, and no deployment or feature enablement occurred for this work.

**Integration state.** Current `main` was merged into the Phase branch without
rewriting history. The later Phase OpenBible contract was retained over main's
earlier add/add draft: `modern_associations` identity comes from the mapping
key, not a nonexistent nested `modern_id`. Main's newer frontend/product
landmines and the approved Phase 5 governing invariants both remain in
`CLAUDE.md`. The named Phase worktree's Alex-owned modified and untracked files
remain preserved and outside PR #3.

---

## Session outcome and measures

- Original outcome: **completed** — Phase 5 designed, approved, implemented,
  verified, committed, and pushed; migration 097 applied and verified; the PR
  branch reconciled with current main for integration review.
- Acceptance: **passed** — 4/4 manifest contracts, 24/24 parser tests, all 61
  Phase 3–5 policy/routing/generation tests, the no-cost answer-boundary
  regressions, 51/51 frontend tests, TypeScript, and lint with zero errors.
  Two already-recorded unused word-study warnings remain from current `main`.
  No production release claim is made.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0** after final verification/push.
- Scope changes approved by Alex: Phase 5 implementation/governing text,
  attended migration 097 application, branch push/pull, and PR integration
  readiness. No merge, deployment, source, registry, classification, or feature
  authority was added.

---

## Next single item

**Review PR #3 and make an explicit merge/deployment decision.** Merging to
`main` may rebuild production services and is not authorized by this record.
After that decision, Phase 6 begins design-only: specify one exact hidden
dataset slice, immutable identities and counts, cost ceiling, dry run,
single-item verification, rollback boundary, and fresh-read reconciliation.
Actual source registration or ingestion remains a separate attended approval.
