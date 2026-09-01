# Biblical Depth Phase 4 — Routing and Retrieval Contract

**Date:** 2026-09-01

**Status:** PROPOSED. Read-only diagnostics are complete. Retrieval and answer-
path edits require Alex's explicit approval of this design and the governing-
text replacements below.

## Outcome

Add a deterministic, default-off routing boundary in the primary async answer
path so protected, general, and registered-plural questions cannot receive
ineligible source material.

## Acceptance criteria

1. Routing occurs before any new reference/commentary passage is considered.
2. The Phase 1 protected-topic registry is the canonical topic classifier.
3. Protected routes admit only topic-approved source IDs plus the existing
   position-paper fence; an empty or incomplete approval registry fails closed.
4. General shared routes retain the existing one-teacher lock and may append
   only separately attributed `general_context` passages.
5. Registered plural routes require two distinct registered viewpoint slots
   backed by two distinct registered source IDs; otherwise they return fixed
   corpus-gap wording before generation.
6. Existing license/visibility, disabled-source, attribution, commentary,
   neighbor, citation, and reference-verification gates remain effective.
7. With the feature flag off, candidate filtering is behaviorally identical to
   the current blanket commentary exclusion.
8. Local mocked tests prove zero protected-source leakage and no one-sided
   plural answer can reach the writer.

## Non-goals

- No production database write or migration application.
- No source registration, ingestion, visibility, licensing, or deployment.
- No prompt or generation-contract change; that belongs to Phase 5.
- No doctrinal decision, protected-source assignment, viewpoint-slot naming,
  or source-to-viewpoint assignment.
- No model-based routing or passage judgment.
- No release or feature-flag enablement.

## Read-only findings

- `producer.py` currently matches a position paper, injects background context,
  retrieves candidates, strips commentary before ranking, applies the one-
  teacher lock, expands neighbors, and strips commentary again.
- `match_chunks` and `search_chunks_fts` enforce existing source license and
  visibility rules, but their result rows do not include `documents.source_id`
  or `source_passage_policy_versions` metadata.
- Phase 1 already owns the canonical protected-topic detector and fail-closed
  query policy. The existing position-paper matcher remains the sole house-
  fence matcher and must not gain a second keyword registry.
- The production protected-source registry and issue viewpoint/source mappings
  are deliberately unassigned. Tests may inject synthetic UUID registries;
  production must not infer assignments from authors, corpus frequency, or
  source names.
- Migration 097 is unapplied. The default-off path must never query its table.

## Proposed interfaces and ordering

### Flag

Add `BIBLICAL_CONTEXT_ANSWER_ENABLED`, parsed once with default `false`.

- `false`: preserve the two existing commentary-equivalent strips and make no
  passage-policy query.
- `true`: run the new route and policy filters. This state is not authorized
  for production by approving implementation.

### Route lifecycle

1. `producer._produce()` calls the existing position-paper matcher once.
2. It calls `source_use_policy.classify_query()` with that exact match before
   retrieval. A detected registered issue may initially be `uncertain` because
   evidence is not yet known, but its boundary and `issue_key` are fixed.
3. Candidate retrieval keeps the existing RPC license/visibility gate.
4. A toolbox enrichment helper resolves each candidate's `source_id` from its
   `document_id` and, only when the flag is on, loads the candidate's current
   migration-097 policy row in bounded batch queries.
5. Candidate sets are split before teacher selection:
   - existing doctrinal candidates follow the current commentary exclusion,
     ranking, and one-teacher lock;
   - new reference candidates must pass the route-specific policy filter and
     cannot participate in teacher selection.
6. Neighbor expansion runs on the already-eligible seeds. Every returned
   neighbor is enriched and rechecked; parent metadata is not proof of the
   neighbor's passage policy.
7. On a registered issue, retrieved `orthodox_viewpoint` rows are converted to
   issue-scoped `ViewpointEvidence`, and `classify_query()` finalizes the stance.
   Fewer than two registered slots or sources returns deterministic corpus-gap
   copy before `_build_history()` or generation.
8. The writer receives one final, already-filtered context. Existing grounding,
   permitted-name, citation, quotation, and reference checks remain unchanged.

### Fail-closed rules

