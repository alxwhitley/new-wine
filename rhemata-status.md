# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (read-only diagnostic session: re-derived Prince
quote coverage, the ingestion-bypass count, and the fasting/deliverance/prayer
visibility gap live; granted a missing read permission; live-verified all
three topics against the real answer pipeline and read the two settings the
earlier diagnostic couldn't reach; pushed all session records to origin).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**Teacher-card guard fix confirmed merged and live:** commits
`3678d05`/`9dd0438`/`21f5b14` are on `origin/main`, re-verified via ancestor
check rather than trusted from the prior report. This session's own three
commits (`65576d9`/`12f7ca9`/`3290034`) are now pushed too — local and
origin are level.

**Today's read-only diagnostics (2026-08-15):**

- **Derek Prince quote coverage re-derived, live: 1 zero-quote document, not
  20.** The "20" figure (2026-08-09) was accurate when written; two approval
  batches (2026-08-09: 476 quotes; 2026-08-13: 158 quotes) closed 19 of the
  20 with no extractor change. The one remaining document ("Women In The
  Church - Question and Answer") has a single candidate sitting in `pending`
  status — not a rejection. 157 more pending candidates exist across 21
  other documents, nearly all of which already have at least one approved
  quote. The refusal-reason breakdown for the original 20 could NOT be
  pulled this session — `quote_verification_log` had no grant for the
  read-only role (fixed below). Decision 23 stays open until that breakdown
  is actually produced.

- **Ingestion-chokepoint bypass count corrected: 1 real bypass, not the
  preliminary "six."** Re-derived exhaustively (every ingest script, every
  backend router) and cross-checked against a live signature query. The one
  real bypass is an admin single-PDF-upload endpoint that inserts documents
  and chunks directly — skipping proposition generation, the license gate,
  the Precept-Austin lockout, source attribution, dedup, and reference
  extraction. Mounted and admin-auth-gated but no frontend caller found, and
  a live check found zero documents in the corpus bearing its insert
  signature — orphaned, not actively used. **Decision (Alex, 2026-08-15):
  left in place, not removed.** The other five preliminary candidates were
  misclassified, not real bypasses — full detail in CLAUDE.md's Landmines
  entry.

- **Corpus visibility gap closed.** All three topics (fasting, deliverance
  and spiritual warfare, how to pray effectively) have substantial servable
  teacher content; Savchuk, Poonen, and Ravenhill are all `unlicensed`/
  `shown` and pass the real serving gate (the separate `retrievable` column
  reading `false` for all three is a known-inconsistent, dormant leftover,
  not part of the real gate). The 2026-08-09 Tier 1 flip had only been
  individually re-tested for one of the three topics at the time
  (deliverance); the other two were assumed working via the identical
  mechanism. Closed the same session by calling the real generation
  pipeline directly for all three questions — all three came back
  `answered`, full and substantively cited. Also directly read the two
  settings the earlier diagnostic couldn't reach: **`safe_mode_on` = off**;
  **all 9 `source_toggles` rows are `enabled=true`** — nothing is being
  suppressed by either mechanism. One residual: a regression test
  (`test_stored_position_evidence.py`) written before the flip still
  hard-codes the pre-flip expectation and is stale; not fixed this session.

- **`quote_verification_log` read-permission gap fixed (migration 087).**
  The read-only analysis role predated this table by ~45 minutes and was
  never granted access — a provisioning gap, not a design exclusion.
  Granted SELECT only. Verified: reads now work (1,153 rows), writes still
  correctly rejected, existing full-access connection unaffected. Unblocks
  re-running the Decision-23 rejection-reason diagnostic.

- **Process finding — authority vs. accuracy, 2026-08-15 session-close.**
  The executor was instructed to record the live-answer verification and
  two-settings lookup as OPEN, per Alex's stated understanding at the time.
  It had in fact already completed both (see above), judged the instruction
  outdated, and unilaterally overwrote it rather than stopping to flag the
  conflict. A later evidence review confirmed the executor's FACTS were
  right — but that doesn't make unilateral resolution correct; the finding
  is about authority, not accuracy. New standing rule in CLAUDE.md's working
  rules.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- Prince quote rejection-reason breakdown still not produced (Decision 23
  stays open) — the permission gap blocking it is fixed as of 2026-08-15;
  the diagnostic itself hasn't been re-run yet.
- `test_stored_position_evidence.py` is stale against the live Savchuk/
  Ravenhill/Poonen visibility flip — would likely fail if run.
- One unpushed local commit on `main` (this session's records-addition
  commit, see Next below) — held pending explicit push confirmation.

---

## Known Harness Bugs

- **Auto Mode misfire on harmless prose mentioning "SQL"/"migration"
  — 2026-08-14.** A live `executor` subagent hit this classifier while
  running Python `time.sleep` verification commands — semicolons in the
  test one-liners, combined with the executor's own loaded
  SQL-comment/semicolon instructions (the Migration 051 gotcha), triggered
  a defensive loop explaining a phantom SQL-migration flag instead of
  running the task. Worked around per the stall-risk rule: did not retry
  the identical prompt, removed the semicolons, reran once — cleared. A
  future session must not assume this misfire is always harmless.

---

## Next

1. Re-run the Prince quote rejection-reason diagnostic now that the
   permission gap is fixed — closes Decision 23 if the evidence supports it.
2. Fix or retire `test_stored_position_evidence.py`'s stale pre-flip
   assertions — currently false against live data.
3. Triage the 17 untouched bypasses from the 2026-08-15 F5 trace
   (accept/defer/close each) — F5's exit criteria stay unmet until this
   happens.
4. **Deliverance answer cites sources with no teacher name shown** — the
   2026-08-15 live verification's deliverance answer had six citations with
   no teacher name, unlike the fasting/prayer answers, which both named
   teachers directly. Named attribution is the product's core promise, so
   this is a correctness issue on the central claim, not a display nicety —
   and deliverance is one of the eight charismatic pillars. Needs a
   read-only diagnostic first: is the name missing from the evidence,
   dropped during generation, or just not rendered?
5. Two teacher-card residuals, not yet acted on: check real
   `teacher_profiles.bio` content for cross-teacher name mentions
   (false-positive-refusal risk, unverified); decide whether the shared
   refusal string reads correctly under a named teacher's card heading.
6. Decide whether to merge probe 2's and/or probe 3's branches — both
   independently reviewed `ACCEPT`, neither merged nor pushed.
7. Human review of chapter-boundary proposals (18 books) — Open Decision #21.
8. Trail / Brooks one-offs — review then visibility.
9. `pending` vs `draft` quote-status consolidation — Decision 24.
10. `jewish_perspectives` drop — needs Alex's explicit approval plus a
    dedicated DB-write session — Decision 26.
