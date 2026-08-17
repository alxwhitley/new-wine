# Rhemata — Architecture Reference

Load on demand. Not always-loaded. See `CLAUDE.md` for invariants.

**Eviction rule:** if you can learn it by reading the repo in under 2 minutes,
delete it rather than maintain a copy. This file decays silently.

Repo root: `/Users/alexwhitley/rhemata`

---

## Shape

```
sources/          # gitignored — raw/cleaned/ingested per pipeline
  youtube/        # raw → cleaned → ingested; ingest_queue.xlsx (Queue + HowToRun + source tabs)
  magazine/       # 01_to_extract → 02_extracted → 03_approved → 04_ingested → 05_archived
  stepbible/      # STEPBible TSVs + TAGNT interlinear files
  inbox/          # non-copyrighted (sermons, papers)
scripts/          # all ingestion + maintenance
  data/           # small committed reference data files (e.g. common_religious_vocab.json)
migrations/       # SQL, run manually in Supabase SQL Editor
recovery/         # deletion exports — NOT under sources/ (gitignored would drop them)
docs/             # source markdown for static marketing pages
  audits/         # one-off reports, diagnostics, comparisons
backend/app/      # FastAPI: main.py, auth.py, routers/, services/, db/,
                  # system_prompt.txt, theological_guardrails.txt
frontend/app/     # Next.js 16 — /home, /sources, /beliefs public; app routes gated
```

Public marketing routes (no auth): `/home`, `/sources`, `/beliefs`. Latter two
render from `docs/*.md`, linked via shared `FooterNav`.

Backend routers: `chat`, `search`, `document`, `library`, `study`,
`pastors_notes`, `usage`, `ingest`, `ingest_queue`, `admin`, `feedback`, `account`.

---

## Database

Tables: `documents`, `chunks`, `propositions`, `proposition_chunks`, `positions`,
`position_evidence`, `verses`, `saved_words`, `excerpts`, `guest_sessions`,
`conversations`, `messages`, `interlinear_words`, `book_quotes`, `user_usage`,
`sources`, `source_aliases`, `source_license_audit`, `app_settings`,
`removed_urls`, `user_roles`, `contributor_requests`, `pastors_cards`,
`deletion_requests`, `source_ingest_queue`, `source_ingest_domain_memory`.

**documents** — `source_type` (sermon|background|magazine_article|commentary|
book|paper|other) · `source_kind` · `citation_mode` (citable|silent_context) ·
`is_copyrighted` (unreliable — see CLAUDE.md invariant 4) · `topic_tags` text[]
(nullable) · `bible_references` text[] GIN · `fts_weighted` tsvector ·
`image_url` · `source_id` uuid NOT NULL FK → sources, ON DELETE SET DEFAULT ·
`original_title`.

**sources** — one row per rights-holder. `license_status`
(public_domain|owned|licensed|unlicensed) = truth about rights. `visibility`
(shown|hidden, DEFAULT hidden = fail-closed) = what the gate obeys. `retrievable`
generated boolean is informational only, NOT read by the gate. RLS service-role.

**source_aliases** — normalized `alias_key` UNIQUE → `source_id` FK ON DELETE
CASCADE. Resolution order: source_name alias → author alias → sentinel + a
grep-able `ALIAS_MISS` log line.