- Missing `source_id`, missing/current-duplicate policy, database error,
  unknown policy class, route mismatch, issue mismatch, viewpoint mismatch, or
  unregistered source drops the new reference candidate.
- A protected or mixed query uses the protected boundary for its entire writer
  context.
- Empty protected-source approvals admit no retrieved candidates. The existing
  house paper may remain silent fence context only on a real matcher result.
- `word_study` and Precept Austin remain excluded in Phase 4 regardless of flag.
- Existing ordinary corpus material is never silently reclassified as
  `general_context`; only migration-097 rows can unlock new reference material.

## File allowlist

- Modify `backend/app/services/async_answers/producer.py`.
- Modify `backend/app/services/answer_toolbox.py`.
- Modify `backend/app/services/position_papers.py` only if a small public
  registry adapter is necessary; no doctrinal text or matcher calibration.
- Create `scripts/test_source_use_routing.py`.
- Modify `scripts/test_position_paper_routing.py` only for routing regressions.

`backend/app/services/source_use_policy.py`, migration 097, prompts, ingestion,
and every serving surface outside the primary async answer path are frozen for
this phase.

## Test contract

Local mocks must cover:

- flag-off parity and zero migration-097 queries;
- protected/general overlap selecting protected for the whole context;
- protected approval by exact source UUID and rejection of every other UUID;
- no commentary, `word_study`, general reference, or unclassified neighbor on
  protected routes;
- one teacher plus separately labeled `general_context` on a general route;
- absent, mixed, uncertain, stale, duplicate, and malformed policy rows;
- two registered plural slots and sources reaching context;
- one slot, one source in two slots, unregistered sources, and issue/viewpoint
  mismatch returning the fixed corpus gap without generation;
- preservation of the position-paper fence, license/visibility assumptions,
  single-teacher lock, citation construction, and post-neighbor defenses.

The existing live-embedding position-paper test is not part of routine Phase 4
verification because it incurs external calls. Run it only under a fresh named
spend ceiling; mocked routing regressions remain mandatory.

## Exact governing-text replacements requiring approval

### Replace CLAUDE.md Settled decision #5 with

> **Commentaries remain excluded from ordinary answers by default and remain
> searchable in Study Mode.** The answer path retains its existing hard
> exclusion whenever `BIBLICAL_CONTEXT_ANSWER_ENABLED=false`. When that flag is
> separately approved and enabled, only a current migration-097
> `general_context` passage may support a general shared-Christian route, or a
> current registered `orthodox_viewpoint` passage may fill its exact issue-
> scoped slot on a plural route. Protected routes never receive general
> commentary/reference material; they admit only exact source IDs in Alex's
> topic-scoped protected-source registry. `word_study` and Precept Austin remain
> excluded. License, visibility, attribution, neighbor, citation, and reference
> gates still apply. Enabling the flag is a separate attended release decision,
> not implied by merging the implementation.

### Replace ARCHITECTURE.md Retrieval opening with

> Query expansion (3 variants via Groq) → vector + FTS per variant → RRF
> (K=60) → disabled-source and existing license/visibility gates →
> route/passage-policy enrichment and filtering when the default-off biblical-
> context flag is enabled; otherwise the existing hard commentary exclusion →
> separate doctrinal and eligible-reference pools → one-teacher lock on the
> doctrinal pool → bounded ranking/rerank → neighbor expansion → enrichment and
> route-policy recheck of every neighbor. Protected routes require exact
> topic-approved source IDs. General reference passages require a current
> eligible migration-097 policy row. Plural routes require two distinct
> registered, evidenced issue slots or return deterministic corpus-gap copy.
> `word_study` and Precept Austin remain excluded from ordinary answers.

Replace the current bullet “Commentaries never enter answer context” with:

> Commentaries do not enter answer context while the biblical-context flag is
> off. If separately enabled, only route-compatible, currently eligible policy
> rows can enter general or registered-plural context; protected routes,
> `word_study`, and Precept Austin remain excluded. Study Mode is unchanged.

## Approval boundary

Approval of this design authorizes only the allowlisted repository
implementation and local/mocked verification with the flag default-off. It does
not approve the governing-text edits themselves, populate either source
registry, apply migration 097, enable the feature, run a live answer, deploy,
or change source visibility.
