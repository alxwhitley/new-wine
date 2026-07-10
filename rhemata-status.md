# rhemata-status.md

**As of:** 2026-07-10 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** #2 (honesty fix) and #3 (chokepoint verification) are both closed out. Next up per plan.md's linear order: **#4 — Resend transactional email** (independent quick win, pulled early per Ordering call D) or **#6 — aliases + sentinel cleanup + strict mode**, first session of the chokepoint conversion band. Alex's call which to run next; nothing blocks either.
- **Next action:** confirm with Alex which of #4 or #6 to run next session.

---

## Where We Are in the Roadmap

(PLAN.md v5.1, linear numbered session list)

- **#1 Back up `sources/` + `ingest_queue.xlsx`** — DONE (Alex confirmed offsite upload to Google Drive; still not independently verified from this Mac — flagged below, unresolved).
- **#1.5 Commit the uncommitted working tree** — DONE (commit `72476b7`).
- **#2 Honesty fix** — DONE this session block. `POSITIONING.md` (lines 76, 127, 145) and `docs/how-rhemata-handles-sources.md` (section 15–17, line 46) rewritten to the paraphrase-and-cite posture; verified-verbatim quoting reframed as planned/future, not live. `backend/app/system_prompt.txt` line 112's ≤50-word retrieval-mode quote permission removed; line 129's now-dangling parenthetical fixed so "never lift phrasing verbatim" applies uniformly across all modes; line 32's voice/attribution firewall kept but narrowed from "quote or paraphrase with attribution" to paraphrase-only attribution (line 54's check untouched, still enforces the firewall). **Committed** (`0af69a6`).
  - **PLAN.md amendment (same session, separate commit):** Rule 11 clarification appended — the paraphrase-only stream is an accuracy guarantee, not a copyright-permission gate; quotes were never copyright-gated (see Decision 2, "License-gating quotes" under Killed). Decision #2 cell appended — re-permitting verbatim quotes ahead of the verifier was explicitly considered and rejected 2026-07-10; not urgent, no re-sequencing requested; if quotes-in-product ever becomes time-sensitive, the correct lever is pulling Q1–Q3 forward, not loosening the stream. **Committed** (`12c3870`).
  - **Still open:** live adversarial post-deploy test not yet run — confirm retrieval-mode answers come back as pure paraphrase (no quotation marks, no near-verbatim slips) once Railway redeploys with the new system_prompt.txt. Test against teachers with famous/tight signature lines (most likely to tempt a quote), not generic queries.
- **#3 Verify the chokepoint conversion actually works** — DONE this session. Verdict: **WORKING WITH CAVEATS** (not clean WORKING). See caveats below. Two separate single-item live runs: `baptism_of_the_holy_spirit.md` proved the dedup guard (`already_ingested()` correctly skipped a known duplicate); a new John Bevere YouTube transcript proved the full write path (resolve → insert document → chunk → embed → propositions), including the previously-untested propositions-gate-fires-for-real branch (4 propositions stored, embeddings + fts populated on all 4, verified by direct query not console output). Hard reconciliation: attempted 1 · stored 1 doc + 1 chunk + 4 propositions · errored 0 · skipped 0. Dedup path and write path were proven in two separate runs, never exercised together in one continuous run.
- **#4–37** — untouched.

---

## In Progress / Uncommitted Locally

- `CLAUDE.md` — modified, uncommitted. Pre-existing drift from before this session (repo-path corrections, `docs/` additions, `admin.py`/`feedback.py` entries, etc.), scoped to #14 — deliberately not touched this session.
- `DESIGN.md` — **confirmed clean**, no pending changes (`git status` clean; last touched in `b6da249`, the 2026-07-09 Notion-cutover commit). Prior uncertainty about this resolved via direct check.
- Everything from #2 and #3's work: committed (`0af69a6`, `12c3870` — see above).

---

## Open Blockers Awaiting a Decision

