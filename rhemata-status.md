# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06/07 (quote rail now genuinely end-to-end and
user-visible — backend wired + pushed + deployed prior session; frontend
display piece built + live-browser-verified THIS session, NOT yet pushed;
quote-source exclusions APPLIED; async cutover LIVE; Project 2 phase 1
steps 1+2 DONE; position papers rebuilt as fence + guarded retrieval).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Cut material is
never the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Project 3 (quote rail) — backend wired + pushed + deployed (2026-08-06);
frontend display piece built + live-browser-verified (2026-08-06/07), NOT
yet pushed. Genuinely end-to-end and user-visible once pushed — ASYNC PATH
ONLY (chat.py untouched — see CLAUDE.md's landmine).**
`producer.produce()` selects approved quotes post-`verify_references` via
deterministic embedding-cosine similarity against each quote's `topic` tag,
fail-soft; `quote_ids`-only delivery through the async SSE meta frame; new
public, un-gated `POST /answer-quotes/resolve`. `QUOTE_TOPIC_SIMILARITY_THRESHOLD`
recalibrated live to 0.40 (was a bad 0.75 guess) — still provisional. Backend
live-verified 28/28 + 4/4 on the per-work quote cap, all test rows cleaned up.
Full backend detail: PLAN.md v5.29.

**Frontend (this session, PLAN.md v5.30):** `frontend/lib/api.ts` threads
`quote_ids` off the meta frame (was parsed and dropped) + adds `resolveQuotes()`
(plain unauthenticated POST, works identically for guest/signed-in). New
`frontend/hooks/useResolvedQuotes.ts` mirrors the app's existing fetch-after-
render idiom (`useTeacherCard`), exposing no loading/error state so an empty
`quote_ids`, a revoked id, or a failed fetch all render nothing. New
`QuoteRail` in `chat-message.tsx` renders a bordered card (gold quote icon,
italic serif quote text, teacher name, topic `Badge` always paired) between
the answer and feedback thumbs — a `teacher_name: null` quote is filtered out
entirely. All within existing DESIGN.md tokens. `planner-reviewer` APPROVED
(all 8 binding criteria verified against the real diff); one non-blocking
hardening note (missing state reset pre-fetch, unreachable today) closed
same session with a 1-line fix.

**Live-verified in a real browser against the real production DB (local
FastAPI run against production Supabase, since `localhost:3000` is
CORS-blocked from the deployed backend — same code/data, not a mock),
all 4 required scenarios, real questions, real Anthropic calls:** guest +
matching question → Andrew Murray "waiting on God" card renders correctly;
signed-in (real disposable Supabase test user, hard-deleted after — zero
orphaned rows) + matching question → Derek Prince "fasting" card renders
identically; non-matching question → zero visible change; `/answer-quotes/resolve`
forced to fail → full answer renders normally, no card, no visible error.
`npx tsc --noEmit` clean throughout. Commits: `d0d0d2e` (feature, local
only). **Not pushed/deployed this session — Alex's call on when.**

**Backend deployment (prior session, still current).** `origin/main` holds
the backend build (`309f4bd`/`4fc98b4`) — Railway (`rhemata` + `answer-worker`)
+ Vercel all deployed green; `POST /answer-quotes/resolve` verified live on
prod. 3 real quote rows (2 approved, 1 revoked) + 3 clearance rows live.

**Non-teacher-material exclusions APPLIED 2026-08-06 (`ddd6b7b` + DB write).**
68 chunks carry `quote_ineligible_reason` (CCEL front matter across Murray's
books, Lord's Table catechism, Müller verbatim chunks, Bride guest-speaker
testimony, etc.) per Alex's judgment calls in
`docs/audits/non_teacher_material_audit_2026-08-06.md`. Trigger enforcement
re-verified live on the three serious items. Several embedded (not whole-
chunk) third-party spans remain FLAGGED, not excluded — needs a sub-chunk
mechanism or Alex accepting whole-chunk loss; full list in that audit doc.

**Project 1 (scalable async answers) — PROVEN end-to-end 2026-08-06;
`serving_enabled` TRUE, async routes SERVING real traffic.** Real question
through the deployed HTTP route confirmed against the `answer_jobs` row:
`status=done`, `outcome=answered`, 11 citations, 6 verified_references. Cost
$0.173, ~106s. **Not proven:** real concurrency at the 100-dial target —
one serial request only.

**Project 2 (one named voice per answer) — phase 1 steps 1+2 DONE**
(`d99798a`/`0f6e372` step 1, `ff7a389`/`97c007c` step 2); step 3 is the
quote rail above, now in progress rather than blocked.
`apply_single_teacher_lock()` restricts retrieval to one teacher at >=60%
dominance. Still doesn't fire on real tongues questions (no teacher clears
60%) — a live, not structural, reason.

