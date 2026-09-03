# Biblical Context Ingestion Completion Queue

> **For the primary Codex session:** Execute this queue continuously, one packet
> at a time. Complete every repository-only, local, and read-only step without
> pausing to ask Alex routine questions. Stop only at an attended gate explicitly
> named below or when a fail-closed condition makes further progress unsafe.

> **Required execution skill:** Use `superpowers:executing-plans` to work this
> queue in order, preserving its checkpoints and attended gates.

**Goal:** Finish the approved V1 biblical-context ingestion path: ingest all
eligible STEPBible TIPNR structural entities, then ingest the approved
OpenBible ancient-place fields, reconcile the complete hidden corpus, and
prepare—but do not perform—the separately governed answer-feature release.

**Starting state:** `main` is `ce5eb16`. Biblical-depth Phases 0–8 are merged
and deployed default-off. Production contains 21 exact TIPNR
`general_context` items (`H0175` plus the 20-item pilot), no propositions, and
zero hidden-retrieval matches. The frozen TIPNR inventory has 3,959 eligible,
172 malformed, 115 skipped, 16 prohibited, and 0 duplicate records; 3,938
eligible items remain. `BIBLICAL_CONTEXT_ANSWER_ENABLED` is unset/default-off,
the source is hidden, and protected/plural registries are empty.

**Architecture:** Preserve the Phase 6 proof and Phase 8 pilot as immutable
exact tools. Add a separate resumable full-batch path. TIPNR is processed in a
canonical sequence of 20 atomic batches: nineteen batches of 200 items and one
batch of 138. Each batch validates or reuses content-addressed vectors before a
write connection opens, writes exactly three rows per item, reconciles from a
fresh read-only connection, and persists immutable evidence. OpenBible follows
the same lifecycle but receives its own inventory, proof, approval, and batch
release; no authorization or outcome transfers from TIPNR.

**Tech stack:** Python 3.12, existing Phase 6–8 contracts, canonical JSON and
SHA-256 helpers, OpenAI `text-embedding-3-small` at 1,536 dimensions,
Postgres/pgvector through psycopg2, strict unittest fakes, ignored mode-0600
local evidence, Railway/Vercel default-off deployment.

**Governing sources:**

- `AGENTS.md`
- `CLAUDE.md` source-use, database-write, deployment, and feature-flag invariants
- `PLAN.md` (zero blockers at queue creation)
- `docs/roadmap.md` A4
- `rhemata-status.md`
- `docs/ingestion/source_manifests/tipnr.yaml`
- `docs/ingestion/source_manifests/openbible.yaml`
- `docs/superpowers/plans/2026-09-01-biblical-depth-phase-8-hidden-pilot.md`

## Autonomous execution contract

The executing session must not ask Alex to choose file names, batch size,
ordering, sample shape, retry policy, evidence location, or routine
implementation details. Those decisions are fixed here.

- Keep exactly one packet active. Begin the next packet immediately when the
  current packet's exit criteria pass.
- Run read-only diagnostics before edits. Diagnose and fix in-scope test or
  implementation failures without asking unless the smallest safe correction
  changes an invariant or widens authority.
- Use TDD for behavior changes. Commit each verified build slice separately.
  Keep build commits separate from docs/records commits.
- Use the primary session for all production operations. Never delegate a paid
  call, credential access, approval decision, migration, production write,
  deployment, or live answer.
- Classify adjacent findings immediately. Only a demonstrated beta-critical
  failure may become a Blocker; otherwise record it as Scheduled, Triggered, or
  Parked and continue the active packet.
- Preserve every unrelated modified or untracked file. Never move, rename,
  archive, or delete anything under `~/rhemata/`.
- Do not alter the Phase 6 `H0175` or Phase 8 20-item selection contracts to
  make the full batch easier. Reuse canonical helpers through new modules.
- All previews are incapable of network, database, model, or write access.
- All preflights use only asserted read-only sessions.
- Every finalized attempt report is canonical, content-addressed, mode `0600`,
  create-new, and ignored under `local/YYYY-MM/`.
- A failed batch stops later batches. Persist evidence, run read-only
  reconciliation, classify the exact state, and report one consolidated result;
  do not improvise a retry against uncertain production state.