**propositions** — atomic paraphrase decompositions. `document_id` FK CASCADE,
`content`, `embedding` vector(1536), `proposition_index`, `fts` generated,
`prompt_version`/`prompt_fingerprint`/`model` (nullable at the schema level —
every pre-2026-07-30 row is NULL here, a known landmine — but a write through
`store_propositions()` itself can no longer omit them, see below).
Indexes: HNSW (m=16, ef_construction=64), GIN on fts, btree on document_id. No
license columns by design — resolves through document_id → source_id → sources.
Gate: extracts for `licensed`/`unlicensed` only; skips `public_domain`/`owned`;
missing source fails closed; Precept Austin locked out by name
(`PRECEPT_AUSTIN_SOURCE_ID`) — its excerpts are near-verbatim reorderings, not
paraphrases. `store_propositions()` is clear-then-write (DELETE by document_id
then insert) — re-running on the same doc_id is always safe. `prompt_version`
is now a REQUIRED parameter (an omission is an immediate `TypeError`, never a
silent NULL write, PLAN.md #45.8); `fingerprint`/`model` are no longer
caller-suppliable at all, derived internally from `prompt_version`. An optional
`chunk_ids` parameter links every proposition stored in that call to the
document's full current chunk set via `proposition_chunks` (below) — omitted
by any caller not yet updated, byte-identical when absent.

**proposition_chunks** — join table, `(proposition_id, chunk_id)` composite PK.
`proposition_id` FK CASCADE (a deleted proposition's back-links go with it);
`chunk_id` FK RESTRICT (a chunk a live proposition depends on can't be silently
deleted out from under it). Additive, migration 074 — every pre-2026-07-30
proposition has zero rows here, meaning "unknown," never backfilled. Records
the full chunk set a proposition's extraction call actually saw, not a single
chunk — extraction always runs on complete reconstructed document text.

**positions** / **position_evidence** — teacher/corpus position layer
(PLAN.md #48; migration 073 foundation, 076 corpus ban-lift, 077 versioning).
`positions.kind` CHECK-locked to `IN ('teacher','corpus')` (widened from
073's teacher-only lock on Alex's 2026-08-01 call — CLAUDE.md Invariant 13; a
third scope still needs code+migration). `source_id` is NULLABLE with a
scope/source coupling CHECK: teacher ⇒ `source_id` NOT NULL (names one
teacher), corpus ⇒ `source_id` NULL (contributors DERIVED from evidence, never
a stored pointer/taxonomy). `prompt_version`/`prompt_fingerprint`/`model` NOT
NULL from row one (Invariant 14, unlike `propositions`' nullable columns
above) — corpus rows stamp `position_corpus_v1`. Versioning columns (mig 077):
`lineage_id` groups a position's versions, `version` monotonic, `is_current`
(partial unique index enforces exactly one current per `(topic_key,
requested_teacher_id)` — the lineage/lookup key), `supersedes_id` chains a
rebuild to its predecessor, `topic_key` = `normalize_topic_key(topic)`
(byte-matches mig 077's SQL), `requested_teacher_id` = the teacher a question
named (NULL = topic/corpus question — the discriminator that lets a topic
lineage widen teacher→corpus without a rewrite). `position_evidence` is a real
join table (`position_id`/`proposition_id`) with `ON DELETE RESTRICT` on
`proposition_id` — an evidence proposition can't be silently deleted out from
under a position that cites it. Served by `scripts/serve_position.py`
(lookup-or-generate); **not yet wired into live chat** as of 2026-08-01.

**app_settings** — one row, `key='safe_mode'`. On = only PD/owned retrievable
regardless of visibility. Never writes `sources.visibility`.

**removed_urls** — blocklist written by `DELETE /admin/document/{id}`, checked by
`youtube_ingest.py` before each ingest (non-fatal skip on hit).

**source_ingest_queue** (migration 075; runner extension applied in migration
088) — admin-submitted candidate source URLs and the durable control
plane for `scripts/source_ingest_worker.py`. The built first slice accepts only
`pdf + single + declared`, claims only `waiting` rows with
`cleared_to_run=true`, and uses worker ownership, leases, bounded retries,
stages, final URL/hash/byte evidence, and exact attempted/stored/skipped/errored
counts. It resolves the declared author to an existing non-sentinel source,
requires canonical `is_source_servable()` approval, never creates aliases or
changes visibility/license/safe mode, and calls `shared_ingest.ingest_document()`
as its only corpus writer. Complete extracted text is retained in
`documents.full_text`; PDF binaries are not retained. Unsupported shapes,
unsafe/empty sources, attribution misses, and non-servable sources stop in
`needs_attention`. The runner code is present in deployed release `0925c93`;
migration 088 is applied and one isolated processor proof completed, but no
source-worker service is configured. The existing admin UI remains the
submission/clearance surface.
RLS remains own-row read/insert plus service-role full access.

Runner safety limits are fixed at three redirects with no HTTPS downgrade,
30-second connect/read timeouts, 50 MiB streamed bytes, 60-second extraction,
2,000 pages, and 10 million extracted characters. Every DNS answer must be
globally routable and the socket is pinned to a validated address while Host,
TLS SNI, and certificate identity stay on the original hostname. Policy/input
failures (`unsupported_*`, retention/author/source/servable failures,
`unsafe_url`, non-PDF/size/page/text/empty extraction) require operator
attention; network/provider/database/internal transients retry up to the row's
bounded attempt ceiling. Logs omit source text, response bodies, credentials,
and URL query/fragment values.

**source_ingest_domain_memory** — one row per URL domain, remembers the
last `attribute_to`/`attribution_mode` used for that domain so the submit
form can prefill on URL blur. Service-role-only RLS (no owning user).

### Retrieval

Query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60) →
disabled-source filter → **hard-exclude commentary** (Settled decision #5;
`is_commentary_chunk` / `exclude_commentary_chunks`, in
`backend/app/services/answer_toolbox.py`) → top 30 with `SOURCE_KIND_FUSION_WEIGHTS` (book ×0.8, lexicon
×0.5; commentary is not soft-weighted — it is removed earlier) → Cohere
rerank → top 8 → neighbor expansion → second commentary strip (defense-in-depth).

- `match_chunks` — HNSW, `hnsw.ef_search=200`
- `search_documents` — document-level FTS, ts_headline snippets
- Neighbor expansion skips commentary/lexicon (`_NEIGHBOR_SKIP_KINDS`)
- Commentaries never enter answer context (decision #5); Study Mode still
  serves them via `match_commentary_*` / `GET /study/commentary`
- FTS OR-fallback: on 0 results, retries OR-joined top-3 longest tokens (min 6
  chars, `_FTS_BROAD_TERMS` excluded)
- `citable_count` gate counts post-Cohere, pre-neighbor top-8; sermon/citable
  only. Hard short-circuit fires only for truly empty chunk sets.

Chunking: magazine — tiktoken cl100k_base, 550 tokens, 80 overlap. Standalone —
recursive character, 1000 chars, 200 overlap. Lexicon — one entry, one chunk.

### Answer generation

`producer.py` `_generate_and_capture()` (the primary chat-style answer path
since chat.py's deletion, 2026-08-07 mirror-unification job — a second,
structurally different served-generation surface, `get_teacher_card()`
in `backend/app/routers/study.py`, also exists; see CLAUDE.md's Landmines
correction on that job) streams `claude-sonnet-4-5`
(`GEN_MAX_TOKENS = 8000`) and emits ONLY the `<answer>`
block; the `<thinking>`/`<research_analysis>` prefix is discarded, never streamed.
**Hard guarantee (Phase 0 §7a): internal reasoning can never reach the user.** If
the generation ends with no `<answer>` block (budget exhausted inside the hidden
blocks), the fallback serves a fixed clean message — it emits `raw_full` only when
that raw output contains NO reasoning tags (a benign plain-prose answer). If
`<answer>` opened but hit the ceiling before `</answer>` (`stop_reason ==
max_tokens`), one clean cutoff sentence is appended. SP1 `verify_references`
(reference_verifier.py) then confirms the model's `<reference_mentions>` against
real data before any study-panel links are surfaced. If the citable evidence
has exactly one named author, the producer also requires that full name in the
answer: one constrained regeneration is followed, only if needed, by a
deterministic grounded `Source voice` label before reference verification.
This orchestration is versioned as `policy_v3`, so older anonymous cached
answers cannot bypass it.

---

## Position papers (fence + guarded retrieval)

`backend/app/services/position_papers.py` — a small, CLOSED, code-defined
registry (`PILLARS`) of Alex's own first-party owned "house position papers."
**All eight charismatic pillars are now live** — `baptism_holy_spirit`,
`speaking_in_tongues`, `deliverance_and_spiritual_warfare`,
`prosperity_and_faith_teaching` (registered 2026-08-13, first round),
and `divine_healing`, `gifts_of_the_spirit_overview`,
`prophecy_and_the_prophetic`, `five_fold_ministry` (registered 2026-08-13,
second round — same fence/exclusion/fallback mechanism as the first four,
no pillar-specific code path). `docs/position_papers/` no longer holds any
unregistered draft. The second-round three that had "failed first-pass
calibration" got real iteration this pass, not a quick fix: own-goal
contrast-anchor bugs (a contrast anchor accidentally describing the
pillar's own genuine territory, the same pattern already documented for
`baptism`/`deliverance`) and cross-pillar bleed against the broad
`gifts_of_the_spirit_overview` anchor were found and fixed the same way
prior rounds were — see the code comments above each pillar's anchor
constants for the specific bugs found and how each was resolved.
`five_fold_ministry`'s editorial question (restoration-after-a-gap vs.
never-ceased) was resolved by Alex the same session — the offices never
ceased, only neglected — before registering, so the draft carried no open
placeholder into its ingested content.

**Corrected 2026-08-06 (CLAUDE.md Settled decisions #8/#16/#17) — a position
paper is constraining silent context, never a served answer.** Until this
date, a match bypassed retrieval entirely and served the paper's own
pre-written body directly, uncited, in Rhemata's own voice — the SHIPPED
mechanism CLAUDE.md's Settled decision #8 flagged, from 2026-08-01, as
directly contradicting decision #8 itself. That conflict is now resolved in
decision #8's favor, not left standing:

- `producer.py` still calls `match_position_paper(question)` early,
  but a match no longer short-circuits anything — retrieval (query expansion,
  hybrid search, rerank, neighbor expansion) runs completely normally, exactly
  as it does for a non-matching question.
- On a match, the paper's own body (`get_paper_body()`) is injected into the
  retrieval context as `[House Position] (citation_mode=silent_context)`
  content: it bounds what the answer may claim (the writer may not contradict
  it) but must never be cited, named, quoted, or have its wording copied.
  Deduped against the pre-existing background-topic injection mechanism
  ("Fix 6", in `producer.py`) so the same document is never retrieved and
  injected twice.
- `backend/app/services/position_paper_exclusion.py` (new) —
  `exclude_contradicting_teachers(pillar_key, house_position_text, question,
  chunks) -> (filtered_chunks, excluded_authors)`. One Anthropic call per
  question (not per teacher): retrieved citable, non-lexicon chunks are
  grouped by author, and the model judges each teacher's material against
  the house position, returning a structured per-teacher contradicts/doesn't
  verdict. A teacher whose material genuinely contradicts is excluded
  entirely from the answer's context/citations — never silently reframed
  into agreement (the failure CLAUDE.md decision #9 flagged). Fails SAFE
  toward NOT excluding on any parse/API error. Every exclusion is logged at
  INFO (question, teacher, topic, reason) for later false-exclusion-rate
  measurement — an explicit, Alex-authorized exception to this codebase's
  usual posture against LLM judgment calls (Open Decision #20 concerns a
  different problem, post-hoc claim verification on an unmatched answer).
- If exclusion removes every chunk from an otherwise non-empty retrieval —
  never for thin/empty retrieval, never on no match, never on an error —
  `render_paper_voice_with_disclaimer()` (in `position_papers.py`) serves the
  sanctioned No-Oracle-Rule fallback: the paper's own voice (still generated
  by `generate_position_paper_answer()`, unchanged, now used ONLY for this
  narrow case) with the standard disclaimer appended deterministically in
  code, never left to the model. Logged every time it fires.

Matching itself is unchanged: fully semantic, the question embedded once
(OpenAI), scored per pillar as max-similarity against that pillar's positive
anchors vs. its contrast anchors, gated by a per-pillar `match_threshold` AND
pos_sim > contrast_sim, cross-pillar ties broken by an explicit
`tie_break_priority`. No phrase blocklist, no hardcoded topic strings.

Scope guard (module docstring, unchanged): this must never become a generic
"serve any `silent_context` document" mechanism — that would be a license-gate
bypass. A new pillar is safe only because it must be Alex's own owned content
added deliberately to `PILLARS` in code, never from a DB table or a runtime
flag.

Public surface: `match_position_paper(question) -> Optional[str]`,
`get_paper_body(pillar_key) -> Optional[str]`,
`generate_position_paper_answer(pillar_key, question, messages) -> Iterator[str]`
(SSE stream — now used only by the fallback path, not the default),
`render_paper_voice_with_disclaimer(pillar_key, question, messages) -> str`
(new — buffers the above + appends `DISCLAIMER_TEXT`),
`PILLARS` (the registry list itself — `answer_toolbox.py` builds its own
`_PILLAR_BY_KEY` lookup from it, used by `producer.py` for the
fence-injection step, rather than new API surface on this module).

**Naming caution — "position" spans three unrelated things** (see CLAUDE.md
Invariant 12's note): (a) the `positions` teacher/corpus table + `positions.py`
(both generators source-blind by signature), (b) this `position_papers.py`
feature — reads document/chunk text by deliberate design, but as of
2026-08-06 only to inject fence context or, in the narrow disclosed fallback,
to phrase an uncited-with-disclaimer answer; not (a)'s routine path and not a
violation of (a)'s invariant either way, (c) the `docs/position_papers/`
draft folder.

---

## Scripts

**Shared writer:** `shared_ingest.py::ingest_document()` — resolve → insert →
chunk → embed → propositions. Hooks: `source_id` override / `resolve_from`,
`find_existing_fn` / `on_existing` (skip|reuse|delete_and_reingest), `chunk_fn`,
`propositions_conn`. Chunk inserts run through a single unconditional batched
`execute_values(...)` — there is no `insert_mode` parameter (collapsed in the
all-or-nothing rewrite). Chunk inserts must NOT include `page_number` or
`source_hash`; neither column has ever existed live.

Routed through `shared_ingest`: `ingest.py`, `ingest_magazine.py`,
`ingest_preceptaustin.py`, `ingest_lexicon.py`, `ingest_helloao.py`
(commit `929bc34`, 2026-08-08 — chunk_fn override for one-chunk-per-verse,
same pattern as lexicon's one-entry-one-chunk).

Accepted exception: the orphaned admin PDF route in
`backend/app/routers/ingest.py` still writes directly and does not gain the
shared writer's proposition/license/source behavior. It now emits bounded,
reconcilable failure context (upload/title identity, stage, attempted document
ID, attempted/stored chunk counts), but that observability does not make it a
compliant writer.

| Script | Purpose |
|---|---|
| `source_ingest_worker.py` + `source_ingest_queue/` | Applied but undeployed durable queue runner: one-at-a-time leased claims, SSRF-safe IP-pinned PDF fetch, child-process extraction bounds, read-only dry run, canonical source/visibility gates, and sole-writer execution with exact reconciliation. One isolated processor proof completed; no worker service exists. First slice is `pdf + single + declared`; retains extracted text, not PDF binaries |
| `apply_migration_088.py` | Explicit `--apply`-gated migration tool. Before mutation it writes a mode-0600 retention snapshot under gitignored `source_ingest_runner_review/`, applies migration 088 once, verifies schema/count/retention on a fresh connection, and runs an exact-fixture two-claimer proof. Repository tests never invoke the live apply path |
| `source_resolver.py` | `normalize_alias_key`, `resolve_source_id`, sentinel + New Wine constants, `print_resolution_table` |
| `propositions.py` | Extraction + storage. `DEFAULT_PROMPT_VERSION` is still `"v3"` (unchanged, so every caller that doesn't opt in is byte-identical to before 2026-07-30). **`EXTRACTION_PROMPT_V3_1` (2026-07-30) is v3's exact wording with ONLY the named-teacher mechanism grafted in** — a `{speaker}` placeholder replaces v3's 8 generic "the author" references, plus one added "never 'the author'" instruction; byte-identical to v3 everywhere else, including the length line (deliberately NOT v4's expanded length/structure/voice retuning). Selected via `prompt_version="v3.1"` + a non-empty `speaker` (same requirement as v4); proven corpus-wide (PLAN.md #17) at 0.0% "the author" rate, length unchanged. `EXTRACTION_PROMPT_V4` still exists, still unwired the same way. A deterministic `MIN_SUBSTANTIVE_WORD_COUNT=50` word-count floor in `process_document()` skips the model call entirely below it, returning `"too_thin_to_extract"` (distinct from `"no_propositions"`, which means the model ran and found nothing) — grounded in the real observed corpus minimum (61 words). `extract_propositions()` unconditionally builds a closed, mechanically-derived list of scripture references actually present in the source and appends it to the Groq message (no opt-out) — the model may not cite beyond it. At the end, unconditionally arbitrates every UNGROUNDED/UNCERTAIN reference via `citation_verifier_layers.verify_reference_grounded(..., llm_enabled=True)` (a live Groq call) before stripping — confirmed-absent strips as before; the arbiter overturning a flag keeps the reference instead, logged `arbitration_overturned`; arbiter unavailable or a still-unparseable reference strips fail-safe (`arbitration_unavailable*`, a narrow disclosed exception to CLAUDE.md Invariant 11). Every strip/keep decision logs to gitignored `reference_grounding_review/stripped_references.jsonl` with both the original reason and the arbitration label. `process_document()` takes optional `name_pattern`/`verse_lookup`/`vocab_matcher` (closeness-check gate, default off, byte-identical when omitted), optional `chunk_ids` (links every stored proposition to `proposition_chunks`, enrichment only), and optional `speaker`/`prompt_version` (2026-07-30, both default `None` → old behavior; a caller opts into `v3.1`/`v4` by supplying both). `store_propositions()` now REQUIRES `prompt_version` (an omission is an immediate `TypeError`, never a silent NULL write, CLAUDE.md Invariant 10) — `fingerprint`/`model` are no longer caller-suppliable at all, derived internally. **A gap surfaced 2026-07-30 (single-call-per-document sends the ENTIRE document, can exceed `max_tokens=8192` on book-length documents) now has a real fix for a SUBSET of books, shipped 2026-07-31, commits `d7c46f5`/`b4ab601`:** `split_book_into_chapters()`/`_extract_and_store_book_chapters()`/`process_book_document()` chapter-scope a book-length document into a multi-call extraction, one call per real chapter, with `is_front_back_matter()` skipping title-page/index/CCEL-metadata/third-party-editorial spans before the model is ever called (the byline/apparatus-credit checks — `_has_third_party_byline()`, `_MATTER_LABEL_APPARATUS` — plus a tightened digit-ratio roman-numeral arm are a separate follow-on fix, **committed 2026-08-01, commit `8e251c8`** — no longer a follow-on gap). Only reliably covers the 8 of 53 book documents whose chapters repeat their own title (`split_method="title_repeat_boundary"`); a second detector for roman-numeral/bare-"Chapter N" books (`detect_book_chapters()`/`_detect_numeral_heading_sequence()`) exists in the same file but is uncommitted and has zero production callers — do not assume it runs. `_roman_to_int()`/`_int_to_roman()`, originally introduced alongside that uncommitted detector, now live earlier in the file (near `_digit_token_ratio()`) since the committed digit-ratio fix depends on them directly — reused unchanged by the still-uncommitted detector too, not forked. See CLAUDE.md Landmines and PLAN.md #50. Separately, a pre-existing, occasionally-deterministic JSON-escaping defect remains true and unrelated to any of this: the model can emit an unescaped quote inside a nested scripture quotation, breaking `json.loads()` — present in v3 and v3.1 alike |
| `backfill_propositions.py` (2026-07-30) | Runs `process_document()` against already-ingested documents that currently have zero propositions, given a JSON file of `{id, source_id, author, source_name, ...}` targets and an optional `prompt_version` CLI arg (omitted = old v3 behavior; `"v3.1"` = named-teacher fix, resolving `speaker` from the target's own `author`/`source_name`). Used for this session's two 25-document proving batches, not the full run (see `run_full_backfill.py`) |
| `run_full_backfill.py` (2026-07-30) | The full remaining-corpus backfill driver (PLAN.md #17/#49) — sequential, one document at a time, on the proven v3.1 path. Crash-safe/resumable by construction: every result appends immediately (fsync'd) to gitignored `backfill_run_review/full_backfill_log.jsonl`; re-running the script excludes any doc_id already in that log (any outcome) from its target list, no separate state file needed. A connection-level failure (psycopg2 `OperationalError`/`InterfaceError`) reopens the connection and continues rather than killing the run. After the main pass, every document whose latest logged result is `error`/`exception:*` gets exactly one retry pass, logged with `attempt="retry"` so a second script run never retries the same document twice |
| `reference_grounding.py` | Shared GROUNDED/UNGROUNDED/UNCERTAIN predicate (PLAN.md #45.5) — is a scripture reference actually present in given source text? `find_reference_spans()` locates every parseable "Book Chap:Verse[-Verse]" substring; `check_reference_grounded()`'s citation-string arm always runs (reuses `reference_verifier._parse_verse_or_range`, imported not forked); an optional verse-wording arm (only if `verse_lookup` supplied) reuses `closeness_check`'s `_anchor_extend_density_span` fuzzy matcher for translation-variance wording matches. Source-agnostic `source_text: str` signature — used unchanged by both `propositions.py` (prevention call site, no `verse_lookup` available, so only the citation-string arm ever fires there) and `detect_reference_fabrication.py` (detection, `verse_lookup` supplied, both arms fire). Whole-document scoping only — no chunk/paragraph backreference is consulted here (though `proposition_chunks` now records the chunk set separately, see Database above), so it cannot distinguish "this reference is genuinely tied to this claim" from "this reference exists somewhere else in a long document" (confirmed real via the Ravenhill Phil 4:8-9 case — an accepted, disclosed limitation, not a bug). Exposes `normalize_reference_text()` (dot-to-space + whitespace-collapse), applied to the reference-under-test in `check_reference_grounded()` and reused (not forked) by `citation_verifier_layers.py`'s three parse sites — fixed 2026-07-29/30; dotted abbreviations ("1 Cor.", "Matt.") now parse and get genuinely evaluated instead of always reading UNCERTAIN |
| `detect_reference_fabrication.py` | Corpus-wide, read-only scripture-citation-fabrication detector (PLAN.md #45.5) — reuses `reference_grounding.py` unmodified against every live proposition's reference(s); `verse_lookup` built once, each in-scope document's source text reconstructed from `chunks` once and cached. Writes UNGROUNDED/UNCERTAIN findings only (never GROUNDED) to gitignored `reference_fabrication_review/corpus_findings.jsonl`, one record per finding, for human review. Zero DB writes — every touch is a SELECT |
| `citation_verifier_layers.py` | Three-layer, cheapest-first citation-grounding verifier (PLAN.md #45.6) — widens recognition beyond `reference_grounding.py`'s compact-form-only scan to spoken/free-form shapes. Layer 1: regex-only, reuses `find_reference_spans()` plus five widened patterns (book+chapter+verse in various orders/forms, including bare "chapter N:M" colon form with no literal "verse" word); every candidate re-validated through `word_or_digit_to_int()` + `_parse_verse_or_range()`, no bypass. Layer 2: document-wide book scope (book named anywhere + same chapter:verse found anywhere via a book-less pattern) — deliberately loose, `multi_book_document`/`distinct_book_count` exposed on the result for that reason. Layer 3: LLM read (`propositions._get_groq()`/`EXTRACTION_MODEL`), gated by `llm_enabled` — **run live for the first time 2026-07-29** (42 real corpus items, 78.6% overturn rate on automated flags) and again 2026-07-30 as the generator's real arbitration step (PLAN.md #45.7/#45.8) — no longer wiring-proven-only. All three parse sites now reuse `reference_grounding.normalize_reference_text()` (fixed 2026-07-29/30, no fork) — previously a dotted reference-under-test could short-circuit to `unparseable_reference` before Layers 1-3 ever ran. `BOOK_MAP` is imported directly from `app.constants` (same object, not a fork). Primary job since 2026-07-28: the generation-time confirming step `extract_propositions()`'s reversed anti-fabrication filter needs, not retroactive corpus audit |
| `closeness_check.py` | Wording gate (PLAN.md #45/#46) — trigram containment + longest-run secondary signal + scripture/name/theology/vocab exemption. `classify()` returns PASS/QUOTE_CANDIDATE/HOLD_TOO_LITTLE, checked in that precedence order (`HOLD_TOO_LITTLE` first, unconditional on the other two constants). **Constants human-calibrated 2026-07-30 (PLAN.md #46, Alex's 24-item blind pass):** `LONGEST_RUN_WORD_THRESHOLD=12` (words, post-exemption — was a provisional 9); `CONTAINMENT_FLOOR=0.40` (re-examined against both the calibration set and the real R1 mechanical-ladder validation tier, held unchanged — raising it enough to pass 3 calibration items would break 14/15 real R1 cases, a named accepted conflict, not silently resolved); `RESIDUAL_TOO_LITTLE_CUTOFF=8` (unchanged, retained per Alex's explicit instruction). `build_vocab_matcher()` compiles `scripts/data/common_religious_vocab.json`'s 1,210 corpus-derived common phrases into a reusable fuzzy matcher reusing `_find_quote_span`'s own anchor/gap/density algorithm and constants (via shared `_anchor_extend_density_span`); wired through `exempt_for_containment`/`exempt_for_run` in masking order scripture→vocab→names→theology (vocab must run before the word-level name/theology stoplists, or they can fragment a vocab phrase's own anchor words first). Gate itself (`process_document()`'s `name_pattern` parameter) remains default-off, not yet activated by any real caller |
| `validate_closeness_check.py` | Validation harness for the above — real-corpus should-pass sampling + mechanical edit-ladder should-flag construction |
| `closeness_triage.py` | Local-only retroactive triage workflow for the 213-item flagged/held pile (PLAN.md #47) — reads the recorded JSONL directly, no classifier rerun. Splits into 139 fast (binary) + 74 real-attention (context + highlighted verbatim run) queues; decisions persist only to a local gitignored `decisions.json` ledger. Read-only/autocommit Postgres connection for source context only — no corpus mutation path. `test_closeness_triage.py` proves balanced batching, run-highlighting, context excerpts, closed decision vocab, and decision persistence |
| `ingest.py` | Standalone PDF/docx/txt + auto-tagging; `skip_dedup` param |
| `ingest_magazine.py` | From .md + frontmatter; bakes chunk-content headers |
| `ingest_lexicon.py` | STEPBible TBESG/TBESH/TFLSJ; one-entry-one-chunk |
| `ingest_lexicon_runner.py` | Batching/pacing driver over `ingest_lexicon`, checkpointed slices |
| `ingest_preceptaustin.py` | Precept Austin word studies; cross-pipeline reuse-by-title |
| `ingest_helloao.py` | Live API fetch, resume-safe; routed through `shared_ingest` (chunk_fn override: one chunk per verse) |
| `ingest_bible.py` / `ingest_interlinear.py` / `ingest_tahot.py` | verses table |
| `extract_magazine.py` | 3-pass Gemini/Groq extraction |
| `scrape_youtube.py` | yt-dlp + Supabase dedupe (legacy path) |
| `clean_transcripts.py` | Groq transcript cleaning |
| `youtube_triage.py` | Stage 2: enumerate + Groq classify; `process_sheet()` |
| `youtube_ingest.py` | Stage 3: fetch + `ingest_file(skip_dedup=True)`; `ingest_sheet()`. Self-contained since 2026-06-27 |
| `run_queue_triage.py` / `run_queue_ingest.py` | Stage 5 Queue orchestrators |
| `discover_sermonindex_playlists.py` | Discovery only, zero writes. Known: first page only (~40); multi-name false positives |
| `verify_chunk_alignment.py` | Standalone embedding/content alignment spot-check. **Docstring is stale** — describes insert modes that no longer exist |
| `taxonomy.py` | 258-tag taxonomy, 15 categories. **Single source of truth** — `taxonomy.md` is generated for humans only |
| `tag_existing_articles.py` / `tag_sermons_transcripts.py` | topic_tags backfill |
| `extract_bible_refs.py` | bible_references backfill |

### Queue tab contract

`url | source_name | review | filter | limit | status`

- `filter`: `min5` (skip ≤5min), `whitelist` (title-match, Groq skipped,
  pre-classified sermon=TRUE). Comma-separate for combos.
- `limit`: integer, applied via `--playlist-items 1:{limit}` at yt-dlp
  enumeration time — not a Python break after the fact. Critical for large
  channels; `enumerate_channel()` timeout is 300s.
- Whitelist mode: blank `source_name` is valid. Tab label derives from URL
  handle. Whitelist file resolves as `scripts/whitelist_{slug}.txt`.
- De-dup is additive; re-runs with a larger limit only append. To re-enumerate,
  blank the row's `status` first.

---

## Commands

```bash
# Backend deploys to Railway on push to main. There is no local backend.
git add -A && git commit -m '...' && git push

cd /Users/alexwhitley/rhemata/frontend && npm run dev   # localhost:3000

cd /Users/alexwhitley/rhemata
python3 scripts/ingest.py                               # standalone

python3 scripts/extract_magazine.py                     # magazine: extract
# manually move approved → sources/magazine/03_approved/
python3 scripts/ingest_magazine.py                      # magazine: ingest

python3 scripts/run_queue_triage.py                     # youtube: all pending
python3 scripts/run_queue_triage.py --only "Sermonindex"
python3 scripts/run_queue_ingest.py
python3 scripts/run_queue_ingest.py --sheet "Sam Storms"

python3 scripts/ingest.py --dry-run-sources             # resolve + print, no writes
```

---

## Environment

`backend/app/.env` — Supabase URL/keys, OpenAI, Groq, Cohere, Gemini, Anthropic,
`ALLOWED_ORIGINS` (comma-separated), `GUEST_QUERY_LIMIT=6`.
`ADMIN_EMAIL` is dead — auth moved to the `user_roles` DB-role guard in
`auth.py` (`require_admin_role`, `require_contributor`).

Frontend (Vercel): `NEXT_PUBLIC_*`. `next.config.ts` adds the Supabase hostname
to `images.remotePatterns`.

`nixpacks.toml` locks Python 3.9. `requirements.txt` pinned via pip freeze.

---

## Admin panel / account panel (merged 2026-07-25)

`AdminModal.tsx` is one modal opened directly from the sidebar footer identity
button, for **every authenticated user** — not admin-only. Left nav: **Profile**
(always visible — identity header with avatar/name/role badge/email, sign out
anchored top-right, then Display name / Email / Weekly usage / Delete-account
cards) first, then, only when `user_roles.role === 'admin'`: **Corpus**
(Documents / Sources / Pipelines), **Feedback**, **Contributors** (includes the
"Account Deletion Requests" card), **Notes Queue**, **Source Queue** (submit
form + Needs Attention + Queue list over `source_ingest_queue`, rendered by
`SourceQueuePanel.tsx`). Gating moved from "does the modal open at all" (old
behavior: closed itself for non-admins) to "which nav items render" — see
`panelReady` (any authenticated user) vs `roleChecked` (admin only, gates the
other five tabs' data fetches) in the component. Realtime uses a unique
channel name per mount (`admin-realtime-${Date.now()}`).

**Known gap, not introduced this build:** the left nav is a fixed 200px
column with no mobile breakpoint — on a real phone-width viewport (~390px)
it doesn't collapse to a drawer, squeezing every tab's content into a
narrow remainder. Confirmed live via Playwright at a 390px viewport while
building the Source Queue tab: no page-level horizontal overflow, but a
two-button toggle row (e.g. "Web page"/"PDF") can still crowd within that
squeezed width. Fixing the shell itself (nav collapsing responsively) is
cross-cutting — affects all five tabs — and out of scope for this build.

There is no separate account `Dialog` anymore. `sidebar.tsx`'s earlier "Your
account" popup (built, shipped, then superseded the same day) was removed
entirely; its content lives inside `AdminModal.tsx`'s Profile tab instead.

**Delete account is a stub.** `POST /account/delete-request` only inserts a row
into `deletion_requests` for manual admin follow-up (resolved from the
Contributors tab's "Account Deletion Requests" card via
`POST /account/delete-requests/{id}/resolve`) — it deletes nothing. No
cascading deletion of `conversations`, `saved_words`, `pastors_cards`,
`user_roles`, or the Supabase auth user exists anywhere in the codebase yet.

**Rule: admin data fetches must surface errors — never silently render
empty/zero.** A `.catch(() => setX([]))` hid a total backend 403 wall behind
"No sources found" for the entire backend lifetime.

**Rule: no N+1 in admin endpoints.** 43 sequential COUNTs timed out on Railway
and the silent catch masked it as empty state. Bulk-fetch, aggregate in Python.
If any admin endpoint is slow or flaky in prod, check for an N+1 loop first.

**FastAPI gotcha:** `Query(...)` / `Path(...)` as route defaults evaluate at
import time. A missing fastapi import → `NameError` → uvicorn never binds → every
route in that file 404s (not 500).

---

## Metering

Authenticated: 50 queries/week, Monday UTC reset. `user_usage.weekly_limit` is
per-row, not hardcoded. `increment_user_query` uses `SELECT FOR UPDATE` +
conditional UPDATE — no race at cap, returns `allowed bool`, hard 429 before any
LLM call. Study endpoints excluded. Guests: `guest_sessions` +
`increment_guest_query`, IP-capped at 20/hr/IP (migration 057) to close the
anon_id-rotation bypass. SSE meta carries `usage: {used, limit, week_start}`.

---

## Standing source policy

- New unlicensed sources register `hidden`. Flipping to `shown` is never an IP
  clearance — it requires an explicit beta-scope decision recorded in PLAN.md.
- Tier-1 beta (≤20 users) has unlicensed sources deliberately `shown` as accepted
  risk. Canonical list is the live DB, never a static list here:
  `SELECT name FROM sources WHERE license_status='unlicensed' AND visibility='shown'`.
  At the Tier-1→Tier-2 trip line, every one goes back through the gate.
- SermonIndex's "public domain where applicable" is intent, not a legal grant —
  it doesn't own third-party preachers' copyrights. Stays `unlicensed/hidden`
  until attorney review. Do NOT upgrade without legal confirmation.
- Entity consolidation lives in `source_aliases`: re-upload venues → speaker;
  name variants → canonical; co-authored → primary. Ruth Prince is her own
  entity, NOT folded into Derek Prince.
