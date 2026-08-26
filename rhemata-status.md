# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-26. Two independent sessions closed today: (1) this
session built and deployed the long-conversation-handoff feature; (2) a
separate repo-infra session converted the master ingestion queue spreadsheet
format (commit `993a3aa`). B6-F1 is unchanged by either.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md` has **1 active blocker**: B6-F1, named-teacher/stored-position
route collision — **unchanged today**. Review is DONE, ACCEPT recorded
2026-08-26 (prior session). Migration 091 is applied live, flag still
`false`. Flipping it to `true` remains the one attended step, still held on
Alex's explicit "hold here." Full detail: PLAN.md's own B6-F1 entry and
`docs/audits/2026-08/b6_answer_latency_session_2026-08-25.md`.

**Long-conversation-handoff feature — specified, built, deployed
(2026-08-26):** Answers `docs/roadmap.md` Horizon item 6. Full design:
`docs/superpowers/specs/2026-08-26-long-conversation-handoff.md`. A
dismissible chat nudge fires once a conversation's estimated cumulative
generation cost crosses $0.50 (~13 turns), suggesting a fresh conversation —
soft nudge, never a hard cap (product-philosophy reason, not cost, per
CLAUDE.md's design filter). Migration 092
(`conversations.cumulative_input_tokens` / `cumulative_output_tokens` /
`turn_count`, `NOT NULL DEFAULT 0`) is **applied live** (attended,
Alex-approved, 10/10 verify checks). `save_exchange()` increments the
running totals with a reconnect-safe idempotency gate (`cur.rowcount == 1`
on the assistant-message insert, not assumed) — proven by
`scripts/test_conversation_length_signal.py` (12/12, including a mutation
check that a broken gate would double-count). `async_chat.py` surfaces the
computed cost/turn estimate in the result payload (`null` for guests — no
server-side conversation row to accumulate against, v1 scope). Frontend:
`ConversationLengthNudge` component + `useChat.ts`/`page.tsx` wiring.
Committed `70f6a3b`, pushed to `origin/main`; Railway `rhemata` +
`answer-worker` both confirmed **Online** post-deploy (backend confirmed
live, 200 at `/`), Vercel production deployment confirmed **Ready**.
**Not yet done, both need Alex:** nudge copy is drafted but unreviewed
(deliberately says nothing about cost/tokens — see the component's own
comment); no live/E2E verification through a real conversation yet.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

**New Wine A2:** unchanged. Issue 02-1973 remains `quarantined` (2 missing
article continuations found by fresh whole-issue review), 0 propositions, 0
database writes. Scheduled behind B6-F1. Artifacts remain local-only,
untracked, under
`docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-25_retry_13/`.

**Master ingestion queue format conversion — DONE (2026-08-26, commit
`993a3aa`):** `docs/ingestion/master_ingestion_queue.xlsx` replaced with four
plain-text TSV files (one per former tab) via new shared
`scripts/ingestion_sheet_io.py` — lossless round trip proven cell-by-cell
(87/87 checks) before the xlsx was deleted. All four scripts that opened the
old file (`sync_master_ingestion_queue.py`, `review_discovery_candidates.py`,
`check_discovery_blog_links.py`, `site_ingest_crawler.py`) updated with
their tests; fixed a live boolean-identity bug the conversion would
otherwise have introduced silently. CLAUDE.md's Landmines entry on this
spreadsheet updated to match. Repo-only, zero database writes.

---

## Findings surfaced, not yet acted on

- **Blocker** (`PLAN.md`, B6-F1): unchanged — flipping the flag to `true` is
  the one remaining attended step.
- **Scheduled** (`docs/roadmap.md`, B6): suite-wide latency candidate still
  needed; teacher-specific route rejected on latency, accepted on integrity.
- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** correct the omitted New Wine article + two
  continuations, rerun local no-write gates.
- **Triggered**: JWKS unknown-`kid` rate limit — residual belongs at the
  edge.
- **Process note (this session):** `scripts/test_metering.py` is a
  live-integration script (writes to the real production `user_usage` row
  for `creative@clf-church.com`, hits the real Railway URL), not an offline
  unit test, despite the same `test_*.py` naming as the offline ones. It
  self-cleans (deletes its row at both start and end — verified before/after
  this session, zero residual), but running it unread is an unannounced
  production write. Read any `scripts/test_*.py` before batch-running it as
  a "regression check" — the filename alone doesn't distinguish the two
  kinds.
- Carried, not re-checked this session: dependency/hardening follow-up
  (starlette+fastapi, pdfplumber+pdfminer, CSP, deferred Next.js major
  bump); staging source name still reads `"Vlad Savchuk (web staging)"`;
  Bonnke URL suspect; no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII/user tables (reconfirmed
  this session against `user_usage` specifically — permission denied); full
  cascading account deletion still unbuilt (migration 090 removed only the
  DB-level blocker).

---

## Next single item

Two independent items, both Alex's call: (1) flip
`async_answer_config.experimental_teacher_routing_enabled` to `true`
(attended Database-write) to fix the B6-F1 named-teacher core-journey
failure in production — unchanged from the prior session, still held; (2)
review the long-conversation-handoff nudge copy and do a live check once
real usage crosses the $0.50 threshold. Active blocker count **1** (B6-F1,
unchanged).
