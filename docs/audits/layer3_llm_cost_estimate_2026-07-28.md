# Layer 3 LLM cost estimate — 2026-07-28

**Nothing in this report involved a real LLM or network call.** Every token count
below comes from tokenizing real, live-queried text with `tiktoken`'s
`cl100k_base` encoding — a real per-document/per-item measurement, not a
`chars/4` guess. `call_layer3_llm()` (`scripts/citation_verifier_layers.py`)
was never invoked; `verify_reference_grounded()` was run throughout with
`llm_enabled=False`, which never reaches Layer 3. All DB touches are SELECTs.

**Tokenizer caveat, stated once, applies to every number in this report:**
there is no Llama tokenizer readily available in this repo. `cl100k_base` is
used as a proxy for `llama-3.3-70b-versatile`'s real tokenizer. This is an
approximation, not exact — real Llama token counts could differ from these
numbers by some margin in either direction.

**Pricing used (confirmed today from groq.com/pricing):**
`llama-3.3-70b-versatile` — **$0.59 / 1M input tokens, $0.79 / 1M output
tokens**.

**Standing ceiling (CLAUDE.md):** "treat $50 as a hard ceiling unless Alex
explicitly approves exceeding it," for any LLM run with meaningful per-item
cost across the corpus.

---

## Scope A — the 59 "needs fixing" + 5 "needs manual review" statements

Source: `docs/audits/statement_recheck_closeness_citation_2026-07-28.md`,
sections 8 and 10.

### A.1 — Resolution to real rows

All 64 statements were resolved to real `propositions.id` rows by exact
`documents.title` match + `proposition_index` match against the live DB.
**64/64 resolved cleanly — 0 ambiguous, 0 unresolved.** (`documents.title`
matched exactly once per row in every case; no fuzzy matching was needed.)

### A.2 — Re-checking against the CURRENT verifier (Layers 1+2, no LLM)

Each of the 64 statements' own listed reference(s) was tested — one call to
`citation_verifier_layers.verify_reference_grounded(reference, source_text,
llm_enabled=False)` per reference, against that statement's document's real,
freshly reconstructed full text (`chunks.content` ordered by `chunk_index`,
same method as `scripts/eligible_statements.py`). Per-statement reference
counts came directly from each row's own "Failing reference(s)" /
"Reference(s) checked" column in the audit doc (e.g., the Zac Poonen "Ezra
10:1, Nehemiah 13:23" row counts as 2 separate references/potential calls).

| | Count |
|---|---|
| Statements in scope | 64 |
| Total individual references tested | **79** (67 from the 59 needs-fixing rows + 12 from the 5 needs-manual-review rows) |
| Confirmed by Layer 1 (widened regex scan) | 37 |
| Confirmed by Layer 2 (document-wide book scope) | 1 |
| **Confirmed by Layers 1+2 combined — would NOT need Layer 3** | **38** |
| Not confirmed by Layers 1+2 | 41 |

Of the 41 not confirmed, only **38** are genuine Layer-3-reachable candidates
(`reason = "not_confirmed_llm_disabled"` — both Layer 1 and Layer 2 actually
ran against the real document text and failed to confirm). The remaining
**3** (all Derek Prince, "Deliverance And Demonology," prop #4/#6/#7 —
"Prov. 16:32," "Deut. 18:9-14," "Eph. 5:18") return
`reason = "unparseable_reference"`: the reference string itself fails
`_parse_verse_or_range()` before Layer 1, 2, or 3 ever run, because of the
pre-existing, disclosed dotted-abbreviation gap (periods aren't normalized
before parsing — same defect named in `ARCHITECTURE.md` and PLAN.md #45.5,
untouched by this session's Layer 1 fix, which only touched the SOURCE-side
scanner, not the reference-under-test parser). `verify_reference_grounded()`
returns immediately on an unparseable reference and never reaches Layer 3
regardless of `llm_enabled` — so these 3 cost **zero** Layer 3 calls in a
real run, not because they're confirmed, but because the check structurally
never gets that far.

**Real candidate pool for Layer 3 cost = 38 references** — not the stale
64-statement figure, and not the raw 41 "unconfirmed" figure either. The
discrepancy versus 64 is explained by two independent effects: (1) this
session's own Layer 1 chapter-colon-gap fix and the already-shipped BOOK_MAP
fix let Layers 1/2 alone confirm about half (38/79 = 48%) of what the stale
report treated as needing further verification; (2) 3 more are excluded
structurally by a separate, unrelated pre-existing bug, not because they're
confirmed.

### A.3 — Document token-length distribution (the 38 candidates)

Real reconstructed full document text, `cl100k_base` tokens:

| | Tokens |
|---|---|
| Min | 1,556 |
| Max | 37,858 |
| Mean | 8,783.6 |
| Median | 8,096.0 |

(24x spread min-to-max — confirms the task brief's expectation that a single
average would misrepresent this corpus.)

### A.4 — Per-call token/cost components

- **`LAYER3_PROMPT` fixed instruction text** (placeholders stripped, measured
  directly): **160 tokens**.
- **`{reference}`**: measured per item, 5–9 tokens each (e.g., "Acts 20:31" =
  5, "Ezra 10:1" and "Song of Solomon 4:7" toward the top of that range).
- **`{source_text}`**: the real per-document token count from A.3 above — the
  dominant cost by two to three orders of magnitude over the other two
  components.
- **Output tokens**: measured directly, not the `max_tokens=200` ceiling.
  `{"engaged": true}` = 6 tokens; `{"engaged": false}` = 6 tokens. Using
  **6** as the typical/floor output-token estimate.
  **Risk, flagged explicitly:** this is a floor/best-case estimate assuming
  the model returns clean, unembellished JSON on the first try. Nothing in
  this build has ever been run against real Groq output (the module's own
  accuracy disclosure) — a verbose deviation (preamble, reasoning, markdown
  fences beyond what the strip regex handles) would raise real per-call
  output cost above this floor. Not modeled here.

### A.5 — Total cost (sum of real per-item costs, not mean × count)

| | Value |
|---|---|
| Layer 3 calls (real candidate count) | 38 |
| Total input tokens across all 38 calls | 340,104 |
| **Total Scope A cost** | **$0.2008** |

**Scope A: $0.20 — 0.4% of the $50 ceiling.**

---

## Scope B — the full backfill

### B.1 — Live document-count re-derivation (do not trust 781 or 810)

Query run live today, same definition as PLAN.md #17 (`documents` whose
resolved source has `license_status = 'unlicensed'`, excluding Precept Austin
`698e0596-a9c6-4890-958d-9199f1b8f762`, and the document currently has zero
rows in `propositions`):

