# Biblical Depth Phase 5 — Prompt and Generation Contract

**Date:** 2026-09-01

**Status:** APPROVED by Alex on 2026-09-01, including the exact governing-text
replacements below. This approval authorizes this design artifact only.
Implementation, governing-file edits, feature enablement, and production
operations remain separately gated.

## Outcome

Define the exact writer-facing prompt and deterministic generation contract for
the primary async chat path when the default-off biblical-context feature is
enabled. The contract must preserve Phase 4's pre-writer routing boundary while
preventing general-reference context, registered plural viewpoints, or a house
paper from influencing the answer outside their approved roles.

## Acceptance criteria

1. With `BIBLICAL_CONTEXT_ANSWER_ENABLED=false`, prompt contents, prompt and
   policy identity, generation behavior, and the existing position-paper
   fallback remain unchanged.
2. With the flag enabled, the finalized Phase 4 route is authoritative for the
   writer and cannot be reopened or reclassified from retrieved material.
3. General-reference context remains visibly separate from the one selected
   doctrinal voice and is attributed to a grounded reference identity.
4. A registered plural answer cannot serve unless every required distinct
   viewpoint/source lane appears separately in the answer.
5. Protected routes continue consuming only exact source IDs from the
   topic-scoped approved registry; no prompt instruction weakens that boundary.
6. On the enabled path, a house paper remains silent fence context only. It is
   never the sole answer substrate and does not supply distinctive answer
   phrasing.
7. Existing permitted-name, prose-quotation, citation, reference, license,
   visibility, commentary, word-study, neighbor, and attribution protections
   remain effective.
8. All correctable writer failures share one bounded retry with the existing
   attribution retry. Phase 5 adds no second retry loop.
9. Prompt wording and effective flag state participate in durable reuse and
   single-flight identity so answers cannot cross contract state.
10. Local mocked tests prove the success, retry, and fail-closed paths without
    a database, network, model, paid call, or production operation.

## Non-goals

- No Phase 5 implementation under this design-only approval.
- No production database write or migration application.
- No source registration, source assignment, ingestion, visibility, licensing,
  passage classification, or registry population.
- No doctrinal decision, protected-source assignment, viewpoint-slot naming,
  or source-to-viewpoint assignment.
- No model-based routing, passage judgment, truth judge, or semantic-faithfulness
  judge.
- No live answer, model spend, feature enablement, deployment, or release.
- No change to `GET /study/teacher/{source_id}` or any other served-generation
  surface outside the primary async chat producer.
- No broad rewrite of the existing global system prompt or theological
  guardrails.

## Read-only findings

- Phase 4 routes and filters every candidate before generation, labels eligible
  material as doctrinal, reference, or viewpoint context, independently
  rechecks neighbors, requires two distinct registered plural slots and source
  IDs, and isolates durable cache identity by flag state.
- The current global prompt still treats citable chunks as one undifferentiated
  class. It does not define how `[Reference Context]` or `[Viewpoint ...]`
  material may influence the answer.
- The global prompt contains static debate examples that can conflict with a
  later Alex-approved issue registry. The deterministic route must therefore be
  authoritative for the exact request without rewriting the global taxonomy.
- Current post-generation checks ground teacher names, attributed quotation
  wording, citations, and reference mentions, but do not prove general-reference
  separation or plural-lane coverage.
- `CLAUDE.md` Settled decision #17 still permits a position paper to become the
  answer substrate after contradiction exclusion empties retrieval. That is
  incompatible with the Phase 4 enabled-path rule that a house paper remains a
  silent fence only, so the conditional governing replacement below is required
  before implementation.
- Production migration 097 is unapplied, the biblical-context flag is off, and
  the protected and plural registries are empty. This design changes none of
  those facts.

## Chosen approach

Use an additive, route-scoped system block plus deterministic pre- and
post-generation validation. Do not rewrite the cached global system prompt.

