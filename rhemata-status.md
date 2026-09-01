# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to, never
durable truth — the durable records are the code, git history, PLAN.md,
docs/roadmap.md, docs/plan-archive.md, and CLAUDE.md. Counts are NOT recorded
here except as a dated snapshot from a specific live query; treat any count
seen elsewhere as unverified.

Last verified: 2026-09-01. **PLAN.md has zero active blockers.** `main` =
`c937b6d`, **ahead 4, NOT pushed**. This session was frontend work plus
committing a parallel Codex session's output. No database writes, no deploy.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines.

---

## Current state

**Four commits, none pushed.** `1db7793` frontend, `2067dd1` biblical-depth
Phase 0+1 (Codex), `41f498d` biblical coverage baseline (Codex, earlier
session), `c937b6d` ingestion TSV review dispositions. Pushing deploys all four
Railway services — attended gate.

**Codex delivered Phase 0 and Phase 1 of the biblical-depth plan, NOT Phase 2.**
The session began on the belief Phase 2 was done; it is not. Verified absent:
`scripts/parse_{tyndale,tipnr,openbible}_context.py`,
`test_biblical_context_parsers.py`, `scripts/fixtures/biblical_context/`. What
landed: four manifests + registration packet (Alex approved the dispositions
2026-09-01, recorded in it) and `backend/app/services/source_use_policy.py` as
the canonical protected registry. Both suites re-run here, not read: exit 0 (4
manifests, 0 failures) and exit 0 (16 tests). **Nothing imports the policy
module on a serving path — no answer behavior changed.** Plan:
`docs/superpowers/plans/2026-09-01-biblical-depth-source-policy.md`.

**The packet's governing-record change is NOT applied.** It carries proposed
replacement text for CLAUDE.md Settled #5 and the implicated ARCHITECTURE
section. Phase 0's own exit condition requires Alex's explicit approval of that
diff before any answer-path work starts. Unapproved and unapplied.

**Four Alex-directed frontend changes shipped (`1db7793`), all unverified in a
browser** — typecheck and lint only.

1. **Chat input has no focus ring, deliberately.** Reverses the fix for
   finding #8 of `docs/audits/2026-08/b6_accessibility_pass_2026-08-28.md`.
   Alex was told it re-opens that WCAG 2.4.7 gap and chose it. The textarea
   keeps `focus:outline-none`, so the product's most-used input has zero
   visible focus indicator.
2. **Answer `h2`/`h3` are pure white** for hierarchy; inline `strong` stays
   `text-foreground` — two tiers, not three. `--ring` is still shadcn's blue
   (`210 74.8% 49.8%`), the only blue token in a warm palette, on 40 sites.
3. **STEPBible CC BY notice removed from four inline UI sites.** Still served
   at `app/sources/page.tsx:72` — now its ONLY location. It must survive any
   future edit of that page or the product falls out of CC BY compliance.
4. **Precept Austin word studies now render in the inline Study Panel**,
   reversing SP2's deliberate lexicon-only decision on Alex's call. "From the
   Library" stays out; the standing PA exclusions (answer retrieval, quote
   pipeline, paraphrase) are untouched. `/study/excerpt` is auth-gated, so
   guests get an honest empty. No PA credit displays — the endpoint returns
   `{"content"}` only, matching `/study`.

**The `/study` word-search regression is live and unfixed.** Searching a word
fetches its PA article into `wordStudyContent` (`app/study/page.tsx:954`) and
never renders it — `WordStudyPanel` shows lexicon only. Dropped in `40cdb4c`;
the orphaned fetch says accidental. Alex chose the panel over it. That page's
`InlineWordPanel` (tap a token in a verse) does still show the excerpt.

**Prose-channel quotation guard is live and unmeasured.** `6e60486` is pushed,
so it runs on the real answer path via `producer.py`'s `_has_ungrounded()`. Its
false-positive rate has never been measured on live traffic; the 400-char
window and surname matching were tuned on five answers. Its punctuation
normalization is load-bearing — corpus text uses curly quotes, the writer emits
straight ones, so removing the fold makes it refuse ACCURATE answers.

**Scripture fidelity is unguarded.** `verify_verse_mention()` is an EXISTENCE
check only; nothing compares a claim or quoted wording to the verse text, and
the verifier only sees references the model DECLARES, so unreferenced
Scripture quotation is invisible to every guard.