- Unless a task says otherwise, its dependency is the immediately preceding
  task. A task is verified only when every acceptance checkbox and the nearest
  packet checkpoint pass; a dedicated `Verification` subsection adds to rather
  than replaces that contract.

### Actions that remain attended gates

This queue is preparation authority, not external-effect authority. Stop for
one consolidated approval packet at each `ATTENDED GATE` below. Do not create
an approval artifact before Alex gives the matching approval.

1. Any paid provider or embedding call.
2. Any production database transaction, including a rollback-only probe.
3. Push, PR merge, deployment, or production environment mutation.
4. Source visibility change.
5. Protected-source, plural-viewpoint, or doctrinal assignment.
6. `BIBLICAL_CONTEXT_ANSWER_ENABLED` activation or a paid live answer.

When a gate is reached, ask once. Include every exact hash, payload category,
request and cost ceiling, transaction and row ceiling, rollback behavior,
reconciliation requirement, merge/deploy target, and explicitly excluded
authority. Do not split one decision into serial approval turns when the exact
scope is already known.

---

## Packet 0 — Re-establish the immutable baseline

**Outcome:** The executing revision, artifact, deployed boundaries, and live
read-only state are known before implementation begins.

**Named non-goals:** No edits, embedding calls, write credentials, production
writes, visibility changes, feature changes, deployment, or merge.

### Task 0.1 — Repository and artifact diagnostics

**Acceptance criteria:**

- [ ] Read the governing sources listed above and the nearest applicable
  instructions.
- [ ] Confirm the tracked worktree is based on current `origin/main`; preserve
  unrelated working-tree files.
- [ ] Verify the pinned TIPNR artifact is 7,916,469 bytes with SHA-256
  `69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e`.
- [ ] Rebuild the Phase 7 inventory three times and require byte-identical
  counts, eligible checksum, and inventory hash.
- [ ] Run all 159 biblical-depth checks/contracts and compile the changed
  executable modules under Python 3.12.

**Verification:**

```bash
cd /Users/alexwhitley/newwine && TIPNR_TEST_ARTIFACT=/private/tmp/newwine-tipnr.txt python3.12 scripts/test_tipnr_hidden_pilot.py
cd /Users/alexwhitley/newwine && TIPNR_TEST_ARTIFACT=/private/tmp/newwine-tipnr.txt python3.12 scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && python3.12 scripts/test_biblical_context_ingest.py
cd /Users/alexwhitley/newwine && python3.12 scripts/test_biblical_source_manifests.py
cd /Users/alexwhitley/newwine && python3.12 scripts/test_source_passage_classification.py
cd /Users/alexwhitley/newwine && PYTHONPATH=backend python3.12 scripts/test_source_use_policy.py
cd /Users/alexwhitley/newwine && PYTHONPATH=backend python3.12 scripts/test_source_use_routing.py
cd /Users/alexwhitley/newwine && PYTHONPATH=backend python3.12 scripts/test_source_use_generation_contract.py
```

**Dependencies:** None.

**Estimated scope:** XS, read-only.

### Task 0.2 — Read-only production census

**Acceptance criteria:**

- [ ] Assert migration 097, source, alias, role, RLS, and constraint identity.
- [ ] Require exactly 21 exact-complete TIPNR items and zero propositions.
- [ ] Require the other 3,938 eligible identities to be clean.
- [ ] Require `BIBLICAL_CONTEXT_ANSWER_ENABLED` absent or exactly false on API
  and worker, hidden source visibility, and empty protected/plural registries.
- [ ] Record the census as canonical ignored-local evidence.

**Dependencies:** Task 0.1.

**Estimated scope:** S, read-only.

**Packet 0 exit:** Baseline exact and all checks green. Any mixed candidate
state is a hard stop with no build or write.

---

## Packet 1 — Freeze the remaining TIPNR corpus

**Outcome:** A pure contract deterministically freezes the exact 3,938-item
remainder and its 20 batch identities without external capability.

**Default decisions:**

- Canonical order is people by entity ID, then places by entity ID.
- Exclude the 21 exact-complete production identities by literal expected ID
  and projection hash, not by a caller-provided offset.
