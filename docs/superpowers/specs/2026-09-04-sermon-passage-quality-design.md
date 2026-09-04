# Sermon passage quality — findings, production changes, and proposed plan

**Date:** 2026-09-04
**Status:** for review. No filter has been built. Three production changes were
made today and are live; they are listed in full below.
**Reviewer:** please read "Questions for the reviewer" at the end — that is what
this document is for.

---

## 1. What prompted this

A read-only diagnostic asked one question: are low-quality sermon-transcript
passages actually reaching the evidence pool that feeds live answers, or are the
strong passages already winning?

The answer path stores what it used. `answer_jobs.retrieved_chunk_ids` holds the
exact post-rerank, post-neighbour-expansion chunk set for every completed answer
— 74 completed answers between 2026-08-06 and 2026-09-04, 623 distinct chunks,
270 of them sermon transcripts. No retrieval had to be re-run and no money was
spent on the diagnostic.

30 sermon-transcript passages associated with chunks that had reached the
**top 8** of a real answer's evidence set were drawn and stratified across
teachers. Alex graded them without seeing the retrieval questions or any prior
labels, but the teacher and title were visible; this was **not source-blind**.

Eight of the 30 source chunks had been deleted by the same-day re-ingest before
grading. For those eight, the displayed passage was the current chunk selected
by word overlap with the deleted historical chunk, not the exact historical
top-8 text. The baseline is therefore useful for qualitative discovery, but it
is not an exact historical-exposure sample and cannot support a base-rate or
before/after estimate.

---

## 2. The grades

**20 keep, 2 borderline, 8 kill.** 13 teachers, 28 sermons, 20 distinct real
questions. Full passages: `docs/audits/2026-09/sermon_passage_sample_2026-09-04.md`.

| Source | Result |
|---|---|
| Derek Prince (edited, published) | 9 / 9 keep |
| Vlad Savchuk | 4 / 4 keep |
| Michael Brown | 2 / 2 keep |
| Doug Kreighbaum | 1 / 1 keep |
| Daniel Kolenda | 2 keep, 1 borderline |
| Zac Poonen | 2 keep, 1 kill |
| **CLF Church** (live service recordings) | **0 / 5** |
| Jack Deere / Leonard Ravenhill | 0 / 2 |
| Robert Trail | borderline |


<details>
<summary>Per-passage grades (all 30)</summary>

| # | Teacher | Source | Grade | Rebuilt today |
|---|---|---|---|---|
| 1 | Derek Prince | Derek Prince | keep |  |
| 2 | Vlad Savchuk | Vlad Savchuk | keep |  |
| 3 | Derek Prince | Derek Prince | keep |  |
| 4 | Daniel Kolenda | Daniel Kolenda | borderline | yes |
| 5 | Zac Poonen | Zac Poonen | keep |  |
| 6 | Josh Fisher | CLF Church | kill |  |
| 7 | Michael Brown | Michael Brown | keep | yes |
| 8 | Derek Prince | Derek Prince | keep |  |
| 9 | Vlad Savchuk | Vlad Savchuk | keep | yes |
| 10 | Derek Prince | Derek Prince | keep |  |
| 11 | Derek Prince | Derek Prince | keep |  |
| 12 | Daniel Kolenda | Daniel Kolenda | keep |  |
| 13 | Zac Poonen | Zac Poonen | kill |  |
| 14 | Doug Kreighbaum | Doug Kreighbaum | keep |  |
| 15 | Jack Deere | Jack Deere | kill | yes |
| 16 | Shabaka Williams | CLF Church | kill |  |
| 17 | Scott Woodard | CLF Church | kill |  |
| 18 | Leonard Ravenhill | Leonard Ravenhill | kill | yes |
| 19 | Robert Trail | Robert Trail | borderline |  |
| 20 | Paul Kidd, Shabaka Williams | CLF Church | kill |  |
| 21 | Derek Prince | Derek Prince | keep |  |
| 22 | Vlad Savchuk | Vlad Savchuk | keep |  |
| 23 | Derek Prince | Derek Prince | keep |  |
| 24 | Josh Fisher | CLF Church | kill |  |
| 25 | Michael Brown | Michael Brown | keep | yes |
| 26 | Derek Prince | Derek Prince | keep |  |
| 27 | Daniel Kolenda | Daniel Kolenda | keep | yes |
| 28 | Zac Poonen | Zac Poonen | keep |  |
| 29 | Vlad Savchuk | Vlad Savchuk | keep | yes |
| 30 | Derek Prince | Derek Prince | keep |  |