```sql
SELECT count(*) FROM documents d
JOIN sources s ON s.id = d.source_id
WHERE s.license_status = 'unlicensed'
  AND s.id != '698e0596-a9c6-4890-958d-9199f1b8f762'
  AND NOT EXISTS (SELECT 1 FROM propositions p WHERE p.document_id = d.id)
```

**Live result: 564.**

**Reconciliation against both stale figures:**

- **810** (PLAN.md #17, recorded 2026-07-14) → **781** (rhemata-status.md,
  recorded 2026-07-24, and the figure in Alex's own task prompt): delta -29,
  ordinary corpus drift over that 10-day window, not independently
  re-verified in this task.
- **781 → 564** (today): delta -217. This is almost entirely explained by
  one confirmed, already-logged event: the **220-document John Bevere corpus
  deletion, 2026-07-25** (`rhemata-status.md`, "John Bevere YouTube corpus
  deleted" entry). That same entry set explicitly names 219 of those 220
  documents as part of the 781 backfill-target figure ("the single largest
  block (219 of 781) of what's still awaiting the eventual propositions
  backfill") — and they were deleted, not backfilled, the very next day.
  **781 - 219 = 562**, within 2 of the live 564. The residual +2 is
  plausibly ordinary new-document ingestion in the 07-24→07-28 window
  (PLAN.md's post-2026-07-25 ingestion policy: "ingest continues at full
  pace; corpus keeps growing," even while propositions generation itself
  stays paused) — this was not independently re-verified line-by-line in
  this task, so it's offered as the most coherent explanation given the
  evidence, not a confirmed fact.
- **Conclusion: 564 is the number to use.** Neither 781 nor 810 should be
  cited going forward — both are snapshots from before the Bevere deletion,
  and PLAN.md #17's own entry (last touched 2026-07-14) has not been updated
  to reflect it.

### B.2 — Who's actually in the 564-document population

| Author | Count | % |
|---|---|---|
| Derek Prince | 492 | 87.2% |
| (no author recorded) | 14 | 2.5% |
| Daniel Kolenda | 8 | 1.4% |
| Leonard Ravenhill | 7 | 1.2% |
| Zac Poonen | 6 | 1.1% |
| Bob Mumford | 4 | 0.7% |
| Doug Kreighbaum | 4 | 0.7% |
| Jack Deere | 3 | 0.5% |
| (21 other named teachers) | 26 | 4.6% |

Confirms PLAN.md's own characterization: this backfill is overwhelmingly
Derek Prince (492 raw documents; PLAN.md's 2026-07-25 linking session
separately established his true deduplicated count as ~429 — the linking
mechanism groups duplicates in a separate table rather than deleting/merging
rows, so a raw per-document query correctly still returns 492).

### B.3 — Real sample of 30 backfill-target documents, real token distribution

30 documents sampled (20 Derek Prince + 10 spanning the other 27 teachers,
fixed random seed for reproducibility), real chunk-reconstructed full text,
`cl100k_base` tokens:

| Sample | n | Min | Max | Mean | Median |
|---|---|---|---|---|---|
| All 30 | 30 | 177 | 15,623 | 8,912.2 | 9,643.5 |
| Derek Prince subsample | 20 | 4,429 | 15,623 | 10,288.1 | 10,461.0 |
| Other-teacher subsample | 10 | 177 | 13,774 | 6,160.3 | 6,400.0 |

**Comparison against the already-processed corpus** (same-size random
sample, n=30, of documents that already have ≥1 proposition):

| Sample | n | Min | Max | Mean | Median |
|---|---|---|---|---|---|
| Already-processed (existing corpus) | 30 | 109 | 24,445 | 8,011.6 | 4,451.5 |

The backfill sample runs meaningfully longer on **median** (9,643.5 vs
4,451.5) though the **means** are close (8,912.2 vs 8,011.6) — a real signal
worth naming (consistent with PLAN.md's note that this backfill is the first
time long-form material — Derek Prince's teaching series — hits the
extractor, "extraction unproven on long-form"), but this is two n=30 samples,
not a corpus-wide population claim.

### B.4 — Three empirically-derived rates (full live re-run, not sampled)

All three computed against the full, current, live 2,409-proposition /
293-document already-processed corpus — a full run, not a subsample (2,409
propositions ran in ~72 seconds; runtime allowed the whole corpus).

**(a) Propositions per source document:**
2,409 live propositions ÷ 293 distinct documents with ≥1 proposition
= **8.222** propositions/document.

**(b) Reference-bearing rate:** re-derived live via
`reference_grounding.find_reference_spans()` (unmodified this session;
already includes the previously-shipped BOOK_MAP ordinal/spelled/Roman-numeral
fix, commit `ee267d4`) against every live proposition's own `content`:
**644 / 2,409 = 26.73%** carry ≥1 parseable reference.
(Previously documented figure: 642/2,409 = 26.65%. Delta +2 — consistent
with, though not independently re-attributed line-by-line to, the already-
shipped BOOK_MAP fix reflected in this live figure. `find_reference_spans`
itself was not modified by this session.)

**(c) Layer 1+2 fail rate**, current code, real full-corpus run: of the 644
reference-bearing propositions, **178** carry at least one reference that
`citation_verifier_layers.verify_reference_grounded(..., llm_enabled=False)`
fails to confirm = **178 / 644 = 27.64%**.
At the individual-reference level (789 references tested across those 644
propositions): 600 confirmed / 189 unconfirmed (76.05% per-reference confirm
rate). **Average unconfirmed references per failing proposition: 189 / 178 =
1.062** — a failing proposition carries slightly more than one bad reference
on average, so counting failing PROPOSITIONS alone understates real Layer 3
call volume by about 6%.

### B.5 — Projection (every factor its own line)

```
564   live backfill-target documents
×  8.222   propositions per document (a)
×  0.2673  reference-bearing rate (b)
×  0.2764  Layer 1+2 fail rate, per reference-bearing proposition (c)
= 342.6   projected FAILING-PROPOSITION count (task's literal formula)

× 1.062   observed refs-per-failing-proposition ratio (Scope A confirmed
          Layer 3 is called per-REFERENCE, not per-statement)
= 363.8   projected Layer 3 CALL count (refined estimate)
```

### B.6 — Per-call cost, using the BACKFILL sample's own token distribution

(Not Scope A's already-processed-corpus distribution — the backfill
population is a different, longer-median population per B.3.)

Fixed prompt: 160 tokens. Reference: ~8 tokens (measured average of a small
set of representative reference strings). Output: 6 tokens (same floor
caveat as Scope A.4).

| Scenario | Doc tokens used | Per-call cost | **Total (363.8 calls)** |
|---|---|---|---|
| Mean (central estimate) | 8,912.2 | $0.005362 | **$1.9508** |
| Median | 9,643.5 | $0.005794 | $2.1077 |
| Best case (min doc) | 177 | $0.000208 | $0.0758 |
| Worst case (max doc) | 15,623 | $0.009321 | $3.3912 |

**Central Scope B estimate: ≈$1.95.**

### B.7 — Sensitivity check (this is a projection, not a measurement)

**Stated explicitly, per the task brief:** this is a projection built from
TODAY's already-processed-corpus rates (a) / (b) / (c) applied forward onto
documents that have never been through extraction — it is NOT a measurement
of the backfill documents' own actual reference-check outcomes, which cannot
exist until those documents are processed. **The single biggest source of
estimate error**: nothing here confirms Derek Prince's ~429 (492 raw)
long-form sermon/teaching-series documents will produce propositions,
reference density, or Layer 1/2 confirmability at the same rates as the
already-processed corpus's actual population (predominantly Vlad Savchuk
short-form YouTube content, Zac Poonen sermon transcripts, Leonard Ravenhill
— see the per-teacher tables in the 2026-07-28 recheck report). PLAN.md #17
itself flags this: "First time long-form books hit the extractor... spot-check
book output quality before trusting the batch (extraction unproven on
long-form)." If long-form material produces a different reference-bearing
rate or fail rate than short-form YouTube content has (and CLAUDE.md
Invariant 11's own correction already shows verse-by-verse expository style
— exactly Derek Prince's register — drives materially different citation
behavior than the corpus norm), every multiplier in B.5 could shift in
either direction.

**Rough sensitivity, both rates ±25% (compounding), central token estimate:**

| Scenario | Rate combination | Projected calls | Cost (mean tokens) | Cost (worst-case tokens) |
|---|---|---|---|---|
| Low | (b) and (c) both -25% | 204.6 | $1.10 | $1.91 |
| **Measured (central)** | as measured | 363.8 | **$1.95** | $3.39 |
| High (stress test) | (b) and (c) both +25% | 568.5 | $3.05 | **$5.30** |

**For comparison only (not recommended — see B.1):** using the stale document
counts instead of live 564, holding all rates at measured value: 810 docs →
522.5 calls → $2.80; 781 docs → 503.8 calls → $2.70.

Every scenario computed, including the compounded worst-case stress test,
stays under $6 — nowhere close to the $50 ceiling.

---

## Summary

| Scope | Real/projected Layer 3 calls | Central cost estimate | Worst-case shown | % of $50 ceiling (central) |
|---|---|---|---|---|
| **A** — 64 flagged/manual-review statements | 38 (real, resolved) | **$0.20** | — (exact, not projected) | 0.4% |
| **B** — full backfill (564 live docs) | 363.8 (projected) | **$1.95** | $5.30 (compounded stress test) | 3.9% |
| **Combined** | ~402 | **~$2.15** | ~$5.50 | ~4.3% |

Both scopes land far under the $50 ceiling, even stacked together and even
under a deliberately pessimistic compounded stress test.

## Recommendation (Alex's call, not resolved here)

Dollar cost is not the binding constraint for either scope — even the
worst-case combined stress test (~$5.50) is an order of magnitude under the
$50 ceiling. The open question is not cost, it's accuracy: Layer 3's prompt
has never been run against real Groq output — the module's own accuracy
disclosure states the entire test suite mocks the LLM call, so nothing has
ever confirmed the prompt reliably distinguishes "the teacher genuinely
engages this passage" from "superficial or false-positive mention" in
practice. Given that, whether to run the full projected ~364-call backfill
scope in one shot once it's live, or start smaller first (Scope A's 38
real, already-resolved candidates is a natural first real batch, small
enough to hand-check every verdict) to observe actual model behavior before
committing to the full projected scope — that's a product/risk judgment
call for Alex to make, not something this dollar-cost estimate should
resolve on its own.
