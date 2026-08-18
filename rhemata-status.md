# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-18. `main` is at `2ef6860`, three commits ahead of the
prior close: `189ef42` (harness-retirement scoping clarification), `82ec0f5`
(quote-relevance rebuild + book-name-map consolidation), `2ef6860` (cleanup
follow-up). The pre-existing untracked `Temporary-assets/` directory remains
untouched.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Rhemata now uses a Beta Critical Path operating model. Codex is the primary
working surface; native agents/worktrees may assist bounded tasks. The custom
multi-provider coordinator and overnight harness are retired from active
development. Their code and history remain intact but no follow-up work is
authorized. This retirement is scoped to the custom multi-provider
coordinator and its unattended dispatch mechanism only; it places no
restriction on ordinary Codex sessions continuing bounded repo-only work
while Alex is away from the keyboard — a normal working session is not an
overnight harness run.

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

**Same-day follow-up (2026-08-18, repo-only, no DB writes, none needing
Alex's attention at build time):** W7's first bullet is DONE (`82ec0f5`) —
quote-selection relevance is now scored from each quote's own `quote_text`
instead of the inherited document topic tag that tied every quote in a
cluster to an identical score (confirmed live: all 14 real "Baptism in the
Holy Spirit"-tagged quotes scored an exact tie under the old design), with a
strict deterministic `(score, id)` tie-break and an idempotent
`create_and_approve_quote()`. Quote rail stays off — `QUOTE_SELECTION_ENABLED`
untouched. The same commit consolidated the five-copy book-name map (CLAUDE.md
Landmines entry) into one canonical `backend/app/constants.py` source with a
generated, drift-gated frontend copy. A further commit (`2ef6860`) deduped a
second hand-duplicated ordinal-stripping regex (`study.py` /
`reference_verifier.py`), synced a now-stale quote-analysis script, and
recorded the book-map consolidation as done in `docs/roadmap.md`. Full detail:
PLAN.md's W7–W8 entry.

**Open, unverified finding:** an `/code-review` run on this session's changes
was interrupted by Alex before its adversarial-verify step. One sub-check
(before the interruption) found the new idempotency check is a non-atomic
SELECT-then-INSERT with no DB uniqueness constraint or lock backing it — a
genuine concurrent call could still duplicate a `quotes` row. PLAUSIBLE, not
CONFIRMED. Recorded in PLAN.md's W7 entry; a future session should re-verify
and, if it holds, harden before this path sees concurrent traffic.

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

**Blocker — active:** none. W1–W4 (repository-only) is complete and merged.

**Blocker — waiting:** W5–W6, all human/production-only gates, unchanged by the
merge — Alex selects and approves one hidden web article, confirms
teacher/source and clearance, and approves deploying this merged containment
code to the live Railway backend (repo merge alone does not put it into
production); then approves running a real (non-dry-run) preview; then one
hidden row-pinned write with reconciliation, idempotency, and rollback proof;
then eligibility/visibility/quote-repair decisions. W7's remaining sub-items
(teacher-scope/label choice, legacy-quote audit), W8 (article-backed proof),
and W9 (recoverability) remain queued behind W5–W6.

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
further repository-only work is queued ahead of that gate — W7's first bullet
was pulled forward and executed same-day since it needed no DB write and no
Alex decision; nothing else in W7–W9 can move without Alex.

Process baseline for this session: two unplanned-but-authorized
investigations completed (quote relevance + idempotency, book-name-map
consolidation, both explicitly requested), one small follow-up cleanup pass
(also requested), zero findings promoted to Blocker, one new finding recorded
as PLAUSIBLE-not-CONFIRMED (idempotency race), zero active blockers, one
waiting on Alex.
