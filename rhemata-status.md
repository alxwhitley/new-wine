# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-27. **PLAN.md has zero active blockers.** This session
shipped and locally merged the hardened in-page Discovery review extension.
New Wine A2 remains the next scheduled corpus thread; see docs/roadmap.md.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Discovery review extension — DONE, merged locally to `main` (merge
`daead27`).** `tools/discovery-review-extension/` is an unpacked Chrome MV3
extension that puts Approve / Do Not Approve controls on the active candidate
site and advances that same tab after a saved decision. The local FastAPI
server remains the sole TSV writer and chooses candidate identity from a fresh
queue read. Mutations require a process-random capability; extension decisions
also carry a worker-only opaque queue revision so a changed queue returns 409
instead of applying the click to another candidate. The toolbar uses a closed
Shadow DOM, accepts trusted browser clicks only, validates response shape and
HTTP(S) navigation, and deactivates an older review tab after a new start.
It has no database, crawler, ingestion-worker, or production-host authority.

**Verification:** Python review tests 80/80, TSV tests 79/79, blog-link tests
24/24, Node extension tests 31/31, plus a headed Chromium proof covering the
normal two-candidate flow and hostile synthetic clicks, four cross-origin
mutation attempts, queue-change conflicts with byte preservation, malformed
and non-HTTP payload refusal, inactive-tab isolation, old-tab deactivation,
same-tab navigation, and terminal state. Real ingestion TSV hashes were
preserved; no production database or ingestion operation ran.

**Discovery queue snapshot (read-only, 2026-08-27):** 118 candidates total:
111 unverified and 7 rejected. Approved Sites has 18 rows, with 1 currently
marked `approved=TRUE`. Alex's modified Discovery TSV remains intentionally
uncommitted. Run instructions are in
`tools/discovery-review-extension/README.md`.

**Merge preservation:** the prior two-script controller edits were saved in a
recoverable stash before the merge because `main` had advanced independently;
their completed implementation is present in the merge. The feature branch
and worktree remain intact because repository policy requires separate,
explicit approval before deleting anything under `~/rhemata/`.

**New Wine A2 — still scheduled and not cleared end-to-end.** The existing
pipeline corrections remain as recorded in `docs/roadmap.md`. Issue 02-1973
still needs a standalone segmentation-only diagnosis of the recurring
`non_article_span_implausibly_large` refusal using the cached transcript before
more blind CLI retries. Production database ingest remains a separate,
attended, explicitly approved operation.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Scheduled A2:** see Current state above — Issue 02-1973 isn't through
  the article gate yet. Production database ingest for this or any New
  Wine issue remains a separate, attended, explicitly approved operation
  regardless of how clean a review run gets.
- **Parked:** the extension's JavaScript success validator treats a
  32-character whitespace capability/revision as syntactically long enough.
  The Python server still rejects it before mutation, so this is a diagnostic
  contract mismatch, not an authorization bypass.
- **Triggered**: JWKS unknown-`kid` rate limit — residual belongs at the
  edge.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual, but read any `scripts/test_*.py` before batch-running it);
  dependency/hardening follow-up (starlette+fastapi, pdfplumber+pdfminer,
  CSP, deferred Next.js major bump); staging source name still reads
  `"Vlad Savchuk (web staging)"`; Bonnke URL suspect; no retention/TTL logic
  for user data; `rhemata_readonly_analysis` has no grant on PII/user
  tables; full cascading account deletion still unbuilt; New Wine review
  pipeline's cost-reporting gap (noted above) is a real observability nit,
  not fixed this session.

---

## Next single item

**No active blocker.** New Wine A2 is the live thread: diagnose the
`non_article_span_implausibly_large` recurrence directly (cheap — OCR is
fully cached) before running more blind CLI retries. Real database ingest
for this or any New Wine issue remains a separate, attended, explicitly
approved operation regardless of how clean a review run gets.
