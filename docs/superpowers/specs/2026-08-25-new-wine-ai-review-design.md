# New Wine AI Review Pipeline Design

**Status:** Accepted by Alex on 2026-08-25. Implementation and paid model runs
remain separate attended steps.

## Outcome

Resume the historical New Wine issue backlog with an auditable, issue-level
quality gate that proves the scan was transcribed completely, reconstructs
whole articles, and stores only propositions directly supported by the
reviewed article text.

## Acceptance criteria

- Every page image, including advertisements and pages believed to contain no
  article text, is compared with its OCR output.
- A page judged incomplete receives exactly one targeted re-OCR attempt.
- Any page still incomplete after that attempt quarantines the entire issue.
- Every reconstructed article begins coherently, ends coherently rather than
  mid-thought, preserves page order and transitions, and contains no adjacent
  article bleed, unexplained omission, or duplication.
- Article review compares each article with the complete verified issue
  transcript, not only its claimed page range.
- Every substantive article produces at least one proposition.
- Every proposition has an exact evidence passage whose offsets round-trip
  into the reviewed article text, and an independent verdict that the
  proposition does not overstate, omit a necessary qualification, or
  misattribute that passage.
- A single failed page, article, or proposition quarantines the issue; no
  partial issue is eligible for ingestion.
- Approved proposition text is persisted and later stored byte-for-byte. The
  ingestion step does not regenerate propositions.
- Database ingestion continues through `scripts/shared_ingest.py` and remains
  an attended, explicitly approved operation with hard reconciliation.

## Non-goals

- No production database write, backlog OCR run, or deployment is authorized
  by this design.
- This does not change the modern web-article crawler or its narrow unattended
  write exception.
- This does not make OCR or mixed-author magazine material quote-eligible.
- This does not make doctrinal or licensing judgments.
- This does not resume YouTube ingestion or the retired multi-provider
  coordinator.
- The review pipeline does not automatically move, rename, archive, or delete
  source or issue files.

## Existing pipeline and problem

`scripts/extract_magazine.py` currently combines three passes in one large
module: Gemini 2.5 Flash transcription, Groq Llama 3.3 70B article
segmentation, and Groq Llama 3.3 70B QA. The stored tracker status reflects
pipeline completion but does not prove that every page's visible text reached
the transcript. That gap explains the observed failures: coherent-looking
articles can still be incomplete because OCR silently omitted material.

`scripts/ingest_magazine.py` already routes documents through
`shared_ingest.ingest_document()`, which atomically stores the document,
chunks, embeddings, and propositions. That chokepoint must remain. The needed
interface change is narrow: permit a reviewed, fingerprint-validated
proposition set to enter the existing proposition storage path without a
second generation call.

## Selected approach

Use a layered retrofit rather than expanding the existing monolith or
rewriting the pipeline:

```text
raw PDF
  -> initial page OCR
  -> page-image/OCR completeness review
  -> one targeted repair for a failed page
  -> verified issue transcript
  -> article segmentation
  -> full-issue article completeness review
  -> proposition preview
  -> proposition evidence review
  -> issue decision: approved | quarantined | pipeline_error
  -> attended shared ingestion
  -> database reconciliation
```

Each layer consumes immutable evidence from the preceding layer and writes a
versioned JSON artifact. A stage may resume only when its input hashes, prompt
fingerprints, and model identifiers match. Otherwise that stage and its
dependents must be recomputed.

## Model strategy

The current defaults need replacement because Groq retired
`llama-3.3-70b-versatile`, while OCR quality must be selected from evidence
rather than model reputation.

| Stage | Candidate/default | Reason |
|---|---|---|
| Initial OCR | Blind benchmark winner: current Gemini 2.5 Flash control, Google Enterprise Document OCR, or Gemini 3.6 Flash | A2 requires the candidate to beat known severe failures without degrading good controls. |
| OCR completeness reviewer | Gemini 3.6 Flash | Current multimodal model compares each rendered page directly with OCR text. |
| One targeted re-OCR | Gemini 3.6 Flash | Paid only on pages the reviewer fails. |
| Article segmentation | Groq `openai/gpt-oss-120b`, low reasoning | Supported production replacement with structured output and enough issue context. |
| Article completeness review | Groq `openai/gpt-oss-120b`, medium reasoning | Fresh-context issue-wide boundary and continuity judgment. |
| Proposition extraction | Existing `openai/gpt-oss-120b` v3.1 path | Preserves current grounding and provenance invariants. |
| Proposition support review | Deterministic evidence validation, then fresh-context `openai/gpt-oss-120b` semantic verdict | Cheap structural checks run first; model calls are reserved for meaning, qualification, and attribution. |

The initial OCR model is not locked until a blind benchmark is accepted by
Alex. Quality is the pass condition; cost is only the tie-breaker. The
benchmark includes named severe-failure pages and representative good-control
pages, hides provider identity during scoring, and records source hashes,
outputs, omissions, substitutions, reading-order errors, tables/columns, and
cost.

Current official pricing supports a low-cost architecture: Document AI OCR is
priced per page, and Gemini Batch/Flex pricing is discounted for asynchronous
work. Provider pricing and model availability must be rechecked when the
benchmark is actually run, because neither is a durable repository invariant.

Official references:

