# Quote-Topic Similarity Threshold Analysis

Generated: 2026-08-08 21:26:09 UTC
Script: `scripts/analyze_quote_threshold.py`

## Scope and method

This report reconstructs the similarity scores the live answer path used
to decide which approved quotes to attach to served answers. It is
**read-only**: no database writes, no change to `QUOTE_TOPIC_SIMILARITY_THRESHOLD`,
and no change to production quote-serving behavior.

How the scores were produced:

1. Pulled every `answer_jobs` row with `status = 'done'` and `outcome = 'answered'`
   that has a non-empty question.
2. Pulled every `quotes` row with `status = 'approved'`.
3. For each answer, determined which teachers' material was actually retrieved
   by resolving `retrieved_chunk_ids` -> `documents.source_id`. Only quotes from
   those teachers were treated as candidates, matching `select_quotes_for_answer()`'s
   `considered_teacher_source_ids` filter.
4. Re-embedded each unique question and each quote topic with the production
   model (`text-embedding-3-small`, 1536 dimensions) using the same
   `app.services.embeddings.embed_text()` / `embed_batch()` functions.
5. Computed cosine similarity with the shared `cosine_similarity()` function.
6. Applied the same top-`MAX_QUOTES_PER_ANSWER` cap the selector uses, per job.

Caveats:

- The production selector logs only the IDs it returns, not every candidate score,
  so this report recomputes rather than queries the raw scores. The embedding model
  and math are identical to production.
- `quote_verification_log` records quote *approval* decisions, not selection scores,
  and is not used here.
- Sample quality judgments at the end are plain-text commentary for a human reviewer;
  they are not a model-based verdict.

## Corpus snapshot

- Completed answered jobs analyzed: **16**
- Distinct questions among those jobs: **6**
- Approved quotes in corpus: **2**
- Candidate (question, quote) pairs evaluated: **28**
- Jobs that actually served at least one quote: **11**

### Approved quotes

| Quote ID | Teacher | Topic | Text |
| --- | --- | --- | --- |
| 9646fce4-304d-4b8a-819c-233b1cc6dcb0 | Andrew Murray | waiting on God | Oh for the eyes of our heart to be opened to see God working in ourselves and in others, and to see how blessed it is... |
| d818478d-a913-4dc8-b5ab-b739ac766cf0 | Derek Prince | fasting | Apparently, fasting, even for Jesus, was necessary for him to get the victory over the devil. |

## Distribution at the current 0.40 threshold

Scores for candidate pairs that were **served** (present in `answer_jobs.quote_ids`)
vs. **rejected** (candidate pairs that scored below 0.40, were pushed out by the
top-3 cap, or were never evaluated because the selector returned no IDs for the job).

