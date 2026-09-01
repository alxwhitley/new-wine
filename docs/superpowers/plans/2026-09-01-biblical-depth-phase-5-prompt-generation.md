# Biblical Depth Phase 5 Prompt and Generation Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved default-off, route-scoped writer contract and deterministic generation validation to the primary async answer producer.

**Architecture:** A focused `source_use_generation_contract.py` module owns typed evidence lanes, prompt rendering, prompt fingerprinting, and deterministic output checks. `producer.py` remains the orchestration owner: it builds the contract only after Phase 4 routing finalizes, appends the request-scoped prompt, shares the existing one-retry budget, and suppresses citations/quotes on hard contract failure.

**Tech Stack:** Python 3.9, dataclasses, standard-library regex/hash/path utilities, existing unittest-style script tests.

**Spec:** `docs/superpowers/specs/2026-09-01-biblical-depth-phase-5-prompt-generation-design.md`

## Global Constraints

- `BIBLICAL_CONTEXT_ANSWER_ENABLED` remains default `false`; flag-off prompt, policy identity, generation, and position-paper fallback behavior remain unchanged.
- Migration 097 remains unapplied and both protected/plural registries remain empty.
- No database/network/model calls, production writes, registry assignments, ingestion, visibility changes, feature enablement, deployment, or doctrinal decisions.
- Modify only the implementation and test files allowlisted by the approved spec, followed by the two exact governing-text replacements in a separate docs commit.
- Preserve Phase 4 routing, exact protected-source filtering, independently rechecked neighbors, one-teacher shared routes, two-source plural evidence, and cache-state isolation.
- Use one combined retry maximum; do not add a Phase 5-specific second retry.
- Keep build and docs commits separate.

---

### Task 1: Route-scoped contract module and prompt

**Files:**
- Create: `backend/app/source_use_generation_prompt.txt`
- Create: `backend/app/services/source_use_generation_contract.py`
- Create: `scripts/test_source_use_generation_contract.py`

**Interfaces:**
- Consumes: finalized `QueryPolicy`, eligible chunk dictionaries, question text, and optional house-fence text.
- Produces: `build_generation_contract(question, query_policy, chunks, house_fence_text=None) -> SourceUseGenerationContract`, `render_generation_prompt(contract) -> str`, `validate_generated_answer(answer, contract) -> Tuple[str, ...]`, `render_retry_constraint(failures) -> str`, `SOURCE_USE_PROMPT_FINGERPRINT`, `SOURCE_USE_PRESENTATION_FAILURE`, and `SourceUseContractError`.

- [ ] **Step 1: Write failing contract tests**

Cover prompt rendering, general-reference identities, plural slot/source/display uniqueness, machine-only viewpoint keys, the reference heading rule, plural per-source headings, direct 12-token house-copy detection, question/evidence overlap exclusions, and deterministic retry text.

- [ ] **Step 2: Run the focused suite and confirm red**

Run: `PYTHONPATH=backend python3 scripts/test_source_use_generation_contract.py`

Expected: FAIL because `app.services.source_use_generation_contract` does not exist.

- [ ] **Step 3: Add the exact prompt template**

Store the approved base and four stance blocks in `backend/app/source_use_generation_prompt.txt` with format fields for `source_boundary`, `presentation_stance`, `issue_key`, and `evidence_lanes`. Keep the internal keys out of the instruction that describes user-facing headings.

- [ ] **Step 4: Implement the typed contract and validator**

Use frozen dataclasses for viewpoint lanes and the complete contract. Derive a plural display identity from a unique author, otherwise a unique title; raise `SourceUseContractError` if two required slots cannot receive distinct source IDs and identities. Validate `## Reference context` plus a grounded reference identity, one `##` heading containing each plural lane identity, and house-only 12-token normalized shingles.

- [ ] **Step 5: Run the focused suite and confirm green**

Run: `PYTHONPATH=backend python3 scripts/test_source_use_generation_contract.py`

Expected: all contract tests pass with no external calls.

### Task 2: Producer prompt, retry, and fail-closed integration

**Files:**
- Modify: `backend/app/services/async_answers/producer.py`
- Modify: `scripts/test_source_use_routing.py`
- Test: `scripts/test_source_use_generation_contract.py`

**Interfaces:**
- Consumes: Task 1's contract builder, renderer, validator, prompt fingerprint, retry renderer, error type, and fixed failure copy.
- Produces: enabled-path prompt identity containing the contract fingerprint and `source_use_generation=v1`; one combined writer retry; `no_material` with no citations/quotes on hard contract failure.

- [ ] **Step 1: Add failing producer integration tests**

Test flag-off prompt/policy parity, enabled fingerprint identity, route prompt injection, combined retry, post-retry failure suppression, plural coverage, reference separation, and enabled house-route rejection before the existing paper-voice fallback.

