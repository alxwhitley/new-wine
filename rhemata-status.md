# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-01.

Trimmed 2026-08-01 back to live-state-only per the Project Knowledge Read
Contract (the file had grown to ~2,700 lines of accumulated session
narrative). The prior session-by-session history (2026-07-17 → 2026-08-01)
lives in git history; retrieve it there if a past session's detail is needed.

---

## Current state

**Proposition generation — resumed, current.** Runs on the bypass-proof v3.1
path (named-teacher extraction; provenance stamping structurally required,
CLAUDE.md Invariant 10). The corpus-wide backfill (PLAN.md #17/#49) completed
2026-07-30; a small number of documents remain unprocessed — the known
JSON-escaping defect (a model-emitted unescaped quote inside a nested scripture
quotation, present in v3/v3.1 alike) plus the book-length single-call gap
(partially addressed, below). Processed/remaining totals: query live.

**Chapter-scoped book extraction — committed, proven, in use.** The
`title_repeat_boundary` path (`split_book_into_chapters()` /
`_extract_and_store_book_chapters()` / `process_book_document()`, plus
`is_front_back_matter()` front/back-matter skipping) is committed and reliably
covers the 8 of 53 book documents whose chapters repeat their own title. Seven
public-domain books now have real propositions via this path, most recently
John Wesley's "The Journal of John Wesley" (1,249 propositions, v3.1, real
write 2026-08-01, independently re-verified on a fresh connection). The second
detector for roman-numeral / bare-"Chapter N" books (`detect_book_chapters()`
etc.) remains DELIBERATELY uncommitted with zero production callers — do not
assume it runs (CLAUDE.md Landmines, PLAN.md #50).

**2026-08-01 live-DB corrections — both closed, re-verified.** Fix (a)/(b)
(third-party byline detector, editorial-apparatus label set, tightened
digit-ratio roman-numeral arm) committed `8e251c8`.
- "The New Life" (Andrew Murray): a Translator's Note wrongly attributed to
  Murray removed — 411 → 408 propositions (3 rows deleted, disambiguated from
  10 genuine Preface rows via `proposition_chunks`).
- "The Lord's Table" (Andrew Murray): the real ~57-word "VII. Saturday" entry,
  previously excluded by the pre-fix digit-ratio arm, extracted and stored —
  148 → 149 propositions.
Both re-verified on fresh connections (separate from the writing connection),
clean `proposition_index` sequences. The two "live imperfection" Landmines and
CLAUDE.md Open Decision #22 are now closed. (DB-write session, no commit — the
DB is the durable record, per repo convention.)

**Position layer — house-voice Position Papers live for 2 pillars.**
`backend/app/services/position_papers.py` serves baptism-in-the-Spirit and
speaking-in-tongues in Rhemata's own voice via `chat.py` interception (newly
documented in ARCHITECTURE.md, "Position papers (house-voice answer path)",
2026-08-01). Remaining charismatic pillars are future work (drafts in the
untracked `docs/position_papers/`, owned by Alex). Teacher/corpus positions
remain structurally gated to `kind='teacher'` (Invariants 13/14); corpus-wide
positions still refused twice.

**Repo at session close.** The working tree carries the deliberately-
uncommitted numeral-heading detector + its test (`scripts/propositions.py`,
`scripts/test_propositions_book_numeral_detection.py`), two uncommitted
frontend commentary-styling tweaks, and the untracked `docs/position_papers/`
drafts. Local `main` is ahead of `origin/main` (unpushed) — pushing is a
separate decision (push to main deploys the backend to Railway).

---

## Open blockers