**Auth flow (`df2d5f9`, `5473265`) — do not revert.** Beta access is per-device
`localStorage`, trimmed and case-insensitive; `hooks/useAuthGate.ts` is the sole
owner of auth-modal state. Pre-existing: a `next-themes` hydration mismatch.

**Every push to `main` deploys production.** All four Railway services rebuild
(`watchPatterns: []`), so even docs-only commits redeploy.

**Two traps.** `/async-chat/result` is SSE with JSON spanning multiple `data:`
lines — parse by EVENT, or an answer reads as zero-citation, exactly like an
attribution-guard failure. Railway deployment meta populates progressively;
mid-`BUILDING` `rootDirectory`/`configFile` read null.

**Decided, do not re-raise:** guest-speaker attribution stays as-is;
`/corpus-inventory/export` stays public. Privacy/ToS DEFERRED pending legal
entity, jurisdiction, contact; `POLICY_COPY` in `consent.py` is duplicated in
`consent-gate.tsx` and they move together.

**Quote rail still off (`QUOTE_SELECTION_ENABLED=false`).** CLF's 63 sermons
are auto-transcribed audio under `sermon_transcript` with a confirmed
mistranscription and nothing gates on transcript status — **before the flag
flips back on, CLF needs quoting exclusion or audio confirmation.** 15 further
CLF recordings are `held_permanent` for content shape + pastoral privacy.

**Search analytics live; B7 done.** A degraded outcome stamps
`answer_jobs.analytics_outcome` (`scripts/analytics_health_report.py`), but
that marker has never fired. **New Wine A2 is NOT ingestion-ready** — held by
Alex, no live-call budget without a fresh ceiling.

**Still on the old name deliberately:** applied migrations; this filename; the
DB source row and the two code sites naming it; `rhemata_tracker.xlsx`; the
Vercel project; `rhemata.app` (404); the API hostname
`rhemata-production.up.railway.app` (frontend API base URL moves in lockstep);
"manna"/"rhema" in corpus. Full list: docs/roadmap.md Triggered.

---

## Findings surfaced, not yet acted on

- **The biblical-depth workstream has no roadmap classification.** It now has
  committed code but no entry in `docs/roadmap.md`. Classification is
  chat-originated per the Project Knowledge Read Contract — Alex's call, not
  the terminal's.
- **Coverage baseline (`41f498d`):** of 48 retrieval questions, 14 strong, 19
  thin, 2 empty, 13 misretrieved; weakest in OT passage interpretation,
  biblical context, whole-Bible synthesis. More material alone will not fix
  it — routing and source concentration shape the answer.
- **`scripts/sp1_answer_harness.py` does not exercise the real answer path.**
  It reimplements generation and never imports `producer.py`. Any before/after
  comparison run through it measures a proxy — relevant to judging the depth
  work.
- **A served citation carried a dangling `chunk_id`** —
  `0b9d1930-7103-4520-8e37-e382dc7b3227` matched zero of 186,944 `chunks` rows
  while its document resolved normally. Needs one check of how `producer.py`
  populates it.
- **`sources/` must never go in this repo** — the remote is PUBLIC. Same rule
  keeps the 60 untracked `new_wine_issue_02_1973_review_*` dirs out of git;
  they were deliberately excluded from this session's commits, as were
  `reference_grounding_review/` and `tasks/` (local scratch).
- **The house source row is still named "Rhemata"** (`bf6d9e28-…`) — rename
  moves `name`, `slug` and both alias columns together (Invariant 6). Attended.
- **11 ingested CLF documents carry an offering appeal**, one an usher
  direction, one a dismissal. Named-congregant audit still open.

---

## Next single item

**None designated — Alex picks.** The session leaves four unpushed commits;
pushing is a production deploy of all four services.

Open, unordered: push + deploy, then measure the quotation guard's live
false-positive rate; Codex resuming biblical-depth Phase 2 (parsers); Alex
ruling on the packet's governing-record diff; the `/study` word-search
regression; browser verification of this session's four UI changes; Scripture
fidelity; the dangling `chunk_id`; the DB source row rename; the 301/318
re-ingest (cost estimate first); New Wine A2 (fresh ceiling); quote
accuracy/relevance repair; privacy/ToS drafts.
