# Biblical Depth and Source-Use Policy Implementation Plan

> **Status:** V1 implementation packet, revised after adversarial review.
> It does not authorize implementation, governing-record changes, production
> database writes, source visibility changes, deployment, or answer-path
> release. Commentary expansion is Triggered future work, not part of V1.

**Goal:** Add a deterministically classified biblical-context baseline and make
a narrow subset usable under independent source-boundary and presentation-
stance policies, without enabling free-form commentary or a model-based
passage judge.

**Spec:** `docs/superpowers/specs/2026-09-01-biblical-depth-source-policy-design.md`

## Global constraints

- Preserve the current blanket commentary exclusion until the release task.
- Do not alter position-paper doctrine.
- Do not create a teacher-family taxonomy.
- No production write without a dry run, one isolated hidden proof, hard
  reconciliation, and Alex's explicit attended approval.
- Every corpus-scale model run needs a named item/token/cost estimate before it
  starts and remains under the standing $50 ceiling unless Alex approves more.
- Use `shared_ingest.ingest_document()` for every document write.
- Keep Precept Austin excluded from ordinary answers and paraphrase generation.
- Keep commentary ineligible for the quote rail.
- Preserve unrelated working-tree changes.
- V1 admits only deterministically mapped structured fields. Doctrinal
  dictionary entries, theme articles, study notes, and free-form commentary
  remain answer-ineligible.
- Existing one-named-voice behavior remains on shared answers; plural is the
  only multi-position exception.
- Before answer-path work, Alex must explicitly approve the exact governing-
  record change replacing the current blanket commentary rule.

## Phase 0 — Human-required decisions and governing reconciliation

**Files created by this phase:**

- `docs/ingestion/source_manifests/tyndale_open_resources.yaml`
- `docs/ingestion/source_manifests/stepbible_data.yaml`
- `docs/ingestion/source_manifests/tipnr.yaml`
- `docs/ingestion/source_manifests/openbible.yaml`
- `docs/audits/2026-09/biblical_depth_source_registration_packet_2026-09-01.md`
- `scripts/test_biblical_source_manifests.py`

**Work:**

1. Collect read-only license and nested-rights evidence into the manifests.
2. Produce, but do not apply, exact proposed source rows: name, aliases,
   `license_status`, explicit visibility, citation mode, source kind, nested-
   rights disposition, attribution string, safe-mode behavior, and checksum.
3. Present the packet to Alex. Record `HUMAN_REQUIRED` until he decides each
   dataset; an executor cannot resolve licensing.
4. Present the exact replacement text for CLAUDE.md Settled decision #5 and
   implicated ARCHITECTURE text. Do not edit either until Alex explicitly
   approves that governing-record change.

**Exit:** every V1 dataset is either explicitly approved or excluded, and the
governing-record diff is explicitly approved. Otherwise stop.

## Phase 1 — Freeze policy fixtures and baseline tests

**File allowlist:**

- Create `backend/app/services/source_use_policy.py`
- Create `scripts/test_source_use_policy.py`
- Modify `scripts/biblical_coverage_cases.json` with protected and plural
  adversarial cases, without running paid generation yet

**Work:**

1. Define `SourceBoundary`, `PresentationStance`, `QueryPolicy`,
   `PassagePolicy`, protected topic keys, and approved-source interfaces.
2. Encode Alex's protected registry in one canonical module.
3. Add tests for direct, paraphrased, adjacent, and mixed protected queries.
4. Define an issue-registry interface with issue-scoped viewpoint slots. Use
   fictional labels in code tests; any real doctrinal slot names/content require
   Alex's direct sign-off before registration.
5. Preserve existing registered protected debates: healing mechanics,
   prophetic accountability, and apostolic authority. Preserve general plural
   treatment for eschatological timing.
6. Test mixed protected/general questions: protected source boundary wins,
   while stance remains house/plural/uncertain according to registered policy.
7. Prove no persistent teacher-family field or mapping is introduced.

**Exit:** deterministic policy fixtures pass locally; no answer behavior has
changed.

## Phase 2 — Deterministic source parsers

**File allowlist:**

