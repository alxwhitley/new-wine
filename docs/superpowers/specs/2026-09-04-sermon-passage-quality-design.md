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

30 sermon-transcript passages that had reached the **top 8** of a real answer's
evidence set were drawn, stratified across teachers, and graded blind by Alex.

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

**Source predicted the grades better than any measured text feature.** Alex has
since ruled out excluding sources: CLF stays, so any solution must work per
passage.

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
path stores what the recogniser emits, which for these videos has **no sentence
punctuation at all**. 20 of the 79 rebuilt documents are wholly unpunctuated;
391 unpunctuated chunks were added to the 337 already present.

`prose_quotation_guard.normalize_for_match()` folds quote characters, dashes,
ellipsis and whitespace, and casefolds — but **not sentence punctuation**.
Verified live against a rebuilt Kolenda chunk:

| answer form | result |
|---|---|
| quoted verbatim, exactly as stored | passes |
| same words, writer adds a comma and a full stop | **flagged ungrounded** |
| same words, writer adds only a full stop | **flagged ungrounded** |

A writer quoting *accurately* from these documents will punctuate naturally,
fail the substring match, and drive regenerate-once-then-refuse. Quotation
appeared in 4 of 7 answers in an earlier real sample, so this is not a rare
path.

Not fixed unilaterally: it means changing a safety guard's matching rule, and
punctuation can occasionally carry meaning. The narrow option is folding
sentence punctuation on both sides of that comparison.

**Also open:** ~20 Leonard Ravenhill documents were rebuilt from captions that
cannot transcribe 1960s tape ("the lowing of the auction" for "the lowing of
the oxen"). Backups exist. These should probably be reverted.

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

## 6. Proposed plan

**Build no filter yet.** Four failed detectors and a 30-passage stratified
sample are not grounds for changing what reaches the writer.

1. **Fix the punctuation-induced refusals** (section 4). Highest priority: it is
   live, self-inflicted, and causes wrong behaviour on real questions.
2. **Revert the ~20 Ravenhill documents** to their backups. Accident repair, not
   a gate.
3. **Build a labelled set worth calibrating against** before anything else:
   ~150 passages, **drawn retrieval-weighted** (from passages that actually
   reached top-8, which is where exposure lives) and **oversampled on CLF** and
   on every source that had only one passage. A uniform random draw from a
   Prince-dominated corpus yields almost no kills and measures the corpus rather
   than the exposure.
4. **Only then** decide between deterministic rules and a narrow, logged,
   model-scored classification — modelled on the authorised quote taste gate
   (Settled #29) and the authorised pre-generation content filter (Settled #16),
   with its own explicit sign-off and cost estimate. Corpus-scale cost is not
   the obstacle: roughly $2–3 for the sermon corpus.

**Explicitly rejected:** distilling sermons to propositions for the writer. It
would strip exactly what Alex rewarded (the illustrations), risks ranked failure
mode #3, collapses retrieval granularity, and intersects the single-voice /
debate-topic classification work already scoped as its own project.

**Explicitly rejected:** soft down-weighting instead of exclusion. Neighbour
expansion runs *after* rerank and ignores ranking weights, so a clean chunk
drags its neighbours into context regardless (`_NEIGHBOR_SKIP_KINDS` exists
because the codebase already learned this for lexicon). The per-author cap of 3
pulls weaker sources back in. Two independent models killed this idea for these
reasons.

---

## 7. Questions for the reviewer

1. **Is the punctuation fix correct?** Folding sentence punctuation on both
   sides of `normalize_for_match()` widens what the guard accepts. Does that
   open a real misrepresentation path, or only close a false-positive one?
2. **Is the 150-passage retrieval-weighted draw the right gate**, or is there a
   cheaper measurement that would settle whether a filter is needed at all —
   e.g. measuring how often killed-grade chunks actually land in served top-8s,
   which nothing here measures?
3. **Is "no filter yet" the right call**, or does 0/5 on CLF justify acting on
   less evidence than I am asking for?
4. **Was rebuilding 79 documents correct**, given it recovered 139,669 words but
   introduced the refusal risk in section 4 and did not measurably improve
   graded quality (62% keep on rebuilt passages vs 68% untouched)?
5. **Is the Ravenhill revert right**, or should those documents be re-ingested
   some other way, or dropped?
6. Anything in section 5 that looks salvageable rather than abandoned?