- Two sentinel-assigned docs ("So Great a Salvation," "The 59 One Another's of the NT") carry no author/source metadata — needs Alex's eyeball (plan.md #6).
- Un-ingested `8.21.24 Prophetic Teaching - Prophetic Ministry.docx` — content read, no byline found; unconfirmed whether this is "the Bedford docx" plan.md refers to.
- `PRODUCT.md` (2026-06-14) overlaps `POSITIONING.md` (now further revised 2026-07-10) — unclear if still authoritative or superseded; needs Alex's call.
- Offsite backup of `sources/` + `ingest_queue.xlsx` — confirmed uploaded per Alex, still not independently verified from this Mac. Real but unverified — worth a 30-second spot-check.
- `SKILL.md` may carry the same false "chokepoint shipped" claim `CLAUDE.md` does — flagged, not yet checked line-by-line. Both corrections deliberately held for #14.
- **New this session — stray `---` separator leaking into stored `chunks.content`** (`extract_txt()`'s header parser breaks out at the `---` line without consuming it). Confirmed live via direct query, not speculative. Not urgent today, but flagged as higher-priority-than-cosmetic: `chunks.content` is the exact text Q2 (the quote verifier, session #22) will treat as ground truth for exact-substring matching — a leaked separator character in that column risks false-negative or false-positive quote verification later. Should be fixed before or during the Q-track, not left as a permanent cosmetic nit. No decision yet on which session owns the fix.

---

## Live Corpus & Infra Snapshot

Not re-queried this session beyond the single test item (`a9e54bb1-bff5-4ef1-a563-147de5564dbd`, John Bevere, unlicensed/shown, source_id `755490fe-cf1d-4a54-bbb4-b67b72afb65f`, 1 chunk, 4 propositions — real row, now live in the corpus, not a throwaway test). Full corpus counts last confirmed 2026-07-09 (see prior snapshot in git history) — re-query next session if current totals are needed.

---

## Chokepoint Conversion — Verified Caveats (session #3, carry forward into #6–13)

These do not block #6 onward but should inform it:

1. **`DOCS_FOLDER` dead default path** (`ingest.py:33`, points under `~/Desktop/rhemata/sources` which doesn't exist at the current repo root `/Users/alexwhitley/rhemata`) — default no-arg invocation silently finds 0 files and exits clean. Always pass `--source-dir` explicitly pointed at the real repo path.
2. **Weak error handling** — broad `except Exception` in `_insert_document_rest`'s retry (catches everything, not just missing-column errors, silently drops `url`/`bible_references` on any failure); no error handling around the chunk-embed-insert loop in `_insert_chunks_rest`, nor around `ingest_file()` calls in `main()`'s batch loop — one bad file kills the entire batch run, not just that file. Relevant when #6 onward starts running larger batches.
3. **`CLAUDE.md` ground-truth staleness** (correct at #14, not now): `embed_text_fn` is live and exercised in `ingest.py` (confirmed both dry-run and live-run — author/year prefix applied before embedding); `content_fn` is intentionally unused (raw content stored by design, protects future quote-verification exactness). The current ground-truth note calling the whole hook pair "unexercised" is now half-stale.
4. **`is_copyrighted` test artifact, not a code bug:** the live-run test copy lived outside `sources/youtube/` by design (isolation to a single file), so `_is_copyrighted()`'s string-match on the path correctly-but-misleadingly evaluated `false`. Run from the real path, this evaluates `true` as expected. No action needed — noted so it isn't mistaken for a defect later.

---

## Next Session Should

Alex to choose between **#4 — Resend transactional email** (independent, low-risk, pulled early) or **#6 — aliases + sentinel cleanup + strict mode** (first session of the chokepoint conversion band, needs Alex's decision on the two unmetadata'd sentinel docs before it can complete). Either is unblocked. If #6 is chosen, come prepared with a call on "So Great a Salvation" and "The 59 One Another's of the NT."
