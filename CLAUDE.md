# Rhemata — Claude Code Context

AI-assisted Bible study tool for Spirit-filled/charismatic believers. RAG chat
with inline citations over a vetted, named corpus. Product model: Magisterium AI.
UX model: Perplexity.

**Design filter for any new feature:** does it make Rhemata sound more like a
spiritual authority in its own right, or more like a directory pointing to real
ones? The former is always wrong. Time-in-app is not a success metric — the goal
is sending users back to real teachers and real churches. A feature that makes a
user say "I don't need my pastor, I have Rhemata" gets killed regardless of
quality.

---

## Ranked failure modes (2026-08-01)

Judge every answer-path change against these, in this order. An accuracy fix
that trades one of these for another has improved nothing:

1. **Theologically wrong answers.** Worst outcome; would make Alex consider the
   product broken.
2. **Misrepresenting a teacher** — putting a position in a real, often living
   minister's mouth that he does not hold.
3. **Generic answers** — reading as interchangeable AI output rather than
   specific to how the question was asked. Fresh per-question synthesis was
   chosen precisely to avoid this; a correctness fix that makes every answer
   uniform has traded failure mode 1 for failure mode 3.

Most questions are general and topical ("what is deliverance"), not
teacher-specific — weight accordingly.

## Settled product decisions (2026-08-01) — do not reopen

Premises from the 1 August build plan (four adversarial architecture audits,
Claude + Codex, two rounds, the last two with live DB, independently
convergent). Design within them; do not relitigate. Where one conflicts with an
existing rule it is flagged inline with ⚠ — **flagged, not resolved, this
records pass** (resolving each means a code change or a governing-doc edit a
later session makes deliberately).

