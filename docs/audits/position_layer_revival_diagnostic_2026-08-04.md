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

## Step 4 (connect + prove) — diagnostic (2026-08-04, read-only)

Read-only investigation only. No schema, code, or config was changed this
session. Every claim below is either confirmed by reading the current
repo (file:line given) or a live `grep` result quoted verbatim; anything
that is inference rather than a direct read is labeled as such.

### 1. End-to-end map — live path vs. source-blind path

**`chat.py`'s `chat()` (:637) is the single live entry point and already
branches twice before reaching the normal RAG path:**

- **(a) Position-paper interception** (`match_position_paper()`, :712) —
  house-voice, zero citations, zero per-token verification, TRUE live
  token streaming straight from the model
  (`position_papers.py:generate_position_paper_answer`, :715-798). Returns
  before "Step 0" (:759).
- **(b) Normal RAG path** (`generate()`, :1006) — the default. Retrieval →
  buffer the full generation server-side (`_stream_answer`, :543) → Phase 2
  attribution-grounding guard, regenerate-once-then-refuse (:1106-1140) →
  `verify_references` (:1144) → background-thread conversation save
  (:1153-1160) → THEN a server-paced typewriter reveal (`_playback_events`,
  :613-622, ~250 chars/sec) → one meta SSE event → `[DONE]`.
- **(c) `async_chat.py`** (built, **not mounted** — `async_chat.py:1-9`'s
  own header) — a durable-queue wrapper around the SAME generation logic as
  (b), mirrored not shared (per the standing async-path drift-point already
  on record in CLAUDE.md). `POST /async-chat/submit` enqueues and returns
  instantly; `GET /async-chat/result/{job_id}` streams keepalives while
  queued/running, then delivers the WHOLE already-verified answer in one SSE
  event and lets the **client** pace the reveal
  (`frontend/lib/api.ts:205-213`, `clientPaceReveal()`) — a third, distinct
  delivery shape from (a) and (b), not just a different transport for the
  same one.

**`scripts/positions.py`/`scripts/serve_position.py` is a fourth, wholly
separate mechanism, with zero live callers today.** Confirmed by grep:
`serve_position()` has exactly one caller in the entire repo outside its own
definition and test/proof scripts — `rebuild_position()`'s own fallback at
`serve_position.py:402` (itself uncalled from anywhere live). It is
exercised only by `scripts/prove_serving_path.py` and
`scripts/test_serve_position.py`. It is architecturally disjoint from (a)-(c)
in a way not previously called out: it opens raw `psycopg2` connections
(one per function call — see §5 finding 1) against the `positions` /
`propositions` tables, never touches the `chunks` table, and never imports
or calls into `app.db.supabase.get_supabase()` — the client every other live
answer path (chat.py, position_papers.py, async_answers/producer.py's
retrieval mirror) uses exclusively.

**What would have to change for a real question to route through it:** a new
interception point in `chat()`, structurally parallel to
`match_position_paper()` (:712) and evaluated at the same point (before
"Step 0", :759) — gated on a topic match against the `positions` table
(`match_stored_position()`, per the prior diagnostic's naming — **confirmed
this function does not exist anywhere in the repo today**, `grep` returns
zero hits). On a match it would need to call something that (1) resolves
`topic_key`/`requested_teacher_id` the same way `serve_position()` does, (2)
serves a stored row verbatim if one exists, or (3) cold-generates — and, for
(3), stream tokens back through whichever SSE shape is chosen (§3) while
still persisting via `_insert_position_version` once the stream completes.
No such orchestration function exists yet in blocking OR streaming form —
see §3's "unwired dead code" finding.

### 2. What "connect" means — options and what's actually supported today

- **Full cutover.** No precedent anywhere in the repo. Highest blast
  radius: once a lineage is written, `serve_position()` serves that SAME
  stored row on every future identical question, forever, until a
  deliberate rebuild (§ "Lifecycle" in `serve_position.py`'s own docstring,
  :6-11) — a bad first generation would not just answer one user badly, it
  would answer every future asker of that question badly, permanently,
  with no live regeneration to self-correct.
- **Two-level flag/off-switch, reusing the async-answer-path's proven
  shape.** **This IS supported today, generically** — the pattern (env var
  gates whether the code/routes are even mounted; a DB boolean is the
  seconds-reversible traffic dial, read fresh every call, never cached) is
  proven end-to-end for a much larger surface (`async_answer_config` +
  `ASYNC_ANSWER_ENABLED`, `backend/app/services/async_answers/config.py`,
  `async_chat.py:97-113`). Re-implementing it for this feature is a small,
  well-trodden addition (a `serving_enabled`-shaped boolean plus a
  `load_config`-shaped reader), not new design.
- **Percentage-based rollout.** No precedent anywhere in the repo — `grep`
  for rollout-percentage/hash-bucket patterns across `backend/app` and
  `scripts` returns zero hits. Guest/user metering is exact-count-based,
  not probabilistic; nothing in the live serving path currently draws
  randomness at all. Building this would introduce a genuinely new kind of
  nondeterminism to the serving path — worth a deliberate decision, not a
  quick bolt-on, if it's ever wanted.
- **Shadow mode (both generate, only one shown).** No precedent — `grep`
  for shadow-mode/comparison-logging patterns returns zero hits; no table
  exists to record a side-by-side comparison. Real, if small, new
  engineering: a background call to the source-blind path alongside normal
  generation, plus somewhere to log both outputs for comparison. Not
  supported today, but the closest option in spirit to what §4's "proven
  end-to-end" actually needs, and the only option with zero user-facing
  risk while evidence is gathered.

### 3. Streaming interface — confirmed, and it is NOT one shape

**Three distinct shapes already exist live/near-live**, not one:

1. `chat.py` main RAG path: nothing reaches the client until the full
   answer is generated AND verified server-side; then many small
   `{"token": part}` SSE events at a fixed server-paced rate
   (`_playback_events`, :613-622).
2. `chat.py` position-paper path: TRUE live per-token SSE — one
   `{"token": text}` event per real `content_block_delta`
   (`position_papers.py:790-794`).
3. `async_chat.py` `/result`: `: keepalive` comments while pending, then
   ONE `{"answer": full_text}` event delivered whole, with the **client**
   pacing the typewriter reveal locally (`frontend/lib/api.ts:205-213`).