- Batch size is 200 except the final 138-item batch.
- Each item preserves only entity type/ID, approved original-language forms,
  and ordered OSIS references.
- The final quality sample is first, lower quartile, median, upper quartile, and
  last item per entity type; freeze the resulting ten literal IDs in a fixture.

### Task 1.1 — Add the full-corpus contract

**Files:**

- Create `scripts/tipnr_full_batch_contract.py`.
- Create `scripts/test_tipnr_full_batch.py`.
- Create `scripts/fixtures/biblical_context/tipnr_full_batch_expected.json`.

**Acceptance criteria:**

- [ ] RED tests pin artifact identity, Phase 7 hashes/counts, 3,938 remaining
  identities, ordering, 20 batch sizes, batch hashes, global packet hash, and
  ten sample IDs.
- [ ] The contract refuses caller selection, limit, offset, alternate source,
  unrecognized field, or any drift in the existing 21 completed projections.
- [ ] Serialized packet, text, fixture, and sample bytes contain none of the
  excluded TIPNR generated prose, translated-name comparisons, ambiguity prose,
  or relationships.

**Verification:**

```bash
cd /Users/alexwhitley/newwine && TIPNR_TEST_ARTIFACT=/private/tmp/newwine-tipnr.txt python3.12 scripts/test_tipnr_full_batch.py TipnrFullBatchContractTests
```

**Dependencies:** Packet 0.

**Estimated scope:** M, 3 files.

### Task 1.2 — Freeze pricing and reconciliation totals

**Files:** Same three Task 1.1 files.

**Acceptance criteria:**

- [ ] Report exact UTF-8 bytes and a conservative token estimate for all 3,938
  texts.
- [ ] Cap execution at 3,938 additional embedding requests and the existing
  conservative full-inventory ceiling of USD `0.02441808`; a lower computed
  estimate does not widen this ceiling.
- [ ] Freeze expected remaining rows at 3,938 documents, 3,938 chunks, and
  3,938 policies: 11,814 rows across 20 transactions.
- [ ] Freeze global post-ingest totals at 3,959 TIPNR documents/chunks/current
  policies and zero TIPNR propositions.

**Dependencies:** Task 1.1.

**Estimated scope:** S, existing files.

**Checkpoint:** Full contract tests green; canonical output identical across
three runs; build-only commit.

---

## Packet 2 — Build preview and read-only preflight

**Outcome:** The complete operation can be inspected and production can be
classified without model or write capability.

### Task 2.1 — Add the zero-effect preview

**Files:**

- Create `scripts/preview_tipnr_full_batch.py`.
- Modify `scripts/test_tipnr_full_batch.py`.

**Acceptance criteria:**

- [ ] Preview imports no network, database, OpenAI, or write dependency.
- [ ] Canonical output includes artifact/packet/batch hashes, item/row totals,
  payload categories, model/dimension, request/cost ceilings, samples, and
  explicit zero-effect reconciliation.
- [ ] Preview accepts only the pinned artifact and optional ignored-local output
  path; it has no `--apply`, selection, limit, offset, URL, or entity override.

**Verification:**

```bash
cd /Users/alexwhitley/newwine && TIPNR_TEST_ARTIFACT=/private/tmp/newwine-tipnr.txt python3.12 scripts/preview_tipnr_full_batch.py
```

**Dependencies:** Packet 1.

**Estimated scope:** S, 2 files.

### Task 2.2 — Add prefix-resumable read-only preflight

**Files:**

- Create `scripts/preflight_tipnr_full_batch.py`.
- Modify `scripts/test_tipnr_full_batch.py`.

**Acceptance criteria:**

- [ ] Classify source/H0175/pilot identity and every remaining candidate using
  an asserted read-only role.
- [ ] Accept only: all-clean; all-exact-complete; or an exact-complete prefix of
  whole batch boundaries followed by an all-clean suffix.
- [ ] Reject a partial item, partial batch, out-of-order completion, unknown row,
  stale policy, proposition, visibility drift, role drift, or migration drift.
- [ ] Report next batch index and exact remaining request/row ceilings without
  loading write or embedding dependencies.

**Dependencies:** Task 2.1.

**Estimated scope:** S, 2 files.

**Checkpoint:** Preview byte-stable; strict tripwire tests prove no external
capability; fresh read-only production preflight is all-clean at the remaining
3,938 identities.