**Position papers — rebuilt 2026-08-06 as fence + guarded retrieval
(`b9af800`), closing CLAUDE.md decision #8's flagged 2026-08-01 conflict.**
A match (2 live pillars) no longer bypasses retrieval: the paper's body
injects as bounding `[House Position]` silent context around a normal,
cited answer. `position_paper_exclusion.py` excludes any retrieved teacher
whose material genuinely contradicts it, never silently reframed into
agreement; if exclusion empties the retrieval,
`render_paper_voice_with_disclaimer()` serves the paper's voice with the
standard disclaimer — the ONLY sanctioned reason for that fallback.
CLAUDE.md #8/#9 RESOLVED + 2 new decisions (#16/#17).

**Answer path.** Buffers fully; runs the Phase-2 retrieval-grounding guard +
prose-attribution scan + `verify_references`; resolves ungrounded credit
(regenerate-once-then-refuse). **Position layer** (teacher/corpus `positions`
table, ≠ position PAPERS) — revised 2026-08-04, nothing built; topic list (#16)
is the prerequisite (`docs/audits/position_layer_revival_diagnostic_2026-08-04.md`).

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book extraction
covers 8/53 books; roman-numeral detector COMMITTED (`8d6b7bc`) but zero
production callers. Counts: query live. Generation model: Sonnet 5 live
(`generation_model_config`, migration 081, 60s-cached).

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer; ~40-concurrent ceiling replacement LIVE
but unproven at real concurrency (one serial test only).

- **#4** `ingest_helloao.py` unconverted. **#6** Guest→account conversion likely broken (`docs/audits/GUEST_AUTH_AUDIT.md`). **#7** Auth CTA inconsistencies remain open (`docs/audits/BUTTON_AUTH_UX_AUDIT.md`); the dead `AuthButton.tsx` component was removed 2026-08-06.
- **#9** v4 propositions prompt built, unwired. **#10** Precept Austin raw-source gap.
- **#12** `jewish_perspectives` orphaned; **#13** SP2 Study Panel — no screen-reader pass.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant. **#16** Lewis/Tolkien/Wilson mistagged `public_domain`.
- **#19** External pipeline diagram stale.
- **#22 (new)** Embedded third-party material FLAGGED but un-excludable at chunk granularity (Mott quote, translator footnotes, New Life Heidelberg quote, Freda Hanbury poem, Müller boundaries, magazine/tape running headers) — needs a sub-chunk exclusion mechanism or Alex's decision to accept whole-chunk loss. See Project 3 above + the audit doc.

Resolved: #1-3, #5, #11 (verify-chunk-alignment docstring corrected 2026-08-06), #15, #17, #18 (home copy + frontend sweep removed empty Bevere/Koulianos marketing; quote claim corrected 2026-08-06), #20 (admin bug did NOT manifest in prod; fix deployed), #21 (all 9 remaining Murray books + Prince audited + exclusions applied 2026-08-06).

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending:
  `UsageRing` not yet remounted in the sidebar drawer.

---

## Next

1. **Project 3 quote rail** — backend deployed, frontend built + verified but
   NOT pushed yet: push/deploy when Alex says go. Also open: decide whether
   to wire chat.py too (per CLAUDE.md's landmine); curate beyond the 2
   approved quotes; calibrate `QUOTE_TOPIC_SIMILARITY_THRESHOLD` against real
   traffic once volume exists; build deferred AI suggestions.
2. **Watch the Project 1 live flip** under real concurrency — one serial test only.
3. **Position layer — one-hop build sequence**: topic list (#16) →
   `match_stored_position()` → review workflow → chunk-shape adapter →
   concurrency fix → `chat.py` injection → rollout.
4. Route `ingest_helloao.py` through `shared_ingest`; rename folders + drop `jewish_perspectives`.
5. Staging Supabase + a verified backup/restore test.
6. Flip async-answer cost constants to list price on/after 2026-08-31.
7. Decide the roman-numeral book-chapter detector's fate — committed, unwired.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet).
