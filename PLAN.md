# Rhemata — Master Plan (v5.1 · linear)

> **Chat-authored, terminal-committed.** Migrated to repo-native `PLAN.md` 2026-07-09 from Notion `plan.md` v5.1 — Notion sync retired for this project (see `CLAUDE.md`'s Project Knowledge Read Contract). This is the durable guide for the next several months. `rhemata-status.md`'s "Where We Are in the Roadmap" section pulls its one-liners from here. **When this doc and reality diverge, update this doc.**
>
> **Writer rule (differs from `rhemata-status.md`):** chat is the sole *author* of roadmap revisions — proposes changes as a prompt, same propose→commit pattern as any other repo edit. Terminal is the sole *committer* of this file, but does not originate roadmap content itself. `rhemata-status.md` is the opposite: terminal both authors and writes it, directly from live repo/DB state, overwritten each session. Different roles for a reason — this file is judgment and planning; that one is a live fact snapshot.

*Consolidates the four original plans; v4 folded in the July 7 diagnostic sweep; v5 (Jul 8) finalized the quote architecture and re-cut into a linear session list; v5.1 (Jul 8) folds in the pre-chokepoint diagnostic sweep. Durable roadmap; live session state stays in `rhemata-status.md`.*

**How this works:** Chat plans, judges, writes prompts. Claude Code executes. Alex decides. Sessions end at a **safe stopping point** — committed, stable, nothing load-bearing half-built — not at a clock time.

**This cycle's product surfaces: Chat + Study only.** Discover is deferred (parked, not cut).

### Version history

- **v5 → v5.1 (Jul 8):** Pre-chokepoint diagnostic sweep resolved #3/#6/#8–13 + the two flagged items. **Big finding: the entire chokepoint working tree is uncommitted** (`shared_ingest.py` untracked; five scripts + `propositions.py` + docs modified-uncommitted) — added #1.5 loss-prevention commit and repurposed #3 to verification. Commentaries atomicity dropped (watched-load basis). Lexicon dedup bug confirmed. helloao = convert. Long-form extraction confirmed unproven (zero books extracted).
- **v4 → v5 (Jul 8):** Quote architecture finalized — universal minus commentaries, inline, folded into the Groq proposition call, fresh verified-only table (#21–25). `book_quotes` confirmed 0 live rows and retired. Whole roadmap re-cut from thematic tracks into one linear, stopping-point session list.
- **v3 → v4:** The quote verifier the plan assumed exists **does not exist** (July 7 sweep). v4: near-term honesty fix; verifier promoted to a scoped build; paraphrase-and-cite becomes the permanent answer-stream posture; sources/ backup escalated to immediate.
- **v2 → v3:** Discover deferred; landing-page rewrite removes Discover references.
- **v1 → v2:** pre-backfill safety gate; silent-failure defenses as standing rules; re-gated PD growth on the chokepoint only; pulled Phase 3 scoping forward; restored the tier risk model.

---

## Standing session rules

1. Read-only diagnostics confirmed by Alex before any build prompt runs.
2. Dry-run + single-item verification before any full batch.
3. **Every batch/backfill ends with a hard reconciliation count** — attempted / stored / errored / skipped, checked against the DB. A "success" with no count is not a success.
4. Long jobs: `nohup` + timestamped logs, `tail -f`.
5. Git from repo root, never `~`. **Repo root is `/Users/alexwhitley/rhemata`** — the `~/Desktop/rhemata` path in older docs is a dead stub from the July 6 folder move.
6. `CLAUDE.md` / `SKILL.md` updated only after a build is confirmed working. (Note: they currently claim the chokepoint is shipped — false; corrected at #3/#14.)
7. Two isolated commits: build separate from docs. **Exception: #1.5 is a one-shot recovery checkpoint of already-messy uncommitted work — clean slicing doesn't apply retroactively; rule 7 resumes from the next change.** (Alex doesn't use git history for recovery — restore-from-backup is the real mechanism — so clean slicing is low-value here anyway.)
8. No bundling. Own-session items stay own-session.
9. Prompts written fresh each session against the current codebase.
10. **Freeze new-source ingests through unconverted scripts** during the chokepoint period (through #13) — each one widens the backfill.
11. **Answers paraphrase and cite; they never quote freely.** Permanent product posture. Verbatim text reaches users only through the verified quotes surface (the quote track, #21–25). No verification of the token stream will ever be needed because the stream never carries quotes.

---

## Open decisions

| # | Decision | Default |
|---|---|---|
| 1 | Cold storage vs. visibility gate | Gate canonical; deletion parked as final hardening |
| 2 | Quote serving flip rule | Stays OFF. (`quotes_enabled` is plan shorthand — no such flag exists in code; the real serving gate is #23/Q3.) Flip criteria: ≤25 words, one/source/answer, attribution + link out — **AND the verifier is built, passing regression tests, and every quotes row machine-verified. Hard technical precondition, not an editorial call.** `book_quotes` retired (0 rows); the new quotes table is verified-only by construction |
| 3 | Near-1930 PD verification (Lake, Brengle, Penn-Lewis, Morgan, Wigglesworth 1924) | Alex checks pub date per title. **PD line advances every Jan 1 — by launch, 1931 works qualify.** Don't skip titles that go PD while you wait |
| 4 | Admin shell: modal or sidebar | Keep modal |
| 5 | **Risk tier.** Tier 1 ≤20 private = low. Tier 2 public/free = meaningful (DMCA). Tier 3 paid = high. | **You are Tier 1. The moment beta exceeds ~20 OR signup opens → Tier 2 — hard checkpoint requiring serving rebuild + legal items (#32–37) + quote verifier (#22) done first.** The "verified by code" claim can't run at public tier without the mechanism |
| 6 | Where this file lives | **Repo root, `PLAN.md` (canonical, as of 2026-07-09).** Chat authors revisions; terminal is sole committer — same propose→commit pattern as any other repo edit. Notion sync retired for this project. *(Superseded: previously "Notion (canonical) + local mirror `notion-sync/`.")* |
| 7 | Bake a full-text column at the chokepoint? | **Yes.** `shared_ingest.py` has `body_text` in scope at the right moment — add a `documents.full_text` write once (#7); every conversion inherits it. Backfill for existing docs: parked |
| 8 | Commentaries atomicity (Jul 8) | **Dropped.** Converting commentaries loses the current atomic doc+chunks transaction (a failed load could leave a half-written document). Accepted because loads are watched, one-at-a-time, re-runnable. **Revisit if commentary ingestion is ever automated or bulk-run (e.g. at #27).** |

---

## Ground truth — verified July 7–8, 2026

- ❗ **The entire chokepoint working tree is UNCOMMITTED (Jul 8 sweep).** `shared_ingest.py` is untracked; `ingest.py` + the four unconverted scripts + `propositions.py` + `CLAUDE.md` + `SKILL.md` + `.gitignore` are modified-uncommitted; migration 058 untracked. The last commit predates all of it. **`CLAUDE.md` describes the chokepoint as shipped — it is not; it has never been committed or verified.** The whole foundation lives in one deletable working tree → #1.5 commits it (loss-prevention), #3 verifies it.
- ❗ **No quote verifier exists anywhere in the codebase.** The "machine-checked character-for-character" claim in `POSITIONING.md` and the live `/sources` page is aspirational (`system_prompt.txt:112` permits ≤50-word quotes; `chat.py:918-939` streams with zero inspection). → Closed by #2 (honesty) now, #22 (verifier) later.
- ✅ **`book_quotes` (Jul 8):** live table holds **0 rows** — nothing to re-verify or purge. Schema has no verification columns; retired. #21 builds a fresh quotes table. (Ungated public-read serving path `library.py:112-119` + RLS `037:79-80` — harmless while empty, closed by #23 before any row is written.)
- ❗ **Migration 058** (`058_clf_aliases.sql`): inserts two `source_aliases` rows (alex whitley / clf church), idempotent, complete, **already applied to production but never committed.** Safe to commit as-is at #1.5.
- ❗ **`psycopg2_batch` spec is known but bigger than "batch insert" (Jul 8).** Needed shape: batch-embed (not per-chunk) + a single round-trip insert of all a document's chunks. Commentaries *also* wanted atomic doc+chunks, but `shared_ingest` inserts the document row separately (REST) — atomicity would need document insertion to move too. Per Decision 8, that atomicity is **dropped**, so the batch function only needs the batched-chunk-insert (#9).
- ❗ **Lexicon reuse bug confirmed (Jul 8).** `on_existing="reuse"` reuses the document row but **re-chunks from index 0 unconditionally** — no check for existing chunks. Re-running an already-chunked doc produces duplicate chunks with colliding `chunk_index` and nothing stops it. Lexicon needs chunk-count lookup + positional-skip + continued numbering (#11 builds it, #12 uses it).
- ✅ **Chokepoint hooks exist (Jul 8):** the chunk-header bake (`content_fn`/`embed_text_fn`, #8) and connection-reuse (`propositions_conn`, #10) are real, correctly-shaped, generic — not vaporware. Neither has been exercised against a converted call site yet.
- ✅ **helloao = convert, not exempt (Jul 8).** It duplicates the exact flow the chokepoint consolidates and uniquely needs none of the unbuilt hooks — arguably the easiest conversion. Candidate to do first in the chokepoint band.
- ❗ **No canonical full-document text exists.** `content_summary` is a ~600-char summary (619/3,796 populated). Full text lives only in chunks; **186 documents have broken `chunk_index` sequences**. Chunk `content` IS verbatim source text — the verifier's ground truth (and chunks are committed before any quote hook fires — no ordering problem, verified Jul 8).
- ❗ **`sources/` has no backup.** Gitignored, single remote, no backup script. Raw PDFs, transcripts, `ingest_queue.xlsx` exist only on one Mac → #1.
- ❗ **Extraction quality unproven on long-form (Jul 8).** Model `llama-3.3-70b-versatile` hardcoded at `propositions.py:75` (1 Groq call + N embed calls/doc, blocking). Sampled propositions read coherent — **but every proposition in the DB is from short-form YouTube/sermon content; ZERO full-length books have been extracted.** #17's backfill is the first time long-form hits the extractor at scale. Quality is unproven exactly where the paraphrase layer is for. Alex's judgment call.
- ❗ **No staging Supabase project exists (Jul 8).** One production URL/DB pair only; no backup/PITR automation anywhere in-repo. #15 starts from zero — restore-works can only be proven by performing one.
- Sentinel: 3 docs. "The Kneeling Christian" → An Unknown Christian (target known); the other two ("So Great a Salvation," "The 59 One Anothers") have no metadata — **need Alex's eyeball/decision** (#6). Alias gap is **forward-looking only** — existing Deere/Brown/Bedford docs are already correctly resolved, not sentinel'd; #6 protects future ingests, doesn't fix broken data. `murray_surrender.pdf` = confirmed duplicate (identical hash to the file already in DB) → just delete the stray.
- Backfill gap: **2,980 unlicensed docs, zero propositions** (251 covered). Zero `licensed` sources — gate branch untested.
- Corpus (live Jul 8): 3,796 docs · 67 sources (39 unlicensed / 26 public_domain / 2 owned / 0 licensed) · 197,169 chunks · 2,028 propositions. Commentaries = 4 sources / 493 docs / 86,501 chunks (~44% of chunks), all `public_domain`, already excluded from propositions.
- `jewish_perspectives`: 2 rows, zero code references — clean to drop (#14).

**Still unverified — confirm before relying on:**
- [ ] Does Supabase backup/restore actually work? (never tested, no staging — #15)
- [ ] Groq long-form extraction quality (never run on a book — first real test at #17)

---

## Roadmap — linear session list (v5.1)

> Sessions are defined by **safe stopping points**, not clock time: each ends at a committed, stable state with nothing load-bearing half-built. This linear order **replaces the old thematic tracks** (Track 1/2/2B/2C/3) — do the next unchecked session. Track labels kept in parentheses for provenance. Numbers are stable IDs.

### Now / safety (both loss-prevention — do first)

**1. Back up `sources/` + `ingest_queue.xlsx`** (T2·0) — offsite copy. 5 min, irreversible-loss guard. *Stop: backup exists and is verified.*
**1.5. Commit the uncommitted working tree** (T2·1) — **loss-prevention checkpoint.** The entire chokepoint conversion is uncommitted and lives only in this working tree. Commit it in **one checkpoint commit** (Alex doesn't use git history — clean slicing has no payoff here). Keep migration 058 clean (idempotent, proven live). **Do NOT commit `CLAUDE.md`'s false "chokepoint shipped" claim** — either hold the docs out of this commit or add a one-line "committed, not yet verified" correction; docs get made true at #14. *Stop: working tree committed and pushed; nothing load-bearing lives only locally.*
**2. Honesty fix — paired** (T1·1a + T3·1) — rewrite `POSITIONING.md` + `/sources` copy to the real posture (paraphrase-and-cite; quotes are a gated future surface) AND remove `system_prompt.txt:112`'s quote permission. One commit set. *Stop: no live claim of a verifier that doesn't exist.*

### Foundation

**3. Verify the chokepoint conversion actually works** (T2·1 remainder) — run `ingest.py` on a demo item, confirm it routes through `shared_ingest` correctly and produces the expected doc/chunks/propositions. Reconcile `CLAUDE.md`'s "shipped" claim to reality. *Was "commit chokepoint work" — the commit moved to #1.5; this is now the verification that was never done.* *Stop: conversion confirmed working on a real item, or the gap documented.*
**4. Resend transactional email** (T3·2) — kills the live Supabase auth-email rate-limit pain. *Stop: auth emails send via Resend.*
**5. Landing page copy rewrite** (T1·7) — drop Discover + Jewish-perspective refs; Pastors' Notes = coming; anti-flattening hook leads; quote language matches #2. *Stop: committed.*

### Chokepoint — clears the corpus-growth gate at #13

**6. Aliases + sentinel cleanup + strict mode** (T2·2) — add Deere/Brown/Bedford/Church Life Class aliases (forward-looking only — existing docs already resolve). Reassign the 3 sentinel docs: Kneeling Christian → An Unknown Christian (known); **decide targets for "So Great a Salvation" + "The 59 One Anothers" (need Alex — no metadata)**; delete the `murray_surrender.pdf` stray duplicate. Strict mode in shared_ingest refuses silent-sentinel. *Stop: silent-sentinel class ended.*
**7. Add `documents.full_text` to shared_ingest** (T2·3, Decision 7) — before any conversion, so all inherit it. *Stop: new ingests write full_text.*
**8. Convert `ingest_magazine.py`** (T2·3a) — uses the existing chunk-header bake hook (idx==0 special case). *Stop: dry-run + single-item verified.*
**9. Build + demo `psycopg2_batch`, then convert `ingest_preceptaustin.py`** (T2·3b) — batched-chunk insert only (atomicity dropped, Decision 8); reuse-by-title. *Mid-point stop: batch demoed + committed. Final stop: conversion verified.*
**10. Convert `ingest_commentaries.py`** (T2·3c) — reuses the batch + connection-reuse hook. **Straight convert, no atomicity rework** (Decision 8). *Mid-point stop at the dry-run line if long.*
**11. Build + demo `on_existing="reuse"` chunk-dedup** (T2·3d prep) — chunk-count lookup + positional-skip + continued numbering (fixes the confirmed re-chunk-from-0 bug). Lexicon needs it. *Stop: mechanism demoed on one item.*
**12. Convert `ingest_lexicon.py`** (T2·3d) — highest risk. *Stop: dry-run + single-item verified.*
**13. Convert `ingest_helloao.py`** (T2·3e) — **convert (easiest, needs no unbuilt hook — consider doing FIRST in this band as a confidence-builder).** → **Chokepoint complete. PD corpus growth unblocked (rule 10 lifts).** *Stop: all pipelines route through shared_ingest.*

### Housekeeping (low-risk batch)

**14.** (T-tail) Folder renames (lexicon/→stepbible/, documents/→inbox/) + drop `jewish_perspectives` + delete duplicate Murray files + **make `CLAUDE.md`/`SKILL.md` true** (they claim the chokepoint is shipped — correct to reality; source/alias counts, repo path, Ravenhill date). *Stop: committed, docs current.*

### Core serving — make the existing corpus answer well

**15. Safety gate** (T2·0 remainder) — stand up staging Supabase (none exists) + perform one real backup/restore + regression test for the fail-closed copyright gate. *Stop: restore proven, gate test green.*
**16. Feedback→flag-proposition path + dry-run backfill on one genre** (T2·5 prep). *Stop: subset verified + reconciled.*
**17. Full propositions backfill** (T2·5) — 2,980 unlicensed docs, excl. PA; transaction-safe; hard reconciliation count. **First time long-form books hit the extractor — spot-check book output quality before trusting the batch (extraction unproven on long-form).** Quotes do NOT ride this (they run whole-corpus at #25). *Stop: reconciled + book quality eyeballed.*
**18. Serving-rule build** (T2·6) — propositions into `match_chunks`/`search_chunks_fts` + 5 RPCs, dedup, two pools fused; staging; one test-licensed source; 20–30 queries. *Mid-point stop after RPCs wired + gate-tested.*
**19. Perplexity-style source links** (T3·5). *Stop: citations link to source cards.*
**20. Serving experience** (T2·7) — prompt rewrite → citation UI/source cards → reader "study notes" view (design pass first) → library Full-text/synthesis indicator → ~50-query QA. *Each sub-step its own stop.*

### Quote track (independent; hard order — #22 and #23 before #24)

**21. Q1 — table + gate** — new quotes table + migration; thread `source_kind` into `process_document()`; commentary gate wired (`source_kind='commentary'` excluded), nothing extracts yet. *Stop: gate in place, no extraction.*
**22. Q2 — the verifier** (long pole) — exact-substring check vs committed chunk `content`, fail-closed, boundary-spanning rejected; + regression suite (good / off-by-one / cross-boundary / wrong-source). *Stop: suite green.*
**23. Q3 — serving gate** — replace the ungated `book_quotes` read path; serving reads verified rows only. **Must land before #24.** *Stop: no unverified row can serve.*
**24. Q4 — inline extraction** — fold quote candidates into the single Groq proposition call; verify-at-storage; fail-closed. *Stop: new ingests produce verified quotes.*
**25. Q5 — whole-corpus quote backfill** — ~3,303 non-commentary docs / ~110,668 chunks; separate from #17; hard reconciliation count. *Stop: reconciled.*

### Corpus growth (T2B; flexible, low-risk, any order after #13)

**26.** New Wine ~194 remaining issues.
**27.** PD commentaries via HelloAO — Barnes, Gill, Spurgeon *Treasury of David*, Calvin, Pulpit, Poole, Vincent, Tyndale notes. *(If this is ever bulk/unattended, revisit commentaries atomicity — Decision 8.)*
**28.** Reference datasets — **each a NEW script** routed through shared_ingest: openbible.info cross-refs, Strong's, TIPNR, Nave's/Easton's/Torrey's Topical, open Bibles.
**29.** PD books (Simpson, H.W. Smith, Moody, Müller + Decision-3 titles as they clear) + Pentecostal archives (Azusa *Apostolic Faith* 13 issues, Bartleman, Consortium selective).

*Never: scrape platform clips; ingest copyrighted books without a signed license.*

### Phase 3 — the differentiator (T2C)

**30. Scope + design owned-synthesis pipeline** (currently "???") — new verse-anchored commentary from PD inputs only; Rhemata-owned, zero licensing exposure. Can start once #27/#29 land. *Stop: estimate + design pass exist.*
**31. Build owned verse-anchored synthesis.** Sized after #30.

### Pre-public-tier gate (T1 rights + pre-deploy — gates the Tier-1→Tier-2 jump at beta >20 / signup, per Decision 5; NOT near-term)

> **Start the lawyer-dependent items early** so the wait overlaps: **dual-use license template** and **modern-voice outreach** (gated on the template existing).

**32.** STEPBible CC-BY-NC audit — verify BY vs NC; exclude NC.
**33.** CC BY attribution surface — openbible.info + STEPBible require in-product attribution; license voids without it. Before serving those.
**34.** SermonIndex visibility audit — resolve the 6 `shown` sources before serving.
**35.** DMCA agent + takedown procedure (~$6).
**36.** Guest-limit hardening (check 052/057 coverage).
**37.** Admin remainder (contributor activity view, pending-count badge, `DELETE /admin/contributors/{id}`) + Pass B mobile drawer + post-deploy backlog.

### Ordering calls (Alex-approved Jul 8)

- **A** — staging/restore/regression gate deferred to #15 (it gates backfill + serving, not the chokepoint conversions); only the two irreversible loss-prevention items stay immediate (#1 backup, #1.5 commit).
- **B** — core serving (#15–20) before quotes (#21–25) before growth (#26–29); no rework cost since #25 backfills whole-corpus regardless.
- **C** — legal/rights clustered at #32–37; lawyer-dependent ones start early to overlap the wait.
- **D** — Resend (#4) + landing rewrite (#5) pulled early as independent quick wins.
- **E (Jul 8 sweep)** — commit split out to #1.5 as loss-prevention; #3 became verification. helloao (#13) recommended first-in-band. Commentaries atomicity dropped (Decision 8).

---

## Scope honesty

~38 sessions, stopping-point-defined (typical sitting ~4 h, but sessions end on a safe state, not the clock — heavy builds #9/#10/#12/#22 have explicit mid-points). Heaviest stretch: core serving (#15–20) plus the two backfills (#17, #25). **Mid-2027 holds with margin.** The two immediate loss-prevention items (#1, #1.5) are minutes of work guarding against total loss — do them before anything else. The honesty fix (#2) is one small session that buys down the largest live *trust* risk.

---

## Superseded / killed

**Superseded structure:**
- **Thematic tracks (Track 1/2/2B/2C/3)** — replaced Jul 8 by the linear session list. Track labels kept in parentheses for provenance.
- **Notion as this file's home** — replaced 2026-07-09 by repo-native `PLAN.md`. See Decision #6.

**Deferred (not cut — revisit post-launch):**
- **Discover surface** — parked this cycle. Routes/code dormant, don't rip out.

**Killed:**
- **Stream-side quote verification** — never to be built. Rule 11 makes it structurally unnecessary.
- **10× dedicated quote-extraction pass** — rejected Jul 8 on cost; extraction folds into the single Groq proposition call (#24).
- **License-gating quotes** — rejected Jul 8; quotes are a universal UX feature (minus commentaries), not a copyright-safety layer.
- **Commentaries atomic doc+chunks transaction** — dropped Jul 8 (Decision 8); watched-load basis. Revisit if automated.
- **Clean git-history slicing of the rescue commit** — waived Jul 8; Alex recovers by restore, not bisect (#1.5 is one checkpoint commit).
- Attorney consult — dropped July 5; five products reassigned to #32–37.
- Quotes in hybrid proposition cards — superseded by the separate verified table (#21).
- "Precept Austin gift" — reversed; PA permanently excluded.
- Launch-blocking framing — launch ~mid-2027; runway is for doing architecture right.