**The frontend consumer is actually a single contract, not three.**
`StreamCallbacks` (`frontend/lib/api.ts:78-82`: `onToken` / `onMeta` /
`onError`) is satisfied by both `streamChatMessage()` (shapes 1 and 2 — it
doesn't distinguish them, both just emit `{"token": ...}` events) and
`streamAsyncChatMessage()` (shape 3, translated to the same callbacks via
`clientPaceReveal()`). **The frontend is not the constraint** — a thin
backend adapter to either existing shape is proven to work twice already;
building a fourth wire shape is a choice, not a requirement.

**`positions.py`'s streaming siblings do not match any of the three.**
`generate_position_text_stream()` / `generate_corpus_position_text_stream()`
(:830-903) yield **plain Python `str` chunks — no SSE framing at all**, by
design (their own docstrings: "a caller ... is responsible for any SSE
framing"). Confirmed by `grep`: their only references anywhere outside
`positions.py` itself are signature-shape assertions in
`test_serve_position.py:54-64` — **zero real callers**. Two live precedents
for closing the gap, requiring comparable effort:
- Wrap each `str` delta in `_sse(json.dumps({"token": text}))` exactly as
  `position_papers.py:794` does → drops straight into `streamChatMessage()`
  unchanged (shape 2).
- Or don't stream token-by-token at all for the connect step: call the
  existing BLOCKING `generate_position_text()` /
  `generate_corpus_position_text()` (already the only generators actually
  wired into `write_position()`/`write_corpus_position()`, :1091/:1175) and
  deliver the whole answer via shape 3's `{"answer": ...}` + client-paced
  reveal. Arguably the better fit here specifically **because §5 finding 3
  shows there is no per-token safety check this path could interrupt on
  anyway** — true live streaming would buy latency-perception only, not
  safety, for this particular generator.

**Newly found this session, not covered by steps 1-3:** `write_position()`
and `write_corpus_position()` call ONLY the blocking generators
(positions.py:1091, :1175) — the streaming siblings added in step 2 are
never invoked by the one code path that actually persists a position.
There is no orchestration function anywhere, blocking or streaming, that
both (a) streams tokens to a caller and (b) still calls
`_insert_position_version()` to persist once the stream ends. That function
does not exist yet — building it is real work step 4 has not scoped.

### 4. What "proven end-to-end" should mean — dimensions and current measurability

| Dimension | Measurable today? | Basis |
|---|---|---|
| Content fidelity (no claims beyond the given evidence) | **No** | Enforced only by the "FOUR CORNERS" prompt instruction (`positions.py:335`, `:451`) — no code-level check exists. Contrast with `chat.py`'s live path, which has two (attribution grounding + `verify_references`). |
| Misattribution inside generated prose | **No** | Both prompts instruct the model to write the teacher's name directly into the output ("Name the teacher at least once, naturally" — `RESOLUTION_INSTRUCTION_ORDINARY`/`_TENSION`, :385-407; "Attribute views to the teachers who actually hold them, by name" — `CORPUS_PROMPT`, :455). This is exactly the failure category `chat.py`'s `_ungrounded_reference_teachers`/`ungrounded_prose_teachers` (`reference_verifier.py`) exist to catch for the live path — nothing analogous runs here, for either the single-teacher or (higher-risk, multi-teacher) corpus generator. |
| Scripture-reference fabrication | **Yes, cheaply, unwired** | `verify_verse_mention()` (`reference_verifier.py:276-292`) only checks that a cited verse exists in `verse_lookup` — it is source-agnostic and could run against generated position text with no adaptation. Not currently called anywhere in `positions.py`/`serve_position.py`. |
| Citation correctness | **N/A by design, structurally safer** | Positions carry no `[Source N]` citations to verify — only `contributor_breakdown_from_db()` (positions.py:721-751), a mechanical `GROUP BY` over immutable `position_evidence` rows, not a model claim. Nothing for a model to get wrong here the way it can with a live `[Source N]` citation. |
| Regression vs. prior fabrication-crisis findings | **Not evaluated — a genuinely new risk surface, not a re-check of an old one** | Invariant 11 / the Landmines citation-fabrication work (`citation_verifier_layers.py`, `reference_grounding.py`) operates at PROPOSITION EXTRACTION time and is already baked into `propositions.eligible`. It has never been run against POSITION SYNTHESIS — a second-order risk (several already-eligible propositions stitched into new prose by a second LLM call) with zero prior audit coverage in this codebase's fabrication-crisis history. |
| Latency under real conditions | **Partially** | The step-2 diagnostic's own 6.94-7.81s figure was explicitly disclosed as "inference from code, not a profiling result," and no p50/p95 under concurrent load has ever been measured (parallel to the async project's own unresolved worker-pooler-concurrency gap). |
| Review/approval status | **Structurally cannot mean "reviewed" today** | See §5 finding 2 — every row is permanently `status='draft'`; nothing transitions it. |

### 5. Blockers / unresolved dependencies — newly found this session

1. **DB access architecture mismatch between the two subsystems.**
   `positions.py`/`serve_position.py` are 100% raw-`psycopg2`,
   connection-per-call — `gather_evidence()`, `gather_evidence_corpus()`,
   `lookup_current_position()`, `_insert_position_version()`,
   `resolve_teacher_source_id()` each open and close their own connection.
   `chat.py` has never opened a raw `psycopg2` connection in its live
   request path — confirmed by import grep, Supabase REST client only.
   Wiring `serve_position()` directly into `chat()`'s synchronous request
   handling means either accepting several new unpooled connection
   round-trips per matched request (latency + connection-count pressure
   `chat.py` doesn't pay anywhere else today), or routing through
   `async_answers/db.py`'s already-built pooled `Db` class instead of
   `positions.py`'s ad hoc connect-per-call pattern. Precedent for the fix
   exists in-repo; it just isn't applied here. Not raised in steps 1-3.

2. **Every stored position is permanently `status='draft'`, by
   construction, not oversight.** Migration 073's CHECK permits
   `('draft','approved','stale','retracted')`; `_insert_position_version`
   (positions.py:992) hardcodes `'draft'` on every insert; **no code
   anywhere transitions draft → approved** (confirmed by grep for
   `'approved'` as a write target — zero hits); `lookup_current_position()`
   (serve_position.py:127-136) serves any row with `status <> 'retracted'`,
   draft included, indistinguishably from a hypothetically-reviewed row.
   This is precisely the tension CLAUDE.md's Settled Decision #1 already
   flags (⚠ "the position serving path stores and re-serves generated
   positions and has a planned draft-review UI ... reconcile if/when that
   path goes live") — **this diagnostic is that "if/when" moment.** It must
   be a deliberate decision (serve drafts live on purpose, matching Decision
   #1's "no human review gate" philosophy — or build the minimal approval
   step PLAN.md's Open Decision #20(b) already anticipated) before any real
   traffic reaches this path, not something left to default.

3. **No code-level content-fidelity check exists for generated position
   text** — see §4's first two rows. Given CLAUDE.md's own ranked failure
   modes (#1 theologically wrong, #2 misrepresenting a teacher) and this
   being named the highest-stakes step in the arc, this is the single
   largest gap between "built" and "safe to expose to real traffic."

4. **The streaming siblings are unwired dead code; no stream-and-persist
   orchestration exists.** See §3.

5. **`propositions.eligible` is correctly available via the fast loader,
   but has no live caller to consume it correctly yet, and the one
   existing precedent in the repo uses the slow path.**
   `generate_teacher_positions.py:66` calls
   `es.compute_eligible_proposition_ids()` (the ~2-hour whole-corpus
   compute) directly — harmless there because it's an offline CLI batch
   driver that predates step 1-2's materialization work, but it is now a
   live-latency footgun template sitting in the repo. Explicit flag for
   whoever builds the `chat.py` interception: it must call
   `eligible_statements.load_eligible_ids()` (the fast materialized
   loader), and should almost certainly memoize the resulting ~8,284-row
   set at process level — mirroring the lazy-cache pattern
   `_ensure_teacher_aliases()` (position_papers.py:402-439) and
   `_ensure_background_topics()` (chat.py:125-150) already use for
   comparable small, slow-changing, whole-table reads — rather than
   re-querying it on every matched live chat request. `load_eligible_ids()`
   itself does no caching (eligible_statements.py:175-208); today's only
   callers (`prove_serving_path.py`, the step-2/3 build) treat that as
   fine because they call it once per script run, not once per request.

6. **No freshness/staleness signal on a served position.** Unlike
   `chat.py`'s live retrieval (always current by construction) and the
   async path (stamps `evidence_version = get_corpus_version()` on every
   answer), a stored position can be arbitrarily old relative to the
   current corpus with nothing communicating that to the caller or reader.
   This is Open Decision #14 (refresh trigger), already flagged unresolved
   in this diagnostic's earlier sections — repeated here only to confirm it
   becomes a live-traffic-facing gap, not a background nice-to-have, the
   moment real questions can reach this path.

7. **Open Decision #16 (topic list) is a hard prerequisite, confirmed
   still entirely unbuilt.** `grep` for `match_stored_position` across the
   whole repo returns zero hits. Whatever calibration discipline
   `match_position_paper()` needed — two live bug-fix rounds, extensively
   documented in `position_papers.py`'s own comments (contrast anchors,
   `MIN_QUALIFY_MARGIN`, the standing-debate exclusions) — will be needed
   again here, from scratch, before any interception point can safely
   decide which questions are even candidates for this path.

### 6. Proposed rollout mechanism + minimal safe first connection step (proposal only — nothing here implemented this session)

Recommended order:

1. **Topic list (#16) + `match_stored_position()`**, calibrated with the
   same anchor/contrast/margin discipline already proven twice on
   `match_position_paper()`, rather than inventing a new matching approach.
2. **A first content-fidelity layer before anything serves live.** At
   minimum, wire `verify_verse_mention()` against generated position text
   (cheap, source-agnostic, already exists, currently unused here).
   Separately decide — explicitly, with Alex, not by default — whether a
   fuller groundedness check (a propositions-based analog of
   `RetrievalGrounding`) is a precondition or an acceptable fast-follow.
   Flag: CLAUDE.md's Settled Decision #4 HOLDS any probabilistic
   claim-support checker — a deterministic check (does the generated text's
   content trace back to the specific propositions it was given) is a
   different kind of thing than the banned probabilistic judge, but that
   line needs to be drawn on purpose here, not assumed by whoever builds
   this next.
3. **Decide the draft/approval question (§5 finding 2) explicitly**, one
   way or the other, before step 4 or 5 below.
4. **Minimal safe first connection: shadow mode, not a flag rollout.**
   Once (1) exists, `chat()` already has everything needed to also call
   `serve_position()` in a background thread alongside normal RAG
   generation — never instead of it — and log both outputs side by side
   (question, RAG answer, position answer, evidence, contributors)
   somewhere queryable, with nothing shown to any real user differently.
   This directly produces the real-question, real-evidence comparisons §4
   needs, at zero user-facing risk, before the two-level off-switch (5)
   is even built.
5. **Only after shadow mode has produced enough comparisons to judge
   quality**, promote to the async-path's proven two-level off-switch
   shape (env var mounts the code; a `serving_enabled`-style DB boolean is
   the seconds-reversible traffic dial) — reusing `async_answer_config`'s
   exact shape rather than inventing a new one.
6. **Route any new live-path DB access for this feature through
   `async_answers/db.py`'s pooled `Db` class**, not a new raw
   `psycopg2` connect-per-call pattern, to avoid adding unpooled
   connection pressure to the live request path (§5 finding 1).

**Open decisions this session adds to the standing list (not decided
here):** whether shadow-mode logging needs its own table or can live in
structured logging for a first pass; whether a deterministic groundedness
check is in-bounds under Decision #4's HELD probabilistic-checker ban;
whether draft positions may ever serve live unreviewed, or must wait for an
approval step. Everything from the prior diagnostic's own open-decisions
list (#13 dominance-threshold ownership, #14 refresh trigger, #15
replace-vs-version, #16 topic list) remains open and is now, per §5, a hard
prerequisite rather than a parallel-track concern.

## Groundedness check — diagnostic (2026-08-04, read-only)

Connection work (this doc's own §6) is paused; this section is scoped
narrowly to the groundedness-check gap named in §5 finding 3. Read-only —
no code, schema, or config changed. Every claim is either a direct
file:line read this session or an explicit inference, labeled as such.

### 1. The live RAG path's existing two-layer guard, in full

**Layer A — attribution-grounding guard (`chat.py:1106-1140`).** Decides
whether the ANSWER ITSELF is safe to show at all. Runs entirely
**pre-reveal** — inside the buffered-generation step, before
`_playback_events()` ever yields a token to the client (:1167). Two
independent arms, combined by `_has_ungrounded_credit()` (:1119-1128):

- **Declared-block arm** (`_ungrounded_reference_teachers`, chat.py:586-610)
  — reads the model's own self-reported `<reference_mentions>` `TEACHER:`
  lines, keeps only ones whose exact string also appears in the served
  prose (`find_occurrences`), drops biblical figures, resolves name→
  `source_id` (`resolve_alias_source_id`), and checks
  `_is_retrieval_grounded` (`reference_verifier.py:126-143`) — was this
  teacher's material retrieved AT ALL for this question (source-id OR
  author-name arm).
- **Prose-scan arm** (`ungrounded_prose_teachers`,
  `reference_verifier.py:576-604`) — independent of anything the model
  self-reported. Scans the served prose directly for (i) any of a finite,
  precomputed "corpus full personal name" universe
  (`build_name_universe()`, :452-475 — every source's canonical name +
  every alias_display, filtered to 2-3-token capitalized personal names),
  and (ii) names appearing in an explicit attribution construction
  ("According to X", "X taught", "X's commentary" — the `_ATTRIBUTION_RE`
  grammar, :514-557). This is what catches an **out-of-corpus invented
  name** the model never declared at all (the documented Warren
  Wiersbe/Ray Stedman/etc. class) — the declared-block arm cannot, because
  there is nothing in `<reference_mentions>` to read.
- **On failure of either arm:** regenerate ONCE with a hard
  `permitted_names` constraint appended to the system prompt
  (`_stream_answer(history, permitted_names=...)`, chat.py:1131 — the
  literal instruction text is at :552-562: "you may attribute a claim BY
  NAME ONLY to these teachers... Do NOT name, cite, or attribute any point
  to any other teacher"). If the SAME check still fails after that one
  regeneration → clean refusal (`_ATTRIBUTION_REFUSAL` boilerplate,
  `refused=True`, citations zeroed, :1130-1140). **Never surgically edits
  prose** — chat.py's own comment states the reason explicitly: "mangling
  risk" (:1106-1110). Fails CLOSED on any exception in this whole block
  (:1138-1140).

**Layer B — `verify_references()` (SP1 reference-pointer verifier,
`reference_verifier.py:665-722`, called at `chat.py:1144`).** A DIFFERENT
job from Layer A: Layer A decides whether to show the answer at all; Layer
B — which only ever runs on an answer Layer A already cleared — decides
which of the model's self-declared `<reference_mentions>` proposals earn a
**verified pointer** in the meta payload (the UI's citation-link
mechanism). It never blocks the answer and never edits the prose; a
mention that fails just gets no pointer. Four required guards per proposed
mention, in order (module docstring, :9-33):

1. **Presence** — the proposed string must literally appear in the served
   answer text (`find_occurrences`) — the model's own claimed position is
   never trusted.
2. **Resolution** — verse: `_parse_verse_or_range` (:220-267, reusing
   `backend/app/constants.py`'s `BOOK_MAP`) + a real `verses` table row for
   every endpoint (`verify_verse_mention`, :276-291 — a range fails whole
   if either endpoint is bad). Teacher: alias-key lookup in
   `source_aliases`, must not be the sentinel/unassigned row, must pass
   `is_source_servable()` (the Invariant 2 license/visibility gate), AND —
   stricter than the detection predicate above — `_link_source_retrieved`
   (:146-169): the resolved `source_id` must be among the sources actually
   **retrieved** for this question, source-id arm only (deliberately
   excluding the author-name arm here, to avoid granting a link to an
   unretrieved source B via a same-named author's homonym on a different
   retrieved source A — :146-163's own documented rationale).
3. **Biblical-figure backstop** — an independent short-circuit; a biblical
   figure never earns a teacher link regardless of what the alias table
   says.
4. **Overlap de-duplication** (`_deduplicate_overlapping_spans`,
   :607-662) — bookkeeping, not a validity guard; keeps the longer of two
   overlapping verified spans (e.g. a verse range vs. its own start verse).

Fails closed structurally throughout: any exception anywhere → empty list,
never a broken request (:717-722).

**What both layers demonstrably do NOT catch — confirmed by reading what
they actually check, not inferred:**

- **Neither layer checks claim SUBSTANCE, ever.** Both are pure
  EXISTENCE/MEMBERSHIP checks — was this name/source retrieved at all;
  does this verse reference resolve to a real row. A real, retrieved
  reference reattached in the served prose to support the WRONG point
  (the documented Leonard Ravenhill Philippians 4:8-9 case, CLAUDE.md
  Landmines) sails through both layers untouched: the teacher was
  retrieved, the verse exists, so every guard passes — the fabrication is
  in HOW the reference is used, which nothing here evaluates. This is the
  exact gap CLAUDE.md's Settled Decision #3 already names as accepted-
  permanent, not something this diagnostic is discovering fresh.
- **A claim invented from general theological/training-data knowledge,
  tied to no specific checkable name or verse, is invisible to both
  layers by construction** — there is no span for either guard to even
  examine (the Vlad Savchuk "Devil's Voice" class, Landmines — "remains
  confirmed but undetectable by any reference-grounding check by
  construction").
- **The prose-scan arm's Arm 2 (attribution-context extraction) is
  deliberately scoped to FULL personal names (2-3 tokens) only** — bare
  surnames are explicitly out of scope by design (:369-372's own
  documented rationale: false-denial risk on legitimate short forms like
  "Prince" for Derek Prince). A misattribution phrased only via a bare
  surname, never expanded to a full name anywhere in the same answer, is
  a genuine residual gap.
- **`verify_verse_mention()` checks existence only** — it does not check
  that the verse is invoked correctly, relevantly, or that nearby text
  accurately reflects that verse's content. Its own docstring at
  `verify_references()` (:679-681) states this outright: "Scripture is
  permitted from the model's own knowledge and does not depend on
  retrieval" — the RAG path deliberately does NOT require a cited verse to
  have come from retrieved material at all, only to be real.
- **Once a teacher clears retrieval-grounding, everything else attributed
  to them in that answer is unchecked for fidelity** — grounding answers
  "was this person's material retrieved," never "is what's attributed to
  them here an accurate paraphrase of what they actually said."

### 2. Reuse assessment — direct reuse vs. structural mismatch

**Directly reusable as-is, no RAG-path assumption baked in:**

- `verify_verse_mention()` / `_parse_verse_or_range()`
  (reference_verifier.py:220-291) — pure DB lookup against `verses`,
  zero dependency on chunks, retrieval, or anything RAG-specific.
- `is_biblical_figure()` — pure name check.
- `build_name_universe()` (:452-475) and the whole name-shape filter stack
  (`_looks_like_personal_full_name`, `_NAME_TOKEN_RE`,
  `_NON_PERSON_TOKENS`) — queries `sources`/`source_aliases` directly, no
  chunk/retrieval dependency.
- `find_occurrences()` / `_prose_name_present()` — pure string presence
  logic over whatever text is handed to it.
- `_extract_prose_attribution_names()` (Arm 2's regex, :514-557) — pure
  text-pattern matching over prose, no RAG dependency; directly relevant
  here since `CORPUS_PROMPT` (positions.py:455) explicitly instructs the
  model to "Attribute views to the teachers who actually hold them, by
  name" — the exact invented-attribution risk shape Arm 2 exists to catch.
- `resolve_alias_source_id()` — pure alias-table lookup.

**Structural mismatch — assumes something the source-blind path doesn't
have:**

- **`RetrievalGrounding` / `build_retrieval_grounding(chunks, db)`**
  (:52-123) is the central one. It is built FROM a `chunks` list
  (`document_id`, `author` fields) — the live retrieval output — and its
  constructor has nothing to consume on the position path, which never
  retrieves chunks at all (Invariant 12). **This is not a dead end,
  though** — see §3: `gather_evidence()`/`gather_evidence_corpus()`
  already return a strictly TIGHTER, cheaper analog for free, with no
  chunk-to-source JOIN query needed at check time the way
  `build_retrieval_grounding()` needs against `documents` (:106-108).
- **`_link_source_retrieved()` + `is_source_servable()` inside
  `verify_teacher_mention()`** — not wrong here, just REDUNDANT: step 3
  already built `LICENSE_GATE_SQL` directly into `gather_evidence()`/
  `gather_evidence_corpus()` (positions.py:548-551, :594-596, :652-653),
  so every `source_id` that could possibly appear as evidence on this path
  is license-cleared BEFORE the generator ever runs. Re-deriving
  servability at check time would be duplicate work solving an
  already-solved problem, not a missing capability.
- **`verify_teacher_mention()`'s alias-resolution machinery** — largely
  unnecessary here, for a different reason than servability: for
  `generate_position_text()`, there is only ONE legitimate teacher, and
  its name/`source_id` are already known, plain-string function
  parameters (`teacher_name`, `source_id`) — no alias lookup is needed to
  know what's permitted, only a scan for anything ELSE. For
  `generate_corpus_position_text()`, the permitted set is the `teacher`
  labels already attached to `attributed_evidence` — again plain strings
  in hand, zero DB round-trip required. The RAG path needs alias
  resolution because it discovers what's grounded only AFTER generation,
  by resolving names back to sources; the position path already KNOWS the
  permitted names BEFORE generation, because it chose the evidence.
- **`parse_reference_mentions()` / the `<reference_mentions>` block.**
  Neither `POSITION_PROMPT`/`TENSION_MODE_PROMPT` (positions.py:330-417)
  nor `CORPUS_PROMPT` (:446-461) instructs the model to emit any such
  self-report block — confirmed by reading both templates in full, no
  `<reference_mentions>` instruction anywhere. This exact parsing
  mechanism has nothing to parse on this path unless the prompts are
  changed to add one (a prompt-template edit with real Invariant 10
  provenance/fingerprint consequences — not a free reuse). **It also
  turns out not to be needed** — see §3: scanning the generated text
  directly makes the whole self-report/presence-crosscheck apparatus
  unnecessary here.

### 3. Does synthesizing from propositions (not raw source) change the problem?

**Yes — materially, for two distinct reasons, not one.**

**(i) The grounding candidate set is already a function parameter, not
something to re-derive.** `build_retrieval_grounding()` has to run a
`documents` JOIN query, after the fact, to map retrieved chunks'
`document_id`s to `source_id`s (:106-108). On the position path, the
caller (`write_position()`/`write_corpus_position()`) already HAS the
exact evidence list in hand as a Python list, with `source_id` (teacher
case: the one `source_id` parameter) or per-item `source_id` + `teacher`
(corpus case, `gather_evidence_corpus()`'s own return shape,
positions.py:664-679) already attached — building a grounding set costs a
`set()` comprehension over data already in memory, zero new query.

**(ii) The evidence itself is a small, closed, discrete set of exact known
strings — not a large, heterogeneous raw document — which changes what
kind of check is safe to build.** This distinction matters because a
structurally similar-sounding check was already tried and explicitly
rejected in this codebase, at a different stage: the Landmines entry "No
cheap check exists for the demonstrated fabrication class" records that a
similarity-based check (does a proposition's meaning match something in
its OWN SOURCE DOCUMENT) was built, run corpus-wide, and rejected —
"confirmed-accurate propositions routinely scored as extreme as or more
extreme than the one known real fabrication, so no cutoff separates
them." That failure is a property of **open-set semantic search against a
large, heterogeneous document** (thousands of words, many unrelated
ideas — lots of accidental near-matches to confuse any similarity cutoff),
not a property of "checking whether generated text traces to given
source material" in general.

At position-synthesis time the equivalent question is a **closed-set
membership problem over at most 15 known candidate strings**
(`MAX_EVIDENCE = 15`, positions.py:219 — the exact propositions
concatenated into `evidence_block`, :774/:807) — a fundamentally smaller
and more tractable search space. **This does NOT mean a similarity-score
threshold would now work where it didn't before** — the prior failure was
about similarity SCORING'S unreliability as a discriminator, a property
of the method, not of search-space size, and this diagnostic does not
walk that finding back. What the small closed set DOES make newly
tractable is a **non-semantic, exact, deterministic** check: does every
scripture reference the generated text cites also appear, verbatim (after
the same normalization `_parse_verse_or_range` already does), somewhere
in the ≤15 evidence propositions' own content strings. That's plain string
matching over a small enumerable set — no threshold, no embedding, no
scoring — and it is a **new** check with no analog on the RAG path, because
`verify_references()` deliberately does NOT require a cited verse to come
from retrieved material at all (§1's Layer B finding, "Scripture is
permitted from the model's own knowledge"). The position path could
require it, because unlike live retrieval, "the evidence" here is a small,
exact, already-decided set, not a loose top-K similarity pool.

**Scope limit, stated precisely so it isn't overclaimed:** this tractability
gain applies only to the REFERENCE-bearing slice of a claim (something with
a checkable Book:C:V span, or a checkable teacher name). It does nothing
for the general-substance-fidelity problem — whether a paraphrase's overall
meaning has quietly drifted from what its evidence actually says, with no
new name or reference attached to flag it. That remains exactly as hard
here as anywhere else in this product (see §6's residual).

### 4. Model-based judge — reaffirmed off the table

No option below proposes scoring an answer's faithfulness with an LLM call,
directly or indirectly (e.g. "ask Claude if this position is grounded in
its evidence"). CLAUDE.md's Settled Decision #4 HOLDS the probabilistic
claim-support checker pending measurement, and that shape has failed five
times on record (Open Decision #20). Every check proposed in §6 is a plain
Python membership/existence test against data already resolved before
generation (the evidence list) or against a small, static reference table
(`verses`) — the same character as the two guards already documented in
§1, deliberately, not by coincidence.

### 5. Existing deterministic building blocks and their real coverage

| Building block | What it actually checks | Coverage for this path |
|---|---|---|
| `verify_verse_mention()` (reference_verifier.py:276-291) | A cited verse/range resolves to a real `verses` row | Directly reusable, unmodified. Existence only — not usage correctness. |
| `build_name_universe()` + name-shape filters (:452-475, :429-449) | The finite set of known corpus personal full names | Directly reusable as the SEARCH space for a name scan; the pass/fail DECISION logic must differ from `verify_teacher_mention()` (see §2). |
| `_extract_prose_attribution_names()` (:514-557) | Names in explicit attribution constructions | Directly reusable, unmodified — same invented-name risk shape `CORPUS_PROMPT` creates. |
| `reference_grounding.find_reference_spans()` (Invariant 11, extraction-time) | A proposition's own reference against ITS OWN SOURCE DOCUMENT, before storage | **Different stage, different problem** — checks extraction fidelity to source text, already baked into `propositions.eligible`. Says nothing about whether a SYNTHESIZED position built from several eligible propositions stays faithful to THEM. Do not treat `eligible=true` propositions as making position text automatically safe — that conflates two different guarantees. |
| `closeness_check.py` / `citation_verifier_layers.py` (Invariant 11's three-layer arbiter) | Same — extraction-time closeness/citation-grounding, feeding `propositions.eligible` | Same distinction as above; not applicable to synthesis-stage checking. |
| **Book-name-map fragility, confirmed live this session** | — | `grep` for a literal `BOOK_MAP =` assignment finds it independently defined in at least `backend/app/constants.py` (the one `reference_verifier.py` uses) AND `scripts/ingest_bible.py`, on top of `reference_grounding.py`'s and `citation_verifier_layers.py`'s own independent reference-span finders (`find_reference_spans`, `find_layer1_candidates`/`find_bookless_chapter_verse_pairs`) — confirming the Landmines' "five independent hand-maintained copies" note is not stale. **Whichever reference-scanning code §6 reuses must be `backend/app/constants.py`'s `BOOK_MAP` via `reference_verifier.py`'s existing `_parse_verse_or_range`** (the one already live in the answer-verification context this new check sits beside) — not a new, sixth copy. |

### 6. Proposed minimal deterministic groundedness check (proposal only — not implemented this session)

Three checks, all pure membership/existence tests, no scoring, no model
call:

**Check 1 — teacher-name closure (misattribution).** Reusing
`build_name_universe()` + `_prose_name_present()` + name-shape filtering +
`_extract_prose_attribution_names()` verbatim, against the generated
position text:
- Teacher-scope (`generate_position_text` output): collect every full
  personal name present (Arm-1-style scan of the name universe) or
  attribution-extracted (Arm 2). PASS iff the only such name(s) are the
  ONE permitted `teacher_name` (or a biblical figure). Simpler than the
  RAG path's version by construction — there is exactly one legitimate
  name to check against, known before generation, not an open retrieved
  set discovered after.
- Corpus-scope (`generate_corpus_position_text` output): PASS iff every
  name found is a member of `{e["teacher"] for e in attributed_evidence}`
  (already in memory, zero query) or a biblical figure.
- No alias-resolution, servability, or retrieval-grounding DB round-trip
  needed for either case (§2) — pure in-memory set membership against the
  caller's own already-known permitted-name set.

**Check 2 — reference existence.** Scan the generated text directly for
`_parse_verse_or_range`-shaped spans (reusing `reference_verifier.py`'s
regex/`BOOK_MAP` machinery, not a new copy — §5). For each span found,
PASS iff `verify_verse_mention(db, raw)` returns True. No self-report
block is needed — see the note below.

**Check 3 — reference-in-evidence membership (new; no RAG-path analog).**
For the same spans found in Check 2, additionally require that the exact
reference string (after `_parse_verse_or_range`'s own normalization)
appears somewhere in the literal `content` of the evidence propositions
handed to the generator. PASS iff every cited reference in the output
also traces to at least one evidence proposition's own text.

**Why no self-report/presence-crosscheck apparatus is needed here, unlike
Layer B:** `parse_reference_mentions()` + the "Presence" guard exist on
the RAG path to reconcile what the model CLAIMED against what it actually
wrote, because the model's self-report is a separate, untrusted channel.
Checks 2-3 skip that entirely by extracting reference spans directly from
the served text itself — whatever the regex finds IS present in the text,
by construction, so there is nothing separate to cross-check. This is a
genuine simplification available here, not a corner cut.

**Failure handling — reusing the exact ordering already established, not
inventing a new one:**
- Any check failing → regenerate ONCE with a tightened instruction
  (explicitly re-stating the permitted name(s) verbatim / that only the
  given evidence's own references may be used — the same shape as
  `chat.py`'s `permitted_names` constraint injection, :552-562).
- Still failing after that one regeneration → **refuse to persist, not
  refuse to answer.** This is the one place the ordering must adapt, not
  just copy: on the RAG path a refusal costs one request. On this path,
  `_insert_position_version()` writing a bad row would serve that same
  bad row to every future identical question indefinitely
  (`serve_position.py`'s own "Lifecycle," :6-11) — so refusing here means
  never calling `_insert_position_version()` at all, returning a new
  result status (e.g. `"refused_groundedness"`, alongside the existing
  `"refused_floor"`/`"errored"` vocabulary `write_position()`/
  `write_corpus_position()` already use), and letting the caller fall
  through to the SAME honest-empty messaging the evidence-floor refusal
  already produces — matching `serve_position.py`'s own Rule 1 ("thin vs.
  absent is never exposed") extended to "refused-for-groundedness vs.
  absent," so no reader-facing "quality" language leaks out.
- **Never surgically edit the generated prose** — same explicit reason
  `chat.py` already gives for this rule ("mangling risk," :1106-1110);
  no reason to relitigate it here.
- **Placement:** inside `write_position()`/`write_corpus_position()`,
  immediately after `generate_position_text()`/
  `generate_corpus_position_text()` returns and BEFORE
  `_insert_position_version()` is called — covers `serve_position()`'s
  cold-generate path AND `rebuild_position()`'s rebuild path for free
  (both funnel through these same two writer functions), the same
  centralization the existing evidence-floor check already uses rather
  than duplicating logic per caller.
- **Fail CLOSED on the check's own failure** (e.g. a transient DB error
  inside `verify_verse_mention`) — treat as a check failure, not a pass,
  matching `RetrievalGrounding.established=False`'s and
  `build_name_universe()`'s existing fail-closed discipline.

**What this will NOT catch — stated plainly, since this residual is what
Alex has to decide to accept:**

- **The Ravenhill-class fabrication**: a genuine evidence reference,
  reattached in the generated prose to support a different point than the
  evidence actually supports. Checks 2 and 3 both PASS (the verse exists,
  and it genuinely came from the evidence) — the fabrication is in HOW
  it's used, which nothing proposed here (or on the RAG path) evaluates
  deterministically.
- **General substance drift** — a paraphrase that quietly overstates,
  sharpens, or softens what its evidence actually says, without adding a
  new name or a new checkable reference. The largest, most dangerous
  residual category, and exactly CLAUDE.md's Settled Decision #3
  already-accepted-as-permanent gap ("inventing the substance is not
  [solvable], at any timeline"). Invisible to every check proposed here,
  exactly as it is on the RAG path today — this proposal does not narrow
  that gap, only closes this path's version of the two slices Decision #3
  already scopes as solvable.
- **Bare-surname-only misattribution** — matches the RAG path's own
  documented scope limit (§1), same false-denial-risk tradeoff, not
  reopened here.
- **General theological error/overreach with no specific attributable
  name or verse attached at all** (the Savchuk "Devil's Voice" class) —
  structurally undetectable by any reference/name-based check, on this
  path exactly as on the RAG path.

**Framing this residual against what's already decided, so it reads as a
scoped closure rather than a new, arbitrary line:** this proposal closes
this path's version of the same two slices CLAUDE.md Decision #3 already
names as deterministically solvable — misattribution (Check 1) and
fabricated/unsupported references (Checks 2-3) — using the same
existence/membership philosophy the RAG path's own guards already use. It
leaves open the exact same substance-fabrication slice already accepted as
permanently open everywhere else in this product. That is a like-for-like
parity with the live RAG path's own accepted risk posture, not a lower bar
being proposed for the new path.

## Design pressure test — diagnostic (2026-08-04, read-only, live DB queried)

Adversarial review of a not-yet-built design (this section's own preamble,
verbatim from the request): (1) stored positions are evidence, never
served answers; (2) answers synthesize fresh at question time, written
from the stored position rather than raw source text; (3) the
deterministic groundedness check (§ above) runs at both hops, second hop
treated as load-bearing; (4) an invalidated position is never
auto-rebuilt, falls back to the live path, rebuilds are deliberate and
batched. Nothing here is implemented; every finding below is either a live
`SELECT` this session (queried via `positions.db_params()` against
`SUPABASE_DB_URL`, read-only, `set_session(readonly=True)`) or a direct
code/migration read, cited by file:line. Findings are ranked FATAL/NEAR-
FATAL → SIGNIFICANT → OPERATIONAL. An alternative is proposed for every
FATAL/NEAR-FATAL finding, per the request.

### FATAL / NEAR-FATAL

**1. The "second hop is load-bearing" framing is backwards — hop 2
structurally cannot see hop-1 drift, and hop-1 drift is real, live, and
already flowing downstream today.**

The design's own logic: hop 1 (propositions → position) is a restatement;
hop 2 (position → answer) is a restatement of THAT restatement; the
groundedness check runs at both hops, and hop 2 — the one actually facing
the reader — is "treated as the load-bearing one." This gets the causality
backwards. Hop 2's check (§ above, Checks 1-3) can only ever verify "does
the answer trace to the STORED POSITION" — it has no access to, and no
way to re-derive, the original propositions once the position exists as
its own row. If hop 1 already drifted from its propositions, hop 2's
check certifies the answer against the DRIFTED ground truth and reports
success. **A hop-2 check, however good, provides zero protection against
error introduced in hop 1** — it can only bound NEW drift introduced
during hop 2 itself. Calling hop 2 "load-bearing" asks the weaker,
downstream check to do the job only a hop-1-facing check can do.

This is not theoretical. Two pieces of evidence, one already on record and
one found live this session:

- **Already on record:** `positions.py`'s own comments document a
  CONFIRMED case of exactly this failure already happening at hop 1 — the
  original `RESOLUTION_INSTRUCTION_ORDINARY` prompt, tested against real
  Derek Prince evidence on Calvinism/predestination, "manufacture[d] a
  one-sided resolution the teacher's own statements do not actually
  assert: 'Prince resolves the tension between predestination and free
  will by appealing to...' — stitching real statements into an
  over-resolved conclusion" (:361-384). This is confirmed hop-1 content
  drift, from real evidence, in this exact module — the fix
  (`RESOLUTION_INSTRUCTION_TENSION`) is topic-specific and does not
  generalize; nothing establishes every topic is safe from the same
  failure shape.
- **Found live this session:** the corpus position `holiness and personal
  purity` (id `0c60ca7a-d564-4ec2-b842-a9db38805361`, `status='draft'`,
  `is_current=true`) draws evidence from proposition
  `0892b75d-1c9f-4a65-a47e-768c1c5c1803` — `eligible=true`, live-confirmed
  — whose full text is: *"The author emphasizes the importance of living a
  life of purity and holiness, and that this is essential for believers to
  be effective witnesses for Christ, as stated in Philippians 4:8-9, where
  Paul encourages believers to think on things that are true, honest,
  just, and of good report."* This is CLAUDE.md's own documented,
  confirmed fabrication case — "Leonard Ravenhill's Philippians 4:8-9
  citation (2026-07-28, a real reference grafted onto the wrong point in
  the same sermon)" — still live, still `eligible=true`, and **already
  selected as trusted evidence for a real, currently-`is_current`
  position.** The stored position's own rendered text includes the phrase
  "essential for believers to be effective witnesses for Christ" —
  traceable directly to this exact proposition's substance — while the
  specific fabricated Philippians 4:8-9 citation itself did not carry
  forward into the rendered text. **None of the proposed Checks 1-3 would
  ever catch this**, at either hop: there is no invented teacher name (the
  substance genuinely came from Ravenhill), and by the time it reaches the
  stored position, there is no invented reference to check either — the
  verse got silently dropped, not the substance. The drift already
  happened, upstream of both checks, and is already resting in a live row
  a future answer-writing hop would treat as ground truth.

**Why this is fatal to the design as framed, not just a gap:** the whole
point of "load-bearing" is where to concentrate trust. Concentrating it at
hop 2 means an operator who verifies hop 2 is thorough could reasonably
believe the pipeline is safe — while hop-1 drift, which hop 2 cannot see
by construction, keeps flowing through untouched.

**Proposed alternative:** stop ranking the hops. Hop 1 is the one that
matters MORE, not less, because its output is reused indefinitely across
every future hop-2 call on that topic (the amortization the whole design
is built around) — a single hop-1 error is not a one-off, it is a
standing liability for as long as the position stays current. Concretely:
(a) treat hop 1's deterministic check as the primary gate, exactly as
already proposed, but stop treating hop 2's check as a stronger backstop
than it can be; (b) because Checks 1-3 cannot catch substance drift at
either hop (§ above, explicitly disclosed), hop 1 specifically — not hop
2 — is where a cheap, targeted human spot-check pays for itself: a
position is written once and read by an unbounded number of future
question-answer hops, so a few minutes of review per position is a much
better trade than the same review effort spent per-answer ever could be.
This does not reopen Settled Decision #1 (no human review on the SERVING
path) — the serving path (hop 2, question time) stays unreviewed exactly
as decided; the review would sit on the BATCH, pre-question hop-1 output,
which decision #1's own text already anticipates as a different thing
("a review model can't enumerate hundreds of thousands of questions in
advance" — a topic list is not hundreds of thousands of questions).

**2. Invalidation is not computable from what's recorded today, and even
built, the design as stated cannot catch the single most likely real-world
staleness cause.**

*Deletion is already handled — this part works.* `position_evidence.
proposition_id REFERENCES propositions (id) ON DELETE RESTRICT` (migration
073:84), deliberately, per its own comment: "if a proposition a position
depends on is ever deleted, that delete must fail loudly and force a
human decision about the position, never silently orphan" (:52-56).
Confirmed this is not decorative: `store_propositions()`'s default path
(`clear_existing=True`) runs `DELETE FROM propositions WHERE document_id =
%s` before every re-insert (propositions.py:1086, :996-1011) — exactly the
statement a document re-extraction/correction pass uses — and RESTRICT
would hard-fail that DELETE the moment any of that document's propositions
are cited as evidence. So a re-EXTRACTION of a contributing document
cannot silently invalidate a position; it cannot proceed at all without a
human resolving the conflict first. Good, and already built.

*But two other real, existing mutation paths are invisible to any
row-existence check, and both are live tools in this repo, not
hypotheticals:*

- **`scripts/rewrite_flagged_statement.py`** — a real, Alex-authorized,
  currently-existing correction tool whose only write, anywhere in the
  file, is `UPDATE propositions SET content = %s, embedding = %s::vector
  WHERE id = %s` (:26, :268) — same row `id`, content changed in place.
  Confirmed by grep: zero reference to `position_evidence` or `positions`
  anywhere in this file. This is the exact tool that would be reached for
  to correct something like finding 1's live Ravenhill fabrication — and
  running it produces no FK violation (no DELETE happens) and no signal
  to any position depending on that row that its cited content just
  changed underneath it.
- **`scripts/backfill_proposition_eligibility.py`** — `UPDATE propositions
  SET eligible = true WHERE id = ANY(%s::uuid[])` (:76), an UPDATE, not a
  DELETE — a re-run after a classifier fix could flip an already-cited
  proposition's eligibility in either direction with the same silence.

`position_evidence` records only `(position_id, proposition_id)` —
confirmed, `_insert_position_version()`'s INSERT (positions.py:1000-1004)
— no content snapshot, no content hash, no eligibility-at-write-time flag,
no candidate-pool size, no `corpus_version()`/eligible-set snapshot.
**"Did the material behind this position change" is answerable today only
in the narrow existence sense RESTRICT already enforces for free — content
mutation and eligibility mutation are both real, both already possible via
tools already in this repo, and both currently invisible.** Building
change-detection for these would require genuinely new record-keeping (a
content hash or full snapshot per `position_evidence` row, checked against
current state) — a real, unscoped build cost the design does not currently
account for.

*Now the sharper problem — even with that new record-keeping built,
invalidation-on-change cannot see invalidation-on-ADDITION, and this is
not hypothetical either:* live-queried this session — **517 propositions
were added to the corpus on 2026-08-03, all AFTER both live corpus
positions (`holiness and personal purity`, `can a believer lose their
salvation`) were created on 2026-08-01 14:28.** 29 more from Derek Prince
himself (already the position's dominant-adjacent contributor), plus new
material from Doug Kreighbaum (whose eligible-proposition count nearly
DOUBLED since, 98 new eligible rows against a prior total of 199), F.F.
Bosworth, Daniel Kolenda, and Vlad Savchuk — all `eligible=true`. None of
this touches a SINGLE existing `position_evidence` row for either
position — by definition, since these are new rows, not edits to old
ones. **A change-detection invalidation rule, however well built, cannot
fire on this, structurally** — nothing about the cited evidence changed;
what's missing is different, newer evidence that was never gathered. Design
point (d)'s exact hypothetical (Prince's material landing and inverting a
topic's balance) is not a future risk to plan for — the shape of it has
already happened, twice over (once historically, satisfying the corpus-ban
precondition per CLAUDE.md Invariant 13 — Prince now has 5,178 total/3,538
eligible propositions across 496 documents, confirmed live, ~46% of the
whole corpus's proposition volume — and again this week, per the 517-row
addition above), and nothing in the stated design would ever notice either
event for an already-built position.

**Proposed alternative:** don't design invalidation as a reactive,
per-row change-detection trigger — design it as a periodic re-gather-and-
diff sweep, which the design's own "rebuilds are triggered deliberately,
in batches" language already implies operationally. Concretely: on a
schedule (or triggered by a completed backfill run, which is already an
identifiable event in this codebase), re-run `gather_evidence()`/
`gather_evidence_corpus()` for every stored topic and diff the FRESH
result against the stored `position_evidence` set — new dominant
contributor, evidence count changed materially, or a `DOMINANCE_THRESHOLD`
crossing that would flip teacher-scope ↔ corpus-scope all become
detectable uniformly, whether the underlying cause was a changed row or an
added one. This also sidesteps needing new hash/snapshot record-keeping
for the mutation case, since a full re-gather naturally reflects both
current content AND current membership without having to separately track
either.

**3. No concurrency protection and no failure memory — a race crashes,
and a structurally-hard topic pays full cost on every single ask,
forever, invisibly.**

Confirmed by grep: zero locking, advisory-lock, or single-flight
mechanism anywhere in `positions.py`/`serve_position.py` — unlike
`async_answers/jobs.py`'s already-built, already-proven "idempotent by
idempotency_key; single-flight + reuse" mechanism sitting elsewhere in
this exact codebase, unused here. `positions_current_lineage_idx`
(migration 077:109-114) is a real UNIQUE INDEX `WHERE is_current` — so two
concurrent first-askers of the same brand-new topic, both cold-generating,
both reaching `_insert_position_version()` (positions.py:933-1021) with
`supersedes=None`, will have their SECOND commit hit a Postgres unique-
violation. Confirmed by reading the function: the `try/except` there only
rolls back and RE-RAISES (:1006-1008) — and `write_position()`/
`write_corpus_position()` do not wrap this call in their own handling
(only the LLM call is guarded, for `PositionGenerationFailed`). **The
loser of a real concurrent race gets an unhandled exception, not a
graceful "someone else just wrote this, re-read it" recovery.**

Separately: `serve_position()` has no memory of a prior refusal. Combined
with finding 1's evidence that certain topics are STRUCTURALLY hard for
this exact prompt to stay within evidence on (the documented Calvinism/
predestination over-resolution bug), a topic whose groundedness check
fails repeatably would pay full cost — cold generation, one regeneration,
two groundedness-check passes, at BOTH hops if built as designed — for
EVERY single asker, forever, with zero backoff and zero visibility (no
table or log anywhere records a refusal pattern, unlike `answer_jobs`'
`outcome`/`last_error` tracking in the async-answer subsystem, an
existing precedent this design doesn't reuse).

**Proposed alternative:** (a) catch the unique-violation specifically at
`_insert_position_version()`'s call sites and re-read-and-serve the
winner's row instead of propagating the exception — a few lines, reusing
`lookup_current_position()` already in hand; (b) persist a minimal
negative-result marker (even a lightweight row with a retry-after, not a
full queue) so a structurally-hard topic's repeat cost is paid once per
interval, not once per asker.

### SIGNIFICANT

**4. "Falls back to the existing live path" names something that doesn't
exist as designed, and is 100% silent under either reading.**

`grep`, live: the phrase "can make mistakes" / "Please let us know if you
see any" appears exactly once in the whole codebase — as a NEGATIVE
instruction inside `position_papers.py`'s voice prompt, telling the model
NOT to add it (:602), on the grounds that it "belongs to a different,
unrelated part of the product." That different part is PLAN.md's own,
already-designed **third answer source**: "(c) Machine-generated live
fallback — own voice permitted, disclaimer required... Built from vetted
propositions only, never raw source text... every such answer MUST carry
the exact disclaimer" (PLAN.md:356, :358). **This tier was never built —
the disclaimer is rendered nowhere in `chat.py`, confirmed by the same
grep.** `chat.py`'s actual, only, currently-shipping live path is grounded
in retrieved CHUNKS — raw source text (`match_chunks`/`search_chunks_fts`,
chat.py:287-330) — a materially different, architecturally unrelated
mechanism from the propositions-only, disclaimer-bearing fallback PLAN.md
already specified for exactly this situation ("when no position exists").

So "falls back to the existing live path" can only mean chat.py's real
RAG-over-chunks path — which was never designed as a documented, lower
tier relative to positions; it is simply the entire product as it exists
today, predating the position-layer project. Falling back to it is
**completely silent** (no disclaimer, no signal of any kind distinguishing
a position-derived answer from a fallback one) under either reading, and
under the "falls back to chat.py's real RAG path" reading specifically,
it isn't even clearly a downgrade — chat.py's chunk-grounded synthesis is
arguably RICHER than a proposition-compressed position (no compression
loss), so "quality tier" is not an established fact here, just an
assumption the design takes on without deciding which fallback is
actually meant.

**5. Settled-decision interactions — one point genuinely improved, three
new or relocated risks.**

- **Decision #1 (fresh synthesis, no stored/reviewed answers) — genuinely
  improved by this redesign, not just technically complied with.** Framing
  the position as evidence and the reader-facing text as a fresh
  per-question write is structurally the same shape chat.py's live path
  already uses (fixed evidence → fresh synthesis shaped to the actual
  question) — closer to "retrieved chunks are evidence" than to "stored
  answers are served." This is real progress over what Step 4's own
  diagnostic analyzed (a stored row served verbatim). **Caveat, to verify
  once built, not assumed:** "written from the stored position" could
  still degrade in practice to a light rewrite of the same fixed paragraph
  for every question on a topic, given how fully the stored position text
  already reads as a finished answer (confirmed live — see the two
  position texts pulled above, both already flowing, complete prose, not
  bullet-style evidence). If that happens, Decision #1's SPIRIT (failure
  mode #3 — generic, interchangeable-feeling answers) is violated even
  while its letter is satisfied. Worth a concrete test once built: ask
  several differently-phrased questions on the same stored topic and
  confirm the answers genuinely differ in shape and emphasis, not just in
  a few swapped words.
- **Decision #9 (house view / teacher view never blended) — a genuinely
  NEW risk this design introduces, not previously present.** Every live
  stored position explicitly names its teacher(s) in-text — confirmed
  live: "Derek Prince teaches...", "Murray clarifies...", "Prince
  similarly teaches..." are the position's own literal opening words. A
  "shape it to how the user asked" rewrite pass, done carelessly, is
  exactly the kind of transformation that can drop or soften attribution
  language while preserving content — producing a response that reads as
  Rhemata's own settled assertion rather than a reported teacher view,
  the precise blend Decision #9 forbids. **None of the proposed Checks
  1-3 catch this** — Check 1 verifies the RIGHT teacher is named if a
  teacher is named at all, not that a teacher is named. This needs its
  own explicit check if hop 2 is built (e.g.: for a teacher-scope answer,
  does the served text contain at least one grounded attribution
  construction at all — reusing `_extract_prose_attribution_names()`'s
  detection machinery for confirmation rather than exclusion).
- **Corpus-scope ban / backfill precondition — reconfirmed live, no
  issue.** Derek Prince: 5,178 total propositions / 3,538 eligible across
  496 documents, live-queried this session — the precondition CLAUDE.md
  Invariant 13 already records as satisfying the 2026-08-01 lift stands,
  unregressed.
- **Draft/approved status — the risk is relocated, not removed.** Design
  point 2 has the answer-writing hop treat the stored position's content
  as ground truth unconditionally, regardless of its (permanently
  `'draft'`, per Step 4's own finding) status. This is compliant with
  Decision #1 (no review gate required) but carries forward exactly the
  same unreviewed-content risk Step 4 already flagged — just one hop
  removed from the reader instead of zero.
- **No-teacher-taxonomy rule — compliant at the DATA layer, at risk in
  the PROSE layer.** `contributor_breakdown_from_db()` (positions.py:
  721-751) always re-derives live from `position_evidence` — genuinely
  not a stored taxonomy, confirmed. But the position's rendered TEXT
  (which finding 2 shows can go stale relative to newly-landed material)
  is frozen prose, not a live re-derivation — a stale position's own
  wording ("the teachers agree that...", naming specific contributors
  in a specific balance) can function AS an implicit taxonomy snapshot in
  effect, even though the underlying schema was deliberately built (migration
  076) to prevent exactly that. The data model avoids the mistake; the
  prose can still make it.

### OPERATIONAL

**6. Cost and latency are a real trade, not a clean win, and the DB-
architecture gap Step 4 already flagged is paid twice.** Two sequential
LLM-authored hops before a cold topic's first reveal (worst case, with one
regeneration at each hop per the proposed groundedness-check ordering:
four LLM calls plus two rounds of deterministic checking) versus the live
path's one hop, worst case two calls. The amortized-cost story is real —
every subsequent asker of an already-built topic pays nothing — but the
FIRST asker of any cold topic pays a materially worse latency tax than
today, at exactly the moment (a new or unusual question) an impression
matters most. Step 4's own diagnostic (§5 finding 1, this doc) already
flagged that `positions.py`/`serve_position.py`'s raw-`psycopg2`,
connection-per-call architecture doesn't match `chat.py`'s Supabase-REST-
only world; a two-hop design pays that mismatch's connection/latency
overhead twice (evidence-gather + persist for hop 1, evidence-read +
answer-write for hop 2) rather than once.

**7. A simpler alternative exists that keeps most of the safety benefit
with one hop, not two.** Keep design point 1 (positions as evidence
documents, never served directly) — that part is sound and is real
progress, per finding 5's first bullet. But instead of building a SECOND,
parallel LLM-authored restatement hop with its own new groundedness check,
let a matched position's underlying propositions feed `chat.py`'s
ALREADY-BUILT, ALREADY-TESTED single hop — inject them into the same
context-assembly + `_stream_answer()` + attribution-grounding +
`verify_references()` pipeline the live RAG path already runs, as
priority evidence alongside or instead of retrieved chunks. This keeps
the total count of LLM-authored restatement hops at ONE, matching today's
live path exactly, and reuses the one groundedness mechanism this codebase
has already built, tested, and hardened over multiple real bug-fix rounds
— rather than asking a brand-new second check to do double duty at a
second hop it cannot actually see past (finding 1). The cost: it gives up
some of the cross-question consistency a genuinely stabilized position
paragraph would provide. That's a real but not a proven loss — PLAN.md's
own deferral note already discloses this exact benefit was never measured
("stored answers are the only identified change that helps latency AND
concurrency together, and its payoff depends on question-overlap rates
that have never been measured," PLAN.md:153) — so trading an unmeasured
benefit for the removal of an entire, currently-unguarded restatement hop
is a defensible trade, not a sacrifice of something proven.

## Fabricated-proposition remediation — diagnostic (2026-08-04, read-only, live DB queried)

Scoped narrowly, per this session's own instruction: the one live
fabrication instance the design pressure test surfaced (finding 1, above),
not the position-layer design work itself. Every fact below is a live
`SELECT` this session or a direct code read, cited precisely. No write
executed — this is the report requested before any action.

### 1. Live state of proposition `0892b75d-1c9f-4a65-a47e-768c1c5c1803`

Re-confirmed live, unchanged since the design pressure test found it:
`eligible=true`, `prompt_fingerprint=None`, `model=None` (a legacy,
pre-Invariant-10 row — `prompt_version='legacy_unknown'`, `created_at`
2026-06-29, before the 2026-07-29 bypass-proofing fix). Source document:
*"Paul's Passion, Preaching, and Praying" by Leonard Ravenhill*
(`document_id c19ad18c-ea97-4841-8fa0-e60afc273521`).

**Every stored position or served surface its substance currently
reaches — exactly one:** the `position_evidence` row linking it to
`holiness and personal purity` (`0c60ca7a-d564-4ec2-b842-a9db38805361`,
corpus-scope, `status='draft'`, `is_current=true`). Confirmed by direct
query — no other position references this proposition ID, and
`proposition_chunks` (migration 074's chunk-linkage table) has zero rows
for it (a legacy row that predates that table). Per the design pressure
test's own finding, this position is otherwise INERT — PLAN.md's own
live-verified note confirms `backend/app` reads nothing from the
`positions` table today, so the blast radius stops at this one stored
row; no live chat surface has ever served it to a reader.

### 2. Is this one bad row, or one of a set never actually cleared?

CLAUDE.md's Landmines record **three** confirmed fabrication cases, not
one — all found the same way ("direct full-source reading," not by any
automated scanner): Carter Conlon's Matthew 7:21-23 addition (2026-07-24),
Leonard Ravenhill's Philippians 4:8-9 citation (2026-07-28, the one
above), and Vlad Savchuk's "Devil's Voice" invented scriptural-authority
claim (undated precisely, "remains confirmed but undetectable by any
reference-grounding check by construction"). Located all three live this
session:

| Case | Proposition ID | Live `eligible` | Position evidence? |
|---|---|---|---|
| Ravenhill / Phil 4:8-9 | `0892b75d-1c9f-4a65-a47e-768c1c5c1803` | **true** | Yes — `holiness and personal purity` |
| Conlon / Matthew 7:21-23 | `18783354-931f-4244-bfe3-f47ce185b3ba` | **true** | No |
| Savchuk / "Devil's Voice" (candidate) | `23d846db-66de-4cc6-8308-138877fd3772` | **true** | No |

**All three are still `eligible=true` today — none was ever marked
ineligible, rewritten, or removed.** This is a set that was documented and
never actually acted on, not one isolated miss. The Savchuk row is a
strong CONTENT match, not a confirmed-identical ID: from the document
CLAUDE.md names ("How to Spot the Devil's Voice in Your Head",
`document_id 6c55bec3-a8ff-45ee-8ccf-5afb862a91a8`, 7 propositions, all
`eligible=true`), one reads *"The enemy's voice can be discerned by its
accent... as stated in the scripture"* — a vague scriptural-authority
claim with no actual chapter:verse, matching the documented description
exactly ("no actual chapter:verse to check"). No dedicated audit doc names
its exact proposition ID (searched `docs/audits/` for all three cases by
name — `corpus_quality_report_2026-07-24.md` and
`statement_recheck_closeness_citation_2026-07-28.md` are the two
candidate reports and neither calls out these specific cases; they are
statistical/structural reports, not individual-finding logs), so this
identification is confident on content but not cross-referenced against an
original ID. **None of the three sits in any automated "flagged" queue —
confirmed by why they were never caught: each already passes BOTH
`closeness_check` and `reference_grounding`'s citation-existence check**
(the citations are real and resolve; the defect is pairing a real
citation with the wrong claim, or — for Savchuk — asserting scriptural
backing with no citation to check at all). This is exactly the corpus-wide
gap CLAUDE.md's Landmines already names ("No cheap check exists for the
demonstrated fabrication class") — these three are its only three known
live instances, still unresolved.

### 3. Correct remedy — precedent assessment

Read `scripts/rewrite_flagged_statement.py` in full (not just its
docstring, as in the prior session). Its own docstring already rules out
two alternatives, with reasons on record: delete-and-regenerate ("would
delete and non-deterministically regenerate every sibling proposition in
a flagged statement's document") and reference-stripping ("leaves
grammatically broken text and removes evidence rather than restoring
faithfulness"). Its chosen mechanism — LLM-drafted single-statement
correction, verified, then a single-row `UPDATE propositions SET content
= %s, embedding = %s::vector ... WHERE id = %s` (:26, :268-278), stamped
with real Invariant-10 provenance (`prompt_version='rewrite_v1'`) — is the
established precedent for correcting a confirmed-bad row while preserving
whatever is genuinely salvageable in it, and it is directly reusable
machinery: single-row UPDATE, retry-with-note pattern, `dry_run=True` by
default (never reaches the UPDATE unless explicitly turned off, :335-337).

**But its automated verification gate does not cover this defect class,
and using it here is not simply "run the existing tool."** `passes_both()`
(:241-243) only checks `closeness_verdict == "PASS"` and `citation_verdict
in ("pass", "no_references")` — the SAME two checks that already let all
three of these rows through as `eligible=true` in the first place. Its
`build_defect_description()` (:143-164) only knows two defect shapes —
"reference doesn't exist in the source" and "wording too close to the
source" — **neither describes "a real reference attached to the wrong
claim," which is what all three of these actually are.** Feeding it
`citation_fail=False, closeness_fail=False` (both true today) would
produce an EMPTY defect description, telling the correction LLM nothing
to fix. Using this tool correctly here requires a small, deliberate
adaptation — either a new defect-description parameter for this class, or
driving `call_rewrite_llm()` directly with a hand-written defect
description — and, because the automated gate cannot detect mispairing
either way, **a human read of the redraft against the actual source
document is required to confirm the fix is real**, exactly as the
original detection method was manual. This is a real but small gap, not a
reason to invent a different approach — the tool's plumbing (safe
single-row write, provenance stamping, retry, dry-run-by-default) is
still the right foundation; only its defect vocabulary and its trust that
`passes_both()` alone certifies correctness don't extend to this case.

**Deletion is not currently a live option regardless of preference** —
worth stating precisely, not just deprioritizing: `position_evidence.
proposition_id REFERENCES propositions (id) ON DELETE RESTRICT`
(migration 073:84) would hard-fail a `DELETE` on this exact row for as
long as `holiness and personal purity`'s `position_evidence` row still
references it (§4). Marking-ineligible and rewriting both remain
available regardless; delete does not, without first resolving §4.

**Marking `eligible = false` is the one unambiguous, zero-new-code,
fully-precedented action available right now.** Same UPDATE shape
`backfill_proposition_eligibility.py` already runs
(`UPDATE propositions SET eligible = true WHERE id = ANY(%s::uuid[])`,
:76 — the same statement with `false` and these three IDs). Confirmed
this session, by grep across `backend/`/`scripts/`, that **nothing outside
the position-generation evidence-gathering path reads
`propositions.eligible` at all** — `chat.py`'s live RAG surface is
`chunks`-grounded, never touches `propositions`. Flipping these three rows
to `eligible=false` has ZERO effect on anything a real user can see today,
and immediately removes all three from every future `gather_evidence()`/
`gather_evidence_corpus()` call, cold-generate or rebuild. It does not fix
the row's content (still sitting there, mispaired, for anyone who queries
`propositions` directly) and does not retroactively touch the
`holiness and personal purity` position already built from it — that's §4.

### 4. What happens to the consuming position

**Nothing today automatically touches it — confirmed, no mechanism exists
to detect or react to an eligibility flip.** No trigger connects
`propositions.eligible` to `position_evidence` (checked live: no
`CREATE TRIGGER` referencing either table exists in any migration).
Flipping `eligible=false` alone leaves `holiness and personal purity`
exactly as it is — `is_current=true`, `status='draft'`, its stored prose
still containing the substance drawn from the fabricated pairing, its
`position_evidence` row still pointing at the (now ineligible, still
existing) proposition.

**A rebuild mechanism does already exist, is already built, and is
already tested — `rebuild_position()` (serve_position.py:379-451),
proven live by `prove_serving_path.py` Case 8.** It re-gathers evidence
fresh (so a corrected eligible-set is picked up automatically — no new
code needed there), writes a NEW version (v2) via the same
`_insert_position_version()` transaction that flips the prior version's
`is_current` to `false` in the same commit (positions.py:980-985), and
keeps the old row rather than overwriting it — matching this project's
"an answer a user already saw stays exactly as it was" versioning rule,
moot here specifically because this position was never served to anyone
(§1). This is exactly the "rebuild deliberately, in batches" mechanism
the paused design's own point 4 describes — it already works; what's
missing (design pressure test, finding 2) is only automatic invalidation-
TRIGGERING, not the rebuild action itself.

**One small, optional judgment call, not a blocker:** `rebuild_position()`
leaves the superseded v1 row's `status` at whatever it already was
(`'draft'`) — it does not set it to `'retracted'`. Since v1 was never
served to a real user and did draw on confirmed-fabricated-adjacent
content, explicitly setting it to `'retracted'` after the rebuild (a
one-line `UPDATE`, not a mechanism gap) would leave a more honest audit
trail than silently-superseded `'draft'` — functionally identical either
way (`is_current=false` already excludes it from ever being looked up
again, with or without `'retracted'`), so this is cosmetic/record-keeping
preference, not a correctness question.

### Proposed action, pending approval

**Unambiguous, precedent exists, zero new code — ready to execute on
approval:**
1. `UPDATE propositions SET eligible = false WHERE id IN
   ('0892b75d-1c9f-4a65-a47e-768c1c5c1803',
   '18783354-931f-4244-bfe3-f47ce185b3ba',
   '23d846db-66de-4cc6-8308-138877fd3772')` — same shape as
   `backfill_proposition_eligibility.py`'s existing UPDATE, zero live-user
   effect (confirmed, §3), immediately protects every future position
   build/rebuild from all three. Runs as a **Database write** session,
   plain script, per the Session Routing table's hard rule — not this
   session, and not the harness.
2. Immediately follow with `rebuild_position()` for `holiness and personal
   purity` (the only one of the three currently consumed) — already
   built, already tested, no new code — producing a v2 that no longer
   draws on the fabricated pairing, in the same database-write session as
   step 1.

**Needs a decision, not a mechanical run — surfaced for you, not decided
here:**
3. Whether to also REWRITE the three rows' content (preserving genuine
   salvageable substance) rather than leaving them permanently
   `eligible=false` and unfixed in the table — precedent and machinery
   exist (`rewrite_flagged_statement.py`), but it needs a hand-written
   defect description for this defect class and a human read of each
   redraft against its real source document before trusting it (§3) —
   not a same-session mechanical action.
4. Whether the Savchuk candidate row should be treated as confirmed
   before acting on it, given its ID isn't cross-referenced against an
   original finding (§2) — the content match is strong, but you may want
   to eyeball it yourself before it's included in step 1.
5. Whether superseded v1 of `holiness and personal purity` should be
   explicitly marked `'retracted'` after the rebuild, or left as
   superseded `'draft'` (§4 — cosmetic, not functional).
