# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-19 (session close — master ingestion-candidate
spreadsheet built, two-tab split, Round 1–3 candidates + URLs loaded).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

Codex is the primary working surface; custom multi-provider coordinator /
overnight harness remain retired (Invariant 15). Beta Critical Path
operating model; `PLAN.md` = blockers (still empty — W1–W9 finish-line
closed 2026-08-19, untouched this session); `docs/roadmap.md` = later work.

**This session — built the master ingestion-candidate spreadsheet system,
end to end, across four turns.** Repo-file work throughout, plus one real
database write (the sync script's `--apply`, attended and Alex-approved
after reviewing a dry run) and one read-only corpus cross-check. No
migrations; admin panel and frontend untouched. Full mechanics recorded in
CLAUDE.md's Landmines section — not repeated here.

1. Built `docs/ingestion/master_ingestion_queue.xlsx` (tracked in git, not
   gitignored like the YouTube/magazine trackers) from the 6 live
   `source_ingest_queue` rows plus the 6 hardcoded frontend research-target
   cards. Verified by re-reading the finished file, not by trusting the
   write.
2. Built `scripts/sync_master_ingestion_queue.py` — dry-run-by-default,
   `--apply` required to write. A synthetic-scenario test caught and fixed
   a real bug before it ever touched the real database: blank sheet cells
   would have nulled out NOT-NULL execution-tracking columns on overwrite.
   Ran `--apply` once for real, Alex-approved: a genuine no-op (0 creates,
   0 overwrites) — the real-write path is still unproven against an actual
   change.
3. Restructured the workbook into two tabs on Alex's decision: Discovery
   (raw, unvetted — the sync script structurally cannot open this tab) and
   Queue (vetted, matches `source_ingest_queue`'s shape). All 12
   pre-existing rows verified preserved across the split. Loaded 112
   unique candidates from a Round 1–3 research pass into Discovery, all
   `verification_status=unverified`. Cross-checked by name against the
   live `sources` table (read-only role): 4 already in the corpus (Bill
   Johnson, Randy Clark, Daniel Kolenda, Craig Keener) — flagged, not
   silently treated as new.
4. Filled Discovery-tab URLs for 109 of the 112 from a second research
   pass; 3 explicitly-ambiguous names left blank with a note instead of a
   guessed URL. Renamed the URL columns to carry the tab's existing
   `claimed_` convention for unverified guesses. Two rows flagged
   known-suspect for Alex to manually check before trusting at all: Loren
   Cunningham and Reinhard Bonnke, both deceased, both listed with clean
   live-looking personal domains.

All 3 commits from this session pushed to origin (`e0eb606`, `4af426e`,
`f2a9196`). No open blocker created.

---

## Classified work

Unchanged from last close except one resolution: the "real DB-backed
future-ingestion-candidates table" item flagged Deferred/non-blocking at
last close is now resolved by this session's work — Alex's decision was a
spreadsheet, not a database table, so that open question is closed, not
still pending.

Still outstanding, still not triaged into `docs/roadmap.md`: the frontend
lint debt (27 pre-existing `react-hooks/set-state-in-effect` errors) and the
parked harness-adapter git stash on `claude/harness-claude-cli-adapter`.

---

## Next single item

Nothing blocking. Options for Alex: promote a Discovery-tab candidate
through real vetting to prove the Queue → database `--apply` path against
an actual change (only proven as a no-op so far); manually check the two
flagged deceased-person URLs before trusting them; or pick up
`docs/roadmap.md`'s B1/A1 items. Active blocker count **0**.
