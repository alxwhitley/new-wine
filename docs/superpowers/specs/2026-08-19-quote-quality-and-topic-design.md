# Quote Quality Extraction and Passage-Level Topic Design

**Date:** 2026-08-19

**Status:** Confirmed by Alex in design review; ready for implementation planning

**Scope:** Path to extract *quality* quotes, assign *passage-level* topic tags
from a controlled vocabulary, and surface them on related answers — without
re-enabling the live quote rail until quality, tagging, presentation, and
legacy quarantine are in place.

## Objective

Build a quotes path where:

1. Extracted quotes are worth serving as standalone excerpts (not merely
   grammatically complete sentences).
2. Each quote is tagged from its own passage against a controlled topic
   vocabulary, so it can surface beside related topical answers and support
   browse/admin by topic.
3. Answer-time selection ranks primarily by question ↔ `quote_text` embedding
   similarity (the 2026-08-18 repair), with a soft boost when passage tags
   overlap the question's topics — never a hard tag gate.
4. The existing 793 approved/pending quotes are treated as untrusted legacy
   until re-extracted under this pipeline; the rail stays off until Alex
   explicitly re-enables it.

Success is a small gold set of newly extracted, quality-gated, correctly
tagged quotes that can attach to related questions under the hybrid selector,
with presentation that carries teacher/source on the quote itself. It is not
a full Derek Prince corpus rebuild in one pass, and it does not flip
`QUOTE_SELECTION_ENABLED`.

## Goals (user)

- Quality quotes are extracted.
- Quotes are tagged in the right way so they surface to a related topic.

## Non-goals (this design)

- Turning `QUOTE_SELECTION_ENABLED` on in production.
- Salvaging or quietly rewriting the 793 legacy rows in place as the v1
  quality fix.
- Putting “worth reading” judgments inside `verify_quote_candidate()` (that
  module stays provenance/authenticity only).
- Hard-filtering selection solely by topic tag match.
- Quote extraction from flat book chunks without trustworthy boundaries
  (standing exclusion).
- Expanding curated teachers beyond the existing confirmed set without a
  separate decision.
- Changing Settled decision #18’s deterministic authenticity verifier, or
  #28’s open teacher-scope product rule (presentation is required before
  re-enable; selection code may still need to catch up to #28 in a later
  phase).

## Approaches considered

### A — Tags as the primary selection index — rejected