Prompt-only enforcement is insufficient because the model can omit one plural
lane or blend reference context into a doctrinal voice. Separate calls per
viewpoint followed by synthesis would add latency, spend, and new semantic
failure surfaces. One route-scoped call with mechanically checked output is the
smallest design that preserves Phase 4's fail-closed posture.

## Writer contract lifecycle

1. Phase 4 completes routing, passage-policy filtering, teacher selection,
   neighbor expansion, neighbor rechecking, and plural-evidence finalization.
2. The producer constructs a typed `SourceUseGenerationContract` from the
   finalized `QueryPolicy` and the already-eligible chunks. Construction does
   not query a model, infer doctrine, or admit new evidence.
3. The contract assigns each writer-visible chunk to exactly one evidence lane:
   doctrinal source, general reference, registered viewpoint, or house fence.
4. A route-specific system block is appended after the existing cached system
   prompt and theological guardrails. It is request-scoped and not cached as a
   shared static block.
5. The existing single model call produces the answer.
6. Existing attribution, quotation, citation, and reference checks run together
   with the Phase 5 structural checks.
7. If any correctable check fails, one retry receives the complete set of failed
   requirements. No independent Phase 5 retry is added.
8. The retry output is checked once. Any remaining hard source-use failure
   returns fixed clean copy with no citations or quotes.

## Route-scoped prompt

The enabled producer appends this exact base block, with server-derived values
substituted into the braces:

> SOURCE-USE CONTRACT — MACHINE SELECTED
>
> The server selected this contract before generation. Do not reclassify the
> question from the retrieved material. This contract supersedes generic
> classification examples in the base prompt when they differ, but it never
> overrides New Wine's settled convictions or theological guardrails.
>
> Source boundary: `{protected_spirit_filled|general}`
>
> Presentation stance: `{house_position|shared_christian|plural|uncertain}`
>
> Registered issue: `{issue_key|none}`
>
> Use only the labeled evidence lanes supplied below. Never infer another
> source, viewpoint, or house conclusion from model memory.

The producer then appends exactly one stance block.

### `shared_christian`

> Preserve the selected doctrinal source as the answer's one doctrinal voice.
> `[Reference Context]` may clarify history, geography, language, literary
> setting, or textual context, but it cannot establish a doctrinal conclusion
> or become a second doctrinal voice. When reference context is supplied, place
> its contribution under `## Reference context` and name the actual reference
> source separately. Do not present reference-source interpretation as the
> selected teacher's claim.

### `plural`

> State only evidence-backed common ground first. Then give one clearly labeled
> section for every registered viewpoint lane listed below. Attribute each lane
> to its actual source, keep the positions distinct, and do not declare a
> winner, consensus, corpus majority, or house conclusion. Do not invent a
> missing side, merge two lanes into one synthesis, or expose internal registry
> keys in the answer.

### `house_position`

> The `[House Position]` material is a silent fence only. It may constrain what
> the answer claims, but it is not answer evidence. Never name it, cite it,
> quote it, copy its distinctive wording, or use it as the sole substrate for
> an answer. The answer must remain supported by independently eligible source
> material.

### `uncertain`

> Do not promote this question into a debate or infer a house position. State
> only what the approved evidence supports. Do not unlock, invent, or import
> another source or viewpoint.

The retry appends a short list of failed mechanical requirements to this same
contract. It does not introduce new evidence or a new classification.

## Evidence-lane identities

Internal issue and viewpoint keys remain machine-only. They are never user-
facing labels.

For each registered plural lane, the producer derives a grounded display
identity from already-retrieved metadata:

1. use a non-empty author when it is unique across the required lanes;
2. otherwise use a non-empty document title when it is unique across the
   required lanes; or
3. fail closed before generation when no distinct grounded display identity
   exists.

This rule does not classify a teacher or choose a viewpoint. It only supplies a
mechanically verifiable name for an already-registered, already-evidenced lane.

General-reference context retains Phase 4's `[Reference Context N]` writer
label. A grounded author or title from the eligible reference chunks supplies
the visible attribution target. Whenever the reference lane is non-empty, the
answer must keep its contribution under the required reference heading and name
a valid reference identity.

