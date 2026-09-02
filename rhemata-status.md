# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.**

---

## Current state

**Biblical-depth Phases 0–8 are merged, deployed, and complete through a
verified hidden TIPNR production pilot.** PR #3 merged into `main` as
`ff89ba5`. Vercel is Ready and Railway reports `SUCCESS` for the New Wine API,
answer worker, search-analytics finalizer, and search-analytics retention
services on that exact revision. Production smoke checks returned HTTP 200 for
the API root, API docs, and `newwine.app`.

The release remains inert. `BIBLICAL_CONTEXT_ANSWER_ENABLED` is unset on both
the API and answer worker and therefore defaults to false. The existing blanket
commentary exclusion remains active, migration 097 is not read by the answer
path, the TIPNR source remains hidden, and protected-source and plural-viewpoint
registries remain empty. No feature activation, visibility change, live answer,
registry assignment, doctrinal assignment, or new production data write
occurred during deployment.

Migration 097 remains applied and verified with its RLS, closed policy classes,
metadata coupling, one-current uniqueness, append-only history, and restricted
grants intact. Production contains 21 current approved `general_context` rows:
the Phase 6 `H0175` proof plus the exact 20-item Phase 8 pilot. None has a
proposition, and the hidden retrieval probes remain empty.

The Phase 8 packet remains frozen at 10 people plus 10 places after excluding
`H0175`:

- selection checksum:
  `398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b`;
- packet hash:
  `a48f506a38db740d4d2cd8648c8de95ac7c25cb4550916e236a023738184a1e8`;
- zero-effect preview hash:
  `4171181b7003317044edafb8eeb836de7596f795489ba1bc8faafac72d716237`;
- sample hash:
  `ad2299d96582635f151b885d59f09b722297a10ab00354a46ddd5145c4041515`.

The successful retry made exactly 20 `text-embedding-3-small` requests under
USD `0.01` and committed one atomic 60-row transaction: 20 documents, 20
chunks, and 20 current policies. Coupled and independent fresh reconciliation
both passed at attempted `20`, stored `20`, errored `0`, skipped `0`, with zero
propositions and zero matches across 20 vector plus 20 FTS probes. The
verification payload hash is
`d50aa50a7d6493412fe66470f9afeb9f38be194f9926462edae86fb50a86ab9e`;
the immutable final evidence file hash is
`d4ddf85fa2e79f037f15faf2555cc2ea60024fbf3aed520d66a150aabe0a6df5`.

The earlier failed apply committed no rows. Its exact embedding count remains
unknown and conservatively bounded at 0–20 under its separate USD `0.01`
ceiling. Build commit `643c9f1` added structured, immutable failure evidence;
build commit `59dd15d` fixed the UUID-array completion stamp exposed by the
authorized rollback probe. The corrected probe staged all 60 rows, made zero
model calls, rolled back, and left all candidates clean. Its evidence hash is
`e57857768c8a398dce480dac6332c53f24a5dd765b641d0313c8a2e45f6983fc`.

Pre-merge verification passed all 159 biblical-depth checks/contracts: Phase 8
`24`, parser/inventory `39`, Phase 6 ingest `31`, manifests `4`, classification
`7`, policy `16`, routing `21`, and generation `17`. All changed executable
Python modules compiled under Python 3.12, Vercel preview passed, and the
independent pre-merge reviewer returned `ACCEPT` with no blocking findings.

The governing boundaries remain unchanged: protected charismatic topics need
Alex-approved exact source IDs; plural disputes need two distinct registered
and evidenced source slots; house papers are fence-only on the enabled path;
neighbors are rechecked; cache identity includes effective policy state; and
missing, stale, malformed, mixed, uncertain, prohibited, or unknown policy
state fails closed.

The Phase 7 inventory remains eligible `3,959`, malformed `172`, skipped `115`,
prohibited `16`, and duplicate `0`. After `H0175` and the Phase 8 pilot, 3,938
eligible TIPNR items remain. The ingestion-ready foundation benchmark is met,
but those items are Scheduled work and have no automatic execution authority.

---

## Session outcome and measures

- Original outcome: **completed** — the exact Phase 8 pilot was safely retried,
  committed, independently reconciled, merged, and deployed default-off.
- Acceptance: **passed** — 159 deterministic checks/contracts, compile proof,
  independent review, green Vercel/Railway deployments, and HTTP 200 production
  smokes.
- Unplanned investigations started: **1** — bounded diagnosis of the first
  apply evidence gap and rollback-probe UUID mismatch.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0**.
- Scope changes approved by Alex: exact pilot retry, PR #3 merge, default-off
  deployment, production verification, and session close. No larger ingestion,
  feature enablement, visibility change, registry assignment, doctrinal
  assignment, or live-answer authority was added.

---

## Next single item

**Decide whether to scope a later ingestion packet for the remaining 3,938
eligible TIPNR items.** It requires a fresh exact selection, cost ceiling,
rollback and reconciliation contract, and separate attended approval. Feature
activation, visibility changes, registry or doctrinal assignments, and live
answer testing remain separate attended decisions.
