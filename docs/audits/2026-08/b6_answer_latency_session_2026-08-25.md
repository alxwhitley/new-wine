# B6 answer-latency session — 2026-08-25

## Outcome

Measure the current answer path with enough stage resolution to identify a
material latency reduction, then admit a candidate only if a representative
blind comparison shows no loss of answer integrity.

## Starting evidence

- Job `8677f62d-7ce9-4c3f-b9a5-dd256566a635` queued for 0.62 seconds and ran
  for 61.47 seconds.
- Job `71ba8da6-0d81-406f-b01f-e9db0caafc2a` queued for 0.94 seconds and ran
  for 64.34 seconds.
- Those run durations cover the whole worker interval from `started_at` to
  `finished_at`; they do not isolate Anthropic generation time.
- The client reveal tail is already capped at six seconds, so this session
  measures the producer path rather than changing reveal behavior.

## Acceptance criteria

A candidate direction may be presented for Alex's implementation approval only
when all of the following are true:

1. On the fixed 12-case benchmark, its median producer latency is at least 20%
   lower than baseline, at least 10 of 12 paired cases are faster, and p90 does
   not regress.
2. The model, prompt version, retrieval policy, position-paper and stored-position
   behavior, attribution checks, reference verification, and quote-off state are
   pinned unless the candidate is the separately reviewed subject of the blind
   comparison.
3. A blind human quality review finds no hard failure in theological accuracy,
   teacher representation, retrieval depth, citation/source faithfulness, or
   durable-job recoverability.
4. Alex approves the implementation direction after seeing latency, quality,
   token, cost, and failure-mode evidence.

No production behavior change is authorized by a faster benchmark result alone.

## Non-goals

- No model swap.
- No shorter evidence context, shallower retrieval, weaker prompt instruction,
  disabled verifier, relaxed attribution rule, or reduced citation requirement.
- No production database write, backfill, deploy, or answer-job mutation.
- No change to the client reveal tail.
- No quote delivery; quote selection remains disabled.
- No reuse of the retired coordinator or overnight harness.

## Measurement surfaces

The read-only trace uses a monotonic clock and records durations without answer
or source text. Its surfaces are:

- routing and stored-position selection;
- background position context;
- retrieval query expansion, search, rerank, neighbors, position exclusion, and
  lexicon work;
- context construction and grounding;
- primary generation, time to first provider event, time to first text, tokens,
  stop reason, and any attribution retry;
- attribution validation, reference verification, and disabled quote-selection
  boundary;
- total producer time, outcome, retrieval counts, citations, verified-reference
  count, model, tokens, and cost.

Queue delay and full durable worker time remain separate production-row
observations. This read-only harness deliberately calls `producer.produce()`
directly and therefore does not claim to measure database persistence or create
an end-to-end job row.

## Bounded benchmark plan

- Fixture: 12 fixed cases spanning stored-position, conversation-history,
  position-paper, debate, named-teacher, Scripture, word-study, and web-article
  paths.
- Baseline: two repetitions per case, 24 paid generations total.
- Estimated baseline cost: $1.80; run stop ceiling: $2.50.
- Safe default: fixture validation only. A paid run requires the explicit
  `--run-paid-readonly` flag and an output path under ignored `local/`.
- Execution order: offline validation, then one paid case, inspect its trace and
  answer, then—and only with separate approval—run the full baseline.
- Baseline output must reconcile attempted, completed, errored, and skipped
  generations and must retain answer/citation identity for later blind review
  while excluding source-passage text from citation records.
- Candidate comparison: at most one bounded direction at a time; use paired
  cases and blind labels. Stop at the first hard quality failure or if the
  latency acceptance threshold cannot be reached without crossing a non-goal.

## Audit budget and exit condition

The initial read-only audit is limited to the two supplied production jobs,
targeted repository inspection, the 12-case fixture, and one coherent offline
verification cycle. It exits when the harness is safe and verified and awaits
Alex's approval for the paid single-case gate. Adjacent findings are classified
and parked rather than pursued.