Retrieve quotes by topic-tag match to the question. Attractive for
deterministic “related topic” behavior, but it recreates the failure mode
that forced containment: document-level (and even imperfect passage-level)
tags caused baptism false positives and exact ties. Wrong or incomplete tags
become wrong quotes with a teacher’s name attached — worse under open teacher
scope (#28).

### B — Embedding-only selection + accurate display tags — rejected as incomplete

Keep question ↔ `quote_text` as the only selection signal; fix extract quality
and make `topic` a truthful display label. Correct for relevance ranking, but
under-delivers the product goal of topic-aware surfacing and browse. Soft
overlap signal is cheap once tags are trustworthy on *new* rows.

### C — Hybrid (selected)

1. **LLM proposes** candidate quotes with structured fields (allowed by
   Settled decision #16: AI may propose, not approve authenticity).
2. **Deterministic quality rubric** gates “worth serving” before any
   pending/approved write.
3. **Existing `verify_quote_candidate()`** gates authenticity/provenance.
4. **Controlled-vocabulary passage tags** assigned at extract time from the
   quote (+ bounded surrounding context), never from
   `documents.topic_tags[0]`.
5. **Selection:** primary rank = question ↔ `quote_text` cosine (≥ 0.35);
   soft boost when tags overlap question topics; never hard-exclude on tag
   miss.
6. **Legacy:** quarantine the 793; rebuild under this pipeline.
7. **Presentation:** design visual separation + teacher/source on the quote
   before any re-enable (#28).

## Approved product decisions (this design review)

1. Hybrid retrieval: text primary, controlled tags soft-boost.
2. LLM propose + quality rubric + authenticity verify for extraction.
3. Controlled topic vocabulary (closed list); free-text topics rejected.
4. Legacy 793 quarantined as untrusted; not the v1 serving set.
5. Presentation for open teacher scope is required before re-enable.
6. Quality lives in a separate stage from `verify_quote_candidate`.
7. Rail remains default-off until Alex’s explicit attended gate.

## Architecture

```text
Source passage (chunk + bounded neighbors)
        │
        ▼
LLM propose (structured)
  quote_text, restated_point, topic_ids[], why_quotable, quality signals
        │
        ▼
Deterministic quality rubric  ──fail──► discard / log (never approve)
        │ pass
        ▼
verify_quote_candidate()      ──fail──► refuse + quote_verification_log
        │ pass
        ▼
Persist as pending or approved under policy
  passage-level topic_ids + primary_topic label
  (legacy rows excluded from selection until re-extract)
        │
        ▼
select_quotes_for_answer (flag still default off)
  score = sim(question, quote_text) [+ soft tag boost]
  threshold + (score, id) order + MAX_QUOTES_PER_ANSWER
        │
        ▼
resolve_quote() → UI
  quote visually separated; teacher + source on the quote
```

### Stage 1 — Propose (LLM)

For a bounded unit of source text (one eligible chunk, or chunk + small
neighbor window), the model returns a shortlist of candidates. Required
structured fields per candidate:

| Field | Role |
|---|---|
| `quote_text` | Exact contiguous substring of the supplied source text |
| `char_start` / `char_end` | Offsets into the supplied text (verifier re-checks) |
| `restated_point` | One-sentence paraphrase of the claim (display companion; not the quote) |
| `topic_ids` | 1–3 IDs from the controlled vocabulary |
| `why_quotable` | Short rationale against the quality rubric |
| `standalone_ok` | Boolean: readable without the surrounding argument |

Constraints on the propose step:

- May only quote text present in the supplied window (no paraphrase-as-quote).
- Prefer 1–3 sentence, complete thoughts; refuse deictic-only openers
  (“Verse 17…”, “As I said…”) unless the quote itself states the point.
- Cap proposals per document/chunk (exact caps set in the implementation
  plan; start conservative).
- Prompt version + model stamped on every proposal batch (provenance
  discipline parallel to propositions/positions).

### Stage 2 — Quality rubric (deterministic + structured checks)

Separate module (suggested: `quote_quality.py`). Does **not** replace the
authenticity verifier. Initial rubric dimensions (implementation plan
calibrates thresholds against a gold set Alex rates):

1. **Standalone** — no unresolved deixis; no mid-connective that only works
   after prior sentences.
2. **Complete thought** — ends on a full claim, not a setup clause.
3. **Substance** — not throat-clearing, not pure verse-read with no
   teacher claim, not audience banter.
4. **Boundary hygiene** — does not swallow the next section’s opening
   sentence (addresses PLAN’s known sample failure; may add checks beyond
   today’s edge-proximity rules).
5. **Length band** — keep within a calibrated char/sentence band suitable
   for the quote rail UI.

Fail → do not write a quote row (or write only to a proposal log if one is
added later). Pass → hand to authenticity verify.

A structured LLM score may *inform* the rubric only if every accept/refuse
is still explainable by named checks; do not revive a free-form
“claim-support judge” (Standing: Open Decision #20 shape is rejected). Prefer
deterministic checks on the proposal fields first; add model-assisted scoring
only if the gold set proves heuristics insufficient.

### Stage 3 — Authenticity (`verify_quote_candidate`)

Unchanged contract: exact substring, speaker confirmation, commentary /
ineligible exclusions, boundary-proximity/sentence-completeness, document
clearance at approve time, per-work cap. Auto-approve policy (Settled #18)
remains: authenticity pass may approve without a human — **quality must
already have passed upstream**, so weak quotes never reach this call.

### Stage 4 — Persist + tags

- Store passage-level `topic_ids` (controlled vocab) and a `primary_topic`
  display string derived from the vocab, not from `documents.topic_tags[0]`.
- Schema change (implementation plan): prefer a dedicated structure
  (e.g. `topic_ids text[]` + keep `topic` as primary display label, or a
  join table). Exact migration is planned later; this design requires that
  selection and display can read passage-level topics without inheriting
  document tags.
- Attribution: teacher + work/source title remain available for presentation
  (work title is attribution, not the topic label — closes the W7 label
  fork in favor of **semantic topic for the topic chip**, work title on the
  attribution line).

### Stage 5 — Selection (hybrid)

Keep:

- `QUOTE_SELECTION_ENABLED` exact `"true"` opt-in.
- `QUOTE_PASSAGE_SIMILARITY_THRESHOLD = 0.35` as primary floor on
  `sim(question_emb, quote_text_emb)`.
- Deterministic `(−score, id)` ordering and `MAX_QUOTES_PER_ANSWER`.

Add:

- Soft boost when the quote’s `topic_ids` intersect topics associated with
  the question (from query expansion / matched background topics / a small
  question→topic mapper defined in the plan). Boost is additive inside the
  ranker; a quote below the similarity floor still cannot attach.
- Selection eligibility: only quotes from the **new pipeline** (or an
  explicit `quality_pipeline_version` / clearance flag). Legacy rows are
  ineligible for selection even if `status='approved'`.

Open teacher scope (#28): presentation must ship before re-enable. Selection
may be widened to allow relevant quotes regardless of whose material wrote
the answer prose only after that UI contract exists; until then, keep the
safer retrieved-teacher filter in code if needed as a temporary belt — but
do not treat that temporary filter as reversing #28.

### Stage 6 — Resolve / present

`resolve_quote()` remains the only text resolution point. UI requirements
before re-enable:

- Quote visually separated from answer prose (not inline as if the answer
  voice said it).
- Teacher name and source/work attribution attached to the quote component.
- Topic chip shows `primary_topic` (passage-level).
- Restated point may sit beside the quote if product copy wants it; quote
  typography remains reserved for verified quote text only (Settled #17
  spirit).

## Legacy quarantine

Live audit (`docs/audits/quote_legacy_relevance_audit_2026-08-18.md`):
793 approved/pending; **592/793 (74.7%)** fail passage↔inherited-topic
relevance; all 592 are Derek Prince. Quality sample
(`docs/audits/quote_quality_sample_2026-08-19.md`): ~20% judged worth
serving.

Policy:

1. Do not re-enable the rail on this set.
2. Mark legacy ineligible for `select_quotes_for_answer` (flag/column/
   pipeline_version — exact mechanism in implementation plan).
3. Rebuild via the new propose→quality→verify path into new rows (or
   replace-in-place only under an attended, reconciled script with hard
   counts — prefer new rows + deprecate old to avoid silent meaning drift).
4. Optional: keep legacy rows visible in admin for comparison; they are not
   serving candidates.

## Controlled topic vocabulary

- Start from existing product topic surfaces where possible (document
  `topic_tags` inventory, background topics, house-position pillars) and
  publish a **closed list** in-repo.
- LLM propose may only emit IDs from that list; unknown IDs fail the quality
  / tag gate.
- Multi-tag allowed (1–3); one primary for display.
- Vocabulary edits are deliberate docs+code changes, not free-text drift.

Exact initial list is an implementation-plan deliverable, reviewed by Alex
before the first real write batch.

## Phased delivery

| Phase | Work | Stop condition |
|---|---|---|
| **A** | Spec (this doc) + implementation plan | Plan reviewed |
| **B** | Quality module + LLM propose (dry-run) + gold set calibration | Alex-rated sample meets agreed precision; no DB quote writes |
| **C** | Schema for passage topics + legacy ineligibility; migrate/flag | Legacy cannot be selected; new rows can store topic_ids |
| **D** | Hybrid selector + tests (rail still off) | Mutation-proven tests; live dry selection on gold set |
| **E** | Presentation (separation + attribution on quote) | UI contract signed off by Alex |
| **F** | Small attended re-extract (one teacher/work slice) | Hard reconciliation; quality sample pass |
| **G** | Attended `QUOTE_SELECTION_ENABLED` decision | Alex only; after W8-style regressions as required by PLAN |

Phases B–E are repo-first and may proceed while W5–W6 article proof remains
a separate attended track. Phase G must not silently expand the private-beta
gate; it remains an explicit Alex enablement.

## Risks and constraints

- **Misattribution under open scope:** presentation is load-bearing; do not
  re-enable without it.
- **LLM propose fabricating span text:** mitigated by exact-substring verify;
  proposals that are not exact substrings never persist.
- **Quality rubric gaming / vagueness:** calibrate on a gold set Alex rates;
  prefer named deterministic checks; avoid opaque judges.
- **Tag soft-boost overfit:** boost must not pull sub-threshold text matches
  above the floor; measure false positives on baptism/fasting/marriage
  clusters already used in calibration.
- **Cost:** any corpus-scale LLM propose run surfaces a cost estimate before
  execution ($50 ceiling unless Alex approves more — project rule).
- **Settled #18:** authenticity approval stays automatic and deterministic;
  quality is upstream eligibility, not a second human approver.

## Files likely touched (planning hint, not an implementation checklist)

- New: `backend/app/services/quote_quality.py` (or `scripts/` + shared module)
- New: propose script / prompt templates with version stamps
- `scripts/quote_candidates.py` — may remain structural helper for non-LLM paths
- `backend/app/services/quotes.py` — selection hybrid; legacy eligibility
- `backend/app/services/quote_verifier.py` — unchanged contract; optional
  boundary strengthening only if proven
- Migration for topic_ids / pipeline_version / legacy flag
- Frontend quote component — presentation contract
- Tests: quality rubric, propose dry-run, hybrid selector, legacy exclusion

## Evidence already in hand

- Passage-level selection fix and calibration: commit `82ec0f5`,
  `scripts/test_quote_passage_relevance.py`
- Legacy relevance audit: `docs/audits/quote_legacy_relevance_audit_2026-08-18.md`
- Quality sample: `docs/audits/quote_quality_sample_2026-08-19.md`
- Containment: `quote_selection_enabled()`, Landmines entry
- Settled #16/#17/#18/#19/#24/#28; PLAN.md W7–W8 + Quote quality blocker

## Open items for the implementation plan (not blocking this design)

1. Initial controlled vocabulary draft for Alex’s edit.
2. Gold-set size and rating rubric worksheet.
3. Exact schema for `topic_ids` / legacy ineligibility.
4. Whether first persist status is `pending` vs auto-`approved` after quality
   + verify (authenticity auto-approve may still apply; product may prefer
   pending for the first rebuild slice).
5. Question→topic mapper for soft boost (reuse retrieval topics vs small
   dedicated map).
6. Cost estimate for first Prince non-book re-extract slice.
7. Boundary-overrun root cause for sample quote 7 (investigate during Phase B).

## Approval

Alex confirmed in design review (2026-08-19 session):

- Hybrid architecture
- LLM propose + rubric + verify
- Controlled vocab + soft boost
- Legacy quarantine + presentation before re-enable
- Phased rollout A→G as sequenced above

Next step: implementation plan via `writing-plans` /
`docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md` after Alex
reviews this spec file.
