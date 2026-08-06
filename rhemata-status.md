# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here — query the live DB, and treat any count
seen elsewhere as unverified.

Last verified: 2026-08-06 (non-teacher-material quote-source exclusions APPLIED
across Murray + Prince; Project 3 quote rail first slice built + demoed; admin-auth
bug fixed, pushed + deployed; Project 1 async cutover LIVE; Project 2 phase 1 steps
1+2 DONE; position papers rebuilt as fence + guarded retrieval).

**Target ≤150 lines (CLAUDE.md's Session close contract).** Cut material is
never the only copy — it survives in git history and PLAN.md/CLAUDE.md/
`docs/audits/` and the commits named below.

---

## Current state

**Deployment.** **The admin-auth fix (`da27fe4`) IS pushed to `origin/main` and
deployed** — Railway `rhemata` + `answer-worker` + Vercel all reported green,
verified live this session. **Local `main` is ahead of `origin/main` by the Project 3
quote-rail build (`0e6a4f1`), its docs (`ad1d782`), and this session's exclusion +
records commits — NOT pushed, NOT deployed.** **Migration 082 + the non-teacher
exclusions ARE live against the real production Supabase** — no staging DB exists;
writes apply directly to the one real database. 3 real demo quote rows (2 Murray, 1
Prince, 1 revoked) + 3 `document_quote_clearance` rows still exist live — decide
whether to keep, revoke, or delete.

**Project 3 (hand-curated quote rail) — first slice BUILT + DEMOED
2026-08-06 (`0e6a4f1`), manual-curation-only, NOT wired into any serving
path.** Schema (migration 082): `quote_source_revisions` (immutable
per-chunk snapshot), `document_quote_clearance` (affirmative-only),
`quotes` (draft/approved/revoked). Every hard rule — admin-role-only
approval, source clearance required, commentary permanent hard-exclude,
exact-substring match against the captured snapshot — is enforced by a DB
trigger, not application code, since the backend bypasses RLS on every call
(migration 037). Verified live: an approval attempt against a real
commentary document was rejected by the database itself, rolled back clean.
Verifier + 4-case regression suite, 8/8 passing. Review tool
(`frontend/app/admin/quotes`) + resolution point (`quotes_service.resolve_quote`)
demoed end-to-end through a real browser — 3 real quotes, resolve by ID, one
revoked re-resolves to nothing. AI-suggested extraction is out of scope. Derek
Prince's `sermon_transcript` corpus is eligible written material per Alex's ruling.

**Non-teacher-material exclusions APPLIED 2026-08-06 (`ddd6b7b` + DB write;
`scripts/apply_non_teacher_exclusions_2026-08-06.py`).** Alex's judgment calls on
the follow-up audit (`docs/audits/non_teacher_material_audit_2026-08-06.md`) are
now live: **68 chunks carry `quote_ineligible_reason`** (6 pre-existing New Life +
62 new). Cleanly excluded (whole non-teacher chunks): CCEL front matter on all 9
remaining Murray books; Lord's Table catechism/Directory appendix; School of
Prayer's George Müller verbatim chunks (Murray's own framing kept eligible) + the
CCEL book advertisement; Bride Prepares Herself (Prince) guest-speaker testimony;
auto scripture indexes where separable. Trigger enforcement re-verified live
(rolled-back test) on the three serious items — Müller, book ad, catechism — all
blocked; a kept Murray chunk not blocked. **FLAGGED, not excluded — third-party
text embedded in a teacher's own chunk, un-isolable at chunk granularity, needs a
sub-chunk mechanism or Alex accepting whole-chunk loss:** the John R. Mott
quotation (School of Obedience, interwoven in every chunk), the Lord's Table + New
Life translator footnotes, the New Life Heidelberg quote (the "second problem area"
beyond 0-5), the Waiting On God 'Freda Hanbury' poem, the Müller boundary chunks,
the Bride ch11 boundary, and the magazine/tape running headers. Detail: the audit
doc + script header.

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

