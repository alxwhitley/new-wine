# Per-answer cost + latency measurement — 2026-08-03

**Session type:** measurement (read-only diagnostic — retrieval reads + LLM
generation only; **zero DB writes**; plain path). Purpose: give Project 1
(scalable async answer execution, designed against 100 simultaneous
generations) a **measured** per-answer cost, replacing the stale
partial-extraction figure as the sizing basis. Measure, do not estimate.

**What was measured:** a faithful offline reproduction of the live `/chat`
answer path (same helper functions imported from `backend/app/routers/chat.py`,
same system blocks, same model, same author-cap + Cohere rerank + neighbor
expansion + **full** background-paper injection), driven over a 23-question mix
across the real traffic categories, most questions run 2–3× (fabrication and
cost are both intermittent). Exact per-call token usage and per-stage
wall-clock captured from each provider response. The two cheap providers were
instrumented to confirm their magnitude. Only the metering/`_save_conversation`
DB writes of the live endpoint were omitted (they are writes; this is a
read-only session) — retrieval, generation, caching, and the guards are
identical to production.

**Measurement cost:** ≈ $2.03 total (well under the $50 ceiling). 43 normal-path
answers, 6 house-voice answers, 2 teacher cards.

**Verified provider prices (fetched from provider docs 2026-08-03):**
Anthropic `claude-sonnet-4-5` $3.00 in / $15.00 out per MTok, cache read 0.1×
input, 5-min ephemeral cache write 1.25× input; OpenAI `text-embedding-3-small`
$0.02/MTok; Groq `llama-3.3-70b-versatile` $0.59/$0.79 per MTok; Cohere
`rerank-v3.5` $2.00 / 1,000 searches ($0.002/search).

---

## Headline

- **Normal answer cost: median $0.039, mean $0.042, range $0.030–$0.074**
  (n=43). The Phase A order-of-magnitude estimate ($0.07–0.12) was ~2–3× too
  high — it under-credited the warm instruction-block cache and over-estimated
  output size. **This measured median is the sizing basis for Project 1; the
  partial-extraction figure is retired for this purpose.**
- **Cost is comfortable, not the ceiling.** At $0.039/answer, a sustained hour
  of 100-generations-always-in-flight ≈ **$400/hr** (worst-case answers
  ~$758/hr); real peaks are bursty, not sustained. The likely true ceiling at
  100 concurrent is provider rate limits (unmeasured here — see C6), not
  dollars.
- **The single dominant cost is the one Anthropic generation call (>99%).**
  Within it, two levers: the per-question **retrieved context** (input, ~50% of
  cost) and the **output** (~46%, of which roughly half is discarded reasoning).
  Groq expansion + Cohere rerank + embeddings together are **0.3%** — rounding
  error, confirmed.

## Cost decomposition — median normal answer ($0.039)

| Component | $ | Share | Note |
|---|---|---|---|
| Retrieved context (input, uncached) | $0.0196 | **50%** | ~6,526 tokens median; worst 14,844. The biggest single line and inherently un-cacheable (different per question). |
| Output (reasoning + visible answer) | $0.0181 | 46% | of which reasoning ≈ $0.0094 |
| Instruction block (cached) | $0.0011 | 3% | 3,656 tokens, warm cache read |
| Groq + Cohere + embeddings | $0.0001 | 0.3% | negligible, confirmed |

## #1 — Prompt caching (the highest-value finding, and it corrects a Phase A guess)

The repeated instruction block (`system_prompt.txt` + `theological_guardrails.txt`)
is **3,656 tokens, constant on every answer, and it IS already cache-controlled**
(`cache_control: ephemeral` on both blocks). Phase A's provisional "appears not
to cache" was wrong — corrected by reading the code and confirmed by the run.

| State | Cost of the block/answer | vs uncached |
|---|---|---|
| Warm (cache read, 0.1×) | $0.0011 (2.8% of a median answer) | **−$0.0099 saved (~90% of the block removed)** |
| Uncached (hypothetical, 1.0×) | $0.0110 (28% of a median answer) | baseline |
| Cold write (1.25×, zero-traffic) | $0.0137 | **+$0.0027 premium** (write with no read) |

**So the "saving available" from caching the instruction block is already
captured — when traffic is warm.** All 43 sequential answers this run hit the
warm cache (`cache_read=3656`, `cache_creation=0`). The nuance that matters for
Project 1:

- **At the 100-concurrent target, the 5-min ephemeral cache is always warm** →
  the ~25%-of-answer-cost saving is real and automatic. Good news for scale.
- **At current ~zero traffic** (answers >5 min apart), every answer is a **cold
  write** — a small **net loss** of +$0.0027 vs no cache. Harmless at these
  volumes, but it means the instruction-block cache is a scale optimization,
  not a zero-traffic one.