1. **Fresh synthesis every question**, shaped to how the user asked. Stored or
   pre-reviewed answers are permanently rejected — a review model can't
   enumerate hundreds of thousands of questions in advance. No human review gate
   anywhere on the serving path. ⚠ *Tension to watch: the position serving path
   stores and re-serves generated positions and has a planned draft-review UI
   (PLAN.md #48 / Open Decision #20(b)) — reconcile if/when that path goes live.*
2. **Launch bar is "materially safer,"** not a demonstrated error rate. No public
   claim about fabrication frequency. Deterministic correctness where it can be
   guaranteed; honest disclosure where it cannot.
3. **Eliminating invented claims is accepted as impossible.** Misattribution to a
   name is solvable deterministically (the permitted-name set is finite and
   computed before the answer is written); inventing the substance is not, at any
   timeline. Reinforces the Landmines fabrication findings and Open Decision #20.
4. **The probabilistic claim-support checker is HELD, pending measurement.** Do
   not build one. Do not propose a model-based judge anywhere — that shape has
   failed five times (Open Decision #20).
5. **Commentaries are excluded from answers; searchable only** (Alex's call,
   1 Aug; Open Decision #12). ⚠ *Conflict flag: the live retrieval path still
   admits commentary chunks into answer context (down-weighted and capped at 3),
   so behavior does not yet match this decision — a code fix, flagged not made.*
6. **Paragraphs that cannot be tied to a specific statement still display** — not
   flagged, not logged, not blocked. Deliberate, to avoid drowning in false
   positives from connective prose. Alex will revisit.
7. **No teacher taxonomy** — teachers are never labeled into theological
   families; contributors are always derived from the evidence at question time.
   *(Already enforced as Invariant 13's standing rule — restated here as a
   product premise, not a second rule.)*
8. **Position Papers are doctrinal grounding, not served answers.** Hand-authored
   by Alex on the charismatic pillars; they constrain what an answer may claim
   and must never supply its phrasing; triggered deterministically by topic,
   never by the system self-assessing "doubt" (unreliable, and would skip the
   paper exactly when it mattered most). ⚠ *Conflict flag: this directly
   contradicts Invariant 12's note (b) and ARCHITECTURE's "Position papers
   (house-voice answer path)," which bless the SHIPPED house-voice path that
   reads a paper's own chunk text to phrase answers. That path is exactly what
   Phase 1 items 1.5–1.7 change. Flagged, NOT resolved this pass — resolving it
   means amending Invariant 12(b), which this records pass deliberately leaves
   untouched.*
9. **House view and teacher view are two visibly separate things in an answer,
   never blended.** ⚠ *Conflict flag: a current house guardrail tells the model
   to follow house framing regardless of how the source puts it, which silently
   corrects a dissenting teacher into agreement — direct misrepresentation of a
   real minister (failure mode 2). Reconciling the system prompt / guardrails is
   a code fix, flagged not made.*
10. **Tongues is a house position, not a debate** (Alex's ruling, 1 Aug): not
    required as initial evidence of Spirit baptism, but reasonably expected for
    all. The neutrality list shrinks by one.
11. **Healing mechanics, prophetic accountability, and apostolic authority stay
    debates** — presented with named teachers on both sides. Alex has no settled
    view and will let the corpus inform it over time. Caveat on record: what the
    corpus says is a function of who is in it, not of what is true — a corpus
    majority must never quietly become a house position without a deliberate
    decision.
12. **Hidden-by-default is reversed: new material defaults to visible**, and
    everything currently hidden becomes visible. Safe now only because there are
    no users; it buys time, not a pass — known quality problems still clear
    before launch. ⚠ *Conflict flag: contradicts ARCHITECTURE's "Standing source
    policy" ("new unlicensed sources register hidden") and the "DEFAULT hidden =
    fail-closed" source design. The license gate SQL (Invariant 2) is unchanged —
    only the default visibility flips. Phase 1 item 1.3 is the code change +
    inventory; the ARCHITECTURE update is flagged, not made this pass.*

---

## Settled product decisions (2026-08-03) — build-plan reset; do not reopen

From two external adversarial reviews (one correctness-focused, one scope-cutting)
of a written proposal, plus Alex's decisions. These supersede parts of the
2026-08-01 plan; design within them. Full roadmap detail: PLAN.md "CURRENT BUILD
SEQUENCE (2026-08-03)".

13. **Build order is three projects, in sequence: (1) scalable async answer
    execution → (2) one named voice per answer → (3) hand-curated, server-gated
    quote rail.** Supersedes the 2026-08-01 phase ordering and PLAN.md Ordering
    Call G.

14. **Capacity target = 100 simultaneous generations, as a DIAL not a ceiling.**
    Exceeding 100 must mean running more workers, never a rebuild; any design
    choice that forecloses horizontal scaling is flagged and refused at review.
    Real per-answer COST must be measured before Project 1 is designed — cost may
    be the true ceiling; do NOT size from the partial extraction-cost figure on
    record. **MEASURED 2026-08-03 (`docs/audits/per_answer_cost_measurement_2026-08-03.md`):
    median normal answer $0.039 (house-voice ~$0.015; teacher card ~$0.015/open)
    — cost is comfortable, NOT the ceiling; the real open ceiling at 100
    concurrent is provider rate limits (RPM/ITPM/OTPM), unchecked from the repo
    — a commercial conversation. The instruction block is already cached (~25%
    saving at scale); the per-question retrieved context (~50% of cost) is the
    un-cacheable driver. This figure replaces the partial-extraction number as
    the sizing basis.** The reveal moves to the CLIENT after the checked answer is delivered;
    no client connection ever owns a generation worker; retries must not skip the
    accuracy check. One app / one queue / one DB / one scalable worker
    deployment — not microservices.

15. **One named voice per answer — the writer gets ONE teacher's propositions;
    the RENDERER (not the model) attaches names and links.** This IS the
    source-blind path; do not build "source-blind generation" as a separate
    project. It structurally closes claim-level A2 misattribution (the other
    teacher's material is never in the generation) — a failure previously logged
    as uncatchable. Teacher profile pages precompute instead of regenerating from
    source text per view (`get_teacher_card()` is the standing live-synthesis
    leak).

16. **Quote rail is manual-approval only; automated extraction is deferred.** An
    AI may PROPOSE quote candidates, never APPROVE one. Eligibility, all binding:
    auto-transcripts are ineligible unless a human checked the passage against the
    audio (~61% of the current evidence layer is auto-transcript from two LIVING
    ministers — a mistranscribed sentence in quotation marks under a living
    minister's name is the worst failure available to this product); also
    initially ineligible — OCR, translations, anthologies/compilations,
    interviews, guest-speaker material, mixed-author magazine pages, scraped
    reposts, any unresolved nested quotation. The real boundary is CONFIDENCE THAT
    THE STORED TEXT IS THE ACTUAL AUTHORED TEXT — not spoken-vs-written. A
    translation is never a teacher's exact words. A quote never appears without its
    restated point beside it. **NO words trimmed at either end — whitespace and
    punctuation only** (SUPERSEDES the earlier "any trimming is recorded" rule;
    the front of a sentence is where negations/conditionals live, and a trim can
    reverse meaning while passing every check). A source must be AFFIRMATIVELY
    cleared — absence of a known problem is not clearance. Cumulative unique
    approved-quote text per work is capped AT APPROVAL TIME (not render-time
    counting). Generated answers carry quote IDs, never text; one server-side
    resolution point serves every surface; revocation is a state change.

17. **The enforceable quote claim.** "A quote cannot be fabricated because the
    model never generates one" is NOT enforceable — withholding source text does
    not stop the writer emitting quotation marks, attribution language, or wording
    recalled from training. Do not record, ship, or publish it. The ONLY permitted
    claim: *text receives verified-quote treatment only through the verified-quote
    component, authorized by a current, approved provenance record.* Supporting
    controls: the prose channel must be prevented from rendering quotation
    typography and verbatim-attribution language; restated points must be
    prevented from carrying quotation markup or first-person teacher
    impersonation.

18. **Position layer cut down — durable stored positions deferred.** The
    single-voice half is Project 2; persistence, rebuild triggers, replace-vs-
    version, review UI, and empty-state redesign are DEFERRED pending real usage.
    The 2026-08-01 corpus-ban lift STANDS (not re-imposed); corpus positions are
    simply not built on. Foundation stays as built. See PLAN.md.

## Session Routing

Determines which path a session's task runs on — not a judgment call. Read
this table first, identify the session type from objective properties of the
task (not vibes), then follow its assigned path. If a task doesn't cleanly
fit one row, it's two sessions, not one hybrid session — split it.

**Hard rule — no exceptions.** Any session that writes to the database, by
any mechanism (a `psycopg2` script, a migration apply, an SQL Editor
statement, a write RPC), runs on the plain script path. Never
`executor`/`planner-reviewer`. This holds regardless of how cleanly a prior
harness session went — the 2026-07-25 document-linking build (migration 071)
was a clean harness result and does not change this rule. Reason: the
harness's write recorder is real ground truth for what it *does* record
(`guard_pretooluse.py`, record-primary since commit `96bc3ff`), but
`BASH_WRITE_INDICATORS` still deliberately over-flags benign Bash calls as
writes (documented, open — `rhemata-status.md`'s "Known Harness Bugs"). A
false-positive write flag costs real data-risk turns on a genuine DB-write
session in a way it doesn't on a repo-only session, where the worst case is
an extra review cycle. (The 2026-07-18 12-turn stall this over-flagging
behavior is related to was itself fixed 2026-07-19, commit `d9ab1cc` — the
residual risk named here is the over-flagging pattern, not that closed bug.)
**Revisit trigger:** once the over-flagging classifier is narrowed (its own
dedicated session, flagged but not scheduled) and a second clean DB-write
harness session is deliberately run and reviewed, this rule gets revisited —
not before, and not by default.

| Session type | Objective trigger criteria | Path | Also load | Skip | Reason |
|---|---|---|---|---|---|
| **Database write** | Any Bash-run script, migration apply, or SQL statement performs INSERT/UPDATE/DELETE/ALTER/schema DDL against Supabase — including via `psycopg2` or the SQL Editor. | **Plain script.** Never harness. | N/A — harness not used | N/A — harness not used | Hard rule above. |
| **Read-only diagnostic / audit** | Zero `Edit`/`Write` calls, zero DB mutation — SELECT-only queries, file reads, greps, read-only script runs. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | No build-then-judge loop needed for a single read-only pass; harness review overhead buys nothing here. |
| **Repo-only multi-step build** | Task ships a working repo change across multiple files and/or multiple ordered steps (new feature, new script plus its own verification, a refactor) — zero DB writes anywhere in the session. | **Harness** (`executor`/`planner-reviewer`). | `HARNESS.md` (always, for harness sessions); `ARCHITECTURE.md` (near-universal for build work); `PRODUCT.md` + `DESIGN.md` only if the task touches UI; `POSITIONING.md` only if it touches copy. | `PRODUCT.md`/`DESIGN.md`/`POSITIONING.md` unless the task's own surface requires them. | This is what the harness exists for — multi-step work that benefits from a planning/review split. |
| **Repo-only single-script / trivial edit** | A single mechanical edit or one-shot script, no multi-step build sequence — zero DB writes anywhere in the session. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | A planning/review loop is overhead a one-shot change doesn't need. |
| **Docs/records-only** | Task's only output is a change to `CLAUDE.md` / `PLAN.md` / `POSITIONING.md` / `DESIGN.md` / `rhemata-status.md`. | **Plain — chat proposes, terminal commits**, per the Project Knowledge Read Contract's propose→commit rule. | N/A — harness not used | N/A — harness not used | Structurally enforced, not just preferred: `guard_pretooluse.py` denies `Edit`/`Write` on all five governed files for any subagent — the harness physically cannot do this work. |

**Stall-risk mitigation for harness sessions (repo-only multi-step build
row):** if a harness session shows the same flagged-item count across ≥3
consecutive turns with no underlying action changing (the 2026-07-18 stall's
signature), abort to the plain path immediately rather than keep retrying —
and log the abort in `rhemata-status.md`'s Known Harness Bugs section with
the turn count and the flagged item, even if you route around it rather than
fixing it that session.

**The upcoming closeness check (Phase 2, paraphrase wording gate) falls
under Repo-only multi-step build → harness**, for the build-and-test work
itself (new detection script, its own verification pass, no DB write). If a
later session runs that check against real corpus data and writes
flags/results back to the database, *that* session is a **Database write**
session and moves to the plain path — same project, different session,
different row, per the hard rule above.

---

## Invariants — violating these reopens a closed hole

1. **Python 3.9.** Use `Optional[str]`, never `str | None`. Railway locks 3.9 via
   `nixpacks.toml`; newer syntax runs locally and breaks in prod.

2. **License gate SQL — preserve in every future RPC edit:**
   ```sql
   EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id
     AND (s.license_status IN ('public_domain','owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')))
   ```
   `safe_mode_on` is read ONCE per plpgsql call. There is NO `IS NULL` arm —
   migration 049 removed it and made `source_id` NOT NULL. Re-adding one is
   fail-open. Gate keys on the entity.

3. **Never delete the sentinel source** `267a09ac-76f3-43fb-901f-3015aef88e22`
   ("Unassigned — needs source", unlicensed/hidden). It is the FK DEFAULT target
   for `documents.source_id`. Deleting it breaks every document resolving to it.
   It looks like an orphaned row during cleanup. It is not. Admin UI hard-guards
   against its deletion.

4. **`is_copyrighted` is unreliable and the gate ignores it on purpose.** Derived
   from folder path; wrong in practice (Derek Prince docs read `false`). Do NOT
   "fix" the gate to read it. Reading the code alone makes this look like an
   obvious improvement. It is a bug.

5. **Propositions are per-script, not DB-enforced.** Unlike `source_id` (NOT NULL
   + sentinel default), nothing stops a new ingest script from skipping
   propositions silently. Any new write path must route through
   `shared_ingest.ingest_document()`. **Verify by grepping the real call site —
   comments and docstrings lie** (`youtube_ingest.py:15` claimed propositions
   "auto-fire"; the call was one level down in `ingest_file()`).

6. **Never fork `normalize_alias_key`.** It must match migration 050's seed
   normalization exactly (lowercase + strip + collapse whitespace) or aliases
   miss silently. One shared implementation in `scripts/source_resolver.py` is
   the contract.

7. **Citable requires a real attributable name.** `citation_mode='citable'` only
   if a real name attaches as source or author. Anonymous/pseudonymous stays
   `silent_context` permanently, even with a real servable `sources` row. "The
   Kneeling Christian" → "An Unknown Christian" (public_domain/shown) is
   deliberately `silent_context`. Do not read it as a sentinel artifact and flip
   it.

8. **Never label a paraphrase rewrite as `owned`.** A rewrite of copyrighted
   source is a derivative. Labeling it owned serves it as safe verbatim and opens
   a hole safe_mode cannot close.

9. **No semicolons inside `--` SQL comments in migrations.** The multi-statement
   runner treats them as terminators; the batch rolls back silently. Verify with
   `SELECT to_regclass('public.<table>')` on a FRESH connection.

10. **An unstamped proposition write is now structurally impossible, not
    merely required.** Added 2026-07-23 as a convention (every proposition
    write must stamp provenance — prompt version label, a fingerprint of the
    exact instruction wording, model — after a leaked worked example required
    a manual text search across every stored row plus git archaeology,
    because nothing recorded which prompt produced what). That convention
    was not enough: the now-deleted `sample_v4_propositions_2026-07-23.py`
    called `store_propositions()` directly with none of the three supplied,
    landing NULL rows — the confirmed reason every one of the 2,409
    pre-2026-07-25 live propositions has NULL provenance (Landmines).
    **Fixed 2026-07-29 (bypass-proofing build):** `store_propositions()` now
    takes `prompt_version` as a REQUIRED parameter — omitting it is an
    immediate `TypeError`, before any DB call happens, never a silent NULL
    write. `fingerprint`/`model` are no longer caller-suppliable at all;
    both are derived internally, deterministically, from `prompt_version`
    (`prompt_fingerprint(prompt_version)` / `EXTRACTION_MODEL`) — the
    fingerprint stays authoritative over the hand-maintained label when the
    two disagree (labels drift; a value computed fresh from the literal
    template text each time cannot), and there is now exactly one place in
    the codebase that decides what gets stamped, not each caller separately
    re-deriving (and potentially mismatching) it. **What remains unclosed,
    disclosed not hidden:** the `propositions` table's provenance columns
    are still NULLABLE at the schema level (unlike `positions`' `NOT NULL`
    columns, Invariant 14) — this enforcement lives at the
    `store_propositions()` function boundary, not a database constraint; a
    caller executing raw SQL directly against the table still bypasses it
    entirely. Any future proposition-writing path must call
    `store_propositions()` itself — never reimplement the insert — to
    inherit this guarantee.

11. **Scripture-reference grounding inside `extract_propositions()` must stay
    unconditional — never make it opt-in — but its strip CRITERION was found
    backwards and is now reversed.** A now-deleted one-off script
    (`sample_v4_propositions_2026-07-23.py`) proved `extract_propositions()`/
    `store_propositions()` are directly callable, bypassing
    `process_document()`'s gates entirely — an opt-out parameter here would
    reopen exactly the hole this fix exists to close, so the check stays
    wired inside `extract_propositions()` itself, no bypass flag, regardless
    of the correction below.

    **The correction (2026-07-28 dry-run,
    `docs/audits/reference_grounding_dry_run_2026-07-28.md`):** the original
    design stripped a reference whenever it could NOT be confirmed
    grounded — which also silently strips references the source genuinely
    gives but the scanner just can't recognize (spoken forms, "chapter N"
    named once with bare verse numbers after). A dry run against 20 real
    documents, before this design was ever used on a live row, found this
    backwards in practice: 85% of what it stripped (33/39) were genuine
    references wrongly removed, running 25–67% loss per document on
    verse-by-verse expository material — exactly Derek Prince's style, the
    corpus's largest block. **No live proposition was ever affected**
    (generation stopped 2026-07-25, before this fix landed 2026-07-28).
    **Standing decision: a reference may only be removed when the source is
    CONFIRMED NOT to contain it — never on mere failure to confirm.** This
    session's own re-wiring precondition is now DONE (2026-07-29
    bypass-proofing build): `extract_propositions()`'s strip step arbitrates
    every UNGROUNDED/UNCERTAIN reference through the three-layer citation
    verifier (`scripts/citation_verifier_layers.py`, live-tested 2026-07-29
    against 42 real corpus items — 78.6% overturn rate, PLAN.md #45.7)
    before stripping: confirmed-absent (arbiter denies) strips as before;
    confirmed-present (arbiter overturns) is kept and logged as an overturn.
    Supersedes the 2026-07-28 "strip on mere failure to confirm" posture
    this invariant originally corrected — that posture is retired, not
    revived. **One narrow, deliberate, disclosed exception:** if the arbiter
    itself cannot run (a live call fails, or the reference genuinely can't
    be parsed even after normalization), the reference still strips,
    fail-safe — judged a lesser harm than a fabricated reference reaching
    users, for this specific, now-rare case only. This is NOT the old
    design revived: the old design stripped on ANY failure to confirm (the
    common case, since no `verse_lookup` was ever available on this call
    path) — the new exception fires only when the much stronger three-layer
    check itself cannot run at all. Provenance is now structural (Invariant
    10) and the allowed-reference-list upstream constraint plus this
    arbitrated strip both live unconditionally inside `extract_propositions()`
    itself — confirmed live, on the exact deleted-script call shape, to hold
    even for a caller that skips `process_document()` entirely.
    **Generation has now resumed and the backfill has run (2026-07-30,
    corrects this invariant's own earlier "still unresolved before
    generation resumes" framing — that precondition language predated the
    run, it is not still open).** PLAN.md #46's human calibration ran and
    closed 2026-07-30, before the run. The full backfill (PLAN.md #17/#49)
    processed 515 documents, 508 succeeded — see rhemata-status.md for the
    complete accounting. **What remains genuinely unresolved, unchanged by
    that run:** the license gate and Precept-Austin lockout are still only
    inside `process_document()`, not structural — a direct caller still
    skips them. **What the run newly surfaced, not previously known:**
    book-length documents (`source_type='book'`) structurally break the
    current single-call, `max_tokens=8192` extraction design — 2 of the 7
    backfill residuals were this class, not the known JSON-escaping defect
    the other 5 share. **All 7 since extracted 2026-08-02** (the 5 sermons via
    the now-fixed parser, the 2 books via the multi-call `process_book_document`
    path): the single-call limitation itself STANDS — the books simply no longer
    go through the single-call path. See PLAN.md #17.

12. **Position generation must stay structurally source-blind.**
    `scripts/positions.py` has TWO — and only two — functions that call the
    LLM to write a position: `generate_position_text()` (teacher scope) and
    `generate_corpus_position_text()` (corpus scope, added 2026-08-01 with the
    corpus serving path). Each takes only a topic, already-paraphrased
    evidence-proposition content (`propositions.content`), and — as plain
    public NAME strings — the teacher(s) that content is attributed to (a
    single `teacher_name` for the teacher function; per-statement `teacher`
    labels for the corpus function, which the divergence rule needs to name
    who holds which view). Neither has a `document_id`/`source_id` parameter,
    and neither opens a database connection, so there is no argument through
    which source/chunk text could reach either. This is enforced by the
    functions' own signatures, not by a prompt instruction telling the model
    to ignore something it was handed. A teacher NAME is not source text —
    passing it, or per-statement teacher labels, does not breach this; the
    breach would be source/chunk TEXT, which no signature here admits. Any
    future position-generation caller, or any future generator, must preserve
    this — a caller that "just needs a bit more context" and adds a chunk-text
    parameter reopens the same live-answer leak the position layer exists to
    close.

    **Naming caution — "position" now names three unrelated things; this
    invariant governs only (a).** (a) The teacher/corpus `positions` table +
    `positions.py`'s generation functions (`generate_position_text` /
    `generate_corpus_position_text`) — the source-blind mechanism described
    above. (b) `backend/app/services/position_papers.py` — the
    shipped house-voice "position papers" feature (baptism/tongues pillars,
    wired into `chat.py`), which by deliberate design DOES read a paper's
    own document/chunk text (`get_paper_body()` reads `chunks`) to answer in
    Rhemata's own voice from Alex's own first-party owned content. That is a
    different, legitimate mechanism — **NOT a violation of this invariant,
    which does not apply to it.** (c) `docs/position_papers/` — draft papers
    for pillars not yet shipped. Do not read (b)'s chunk-reading as breaking
    (a)'s source-blindness; they are separate code paths with separate
    rules. See ARCHITECTURE.md, "Position papers (house-voice answer path)."

13. **Position scope is locked to exactly two values (`'teacher'` |
    `'corpus'`), double-locked — a third scope is still refused twice.** A
    `positions` row's scope is enforced in two independent places that must
    agree: `write_position()` (teacher) and `write_corpus_position()` (corpus)
    reject any other scope via `_assert_permitted_scope()` before opening a
    transaction, AND `positions.kind` carries a
    `CHECK (kind IN ('teacher','corpus'))` constraint (migration 076, widened
    from 073's teacher-only lock) that rejects the insert even if that
    application gate were bypassed or forked. Widening to a THIRD scope
    requires a deliberate code change AND a migration, never a runtime flag.
    **Corpus-wide was BANNED until 2026-08-01, then UNBANNED on Alex's
    explicit decision that day** — **(2026-08-03 posture, per the build-plan settled
    decisions above: that lift STANDS — not re-imposed, constraint not narrowed,
    existing rows not deleted; corpus positions are simply not being BUILT ON,
    because the durable-stored-positions work is deferred — a product posture,
    not a re-ban.)** the #49 backfill (850/857 eligible
    documents, incl. 477 of Derek Prince's) satisfied the precondition this
    invariant originally named. Recorded so a future session reads the widened
    CHECK as a decision, not drift: the original teacher-only lock existed
    because a corpus position authored before Prince's material landed would
    have named whichever teachers happened to already have statements as "the
    corpus" and inverted the day his documents were processed. A teacher
    position names exactly one source (`source_id` NOT NULL); a corpus position
    names none (`source_id` NULL) and derives its contributing teachers from
    its evidence — enforced by migration 076's scope/source coupling CHECK, so
    the schema itself cannot drift into an averaged, unattributed position.
    Contributors are ALWAYS derived from a position version's evidence at
    build/serve time (`contributor_breakdown_from_db()`), NEVER a stored
    taxonomy of which teacher belongs to which family — that standing rule
    (PLAN.md track PL) is unchanged and non-negotiable. **Still open, NOT
    closed by the ban lift:** PLAN.md Open Decision #13 (who owns the
    teacher-vs-corpus scope-boundary judgment call) remains unresolved; the
    threshold that actually decides teacher vs corpus for a topic question
    (`positions.DOMINANCE_THRESHOLD` = 0.60 — a single teacher supplying ≥60%
    of gathered evidence is teacher scope) is a reasoned, overrulable starting
    point, not a calibrated constant — see PLAN.md.

14. **`positions.prompt_version`/`prompt_fingerprint`/`model` are `NOT NULL`
    — keep this discipline for any future LLM-generated-content table.**
    Unlike `propositions`' nullable provenance columns (the reason a fixed
    set of 2,409 legacy propositions has NULL provenance permanently — see
    the Landmines section; every proposition written since 2026-07-29's
    bypass-proofing build, 5,814 and counting as of 2026-07-30, is
    correctly stamped `v3`/`v3.1` and not part of this gap), an unstamped
    `positions` write is impossible at the schema level, not just
    discouraged by convention. Don't relax this for a future table "just to
    unblock a migration" — nullable provenance is exactly how Invariant
    10's hole opened in the first place.

---

## Landmines (live, as of last audit — verify before trusting)

- **A live, unbacked quote guarantee is CURRENTLY SHIPPING (B5 landmine,
  recurring in the present).** `frontend/app/home/page.tsx` (~line 492) still
  states, present-tense: "Every quote is checked character-for-character against
  the source before it can appear — a quote cannot exist in Rhemata unless the
  teacher actually said it… Rhemata structurally can't." No mechanism backs this.
  It is the SAME landmine as the earlier `/sources` incident (a separate component
  left carrying the claim after everywhere else — POSITIONING.md, `/sources`,
  `docs/how-rhemata-handles-sources.md` — was corrected to roadmap framing), NOT a
  historical lesson. Any change to the quote guarantee must sweep EVERY surface in
  the same session. Queued: its own copy-fix session immediately after the
  2026-08-03 records pass. (Records pass was report-only — copy not changed.)
- **The John Bevere source is EMPTY BUT SERVABLE (live query 2026-08-03).** His
  documents and propositions were fully deleted 2026-07-25 (confirmed live: 0
  documents, 0 propositions by author or by source), but the `sources` row
  (`John Bevere`, `unlicensed`/**`shown`**) and 5 `source_aliases` REMAIN — so his
  name still resolves as a real servable source with zero content: the exact
  "verified link to an empty author page" surface the tongues-answer audit named.
  The home page ALSO markets him as a "trusted modern-day teacher" (a living
  minister named with zero corpus material — a live misrepresentation, failure
  mode 2). Both belong in the copy-fix session. Resolves a records conflict: an
  older record implying his material was "fully processed for propositions" is
  stale — it is now zero.
- **Stale chat-side figures/premises — verify against the repo/live DB before
  recording.** Twice on 2026-08-03 a confident chat-side assertion was falsified by
  the repo: the "781 / 91%-Prince+Bevere" backfill figure (already retired) and the
  corpus-ban "still in force" premise (lifted 2026-08-01). When a prompt or chat
  asserts a count, a decision-state, or a plan premise, the repo/live DB is
  authoritative on what currently EXISTS — check before writing it down. Related:
  the scale-deferral trap — the current ~40-concurrent ceiling was never decided,
  it emerged from repeated "defer scale until users" choices; any proposal to defer
  scale work "until there are users" repeats exactly that reasoning (Project 1's
  100-concurrent dial exists to end it).

- **Project 1 async answer path is BUILT and cutover-WIRED, but the traffic
  switch is OFF (Stage 2, 2026-08-04, build `dd71b87`; Stage 1 `82413c9`).**
  `backend/app/services/async_answers/` + `scripts/answer_worker.py` +
  `backend/app/routers/async_chat.py` run a durable Postgres-backed answer queue
  (migrations 078/079: `answer_jobs`/`async_answer_config`/`provider_rate_usage`
  + `corpus_version()`) ALONGSIDE the live `/chat`. **Two-level OFF switch, both
  default OFF:** env `ASYNC_ANSWER_ENABLED` mounts the routes (main.py, deploy-
  level); DB `async_answer_config.serving_enabled` is the seconds-reversible
  TRAFFIC switch the frontend consults via `GET /async-chat/mode`. Do NOT assume
  the async path serves anything until BOTH are on. **DRIFT POINT (unchanged, load-
  bearing):** `async_answers/producer.py` MIRRORS `chat.py`'s retrieval
  orchestration + generation constants (`GEN_MODEL`/`GEN_MAX_TOKENS` + the STRICT
  ATTRIBUTION CONSTRAINT string) AND now its position-paper interception +
  background-topic injection ordering — a change to any of those in `chat.py` that
  is NOT also applied to `producer.py` silently diverges the async answer (the
  accuracy-critical extraction, grounding, `verify_references`, and the
  `evidence_version` = `get_corpus_version()` signal are IMPORTED/shared, so those
  stay in sync). Unify at full cutover. **Remaining BEFORE a real flip (NOT built —
  a flip without these is a regression):** (a) metering/usage-limit parity on
  `/async-chat/submit` (the live path meters guests/users fail-closed; the async
  submit does not) — and each submission must meter independently even when single-
  flight shares one generation; (b) auth→user_id + conversation persistence (the
  worker writes the answer to `answer_jobs` but nothing saves the `messages`/
  `conversations` rows a logged-in user's history needs); (c) `psycopg2-binary` in
  `backend/requirements.txt` (the live backend never imports the async modules so it
  deploys fine, but the worker + `async_chat` router fail to import on Railway
  without it); (d) the DB route — the worker's `SUPABASE_DB_URL` is the session
  pooler (15-client cap, ~14 concurrent/worker), which must move to the transaction
  pooler / a sized route for the 100-concurrent dial. Observed + faithfully mirrored,
  NOT fixed: the live `match_position_paper` over-matches "What is deliverance?" ->
  baptism house voice (a live-behaviour issue, out of scope). `corpus_version()`'s
  one gap: an in-place admin re-chunk edit isn't reflected (reuse defaults OFF, so
  moot until reuse is enabled).

- `ingest_helloao.py` is not routed through `shared_ingest`. Fetches a live
  API and is the real gap.
- **Never run a proposition-extraction pass against "all documents with zero
  propositions" — target a NAMED document set by ID.** That bare query returns
  the 2,176 permanently-excluded Precept Austin word-studies (locked out by name,
  `PRECEPT_AUSTIN_SOURCE_ID`) plus public-domain/owned material the license gate
  skips. The genuine backfill set is only what the ACTUAL gate admits (license IN
  `licensed`/`unlicensed`, not Precept Austin, ≥50 words) — re-derived live
  2026-08-02 as exactly 7 documents, now extracted (0 remaining; build `05aa519`;
  `docs/audits/backfill_reverification_2026-08-02.md`, commit `122ad48`). This is
  the concrete danger the long-stale "781-docs" figure created: a future run must
  enumerate its targets, never sweep the zero-prop set.
- **The corpus has NO record of extraction attempts** — no completion timestamp
  (`documents.ingest_completed_at` is NULL corpus-wide), no status column, no log
  table. "Never attempted" and "attempted and failed" are indistinguishable from
  the database — which is exactly why the stale backfill-target figure survived
  undetected. NOT being fixed (recorded, not built): treat any zero-proposition
  document's history as unknown, never as "awaiting a first attempt."
- **A long model stall can outlast the DB connection and drop it mid-extraction.**
  Observed 2026-08-02: one sermon's reference-grounding stalled ~26 min, the
  Supabase pooler dropped the idle connection, and it succeeded instantly on a
  fresh-connection retry. Any future large extraction run needs reconnect
  resilience (reopen on `psycopg2` `OperationalError`/`InterfaceError` and
  continue), as `scripts/run_full_backfill.py` already does — never run one on a
  single bare connection.
- **Corrected 2026-07-30 — no longer true of the majority of the corpus.**
  A fixed set of **2,409 legacy propositions (created no later than
  2026-07-23) have NULL provenance permanently** — confirmed corpus-wide
  2026-07-28, via the same bypass mechanism described below, and this
  specific set of rows will never retroactively gain provenance (nothing
  rewrites old rows). **But generation resumed and the backfill ran
  2026-07-30**, using the now-closed bypass-proofing (Invariant 10): 5,814
  propositions written since (222 `v3`, 5,592 `v3.1`) all carry correct,
  verified `prompt_version`/`prompt_fingerprint`/`model` — confirmed by
  direct query, not assumed. Provenance stamping (migration 067) never
  fired on an actual write until this session: every write before
  2026-07-30, including all 2,409 legacy rows, went through a since-deleted
  one-off script that called `extract_propositions()`/`store_propositions()`
  directly, bypassing the stamping call site inside `process_document()`.
  The underlying bypass mechanism itself is now closed (2026-07-30) — see
  Invariant 10 — an unstamped write is structurally impossible on any
  future call through `store_propositions()`, not merely discouraged. That
  fix has no effect on the 2,409 rows already in the table before it
  landed; it only guarantees writes from 2026-07-29 onward are stamped. A
  2026-07-23 diagnostic built a reasonably strong circumstantial case for
  what produced the pre-07-23 rows specifically (git history + a
  full-corpus text sweep for one known leak), but that's evidence, not a
  stored fact for those rows. Treat any claim about which prompt version
  produced any row dated before 2026-07-29 as unverified unless re-checked
  by the same method (PLAN.md #45.5) — this caveat does NOT extend to the
  `v3`/`v3.1` rows written 2026-07-30, which carry real, queried-not-
  inferred provenance.
- **Citation-fabrication scale claims from 2026-07-28 are superseded — do
  not cite the 72-reference/64-proposition baseline as ground truth
  anywhere.** The scanner behind that figure
  (`reference_grounding.find_reference_spans()`) only recognizes compact
  "Book N:M" citations and is blind to spoken forms ("Hebrews chapter ten,
  verse twenty-five") and to the dominant expository pattern where a book is
  named once and later citations are verse-only — a manual check on 5/5
  sampled "fabrications" found every one was a genuine reference the scanner
  simply couldn't parse. Genuine citation fabrication now appears RARE: two
  cases confirmed to date by direct full-source reading, from two
  independent detection efforts — Carter Conlon's Matthew 7:21-23 addition
  (2026-07-24, found via a since-rejected similarity-based misattribution
  check) and Leonard Ravenhill's Philippians 4:8-9 citation (2026-07-28, a
  real reference grafted onto the wrong point in the same sermon). A third,
  structurally different case (Savchuk's "Devil's Voice" — an invented
  scriptural-AUTHORITY claim with no actual chapter:verse to check) remains
  confirmed but undetectable by any reference-grounding check by
  construction — nothing to parse. **The spoken-form gap named here is now
  fixed (2026-07-28, `scripts/citation_verifier_layers.py`'s Layer 1,
  commit `ff74a42`)** — but that fix lives in the repurposed
  generation-time verifier (PLAN.md #45.6), not in
  `reference_grounding.find_reference_spans()`, the scanner
  `detect_reference_fabrication.py` actually used to produce the baseline
  below. A trustworthy corpus-wide number still requires an actual
  corpus-wide re-run using the fixed recognition — demoted to later work,
  not scheduled (PLAN.md #45.6). Local, gitignored
  `reference_fabrication_review/corpus_findings.jsonl` holds the stale
  72-item list; treat every entry in it as a review candidate, not a
  confirmed problem. See also Invariant 11 — the strip mechanism this scan
  fed was itself found to have a backwards default; the re-wiring to a
  confirming step is now DONE (2026-07-30), so this specific blocker on the
  backfill is cleared, though other preconditions (PLAN.md #49) remain.
- **The book-name map exists as five independent hand-maintained copies
  that will drift out of sync with each other over time.** A 2026-07-28
  blast-radius survey (the BOOK_MAP ordinal/spelled/Roman-numeral fix,
  commit `ee267d4`) found five separate maps and four live-serving
  consumer sites (the mounted `/study/verse` endpoint, the reference
  verifier on every live chat answer, the Study page's verse-search parser,
  and the chat-answer scripture underliner). All four sites were fixed
  together this pass, but the underlying multi-copy structure wasn't —
  consolidating into one shared map is a parked future session, not
  scheduled. Fixing a book-name bug at only one of the five copies will
  silently leave the other four wrong.
- **`study-reference.ts::detectVerseReferences` (the live chat-answer
  scripture underliner) has a real, pre-existing false-match bug**,
  confirmed live on unmodified `HEAD` 2026-07-28, unrelated to and not
  caused by that session's BOOK_MAP work: it scans free prose for embedded
  valid substrings, so `"I Genesis 1:1"` matches the embedded
  `"Genesis 1:1"` and ignores the leading "I ". Backend sites don't share
  this shape of bug (they parse one anchored, isolated string, not
  free-scanned prose). Unowned, unfixed.
- Some sources have no alias rows; re-ingesting their content sentinels
  silently. `ALIAS_MISS` is the grep-able breadcrumb.
- **No cheap check exists for the demonstrated fabrication class: real,
  accurate content correctly sourced from one named teacher, attached to a
  different named teacher's document.** Tested 2026-07-24: a similarity-based
  check (does a proposition's meaning match something in its own document)
  was built, run corpus-wide, and rejected — confirmed-accurate propositions
  routinely scored as extreme as or more extreme than the one known real
  fabrication, so no cutoff separates them. A names/numbers/citations-present
  check remains worth building but is blind to this exact failure by
  construction — the known fabrication contains no checkable specifics at
  all. Don't treat either check, if one gets built, as covering this failure
  class without re-confirming against it directly.
- **Delete account is a stub, not real deletion.** `POST /account/delete-request`
  only inserts a row into `deletion_requests` for manual admin follow-up
  (Admin panel → Contributors → "Account Deletion Requests"). No cascading
  deletion of `conversations`, `saved_words`, `pastors_cards`, `user_roles`,
  or the Supabase auth user exists anywhere in the codebase. A submitted
  request means nothing has been removed yet.
- **YouTube ingestion has stopped — Alex's decision, 2026-07-25.** Do not run
  `run_queue_triage.py` / `run_queue_ingest.py` or otherwise pull new YouTube
  material without checking with Alex first. Vlad Savchuk and Zac Poonen — 61%
  of the current propositions layer between them — both entered via this
  route; a stale-looking ingest queue is a decision, not an oversight. See
  `PLAN.md` #44 for the reason (duplicate clip/full-sermon content found the
  same day).
- **No mechanism exists anywhere in this schema to link two documents as one
  work.** The standing "link, don't merge" policy for split-work groups and
  duplicate clips (`PLAN.md` #44) has no table or column backing it yet —
  confirmed by a direct schema check 2026-07-25. Don't assume a linked-work
  concept is queryable; it has to be designed and built first.
- **Book-length extraction now has a real, committed path — but it only
  reliably covers 8 of the corpus's 53 book documents.** `split_book_into_chapters()`/
  `_extract_and_store_book_chapters()`/`is_front_back_matter()` (commits
  `d7c46f5`/`b4ab601`, plus the byline/apparatus/digit-ratio correction
  pass `8e251c8` below) chapter-scope extraction for books whose real
  chapters repeat their own title — proven live on 7 public-domain books
  (the original 6, plus John Wesley's "The Journal of John Wesley" —
  1,249 propositions, real write, 2026-08-01), now real propositions. A
  second detector for the other 45 (roman-numeral or bare "Chapter N"
  headings) exists in the working tree but is **deliberately uncommitted
  and has zero production callers** — it found a confident-wrong-answer
  failure mode twice (fixed once, a second mechanism found no clean fix)
  and is not safe to wire in without per-book verification. Do not assume
  `detect_book_chapters()` is live just because it exists in
  `propositions.py` — check for actual callers. See PLAN.md #50 and Open
  Decision #21.
- **CORRECTED 2026-08-01 — no longer an open decision.** The two live
  imperfections below (originally found 2026-07-31) are now fixed at the
  data level, not just in code: commit `8e251c8` shipped the byline/
  apparatus/digit-ratio fixes described in the entry below this one, and a
  same-session DB-write pass used them to correct both books directly,
  independently re-verified against a fresh connection (not the
  correction script's own self-report). "The New Life": the 3 specific
  propositions (of 411) that came from the Translator's Note were
  identified via `proposition_chunks` chunk-linkage (disambiguated from
  10 genuinely-Murray Preface propositions that merely shared one
  boundary chunk) and deleted — 411 → 408 live propositions. "The Lord's
  Table": "VII. Saturday" (57 real words, confirmed to have zero existing
  propositions, same disambiguation method) was extracted and stored as
  proposition_index 149 — 148 → 149 live propositions. See
  `rhemata-status.md`'s "Live-DB corrections + Wesley's Journal real
  write" entry for the full evidentiary detail. PLAN.md Open Decision #22
  should be closed to match — original text left below for the historical
  record, not because it's still open:
  - Two book documents already have live propositions with small, known,
    uncorrected defects (found 2026-07-31, fixed in code for future
    extractions, not retroactively repaired). "The New Life" (Andrew
    Murray) has a translator's note misattributed to Murray among its 411
    live propositions. "The Lord's Table" (Andrew Murray) is missing one
    real ~57-word entry ("VII. Saturday") that a since-fixed bug wrongly
    excluded before the book was written.
- **The third-party-attribution byline detector built to fix the Wesley
  misattribution bug is over-broad and unproven beyond one book — still
  true after committing.** `_has_third_party_byline()` (now committed,
  `8e251c8`, 2026-08-01 — no longer sitting uncommitted as this entry
  originally said) fires on any short line-start "By [phrase]" that
  shares no words with the document's known author — NOT specifically a
  named-person credit. Confirmed it would also fire on "By faith alone"
  or "By the grace of God." No false positive occurred on the one book
  tested (Wesley's "Journal," now proven twice: the original storage-
  disabled dry run, and the real storage-enabled write, 1,249
  propositions, 2026-08-01 — 3 of its front-matter exclusions fire via
  this exact detector, independently re-confirmed against the live DB via
  `proposition_chunks`), but a genuine content span opening with a short
  "By..." epigraph or hymn line would be wrongly excluded by this exact
  mechanism. Do not extend this to more books without hardening it first
  (e.g. requiring the credited phrase to look like a capitalized personal
  name).

**Corpus counts are never documented here.** Query live — any static number rots
within days and has already caused one round of false blockers.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (React 19), Tailwind 4 → Vercel |
| Backend | Python 3.9 / FastAPI → Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, set explicitly) |
| Answer generation | Anthropic `claude-sonnet-4-5` via `anthropic` SDK |
| Query expansion / metadata / tagging / transcript cleaning | Groq `llama-3.3-70b-versatile` |
| Reranking | Cohere rerank-v3.5 — top 30 RRF → top 8 |
| Vision / OCR | Gemini 2.5 Flash |

---

## How to Work on This Project

- Alex works fast — short messages, direct feedback.
- Surface risks before building, not after.
- All code changes stay in Claude Code. Don't suggest manual edits unless trivial.
- Read output directly — never ask Alex to copy-paste terminal output.
- Check actual files before assuming structure.
- Never log planned work as done. Never claim build state you can't see.
- **Any LLM run with meaningful per-item cost across the corpus** — surface
  a cost estimate to Alex BEFORE running, design it to run once rather than
  iterate live against the corpus, and treat $50 as a hard ceiling unless
  Alex explicitly approves exceeding it.

---

## Project Knowledge Read Contract

State lives in repo files. No Notion mirroring, no sync step (retired 2026-07-09).

| File | Owns |
|---|---|
| `CLAUDE.md` | This file. Invariants, stack, working rules. Always loaded. |
| `ARCHITECTURE.md` | Tree, schema, scripts, env vars, commands. Load on demand. |
| `HARNESS.md` | Executor/planner-reviewer gate design. Harness sessions only. |
| `POSITIONING.md` | Messaging, voice, product posture. Source of truth. |
| `PRODUCT.md` | Who it's for, brand register, design principles, anti-references. Read before UI work. |
| `DESIGN.md` | Styling-token authority. No hardcoded hex. |
| `PLAN.md` | Roadmap, standing session rules, open decisions, findings log. |
| `rhemata-status.md` | Live state only. Overwritten each session. Never durable truth. |

**Writer rules:** terminal authors and writes `CLAUDE.md`, `ARCHITECTURE.md`,
`HARNESS.md`, `PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — from
confirmed-working builds only. `PLAN.md` content is chat-originated: chat decides roadmap, terminal writes
it verbatim. Terminal is the pen, not the author. Chat never edits any file
directly.

**Eviction rule for this file:** every line must change what you'd do on a normal
task. If a line describes the codebase accurately but wouldn't stop a mistake,
it belongs in ARCHITECTURE.md. If a decision is superseded, **delete it** — do
not stack a correction on top. Git is the provenance record. This file reached
12,000 words because nothing was ever removed, only appended to.

**Repo root is reserved.** Only these markdown files may live at root:
`CLAUDE.md`, `ARCHITECTURE.md`, `HARNESS.md`, `PLAN.md`, `POSITIONING.md`,
`PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — plus tooling config. Every other markdown
file goes in a folder: audits and one-off reports to `docs/audits/`, marketing
source markdown to `docs/`. A new file at root is a mistake, not a decision.
`CLAUDE.md` must stay at root — Claude Code looks for it there.