---

## Packet 3 — Build attended resumable execution

**Outcome:** Exact same-day approval can drive one batch at a time with durable
request evidence, vector reuse, atomic writes, and immediate reconciliation.

### Task 3.1 — Add approval and vector-cache contracts

**Files:**

- Create `scripts/apply_tipnr_full_batch.py`.
- Modify `scripts/test_tipnr_full_batch.py`.

**Acceptance criteria:**

- [ ] Approval equality includes date, artifact/global packet hash, all 20 batch
  hashes, model, dimensions, payload disclosure, maximum 3,938 requests, USD
  `0.02441808`, 20 transactions, 11,814 rows, rollback probe, and required final
  reconciliation.
- [ ] The module loads no OpenAI or write dependency until approval equality and
  fresh preflight pass.
- [ ] Each batch validates all vectors for count, finite numeric values, 1,536
  dimensions, item hash, model, and packet/batch identity before opening a write
  connection.
- [ ] Validated vectors may be cached only in content-addressed mode-0600 ignored
  local evidence bound to model, dimensions, rendered hashes, and batch hash.
  Cache mismatch fails closed; it never silently regenerates or substitutes.

**Dependencies:** Packet 2.

**Estimated scope:** M, 2 files.

### Task 3.2 — Add atomic per-batch writer

**Files:** Same Task 3.1 files.

**Acceptance criteria:**

- [ ] Batch transactions insert only the exact documents, chunks, and current
  `general_context` policies for that batch.
- [ ] Source, alias, completed TIPNR rows, propositions, visibility, registries,
  settings, and unrelated tables have no write path.
- [ ] Use parameterized SQL, local statement/lock timeouts, staged exact-count
  checks, UUID-array completion stamp, commit-once, and rollback-on-exception.
- [ ] First/middle/last embedding failures, connection failure, every staging
  failure, commit uncertainty, and evidence collision produce structured
  request/transaction counters and immutable evidence.

**Dependencies:** Task 3.1.

**Estimated scope:** M, existing files.

### Task 3.3 — Add fresh per-batch and global reconciliation

**Files:**

- Create `scripts/reconcile_tipnr_full_batch.py`.
- Modify `scripts/test_tipnr_full_batch.py`.

**Acceptance criteria:**

- [ ] After each commit, reconnect read-only and require the completed prefix to
  be exact, the suffix clean, zero propositions, and attempted = stored +
  errored + skipped.
- [ ] Run one vector and one FTS hidden-retrieval probe per newly completed item
  and require zero matches while the feature remains off.
- [ ] Final global reconciliation requires all 3,959 eligible TIPNR identities
  exact-complete; malformed/skipped/prohibited identities absent; 3,959 current
  policies; zero propositions; and all deterministic samples exact.

**Dependencies:** Task 3.2.

**Estimated scope:** S, 2 files.

### Task 3.4 — Add rollback-only structural probe mode

**Files:** Task 3 files only.

**Acceptance criteria:**

- [ ] Probe stages the first remaining 200-item batch with deterministic
  zero-vectors, verifies all 600 staged rows and completion stamping, always
  rolls back, and performs fresh all-clean postflight.
- [ ] Probe makes zero model requests and cannot commit even if a caller passes
  a commit-like option.
- [ ] Probe authorization is distinct in the approval mapping but may be named
  together with the later exact execution in one consolidated attended request.

**Dependencies:** Task 3.3.

**Estimated scope:** S, existing files.

**Checkpoint:** Full TIPNR suite and all 159 existing checks pass; changed
modules compile; mutation tests prove approval, cache, transaction, and
reconciliation gates are load-bearing; build-only commits remain separated.

---

## Packet 4 — Review and assemble one TIPNR approval packet

**Outcome:** Everything safe is complete. Alex receives one exact decision that
can authorize the rollback probe, paid embeddings, production transactions,
merge/deploy, and reconciliation without later routine questions.

### Task 4.1 — Independent pre-release review

**Acceptance criteria:**

- [ ] Review correctness, privacy/security, atomicity, resumability, payload
  boundaries, cost accounting, hiddenness, feature-off behavior, registry and
  proposition isolation, rollback, and evidence durability.