- Modify only the Phase 0 manifests after an approved disposition
- Create `scripts/parse_tyndale_context.py`
- Create `scripts/parse_tipnr_context.py`
- Create `scripts/parse_openbible_context.py`
- Create `scripts/test_biblical_context_parsers.py`
- Create pinned fixtures under `scripts/fixtures/biblical_context/`

**Work:**

1. Parse only fields explicitly approved in Phase 0 and structurally mapped to
   `general_context` (initial target: cleared people/place/geography fields).
2. Do not parse doctrinal dictionary entries, theme articles, study notes, or
   commentary into V1 answer eligibility.
3. Do not duplicate the existing STEPBible lexicon/interlinear corpus.
4. Produce dry-run counts, duplicate detection, reference coverage, malformed
   row counts, and exact checksums.

**Exit:** deterministic parsers reproduce the same manifests/counts from pinned
inputs; zero DB writes.

## Phase 3 — Versioned deterministic passage policy

**File allowlist:**

- Create `migrations/096_source_passage_policy.sql` (096 is the next unused
  number as of this plan; stop for re-planning if it is occupied)
- Create `scripts/apply_migration_096.py`
- Create `scripts/classify_source_passages.py`
- Create `scripts/test_source_passage_classification.py`

**Work:**

1. Add append-only `source_passage_policy_versions`: `id`, `chunk_id`,
   `policy_class`, `protected_topic_keys`, `issue_key`, `viewpoint_key`,
   `classifier_kind`, `rule_version`, `model`, `prompt_fingerprint`,
   `reason_codes`, `is_current`, and `created_at`; foreign-key to `chunks`,
   closed-set CHECKs, metadata-coupling CHECKs, and one current row per chunk.
2. `classifier_kind='deterministic'` requires NULL model/prompt fields;
   `classifier_kind='model'` requires both non-NULL, but V1 refuses to create
   model rows.
3. History is append-only: replacement flips the former row's `is_current`
   false and inserts a new row in one transaction.
4. Make answer eligibility fail closed when classification is absent, mixed, or
   uncertain.
5. Map only approved structural fields to `general_context`; refuse all
   doctrinal/free-form fields. No model call and no classification cost in V1.
6. Provide migration dry-run/verify behavior; applying it is a separate
   attended production gate.

**Exit:** 100% of pinned approved fields map reproducibly to `general_context`;
100% of doctrinal/free-form/unknown fixtures remain ineligible; history and
closed-set constraints pass local tests; no production batch has run.

## Phase 4 — Query routing and retrieval contracts

**File allowlist:**

- Modify `backend/app/services/async_answers/producer.py`
- Modify `backend/app/services/answer_toolbox.py`
- Reuse/refactor `backend/app/services/position_papers.py` carefully
- Create `scripts/test_source_use_routing.py`
- Modify `scripts/test_position_paper_routing.py`

**Work:**

1. Route every question to a source boundary and presentation stance before
   reference eligibility is considered.
2. Reuse the position-paper fence for protected topics and make the expanded
   protected registry canonical rather than duplicating keyword lists.
3. On protected routes, structurally restrict writer context to approved source
   IDs plus existing house context.
4. On general routes, admit only `general_context` passages as separately
   attributed supporting context; preserve one selected doctrinal teacher.
5. On plural routes, use only Alex-approved issue-registry slots; require two
   distinct slots with evidence or emit deterministic corpus-gap wording.
6. Retain the current hard commentary exclusion behind a default-off feature
   flag so rollback requires no deploy or data mutation.
7. Preserve existing license/visibility, attribution, neighbor-expansion,
   citation, and reference-verification gates.

**Exit:** local/mocked tests prove the writer never receives general reference
or commentary on protected routes and cannot call a one-sided result consensus.

## Phase 5 — Generation and boundary verification

**File allowlist:**

- Modify `backend/app/system_prompt.txt`
- Modify `backend/app/services/async_answers/producer.py`
- Create `backend/app/services/source_use_verifier.py`
- Create `scripts/test_source_use_verifier.py`

**Work:**

1. Add generation contracts from both policy axes: house/shared/plural stance
   under protected/general source boundaries.