- Pairs served in production: **11**
- Pairs the selector algorithm would select at 0.40: **12**
- Jobs with qualifying candidates but `quote_ids` is NULL/empty: **1** (the producer's fail-soft wrapper likely caught an embedding/DB fault for these jobs; they appear as 'rejected' below because no quote was actually served).
  - `7cb9aa37-ef49-4f62-806d-e091679b61a4` | best score 0.5790 | What did Andrew Murray teach about waiting on God?

| Group | Count | Min | Max | Mean | Median |
| --- | --- | --- | --- | --- | --- |
| Served | 11 | 0.4587 | 0.7451 | 0.7190 | 0.7451 |
| Rejected | 17 | 0.0171 | 0.5790 | 0.1955 | 0.1958 |

### Score histogram (all candidate pairs)

| Range | Count | Served | Rejected |
| --- | --- | --- | --- |
| 0.00 - 0.10 | 3 | 0 | 3 |
| 0.10 - 0.20 | 12 | 0 | 12 |
| 0.20 - 0.25 | 0 | 0 | 0 |
| 0.25 - 0.30 | 1 | 0 | 1 |
| 0.30 - 0.35 | 0 | 0 | 0 |
| 0.35 - 0.40 | 0 | 0 | 0 |
| 0.40 - 0.45 | 0 | 0 | 0 |
| 0.45 - 0.50 | 1 | 1 | 0 |
| 0.50 - 0.55 | 0 | 0 | 0 |
| 0.55 - 0.60 | 1 | 0 | 1 |
| 0.60 - 1.00 | 10 | 10 | 0 |

## Threshold comparison

Columns:

- **Selected pairs**: total (question, quote) pairs that would be selected.
- **Jobs with any quote**: distinct answered jobs receiving at least one quote.
- **New pairs vs 0.40**: pairs that qualify at this threshold but not at 0.40.
- **New jobs vs 0.40**: jobs that would receive a quote for the first time
  at this threshold (i.e., they received none at 0.40 but would receive at least one here).

| Threshold | Selected pairs | Jobs with any quote | New pairs vs 0.40 | New jobs vs 0.40 |
| --- | --- | --- | --- | --- |
| 0.40 | 12 | 12 | 0 | 0 |
| 0.35 | 12 | 12 | 0 | 0 |
| 0.30 | 12 | 12 | 0 | 0 |
| 0.25 | 13 | 12 | 1 | 0 |

## Samples of newly qualifying pairs

For each threshold below 0.40, every pair that newly qualifies is shown, because the
corpus is small enough to review exhaustively. The 'Verdict' column is a plain-text
first impression for human review, not a model-based label.

### Threshold 0.35

_No pairs newly qualify at this threshold._

### Threshold 0.30

_No pairs newly qualify at this threshold._

### Threshold 0.25

| Score | Question | Topic | Teacher | Served at 0.40? | Verdict |
| --- | --- | --- | --- | --- | --- |
| 0.2786 | Why did Jesus fast in the wilderness? | waiting on God | Andrew Murray | no | likely false positive |


## Raw candidate pair scores

Complete list of every (question, quote) candidate pair, sorted by score descending.
Job IDs are shown so duplicate questions can be disambiguated.

| Score | Job | Question | Topic | Teacher | Served at 0.40? |
| --- | --- | --- | --- | --- | --- |
| 0.7451 | `746a3740` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `597af600` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `8c72eea2` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `f1dff7e2` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `b3c65cc9` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `8e43c9af` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `c7f84fad` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `578eaefa` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `cd7b6ecf` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.7451 | `faddfdb4` | What does it mean to wait on God? | waiting on God | Andrew Murray | yes |
| 0.5790 | `7cb9aa37` | What did Andrew Murray teach about waiting on God? | waiting on God | Andrew Murray | no |
| 0.4587 | `76c11e83` | Why did Jesus fast in the wilderness? | fasting | Derek Prince | yes |
| 0.2786 | `76c11e83` | Why did Jesus fast in the wilderness? | waiting on God | Andrew Murray | no |
| 0.1958 | `746a3740` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `597af600` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `8c72eea2` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `f1dff7e2` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `b3c65cc9` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `8e43c9af` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `c7f84fad` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `578eaefa` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `cd7b6ecf` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1958 | `faddfdb4` | What does it mean to wait on God? | fasting | Derek Prince | no |
| 0.1920 | `2c6c13c9` | What is the baptism of the Holy Spirit? | fasting | Derek Prince | no |
| 0.1760 | `7cb9aa37` | What did Andrew Murray teach about waiting on God? | fasting | Derek Prince | no |
| 0.0612 | `06cb4c91` | What are the five-fold ministry gifts in Ephesians 4? | fasting | Derek Prince | no |
| 0.0612 | `1abe8b21` | What are the five-fold ministry gifts in Ephesians 4? | fasting | Derek Prince | no |
| 0.0171 | `b4323fe5` | What does the Bible teach about the gifts of the Holy Spirit, and how are bel... | fasting | Derek Prince | no |

## Conclusion

This report presents the evidence; it does **not** recommend a threshold value.
The data above shows how many additional quotes would be served at each lower
threshold and provides concrete question/topic pairs for human sanity-checking.