## Deterministic pre-generation checks

Before the writer is called on the enabled path:

- reassert that the contract was built from a finalized Phase 4 policy;
- reject any chunk without exactly one eligible evidence-lane role;
- preserve the exact protected-source allowlist already enforced by Phase 4;
- require two distinct registered viewpoint slots, source UUIDs, and grounded
  display identities for `plural`;
- require every plural lane to contain at least one still-eligible chunk after
  neighbor rechecking;
- preserve the one-teacher doctrinal pool on `shared_christian`;
- treat the house paper as fence metadata rather than answer evidence; and
- when the enabled house route has no independently eligible evidence after
  contradiction exclusion, return the existing clean no-material response
  before any writer call.

The last rule disables the paper-voice fallback only on the separately enabled
biblical-context path. Flag-off behavior remains unchanged.

## Deterministic post-generation checks

Phase 5 checks only properties that can be proven mechanically.

### General-reference separation

Whenever the reference lane is non-empty, require:

- a visible `## Reference context` heading; and
- at least one grounded display identity from an eligible reference chunk
  beneath that heading.

The prompt defines the lane's semantic limits. The checker does not pretend to
prove that every sentence was semantically classified correctly.

### Plural coverage

Require every registered lane's distinct grounded display identity to occur in
its own labeled section. A single identity cannot satisfy two lanes, and a bare
claim that an issue is "debated" cannot satisfy coverage.

This proves visible source-lane coverage, not theological truth or perfect
semantic faithfulness.

### House-paper copying

When a house fence is present, compare normalized 12-token shingles from the
answer against the paper. A match is not treated as paper copying when the same
normalized span also occurs in the user's question or independently eligible
retrieved evidence. Any remaining match is a hard source-use failure.

This check catches direct reproduction of distinctive paper wording without a
model judge. It does not claim to detect paraphrase or theological drift.

### Existing checks

The existing permitted-name, sole-author, ungrounded-teacher,
prose-quotation, citation, and reference checks remain authoritative. Phase 5
reuses their grounding inputs rather than building a parallel name or citation
universe.

## One-retry resolution

The primary output is evaluated once for all existing and Phase 5 requirements.
If retryable failures exist, the producer makes one constrained retry containing
the complete failed-requirement list.

After the retry:

- an ungrounded attribution retains the existing clean attribution refusal;
- omission of the sole citable author retains the existing deterministic
  `Source voice` label, provided no other hard check failed; and
- a remaining reference-separation, plural-coverage, or house-copy failure
  returns this fixed answer with outcome `no_material`, no citations, and no
  quote IDs:

> New Wine could not reliably present the available sources under this
> question's required source boundaries.

A pre-writer plural breadth failure continues to use the existing, distinct
corpus-gap copy:

> New Wine does not yet have enough registered source breadth to compare the
> approved viewpoints on this issue.

The two messages remain distinct because one reports missing eligible evidence
and the other reports a writer-output contract failure.

## Prompt and cache identity

The flag-off path retains the current `PROMPT_VERSION` and effective policy
identity exactly.

When the flag is enabled:

- the exact Phase 5 prompt file contributes a deterministic fingerprint to the
  effective prompt version;
- policy identity includes `source_use_generation=v1`; and
- the existing `biblical_context_answer=true` state remains present.

Therefore reuse and single-flight identity cannot cross flag state, cannot
reuse a Phase 4-only enabled answer under the Phase 5 contract, and cannot
survive a later wording change without a changed fingerprint. The fingerprint
is computed from the actual prompt text rather than relying only on a manual
version bump.

## File allowlist

- Modify `backend/app/services/async_answers/producer.py`.
- Create `backend/app/source_use_generation_prompt.txt`.
- Create `backend/app/services/source_use_generation_contract.py`.
- Create `scripts/test_source_use_generation_contract.py`.
- Modify `scripts/test_source_use_routing.py` only for integration,
  flag-parity, cache-isolation, and house-fence regressions.