2. Require shared answers to ground doctrine in Scripture/approved evidence;
   reference material supplies context.
3. Require plural answers to state common ground, use registered viewpoint
   slots, attribute evidence, and avoid adjudication.
4. Add deterministic checks for allowed source IDs, eligible passage policy,
   two-group plural evidence, and existing permitted-name/reference grounding.
5. Regenerate once or refuse/disclose according to the existing hardened answer
   conventions; do not surgically rewrite prose.
6. Include the policy mode and classifier versions in the answer policy version
   so cached/reused answers cannot cross policy states.

**Exit:** targeted mutation tests fail when each structural guard is removed and
pass when restored. Required safety threshold is zero protected-source leaks,
zero plural answers with fewer than two registered evidenced slots, and zero
shared answers promoted to multi-position mode.

## Phase 6 — Hidden isolated ingestion proof

**Attended production gate; not authorized by this plan.**

**Files created by the implementation:**

- `scripts/preview_biblical_context_ingest.py`
- `scripts/ingest_biblical_context_batch.py`
- `scripts/reconcile_biblical_context_batch.py`
- `local/2026-09/biblical_context_v1_proof.json` (gitignored run manifest)

1. Present exact source, document, and passage counts plus cost estimate.
2. Run dry-run preview.
3. With Alex's explicit approval, register the source using the exact Phase 0
   disposition and ingest one explicitly hidden document/dataset slice. If Alex
   does not approve the hidden exception to the visible-default rule, stop
   `HUMAN_REQUIRED`; rollback-only evidence does not replace a persisted,
   independently reconcilable proof.
4. Reconcile attempted/stored/errored/skipped counts from a fresh read.
5. Verify attribution, license metadata, checksum, classification provenance,
   source identity, and non-retrievability while the flag is off.
6. Stop for explicit release approval.

## Phase 7 — Attended bounded ingestion batch

**Production gate; separately authorized after Phase 6.**

1. Freeze an immutable manifest of the exact source files/records, checksums,
   attempted document count, expected skip count, and maximum embedding/
   proposition cost.
2. Obtain Alex's explicit approval for that named batch and cost ceiling.
3. Run only that manifest through the shared ingestion path; no discovery or
   queue expansion during the run.
4. Record attempted, stored, errored, and skipped counts.
5. Independently verify those counts from a fresh read-only connection and
   verify that every stored row remains hidden and policy-ineligible.
6. Stop on any mismatch. Do not proceed to answer evaluation on a partially
   reconciled corpus.

The immutable run manifest path is
`local/2026-09/biblical_context_v1_batch.json`; the run report is
`local/2026-09/biblical_context_v1_batch_result.json`.

## Phase 8 — Narrow reference release and coverage measurement

**Attended answer-path/source-visibility gate; separately authorized.**

1. Enable only deterministically cleared structured context fields; V1 does not
   enable doctrinal dictionary/book-introduction prose or commentary.
2. Run protected-topic adversarial tests first; required result: zero general
   reference/commentary source IDs in protected writer context and citations.
3. Run plural tests; required result: at least two evidenced positions or an
   explicit corpus-gap disclosure.
4. Re-run the 15 weakest biblical-coverage cases.
5. Required improvement bar: zero case regresses in safety classification, at
   least 8 of the 15 weak cases improve by one audit band, and empty plus
   misretrieved totals do not increase. If it passes, run all 48 baseline cases.
6. Record cost, source concentration, strong/thin/empty/misretrieved counts, and
   compare to the 2026-08-31 baseline.
7. Alex performs the attended flag release or leaves the feature off.

## Phase 9 — Selected commentary expansion (Triggered; outside V1)

1. Start only after the reference release passes.
2. Continue only if a deterministic mapping exists or Alex separately approves
   a bounded model-classifier exception with error policy and thresholds.
3. Select one commentary set, classify it, and repeat the same dry-run/proof/
   reconciliation/evaluation gates.
4. Expand one source at a time; never flip all historical commentary at once.
5. Leave Precept Austin and quote-rail use excluded.

## Exact verification commands and timeouts

