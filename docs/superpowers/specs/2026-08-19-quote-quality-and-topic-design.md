# Quote Quality Extraction and Passage-Level Topic Design

**Date:** 2026-08-19

**Status:** Revised after adversarial review (Claude Code + Grok); Alex
confirmed beta **ships with quoting ON**, so this work is launch-critical.
Ready for implementation planning only after the preconditions in
**Blockers before implementation** are met.

**Scope:** Path to extract *quality* quotes, assign *passage-level* topic tags
from a controlled vocabulary, and surface them on related answers — without
re-enabling the live quote rail until quality, tagging, presentation, boundary
hardening, and a gold serving set exist.

**Lane:** Spec/analysis may be authored in Grok. **Implementation is
answer-accuracy work and is outside Grok’s lane** — build in Codex/Claude
(attended primary session), not via Grok.

## Objective

Build a quotes path where:

1. Extracted quotes are worth serving as standalone excerpts (not merely
   grammatically complete sentences).
2. Each quote is tagged from its own passage against a controlled topic
   vocabulary Alex authors, so tags support display, browse/admin, and
   (later) optional selection boost — never document-tag inheritance.
3. Answer-time selection ranks by question ↔ `quote_text` embedding
   similarity (the 2026-08-18 repair). **V1 does not soft-boost from tags.**
4. The existing 793 approved/pending quotes remain in the database as
   **live-but-unserved** while `QUOTE_SELECTION_ENABLED` is off during the
   build; they are not an ambiguous third state. They become selection-
   ineligible before any re-enable, and are not the v1 serving set.
5. Private beta **requires quoting on** (Alex, 2026-08-19). This rebuild,
   vocabulary, presentation, and boundary fix are therefore on the launch
   critical path — not post-launch.

Success is a small gold set of newly extracted, quality-gated, correctly
tagged quotes, with presentation that carries teacher/source on the quote
itself, proven under selection with the rail still off, then an attended
re-enable. It is not a full Derek Prince corpus rebuild in one pass.

## Goals (user)

- Quality quotes are extracted.
- Quotes are tagged in the right way so they surface to a related topic.

## Non-goals (this design)

- Turning `QUOTE_SELECTION_ENABLED` on without Alex’s attended gate.
- Salvaging or quietly rewriting the 793 legacy rows in place as the v1
  quality fix.
- Putting “worth reading” judgments inside `verify_quote_candidate()` (that
  module stays provenance/authenticity only — except boundary hardening
  proven necessary by the known overrun defect).
- Hard-filtering selection solely by topic tag match.
- **V1 soft-boost from tags** (deferred; see Selection).
- Quote extraction from flat book chunks without trustworthy boundaries
  (standing exclusion).
- Expanding curated teachers beyond the existing confirmed set without a
  separate decision.
- Changing Settled decision #18’s deterministic authenticity auto-approve
  policy, or #28’s open teacher-scope product rule.
- Grok implementing code on this path.

## Blockers before implementation

These are deliberate gates, not plan footnotes:

1. **Settled decision (Alex, record in `CLAUDE.md`)** — authorize or refuse
   a **model-involved quality / serveability gate** on the quote path.
   Standing posture (Settled #4 / Open Decision #20) rejects model-based
   judges on the answer path; that shape failed five times. Settled #16
   already allows AI to *propose* quote candidates. Using a model (or
   model-shaped fields) as a gate that decides whether a quote may become
   approved/servable is a taste judgment and needs the same explicit
   exception treatment as decision #16’s contradiction filter: on the
   record, wrong in both directions sometimes, logged, measurable.
   **No implementation of propose→quality→approve until this is written.**
2. **Controlled vocabulary (Alex)** — closed topic list is a doctrinal /
   product call. Gates extract tagging. Draft may be proposed in a plan;
   Alex authors/approves the list before any real tagged write.
3. **Boundary defect root-cause + fix** — sample quote 7 (“The New
   Testament Evangelist”) ran past its point and swallowed the next
   section’s opening line. Authenticity’s boundary check did not catch it.
   Investigate and harden **before** any rebuild write so new quotes do not
   inherit the flaw. Proof: that sample (and cousins) fail closed after the
   fix.
4. **Named cost estimate** — before any corpus-scale LLM propose run,
   surface attempted document/chunk counts, expected $/run, and stay under
   the **$50 ceiling** unless Alex explicitly approves more. No mid-run
   discovery.

## Approaches considered

### A — Tags as the primary selection index — rejected

Retrieves by topic-tag match. Recreates the baptism false-positive / exact-tie
failure mode. Worse under open teacher scope (#28).

### B — Embedding-only selection + accurate display tags — selected for v1

Keep question ↔ `quote_text` as the only selection signal for v1; fix extract
quality; make tags truthful for display/browse. Soft tag boost deferred until
real traffic or a labeled dry harness can evaluate it. (Long-term hybrid
target retained below as a later enhancement, not a v1 deliverable.)

### C — Hybrid text + soft tag boost — deferred (not v1)

Same as B, plus a soft boost when tags overlap question topics, never lifting
sub-floor text matches. Correct long-term shape if boost is measurable; with
no traffic, it is a dial that cannot be evaluated and is cut from v1.

## Approved product decisions (design review + revision)

1. **Beta ships with quoting ON** — this work is launch-critical (Alex,
   2026-08-19).
2. Extraction path: LLM propose + quality gate + authenticity verify —
   **subject to blocker #1** (settled decision on model-involved quality).
3. Controlled topic vocabulary (closed list); Alex authors; free-text
   rejected.
4. **V1 selection:** question ↔ `quote_text` only; tags for display/browse.
   Soft boost deferred.
5. Legacy 793: **live-but-unserved** while the rail is off during the build
   (explicit, not ambiguous). Selection-ineligible before re-enable; not the
   v1 serving set.
6. Presentation for open teacher scope required before re-enable (#28).
7. Quality lives outside `verify_quote_candidate`, except boundary hardening
   that belongs in authenticity once root-caused.
8. Rail remains default-off until Alex’s explicit attended gate after gold
   set + presentation + regressions.
9. Implementation outside Grok’s lane.

## Architecture

```text
Source passage (chunk + bounded neighbors)
        │
        ▼
LLM propose (structured)     [requires settled quality-gate decision]
  quote_text, restated_point, topic_ids[], why_quotable, …
        │
        ▼
Quality gate (per settled decision)  ──fail──► discard / log
        │ pass
        ▼
verify_quote_candidate()     [boundary hardened before rebuild]
        │ pass
        ▼
Persist new-pipeline rows (gold set first)
  passage-level topic_ids + primary_topic
  legacy 793 remain in DB, live-but-unserved (rail off)
        │
        ▼
select_quotes_for_answer (flag still default off)
  score = sim(question, quote_text) only in v1
  new-pipeline / gold eligible only before re-enable
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
| `topic_ids` | 1–3 IDs from Alex’s controlled vocabulary |
| `why_quotable` | Short rationale against the quality rubric |
| `standalone_ok` | Boolean: readable without the surrounding argument |

Constraints:

- May only quote text present in the supplied window.
- Prefer 1–3 sentence complete thoughts; refuse deictic-only openers unless
  the quote itself states the point.
- Cap proposals per document/chunk (implementation plan; start conservative).
- Prompt version + model stamped on every proposal batch.

### Stage 2 — Quality gate

Separate from authenticity. Exact mechanism (deterministic-only vs
model-assisted vs hybrid) is **fixed by the settled decision in blocker #1**,
not by this spec inventing a judge. Whatever is authorized must:

- Keep every accept/refuse explainable and logged.
- Not revive a free-form claim-support judge (Open Decision #20 shape).
- Calibrate against a gold set Alex rates before corpus-scale runs.

Illustrative rubric *dimensions* (not yet an authorized judge):

1. Standalone (no unresolved deixis / mid-connective).
2. Complete thought.
3. Substance (not throat-clearing, bare verse-read, or banter).
4. Boundary hygiene (does not swallow the next section — also enforced in
   authenticity after the root-cause fix).
5. Length band suitable for the rail UI.

Fail → no quote row (or proposal-log only). Pass → authenticity verify.

### Stage 3 — Authenticity (`verify_quote_candidate`)

Contract remains: exact substring, speaker confirmation, commentary /
ineligible exclusions, boundary-proximity/sentence-completeness, document
clearance at approve time, per-work cap. Auto-approve (Settled #18) remains
for authenticity — **quality must already have passed upstream**.

**Change required before rebuild:** root-cause and harden the boundary check
so the known overrun class fails closed. This is not “optional polish”; it is
blocker #3.

### Stage 4 — Persist + tags

- Store passage-level `topic_ids` and `primary_topic` from the controlled
  vocab — never `documents.topic_tags[0]`.
- Schema: implementation plan chooses `topic_ids text[]` + display `topic`,
  or equivalent; plus a `quality_pipeline_version` (or similar) so selection
  can distinguish new-pipeline rows from legacy.
- Label policy: **semantic topic** on the topic chip; **work/source title**
  on the attribution line (closes W7’s label fork).

### Stage 5 — Selection (v1)

Keep:

- `QUOTE_SELECTION_ENABLED` exact `"true"` opt-in.
- `QUOTE_PASSAGE_SIMILARITY_THRESHOLD = 0.35` on
  `sim(question_emb, quote_text_emb)`.
- Deterministic `(−score, id)` ordering and `MAX_QUOTES_PER_ANSWER`.

V1:

- **No tag soft-boost.**
- Eligible rows: new-pipeline / gold only. Legacy ineligible at selection
  time before any re-enable.

Later (Scheduled / triggered after measurement — not launch-blocking once
v1 quoting works):

- Soft boost when tags overlap question topics; never lift sub-floor matches.

Open teacher scope (#28): presentation before re-enable. Selection widening
to match #28 only after that UI exists.

### Stage 6 — Resolve / present

`resolve_quote()` remains the only text resolution point. Before re-enable:

- Quote visually separated from answer prose.
- Teacher name and source/work attribution on the quote component.
- Topic chip shows passage-level `primary_topic`.
- Restated point optional beside the quote; quote typography only for
  verified quote text (Settled #17 spirit).

## Legacy: live-but-unserved during the build

Live audit: 793 approved/pending; **592/793 (74.7%)** fail
passage↔inherited-topic relevance (all Derek Prince). Quality sample: ~20%
judged worth serving.

**Explicit state during build (avoids deadlock and ambiguity):**

| State | Meaning |
|---|---|
| DB rows exist | Yes — 793 remain queryable in admin |
| `QUOTE_SELECTION_ENABLED` | Off — **nothing reaches users** |
| Serving set | Not these rows |
| Ambiguous “quarantine” | **No** — call this **live-but-unserved** |

Ordering that avoids presentation deadlock:

1. Boundary fix + settled quality decision + Alex vocab (blockers).
2. Dry-run propose + calibrate on a small slice (costed).
3. **Gold write** — small attended new-pipeline set (enough real quotes for
   UI and selection proofs).
4. Presentation built/verified against gold (and fixtures as needed).
5. Mark legacy **selection-ineligible** (still in DB; still unserved).
6. Regressions / W8-style proofs with rail still off.
7. Attended re-enable on gold (or gold + later bounded rebuild batches).

Do **not** require “full legacy purge first” before presentation has real
quote shapes to render. Do **not** leave legacy eligible for selection if the
rail is turned on.

## Controlled topic vocabulary

- Closed list in-repo; **Alex authors / approves** (doctrinal/product gate).
- Propose step may only emit IDs from that list.
- Multi-tag 1–3; one primary for display.
- Edits are deliberate docs+code changes.

## Cost

Any LLM propose over more than a tiny calibration slice:

1. Named estimate to Alex before run (docs/chunks in scope, model, $/run).
2. Design to run once, not iterate live against the corpus.
3. **$50 hard ceiling** unless Alex explicitly approves more.

First Prince non-book rebuild batch is costed in the implementation plan
before Phase F-equivalent writes.

## Phased delivery (launch-critical)

| Phase | Work | Stop condition |
|---|---|---|
| **A0** | Alex: settled quality-gate decision in `CLAUDE.md`; author vocab | Decisions recorded |
| **A1** | Implementation plan (Codex/Claude lane) incl. costed first slice | Plan reviewed |
| **B** | Boundary root-cause + verifier harden + tests | Sample overrun fails closed; no quote corpus writes yet |
| **C** | Quality module + LLM propose dry-run; gold calibration | Alex-rated precision; cost within ceiling |
| **D** | Schema: topic_ids + pipeline_version; gold attended write | Hard reconciliation; gold usable |
| **E** | Selection: new-pipeline-only eligibility; text-only rank (rail off) | Mutation-proven tests |
| **F** | Presentation (separation + attribution) against gold | Alex UI sign-off |
| **G** | Mark legacy selection-ineligible; W8-style regressions | Proofs pass; rail still off |
| **H** | Attended `QUOTE_SELECTION_ENABLED=true` | Alex only |

Long-term soft-boost is **out of this launch sequence** (Scheduled after
measurement).

## Risks and constraints

- **Launch load:** quoting-on beta adds rebuild + vocab + presentation +
  boundary fix to the October path — schedule explicitly in `PLAN.md`.
- **Misattribution under open scope:** presentation is load-bearing.
- **LLM span fabrication:** exact-substring verify; non-substrings never
  persist.
- **Unauthorized model judge:** blocked until settled decision exists.
- **Boundary inheritance:** rebuild forbidden until harden lands.
- **Cost overrun:** estimate + $50 ceiling before corpus propose.
- **Settled #18:** authenticity auto-approve unchanged; quality is upstream.

## Files likely touched (planning hint)

- New quality / propose modules and prompt versions
- `quote_verifier.py` — boundary harden
- `quotes.py` — eligibility + selection (no boost in v1)
- Migration: topic_ids / pipeline_version / legacy selection flag
- Frontend quote component — presentation
- Tests for boundary, quality, eligibility, selection
- `CLAUDE.md` / `PLAN.md` — settled decision + launch blocker placement

**Implementer:** Codex/Claude, not Grok.

## Evidence already in hand

- Passage-level selection fix: `82ec0f5`,
  `scripts/test_quote_passage_relevance.py`
- Legacy relevance audit:
  `docs/audits/quote_legacy_relevance_audit_2026-08-18.md`
- Quality sample: `docs/audits/quote_quality_sample_2026-08-19.md`
- Containment: `quote_selection_enabled()`, Landmines
- Settled #16/#17/#18/#19/#24/#28; PLAN.md W7–W8 + Quote quality blocker

## Open items for the implementation plan

1. Wording of the settled quality-gate decision for Alex to confirm into
   `CLAUDE.md`.
2. Vocabulary worksheet for Alex to author.
3. Boundary root-cause procedure and regression fixtures.
4. Exact schema for topic_ids / pipeline_version / legacy ineligibility.
5. Gold-set size and rating worksheet.
6. **Named cost estimate** for first rebuild slice.
7. Whether first persist is `pending` vs auto-`approved` after quality +
   verify.
8. PLAN.md update: promote this sequence as launch-critical given quoting-on
   beta (records session; chat-originated priority).

## Approval trail

**Initial design review (Alex):** hybrid architecture; LLM propose + rubric +
verify; controlled vocab; legacy quarantine; presentation before re-enable.

**Adversarial revision (Claude Code review + Grok response; Alex):**

1. Model-involved quality gate → **settled decision before implementation**.
2. Boundary defect → **root-cause + fix before rebuild**.
3. Cost → **named estimate + $50 ceiling before corpus propose**.
4. Soft tag boost → **deferred from v1** (display/browse tags only).
5. Vocab → **Alex authors** (explicit gate).
6. Legacy during build → **live-but-unserved** (rail off); gold before
   selection-ineligibility / presentation deadlock avoided.
7. Implementation → **outside Grok’s lane**.
8. **Beta ships quoting ON** → launch-critical (Alex, 2026-08-19).

Next step after Alex accepts this revision: record the quality-gate settled
decision + start vocab; then implementation plan in the Codex/Claude lane
(`docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md`).
