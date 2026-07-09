# rhemata-status.md

**As of:** 2026-07-09 (session close) · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** PLAN.md **#2 — Honesty fix**, next up. Rewrite `POSITIONING.md` + `docs/how-rhemata-handles-sources.md` (and the deployed `frontend/app/sources/page.tsx` copy) to the real posture — paraphrase-and-cite; quotes are a gated future surface, not a live guarantee — and remove `system_prompt.txt:112`'s permission to quote ≤50 words. One commit set. Stop condition: no live claim of a verifier that doesn't exist.
- The verifier overclaim was re-confirmed live tonight in all three places (`POSITIONING.md:76/:145`, `docs/how-rhemata-handles-sources.md:15-17`, `sources/page.tsx:39`).

---

## Where We Are in the Roadmap

(PLAN.md v5.1, linear numbered session list)

- **#1 Back up `sources/` + `ingest_queue.xlsx`** — DONE 2026-07-09 (offsite to Google Drive per Alex; never independently verified from this Mac — real verification lands with #15's restore test).
- **#1.5 Commit the uncommitted working tree** — DONE 2026-07-09 (commit `72476b7`, pushed). Includes migration `058_clf_aliases.sql`, previously applied live but never committed.
- **#2 Honesty fix** — NEXT, not started.
- **#3 Verify the chokepoint conversion** — not started. Tonight's audit sharpened it: the Jul-3 demo doc ("Stuck in the wilderness") resolved to an `owned` source, so the propositions step returned `skipped_licensed` — the gate branch was exercised but extraction+storage never was. Also `ingest.py:33` hardcodes the dead `~/Desktop/rhemata` DOCS_FOLDER path, which will trip #3's demo unless run with `--source-dir` (or fixed first, one line).
- **#4–37** — untouched.

---

## Resolved This Session (2026-07-09)

- **Notion cutover complete and pushed** (`b6da249`): chat now reads five repo files directly (CLAUDE.md, POSITIONING.md, DESIGN.md, PLAN.md, rhemata-status.md); Read Contract in CLAUDE.md; `PLAN.md` created as repo-native v5.1 mirror; `notion-sync/` deleted; Notion mirroring retired for this project.
- **Chokepoint loss-prevention checkpoint** committed and pushed (`72476b7`) — nothing load-bearing lives only locally anymore.
- **Theme contradiction fixed and committed**: DESIGN.md corrected to dark-only/`forcedTheme` (matches `providers.tsx` + `globals.css`); retired light tokens deleted.
- **Tier-1 visibility policy decision recorded** (`ef22a54`): the 25 `unlicensed/shown` sources are a deliberate accepted-risk beta-scope call (Decision 5), not drift; CLAUDE.md policy line corrected to the standing rule (new unlicensed sources register hidden; `shown` requires an explicit recorded beta-scope decision).
- **Full read-only audit ran clean on the load-bearing systems**: license gate verified in all 7 RPCs (no NULL arm, safe_mode read), RLS locked on corpus tables, sentinel sealed at 3 docs, backfill-gap numbers match docs exactly, git synced with origin.

---

## In Progress / Uncommitted Locally

- `CLAUDE.md` — modified, uncommitted, **only dirty file**. Scoped to #14: the held-out chokepoint doc corrections (the "shipped" claim that must not commit until #3 verifies the conversion). Two surgical commits this session (`b6da249`, `ef22a54`) extracted specific sections from it without committing this content.

---

## Open Items (from tonight's audit)

Bucketed **#14 (housekeeping)** unless noted:

- **Standing-rule wording confirmation** — smaller than #14, can ride any session: confirm the corrected visibility-policy wording in CLAUDE.md reads as intended now that it's committed.
- **Dead `~/Desktop/rhemata` path in 8 scripts** — `clean_transcripts.py`, `extract_book_quotes.py`, `generate_excerpts.py`, `ingest_interlinear.py`, `ingest_tahot.py`, `ingest.py` (DOCS_FOLDER), `scrape_youtube.py`, `test_excerpt_generation.py`. The `ingest.py` one **blocks #3** — fix it there; the rest at #14.
- **SKILL.md staleness** — blockers list still says migration 058 "uncommitted" (committed at #1.5) and "`sources/` has no backup" (backup exists, unverified). Make true at #14.
- **PRODUCT.md staleness** — oldest doc in repo (2026-06-14), overlaps POSITIONING.md, outside the five-file read contract; needs Alex's keep/supersede call at #14.
- **Duplicate document titles** — ≥5 titles exist twice in `documents` (possible retrieval double-weighting); investigate at #14.

Carry-over blockers (pre-existing, unchanged):

- Two sentinel docs ("So Great a Salvation," "The 59 One Another's") have no metadata — need Alex's eyeball at #6. Bedford-docx identity (`8.21.24 Prophetic Teaching...docx`) still unconfirmed.
- Offsite backup unverified — proven only by #15's real restore.
- 1,086 documents carry dead `Desktop/rhemata` `file_path` values (harmless to serving; landmine for future scripts). Track.

---

## Live Corpus & Infra Snapshot

(queried live, 2026-07-09)

- **Documents:** 3,796 · **Chunks:** 197,169 · **Propositions:** 2,028 (251 docs covered; 2,980 unlicensed docs at zero — backfill is #17)
- **Sources:** 67 — 39 `unlicensed` (25 shown per the recorded Tier-1 decision) / 26 `public_domain` / 2 `owned` / 0 `licensed`
- **`book_quotes`:** 0 rows (retired; new verified-only table is #21)
- **Sentinel-assigned docs:** 3 · `safe_mode`: off
- **Staging Supabase:** none — production only, no backup/PITR automation in-repo (#15)

---

## Next Session Should

Run PLAN.md **#2 — honesty fix** (copy + system prompt, one commit set). If there's spare capacity, the one-line `ingest.py` DOCS_FOLDER fix unblocks #3 next.