Timeouts are wall-clock ceilings enforced by the executing Codex command/tool;
exceeding one is a failed verification, not permission to wait indefinitely.
Every command must exit `0`. Test scripts must print a final zero-failure
summary; preview/reconciliation scripts must print their exact count tuple.

| Phase | Command | Timeout | Expected result |
|---|---|---:|---|
| 0 | `python3.12 scripts/test_biblical_source_manifests.py` | 120s | all approved/excluded dispositions and required fields accounted for |
| 1 | `python3.12 scripts/test_source_use_policy.py` | 120s | zero policy fixture failures |
| 2 | `python3.12 scripts/test_biblical_context_parsers.py` | 300s | byte-identical repeated parse; zero malformed pinned fixtures |
| 3 | `python3.12 scripts/test_source_passage_classification.py` | 180s | all approved structural fields eligible; all free-form/unknown fields refused |
| 3 | `python3.12 scripts/apply_migration_096.py --dry-run` | 120s | SQL parsed, no DB connection/write |
| 4 | `python3.12 scripts/test_source_use_routing.py` | 180s | zero protected leaks; registered plural slots enforced |
| 4 | `python3.12 scripts/test_position_paper_routing.py` | 300s | all existing pillar/debate regressions pass |
| 5 | `python3.12 scripts/test_source_use_verifier.py` | 180s | zero guard failures; each mutation fixture is refused |
| 6 | `python3.12 scripts/preview_biblical_context_ingest.py --manifest local/2026-09/biblical_context_v1_proof.json` | 900s | zero writes; exact attempted/stored=`0`/errored/skipped preview tuple |
| 6 | `python3.12 scripts/ingest_biblical_context_batch.py --manifest local/2026-09/biblical_context_v1_proof.json --apply` | 1800s | one approved hidden proof item attempted; separately approved production write only |
| 6 | `python3.12 scripts/reconcile_biblical_context_batch.py --manifest local/2026-09/biblical_context_v1_proof.json --readonly` | 300s | fresh-read counts exactly match the proof report |
| 7 | `python3.12 scripts/preview_biblical_context_ingest.py --manifest local/2026-09/biblical_context_v1_batch.json` | 1800s | zero writes; exact frozen batch counts/cost bound |
| 7 | `python3.12 scripts/ingest_biblical_context_batch.py --manifest local/2026-09/biblical_context_v1_batch.json --apply` | 7200s | only frozen manifest attempted; separately approved production write only |
| 7 | `python3.12 scripts/reconcile_biblical_context_batch.py --manifest local/2026-09/biblical_context_v1_batch.json --result local/2026-09/biblical_context_v1_batch_result.json --readonly` | 600s | fresh-read attempted/stored/errored/skipped counts agree exactly |
| 8 | `python3.12 scripts/biblical_coverage_audit.py --fixture scripts/biblical_coverage_cases.json --run-retrieval-readonly --output local/2026-09/biblical_coverage_v1_retrieval.json` | 1800s | all cases complete; no DB writes |
| 8 | `python3.12 scripts/biblical_coverage_audit.py --fixture scripts/biblical_coverage_cases.json --run-paid-readonly --max-cost-usd 1.50 --output local/2026-09/biblical_coverage_v1_answers.json` | 7200s | only after renewed $1.50 approval; hard cost stop honored |

After the separately approved migration apply, run
`python3.12 scripts/apply_migration_096.py --verify` (300s) against a fresh
read-only connection. The apply command must be copied from the script's
dry-run output verbatim and is not authorized by this plan.

## Final verification checklist

- Protected registry has one implementation and Alex-owned tests.
- Protected route writer context contains only approved protected sources.
- Unknown/mixed passage classification is ordinary-answer ineligible.
- Plural route requires two registered evidence slots and never uses corpus majority as a
  house position.
- No permanent teacher taxonomy exists.
- Rights/provenance manifest exists for every ingested dataset.
- All write paths use shared ingestion and reconcile counts.
- Current commentary exclusion is instantly recoverable by flag.
- Fifteen weak cases and full 48-case suite are compared to baseline.
- No production write, visibility change, flag flip, or deploy occurs without
  its own explicit attended approval.