Migration 097, passage classification, source registries, ingestion, global
system prompt, theological guardrails, frontend code, and every other served-
generation surface are frozen.

## Test contract

Local mocks must cover:

- flag-off byte-for-byte prompt and policy identity parity;
- enabled prompt fingerprint and `source_use_generation=v1` cache isolation;
- finalized route values appearing in the request-scoped contract;
- route contract overriding generic debate examples without modifying settled
  convictions or theological guardrails;
- one doctrinal voice plus separately headed and attributed reference context;
- rejection and one combined retry for blended or unattributed reference use;
- plural success with two distinct registered lanes, source IDs, identities,
  and answer sections;
- pre-writer rejection of duplicate sources, duplicate display identities,
  missing lanes, or missing identity metadata;
- one-sided or merged plural output triggering the combined retry and then
  fixed clean failure;
- no consensus, corpus-majority, winner, or inferred-house instruction on a
  plural route;
- enabled house routes never reaching the paper-voice fallback;
- direct distinctive paper copying triggering retry and clean failure;
- shared question/evidence spans excluded from the house-copy detector;
- preservation of the existing sole-author label and attribution refusal;
- no citations or quote IDs on a Phase 5 hard failure; and
- no database, network, model, or paid calls.

## Exact governing-text replacements requiring approval

Alex approved both replacements below on 2026-09-01. They are recorded here
but are not authorized to be applied until Phase 5 implementation is separately
approved.

### Replace `CLAUDE.md` Settled decision #17 with

> **If excluding every retrieved teacher would leave an empty answer, behavior
> depends on the biblical-context release state.** While
> `BIBLICAL_CONTEXT_ANSWER_ENABLED=false`, the existing position-paper voice
> fallback and deterministic disclaimer remain unchanged. When that flag is
> separately approved and enabled, the fallback is disabled: the position paper
> remains silent fence context only, and an empty independently eligible
> evidence set returns clean no-material copy before generation. The enabled
> path may never use the paper itself as answer substrate or supply the paper's
> distinctive phrasing. This does not alter decision #16's contradiction
> exclusion or authorize feature enablement.

### Replace the final paragraph of `ARCHITECTURE.md`'s “Answer generation” section with

> When the default-off biblical-context feature is enabled, `producer.py`
> appends a route-scoped generation contract derived from the finalized pre-
> writer policy. General-reference context remains visibly separate from the
> selected doctrinal voice; plural generation requires distinct labeled
> coverage of every registered evidence lane; protected routes retain their
> exact approved-source boundary; and a house paper remains silent fence
> context only. Deterministic validation shares the existing single retry budget
> and checks source-display coverage, reference separation, direct house-paper
> copying, permitted names, quotations, citations, and references. Failure after
> the retry serves fixed clean copy with no citations or quotes. Flag-off prompt
> and generation behavior remain unchanged, and enabled contract wording has
> its own reuse-key fingerprint.

## Verification sequence after separate implementation approval

1. Run read-only repository diagnostics before any build.
2. Implement only the allowlisted files, keeping the flag default-off.
3. Run the new mocked contract suite and the existing Phase 4 routing suite.
4. Run the existing attribution, quotation, citation, reference, commentary,
   quote-gate, async-serving, and position-paper no-cost regressions once as one
   coherent verification cycle.
5. Keep any build commit separate from the governing/docs commit.
6. Stop before migration application, registry population, feature enablement,
   live answer, deployment, or production write.
7. Before any later batch, require a dry run and one isolated item verification;
   end the batch with attempted/stored/errored/skipped reconciliation.

## Approval boundary

Approval of this design authorizes only this docs-only specification commit. A
separate explicit approval is required to implement the allowlisted repository
changes and apply the two governing-text replacements. Implementation approval
would still not authorize registry assignments, migration 097 application,
source registration or ingestion, a classification batch, feature enablement,
live model calls, deployment, visibility changes, or any production write.