</details>

**Grades clustered by source in this source-visible, stratified sample.** That
is a diagnostic signal, not a source-effect estimate: source identity was
visible, selection was not prevalence-weighted, and eight passages were
post-rebuild replacements. Alex has ruled out excluding sources: CLF stays, so
any solution must work per passage and must prove that it is not merely a
source proxy.

Ruled out by measurement, not assumption:

- passage length (median 2,330 chars kept vs 2,261 killed)
- sentence punctuation — four **kept** passages are equally unpunctuated
- scripture-reference density (weak)
- **narrative vs teaching** — the strongest negative result. The two most
  narrative passages in the sample are Derek Prince's and both were kept
  (a "Niagara Falls baptism"; a man waiting at a bus stop). They score *higher*
  on every first-person storytelling measure than the killed testimonies. The
  distinction is good storytelling vs weak storytelling, which is taste.

---

## 3. Production changes made today (all live — corpus data has no deploy step)

### 3a. 79 sermon documents rebuilt (`b641898`)

Re-fetching every pre-fix video's real json3 captions and comparing word counts
against stored text showed that of 303 verifiable pre-fix documents, **14 stored
under 55% of what was said** (worst 37%) and 65 stored 55–80%. 79 documents were
deleted and rebuilt: **+139,669 words, 1.48x**, 79/79 present, zero duplicates.

Two defects surfaced and were repaired: the re-ingest nulls `documents.author`
when a video title yields no speaker (would have silently disabled the
single-author naming contract on 38 documents), and on four documents it wrote a
*wrong* name — `Joshua Lewis` on Jack Deere's material, `Daniel Kenda` (the
captions misspell Kolenda), and `Dr. Brown` / `Dr. Michael Brown` duplicates.

### 3b. Four stored positions rebuilt (`b641898`)

Deleting propositions extracted from truncated text removed 18
`position_evidence` rows. All four affected positions were rebuilt through
`serve_position.rebuild_position()` and went from 10–12 evidence rows to 15,
with **no scope change**. Prior versions retained.

### 3c. One guest interview silenced (this commit)

"The Truth About Nephilim, Watchers, and Demons" — a Savchuk-hosted interview,
`citable`, empty author, whose substantive doctrinal claims are the **guest's**.
Set to `citation_mode='silent_context'`, the standing rule for multi-speaker
documents. Found by reading, not by a detector.

---

## 4. Open risk introduced today — the most concrete item here

**The rebuild traded punctuation for completeness, and that causes real answer
refusals.**

The old destructive cleaning pass produced punctuated prose. The correct json3
path stores what the recogniser emits. 20 of the 79 rebuilt documents contain
no sentence terminator; 391 chunks without sentence-ending punctuation were
added to the 337 already present. Three of those documents contain none of
`. , ; : ! ?` at all.

`prose_quotation_guard.normalize_for_match()` folds quote characters, dashes,
ellipsis and whitespace, and casefolds — but **not sentence punctuation**.
Verified live against a rebuilt Kolenda chunk:

| answer form | result |
|---|---|
| quoted verbatim, exactly as stored | passes |
| same words, writer adds a comma and a full stop | **flagged ungrounded** |
| same words, writer adds only a full stop | **flagged ungrounded** |

A writer quoting *accurately* from these documents may punctuate naturally,
fail the substring match, and drive regenerate-once-then-refuse. An earlier
audit found four defective quotations across five answers, establishing real
use of the guarded path but not its live refusal frequency.

The first proposed fix -- folding sentence punctuation globally inside
`normalize_for_match()` -- is rejected. Punctuation can carry meaning, and the
global normalizer is also used for attribution keys and windows.

