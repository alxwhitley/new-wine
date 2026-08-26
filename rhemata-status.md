# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-26 (B6-F1 blind human quality review completed and
ACCEPT recorded; production-activation migration drafted and applied, flag
still off; master ingestion queue converted .xlsx -> TSV, committed).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md` has **1 active blocker**: B6-F1, named-teacher/stored-position route
collision. This session closed the review step and began, but did not finish,
production activation. A separate, unrelated repo-infra session this same
date converted the master ingestion queue spreadsheet format (own subsection
below) — no interaction with B6-F1.

**B6-F1 blind review — DONE, decision ACCEPT (2026-08-26):** Located the blind
packet, unblinding key, and mechanical report — they live in the
`codex/b6-answer-latency` worktree's own gitignored `local/2026-08/`, not the
main tree's. Mechanically confirmed the packet was genuinely blind (no model,
cost, timing, token, or variant field on either side). Presented both
`named_teacher_deliverance` blind pairs — the only relevant category, since
this correction changes the named-teacher route only — to Alex one at a time;
his scores were locked before the key was opened. He found no hard failure
across the five protected axes in the answering variant, either repetition;
the refusing variant was the known pre-existing problem, not a new failure.
Unblinding and the mechanical report reconciled cleanly: baseline's only 2
refusals in the 24-pair batch both landed on this case; the candidate answered
24/24. Alex recorded **ACCEPT**. Full detail:
`docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`'s "Blind human
quality review and decision (2026-08-26)" section.

**Production activation — scoped, drafted, migration 091 APPLIED live,
flag still OFF:** `migrations/091_teacher_specific_routing_flag.sql` adds
`async_answer_config.experimental_teacher_routing_enabled`
(`NOT NULL DEFAULT false`), mirroring migration 079's `serving_enabled`
seconds-reversible-switch pattern. `scripts/answer_worker.py`'s sole
`produce()` call site now threads it through as `experimental_teacher_routing=`.
Applied live via `scripts/apply_migration_091.py --apply` (attended,
Alex-approved) — its own 5-check verify pass confirmed the column exists,
`NOT NULL`, default `false`, the config row exists, and the live value reads
`false`. New offline regression: `scripts/test_teacher_specific_routing_flag.py`
(7/7 passing); existing `test_async_serving_gate.py` and the full B6 benchmark
suite (14/14) still pass. **Production behavior is unchanged** — the flag is
still `false`. Flipping it to `true` is a separate, attended Database-write
operation; held this session on Alex's explicit "hold here."

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged this
session.

**New Wine A2:** unchanged this session. Issue 02-1973 remains `quarantined`
(2 missing article continuations found by fresh whole-issue review), 0
propositions, 0 database writes. Scheduled behind B6-F1. Artifacts remain
local-only, untracked, under
`docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-25_retry_13/`.

**Master ingestion queue format conversion — DONE (2026-08-26, commit
`993a3aa`):** `docs/ingestion/master_ingestion_queue.xlsx` (one binary
workbook) replaced with four plain-text TSV files, one per former tab
(Read Me/Discovery/Queue/Approved Sites), via a new shared
`scripts/ingestion_sheet_io.py` — lossless round trip proven cell-by-cell
against the live workbook (87/87 checks) before the xlsx was deleted.
Scope expanded mid-session, Alex-approved: all four scripts found to open
the old file directly (`sync_master_ingestion_queue.py`,
`review_discovery_candidates.py`, `check_discovery_blog_links.py`,
`site_ingest_crawler.py`), not just the one the original task named, were
updated along with their tests. Discovery gained 7 new blank/unclassified
columns (clearance checklist x4 booleans + date, clearance-cost lane,
blog_index_url). Fixed a live bug the conversion would otherwise have
introduced silently: `review_discovery_candidates.py`'s `is True`/`is False`
boolean identity checks would have stopped filtering anything once Excel
booleans became TSV strings — now routed through
`ingestion_sheet_io.parse_bool_cell()`. CLAUDE.md's Landmines entry on this
spreadsheet is updated to match the new file layout. Repo-only session,
zero database writes.

---

## Findings surfaced, not yet acted on

- **Blocker** (`PLAN.md`, B6-F1): review DONE, ACCEPT recorded, migration 091
  applied live at `false`. The one remaining step — flipping the flag to
  `true` — is an attended DB write not yet authorized.
- **Scheduled** (`docs/roadmap.md`, B6): a future suite-wide latency candidate
  must address the generation bottleneck; the teacher-specific route was
  rejected as a latency direction (2.81% median improvement) but accepted on
  integrity — these are separate questions, don't conflate them again.
- **Scheduled** (`docs/roadmap.md`): quote accuracy/relevance repair before
  any attended re-enable.
- **Scheduled A2:** correct the omitted New Wine article and two
  continuations, then rerun the local no-write gates. Quarantine is the
  desired safety result, not authorization for ingestion.
- **Triggered** (`docs/roadmap.md`): JWKS unknown-`kid` rate limit — PyJWT
  2.13.0 already fixed the amplifying half; the residual belongs at the edge.
- Carried, not re-checked this session: dependency/hardening follow-up
  (starlette+fastapi, pdfplumber+pdfminer, CSP, deferred Next.js major bump);
  staging source name still reads `"Vlad Savchuk (web staging)"`; Bonnke URL
  suspect; no retention/TTL logic for user data; `rhemata_readonly_analysis`
  has no grant on PII tables; full cascading account deletion still unbuilt
  (migration 090 removed only the DB-level blocker).

---

## Next single item

Alex's explicit call: flip `async_answer_config.experimental_teacher_routing_enabled`
to `true` (attended Database-write session) to actually fix the named-teacher
core-journey failure in production, then run one live smoke check. Held this
session on Alex's "hold here, wrap up session" instruction — not done, not
scheduled elsewhere. New Wine A2 remains scheduled behind the active
critical-path blocker. Active blocker count **1**.