## Read-only candidate classification

The earlier 2026-08-03 measurement found approximately 2.6 seconds of retrieval
beside a 35-second median generation call. Hidden research output accounted for
a median 59% of generation wall time. Retrieval-only work therefore cannot
plausibly meet this session's 20% producer-latency threshold by itself.

Current Anthropic documentation narrows the safe candidate space:

- **Benchmark candidate — `effort="medium"`:** Sonnet 5 defaults to high effort,
  and Anthropic documents medium effort as the same model with moderate token,
  speed, and cost savings. It works when thinking is disabled. This is still an
  answer-generation behavior change and is not authorized for implementation;
  it requires the fixed paired benchmark and blind quality review first.
- **Rejected — Fast mode:** currently supports Opus 5 and Opus 4.8, not Sonnet
  5, and would therefore require a forbidden model swap.
- **Rejected — Priority Tier:** Anthropic currently excludes Sonnet 5 from
  Priority Tier support.
- **Rejected without separate evidence — shorter prompt/context/output:** these
  directly cross the recorded evidence and prompt safeguards or risk truncated
  answers. They are not first-line B6 candidates.
- **Rejected as an integrity shortcut — early client streaming:** the producer
  buffers the answer so attribution and reference checks can fail closed before
  delivery. Revealing unverified text would weaken the existing safeguards.

