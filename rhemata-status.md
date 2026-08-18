# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (handoff). `main` tip includes quote-quality
track through Task 8 Step 1 (`1eec654` regressions) and handoff docs
(`57faa67`). Migration 089 applied. Next single item: attended Task 5
gold `--apply` on the 3 calibration docs — **wait for Alex’s explicit
go**; do not flip `QUOTE_SELECTION_ENABLED`. Untracked
`Temporary-assets/` and `docs/audits/quote_quality_sample_2026-08-19.md`
remain deliberately uncommitted.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Handoff (do not `--apply` without go):** Task 5 gold write on the 3
calibration Prince non-book docs (~59 chunks, ~$1.42). Command after
explicit go:

`PYTHONUNBUFFERED=1 python3 scripts/extract_quotes_quality_pipeline.py --limit 3 --apply --status pending`

Expect ~mid-20s pending rows (`quote_quality_v1`, `selection_eligible=true`,
`topic_ids` set). Rail stays off. Already done on this track: Tasks 1–4,
6–7; Task 5 script wired; migration 089 applied; calibration #2 = 27
verify-pass; Task 8 Step 1 flag-off regressions. Still after apply: hard
reconciliation, Alex QuoteRail visual sign-off, attended re-enable.

Refs: `docs/superpowers/plans/2026-08-19-quote-quality-and-topic.md`,
`docs/audits/quote_propose_calibration_note_2026-08-19.md`,
`scripts/extract_quotes_quality_pipeline.py`.

Rhemata uses the Beta Critical Path model; Codex is the primary surface.
Custom multi-provider coordinator / overnight harness remain retired.

Planning is now split by operational purpose: `PLAN.md` is the short active
Blocker queue; `docs/roadmap.md` contains Scheduled, Triggered, and Parked work;
`docs/plan-archive.md` contains completed and superseded history. Ordinary
sessions do not load the roadmap or archive unless the task needs them.

`codex/source-ingest-runner` is deployed through release `0925c93`. Migration
088 is applied. Queue row `8e8f23e0-7dc6-4057-aa4d-c07f1b607c99` completed an
isolated processor proof into document `35b53381-2153-4936-a97b-641a20e29205`
(two chunks, zero propositions because the source is public domain). No Railway
source-worker service exists; this was not a deployed-worker proof.

Alex replaced the old F2→F3→F4→F6 order after an ultra adversarial review with
the controlled web-article path (PLAN.md W1–W9). **W1–W4 (the repository-only
safety block) merged to `main` 2026-08-18** and is verified live in the code,
not just claimed: quote selection is now contained behind a default-off,
exact-opt-in flag (`QUOTE_SELECTION_ENABLED`) whose effect holds across fresh,
cached, idempotent-redelivery, and in-flight answers; live `--row-id` worker
execution is restricted to `--once` with parameterized, no-fallback single-row
claiming (a target row that isn't claimable returns no row, never a silent
substitute); hidden `web_page + single + declared` staging is now available
for existing non-sentinel sources with `license_status IN
('licensed','unlicensed')`; and a deterministic, zero-database-write
full-compute preview pipeline (metadata → chunks → embeddings →
propositions/provenance → usage evidence → proposal-only quote spans) exists
and is mutation-tested to prove it never writes. Full technical detail:
CLAUDE.md Invariant 16 and the new quote-containment Landmines entry.

**2026-08-18 (repo-only, no DB writes):** W7's first two items are DONE
(`82ec0f5`) — quote-selection relevance is now scored from each quote's
own `quote_text` instead of the inherited document topic tag that tied
every quote in a cluster to an identical score (confirmed live: all 14
real "Baptism in the Holy Spirit"-tagged quotes scored an exact tie under
the old design), with a strict deterministic `(score, id)` tie-break and
an idempotent `create_and_approve_quote()`. Quote rail stays off —
`QUOTE_SELECTION_ENABLED` untouched. The same commit consolidated the
five-copy book-name map (CLAUDE.md Landmines entry) into one canonical
`backend/app/constants.py` source with a generated, drift-gated frontend
copy. A further commit (`2ef6860`) deduped a second hand-duplicated
ordinal-stripping regex (`study.py` / `reference_verifier.py`), synced a
now-stale quote-analysis script, and recorded the book-map consolidation
as done in `docs/roadmap.md`.

**2026-08-19 (read-only audit + repo-only fix, no DB writes):** the legacy
quote-relevance audit ran (`docs/audits/quote_legacy_relevance_audit_2026-08-18.md`,
via the `rhemata_readonly_analysis` role) — 793 approved/pending quotes
audited, 74.7% (592/793) fail relevance against their own inherited
document-level topic label, 592 of 592 affected quotes are in Derek
Prince's corpus. No decision made on the flagged rows; nothing changed.
A 20-quote random read-only sample was also pulled for Alex
(`docs/audits/quote_quality_sample_2026-08-19.md`, deliberately
uncommitted) — Alex assessed roughly 20% as worth serving. **New blocker
logged in PLAN.md:** "Quote quality — no quality bar exists anywhere in
the quote pipeline," not scoped this session.

The idempotency race flagged 2026-08-18 (PLAUSIBLE, not CONFIRMED) is now
RESOLVED: closed via a Postgres session-level advisory lock in
`create_and_approve_quote()` (`quotes.py::_creation_lock`), no migration
required, mutation-proven with real threads racing the real function
(commits `aac7f7e`, `046180d`, `46a6a5f`). **Correction:** an earlier
claim that migration 088 provided a unique-constraint backstop on quotes
was false — migration 088 is `source_ingest_runner.sql`, unrelated; no
unique constraint of any kind existed on the quotes tables before this
fix.