**Answer path — current behavior.** Buffers fully, runs the Phase-2
retrieval-grounding guard + prose-attribution scan + `verify_references`,
resolves ungrounded credit (regenerate-once-then-refuse). **Position layer**
(teacher/corpus `positions` table, unrelated to position PAPERS above) —
design revised 2026-08-04, nothing built; topic list (#16) is the unbuilt
prerequisite. Detail: `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

**Corpus/data.** Propositions backfill COMPLETE. Chapter-scoped book
extraction covers 8/53 books; roman-numeral detector COMMITTED (`8d6b7bc`)
but zero production callers. Lewis/Tolkien/Wilson mistagged `public_domain`
(#16, open). Counts: query live. Generation model: Sonnet 5 live,
`generation_model_config` (migration 081) holds it, 60s-cached.

---

## Open blockers

**Launch blockers (Project 1's remit, neither blocks further build work):**
~68s to a fully-revealed answer; ~40-concurrent ceiling replacement LIVE
but unproven at real concurrency (one serial test only).

- **#4** `ingest_helloao.py` unconverted. **#6** Guest→account conversion likely broken (`docs/audits/GUEST_AUTH_AUDIT.md`). **#7** Auth CTA inconsistencies (`docs/audits/BUTTON_AUTH_UX_AUDIT.md`).
- **#9** v4 propositions prompt built, unwired. **#10** Precept Austin raw-source gap. **#11** `verify_chunk_alignment.py` docstring stale.
- **#12** `jewish_perspectives` orphaned; **#13** SP2 Study Panel — no screen-reader pass.
- **#14** Hebrew lexicon (TBESH) not covered by the Greek CC BY 4.0 grant. **#16** Lewis/Tolkien/Wilson mistagged `public_domain`.
- **#18** Home-page names Bevere/Koulianos as "trusted teachers" — living-minister misrepresentation, still open. **#19** External pipeline diagram stale.
- **#22 (new)** Embedded third-party material FLAGGED but un-excludable at chunk granularity (Mott quote, translator footnotes, New Life Heidelberg quote, Freda Hanbury poem, Müller boundaries, magazine/tape running headers) — needs a sub-chunk exclusion mechanism or Alex's decision to accept whole-chunk loss. See Project 3 above + the audit doc.

Resolved: #1-3, #5, #15, #17, #20 (admin bug did NOT manifest in prod; fix deployed), #21 (all 9 remaining Murray books + Prince audited + exclusions applied 2026-08-06).

---

## Mobile UI

- Pass A shipped (floating-panel chat, full-bleed shell, bottom tab bar,
  gated behind `NEXT_PUBLIC_FULL_NAV_ENABLED`). Pass B pending:
  `UsageRing` not yet remounted in the sidebar drawer.

---

## Next

1. **Project 3 quote rail — decide next steps** (not yet ordered): wire
   `resolve_quote()` into a real serving surface; build the deferred
   AI-candidate-suggestion piece; curate beyond the 3 demo quotes; check
   the other 9 Murray books + Prince docs for exclusion-worthy front matter
   at scale (#21).
2. **Watch the Project 1 live flip** under real concurrency — one serial
   test only so far.
3. **Position layer — one-hop build sequence**: topic list (#16) →
   `match_stored_position()` → review workflow → chunk-shape adapter →
   concurrency fix → `chat.py` injection → rollout.
4. Route `ingest_helloao.py` through `shared_ingest`; folder renames + drop
   the orphaned `jewish_perspectives` table.
5. Staging Supabase + a verified backup/restore test.
6. Flip `async_answers/config.py`'s cost constants to list price on/after
   2026-08-31.
7. Decide the roman-numeral book-chapter detector's fate — committed, unwired.

SP track: SP2/SP4/panel-refinement done. Next: #43 (SP5, mobile bottom-sheet).
