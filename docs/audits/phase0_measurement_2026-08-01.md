# Phase 0 Measurement Pass — Accuracy / Anti-Fabrication Build Plan

**Date:** 2026-08-01
**Session type:** read-only diagnostic / audit (plain terminal path per CLAUDE.md
Session Routing). **No code, config, or DB rows were modified. Every Supabase query was
SELECT-only.** All prototype checks are offline; nothing was wired into the live path.
**Cost:** ~68 answer generations (32 baseline + 36 variance), ~$3–4 in API cost
(Anthropic generation dominant), well under the $50 ceiling.

Phase 0 is the read-only measurement gate the adopted plan (PLAN.md active phase
sequence) puts before Phase 1. It answers four questions: the *corrected* fabrication
rate, run-to-run variance, the false-positive rate of the two prototype deterministic
guards (Phase 2's teacher-name and numbers/absolutes checks), and a latency baseline.

---

## 0. How the live answer path was exercised (fidelity + caveats)

The measurement runs a **faithful offline reproduction** of `backend/app/routers/chat.py`,
not the deployed HTTP endpoint. It imports the real production functions and mirrors the
endpoint body step-for-step: position-paper interception (`match_position_paper`),
background-topic injection, query expansion (Groq `llama-3.3-70b`), hybrid RRF fusion
(pgvector + FTS, keyword routing), disabled-source filtering, boost + source-kind fusion
weights, document collapse (2/doc), **author cap (3/author)**, top-30 → **Cohere
rerank-v3.5** → top-8, neighbor expansion, commentary cap, conditional lexicon retrieval,
Claude generation (`claude-sonnet-4-5`, streamed, `max_tokens=1500`, `<answer>`
extraction), and SP1 reference verification (`verify_references`).

**Why offline, not the live URL:** the deployed endpoint's metering RPCs
(`increment_guest_query` / `increment_user_query`) and its `_save_conversation` call are
DB mutations. A SELECT-only session cannot fire them. The reproduction omits *only* those
writes (they live in the HTTP handler / fire only when a `user_id` is present); the
retrieval and generation code, models, prompts, and caps are identical to production.
**The pre-existing `scripts/sp1_answer_harness.py` was deliberately NOT used:** it is
stale (imports `_get_anthropic`, which `chat.py` no longer exposes) and, more importantly,
a *simplified* pipeline — no query expansion, no Cohere rerank, no author cap, no neighbor
expansion, no source-kind weights. Since the author-cap + multi-voice pressure is exactly
the mechanism the plan blames for fabrication, measuring the simplified path would measure
a different system than the one that fabricates.

**Caveats that bound every number below:**
- **Sample is a spot-check, not a certified rate.** 32 distinct questions (one run each)
  for the baseline; 12 of them repeated to 4 runs for variance. This sizes the problem —
  it is not a launch-grade error-rate certification (consistent with settled decision #2,
  "materially safer," and the no-public-frequency-claim posture).
- **Latency is stale (see §6).** Runs predate today's concurrency fix (9fdf8d2) in
  spirit, and were taken single-request from a local machine. Structural latency findings
  hold; absolute retrieval seconds do not.
- Answers are generated fresh; §4 measures exactly that nondeterminism.

### Fabrication classes measured
The plan's trigger was a teacher-attribution failure, and CLAUDE.md's ranked failure
modes put "misrepresenting a teacher" (#2) above "generic answers." So the headline metric
is **teacher-attribution fabrication**, in two classes, plus a corrected **scripture**
check:

- **`not_in_corpus`** — the answer attributes to a teacher who resolves to *no*
  `source_aliases` row (pure invention, or a nested quote re-credited to its original
  author). SP1 already withholds the study-panel *link* for these, but the misattribution
  stands in the **visible answer text**.
- **`in_corpus_not_retrieved`** — attributes to a teacher who *exists* in the corpus but
  whose material was **not retrieved for this question**. The dangerous class: it is
  exactly the gap in `verify_teacher_mention` (which checks name-resolves + license gate,
  never "was this teacher's material retrieved"), so it can render as a **verified** link
  — the "Bevere → empty author page" symptom.
- **Scripture (corrected recognition):** extract every reference the model wrote in *any*
  teacher-used form with the widened Layer-1 scanner
  (`citation_verifier_layers.find_layer1_candidates`), then resolve each against the
  `verses` table. A non-resolving reference is the scripture-fabrication signal. (The
  system prompt *permits* citing Scripture from the model's own knowledge, so
  grounded-in-retrieval is informational only, not a fabrication signal.)

---

## Question set (32 baseline)

| ID | Topic | Kind | Question |
|---|---|---|---|
| D1–D4 | deliverance | general/retrieval/debate | "What is deliverance ministry…", "…free from demonic strongholds", "Which teachers…generational curses", "…deliverance or just discipleship" |
| H1–H4 | healing | nondebate/debate/retrieval/general | "…healing guaranteed in the atonement", "Why isn't everyone healed…", "…faith and healing", "How should I pray for the sick" |
| P1–P4 | prophecy | general/debate/retrieval/debate | "…gift of prophecy today", "…testing a prophetic word", "…OT vs NT prophets", "Can a prophetic word be partly wrong…" |
| T1–T4 | tongues/baptism | nondebate/debate/retrieval | "Is tongues for today", "What is baptism of the Holy Spirit", "…initial evidence…", "Which teachers teach on tongues" |
| G1–G6 | general | general | fear of the Lord, hearing God's voice, intercession, fasting, spiritual warfare, repentance |
| TS1–TS4 | teacher-specific | teacher | Derek Prince / Zac Poonen / Vlad Savchuk / Leonard Ravenhill |
| S1–S4 | multi-voice | stress/debate | end times, holiness, apostolic authority, revival voices |
| E1–E2 | edge | edge | hyper-grace, contemplative meditation |

**Variance subset (12, ×4 runs):** H3, P4, D2, S1, P2, S2, H2, TS1, S4, P1, H1, S3.

**Path split (baseline, 32):** 26 normal (teacher-citation), 6 position-paper
(T1/T2/T3/T4 + H3 + G2 — see §7). The teacher-fabrication metric applies only to the 26
normal-path answers; the position-paper path names no teachers.

---

## 1. Corrected fabrication rate

### Teacher-attribution fabrication
Across the whole sample (**125 attributions** over 59 normal-path answers), the
teacher-name prototype flagged **8**, and **manual adjudication confirmed all 8 as genuine
fabrications** (0 false positives — see §5). They span three mechanisms:

**(a) Pure invention.** *D2 — "How do believers get free from demonic strongholds?"*
> "Warren Wiersbe's commentary on 1 John 5:18 reminds us that Jesus Christ keeps the
> believer so that the evil one cannot get his hands on him."

Warren Wiersbe has no `source_aliases` row and was not among the 8 retrieved authors. A
specific claim about 1 John 5:18 is credited to a commentator not in the corpus — invented
from training knowledge. SP1 correctly withheld the *link* (`in_verified=False`), but the
misattribution survives in the visible answer.

**(b) Nested-quote re-attribution** (the trigger audit's Billy-Graham case). On the
multi-voice questions, the model lifts quotes that a *retrieved* source (Precept Austin's
word studies) attributes to third parties and re-credits them to those third parties as
named library authorities: **Ray Stedman** and **Douglas Wilson** (S2, "## Ray Stedman on
sanctification / According to Ray Stedman *as quoted in Precept Austin's word study*…"),
**Philip Jenkins**, **Ralph Martin**, **Vance Havner** (S4). None of these has their own
retrieved material.

**(c) Verified-link-but-not-retrieved** (the Bevere symptom, reproduced). *S4 — "Who are
the key voices on revival…":*
> "According to the same word study, Tozer taught that personal revival comes through
> devoted time cultivating knowledge of God…"

**A.W. Tozer** resolves to a real servable corpus source, so `verify_teacher_mention`
**passed** it — it rendered as a **verified clickable teacher link** — yet Tozer's own
source was never retrieved; the content came from Precept Austin quoting Tozer. One
instance combining both trigger-audit failure modes: a verified link to unused material
*and* a nested quote. This is the single most important confirmation in this pass: the
dangerous `in_corpus_not_retrieved` class exists in the wild and **passes the current
verifier** (`verified_but_not_retrieved: 1`).

### Rate
- **Single-run baseline:** 1 of 26 distinct normal-path questions fabricated on its one
  run = **3.8%**.
- **This understates exposure** — see §4. The 4× variance pass surfaced two *more*
  fabricating questions (S2, S4) that were **clean on their first (baseline) run**.
- Pooled across all 59 normal-path answers (baseline + variance), 4 contained a
  fabrication = **6.8%**.

Whichever denominator, the corrected teacher-fabrication rate is **low single digits per
run, but real and reproducible**, and the worst class (verified fabricated link) is
present.

---

## 2. Scripture-fabrication rate (and why the old 72-reference number was inflated)

**155 scripture references** were extracted from the sampled answers using the corrected
(widened) recognition. **0 did not resolve to a real verse → 0% scripture fabrication.**

The prior 72-reference/64-proposition figure was a **scanner artifact, not a fabrication
count**. That scanner (`reference_grounding.find_reference_spans`) only recognizes compact
"Book C:V" citations and false-flags the spoken/expository forms teachers actually use
("Hebrews chapter ten, verse twenty-five"; a book named once with bare verse numbers
after). The corrected scanner recognizes those forms and evaluates them properly; when it
does, essentially every reference the model writes resolves to a genuine verse. Scripture
fabrication in the *answer path* is not a measurable problem in this sample — consistent
with settled decision #3 (misattribution to a name is deterministically solvable;
inventing substance is the hard part) and with the Landmines note demoting the stale
baseline. (Caveat: the model is *permitted* to cite Scripture from its own knowledge, so
"resolves to a real verse" is the correct bar here; verifying that a cited verse actually
*says* what the answer claims is a separate, harder check not attempted this pass.)

---

## 3. Variance (run-to-run)

12 questions × 4 runs (48 answers). The fabrication **outcome** and the render
**status** were each compared across a question's 4 runs.

| Signal | Result |
|---|---|
| Questions whose **fabrication outcome flipped** across runs | **3 of 12** (D2, S2, S4) |
| Questions that fabricated on **all 4 runs** | **0 of 12** |
| Questions whose **render/degradation flipped** across runs | **7 of 12** |
| Position-paper **routing** consistency | **Consistent** (H3 → tongues pillar on all 4 runs) |

**The central finding: fabrication is intermittent, never consistent.**
- **D2** fabricated (Wiersbe) on 1 of 4 runs.
- **S2** fabricated (Stedman, Wilson) on 1 of 4 runs — **clean on the baseline run**.
- **S4** fabricated on 2 of 4 runs (Havner/Tozer/Jenkins/Martin, then Havner) — **clean on
  the baseline run**.

Because it is intermittent, **a single-run test systematically understates the fabrication
rate.** The baseline pass found only D2; the variance pass revealed that S2 and S4 also
fabricate — they just happened to render cleanly the first time. **This is the empirical
case that variance matters more than any single-run pass rate**, exactly as the plan
premised.

Two secondary variance facts:
- **max_tokens degradation is also probabilistic** (7/12 flipped) — the same question
  sometimes renders a clean answer and sometimes truncates or dumps scratchpad, depending
  on run-to-run thinking-block length (see §7a).
- **Position-paper misrouting is deterministic** — it is cosine similarity over
  deterministic embeddings, so a question that mis-routes mis-routes every time (see §7b).

---

## 4. Prototype guard false-positive rates

Both guards are **offline prototypes**; neither was wired into the live path.

### 4a. Teacher-name check — **0% false positives**
For each answer: take the model's own `<reference_mentions>` TEACHER lines (what
`verify_references` consumes) plus a strict prose net; resolve each name →
`source_aliases.source_id`; map every retrieved chunk's `document_id` →
`documents.source_id`; a teacher counts as "retrieved for this question" if its source_id
is in the retrieved set **or** its normalized name matches a retrieved chunk author.

- **8 flags across 125 attributions; all 8 adjudicated true positives; 0 false positives.**
- An independent prose scan over all 26 baseline answers found **0 fabrications the check
  missed** (no false negatives for the "name not retrieved" class). Full-name attributions
  it surfaced — Dennis Moses (P4), Andrew Murray (G1/G3), Derek Prince (G4/G6/E1) — are all
  genuinely retrieved.
- A claim-level A2 spot-check (S1) confirmed the model's attributions to Derek Prince were
  verbatim-accurate against his retrieved chunks (secret-rapture rejection, "fire come
  down from heaven", "interval between two waves"), with correct document titles.

**Design finding for the real guard:** Andrew Murray is retrieved yet has **no alias row**
(the alias-gap Landmine). A check keying on alias resolution *alone* would false-flag him;
the prototype avoids it by also matching retrieved-author identity. **The eventual guard
must key on retrieved identity, not alias resolution alone** — otherwise the alias gaps
become false positives. With that discipline, the check is clean enough to gate on:
**0/125 false positives means a real guard built this way could be strict** without
suppressing legitimate attribution.

**Limitation:** the check catches "the named teacher's material was not retrieved" (the A1
class, and the nested-quote / verified-link cases). It **cannot** catch A2 — a claim
correctly sourced to one *retrieved* teacher but attributed to a *different* retrieved
teacher (the Brown/Kolenda case). No deterministic "was it retrieved" check can; that
needs claim-level source matching, which the corpus-quality work already found hard (the
rejected similarity check).

### 4b. Numbers / absolutes check — **100% false positives (0 true positives)**
For each sentence: extract digits, years, centuries, decades, spelled number-words, and
universal quantifiers; flag any that does not trace to the concatenated retrieved chunk
text. **Documented scripture exemption:** a curated biblical-number set (`forty`, `40`,
`three`, `seven`, `seventy`, `twelve`, `153`, `144000`, `666`, `1260`, `forty days`,
`three days`, `the twelve`, `seventy times seven`, `thousand years`, `seven
churches/seals/trumpets`, …), a same-sentence-as-a-scripture-reference rule, and `one`-idiom
exclusion (`loved one`, `one another`, `no one`, …).

- **14 flags on normal-path answers; all 14 adjudicated false positives. 0 true positives.**
- (26 additional flags on position-paper answers were excluded as inapplicable — those
  answers carry no retrieved chunks; their "source" is the owned paper body, which the
  harness does not put in the checked text.)

The false positives fall into clean categories, each of which a blunt guard cannot
distinguish from a fabrication:
1. **Fair quantifiers in theological prose** — "every believer", "in every case", "the
   only [offensive weapon]", "never/always" — legitimate description, often grounded in a
   scripture reference in the same sentence.
2. **Leaked `<thinking>` meta-text** — "250-400 words is appropriate" (from a degraded
   answer that dumped its own scratchpad).
3. **Grounded dates in a variant surface form** — "1961-62" flagged because the source
   wrote "1961–2" (year 1961 *is* grounded).
4. **Accurate but ungrounded general-knowledge dates** — "1904 Welsh revival", "1995
   Brownsville" — the source discussed the events without stating the year; the model
   supplied correct years from general knowledge. (Control: "1948 Hebrides" *was* in the
   source and was correctly not flagged — the grounding logic works; the problem is that
   "not in retrieved text" ≠ "fabricated" for well-known facts.)

**No fabricated number appeared anywhere in the sample.** (The trigger audit's one wrong
date — "mid-to-late 1800s" — lived on a *tongues* answer, which now routes to the
position-paper path and so is off the teacher-citation path entirely; see §7b.)

**Implication:** as prototyped, the numbers/absolutes check is unusable as a guard — it
would flag legitimate content on ~1 in 4 answers while catching nothing. Making it useful
requires narrowing it drastically (specific asserted statistics only, not quantifiers or
organizational counts) **and** a correctness oracle it does not have (an accurate date the
source didn't state is not a fabrication). It is a much lower-value guard than the
teacher-name check.

---

## 5. Adjudication standard

The Wiersbe case set the bar and was re-confirmed independently in this pass, not carried
forward as settled. A flag counts as a **true fabrication/misattribution** when: the
answer *attributes* a claim to a named teacher (not a passing mention), and that teacher's
own material was not the retrieved basis for the claim — either absent from the corpus
(`not_in_corpus`) or present but not retrieved for this question
(`in_corpus_not_retrieved`), including nested quotes re-credited to the quoted party. A
flag is a **false positive** when the attribution/number is legitimate: the teacher was
retrieved (possibly under an alias gap), or the number is grounded / scripture-derived /
an accurate general fact. Every one of the 8 teacher flags and 14 number flags was
adjudicated by reading the answer sentence and the retrieved authors/chunks.

---

## 6. Latency baseline — **STALE, do not treat as current; fresh run is follow-up**

**These numbers predate today's concurrency fix (commit 9fdf8d2, "unblock concurrent
request handling on /chat, Phase 1.1 + 1.2") and were taken single-request from a local
machine.** 9fdf8d2 changed `async def chat` → `def chat` (so FastAPI runs it in a
threadpool instead of monopolizing the event loop) and made `get_supabase()` a cached
singleton. It touches **no** retrieval ranking, prompt, cap, model, or generation logic —
so it does **not** invalidate the fabrication numbers above — but it directly changes
concurrent-load latency (its own commit message: 6 concurrent requests went 3.32s → 0.55s
wall-clock). **A fresh latency baseline should be measured post-9fdf8d2, from the Railway
environment (not a laptop), before any latency decision. Not re-measured this session.**

What the (stale) single-request local numbers show, seconds:

| Group (n) | TTFT median | TTFT p90 | Total median | Retrieval median |
|---|---|---|---|---|
| Normal, clean (19) | 23.8 | 29.2 | 38.4 | 5.8 |
| Normal, all (26) | 25.4 | 32.6 | 41.6 | 4.2 |
| Normal, degraded (7) | 29.2 | — | 48.6 | 2.6 |
| Position-paper (6) | **1.6** | 1.9 | 16.3 | 0.3 |

Two structural facts that are **robust to 9fdf8d2 and to the local-machine caveat**
(neither depends on cross-request concurrency or network round-trips — they are
model-side generation time):
- **Time-to-first-visible-text is dominated by hidden reasoning.** On clean normal
  answers, the model spends a **median ~18s** (mean 17.8s, max 24.1s) streaming the hidden
  `<thinking>` + `<research_analysis>` blocks *before* the first `<answer>` token the user
  sees. That is the single largest TTFT component, larger than retrieval.
- **The position-paper path is ~15× faster to first token** (1.6s vs 23.8s median) because
  it streams plain prose with no hidden XML blocks. This is a live illustration of what
  removing the hidden-reasoning preamble would buy.

Retrieval seconds (median ~5.8s local) are inflated by laptop→Supabase round-trips and
will be materially lower from Railway; do not treat them as the production retrieval cost.

---

## 7. Unplanned findings

### 7a. `max_tokens=1500` interacts with the hidden reasoning blocks to degrade answers

**7 of 26 normal-path baseline answers (27%) did not render a clean answer.** The
`<thinking>` + `<research_analysis>` blocks consume the 1500-token budget before the model
emits a complete `<answer>`. The affected answers skew toward larger retrieved sets (range
13–26 chunks; 6 of 7 had ≥18) but chunk count alone is not the trigger — some clean answers
also had 26 chunks — so it is the *length of the hidden reasoning* that exhausts the budget,
which is why it is probabilistic rather than a fixed function of retrieval size:
- **6 truncated** (`<answer>` opened, never closed) — the user sees an answer that stops
  mid-sentence.
- **1 no-answer-block** (H2) — no `<answer>` ever opened; the user sees the raw reasoning
  scratchpad ("Source 10 (Precept Austin): Similar to Source 6…", "250-400 words is
  appropriate", "I need to be careful here. The sources DO reference James 5:15…").

This is faithful to production: `chat.py`'s streaming fallback (`if not answer_parts:` →
emit raw output minus `<reference_mentions>`) is exactly what fires. It is **probabilistic**
(§3: render flipped on 7/12 repeated questions), so it will recur unpredictably on
long-context questions. It is independent of 9fdf8d2 (which changes neither the token cap
nor generation). Likely fixes to weigh in Phase 1: raise `max_tokens`, and/or move the
reasoning out of the token budget (structured/turn-separated reasoning, or trimming the
`<thinking>`/`<research_analysis>` scaffold). This degradation is arguably a worse
day-one user experience than the low-rate fabrication, because when it fires the user gets
visibly broken output, not a subtly-wrong attribution.

### 7b. Position-paper router over-matches — healing and "hearing God's voice" questions hijacked into the tongues pillar

The position-paper interception (baptism + tongues pillars) has two edges this pass
surfaced. On the good side, it means **tongues/baptism questions cannot produce
teacher-misattribution at all** — they name no teachers — so the plan's specific trigger
(a *tongues* answer misattributing to Kolenda/Brown/Bevere) is **no longer reachable on
that topic**. But the matcher is **greedy**, and three sampled questions were mis-routed
(all deterministic — same route on every run):

| Question | Routed to | Problem |
|---|---|---|
| **H3** "What do charismatic teachers say about the relationship between faith and healing?" | `speaking_in_tongues` | A *healing* question, explicitly asking *what teachers say*, answered in house voice on *tongues* — wrong topic **and** it suppresses the teacher attribution the user asked for. |
| **G2** "How do I hear God's voice in daily life?" | `speaking_in_tongues` | Not a tongues question at all — wrong-doctrine routing. |
| **T4** "Which teachers in the library teach on speaking in tongues?" | `speaking_in_tongues` | A *retrieval-intent* question ("which teachers") answered in house voice, naming none. |

This is a direct, measured instance of the exact problems the plan's **Phase 1 items
1.5–1.7** name (the tongues-paper neutrality breach, the teacher-question hijack, and
wrong-doctrine routing). Because routing is deterministic, every user who phrases a
healing/faith or hearing-God question this way gets the wrong answer every time. The
matcher's thresholds/contrast anchors (`position_papers.py`) need tightening, or the
interception needs to defer to the teacher-citation path when the question is
teacher-/retrieval-shaped.

---

## Summary

The corrected fabrication picture is **materially different from the stale number, but not
in the direction of "all clear."** Scripture fabrication is effectively **0%** (155
references, none non-resolving) — the old 72-reference figure was a compact-scanner
artifact, now explained and retired. Teacher-attribution fabrication, however, is **real
and reproducible at low-single-digit per-run rates** (1/26 baseline; 4/59 pooled), and the
**worst class is present and passes the current verifier**: A.W. Tozer rendered as a
*verified* teacher link on material that was never retrieved (the Bevere symptom), via a
nested Precept-Austin quote (the Graham symptom). **Variance is a real problem and the
headline methodological result:** fabrication is intermittent (3/12 questions flipped, 0/12
consistent), so the single-run rate understates exposure — the baseline pass missed S2 and
S4's fabrications entirely because they rendered cleanly the first time. On the guards, the
**teacher-name check produced 0 false positives across 125 attributions** (and 0 missed
fabrications on independent re-scan) — strong enough that a real guard built on retrieved
*identity* (not alias resolution, which the alias gaps would break) could be strict; the
**numbers/absolutes check produced 100% false positives and 0 true positives** — unusable
as prototyped, and a much lower-value guard.

**Does this change the plan's sequencing?** The four Phase 0 measurements **confirm the
existing sequence** — the teacher-name check (Phase 2) is validated as the right, feasible
deterministic guard, and building the model-based numbers/claim-support checker remains
correctly HELD (settled decision #4); this pass gives it a concrete reason (100% FP as a
naive check, and even a perfect grounding check can't call an accurate-but-ungrounded fact
a fabrication). But the two **unplanned findings deserve to be pulled forward**: (1) the
`max_tokens`/thinking-block **answer degradation hits ~27% of long-context answers and
renders visibly broken output** — a worse day-one experience than the low-rate
fabrication, and cheap to fix (raise the cap / move reasoning out of the budget); it
belongs early in Phase 1 alongside the already-landed 1.1/1.2 concurrency work, not later.
(2) The **position-paper over-matching** is already in scope as Phase 1 items 1.5–1.7, and
this pass confirms it is live, deterministic, and user-visible (healing and hearing-God
questions hijacked into the tongues pillar) — it should be treated as confirmed-and-ready,
not still-hypothetical. Neither unplanned finding is a reason to build anything beyond
Phase 0 in this session; both are flagged here for Phase 1 scoping, not acted on.

**Follow-ups (not done this session):** fresh post-9fdf8d2 latency baseline from Railway;
a claim-level (A2) misattribution probe if the Brown/Kolenda class is to be measured; and
whether the numbers/absolutes guard is worth building at all given its measured value.
