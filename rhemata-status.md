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

**Biblical-depth Phases 0–6 are complete through the attended hidden
single-item production proof.** PR #3 contains the approved rights/provenance
manifests, canonical source-use policy, hidden TIPNR/OpenBible preview tooling,
deterministic passage classification, migration 097, default-off
routing/retrieval, the Phase 5 prompt/generation contract, and the dedicated
Phase 6 writer/reconciler permanently limited to TIPNR entity `H0175`. The
proof path does not add a general proposition bypass to shared ingestion.

The immutable preview projected exactly one hidden licensed source, one alias,
one attributed `biblical_context` document, one chunk carrying four ordered
OSIS references, and one deterministic current `general_context` policy row;
its hash remains
`4b58d2f3e2860cdbe002e32eba8e47febfbb23d2d5ed63dd630fdec383b33b65`.
Alex separately approved and attended the exact `stepbible-tipnr` registration,
one 1536-dimension `text-embedding-3-small` request under the `$0.01` ceiling,
and one atomic `H0175` transaction. Production now contains that exact hidden
projection and policy ID `4e3169db-2aaf-4f0f-91e0-fc7c3a234625`; no proposition
exists for the document.

The governing boundary remains unchanged:

- protected Spirit-filled/charismatic topics admit only exact source IDs from
  Alex-approved topic-scoped registries;
- general biblical/history context remains separately labeled and may use only
  current eligible structured-reference passages;
- other orthodox disputes require two distinct registered and evidenced source
  slots, never corpus-majority inference or adjudication;
- every neighbor is rechecked, cache identities isolate effective policy state,
  and a house paper remains fence-only on the enabled path;
- mixed, uncertain, absent, malformed, stale, prohibited, and unknown passage
  classifications fail closed.

**Migration 097 remains applied and verified in production.** Its table, RLS,
closed-set and metadata-coupling constraints, one-current partial unique index,
append-only trigger, and privilege boundaries remain unchanged. The table now
contains the one approved `general_context` proof row.

**The feature remains inactive and the proof remains hidden.**
`BIBLICAL_CONTEXT_ANSWER_ENABLED` still defaults to false, so production retains
the existing blanket commentary exclusion and does not read migration 097 on
the answer path. Protected-source and plural-viewpoint registries remain empty.
No batch or proposition process ran, no visibility changed, no live answer was
requested, and no deployment or feature enablement occurred.

The initial post-commit verifier exposed a permission mismatch: the dedicated
analysis role can execute the security-invoker retrieval RPCs but cannot select
their `app_settings` dependency. No write or embedding retry occurred. Alex
approved build commit `494175e`, which keeps exact-state checks on
`newwine_readonly_analysis`, runs only the two RPC probes through a separate
service connection asserted read-only before queries, and preserves the apply
result if post-commit verification fails. Fresh reconciliation passed at
attempted `1`, stored `1`, errored `0`, skipped `0`, with vector `0` and FTS `0`.
The ignored proof artifact hash is
`fc749e7b68db61c0984073a13ed298027d7ca775679f37130bd2959547de368f`.

**Integration state.** Current `main` was merged into the Phase branch without
rewriting history. The later Phase OpenBible contract was retained over main's
earlier add/add draft: `modern_associations` identity comes from the mapping
key, not a nonexistent nested `modern_id`. Main's newer frontend/product
landmines and the approved Phase 5 governing invariants both remain in
`CLAUDE.md`. The named Phase worktree's Alex-owned modified and untracked files
remain preserved and outside PR #3.

---

## Session outcome and measures

- Original outcome: **completed** — the exact hidden Phase 6 production proof
  was authorized, atomically stored, and independently reconciled without
  releasing it to retrieval or answers.
- Acceptance: **passed** — 4/4 manifest contracts, 24/24 parser tests, all 61
  Phase 3–5 policy/routing/generation tests, the no-cost Tier A fence, and 31/31
  Phase 6 tests. Python compilation and diff checks pass. Live reconciliation
  proved attempted `1`, stored `1`, errored `0`, skipped `0`, and zero vector or
  FTS retrieval matches. The disclosed paid/live position-paper tiers were not
  run.
- Unplanned investigations started: **1** — the post-commit analysis-role/RPC
  permission mismatch, resolved without a privilege or database change.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0**.
- Scope changes approved by Alex: exact hidden source registration, one bounded
  embedding, one atomic `H0175` transaction, repository-only reconciliation
  remediation, and the governing-text replacement. No merge, deployment,
  batch, registry assignment, visibility change, live answer, or feature
  authority was added.

---

## Next single item

**Explicitly approve or decline a bounded Phase 7 TIPNR expansion design.** The
design must freeze inventory, cost, resumability, reconciliation, and sampling
before any later batch. The completed Phase 6 proof is not batch authority.
Visibility change, answer enablement, live answers, deployment, registry
assignments, and PR #3 merge remain separate attended decisions.
