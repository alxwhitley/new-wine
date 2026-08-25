# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (Discovery review tooling + a real one-shot
attended web ingestion; commits `b996ed7`, `720e1c8`, `ba63f54` shipped and
DB-verified live).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue is unaffected — still **0** active
blockers. This session was ad hoc ingestion-tooling work plus one real
attended ingestion, not a blocker-queue item. No production deploy;
changes are repo/script work plus DB writes executed by Alex in an
attended terminal (Claude Code Auto Mode still blocks direct writes from
this session — same reconfirmed block as before, not re-tested further).

**Discovery review tooling, built and committed (`b996ed7`):**
`scripts/review_discovery_candidates.py` — a local one-candidate-at-a-time
FastAPI page (name + link only, Yes/No, no forms, no session state) that
writes straight to the `Approved Sites` tab or marks a row `rejected`.
`scripts/check_discovery_blog_links.py` — a one-shot live fetch+link-check
per unverified candidate, reusing the crawler's own fetch/link-discovery,
labeling a new `auto_link_check` column so the review tool can skip
confirmed dead candidates automatically. Both are documented in CLAUDE.md's
Landmines so a future session finds them before rebuilding either.

Ran the checker for real against all 109 unverified Discovery candidates:
26 `looks_like_blog`, 2 `no_blog_detected` (now auto-skipped), **81
`check_failed`** — mostly sites bot-blocking the fetch, most likely because
the shared fetcher sends no `User-Agent` header. Net filtering benefit was
much smaller than hoped because of that block rate. Not fixed this
session — flagged as a real, separate decision (touches shared SSRF-
hardened infrastructure the production crawler also depends on).

`scripts/site_ingest_crawler.py`: `--site NAME` is now optional — omitting
it loops over every `Approved Sites` row with `approved=TRUE` in one
invocation, same per-site gates as before. Scope of the unattended-write
carve-out is unchanged, only the CLI ergonomics.

**Incident, caught and resolved, not caused by this session's tooling:**
before any of the above ran, the live spreadsheet's `Approved Sites` tab
and two Discovery columns were found missing from the on-disk file
(uncommitted local Excel edits). Restored via `git checkout` to the exact
last-committed state; confirmed byte-identical after.

**Watchman Nee — first real document write of this specific pipeline,
attended, DB-verified:** Alex asked to ingest
`watchmannee.org/major-teachings.html`. Investigation found this page and
4 others on the same site are Living Stream Ministry material explicitly
credited to Witness Lee, not Nee's own writing — third-person exposition
throughout, no quote/excerpt markers. Flagged directly with the textual
evidence; **Alex's explicit decision was to attribute to Watchman Nee
anyway**, recorded in full in the new source's own `notes` column so this
reads as deliberate, not an oversight. Two of the five pages were ingested
(the other three excluded: one has no citation at all on the page; two mix
an unconfirmed-author narrative with direct first-person Nee quotes in the
same page — `attribution_mode='per_item'` is schema-only, the processor
hard-refuses anything but `'declared'`, so mixed-authorship pages can't be
split correctly today).

A real mistake was made and caught by the processor's own gate, not by
review: the registration script set the new source `visibility='shown'`
(the general new-material-default policy, Settled #12) instead of
`'hidden'` — what Invariant 16 already documents as required for a *new
web-article* source specifically. Both queue rows correctly refused
(`source_visibility_not_hidden`, `attempts` stayed 0, nothing written
incorrectly). Fixed with a follow-up attended script; both rows retried
successfully. **Final, DB-verified state:** source `df64f6c3-…`
("Watchman Nee", `unlicensed`/`hidden` — not currently servable in any
answer), two documents stored (`a3e8c760-…` "Major Teachings": 10
chunks/12 propositions; `57d5f55d-…` "Other Crucial Scriptural Teachings":
17 chunks/20 propositions). Making this source visible/live is a separate,
later, deliberate decision — not done this session.

All of this session's code + the staging/fix scripts are committed:
`b996ed7`, `720e1c8`, `ba63f54`.

---

## Findings surfaced, not yet acted on

- Whether `source_ingest_queue/fetcher.py` should send a realistic
  User-Agent header — the real driver behind the 81/109 `check_failed`
  rate above; would likely also raise the production crawler's real
  success rate on approved sites, not just the checker's. Not decided or
  built this session — touches shared SSRF-hardened fetch infrastructure.
- The three excluded `watchmannee.org` pages (`christian-faith.html` — no
  citation at all; `life-ministry.html` / `watchman-nee-testimony.html` —
  mixed unconfirmed-narrative + direct Nee quotes) remain un-ingested;
  need either `attribution_mode='per_item'` actually implemented, or a
  manual excerpt-only approach, before they can go in correctly attributed.
- 81 of 109 Discovery candidates remain `check_failed` in the review tool —
  unresolved either way, still visible for Alex to review manually.
- **Scheduled** (`docs/roadmap.md`): quote accuracy/relevance repair before
  any attended re-enable; the live rail remains off. B6 model-generation
  latency benchmark (61–64s generation, sub-second queue time as of last
  measurement). Starlette+FastAPI / pdfplumber+pdfminer coupled dependency
  bumps; frontend CSP; the deferred Next.js major bump.
- Carried, not re-checked this session: Bonnke URL suspect (expired cert,
  no CfaN corroboration); staging source name still reads `"Vlad Savchuk
  (web staging)"` on citations; no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII tables; full cascading
  account deletion still unbuilt (`POST /account/delete-request` is still
  a stub).

---

## Next single item

Alex's call. Two independent threads are open, neither blocking the
other: (1) keep working through the Discovery backlog with
`review_discovery_candidates.py` — 105+ candidates still need a Yes/No,
and (2) decide whether/when to make the Watchman Nee source
visible/servable, or leave it staged indefinitely. Separately worth
deciding: the fetcher User-Agent question above, since it affects both the
checker and the production crawler. Active blocker count **0**.