The review also found a more fundamental defect in the existing guard: the
caller passes only a list of evidence strings, and the guard concatenates all
teachers' evidence into one haystack. A quotation attributed to teacher A
therefore passes when its words occur only in teacher B's retrieved chunk. A
minimal offline reproduction attributed Michael Brown's words to Derek Prince
and returned no violation. This is part of B8's closure, not a separate filter
project.

The initially approved author-scoped fallback was implemented in `1f775ac`,
then superseded before deployment after a second review surfaced the governing
policy mismatch. `CLAUDE.md` Settled #17 permits verified-quote treatment only
through the verified-quote component and requires ordinary prose to be
prevented from rendering quotation typography and verbatim attribution.

Alex chose the stricter design:

1. Detect a double-quoted span of at least five words attributed to a permitted
   citable source and report it as prohibited without consulting evidence text.
2. Keep the existing exclusions for Scripture, negated hypothetical quotations,
   short terms/scare quotes, and quotations with no permitted attribution.
3. When multiple permitted names occur in the attribution window, bind the
   quotation to the nearest preceding name. A name appearing only inside the
   quotation is not attribution.
4. Preserve the existing regenerate-once-then-refuse remedy. Never rewrite the
   answer surgically.

This removes the punctuation ambiguity, cross-author concatenation, and nested
quotation bypass together. It also removes author-tagged evidence from the
guard boundary because evidence cannot authorize prose quotation typography.