- [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini document processing](https://ai.google.dev/gemini-api/docs/document-processing)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini Batch API](https://ai.google.dev/gemini-api/docs/batch-api)
- [Google Document AI pricing](https://cloud.google.com/products/document-ai/pricing)
- [Groq deprecations](https://console.groq.com/docs/deprecations)
- [Groq GPT-OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b)
- [Groq structured outputs](https://console.groq.com/docs/structured-outputs)

## Durable artifacts

Every review run is rooted in a stable issue workspace and records four
canonical artifacts.

### `ocr_manifest.json`

Records the PDF SHA-256, page count, renderer settings, and for every page:
page number, image hash, initial OCR text and hash, OCR provider/model,
reviewer verdict and reasons, repair attempt count (zero or one), repaired
text and hash when applicable, final accepted text, prompt fingerprints,
usage, cost, and timestamps.

The manifest is invalid if its ordered page count differs from the PDF or if
any image hash cannot be reproduced. `verified` requires every page to have a
passing final verdict.

### `article_manifest.json`

Records each article's stable ID, title, author, ordered source pages,
character spans in the verified issue transcript, exact article text and hash,
start/end coherence, transition checks, omission/duplication/bleed findings,
attribution verdict, and final verdict. It also records the segmentation model,
prompt fingerprint, usage, and cost.

Deterministic validation proves that page numbers exist, spans are ordered and
in bounds, the article text round-trips from those spans, and article IDs and
filenames are unique. The semantic reviewer receives the complete verified
issue transcript plus the complete proposed article set.

### `proposition_review.json`

Records the exact extraction output and provenance for every article. Each
proposition has `proposition_index`, exact `content`, `evidence_text`,
`evidence_start`, `evidence_end`, `supported`, `missing_qualification`,
`overstatement`, `attribution_ok`, and reviewer reasons.

Deterministic validation requires:

```python
article_text[evidence_start:evidence_end] == evidence_text
```

Indices must be unique and contiguous. Empty evidence, invalid offsets,
unsupported propositions, overstatement, lost qualifications, and attribution
failure all fail the article. A substantive article with zero propositions
also fails.

### `issue_decision.json`

Aggregates all input hashes, artifact hashes, model and prompt fingerprints,
page/article/proposition totals, usage and cost, gate results, and quarantine
reasons. Its state is exactly one of:

- `approved`: every quality gate passed; eligible for attended ingestion.
- `quarantined`: content quality failed; no part of the issue is eligible.
- `pipeline_error`: a technical failure prevented a quality decision; safe to
  resume from the last matching artifact.

Approval is fail-closed. Missing, malformed, stale, or unreconciled evidence
cannot be interpreted as approval.

## State and resume contract

The normal state sequence is:

```text
pending -> ocr_reviewed -> segmented -> article_reviewed
        -> proposition_reviewed -> approved -> ingested -> reconciled
```

`quarantined` and `pipeline_error` are terminal for that run, but a subsequent
run may start from the newest valid predecessor artifact. Cache identity is the
hash of the complete stage input plus model ID, prompt fingerprint, renderer
settings, and schema version. Changing any component invalidates that stage and
all downstream stages.

Artifact writes never trigger file promotion. Review approval is represented
only by `issue_decision.json`; ingestion consumes that evidence explicitly.

## Proposition ingestion bridge

The reviewed proposition set must traverse existing gates rather than use a
new SQL path. `propositions.process_document()` will gain an optional
`approved_propositions` input. When present, it still runs source-license,
Precept Austin, substantive-length, prompt-version, fingerprint, model, and
chunk-linkage checks, but skips the generation call and sends the exact
approved list to `store_propositions()`.

`shared_ingest.ingest_document()` will accept and pass that optional input
inside its existing atomic transaction. All existing callers that omit it keep
their current behavior. Magazine ingestion validates the manifest hashes and
provenance before passing it. Stored proposition text must equal the approved
artifact byte-for-byte.

## Cost controls without quality loss

- Use the expensive multimodal reviewer on every page because silent omission
  is the known failure; save cost elsewhere.
- Permit only one re-OCR and only on failed pages.
- Use compact structured JSON and omit repeated source text from outputs.
- Use low reasoning for segmentation and medium reasoning only for coherence
  judgments.
- Run deterministic schema, hash, offset, count, and substring checks before
  semantic review calls.
- Resume from fingerprint-matching artifacts rather than repeat successful
  calls.
- Use eligible asynchronous batch pricing when turnaround time permits.
- Persist approved propositions so ingestion cannot pay for or introduce a
  nondeterministic second generation.

## Operational rollout

1. Build the no-write benchmark harness and blind fixtures.
2. Run the paid benchmark only after Alex explicitly approves its named cost.
3. Alex accepts a winner; record the decision without activating ingestion.
4. Build and test the review pipeline with provider fakes and fixed fixtures.
5. Dry-run one complete real issue with no database writes or file moves.
6. Review its artifacts, quality, and actual cost.
7. After separate approval, perform one attended isolated database write and
   reconcile attempted, stored, skipped, and errored counts plus document,
   chunk, and proposition totals.
8. Run a small bounded batch, reconcile it independently, and only then resume
   the remaining backlog.

At every paid or write-bearing gate, the command, target issue(s), expected
cost/counts, and stop condition are named before execution.