Open items only; #1, #2, #3, #5 are resolved (git history — commits `5bdf720`,
`d4826dc`).

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe; blocks the 8 further
HelloAO commentaries (PLAN.md #27). The real chokepoint gap.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace:
`docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace: `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill gap (residual).** Some unlicensed docs ingested
before the wiring, plus alias gaps for several entities (re-ingest sentinels
silently — `ALIAS_MISS` breadcrumb). Counts unverified; query live.

**9. v4 propositions prompt — decision pending.** `EXTRACTION_PROMPT_V4` exists,
committed `ff0652c`, unwired; v3 is the default and v3.1 the named-teacher
path. Median word count still short of target on the 18-doc test
(`docs/audits/proposition-v3-v4-comparison-2026-07-16.md`). Adopt / iterate /
discard — and if adopt, decide backfill.

**10. Precept Austin raw-source gap.** Fewer raw scrape files in
`sources/precept_austin/raw/` than ingested documents — some have no local raw
backing if re-verification is ever needed.

**11. `verify_chunk_alignment.py` docstring stale.** Describes `shared_ingest`
insert modes (`psycopg2_batch` / `rest_per_chunk`) that no longer exist.

**12. `jewish_perspectives` table orphaned.** 2 rows, zero code references
outside migrations/docs.

**13. SP2 Study Panel — no real screen-reader pass ever run.** Phase 9 fixed 5
keyboard/ARIA gaps via a structural/keyboard audit; no VoiceOver/NVDA listen
has been done.

**14. Hebrew lexicon permission gate.** TBESH (Hebrew) is NOT covered by the
CC BY 4.0 grant that clears Greek (TBESG/TFLSJ); needs Online Bible's own
permission. SP2 renders Greek only, structurally. Do not build against TBESH
until cleared (PLAN.md Open Decisions #11).

**15. Attribution-mode mismatch, 307 HistoricalChristianFaith docs.** The
importer set `citation_mode='citable'`; all 307 live rows are `silent_context`
— unknown whether intentional. Decision needed (attribution is core
positioning, Invariant 7). Audit:
`docs/audits/historical_commentary_attribution_and_copyright_audit_2026-07-31.md`.

**16. Copyright flag, HistoricalChristianFaith source.** Three authors under a
blanket `public_domain`/`shown` source record may not be PD: C.S. Lewis
(d. 1963), J.R.R. Tolkien (d. 1973), Douglas Wilson (living). Verify or gate
before treating as servable; interim lever = the `source_kind='commentary'`
"Historical Commentaries" toggle (currently enabled). Same audit as #15.

---

## Known harness bugs

Both resolved: the 2026-07-18 executor write-accounting loop (fixed 2026-07-19,
`d9ab1cc`) and the `BASH_WRITE_INDICATORS` SQL-verb over-flagging (narrowed
2026-07-31, `569d412` — no DB-write-capable command is ever allowlisted).
CLAUDE.md's Session Routing DB-write hard rule is unchanged; its revisit
trigger's second condition — a deliberately-run, reviewed, clean DB-write
harness session — remains open. Proofs:
`.claude/harness-selftest/test_write_accounting_loop_fix.py`,
`test_sql_verb_narrowing.py`.

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar). The
  tab bar is gated off by default behind `NEXT_PUBLIC_FULL_NAV_ENABLED`
  (chat-only beta); `=true` restores it exactly.
- Pass B pending: `UsageRing` was pulled from the mobile top bar and not yet
  remounted in the sidebar drawer.

---

## Next

1. **Blocker #4 — route `ingest_helloao.py` through `shared_ingest`.** Sole
   remaining chokepoint conversion; unblocks HelloAO commentary growth
   (PLAN.md #27) only, not corpus growth generally.
2. **Folder renames** (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) + drop
   the orphaned `jewish_perspectives` table.
3. **Staging Supabase + backup/restore test.** The `sources/` backup exists
   (2026-07-19) but a restore has never been verified — do not assume it works
   until tested.

SP track: SP2 done (Phases 1–9); SP4 teacher cards shipped and signed off; SP
panel refinement done. Next SP item is #43 (SP5, mobile bottom-sheet). #38
(SP0 mobile mockup) completion unverified — confirm before assuming.