**Also open:** 20 Leonard Ravenhill documents were rebuilt from captions that
cannot transcribe 1960s tape ("the lowing of the auction" for "the lowing of
the oxen"). Backups exist, but a three-way transcription pilot must precede a
restore, retranscribe, or removal decision.

---

## 5. Four detectors tried, four failed — do not rebuild these

Recorded so the next session does not repeat them. Each produced
confident-looking numbers that dissolved on inspection.

| Detector | Why it failed |
|---|---|
| `>>` markers = multi-speaker | Perfect in-sample separation (3 of 8 kills, 0 of 20 keeps). On reading, the markers sit **mid-sentence inside one person's thought** ("...the really big decisions, `>>` right? When the big decisions..."). They are caption cue artifacts. Of 817 marker-bearing chunks, 638 are CLF and 174 Savchuk. |
| Outline/handout signature | Real, but calibrated on **n=1** (one kill at 5.12, all else ≤0.25). A description of a document, not a rule. |
| Short-turn ratio + assent tokens | Finds preaching repetition and congregational prayer — "leave, / leave, / leave, / LEAVE.", "Lord Jesus, / I believe. / I believe". **6 of 8 hits false.** |
| Question-terminated turn pairs | Finds rhetorical questions. Two documents confirmed by reading *not* to be interviews outrank the one that is. Density does not separate them either. |

**Every real finding today came from reading the material.** Every mechanical
signal failed. That is the central evidence bearing on whether to build a
filter at all.

---

## 6. Approved implementation plan

**Build no filter yet.** Four failed detectors and a 30-passage stratified
sample are not grounds for changing what reaches the writer.

### Stage 1 — close B8 in the repository

Implement the no-attributed-prose-quotation design in section 4.
Acceptance requires credential-free regressions proving all of the following:

- an exact quotation present in retrieved evidence is rejected;
- punctuation-altered, fabricated, and nested quotations are rejected;
- the nearest preceding teacher controls attribution when two names are near;
- Scripture, negated hypotheticals, short terms/scare quotes, and unattributed
  prose remain excluded;
- every pre-existing quotation-guard regression remains green.

A production smoke is a separate attended operation after repository
verification. No deployment or database write is authorized by this plan.

Repository implementation completed in `d1ac57a`: 25 quotation-guard checks,
17 generation-contract tests, 21 routing tests, and Python 3.12 syntax
compilation passed. Alex then approved an isolated backend-only Railway
deployment because local `main` contained unrelated unpublished work. The API
and answer worker reached `SUCCESS`, and guest job
`e8d29d61-ec7d-4b28-a2e9-ab2513749579` completed with a 3,326-character,
seven-citation answer whose independent guard refetch found zero prohibited
quotations. Stage 1 is complete and live as of 2026-09-04; no Git push, Vercel
deploy, migration, or corpus write was part of the release.

### Stage 2 — resolve the Ravenhill source-quality accident

Do not blindly restore the old backups: they contain the earlier
model-cleaned, truncated text. Select three representative Ravenhill documents
and compare (a) backup text, (b) current json3 captions, and (c) a forced
Whisper transcription against short, human-checked audio spans. Choose one
document policy from that evidence: restore, retranscribe, or remove from answer
retrieval. Any production action requires Alex's attended approval and must use
dry run -> one-document proof -> reconciliation -> bounded batch, including
documents, chunks, propositions, position evidence, and rebuilt positions.
Remeasure the punctuation exposure after the chosen repair.

### Stage 3 — measure whether passage quality harms served answers

Before building a classifier, audit the existing 20 distinct question groups,
not all 74 repeated jobs as though they were independent exposure. For each
question group, record whether a kill-grade sermon passage reached top 8 and
whether it materially degraded the served answer. Report both numerators and
denominators. Any theological error or teacher misrepresentation follows the
Blocker promotion rule; ordinary weak-passage quality remains Scheduled. Stop
after the answer-level exposure and harm rates are known and Alex has made the
filter/no-filter decision.

### Stage 4 — build calibration data only if Stage 3 authorizes it

Do not precommit to 150 items. Choose the size from the measured kill base rate
and the error bound needed for the decision. Keep prevalence estimation and
classifier development distinct even if they share passages. The durable,
redacted manifest must include chunk/document/source IDs, an immutable content
hash or snapshot, corpus/policy version, top-8 position, exposure multiplicity,
selection stratum and inclusion weight, label and rubric reason. Omit private
question text.

Randomize and mask teacher/source/title during grading. Freeze a holdout grouped
by document so overlapping chunks cannot leak across train and validation; also
report per-source results and a source-held-out challenge slice. Before any
implementation, set maximum keep false-exclusion, minimum kill recall,
no-material/coverage, and counterfactual answer-quality thresholds.

### Stage 5 — compare mechanisms, then seek a separate release decision

Compare at least: deterministic rules, hard passage exclusion, quality-aware
neighbor admission or post-expansion selection, and a narrow logged model
classifier modelled on Settled #29/#16. A naive pre-rerank soft weight remains
rejected because unscored neighbor expansion bypasses it; soft selection as a
whole is not rejected. Any model path needs its own sign-off, prompt/model
fingerprint, cost estimate, reconstructable reason codes, shadow evaluation,
and attended activation.

**Explicitly rejected:** distilling sermons to propositions for the writer. It
would strip exactly what Alex rewarded (the illustrations), risks ranked failure
mode #3, collapses retrieval granularity, and intersects the single-voice /
debate-topic classification work already scoped as its own project.

**Explicitly rejected:** naive pre-rerank soft down-weighting with the current
pipeline unchanged. Neighbour expansion runs after rerank and ignores those
weights, so a clean chunk can drag its neighbours into context regardless.
Quality-aware neighbor admission and post-expansion selection remain candidates
for Stage 5 because the existing evidence does not test them.

---

## 7. Review decisions incorporated

1. Global punctuation folding and the later author-scoped fallback are both
   superseded. Stage 1 enforces Settled #17 by prohibiting attributed teacher
   quotations in ordinary prose regardless of evidence wording.
2. The 150-passage draw is not the first gate. Stage 3 measures answer-level
   exposure and harm across distinct question groups first.
3. No passage filter is authorized by 0/5 CLF in a source-visible,
   non-prevalence sample.
4. Recovering complete source text was directionally correct, but the 62% vs
   68% comparison is not paired or causal and does not measure rebuild quality.
   Future ingest verification must include downstream guard compatibility and
   representative source-fidelity checks before a full batch.
5. Ravenhill gets a three-way transcription pilot before restore/retranscribe/
   removal is chosen.
6. The failed detectors may be reused only as challenge-set strata and error-
   analysis labels, never as production exclusion rules without new evidence.

Correction to section 4's earlier wording: the prior audit found **4 of 7
quotations defective across five answers**. It did not find quotations in 4 of
7 answers, and it does not establish the live refusal frequency.