- [ ] Resolve every Critical/Required finding in build-only commits and rerun
  the full verification matrix.
- [ ] Require reviewer verdict `ACCEPT`; otherwise stop with one consolidated
  defect report rather than asking design questions serially.

**Dependencies:** Packet 3.

**Estimated scope:** M, read-only review plus bounded fixes if required.

### Task 4.2 — Produce the exact approval request

**Acceptance criteria:**

- [ ] Include final commit, artifact/global/batch/preview hashes, exact item and
  row counts, rendered bytes, payload disclosure, model/dimensions, request and
  cost ceilings, rollback-probe operation, 20 transaction identities,
  reconciliation/sample requirements, rollback triggers, and evidence paths.
- [ ] Separately enumerate merge/deploy of default-off tooling, rollback-only
  probe, paid embedding calls, production writes, and final verification so one
  Alex response can explicitly authorize each exact operation.
- [ ] State that approval does not authorize feature enablement, visibility,
  live answers, registry/doctrinal assignments, OpenBible, or any other source.

**Dependencies:** Task 4.1.

**Estimated scope:** S, docs/evidence only.

### ATTENDED GATE TIPNR

Stop here. Do not create the same-day approval artifact, push/merge/deploy,
request embeddings, load write credentials, run the rollback probe, or write
production until Alex explicitly authorizes the exact Packet 4.2 operations.

---

## Packet 5 — Execute TIPNR after exact approval

**Outcome:** All 3,959 eligible TIPNR items are exact-complete and independently
reconciled while remaining hidden and answer-inactive.

### Task 5.1 — Materialize and validate same-day approval

- [ ] Create the ignored mode-0600 approval artifact from Alex's exact words.
- [ ] Re-run preview and preflight; require hashes unchanged and state ready.
- [ ] Verify production feature flags, source visibility, roles, migration, and
  registries again immediately before execution.

### Task 5.2 — Run the rollback-only 200-item probe

- [ ] Stage and verify 600 rows with zero-vectors, force rollback, then prove all
  3,938 remaining candidates clean from a fresh read-only connection.
- [ ] Persist evidence and continue automatically only if every probe and
  postflight assertion passes.

### Task 5.3 — Execute the 20 batches

For batch 1 through 20:

- [ ] Reconfirm exact prefix/suffix state and batch identity.
- [ ] Generate or validate cached vectors within the global request/cost ceiling.
- [ ] Commit the exact 600 rows, or 414 rows for the final batch, atomically.
- [ ] Reconcile the committed prefix, clean suffix, zero propositions, and zero
  matches across the new batch's vector/FTS probes.
- [ ] Persist immutable evidence before advancing.

Do not ask between clean batches. On any mismatch, stop later batches, preserve
evidence, perform read-only state classification, and report the exact safe
recovery boundary.

### Task 5.4 — Independent global reconciliation

- [ ] Use fresh read-only connections independent of the writer.
- [ ] Require 3,959 exact TIPNR documents, chunks, and current policies; zero
  propositions; excluded identities absent; source hidden; feature off.
- [ ] Require global eligible-inventory accounting of attempted `3,959`, stored
  `3,959`, errored `0`, skipped `0`, while separately reporting this run as
  `3,938` attempted/stored and the original 21 as pre-existing.
- [ ] Verify deterministic ten-item quality sample and final evidence hashes.

**Packet 5 exit:** TIPNR V1 hidden ingestion complete.

---

## Packet 6 — Close TIPNR and prepare OpenBible

**Outcome:** TIPNR is durably closed and the next single item becomes the
OpenBible ancient-place inventory.

### Task 6.1 — Records-only TIPNR closure

- [ ] Replace A4 and `rhemata-status.md` state with exact completed counts,
  evidence hashes, spend/request totals, and unchanged default-off boundaries.
- [ ] Record process measures and make one docs-only commit separate from build
  and execution commits.
- [ ] Do not change `PLAN.md` unless a demonstrated beta-critical failure was
  promoted under `AGENTS.md`.

### Task 6.2 — Re-read OpenBible authority

- [ ] Re-read the manifest and governing policy after TIPNR closes.
- [ ] Keep cross references, OSM-derived coordinates/geometry, media,
  translation arrays/counts, and free-form descriptions prohibited.