**New settled decision, 2026-08-19 (CLAUDE.md #28):** quote teacher scope
is OPEN — a relevant quote may appear on any answer about the subject
regardless of which teacher's material the answer prose was generated
from. Alex's explicit decision; accepted risk (teacher misrepresentation,
ranked failure mode #2) recorded verbatim in CLAUDE.md. Requires
presentation (visual separation, attribution attached to the quote
itself, never inferred from surrounding prose) to be designed and settled
before the quote rail is re-enabled. Corpus fact bearing on this decision
(confirmed live 2026-08-19): of 793 quotes, all but one are Derek
Prince's — so in practice, open scope means Prince quotes may appear
beneath any other teacher's answer, never the reverse.

Full detail: PLAN.md's W7–W8 entry and its new "Quote quality" blocker;
CLAUDE.md's quote-containment Landmines entry and settled decision #28.

Quote rail remains off in production: `QUOTE_SELECTION_ENABLED` is absent
from both Railway services entirely (`rhemata` and `answer-worker`,
checked directly via `railway variables`), which reads as off —
`quote_selection_enabled()` requires the exact string `"true"`.

A local-only, unpushed commit `cefcae5` ("v11 harness prep") sits in the
detached-HEAD worktree `~/.codex/worktrees/ca07/rhemata`, authored 2026-08-17
11:35 — before that same day's later 4f476eb→5af5fba session-close chain that
retired the harness coordinator (Invariant 15). Its content (a real adapter
"has run for real across v3-v10") conflicts with that later, already-pushed
record. Alex's explicit call: trust the later version already on `main`; leave
`cefcae5` unpushed and untouched. No action needed on it unless Alex reopens
the coordinator-retirement decision.

**Also surfaced, not touched (Alex's explicit "leave it for now"):**
`.worktrees/` holds ~2.9G, mostly stale — 49 `beta-night1*` worktrees on one
identical unmerged commit (`2e654e6`, likely retired-harness dispatch
artifacts) plus 11 other worktrees already fully merged into `main` (0 commits
ahead). `claude/harness-claude-cli-adapter` (1 ahead) and
`codex/o3-queue-resume-quarantine` (3 ahead) hold real unmerged work and were
excluded from that assessment. Nothing pruned.

---

## Classified work

**Blocker — active:** none currently being worked. One new blocker logged,
not scoped: "Quote quality — no quality bar exists anywhere in the quote
pipeline" (PLAN.md) — required before the quote rail is re-enabled;
deliberately not solved this session, Alex's explicit call. W1–W4
(repository-only) is complete and merged.

**Blocker — waiting:** W5–W6, all human/production-only gates, unchanged by the
merge — Alex selects and approves one hidden web article, confirms
teacher/source and clearance, and approves deploying this merged containment
code to the live Railway backend (repo merge alone does not put it into
production); then approves running a real (non-dry-run) preview; then one
hidden row-pinned write with reconciliation, idempotency, and rollback proof;
then eligibility/visibility/quote-repair decisions. W7's remaining sub-items
— the visible quote label choice (source/work title vs. semantic topic tag;
teacher scope itself is now decided, CLAUDE.md #28, open scope) and the
legacy-quote audit (now PARTIAL — ran, no decision on the flagged rows) —
W8 (article-backed proof), and W9 (recoverability) remain queued behind
W5–W6. Presentation design for open-scope quotes (visual separation,
attribution attached to the quote itself) is also required before the
quote rail is re-enabled, per CLAUDE.md #28, and is not yet done.

**Scheduled:** broad visible-default policy, general prompt/claim-support work,
B1–B7 product work, and remaining corpus work after the web-article proof.

**Triggered:** New Wine PDF ingestion waits for an Alex-accepted blind OCR
benchmark win. Tier-2 work begins at public signup or more than roughly 20 beta
users. Load testing reopens only after measured beta evidence or a demonstrated
concurrency failure. Admin notifications wait for scheduled position-refresh
work. The Manna rebrand waits until Alex schedules it as a bounded product
phase.

**Parked:** custom harness/adapter work, missing-author cleanup, quote-status
cleanup, chapter-detector expansion, one-off visibility work,
`jewish_perspectives`, and other named roadmap entries unless a recorded
trigger fires or Alex explicitly promotes an item.

---

## Next single item

Still the attended W5–W6 gate: Alex selects and approves one hidden web
article, approves deploying quote containment to production, then runs the
real preview, the single hidden row-pinned write, and idempotency/rollback
proof, before any eligibility, visibility, or quote-repair decision. No
further repository-only work is queued ahead of that gate. The new "Quote
quality" blocker and the presentation-design requirement from CLAUDE.md #28
are additional prerequisites for quote-rail re-enablement specifically —
neither is scoped yet and neither changes the current W5–W6 priority.

Process baseline for this session (2026-08-19): one read-only audit
completed (legacy quote relevance, explicitly requested), one read-only
quote sample pulled for Alex (explicitly requested, deliberately
uncommitted), one repo-only fix completed with a mutation-proven test
(idempotency race, explicitly requested), one prior PLAUSIBLE-not-CONFIRMED
finding closed, one prior factual claim (migration 088) corrected, one new
finding promoted to Blocker (quote quality, not scoped — Alex's explicit
call to log rather than chase), one new settled decision recorded (quote
teacher scope, open), zero database writes, zero deploys, zero active
blockers being worked, one waiting on Alex.