- **There is no further instruction-block saving to capture — it's done.** The
  real un-cached cost is the **per-question retrieved context** ($0.0196, 50% of
  the answer), which is different every question and cannot be cross-cached.
  Reducing that (Project 2's single-teacher, smaller context) is the lever, not
  more caching.

## #2 — The reasoning output (measured as a variable line item, not a constant)

The hidden `<thinking>`/`<research_analysis>` blocks are generated **before**
`<answer>`, billed at **output** rate, then discarded from what the reader sees.
Measured across 43 answers:

| Metric | Min | Median | Worst |
|---|---|---|---|
| Reasoning share of OUTPUT tokens | 30% | **53%** | 71% |
| Reasoning share of generation WALL-CLOCK | 33% | **59%** | 73% |
| Reasoning output tokens | — | 625 | 1,625 |
| Reasoning share of TOTAL answer cost | — | **22%** | 42% |
| Reasoning $ / answer | — | $0.0094 | $0.0244 |

**It is neither fixed nor unavoidable-as-a-constant** — it ranges from a third
to nearly three-quarters of both the output bill and the generation wait,
answer to answer. It is the **single largest latency component** (median 59% of
generation wall-clock) and ~22% of the money. **Not changed and not proposed for
change this session** — it is the self-verification pass; accuracy is not traded
for speed (settled decision #4 / Open Decision #20). Recorded here so it stops
being treated as a fixed line.

## Latency (generation wall-clock, offline)

Median **35s**, p90 45s, worst **64.5s**, min 11s; + ~2.6s retrieval. Consistent
with the live ~54s-to-first-text launch blocker (the live figure adds the
buffer-then-verify hold + playback, which this offline measure doesn't include).
The reasoning (above) is the majority of this wait.

## House-voice path (position-paper interception)

Median **$0.015**, ~12s, **no reasoning blocks**, `max_tokens` 2048. Cheaper and
~3× faster than the normal path. The paper body is cached (cold write once, then
reads). **Incidental (not in scope):** the scripture question "What does Romans
8:28 mean?" routed to the house-voice path — a possible position-paper
over-match on a plain scripture question. Flagged, not investigated.

## #3 — Teacher profile cards

| Teacher | Cost/open | Wall | Caching |
|---|---|---|---|
| Derek Prince | $0.0152 | 12.3s | none |
| Jack Deere | $0.0151 | 10.1s | none |

Each open embeds the question, retrieves excerpts, and runs a fresh generation
with **no cache_control** on its system blocks — so the full ~$0.015 and
~11–13s is paid **every open**. **Precomputing (Project 2 scope) saves the full
per-open cost and time**; at any real profile-view volume this is pure current
waste.

## Concurrency-target economics (C2, C5, C7)

- **Per-answer $0.039 is the durable figure; cost scales linearly with volume.**
- **Full sustained load** (100 generations always in flight, ~35s each ≈ 10,300
  answers/hr): **≈ $400/hr median, ≈ $758/hr worst-case.** That is the ceiling
  of continuous saturation — ≈ $9.6k/day only if held 24/7, which real peaks
  are not.
- **Stated realistic duty cycle** (peak 100, average ≈ 15% of peak — a common
  web ratio, stated as an assumption, not a measurement): **≈ $60/hr average ≈
  $1,440/day**. This depends entirely on volume, which is unknown — do not treat
  it as a forecast.
- **Exact-match answer-reuse sensitivity (C5, sensitivity not prediction):**
  cost scales by (1 − repeat rate). At 30% repeats ≈ $281/hr; 50% ≈ $201/hr;
  70% ≈ $120/hr (against the $400/hr full-saturation baseline). The actual
  repeat rate is unmeasured and must not be guessed.
- **C7 honest read: cost is comfortable, not prohibitive.** $0.039/answer is
  cheap; single-teacher answers (Project 2) will lower it further (below). The
  target does not need revisiting on cost grounds.

## C4 — What single-teacher answers (Project 2) would do

Directional estimate from the decomposition (Project 2 is not built, so this is
an estimate, not a measurement): the retrieved-context input is ~50% of the
cost; a single-teacher answer retrieves fewer points and a shorter context, and
tends to a shorter, single-voice output. If context roughly halves and output
shrinks modestly, per-answer cost drops **~25–40% (to ≈ $0.025–0.030)**, with a
latency reduction too. The reasoning pass (the dominant latency piece) is not
removed by single-voice generation, so latency improves but is not solved.

## C6 — Provider limits (the genuine open ceiling — NOT measurable here)

Whether 100 simultaneous `claude-sonnet-4-5` generations exceed the account's
**rate/concurrency limits** (requests-per-minute, input/output tokens-per-minute)
cannot be read from this environment — those live in the provider console and
are tier-dependent. **This is the real risk at 100 concurrent, and it is a
commercial conversation with Anthropic (a tier/limit increase), not an
engineering task.** Flag for Alex now, before Project 1 is built: confirm the
Sonnet tier's RPM/ITPM/OTPM headroom against 100 concurrent × ~7k input +
~1.3k output tokens each (~700k input + ~130k output tokens per concurrent
wave). Groq (query expansion) and Cohere (rerank) have their own separate
limits at that concurrency, also unchecked here.

## Recommendation (D3)

**Build per-answer cost + token recording into Project 1 as standing
instrumentation** (question, retrieved proposition/chunk IDs, model + prompt
versions, input/cache-read/cache-write/output tokens, per-stage timing, path,
regenerated-flag, outcome). One line of reasoning: both external reviewers
already flagged it as cheap-now / unrecoverable-later, this session had to
reconstruct every figure offline because nothing is recorded, and Project 1's
job queue is the natural place to persist it per job.

## Caveats / not covered

- **Regeneration** (the conditional regenerate-once when a guard flags an
  ungrounded credit) was **not** included in these per-answer numbers — it adds
  roughly one more generation (~$0.03–0.04) when it fires, at the intermittent
  Phase-0 flip rate. Base generation is what's reported.
- Numbers are `claude-sonnet-4-5` at today's prices; a model or prompt change
  moves them.
- Offline reproduction omits only the live endpoint's metering/save writes.