- [ ] Begin Packet 7 immediately; no question is required for these already
  settled exclusions.

---

## Packet 7 — Make OpenBible ancient places execution-ready

**Outcome:** The pinned 1,341-row `ancient.jsonl` dataset has a deterministic
eligible inventory, hidden single-item proof, and resumable full-batch tooling.

### Task 7.1 — Freeze the complete ancient-place inventory

**Files:**

- Create `scripts/inventory_openbible_context.py`.
- Create `scripts/openbible_full_batch_contract.py`.
- Create `scripts/test_openbible_full_batch.py`.
- Create an exact compact expected fixture under
  `scripts/fixtures/biblical_context/`.

**Acceptance criteria:**

- [ ] Verify the pinned repository/archive and `ancient.jsonl` hashes and all
  1,341 structural rows.
- [ ] Preserve only approved ID, friendly label, closed place types, OSIS
  references, and qualified candidate identification ID/name/integer score.
- [ ] Refuse unknown fields/shapes and report eligible, malformed, skipped,
  prohibited, and duplicate outcomes with canonical hashes.
- [ ] Select the first eligible place by canonical place ID as the isolated
  proof. Freeze its literal identity and projection hash.

**Dependencies:** Packet 6.

**Estimated scope:** M, 4 files.

### Task 7.2 — Build OpenBible preview, preflight, and proof writer

**Files:**

- Create `scripts/preview_openbible_hidden_proof.py`.
- Create `scripts/preflight_openbible_hidden_proof.py`.
- Create `scripts/apply_openbible_hidden_proof.py`.
- Modify `scripts/test_openbible_full_batch.py`.

**Acceptance criteria:**

- [ ] Zero-effect preview and read-only preflight follow Phase 6/8 capability
  separation without importing the TIPNR source identity.
- [ ] Same-day approval freezes hidden source+alias registration, one embedding,
  one atomic source/alias/document/chunk/policy transaction, and reconciliation.
- [ ] Candidate identifications remain explicitly qualified; integer scores are
  never rendered as probability or categorical fact.

**Dependencies:** Task 7.1.

**Estimated scope:** M, 4 files.

### ATTENDED GATE OPENBIBLE PROOF

After all repository tests and independent review pass, stop once with the exact
proof payload, model/request/cost ceiling, source-registration rows, transaction
hash, reconciliation, merge/deploy scope, and exclusions. Do not infer approval
from TIPNR.

### Task 7.3 — Execute and reconcile the proof after approval

- [ ] Merge/deploy only the approved default-off tooling if explicitly included.
- [ ] Materialize exact same-day approval, preflight all-clean, make one
  embedding request, commit the exact proof atomically, and reconcile freshly.
- [ ] Require source hidden, zero propositions, zero vector/FTS matches, feature
  off, and immutable evidence before continuing.

### Task 7.4 — Build the remaining OpenBible batch packet

- [ ] Exclude the exact proof identity and freeze the remaining eligible set.
- [ ] Use 200-item atomic batches and one final remainder batch; compute exact
  batch count, hashes, request/row totals, token estimate, and cost ceiling from
  the approved rendered texts rather than assuming all 1,341 rows are eligible.
- [ ] Add prefix-resumable preflight, vector cache, rollback-only first-batch
  probe, writer, per-batch reconciliation, global reconciliation, and a
  deterministic first/quartile/median/quartile/last sample.
- [ ] Run the complete biblical-depth plus OpenBible regression matrix and obtain
  independent `ACCEPT` review.

### ATTENDED GATE OPENBIBLE BATCH

Stop once with one consolidated exact approval request for the rollback probe,
paid embeddings, bounded transactions, merge/deploy if required, and final
reconciliation. No cross-reference, visibility, registry, doctrine, feature,
or live-answer authority is included.

### Task 7.5 — Execute and reconcile OpenBible after approval

- [ ] Run the authorized rollback probe and require clean postflight.
- [ ] Execute clean batches without pausing between them.
- [ ] Stop on the first mismatch; otherwise finish independent global
  reconciliation, exclusion checks, hidden retrieval probes, and sample review.

**Packet 7 exit:** Approved OpenBible ancient-place V1 data hidden and exact;
cross references and all excluded field families absent.

