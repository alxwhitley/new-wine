# Position-synthesizing layer revival — read-only diagnostic (2026-08-04)

Read-only diagnostic. No application code was run or edited; no DB writes.
Two Explore agents inspected code/git history/docs directly; findings below
are separated into "confirmed by reading the code this session" vs. "prior
claim, not independently re-verified" throughout.

## Why this ran

Alex wants to revive the position-synthesizing layer (source-blind position
generation, one dominant teacher or the whole corpus) via four steps:
(1) confirm what's built, (2) make generation fast enough for question time,
(3) add a license/visibility check before evidence is used, (4) connect it to
live chat and prove it before real traffic. This diagnostic covers (1)-(3) and
the wiring shape of (4), to turn a "three to four weeks" estimate into a real,
file-referenced plan before anything is rebuilt or connected.

**Governance note:** CLAUDE.md's 2026-08-03 settled decisions (item 18)
deferred this system's durable-stored-positions half pending real usage, and
tied Open Decisions #14/#15/#16 to that deferral. Alex explicitly un-deferred
it on 2026-08-04 (see CLAUDE.md item 18's updated text) — this diagnostic and
the plan below proceed on that basis.

## 1. Inventory — untouched since 2026-08-01

Confirmed via `git log --follow` on every relevant file: the latest touching
commit for `scripts/positions.py`, `scripts/serve_position.py`,
`scripts/eligible_statements.py`, `scripts/prove_serving_path.py`,
`scripts/test_serve_position.py`, and migration 077 is `6b66199`
(2026-08-01); migration 076 alone is `2183a38` (also 2026-08-01);
`scripts/test_positions.py` is `d0f2404` (2026-07-30). Nothing has touched
this subsystem since. Later migrations 078/079 (the unrelated async-answer
project) do not reference the `positions` table at all.

**`scripts/positions.py`** (1102 lines):
- `generate_position_text(teacher_name, topic, evidence)` (:718) and
  `generate_corpus_position_text(topic, attributed_evidence)` (:752) are pure
  LLM-call wrappers — no DB import, no `source_id`/`document_id` parameter.
  Confirmed source-blind per CLAUDE.md Invariant 12, and independently
  asserted by `test_serve_position.py:31-50` via `inspect.signature()` against
  a forbidden-parameter list (`source_id, document_id, doc_id, chunk, chunks,
  conn, params, cur`) — still passes against the current signatures verbatim.
- Evidence gathering is separate and is the only DB-touching code:
  `gather_evidence()` (:531-579, single teacher) and
  `gather_evidence_corpus()` (:582-639, corpus-wide) — each opens/closes its
  own read-only connection.
- Every other function is either pure (`normalize_topic_key` :248,
  `prompt_fingerprint`/`_fingerprint` :348/352, `is_calvinism_predestination_topic`
  :464, `determine_scope`/`contributor_breakdown` :642/663) or a thin
  orchestrator (`write_position`/`write_corpus_position` :907/1023 call the
  generators above; `_insert_position_version` :817 is the one write path, a
  single transaction).

**`scripts/serve_position.py`** — lookup-or-generate:
`serve_position()` (:354) normalizes the topic → `topic_key`, resolves
`requested_teacher_id`, checks `lookup_current_position()` (:114, keyed on
`(topic_key, requested_teacher_id)` via `IS NOT DISTINCT FROM`); a stored
current row serves verbatim with **no LLM call** (`_serve_stored`, :205);
otherwise generates via `_generate_teacher_explicit`/`_generate_topic`
(:289/:305). `rebuild_position()` (:379) versions a rebuild via
`supersedes_id`, and allows teacher→corpus widening (the lookup key doesn't
include `kind`). Versioning columns confirmed present in actual queries:
`lineage_id`, `version`, `is_current`, `supersedes_id`, `topic_key`,
`requested_teacher_id` (serve_position.py:129-137). Four empty-state rules
implemented at :83-96 and :245-286.

**`scripts/eligible_statements.py`** — `EligibilityChecker`
(:123-172) is a lazy, per-candidate memoized wrapper around
`classify_eligibility()` (:91, document-text trigram closeness + citation
grounding). Its own docstring states the whole-corpus compute is CPU-bound and
far too slow for question time — **confirmed by reading the implementation**
(it reconstructs full document text and trigram-checks against every
proposition).

**UPDATE (same day, step 2 build): the "~15+ min" figure was wrong by 8x.**
Actually running `compute_eligible_proposition_ids()` against the full
11,139-proposition corpus (twice — once as a dry run, once for the real
write) measured **2h04m and 2h02m wall-clock respectively** (98-100% CPU
throughout, confirmed via `ps`, not a hang). Result: 8,284 eligible / 2,855
not eligible, identical both runs (deterministic, as expected). This is now
the real, measured basis for treating this as a genuine "materialize, don't
recompute live" hard blocker — it isn't just CPU-bound in principle, it is
CPU-bound at a scale that makes even a periodic re-backfill a multi-hour
commitment, not a quick nightly job. `scripts/backfill_proposition_
eligibility.py` now caches its computed result to `scripts/
eligible_ids_cache.json` (gitignored) immediately after computing, so a
failed/retried write never pays this cost twice — but a fresh recompute
(no `--use-cache`) still takes the full ~2h.

**`scripts/prove_serving_path.py`** — exactly 8 scenarios, 39 `check()`
assertions (grep-counted, matching the "39/39" figure on record) covering
serve-stored, teacher-generate, honest-empty (×2), corpus scope, genuine
disagreement, idempotent re-serve, and versioning/widening. Confirmed
**structurally consistent with current code** — the functions and shapes it
calls against still match current signatures. No drift found since
2026-08-01.

**Migrations 076/077** — confirmed present and unaltered: `positions.kind`
CHECK (`'teacher'`/`'corpus'`), `source_id` nullable + scope/source coupling
CHECK, and the versioning columns + a partial unique index enforcing one
current row per lineage.

## 2. Speed — confirmed by reading code, not by profiling

The recorded "6.94–7.81s across 3 live runs" figure (PLAN.md, not a
docs/audits measurement file) isolates only the `client.messages.create(...)`
call inside the two generators (positions.py:738-746 / 776-783):
`model="claude-sonnet-4-5"`, `max_tokens=500` (teacher) / `600` (corpus),
**blocking — no `stream=True`**.

**Neither generator sets `cache_control`** on its system blocks — unlike
`chat.py`'s `ANSWER_SYSTEM_BLOCKS` (:64-75) and `position_papers.py`'s
`system_blocks` (:754-769), both of which mark `cache_control: ephemeral`.
This is a concrete, unexploited win: an uncached ~500-token system+guardrails
prompt pays full write cost on every single call.

The position prompts (`BASE_TEMPLATE` :345, `CORPUS_PROMPT` :459) explicitly
instruct "Output ONLY the position text — no preamble, no headers, no
meta-commentary" and never request `<thinking>`/`<research_analysis>` blocks
— unlike the main chat path (`chat.py`'s `_stream_answer()`, `max_tokens=3000`,
driven by `system_prompt.txt`'s thinking→research_analysis→answer structure),
which a prior measurement (`docs/audits/per_answer_cost_measurement_2026-08-03.md`)
found spends ~53–59% of median generation wall-clock on hidden reasoning.
Structurally, the position call should *not* pay that specific tax — but **no
existing audit decomposes the 6.94–7.81s figure itself**; the reasoning above
is inference from code, not a profiling result.

`serve_position()`'s cold-generate path only pays this latency on the *first*
ask per topic — a stored row then serves instantly forever, until a
deliberate rebuild. `get_teacher_card()` (`backend/app/routers/study.py:819-924`)
is a *separate* mechanism that live-synthesizes on *every* view by design
(re-embeds the question, runs `match_teacher_chunks`, live-calls the LLM,
stores nothing) — already named as Project 2 scope (CLAUDE.md item 15,
"the standing live-synthesis leak," fix = precompute) and **explicitly out of
scope for this revival**. Note: `get_teacher_card()` *does* correctly apply
the license/visibility gate (via `is_source_servable()`) — see below.

## 3. License/visibility gap — confirmed present, exact location

Live chat retrieval (`chat.py:300`, `match_chunks` RPC) is gated by CLAUDE.md
Invariant 2's predicate, implemented in migrations 047/049:

```sql
EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id
  AND (s.license_status IN ('public_domain','owned')
       OR (NOT safe_mode_on AND s.visibility = 'shown')))
```

`get_teacher_card()` (study.py:855) applies the same predicate via the
reusable Python-side `is_source_servable()` (`source_resolver.py:25-44`).

**`positions.py`'s evidence-gathering functions apply neither.**
`gather_evidence()` (:552-563):

```sql
SELECT p.id::text, p.content, d.id::text, 1 - (p.embedding <=> %s::vector) AS similarity
FROM propositions p JOIN documents d ON d.id = p.document_id
WHERE d.source_id = %s ORDER BY p.embedding <=> %s::vector LIMIT 500
```

`gather_evidence_corpus()` (:606-618) is the same shape — it joins `sources`
only to fetch `s.name` for teacher-label display, never to gate. Neither
function references `license_status`, `visibility`, or `safe_mode_on`. This
is the sole, confirmed gap — exactly as named in prior project records.

## 4. Connection point — confirmed

`chat.py`'s `chat()` function (:637, not literally named `generate()`) calls
`match_position_paper()` (:712); on a match, `generate_position_paper_answer()`
(`position_papers.py:715-796`) streams from a paper's own chunk text
(`get_paper_body()`/`_ensure_body()`, :649-693) and returns before "Step 0"
(chat.py:759) — fully bypassing normal retrieval/`_stream_answer()`. This is
Invariant 12(b)'s already-shipped house-voice mechanism, separate from the
`positions` table. **No interception point exists today for the teacher/corpus
`positions` table.**

`get_teacher_card()` (study.py:819-924): re-embeds the question (:872), runs
`match_teacher_chunks` (:879-886), live-calls the LLM (`max_tokens=400`,
:904-918) to synthesize fresh from chunk excerpts every time — nothing
stored, ever. To serve a stored position instead of live chat.py generation,
a new interception point (parallel to `match_position_paper()`) would look up
a `positions` row via `normalize_topic_key()` (positions.py:248-264) before
falling through to `_stream_answer()`. `get_teacher_card()`'s live
embed→retrieve→synthesize block would need to become a read of a
precomputed row for that `source_id`.

## Recommended plan for steps 2–4

See PLAN.md's version-history entry for this date, and the plan file this
diagnostic session produced, for the full recommended build sequence. Summary:

- **Step 2 (speed):** materialize eligibility (`classify_eligibility()`
  reused verbatim in a batch job, not recomputed live) is the highest-priority
  fix — a documented hard CPU-bound blocker, separate from the LLM-call
  figure. Then add `cache_control` to both generators (cheap, do regardless)
  and streaming siblings mirroring `position_papers.py`'s existing streaming
  pattern, keeping the blocking functions unchanged for the offline/batch
  path. `get_teacher_card()` stays out of scope (Project 2's fix, precompute).
- **Step 3 (license gate):** add the Invariant 2 predicate as one shared named
  SQL constant to both `gather_evidence()` and `gather_evidence_corpus()`,
  query-time (not a per-row Python check — this module is psycopg2-only).
  Audit the 3 existing draft rows against the new filter before trusting them.
- **Step 4 (connect + prove):** the real work is topic matching
  (`match_stored_position()`, calibrated with the same discipline
  `match_position_paper()` needed over two live bug-fix rounds), not wiring
  itself — this makes Open Decision #16 (topic list) a hard prerequisite. Two-
  level off-switch reusing the async-answer-path's proven pattern, sized down
  to one `app_settings` boolean. Resolve whether draft-status positions may
  serve unreviewed before any real traffic sees this.

**Open decisions flagged for Alex, not decided here:** #13 (dominance
threshold ownership), #14 (refresh trigger), #15 (replace-vs-version), #16
(topic list — now a hard prerequisite), whether draft positions need an
approval gate before serving live, whether an empty-topic result should
surface its own wording inside a live chat turn, and where
`positions.py`/`serve_position.py` should live relative to
`backend/app/services/`.

## Step 2 (speed) — built and verified, same day

All three pieces shipped:

1. **Materialized eligibility** (migration 080: `propositions.eligible boolean
   NOT NULL DEFAULT false` + a partial index; `scripts/
   backfill_proposition_eligibility.py` backfills it by calling
   `compute_eligible_proposition_ids()` verbatim). Real write: 8,284
   eligible / 2,855 not-eligible of 11,139 total, reconciled on a fresh
   connection. `eligible_statements.load_eligible_ids()` is the new fast
   loader (a single indexed `SELECT ... WHERE eligible = true`); no change was
   needed to `gather_evidence()`/`gather_evidence_corpus()` themselves —
   `_is_eligible()` (positions.py:520-528) already treats a precomputed set
   polymorphically alongside the lazy `EligibilityChecker`, so only the
   *caller* that builds the eligible-ids argument needed to change.
   `prove_serving_path.py`'s `build_eligibility()` now uses the materialized
   loader instead of the lazy checker.
2. **`cache_control: ephemeral`** added to both `generate_position_text()` and
   `generate_corpus_position_text()`'s system blocks (positions.py), mirroring
   `chat.py`/`position_papers.py`'s existing pattern.
3. **Streaming siblings** `generate_position_text_stream()` /
   `generate_corpus_position_text_stream()` added (positions.py), yielding
   plain `str` chunks (no SSE framing — that's a future
   `backend/app/services/position_layer.py` integration concern, step 4's
   scope, not this module's). The existing blocking functions are unchanged
   and still used by the offline/batch path. Both new functions carry the
   identical source-blind signature — extended `test_serve_position.py`'s
   Invariant-12 signature check to cover them; all pass.

**Verification: `test_serve_position.py` (deterministic) — all pass, 100%.**

**Verification: `prove_serving_path.py` (live, real LLM calls) — 32/36
checks passed; the 4 failures are a pre-existing test-fixture staleness
issue, NOT a regression from today's changes.** Root cause, confirmed live:
three of the proof's hardcoded topics ("the divine exchange at the cross" /
Prince, "holiness and personal purity" / corpus, "can a believer lose their
salvation" / corpus) already have permanent `is_current=true` stored
positions from the *original* 2026-08-01 proof run (PLAN.md's own record:
"3 genuine draft positions persisted... the widening demo lineage was
cleaned up" — a deliberate choice at the time, these three were kept, unlike
the widening demo). This is the first time anyone has re-run
`prove_serving_path.py` since that original run, so this is the first time
its non-idempotency on those 3 fixture topics has ever surfaced. Today,
`serve_position()` correctly found the existing rows and served them from
storage — exactly correct lookup-or-generate behavior — but the test's
hardcoded expectations (`served_from == "generated"`, an LLM call actually
happening, a `scope_determined` key that only `_serve_written()` ever sets)
assume a first-time ask, so those specific assertions fail on a second run
regardless of anything about eligibility materialization. Every check that
actually exercises the changed code path passed cleanly: Case 1 (serve-
stored), Case 3/6 (honest-empty, exercises the floor logic against the new
materialized set), and — most importantly — Case 8 (fresh teacher-dominated
generation, then a corpus-widening rebuild, both against a genuinely new
topic never asked before, both with correct DB versioning and cleanup). This
proof-script non-idempotency is a real, disclosed, PRE-EXISTING gap,
independent of this session's changes — left as-is, not silently patched, since
fixing it means either choosing new fixture topics (a judgment call about
what still exercises the same scenarios) or deciding whether to finally clean
up the 3 persisted rows, neither of which this session's scope covers.

## Step 3 (license/visibility gate) — diagnostic (2026-08-04, read-only)

Read-only investigation only. No schema, migration, or generator code was
changed this session — every SQL definition below was re-confirmed against
the LIVE database (`pg_get_functiondef`, `information_schema`,
`pg_constraint`, direct `SELECT`s), not just the migration files, because
this repo has a **documented, confirmed history of live-vs-file drift on RPC
definitions** (migration 056's own comment: `match_commentary_by_book`'s live
definition did not match its own migration-028 file). `match_chunks` was
checked the same way and confirmed NOT drifted — its live definition matches
migration 049's file exactly.

### 1. Every place rights/license/visibility is checked before use in an answer

- **`match_chunks` / `search_chunks_fts`** (migrations 043→045→046→047→048→049;
  live-confirmed unchanged since 049) — the main `chat.py` retrieval path
  (`db.rpc("match_chunks"/"search_chunks_fts", ...)`, `chat.py:287-330`).
- **`match_lexicon_chunks`, `match_commentary_by_book`, `match_commentary_chunks`,
  `match_sermon_chunks_by_ref`, `search_documents`** (migration 056) — five more
  RPCs gated the same way.
- **`match_teacher_chunks`** (migration 065) — used by `get_teacher_card()`;
  same gate, applied as defense-in-depth (the calling endpoint already filters
  via `is_source_servable()` before calling this RPC — migration 065's own
  comment).
- **`is_source_servable()`** (`backend/app/services/source_resolver.py:25-49`)
  — the canonical, reusable Python-side implementation of the identical
  predicate, used by `study.py`'s `get_teacher_card()`.
- **`backend/app/services/position_papers.py`** — **zero** rights checks
  anywhere (confirmed by grep: no match for `license_status`, `visibility`,
  `safe_mode`, `is_source_servable`, or `is_copyrighted`). Position papers
  read only Alex's own first-party authored content (Invariant 12(b)), which
  plausibly explains the absence — but this is a confirmed absence, not an
  assumed one.
- **`scripts/positions.py`'s `gather_evidence()`/`gather_evidence_corpus()`**
  — zero rights checks (re-confirmed from the prior diagnostic session).
  **This is the actual gap step 3 closes.**

### 2. The specific field(s) — precise semantics, live-verified

| Field | Type / values (live-confirmed) | Real meaning |
|---|---|---|
| `sources.license_status` | text, NOT NULL DEFAULT `'unlicensed'`, CHECK IN (`'public_domain'`,`'owned'`,`'licensed'`,`'unlicensed'`) | Legal rights/permission status of the ENTITY (teacher/rights-holder) — migration 043 |
| `sources.visibility` | text, NOT NULL DEFAULT `'hidden'`, CHECK IN (`'shown'`,`'hidden'`) | The CURATION dial, independent of `license_status` (migration 046's own comment: "independent of license_status") |
| `app_settings['safe_mode']` | text `'on'`/`'off'`, one global row (currently **`'off'`**, live-confirmed) | Global kill switch; read fresh every call, never cached (`is_source_servable()`'s own docstring) |

**The real gate, confirmed identical everywhere it's used (migrations 049/056/065, `is_source_servable()`), unchanged since migration 049:**
```sql
s.license_status IN ('public_domain', 'owned')
OR (NOT safe_mode_on AND s.visibility = 'shown')
```

**`documents.is_copyrighted` — THE TRAP FIELD, confirmed precisely.** Live:
`boolean NOT NULL DEFAULT false` (1,068 `false` / 2,527 `true` live). It still
exists and is still referenced in `match_chunks`'s live WHERE clause
(`include_copyrighted OR d.is_copyrighted = false`) — **not removed, but
neutralized**: `chat.py`'s caller passes `include_copyrighted` computed as
`filters["include_copyrighted"] and INCLUDE_COPYRIGHTED_ENV` (`chat.py:761`,
default-True-shaped), which in the common case makes that clause a no-op.
CLAUDE.md Invariant 4 confirms why this field is untrustworthy as a rights
signal on its own: it's derived from folder path at ingest time and is wrong
in practice (Derek Prince's documents, under real copyright, read `false`).
**Do not use `is_copyrighted` for step 3's gate** — it answers a different,
unreliable question ("did the ingest folder path look copyrighted"), not
"does Rhemata have the rights to serve this."

**`citation_mode`** (a `documents`-level text field, e.g. `'citable'`/
`'silent_context'`) is a **different concern** — Invariant 7: whether a real
attributable name may be shown, not whether content may be retrieved/used at
all. One RPC (`match_sermon_chunks_by_ref`) additionally filters on
`citation_mode = 'citable'`, but that's an attribution-display filter specific
to that RPC's use case, not part of the rights gate itself. Flagging this
explicitly so it isn't mistaken for a second rights field.

**`sources.retrievable`** (a generated column, migration 043) — confirmed to
exist live but **do not use it**; see finding #5 below.

**Live value distribution (2026-08-04):** `owned`/`shown`: 2 sources,
`public_domain`/`shown`: 28, `unlicensed`/`hidden`: 14, `unlicensed`/`shown`:
29. No `'licensed'`-status source currently exists. `safe_mode` is `'off'`.

### 3. `gather_evidence()`/`gather_evidence_corpus()` — current filtering + relationship to `propositions.eligible`

Re-confirmed: zero reference to `license_status`/`visibility`/`safe_mode_on`
in either function (`positions.py:552-563`, `:606-618`).

**`propositions.eligible` (migration 080, step 1) is entirely orthogonal to
rights gating.** It is a closeness+citation-grounding "is this proposition's
content faithful/well-grounded" signal
(`eligible_statements.classify_eligibility()`) — confirmed via grep, its own
code never references `sources`, `license_status`, `visibility`, or
`safe_mode` anywhere. The polymorphic `_is_eligible()` check
(`positions.py:520-528`) that `gather_evidence`/`gather_evidence_corpus` call
has nothing to do with rights; it is purely a quality/faithfulness gate.
Materializing eligibility (step 2) did not touch, and does not substitute
for, a rights gate — these are two independent dimensions a proposition must
clear (faithful AND rights-cleared), not one.

### 4. Proposed minimal correct gate (proposal only — not implemented this session)

- **Reuse the exact Invariant 2 predicate verbatim** — the same one
  migrations 049/056/065 and `is_source_servable()` already use. Nothing new
  to invent.
- **No new migration or precomputed column needed**, unlike
  `propositions.eligible`: `license_status`/`visibility` live on `sources`,
  one row per teacher/entity (73 rows live), not per-proposition — a plain
  `JOIN` at query time is cheap (an indexed lookup against a tiny table), not
  the CPU-bound whole-corpus computation eligibility required.
- **`gather_evidence()`** (positions.py:531-579) already `JOIN`s `documents
  d` — add `JOIN sources s ON s.id = d.source_id` plus a `safe_mode_on`
  lookup (read fresh every call, matching `is_source_servable()`'s
  discipline — never cache it), then `AND (s.license_status IN
  ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility =
  'shown'))`.
- **`gather_evidence_corpus()`** (positions.py:582-639) **already** `JOIN`s
  `sources s` (for the teacher-name label) — the predicate slots directly
  onto that existing join; no new join needed there.
- **Do not reference** `documents.is_copyrighted` (unreliable, §2), `citation_mode`
  (a different concern, §2), or `sources.retrievable` (inconsistent, §5).
- **Recommend** factoring the predicate into one shared named SQL fragment in
  `positions.py` (as the prior diagnostic session already recommended), with
  a comment pointing at CLAUDE.md Invariant 2 as the source of truth — this
  repo has a confirmed precedent for what happens when a gate's wording isn't
  centralized (`match_commentary_by_book`'s drift, §1 preamble).

### 5. Pre-existing bugs/inconsistencies found (recorded only, not fixed)

- **`sources.retrievable` (generated column, migration 043) does not match
  the real serving gate, and is unused anywhere in the codebase** (confirmed
  by a repo-wide grep for `.retrievable` across `backend/`, `scripts/`,
  `frontend/` — zero real hits). Its formula is `license_status IN
  ('public_domain','owned','licensed')` — no `visibility`, no `safe_mode`  —
  while the REAL gate treats `'licensed'` sources the SAME as
  `'unlicensed'`: subject to `visibility='shown'` AND `NOT safe_mode_on`, not
  automatically retrievable. **Currently dormant** — no live `'licensed'`
  source exists to expose the discrepancy (confirmed live, §2) — but this
  column would silently mislead anyone who reads it directly (e.g. a future
  admin dashboard) into believing a licensed-but-hidden source is servable
  when the real gate would exclude it.
- **29 of 73 sources are `license_status='unlicensed'` AND
  `visibility='shown'`, currently live-retrievable since `safe_mode` is
  `'off'`.** Not flagged as a bug — this matches the documented 2026-08-01
  "hidden-by-default reversed" decision and `visibility` being the deliberate
  curation dial for unlicensed material — recorded here as a live fact
  worth knowing, since it's a large fraction of what "unlicensed" sources
  actually means operationally (visibility-gated, not rights-cleared).
- **`chat.py`'s `include_copyrighted` is not simply "always True"** the way
  Invariant 4's prose might suggest at a glance — it's `filters
  ["include_copyrighted"] and INCLUDE_COPYRIGHTED_ENV` (`chat.py:761`), a
  real conditional on request-level filters and an environment flag. Not
  investigated further this session (out of scope — this concerns `chat.py`'s
  retrieval, not the source-blind path), flagged only so a future reader
  doesn't assume the neutralization is unconditional without checking.

## Step 3 (license/visibility gate) — built and verified (2026-08-04)

Executed the proposal above exactly: `LICENSE_GATE_SQL` (positions.py, a
shared named constant reusing Invariant 2's predicate verbatim) +
`_read_safe_mode_on()` (reads `app_settings['safe_mode']` fresh per call,
never cached). `gather_evidence_corpus()`'s existing `sources` join got the
predicate added to its `WHERE`; `gather_evidence()` got a new `JOIN sources
s` + the same predicate. No migration, no schema change, no touch to
`documents.is_copyrighted`, `citation_mode`, `sources.retrievable`, or
`propositions.eligible` — exactly as scoped. Commit `6fc39bc`.

**Verified:** `test_positions.py` (Tier A + Tier B, live) and
`test_serve_position.py` both clean. `prove_serving_path.py`: 32/36,
byte-identical to the pre-gate baseline — same 4 pre-existing failures
described above (fixture staleness, unrelated).

**Confirmed the gate does real, correct work, not just a no-op:** Case 3's
crossover-teacher list changed from `[Prince, Savchuk, Kreighbaum, Poonen]`
to `[Prince, Kreighbaum]` — Savchuk and Poonen are both live-confirmed
`license_status='unlicensed'`, `visibility='hidden'`, so the real gate
correctly excludes them; Prince and Kreighbaum are `unlicensed`/`shown`,
correctly included. This matches exactly what `match_chunks`/
`is_source_servable()` already decide for these same four sources —
`gather_evidence()`/`gather_evidence_corpus()` no longer disagree with the
rest of the product on which sources are servable.

**Still open, not this session's scope:** `sources.retrievable`'s dormant
inconsistency (finding #5) — flagged, not fixed. Step 4 (topic-matching +
chat.py wiring) is next.