- [ ] **Step 2: Run focused producer suites and confirm red**

Run: `PYTHONPATH=backend python3 scripts/test_source_use_generation_contract.py && PYTHONPATH=backend python3 scripts/test_source_use_routing.py`

Expected: new integration assertions fail against the Phase 4 producer.

- [ ] **Step 3: Wire prompt and cache identity**

When enabled, append `:<SOURCE_USE_PROMPT_FINGERPRINT>` to effective prompt identity and `:source_use_generation=v1` to policy identity. Extend `_generate_and_capture()` with optional route prompt and retry constraint blocks; pass neither when the flag is off.

- [ ] **Step 4: Build the contract after route finalization**

Retain the matched house-paper body only as contract fence text. On enabled routes, build the contract from finalized policy and final eligible chunks. Convert construction failures into clean pre-writer `no_material` responses.

- [ ] **Step 5: Enforce fence-only enabled behavior**

If contradiction exclusion empties independently eligible evidence on an enabled house route, return clean no-material before `render_paper_voice_with_disclaimer()`. Preserve the existing fallback exactly when the feature flag is off.

- [ ] **Step 6: Share the one retry budget**

Evaluate existing attribution/quotation checks and Phase 5 validation after the primary call. If either fails, make one retry with the existing permitted-name constraint plus the full deterministic failure list. Preserve the sole-author deterministic label. If source-use failures remain, set the fixed presentation-failure answer, outcome `no_material`, and suppress citations, verified references, and quote selection.

- [ ] **Step 7: Run focused suites and confirm green**

Run: `PYTHONPATH=backend python3 scripts/test_source_use_generation_contract.py && PYTHONPATH=backend python3 scripts/test_source_use_routing.py`

Expected: both suites pass with no external calls.

- [ ] **Step 8: Commit the build**

Stage only the prompt, contract module, producer, and two test files. Commit message: `feat(policy): enforce source-use generation contract`.

### Task 3: Coherent regression verification

**Files:**
- No new files.

**Interfaces:**
- Consumes: completed Task 2 build.
- Produces: fresh evidence that the enabled contract did not regress the default-off answer path or adjacent deterministic guards.

- [ ] **Step 1: Compile changed Python files**

Run: `PYTHONPATH=backend python3 -m py_compile backend/app/services/source_use_generation_contract.py backend/app/services/async_answers/producer.py scripts/test_source_use_generation_contract.py scripts/test_source_use_routing.py`

- [ ] **Step 2: Run the approved no-cost regression set once**

Run the new contract and Phase 4 routing suites plus the existing source-use policy, passage-policy, single-author attribution, commentary exclusion, quote-selection gate, quote-rail regression, answer-latency contract, async-serving gate, and no-cost position-paper Tier A scripts discovered in the repository. Do not run a live-embedding or model-backed test.

- [ ] **Step 3: Inspect the build commit**

Run `git show --stat --oneline HEAD`, `git diff HEAD^ HEAD --check`, and `git status --short`. Confirm the build commit contains no documentation or governing files.

### Task 4: Apply approved governing replacements

**Files:**
- Modify: `CLAUDE.md`
- Modify: `ARCHITECTURE.md`

**Interfaces:**
- Consumes: the two exact replacement blocks in the approved spec.
- Produces: governing text that accurately describes the implemented default-off and enabled contracts.

- [ ] **Step 1: Replace CLAUDE decision #17 exactly**

Replace only the existing decision #17 paragraph with the approved conditional flag-off fallback / enabled fence-only wording.

- [ ] **Step 2: Replace the final Answer generation paragraph exactly**

Replace only the existing final paragraph in `ARCHITECTURE.md`'s Answer generation section with the approved route-contract and deterministic-validation paragraph.

- [ ] **Step 3: Verify the docs-only diff**

Run: `git diff --check && git diff -- CLAUDE.md ARCHITECTURE.md`

Confirm no implementation file is present and both blocks match the spec byte-for-byte in substance.

- [ ] **Step 4: Commit governing documentation separately**

Commit message: `docs: govern source-use generation contract`.

### Task 5: Final boundary audit

**Files:**
- No new files.

**Interfaces:**
- Consumes: build and docs commits.
- Produces: a clean handoff that stops before every production gate.

- [ ] **Step 1: Re-run the focused suites after both commits**

Run: `PYTHONPATH=backend python3 scripts/test_source_use_generation_contract.py && PYTHONPATH=backend python3 scripts/test_source_use_routing.py`

- [ ] **Step 2: Confirm commit separation and repository state**

Run: `git log -3 --oneline`, `git show --name-status --format= HEAD`, `git show --name-status --format= HEAD^`, and `git status --short --branch`.

- [ ] **Step 3: Stop before external authority gates**

Do not push, apply migration 097, populate registries, register or ingest a source, run a live answer, spend model funds, enable the feature, deploy, alter visibility, or write production data.