---

## Packet 8 — Final ingestion census and closure

**Outcome:** Every reviewed V1 reference record is accounted for as stored or
deliberately excluded, and no further ingestion work is implied.

### Task 8.1 — Independent complete corpus census

- [ ] Reconcile registered sources/aliases, licenses/attribution, visibility,
  documents, chunks, current policies, propositions, and vector/FTS behavior.
- [ ] Match TIPNR totals to the frozen 4,262-outcome inventory.
- [ ] Match OpenBible totals to its newly frozen complete inventory.
- [ ] Prove prohibited TIPNR fields, OpenBible cross references, geometry,
  media, translation data, free-form descriptions, and unknown fields are absent.
- [ ] Record exact attempted/stored/errored/skipped counts, provider requests and
  spend, transaction totals, evidence hashes, and deterministic samples.

### Task 8.2 — Close A4 ingestion state

- [ ] Replace A4 and `rhemata-status.md` with the final hidden V1 corpus state.
- [ ] Keep `BIBLICAL_CONTEXT_ANSWER_ENABLED` default-off and registries empty.
- [ ] Make a docs-only commit separate from all build/execution commits.
- [ ] Push/merge/deploy only with Alex's exact attended authorization; otherwise
  leave a clean, reviewed branch and one consolidated integration request.

**Packet 8 exit:** Biblical-context ingestion is complete. The answer feature is
still inactive.

---

## Packet 9 — Prepare, but do not perform, answer-feature release

**Outcome:** Alex receives one evidence-backed release decision packet without
any visibility, doctrinal, registry, flag, or paid live-answer change.

### Task 9.1 — Build the release-readiness packet

- [ ] Re-run current-policy/cache, flag-off, protected, plural, neighbor,
  house-fence, generation-contract, attribution, license, visibility, citation,
  and reference-verifier tests.
- [ ] Define an honest-empty test set and a representative general-context test
  set using only already-approved structured facts.
- [ ] Inventory exact decisions still requiring Alex: protected source UUIDs,
  plural viewpoint/source slots, whether hidden sources may serve while hidden,
  paid live-answer ceiling, canary audience, monitoring thresholds, and rollback.
- [ ] Do not propose doctrinal mappings or infer them from teachers, authors,
  corpus frequency, or the ingested data.

### ATTENDED GATE FEATURE RELEASE

Stop. Feature activation is a new release operation, not part of ingestion.
Require separate explicit approval before changing environment variables,
visibility, registries, doctrine, running paid live answers, or widening the
audience.

---

## Final definition of done

The ingestion process is finished only when:

- [ ] All 3,959 eligible TIPNR identities are exact-complete with zero TIPNR
  propositions and every noneligible outcome accounted for.
- [ ] Every eligible OpenBible ancient-place identity is exact-complete with
  zero propositions and every excluded/invalid outcome accounted for.
- [ ] All sources remain correctly licensed, attributed, and hidden.
- [ ] Independent fresh reconciliation agrees with every per-batch report.
- [ ] Every provider request, dollar amount, transaction, row, sample, and
  evidence artifact reconciles exactly.
- [ ] Cross references and every prohibited field family are absent.
- [ ] The feature remains default-off until the separate Packet 9 decision.
- [ ] Build, execution, and records commits remain cleanly separated.
- [ ] `PLAN.md` still contains only real Blockers; A4 and current status are
  replaced rather than stacked.

## Queue stop conditions

Routine failures are diagnosed and fixed within the active packet. Stop without
asking serial questions only when one of these occurs:

1. An attended gate is reached.
2. Production is mixed, partial within a batch, out of canonical order, or has
   an uncertain commit outcome that fresh read-only reconciliation cannot prove.
3. Artifact, manifest, license, attribution, schema, role, visibility, feature,
   registry, or governing invariant drifts.
4. A proposed fix would touch doctrine, broaden allowed fields, weaken a safety
   gate, delete/move data, or expand beyond A4.
5. A demonstrated beta-critical failure is found.

At a stop, return one concise evidence packet: completed tasks, exact blocker or
gate, hashes/counts, preserved state, smallest safe next operation, and one
consolidated authorization request if authorization can resolve it.
