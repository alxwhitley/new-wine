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

**Biblical-depth Phases 0–6 are complete through the repository and zero-effect
preview boundary.** PR #3 now
contains the approved rights/provenance manifests, canonical source-use policy,
hidden zero-write TIPNR/OpenBible preview tooling, deterministic passage
classification, migration 097, default-off routing/retrieval, and the Phase 5
prompt/generation contract. Phase 6 adds a dedicated approval-gated writer and
fresh read-only reconciler permanently limited to TIPNR entity `H0175`; it does
not add a general proposition bypass to shared ingestion. The implementation
preserves the single existing retry budget and deterministically validates
reference separation,
plural lane identity, direct house-paper copying, permitted names, quotations,
citations, and references before serving.

The Phase 6 zero-effect preview projects exactly one hidden licensed source,
one alias, one attributed `biblical_context` document, one chunk carrying four
ordered OSIS references, and one deterministic current `general_context`
policy row. It predicts one 1536-dimension `text-embedding-3-small` request under
a `$0.01` ceiling. Both authorization flags are false; preview hash is
`4b58d2f3e2860cdbe002e32eba8e47febfbb23d2d5ed63dd630fdec383b33b65`.

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

**The feature and proof remain inactive.** `BIBLICAL_CONTEXT_ANSWER_ENABLED` still
defaults to false, so production retains the existing blanket commentary
exclusion and does not read migration 097 on the answer path. Protected-source
and plural-viewpoint registries remain empty. No source was registered or
ingested, no embedding or classification batch ran, no visibility changed, no
live answer was requested, and no deployment or feature enablement occurred for
this work. The isolated worktree has no database env files, so the final fresh
collision recheck belongs to the attended production packet; the earlier
read-only diagnostic found no proposed name/slug/alias/document collision and
zero policy rows.

**Integration state.** Current `main` was merged into the Phase branch without
rewriting history. The later Phase OpenBible contract was retained over main's
earlier add/add draft: `modern_associations` identity comes from the mapping
key, not a nonexistent nested `modern_id`. Main's newer frontend/product
landmines and the approved Phase 5 governing invariants both remain in
`CLAUDE.md`. The named Phase worktree's Alex-owned modified and untracked files
remain preserved and outside PR #3.

---

## Session outcome and measures

- Original outcome: **completed at the authorized boundary** — Phase 6 was
  designed, implemented, adversarially reviewed, committed, and exercised only
  through the zero-effect preview. No production proof was authorized or run.
- Acceptance: **passed in repository scope** — 4/4 manifest contracts, 24/24
  parser tests, all 61 Phase 3–5 policy/routing/generation tests, the no-cost
  Tier A fence, and 29/29 Phase 6 tests. Python compilation and diff checks pass.
  The disclosed paid/live position-paper tiers were not run. No production
  release or ingestion claim is made.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **1** — the separately approved attended
  Phase 6 single-item production proof.
- Scope changes approved by Alex: Phase 6 design, local implementation, tests,
  and zero-effect preview. No merge, deployment, source registration,
  ingestion, embedding spend, registry/classification assignment, visibility,
  live answer, or feature authority was added.

---

## Next single item

**Prepare and explicitly approve or decline the attended Phase 6 production
packet.** Before any effect, re-run collision diagnostics through
`newwine_readonly_analysis` and verify current embedding pricing under the
`$0.01` ceiling. Approval must separately name the exact hidden source
registration, single embedding request, and one atomic `H0175` transaction.
The run must stop after fresh read-only reconciliation; it does not authorize a
batch, visibility change, answer enablement, live answer, deployment, or PR
merge. PR #3 remains unmerged and its merge/deployment decision is still
separate.
