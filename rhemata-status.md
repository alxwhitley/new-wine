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

**Biblical-depth Phases 0–8 are complete through a verified hidden TIPNR
production pilot.** PR #3 contains the approved rights/provenance
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

Phase 7 made no model call or database connection. The exact pinned
7,916,469-byte TIPNR artifact contains 4,262 structural marker records: three
documentation records and 4,259 entity records. Deterministic classification
closed at eligible `3,959`, malformed `172`, skipped `115`, prohibited `16`,
and duplicate `0`; eligible people/places are `3,055`/`904`. The eligible
checksum is
`1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2`
and canonical inventory hash is
`edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040`.
Three repeated runs were byte-identical. The cost projection is 3,959 later
embedding requests over 1,831,354 canonical UTF-8 bytes, conservatively
610,452 tokens, estimated USD `0.01220904`, with a proposed maximum ceiling of
USD `0.02441808`; it is evidence for a later packet, not spend authority.

Phase 8 freezes exactly 20 additional items: the first 10 eligible people and
first 10 eligible places by entity ID after excluding `H0175`. The selection
checksum is
`398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b`,
the complete packet hash is
`a48f506a38db740d4d2cd8648c8de95ac7c25cb4550916e236a023738184a1e8`,
and the zero-effect preview payload hash is
`4171181b7003317044edafb8eeb836de7596f795489ba1bc8faafac72d716237`.
The 20 rendered texts total 5,463 UTF-8 bytes, conservatively estimate 1,821
tokens and USD `0.00003642`, and are capped at 20
`text-embedding-3-small` requests and USD `0.01`. The fixed sample IDs are
`G0010`, `G0132`, `G0223J`, `G0009`, `G0137`, and `G0494`; sample hash is
`ad2299d96582635f151b885d59f09b722297a10ab00354a46ddd5145c4041515`.

The Phase 8 preview has no network, database, or model capability. Read-only
preflight requires exact H0175 verification and a unanimous all-clean or
all-exact-complete 20-item state. The apply gate requires an exact same-day
approval, validates all 20 vectors before opening a write connection, and can
write only one atomic 60-row transaction: 20 documents, 20 chunks, and 20
current `general_context` policies. It does not insert or update the existing
source, alias, or `H0175`, and has no proposition write path. Fresh
reconciliation requires all 20 exact-complete rows, zero propositions, and
zero matches across 20 vector plus 20 FTS probes.

The first authorized apply attempt produced no durable report and committed no
database rows; a fresh read-only check found all 20 candidates clean. Because
the failed process did not preserve request counters, its exact embedding count
is unknown and conservatively bounded at 0–20 under its separate USD `0.01`
ceiling. Build commit `643c9f1` added structured request counters and immutable,
content-addressed attempt evidence. An authorized rollback-only probe then
found a live UUID/text completion-stamp mismatch; build commit `59dd15d` casts
the document IDs to `uuid[]`. The corrected rollback probe staged all 60 rows,
made zero model requests, rolled back, and left all 20 candidates clean. Its
evidence hash is
`e57857768c8a398dce480dac6332c53f24a5dd765b641d0313c8a2e45f6983fc`.

Alex separately authorized a fresh retry. It completed exactly 20 additional
`text-embedding-3-small` requests under USD `0.01`, validated all vectors, and
committed the exact atomic 60-row transaction. Both the coupled verifier and a
fresh independent read-only reconciliation passed at attempted `20`, stored
`20`, errored `0`, skipped `0`, with zero propositions and zero matches across
all 20 vector and 20 FTS probes. The sample hash remains exact, the verification
payload hash is
`d50aa50a7d6493412fe66470f9afeb9f38be194f9926462edae86fb50a86ab9e`,
and the immutable final evidence file hash is
`d4ddf85fa2e79f037f15faf2555cc2ea60024fbf3aed520d66a150aabe0a6df5`.

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
contains 21 current approved `general_context` rows: the `H0175` proof plus the
20-item Phase 8 pilot.

**The feature remains inactive and the proof remains hidden.**
`BIBLICAL_CONTEXT_ANSWER_ENABLED` still defaults to false, so production retains
the existing blanket commentary exclusion and does not read migration 097 on
the answer path. Protected-source and plural-viewpoint registries remain empty.
No proposition process ran, no visibility changed, no live answer was
requested, and no deployment or feature enablement occurred. The successful
pilot does not authorize ingestion of the remaining 3,938 eligible TIPNR items.

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

- Original outcome: **completed** — the exact balanced 20-item Phase 8 pilot
  committed atomically and passed both coupled and independent reconciliation;
  the biblical-depth foundation has met its ingestion-ready benchmark.
- Acceptance: **passed** — 24/24 Phase 8 tests, 4/4 manifest contracts, 39/39
  parser/inventory tests, all 61 Phase 3–5 classification/policy/routing/
  generation tests, and 31/31 Phase 6 tests. The corrected rollback probe
  staged and rolled back all 60 rows with a clean postflight. The authorized
  retry completed exactly 20 requests, stored 20/20 items with zero errors or
  skips, and both fresh reconciliations found zero propositions and 40/40
  retrieval probes with zero matches.
- Unplanned investigations started: **1** — the failed first-attempt evidence
  gap and rollback-probe UUID mismatch were diagnosed only to close the active
  pilot safely.
- Findings promoted to Blocker: **0**.
- Active critical-path item at close: **0** — any larger TIPNR ingestion remains
  Scheduled work rather than an active blocker.
- Scope changes approved by Alex: the exact preflight, initial apply attempt,
  failure-evidence hardening, rollback probes and UUID fix, fresh 20-request
  retry, atomic 60-row production transaction, and fresh reconciliation. No
  full-corpus batch, merge, deployment, registry assignment, doctrinal
  assignment, visibility change, live answer, or feature authority was added.

---

## Next single item

**Decide whether to scope a later ingestion packet for the remaining 3,938
eligible TIPNR items.** Any such packet requires a fresh design, exact selection
and cost ceiling, rollback and reconciliation contract, and separate attended
approval. The verified pilot supplies no automatic continuation authority.
Visibility change, answer enablement, live answers, deployment, registry
assignments, doctrinal assignments, and PR #3 merge remain separate attended
decisions.