Official references: [Anthropic effort](https://platform.claude.com/docs/en/build-with-claude/effort),
[Fast mode](https://platform.claude.com/docs/en/build-with-claude/fast-mode),
[service tiers](https://platform.claude.com/docs/en/api/service-tiers), and
[latency guidance](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-latency).

## Paid single-case gate

Alex explicitly authorized one paid, read-only run with existing-provider
transmission and a $0.15 ceiling. The `named_teacher_deliverance` case completed
with attempted/completed/errored/skipped = **1/1/0/0**, cost **$0.052959**, and
no production database writes. Its ignored local record is
`local/2026-08/b6-single-named-teacher-2026-08-25.jsonl`.

Measured non-overlapping critical-path durations:

- routing: 71 ms;
- stored-evidence retrieval: 586 ms;
- background context: 55 ms;
- grounding: 71 ms;
- primary generation: 17.78 s (first text 2.38 s);
- attribution validation including retry: 19.86 s;
- total producer: **38.54 s**.

The retry itself took 18.40 s (first text 1.63 s). The final result was
`refused_attribution`, with 15 retrieved/citable propositions, zero delivered
citations, zero verified references, and zero quote IDs. The two generations
used 4,873 input tokens, 2,852 output tokens, 5,442 cache-read tokens, and 5,442
cache-write tokens.

### Root cause and classification

The fixture question explicitly asks for Derek Prince but contains both stored
topic anchors, “deliverance” and “spiritual warfare.” The deterministic matcher
therefore selected `deliverance from demons and spiritual warfare` before
normal retrieval. A follow-up read-only identity query confirmed that all 15
servable propositions came from six Vlad Savchuk sermon documents. The primary
answer had no retrieved Derek Prince identity to ground it against; the retry
was constrained to Vlad Savchuk while the user question still asked for Derek
Prince. The attribution guard correctly failed closed after both attempts.

This is **Blocker B6-F1**, not a latency candidate: it is a concrete failure of
the named-teacher core answer journey with a teacher-representation boundary.
The minimum closure is teacher-compatible routing/evidence for explicit
named-teacher questions while preserving the existing attribution and citation
guards. The remaining paid B6 baseline is paused pending Alex's explicit
decision; the finding does not authorize a matcher fix or guard relaxation.

## B6-F1 candidate gate

Alex approved a benchmark-only direction: one shared, fail-closed
teacher-specific intent gate is consulted before both position-paper and
stored-position interception. The candidate leaves generic stored-topic routing
unchanged, prevents named-teacher and teacher-list questions from entering the
topic-only stored-evidence path, and is opt-in from the benchmark harness; the
production/default producer path remains unchanged. Offline regression coverage
checks all six stored topics, generic-topic controls, both interception routes,
and alias-load failure.

Alex then authorized one second paid, read-only run with existing-provider
transmission, no database writes, and a $0.15 ceiling. The same
`named_teacher_deliverance` case under `teacher_specific_v1` reconciled
attempted/completed/errored/skipped = **1/1/0/0**, cost **$0.049321**, and wrote
only its ignored local benchmark record:
`local/2026-08/b6-candidate-named-teacher-2026-08-25.jsonl`.

The candidate result was `answered`, with 12 retrieved chunks, seven retrieved
points, seven delivered citations, one verified reference, and zero quote IDs.
It did not require an attribution retry. The later expansion-fixed gate below
identified that delivered-source identity still required review. Measured stages
were:

- routing: 51 ms;
- background context: 53 ms;
- query expansion: 341 ms;
- retrieval search: 14.49 s;
- total retrieval: 15.08 s;
- primary generation: 24.60 s (first text 1.69 s);
- attribution validation: 463 ms;
- reference verification: 196 ms;
- total producer: **40.57 s**.

This closes the exact-case functional proof but not the Blocker or the B6
latency gate. The candidate restored the requested teacher and avoided the
18.40-second retry, but its total was 2.03 seconds slower than the refusing
baseline because the two runs exercised different retrieval routes and the
candidate's normal search took 14.49 seconds. One non-blind case cannot establish
the required representative latency or quality result.

### Query-expansion prerequisite

The candidate run also confirmed that query expansion currently calls Groq's
hardcoded `llama-3.3-70b-versatile`, which returned 404 for the current key. The
repository had already recorded that model failure on 2026-08-19 while leaving
the answer-toolbox path unverified. The fail-soft fallback retained the original
query and the answer still succeeded, but the run is not a clean comparison of
the intended retrieval pipeline.

Alex approved correcting this separate configuration issue. Query expansion now
uses the already-established Groq `openai/gpt-oss-120b` path. Paid B6 commands
perform a fixed synthetic-query expansion preflight before creating their output
or starting retrieval/generation; fewer than two returned variants aborts the
run, and a successful run records the model, variant count, and whether keyword
routing was present. Offline red/green coverage proves the old unavailable-model
behavior falls back and that the benchmark rejects that fallback. Live provider
availability is not yet claimed: no additional provider call was made without a
new paid ceiling.

## Expansion-fixed live candidate gate

Alex authorized one paid, read-only rerun with no database writes and a $0.15
ceiling. The expansion-fixed `teacher_specific_v1` case reconciled
attempted/completed/errored/skipped = **1/1/0/0** at **$0.049373**. Its ignored
local record is
`local/2026-08/b6-candidate-named-teacher-expansion-fixed-2026-08-25.jsonl`.
The preflight and case both used Groq `openai/gpt-oss-120b`; the preflight
returned three variants with keyword routing, confirming that the silent
fallback was not active.

Measured stages were:

- routing: 161 ms;
- background context: 68 ms;
- query expansion: 473 ms;
- retrieval search: 4.12 s;
- total retrieval: 4.84 s;
- primary generation: 23.54 s (first text 1.88 s);
- attribution validation: 379 ms;
- reference verification: 171 ms;
- total producer: **29.25 s**.

This is 11.32 seconds (27.9%) faster than the fallback candidate and avoids the
original baseline's 18.40-second attribution retry. It remains a one-case
directional result, not the representative B6 latency proof.

### Remaining B6-F1 quality failure

The result answered and included seven delivered citations and one verified
reference with zero quote IDs. Three citations identify Derek Prince, but four
do not establish Derek Prince authorship: two have null authors, and two carry
`This Is How You Should Fight Your Battles` in the author field while their
document title is `Your Battle Ends Here | This Is How You Should Fight Your
Battles`. The answer nevertheless closes by saying all points came from Derek
Prince's own sermons and outlines.

The candidate therefore does **not** pass source-faithfulness or
teacher-representation review. The route veto fixed the first collision but
normal retrieval does not itself enforce the explicitly requested teacher. Its
existing single-teacher lock applies only to a matched settled topic and then
only when one source clears the dominance threshold; named-teacher intent is
not that gate. The attribution validator prevents an ungrounded teacher name in
prose, but it does not require every delivered source for a named-teacher answer
to resolve to that requested teacher.

No full paid benchmark or production activation is justified. The smallest
next candidate must resolve an explicit named-teacher alias to source identity,
restrict citable answer evidence and delivered citations to that identity, fail
closed when identity cannot be established, and preserve generic multi-teacher
retrieval. This requires Alex's approval before implementation.

## Named-teacher source-boundary candidate

Alex approved that bounded candidate. It remains opt-in through
`teacher_specific_v1`; default production behavior is unchanged. The candidate:

- resolves all aliases present in the question through the canonical
  `source_aliases.alias_key -> source_id` mapping;
- applies an exclusive lock only when the aliases resolve to exactly one source;
- filters the pre-rerank pool by `documents.source_id`;
- filters again after neighbor expansion so another source cannot re-enter;
- labels surviving chunks and delivered citations with canonical `sources.name`
  rather than malformed document-level author text;
- returns no answer evidence when alias, document-source, or canonical-name
  resolution fails; and
- leaves generic and explicitly multi-teacher questions unrestricted.

Deterministic red/green coverage reproduces the former mixed-source behavior
and now proves initial filtering, neighbor filtering, canonical author labeling,
multi-teacher/generic preservation, and fail-closed lookup errors. The B6
benchmark suite, shared intent suite, stored-position Tier A suite, compilation,
and diff validation pass. No paid call, database write, deployment, prompt
change, model change, or quote activation was made for this increment. A new
expressly capped single-case run is required before any representative blind
benchmark.

## Source-boundary live gate

Alex authorized one paid, read-only source-boundary candidate run with no
database writes and a $0.15 ceiling. It reconciled
attempted/completed/errored/skipped = **1/1/0/0** at **$0.072789** and wrote the
ignored local record
`local/2026-08/b6-candidate-named-teacher-source-boundary-2026-08-25.jsonl`.
Query expansion again preflighted successfully with three variants and keyword
routing.

The mechanical source-identity gate passed: all 27 delivered citations were
canonically labeled Derek Prince, six references verified, attribution required
no retry, and zero quote IDs were produced. This resolves the prior mixed-source
citation symptom for the exact case. The theological/content judgment remains
for blind human review; this single visible case does not satisfy that gate.

Measured stages were:

- routing: 94 ms;
- query expansion: 624 ms;
- retrieval search: 16.88 s;
- explicit teacher-source lock: 225 ms;
- neighbor expansion and post-filter: 629 ms;
- total retrieval: 18.49 s;
- primary generation: 28.76 s (first text 1.89 s);
- attribution validation: 362 ms;
- reference verification: 551 ms;
- total producer: **48.40 s**.

### Oversized-pool finding and local correction

The candidate admitted 27 Derek Prince chunks and 16,887 input tokens because
the pre-existing “cap 12” loop only stopped adding neighbors; it did not trim an
initial pool already larger than 12 when reranking was unavailable. This is why
the source-faithful run was slower and more expensive than the prior candidate.

A candidate-only red/green correction now hard-caps the ranked initial pool and
neighbor merge to 12 total chunks while preserving rank order. The default
production path is unchanged. The regression proves both a 27-item initial pool
shrinks to the top 12 and an eight-item pool can add only four neighbors. This
correction has not received a paid live run, so no latency or content claim is
made for it and the full blind benchmark remains unauthorized.

## Twelve-chunk live candidate gate

Alex authorized one paid, read-only 12-chunk candidate run with no database
writes and a $0.15 ceiling. The first process attempt stopped before provider
or database access because the isolated worktree had no local environment file;
it created no output and incurred no cost. The retry loaded the existing Rhemata
credentials into that process only and reconciled
attempted/completed/errored/skipped = **1/1/0/0** at **$0.046979**. Its ignored
local record is
`local/2026-08/b6-candidate-named-teacher-12-chunk-2026-08-25.jsonl`.

The hard cap passed live: retrieval and delivered citations were exactly 12
unique chunks, every delivered author was canonically Derek Prince, one
reference verified, attribution required no retry, query expansion produced
three variants with keyword routing, and quote IDs remained empty. The model,
prompt, and policy stayed pinned to `claude-sonnet-5`,
`prompt_6ea8b855b412`, and `policy_v3:quote_selection=false`.

Measured stages were:

- routing: 106 ms;
- query expansion: 625 ms;
- retrieval search: 3.48 s;
- explicit teacher-source lock: 1.16 s;
- neighbor expansion and post-filter: 321 ms;
- total retrieval: 5.68 s;
- primary generation: 21.44 s (first text 1.82 s);
- attribution validation: 583 ms;
- reference verification: 184 ms;
- total producer: **28.28 s**.

Against the preceding 27-chunk source-boundary run, total producer latency fell
20.12 seconds (**41.6%**), retrieval fell 12.81 seconds (**69.3%**), generation
fell 7.32 seconds (**25.5%**), input tokens fell from 16,887 to 7,387
(**56.3%**), and cost fell from $0.072789 to $0.046979 (**35.5%**). This proves
the oversized-pool correction and preserves the exact case's mechanical source
boundary. It does not establish theological/content equivalence or
representative quality: the answer still requires blind human review, and no
production activation or full paid benchmark is authorized by this result.

## Representative paired gate

Alex approved the consolidated boundary-1 queue: two repetitions of all 12
fixed cases for both the pinned baseline and `teacher_specific_v1`, with no
database writes, separate $2.50 ceilings, and a $5.00 combined maximum. Before
spending, the fixture gained a fail-closed comparison contract pinning the
blind fields, five protected quality axes, hard failures, two repetitions,
ceilings, and latency thresholds. Offline tests and the 24-generation-per-
variant dry run passed.

Both paid batches reconciled completely:

- baseline: **24/24/0/0**, $1.395375, 22 answered and two expected
  named-teacher attribution refusals;
- candidate: **24/24/0/0**, $1.348848, all 24 answered;
- combined: **48/48/0/0**, $2.744223, zero quote records and no database
  writes.

The representative latency gate **failed**:

- median producer time: 47.31 s baseline versus 45.98 s candidate, only
  **2.81%** faster against a 20% requirement;
- paired case wins: **8 of 12** against a 10-of-12 requirement;
- p90: 57.98 s baseline versus 56.78 s candidate, so p90 did not regress;
- named-teacher median: 34.38 s baseline refusal versus 41.19 s candidate
  answer. This is not a like-for-like successful-answer latency comparison.

The candidate used 296,284 input tokens versus 335,625 for baseline, but
produced 72,907 output tokens versus 68,331. The first candidate repetition
also logged fail-safe JSON-parse failures for both position-paper exclusion
classifier calls; those records completed, but this is retained as quality
review evidence.

The causal interpretation is now explicit: `teacher_specific_v1` changes the
named-teacher route only. It is an integrity correction, not a representative
latency optimization across the other 11 cases, so it could not reasonably
satisfy a 20% whole-suite median improvement through that mechanism. Timing
movement elsewhere is provider/run variance. The paired run therefore rejects
this candidate as the B6 latency direction. No production implementation or
deployment is authorized.

A 24-pair blinded packet, separate unblinding key, and mechanical report were
generated under ignored `local/2026-08/` paths. Their structure verifies that
variant, model, timing, cost, and token fields are hidden and that every pair
has the five-axis rubric. Human scoring is not required to reject a candidate
that already failed the prerequisite latency gate; the packet remains available
for targeted integrity review of the named-teacher correction.
