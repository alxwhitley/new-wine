# Quote Quality + Passage Taxonomy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a gold set of quality-gated, taxonomy-tagged quotes and presentation so private beta can turn quoting ON — without serving the legacy 793.

**Architecture:** LLM proposes exact spans + taxonomy tags → quality gate (Settled #29) → hardened `verify_quote_candidate` → persist with `quality_pipeline_version` → select by question↔`quote_text` only (no tag boost) among new-pipeline rows → UI separates quote with teacher/source attribution. Legacy rows stay live-but-unserved until marked selection-ineligible.

**Tech Stack:** Python 3.12, FastAPI/Supabase, `scripts/taxonomy.py` `VALID_TAGS`, Anthropic for propose, existing embeddings for selection, Next.js quote UI.

**Spec:** `docs/superpowers/specs/2026-08-19-quote-quality-and-topic-design.md`

**Lane:** Alex authorized Grok to implement this track (2026-08-19). Still no production DB quote writes without explicit attended approval per batch.

## Global Constraints

- `QUOTE_SELECTION_ENABLED` stays off until Task 8 (Alex attended).
- Topic labels = `scripts/taxonomy.py` `VALID_TAGS` only (import that module; do not fork).
- V1 selection = `quote_text` similarity only; no soft tag boost.
- Authenticity = `verify_quote_candidate` only; quality is upstream.
- Corpus LLM propose: named cost estimate + **$50 ceiling** unless Alex approves more.
- Build commits and docs commits stay separate.
- No book flat-chunk quote extraction.

## Cost estimate (gold slice — before any paid propose run)

| Slice | Docs | Chunks (approx) | Propose calls (1/chunk, capped) | Rough $ (Sonnet-class; refine before run) |
|---|---|---|---|---|
| Calibration dry-run | 3 | ~60–90 | ≤90 | **~$5–12** |
| Gold write | 10 | ~200–300 | ≤200 | **~$15–40** |
| Full Prince non-book | 496 | ~11,062 | thousands | **Well over $50 — not in this plan** |

**Rule:** print a fresh estimate from live doc/chunk counts + chosen model pricing in the dry-run script header; abort if projected > $50 without Alex’s written OK. Prefer one calibration pass, then one gold pass — do not iterate live against the corpus.

---

### Task 1: Boundary harden — DONE

**Status:** DONE (`9a4c141`).

- Root cause: open/close terminals allowed `\n\n` + next-section opener.
- Fix: `internal_paragraph_break` in `quote_verifier.py`.
- Tests: live evangelist overrun refuses; first paragraph alone accepts; full `test_quote_verifier.py` green.

---

### Task 2: Schema — pipeline version + topic_ids + selection eligibility

**Files:**
- Create: `migrations/089_quote_quality_pipeline.sql`
- Create: `scripts/apply_migration_089.py` (follow `apply_migration_088.py` gated pattern)
- Modify: `backend/app/services/quotes.py` (read new columns in resolve/select)
- Test: `scripts/test_quote_pipeline_schema.py`

**Produces:**
- `quotes.topic_ids text[]` nullable (legacy null)
- `quotes.quality_pipeline_version text` nullable (legacy null; new rows e.g. `quote_quality_v1`)
- `quotes.selection_eligible boolean NOT NULL DEFAULT true` — then set legacy to `false` in Task 6 (or default false for safety and only gold true — prefer: default true for backward compat while rail off; Task 6 sets legacy false and requires `quality_pipeline_version IS NOT NULL` for eligibility)

Recommended eligibility predicate for selection:

```sql
selection_eligible = true
AND quality_pipeline_version IS NOT NULL
AND status = 'approved'
```

Legacy backfill in same migration:

```sql
UPDATE quotes SET selection_eligible = false WHERE quality_pipeline_version IS NULL;
```

(Rail is off, so this is safe; makes intent explicit.)

- [x] **Step 1:** Write migration SQL + apply script with `--apply` gate and fresh-connection verify (`ed55817`).
- [x] **Step 2:** Unit/schema test asserting columns exist and legacy rows are `selection_eligible=false` after apply.
- [x] **Step 3:** Migration 089 **applied** to production (Alex-attended; recorded 2026-08-19 handoff).
- [x] **Step 4:** Commit migration + tests only (no apply in the commit).

---

### Task 3: Quality module (deterministic rubric on proposal fields)

**Files:**
- Create: `backend/app/services/quote_quality.py`
- Test: `scripts/test_quote_quality.py`

**Produces:**

```python
@dataclass(frozen=True)
class QualityVerdict:
    ok: bool
    rule: str
    reason: str | None

def assess_quote_quality(
    quote_text: str,
    *,
    restated_point: str | None = None,
    why_quotable: str | None = None,
    standalone_ok: bool | None = None,
) -> QualityVerdict:
    ...
```

Deterministic v1 checks (Settled #29 allows later model-assisted scoring; start deterministic):

1. Length band (e.g. 80–500 chars after strip).
2. No internal `\n\n` (defense in depth with verifier).
3. Reject deixis-heavy openers: regex for `^(Verse|Chapter|As I (said|mentioned)|This is a wonderful)`.
4. Reject if `standalone_ok is False` when provided by propose.
5. Reject if quote_text has no letter ratio / is mostly scripture citation pattern without teacher claim (keep conservative; prefer false refuse).

- [ ] **Step 1:** Failing tests for sample weak quotes from `docs/audits/quote_quality_sample_2026-08-19.md` (connective / “Verse 17…” class) and a strong standalone.
- [ ] **Step 2:** Implement `assess_quote_quality`.
- [ ] **Step 3:** Tests green; commit.

---

### Task 4: LLM propose (dry-run only first)

**Files:**
- Create: `backend/app/services/quote_propose.py` (prompt + parse + taxonomy validate)
- Create: `scripts/propose_quotes_dry_run.py`
- Create: prompt template with `prompt_version` stamp (e.g. `quote_propose_v1`)
- Test: `scripts/test_quote_propose_unit.py` (parse/validate; mock model)

**Produces:** structured candidates:

```python
@dataclass(frozen=True)
class ProposedQuote:
    quote_text: str
    char_start: int
    char_end: int
    restated_point: str
    topic_ids: list[str]  # must be subset of VALID_TAGS
    why_quotable: str
    standalone_ok: bool
```

Rules:

- Import `VALID_TAGS` from `scripts.taxonomy` (add `sys.path` like other scripts) or shared import path — **one** source.
- Reject unknown tags.
- `quote_text` must equal `window[char_start:char_end]` and be exact substring of source window.
- Dry-run script: `--doc-ids` or `--limit N`, prints proposals + quality + verify verdicts, **zero DB writes**. Mutation-test that `create_and_approve_quote` / raw INSERT are never called.

- [x] **Step 1:** Unit tests for JSON parse, taxonomy filter, offset check.
- [x] **Step 2:** Implement propose + dry-run CLI with cost projection printed up front.
- [x] **Step 3 (estimate-only):** Live projection on first-3 cleared Prince sermons — **~$1.42 / 59 windows**, under ceiling. Paid `--run` held for Alex OK. Note: `docs/audits/quote_propose_calibration_note_2026-08-19.md`.
- [x] **Step 4:** Commit code + calibration note (separate commits).

---

### Task 5: Gold write path (attended)

**Files:**
- Create: `scripts/extract_quotes_quality_pipeline.py`
- Modify: `backend/app/services/quotes.py` `create_and_approve_quote` to accept `topic_ids` + `quality_pipeline_version` (or insert path used by script)

**Flow per candidate:** quality pass → `verify_quote_candidate` → insert with `quality_pipeline_version='quote_quality_v1'`, `selection_eligible=true`, `topic` = primary taxonomy tag, `topic_ids` = list, `status` per policy (`pending` recommended for first gold; Alex can approve batch).

- [x] **Step 1:** Wire insert; dry-run mode default (`extract_quotes_quality_pipeline.py`; `create_and_approve_quote` accepts `topic_ids` / `quality_pipeline_version` / `status=pending`).
- [x] **Step 2:** Applied on the **3 calibration docs** (Alex go, 2026-08-19):
  `PYTHONUNBUFFERED=1 …/python scripts/extract_quotes_quality_pipeline.py --limit 3 --apply --status pending`
  (~59 chunks, ~$1.42 est). `QUOTE_SELECTION_ENABLED` untouched.
- [x] **Step 3:** Hard reconciliation — script: windows=59 proposals=42
  refused_quality=11 refused_verify=3 skipped_dup=0 stored=28 errors=0;
  live DB: 28/28 IDs pending + `quote_quality_v1` + `selection_eligible=true`
  + `topic_ids` set. Report:
  `quote_propose_review/gold_pipeline_apply_20260818T212522Z.json`.
- [x] **Step 4:** Apply-run complete; visual sign-off + re-enable remain Q3.

---

### Task 6: Selection uses new-pipeline eligibility only

**Files:**
- Modify: `backend/app/services/quotes.py` `select_quotes_for_answer`
- Test: `scripts/test_quote_selection_gate.py` and/or `scripts/test_quote_passage_relevance.py`

```python
# Only rows with quality_pipeline_version set AND selection_eligible
# Rank: sim(question, quote_text) >= 0.35; no tag boost
```

- [x] **Step 1:** Failing test: legacy approved row never selected even if text matches.
- [x] **Step 2:** Implement filter; tests green; commit.

---

### Task 7: Presentation (open-scope safety)

**Files:**
- Modify: frontend quote component(s) under `frontend/components/` (locate current quote rail render in `chat-message.tsx` / related)
- Test: lightweight component or snapshot check if present; else manual checklist in plan completion note

Requirements (Settled #28):

- Visually separated from answer prose.
- Teacher name + source/work title on the quote.
- Topic chip = primary taxonomy tag (`topic` / `topic_ids[0]`).

- [x] **Step 1:** Implement UI against gold resolve payload (`resolve_quote` adds `work_title` / `topic_ids` / `restated_point`; QuoteRail shows separation + teacher · work + topic chip).
- [ ] **Step 2:** Alex visual sign-off.
- [x] **Step 3:** Commit (sign-off still open).

---

### Task 8: Regressions + attended re-enable

**Files:**
- Create/extend: `scripts/test_quote_rail_regressions.py` (baptism false-positive class, no bad quote ids, etc.)

- [x] **Step 1:** Run regressions with flag off (selection dry) —
  `scripts/test_quote_rail_regressions.py` (`1eec654`): flag-off
  producer/SSE, no bad/legacy IDs, baptism FP class, honest no-support,
  teacher-card no quote surface, presentation source contract, eligibility
  mutation. Article-supported proof explicitly deferred until W5–W6.
- [ ] **Step 2:** Alex sets `QUOTE_SELECTION_ENABLED=true` in deployed env only after sign-off.
- [ ] **Step 3:** Smoke one real answer; confirm quote IDs are gold-pipeline only.
- [ ] **Step 4:** Docs/status update.

---

## Task dependency graph

```text
Task1 (DONE) → Task2 → Task3 → Task4 → Task5 → Task6 → Task7 → Task8
                 ↘________________↗
```

## Spec coverage checklist

| Spec requirement | Task |
|---|---|
| Boundary before rebuild | Task 1 DONE |
| Settled #29 quality gate | Task 3 (+ propose in 4) |
| Taxonomy reuse | Task 4–5 |
| Live-but-unserved → selection-ineligible | Task 2 + 6 |
| Gold before presentation deadlock | Task 5 then 7 |
| No soft boost v1 | Task 6 |
| Cost ceiling | Task 4–5 |
| Presentation before re-enable | Task 7 then 8 |
| Rail off until Alex | Task 8 |

## Out of scope (this plan)

- Full 496-doc Prince rebuild
- Tag soft-boost
- Book quote extraction
- Turning quoting on without Alex
