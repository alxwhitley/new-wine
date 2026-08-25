# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (mobile answer continuity, source visibility,
accessibility, and prompt alignment; commits `f76e526` and `c386e52` shipped
and production verified live).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md`'s private-beta blocker queue remains **0** active blockers. This
session was ad hoc web-ingestion tooling work, not a blocker-queue item — no
production deploy; changes are repo/script + one DB record (a source
visibility flip).

**Master ingestion spreadsheet** (`docs/ingestion/master_ingestion_queue.xlsx`):
a real live-verification pass ran over all 118 Discovery candidates (13
mechanically excluded first — no written content, archival/reference, no
URL on file; 105 checked live). Two new Discovery columns
(`agent_verified_has_blog`, `agent_verification_notes`) record findings
without touching `verification_status`, which stays reserved for Alex.
Result: 18 cleared into a new `Approved Sites` tab (proposed, `approved`
blank except Craig S. Keener — Alex's explicit call, this session), 8 more
have real content but need per-post byline filtering before they're safe,
79 not cleared. Recurring finding across ~5 independent candidates (Lisa
Chan/Francis Chan, Todd Korpi/Tara Korpi, Peter Youngren/Taina Youngren,
Lydia Stanley Morris/Nathan Morris, Heidi Baker/Rolland Baker): a
"single-teacher" domain silently carrying a family member's byline is
structural and recurring in this candidate pool, not the one-off it looked
like — this is why the crawler's byline gate (below) is unconditional, not
a one-time fix. Also found: several Discovery research-pass claims that
don't check out at all — Taehyun Lee's claimed affiliation matches no real
faculty record, Will Ford's domain is compromised (serving gambling spam).

**Autonomous site-ingest crawler — built, and Alex's explicit, narrowly
scoped exception to the DB-write-attended hard rule (CLAUDE.md Session
Routing + Invariant 16).** `source_ingest_queue` web-article writes via
`scripts/site_ingest_crawler.py` may now run unattended, gated by a new
deterministic byline-verification step (`source_ingest_queue/
byline_verify.py` — meta/JSON-LD/"By Name" signal extraction + token-
overlap comparison, mutation-proven against the shared-surname failure
mode above) replacing per-item human review. `link_discovery.py` does
same-domain post/pagination discovery. `scripts/
test_site_ingest_crawler.py`: 49/49. Two real bugs were caught by running
it live (not by review) and fixed before being called done: a false
"already known" dedup count that was actually a check-budget truncation,
and header/footer/aside nav links being treated as post candidates.

**Live proof, Craig Keener, independently re-verified against the DB
afterward:** visibility flipped `shown`→`hidden`
(`63119173-a295-4ec0-90e5-f3a55dcc8970`). Crawler correctly byline-
confirmed his real "My testimony" post via its own `<meta name="author">`
tag and queued it automatically (`9a32fc5d-680b-4c9f-a1f4-80cdaaae1b0b`);
the existing content-quality gate then correctly refused it
(`article_too_thin` — checked live, a genuine ~15-word video-embed
wrapper, not an extraction bug). Zero documents written; zero corpus
pollution. **This proves the refusal path only — no document has actually
been stored by this crawler yet.** 11 of 15 discovered candidate URLs on
his site (real essays: "Animal rights ethics," "Barak to the barracks,"
"Bar exam," "Shooting star") were never checked this run (budget-capped
at 4 checked, 1 confirmed-write cap).

**Claude Code Auto Mode blocks direct production DB writes — reconfirmed,
not a fluke.** Both real writes this session (the visibility flip, the
crawler `--apply`) were blocked consistently across genuinely reformulated
retries. Routed through the 2026-08-13 Grok-execution pattern a second
time (Claude writes/reviews, Grok executes verbatim, Claude independently
re-verifies after) — both writes above are that verified result. **Alex's
stated preference: route ingestion execution to Grok directly going
forward rather than alternating mid-task.**

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, new "Dependency and hardening follow-up"
  section): starlette+fastapi coupled bump — do the read-only exploitability
  triage of its 7 advisories first, the same pass that reduced 3 alarming
  Next.js CVEs to zero live attack surface; pdfplumber+pdfminer coupled bump;
  CSP on the frontend; the deferred Next.js major bump.
- **Scheduled** (`docs/roadmap.md`): quote accuracy and relevance repair before
  any attended re-enable; the live rail remains off.
- **Scheduled** (`docs/roadmap.md`, B6): model-generation latency benchmark;
  current production evidence is 61–64s generation with sub-second queue time.
- **Triggered** (`docs/roadmap.md`): JWKS unknown-`kid` rate limit — PyJWT
  2.13.0 already fixed the amplifying half (cache-wipe on failed fetch); the
  residual is un-amplified and belongs at the edge, not in `auth.py`.
- Public `/docs` + `/openapi.json` on the API list every route including
  admin ones. Routes stay auth-gated, so this is a map, not an open door.
  Left as-is deliberately — Alex may use it; not yet formally classified.
- Staging source name still reads `"Vlad Savchuk (web staging)"` on
  citations — attended one-row `sources.name` UPDATE whenever Alex wants it.
- Carried, not re-checked this session: Bonnke URL suspect (expired cert, no
  CfaN corroboration); no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII tables; full cascading
  account deletion still unbuilt (migration 090 removed only the DB-level
  blocker — `POST /account/delete-request` is still a stub).

---

## Next single item

Alex's call, and he's routing ingestion work to Grok directly now rather
than alternating with this session mid-task: the next crawler run should
check Craig Keener's remaining 11 discovered candidates (or a fresh
`--max-pages`/`--max-candidates` pass) to get this system's first actual
document write, then re-verify independently. Unrelated: the next measured
UX item is still the B6 answer-generation latency benchmark, or the quote
track if picked up instead (define the representative accuracy/relevance
acceptance set before changing selection or extraction). Active blocker
count **0**.
