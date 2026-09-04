# New Wine — Private-Beta Blocker Plan

> This is the only active work queue. Later work lives in `docs/roadmap.md`;
> completed and superseded reasoning lives in `docs/plan-archive.md`.

**Goal:** private beta ships with an accurate, guarded answer journey. The
quote rail is **OFF** by Alex's 2026-08-25 decision because its accuracy and
relevance are below the desired bar; re-enablement requires the Scheduled
repair gate in `docs/roadmap.md` plus Alex's attended approval. Web-article
ingestion remains an attended parallel track.

**Current item: B8 — prose quotation enforcement** (promoted
2026-09-04, self-inflicted the same session). **Active blocker count: 1.**
B7 is DONE and live (2026-08-31): migration 095 applied and independently
verified from a fresh connection, all four Railway services deployed at
`6e0bb4a`, full path re-proved in production after the deploy. Quote repair
remains Scheduled, not an active Blocker.

**B6-F1 is DONE** (2026-08-26). The activation flag was flipped to `true` and
its wiring code was found to have been drafted but never actually deployed
(only the migration and `producer.py`'s underlying correction were live);
committed and deployed same day, commit `77fbb52`. A live smoke check against
the exact reproduction question confirmed the fix — see the closed entry below.

**2026-08-31 (attended, three outcomes; one promoted a Blocker).** (1) The
deferred analytics production smoke ran and passed: search analytics genuinely
record and process end to end, proven by live submission plus independent
read, not by code reading —
`docs/audits/2026-08/analytics_production_smoke_2026-08-31.md`, commit
`fe1026f`. Five residuals are named there and all remain unverified, chiefly
personal-wording redaction and the retention purge actually firing; none
blocks the beta journey. (2) `scripts/verify_metering_live.py` was guarded
against accidental production writes (`--apply` required, import
side-effect-free, proven by tripwiring every I/O entry point), commit
`a395efb`, then renamed out of the `test_*.py` namespace on Alex's approval so
it stops advertising itself to other plans as the pattern to copy. (3) The
fail-closed coupling that the smoke surfaced was investigated, **promoted to
Blocker B7 on Alex's decision**, then fixed, applied, and deployed the same
day — decoupling, missing-data marker, and timeout, all live. B7 is closed.

**B6 general answer-latency — DONE, live (2026-08-27), not a Blocker item.**
Never promoted past `docs/roadmap.md`'s Scheduled B6 latency work; recorded
here only as a pointer. `output_config.effort="medium"` is now hardcoded into
every real answer generation (commits `07f6922`→`f00b303`): 25.46% faster
median producer time on the fixed 12-case paired benchmark, no p90
regression, zero hard failures on a targeted 6-pair blind quality review.
Full trail: `docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

## Governing boundary

- A new finding interrupts this queue only if it can plausibly cause theological
  error, teacher misrepresentation, data loss, a security/privacy breach, or
  failure of the core beta journey. Everything else is classified Scheduled,
  Triggered, or Parked in `docs/roadmap.md`.
- Audits and implementation tasks use named files, acceptance tests, and a stop
  condition. Adjacent findings are recorded; they do not expand the session.
- Repository-only work may run back to back. Production database writes,
  deployments, source-visibility changes, and quote-rail re-enablement are
  attended gates requiring Alex's explicit approval.
- Every write path follows dry run → one isolated hidden proof → reconciliation
  → explicit release → bounded batch. No general worker may claim an unrelated
  row during the isolated proof.
- Corpus-scale LLM quote propose runs require a **named cost estimate** before
  execution and a **$50 ceiling** unless Alex explicitly approves more.

## Active blocker sequence

### B8 — Prose quotation enforcement

**Status: REPOSITORY COMPLETE; attended production smoke and deployment
pending. Created by this repo's own 2026-09-04 re-ingest; Alex approved the
stricter closure design on 2026-09-04.**

Rebuilding 79 sermon documents from raw json3 captions (`b641898`) removed
sentence terminators from 20 of them, adding 391 chunks without sentence-ending
punctuation to the 337 already present. Three of those documents contain none
of `. , ; : ! ?` at all.
`prose_quotation_guard.normalize_for_match()` folds quote characters, dashes,
ellipsis and whitespace but **not sentence punctuation**, so a writer quoting
those documents accurately and punctuating naturally fails the exact-substring
match and drives regenerate-once-then-refuse.

**Evidence, verified live** against a rebuilt Kolenda chunk: quoted verbatim →
passes; the same words with a comma and a full stop added → flagged ungrounded;
with only a full stop added → flagged. An earlier audit found four defective
quotations across five answers, establishing real use of this path but not its
live refusal frequency.

**Affected surface:** the core beta answer journey — correct answers refused.

Review found that a global punctuation fold is too broad and that the current
guard has a pre-existing author-scope defect: it concatenates all retrieved
teachers' text, so teacher B's words can falsely ground a quotation attributed
to teacher A.

Alex chose the governing rule already recorded in `CLAUDE.md` Settled #17 over
making source matching more permissive: verified-quote treatment belongs only
to the verified-quote component. Ordinary answer prose may paraphrase teachers
but may not render an attributed teacher quotation.

**Smallest closure condition:** deterministically reject every double-quoted
span of at least five words attributed to a permitted citable source, without
consulting evidence text. Preserve the existing exclusions for Scripture,
negated hypotheticals, short terms/scare quotes, and unattributed prose; bind
multiple nearby names to the nearest preceding source. The existing
regenerate-once-then-refuse remedy remains unchanged. Credential-free
regressions must prove exact-source, punctuation-altered, nested, and fabricated
teacher quotations are all rejected while every deliberate non-target remains
excluded. Production smoke and deployment remain separate attended gates.

**Non-goals:** sermon passage filtering, Ravenhill corpus writes, transcript
rewriting, deployment, and any model-based answer-path judge.

**Superseded repository proof (2026-09-04, `1f775ac`):** author-scoped,
strict-first matching passed 32 quotation-guard checks, 17 generation-contract
tests, 21 routing tests, and syntax compilation. Before deployment, review found
that this still contradicted Settled #17 and left nested quotations unresolved.
Alex chose the stricter no-attributed-quotation policy; `1f775ac` remains useful
history but is not the release candidate.

**Current repository proof (2026-09-04, `d1ac57a`):** the guard no longer
accepts evidence text and deterministically rejects attributed prose quotations
whether exact, punctuation-altered, fabricated, or nested. The existing
Scripture, negated-hypothetical, short-term/scare-quote, and unattributed-prose
exclusions remain. Python 3.12 verification passed 25 quotation-guard checks,
17 generation-contract tests, 21 routing tests, and syntax compilation. B8
remains active until an explicitly approved production smoke and deployment
verify the live answer path.

**Promoted on the documented bar** (concrete failure, live evidence, named
surface, named closure) with no current item to displace. Downgradeable by
Alex. Full detail and reviewed implementation stages:
`docs/superpowers/specs/2026-09-04-sermon-passage-quality-design.md`.

### B7 — Fail-closed analytics → answer coupling

**Status: DONE and live (2026-08-31, attended).** All three items are
deployed and verified in production.

Closing steps, both performed this session:

1. Migration 095 applied — its own script passed 9/9, then verified
   INDEPENDENTLY from a fresh read-only connection: column present and
   nullable, partial index present, CHECK enforcing the closed set, and all
   47 pre-existing rows untouched (`marked=0`).
2. Deployed. `6e0bb4a` pushed; `rhemata`, `answer-worker`,
   `search-analytics-finalizer`, and `search-analytics-retention` all reached
   `SUCCESS` on that commit. No frontend file changed in the four commits, so
   Vercel was a genuine no-op rather than an unchecked assumption.

Post-deploy production proof, not inference: a real submission through the
live endpoint returned `200 {"reason":"created"}` and completed
`outcome=answered` on `claude-sonnet-5` with a 2,654-char answer
(`$0.062`) — so the rewritten `/submit` path serves answers on the deployed
code. It was a guest submission, which also exercised the
`SKIPPED_GUEST` branch live: `search_occurrences` stayed at 2 and no marker
was written. `scripts/analytics_health_report.py` now runs against the live
schema and reports both traffic hours as `healthy, 0 unrecorded` — the
distinction that did not exist before this work.

**One thing deliberately not claimed:** the marker has never actually fired
in production, because nothing has degraded since it went live. Its write
path is proven by the 50-check suite against the real code and its column and
CHECK are verified live, but "observed marking a real outage" is not
something this session could manufacture, and is not claimed.

**Item 2 — decoupling. DONE (`f2ee6ff`).** When analytics cannot be reached,
or consent state cannot be determined, the system does not record and answers
anyway. All three calls moved behind `recording.record_search_occurrence()`,
which never raises; the router has no except clause by design. Both privacy
protections preserved exactly — unknown consent never resolves to
"consented," and nothing is written under a key `withdraw()` could not find.
Only the consequence of a refusal changed, from "no answer" to "no row."
`enforce_query_limit` untouched and still fail-closed; guests unchanged.

**Item 3 — marker. BUILT, NOT LIVE.** Migration 095 adds
`answer_jobs.analytics_outcome`, stamped only on a degraded outcome, so
"analytics was down for these hours" stops being indistinguishable from
"nobody searched." Lands over direct Postgres, which survives a PostgREST
outage, on a row guaranteed to exist because enqueue already succeeded over
that same connection. Carries no question, no fingerprint, no subject key,
and `answer_jobs` has no `user_id`, so it creates no account-to-search
linkage. Read it with `scripts/analytics_health_report.py` — no
`newwine_readonly_analysis` grants needed, and those stay deferred.

**Item 4 — timeout. DONE (`f80d4a2`).** No timeout existed anywhere on this
path, so a hung dependency stalled the request under any remediation. Now 5s,
taken from `pastors_notes.TAGGING_TIMEOUT`'s precedent (auxiliary enrichment
on a user-facing path, non-fatal if exceeded) rather than invented, applied
where it interrupts I/O: a dedicated analytics Supabase client and an opt-in
`Db(statement_timeout_ms=...)`. The worker's Db carries no budget. A
`QueryCanceled` is excluded from `Db.run`'s retry, which would otherwise have
silently doubled it.

**Proof:** `scripts/test_analytics_answer_decoupling.py`, 50 checks, each
failure mode driven against the real `submit()` and asserted twice — answer
served, and nothing recorded, the latter observed from actual INSERT
statements. Mutation-verified: each guard reverted in turn fails the suite,
including guard 1 recording an unconsented user.

**User-facing half of the audit's (e): resolved by removal, copy untouched
per Alex.** `analytics_unavailable` no longer exists in any code path, so the
mislabel where an analytics failure surfaced to the user as `queue_full` is
gone — those failures no longer reach a user at all. The remaining 503s are
`async_serving_disabled` (own message) and a genuine `queue_full`, which is
now accurate whenever it appears.

*Investigation (2026-08-31, no fix designed at the time) below.*

The problem: an analytics-subsystem failure takes answers away from real users.
`POST /async-chat/submit` makes three blocking analytics calls
(`async_chat.py:215-248`) *after* the quota is spent and the job is already
enqueued. On failure the caller never receives its `job_id`, so the worker
still generates and pays for an answer nobody receives.

What the investigation changed about the premise, both worth knowing before
anyone scopes a fix:

- **It is not one fail-closed branch, it is three, and only one is
  deliberate.** `create_occurrence` is guarded and returns 503
  `analytics_unavailable`. The two consent reads before it have no `except` at
  all and produce an unhandled **500**.
- **It is not limited to consented accounts.** The consent *check* is itself
  unguarded and runs for every signed-in user, so an `analytics_consent` read
  failure removes answers from users who never opted in and from users who
  explicitly withdrew. Guests are fully immune.

Two of the three branches are protecting something real and must keep failing
closed **with respect to recording** — unknown consent must resolve to "not
consented," and no occurrence may be written that `withdraw()` could not later
delete. Neither protection requires withholding an answer; the coupling exists
because "skip the write" and "reject the request" were never separated. The
third branch protects analytics completeness only — a product-quality goal, not
a privacy or safety one.

Blast radius today: no error monitoring of any kind exists, the healthcheck
(`healthcheckPath = "/"`) stays green throughout, the client reports the
failure to the user as "Something went wrong. Please try again" while
internally mislabelling it `queue_full`, and that copy plus the failed-turn
strip actively invites retries that each burn quota and another generation.
The analytics feature cannot detect its own outage, because "no rows written"
is indistinguishable from "no traffic" — the exact ambiguity Phase A of the
2026-08-31 smoke ran into.

Also latent, and it should gate any key rotation: branch 2 becomes a live
outage the moment `CURRENT_SUBJECT_KEY_VERSION` is bumped. Separately, no
timeout is configured anywhere on this path, so a hung dependency hangs the
request under any remediation.

Six remediation options with explicit tradeoffs, none recommended:
`docs/audits/2026-08/analytics_answer_coupling_2026-08-31.md`.

### B6-F1 — Named-teacher/stored-position route collision

**Status:** DONE (2026-08-26). A Derek Prince deliverance question was being
intercepted by topic-only stored evidence from Vlad Savchuk and cleanly
refused after two attribution failures. The source-boundary correction
(teacher identity resolved via canonical `source_id`, enforced before/after
neighbor expansion, evidence capped at 12 chunks) passed its targeted blind
human quality review — Alex recorded **ACCEPT** 2026-08-26, no protected-axis
hard failure across both relevant blind pairs. (Separately, the same
candidate was rejected 2026-08-25 as a suite-wide *latency* direction — only
2.81% median improvement against the required 20%; that finding stands,
unrelated to this closure.)

Migration 091 added the activation flag; Alex flipped it to `true`
2026-08-26 (attended). The flip initially had **zero effect** — the wiring
code that reads the flag (`config.py`) and threads it into the real
`produce()` call (`answer_worker.py`) had been drafted but never actually
committed or deployed, despite this file previously describing it as
"wired." Found via a live smoke check, not assumed: the exact reproduction
question still returned `refused_attribution` after the flip. Fixed same
day, commit `77fbb52`, deployed to Railway `rhemata` + `answer-worker`. A
second live smoke check against the identical reproduction question then
confirmed the fix genuinely works: `outcome=answered`, 12/12 citations
attributed to Derek Prince alone, zero attribution retry.

Full evidence and timing: `docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.
Any suite-wide latency direction remains separate Scheduled B6 work
(`docs/roadmap.md`) and needs a mechanism that addresses the generation
bottleneck across the whole suite, not just named-teacher routing.

### W1–W4 — Safe web-article runway

**Status:** DONE — merged to `main` 2026-08-18 (PR #1
`harness/quote-containment-and-staging`, closing commit `a8a7731`, merge
`923f1ed`). Quote-rail flag (default off), single-row `--row-id` claiming, the
staged web-article contract, and the zero-write preview all verified live
against the merged code. Full detail: CLAUDE.md Invariant 16 + the
quote-containment Landmines entry.

### Q0 — Quote quality design accepted (launch-critical)

**Status:** HISTORICAL DONE 2026-08-19 — revised spec committed (`95c7ae0` and
follow-ups). The former decision that beta ships with quoting on was
superseded by Alex on 2026-08-25: the rail is off until accuracy and relevance
are repaired. Existing quote safety constraints still govern any future
re-enable.

Decisions locked in the spec + CLAUDE.md Settled #29:

- LLM propose + quality/serveability gate + authenticity verify (quality gate
  is an explicit authorized exception; wrong both ways; logged).
- Topic labels = existing taxonomy (`scripts/taxonomy.py` / `docs/taxonomy.md`),
  passage-level — not a new vocabulary, not document-tag inheritance.
- V1 selection = question ↔ `quote_text` only; tag soft-boost deferred.
- Legacy 793 = **live-but-unserved** while rail is off during build; gold set
  before selection-ineligibility; presentation before re-enable.
- Boundary overrun must be root-caused and hardened **before** rebuild writes.
- Alex authorized Grok to implement this track (2026-08-19); production
  quote writes and rail re-enable remain attended Alex gates.

### Q1 — Pre-implementation gates + implementation plan

**Status:** DONE enough to execute — boundary harden + plan landed 2026-08-19.

- [x] Spec accepted; Settled #29 recorded (quality-gate exception + taxonomy).
- [x] Vocabulary source chosen: reuse `scripts/taxonomy.py` `VALID_TAGS`
  (human ref: `docs/taxonomy.md`) — no second list.
- [x] Implementation plan written (Grok, Alex-authorized):
  `docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md` with named
  gold-slice cost band (~$15–40 / 10 docs; full Prince non-book out of
  ceiling).
- [x] Boundary root-cause + verifier harden (`9a4c141`):
  `internal_paragraph_break` — live evangelist overrun refuses; first
  paragraph control passes; `test_quote_verifier.py` all green.
- [x] Alex authorized Grok to run this plan (this session).

### Q2 — Gold extract + presentation + legacy selection-ineligibility

**Status:** DONE 2026-08-19 — gold + eligibility + presentation + Claude
visual/taste polish (`9b7fb45`).

- [x] Costed dry-run propose + calibration note (paid #2: 27 verify-pass /
  ~$1.42 / 59 windows) —
  `docs/audits/2026-08/quote_propose_calibration_note_2026-08-19.md`.
- [x] Schema committed + migration 089 applied (topic_ids /
  quality_pipeline_version / selection_eligible; legacy
  selection_eligible=false).
- [x] Attended gold write on 3 calibration docs (`--limit 3 --apply
  --status pending`) + hard reconciliation — **stored=28**,
  refused_quality=11, refused_verify=3, errors=0; later promoted
  pending→approved (28/28) for re-enable.
- [x] Selection eligibility = new-pipeline/gold only in code.
- [x] Presentation code + Settled #28 polish: attribution leads; lifted
  `bg-popover` card; outline topic chip (`9b7fb45`, DESIGN.md token).
- [x] Legacy 793 selection-ineligible via migration 089 backfill (rows
  remain; unselectable).

### Q3 — Regressions + attended quote-rail re-enable

**Status:** HISTORICAL DONE 2026-08-19 — flag on + smoke gold-only + polish
landed. Superseded operationally 2026-08-25: `QUOTE_SELECTION_ENABLED=false`
on both production services; the flag-off delivery contract was re-verified.
(Absorbs prior W8 quote proofs.)

- [x] Flag-off regressions: baptism FP class; honest no-support; exact
  chunk IDs; **no bad quote IDs**; bounded teacher-card (no quote rail);
  eligibility mutation. Article-supported answer proof deferred until
  W5–W6 lands a live article.
- [x] Pending→approved for the 28 gold rows (attended; 28/28 reconciled).
- [x] Attended `QUOTE_SELECTION_ENABLED=true` on Railway `rhemata` +
  `answer-worker` + smoke — job `6e1e0b62-…`,
  `policy_v3:quote_selection=true`, 3 quote IDs all
  `quote_quality_v1` / approved / selection_eligible; resolve returns
  work_title + topic_ids + restated_point.

### W5–W6 — One quarantined article proof

**Status:** DONE 2026-08-19 — write + eligibility + shown + answer-integrity
smoke all closed.

- [x] Alex selects the exact article, confirms teacher/source and clearance, and
  approves deploying quote containment.
  (pastorvlad.org prayer-language; staging `Vlad Savchuk (web staging)`;
  live Savchuk unchanged; quote rail already on / gold-only.)
- [x] Full no-write preview + Alex accept
  (`docs/audits/2026-08/w5_savchuk_web_article_preview_2026-08-19.md`).
- [x] One row-pinned write + reconcile (doc `c97533db-…`: 1/1/0/0; 4 chunks;
  12 props; 0 quotes) —
  `docs/audits/2026-08/w5_savchuk_web_article_write_2026-08-19.md`.
- [x] Idempotent rerun (skipped=1) + rollback procedure documented
  (`export_restore_document.py`; not executed — article retained).
- [x] Eligibility: Alex taste-pattern KEEP P1/P3/P7/P12 (4 true / 8 false) —
  `docs/audits/2026-08/w5_savchuk_eligibility_review_2026-08-19.md`.
- [x] Staging visibility → `shown` (Alex); `match_chunks` probe hits all 4
  article chunks for a prayer-language question.
- [x] Answer-integrity / article-supported async smoke — job
  `94cf9284-be14-481c-8f4c-38e2c4fdb81c`; 2 article chunks retrieved + cited;
  prose tracks article; speaker label still “Vlad Savchuk (web staging)” on
  citations (optional rename, non-blocking) —
  `docs/audits/2026-08/w5_savchuk_article_answer_smoke_2026-08-19.md`.

### W7–W8 — Quote and answer integrity (partially superseded)

**Status:** Relevance + idempotency DONE (`82ec0f5`). Remaining work folded
into Q1–Q3 above.

- [x] Passage-level relevance + deterministic tie-break + idempotent create.
- [x] Teacher scope OPEN — Settled #28; presentation required before re-enable.
- [x] Visible label policy — **semantic topic** (taxonomy tag) on the topic
  chip; **work/source title** on the attribution line (spec).
- [x] Legacy audit ran; disposition = live-but-unserved during build, then
  selection-ineligible before re-enable; rebuild via new pipeline (not
  salvage-in-place as v1).
- [x] Candidate origin for bulk Prince path — **mechanical** (not LLM); closed
  by read-only pipeline map 2026-08-19.
- [ ] Boundary overrun investigation — moved to **Q1** (must precede rebuild).
- [ ] Answer-integrity proofs + re-enable — moved to **Q3**.

### W9 — Recoverability and first small batch

**Status:** DONE 2026-08-19 — inventory + named 3-article batch write/reconcile/
shown + eligibility (**12/24** KEEP, Alex-approved).

- [x] Record authoritative Supabase backup/PITR retention, restore granularity,
  owner, RTO/RPO, and exclusions; prove the safest available restore scope or
  record Alex's explicit acceptance.
  (`docs/audits/2026-08/w9_recoverability_inventory_2026-08-19.md` — dashboard:
  scheduled daily physical backups enabled, 7 days visible, PITR disabled;
  Alex accepted ~24h RPO and unproven project RTO without a restore drill.)
- [x] Run one named, costed, resumable web-article batch with immutable inputs,
  logs, hard reconciliation, quality sampling, and an explicit release decision.
  Active trio (Vlad bylines): tenways, planted-not-buried, signs-the-enemy…
  — queue **3/3/0/0**; staging `shown`; Lana row quarantined; eligibility
  **12/24**. Manifest + write audit:
  `docs/audits/2026-08/w9_web_article_batch_manifest_2026-08-19.md`,
  `docs/audits/2026-08/w9_web_article_batch_write_2026-08-19.md`.

## Explicitly outside this finish line

- **Triggered / Scheduled later:** tag soft-boost in quote selection (after
  measurement); full Prince corpus rebuild beyond the gold slice; New Wine OCR
  resume; product B1–B7; corpus A1–A6.
- Migration 088 is already applied. Its isolated processor proof completed on
  queue row `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99`; never reapply it.

## Session close

Record only the original outcome, its acceptance result, classified discoveries,
Alex-approved scope changes, and the next single item. Track: original outcome
completed, unplanned investigations started, findings promoted to Blocker, and
active blocker count. Healthy target: completed, zero, rare, and one.
