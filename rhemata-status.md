# rhemata-status.md

**As of:** 2026-07-12 · terminal-owned · **overwritten each session, not a log** (history lives in git history; this file is only the current snapshot).

**Source of truth by domain:** durable architecture/decisions → `CLAUDE.md` · messaging/positioning → `POSITIONING.md` · styling tokens → `DESIGN.md` · roadmap → `PLAN.md` · **this file → live state only, nothing durable, nothing "how it works."**

---

## Current Priority / Next Action

- **Current priority:** none open. #6, #7, and #8 are all DONE and pushed. Next session opens on **#9, diagnostic-first (read-only)** — do not start building until scope is confirmed.
- **Next action:** #9 — confirm the exact shape of `psycopg2_batch` (the still-unbuilt `NotImplementedError` stub in `scripts/shared_ingest.py`'s `_INSERT_MODES`) before converting `ingest_preceptaustin.py`. This is genuinely different from #7/#8: those conversions needed no new shared-writer machinery; #9 does. Scope it well here — `psycopg2_batch` is shared infrastructure #10 (`ingest_commentaries.py`, PLAN.md: "reuses the batch + connection-reuse hook") also depends on, so a rushed or narrow build here creates rework at #10.

---

## Where We Are in the Roadmap

(PLAN.md v5.1+, linear numbered session list)

- **#1–#4:** DONE (see git history; not restated here).
- **#5.5 (harness hardening):** DONE end to end — every exit condition closed, all three diagnosed harness bugs closed. Commit trail: `35ae840` → `8816804` → `6379925` (recording + record-primary gate) → `f2378a7` (MCP write-gate) → `b6340d5` (bug #1: per-agent write-log scoping) → `96bc3ff` (exit condition (a): prose-trust replaced with a match-check) → `874ba8f` (bug #3 retired) → `7afc77c` (report-to-disk build dropped, scope decisions recorded). Full design history and diagnostic writeups live in CLAUDE.md's "Harness / Agentic-Loop — Gate Design Principles" section, not here.
- **#6 (aliases + sentinel cleanup + strict mode): DONE** — commit `dc39dab`. Four `source_aliases` rows inserted, "The Kneeling Christian" reassigned off the sentinel, `citation_mode` standing rule established (CLAUDE.md). First real corpus write through the finished harness gate — clean pass.
- **#7 (`documents.full_text` chokepoint): DONE** — commit `55e46f1`. Migration `060` + one field addition in `shared_ingest.py`, verified live via dry-run + real test ingest.
- **#8 (convert `ingest_magazine.py`): DONE** — commit `0935697`. Routed through `shared_ingest.ingest_document()`; gained `--dry-run`/`--source-dir` safe-test flags; chunk-header embed asymmetry independently proven via recomputed-embedding cosine comparison, not asserted. Two findings surfaced and deliberately left unfixed — see "Open Flags" below.
- **#9 (build `psycopg2_batch`, then convert `ingest_preceptaustin.py`): NOT STARTED.** Next session opens here, diagnostic-first per the standing rule that build sessions follow a read-only scoping pass.
- **#10–#13, #15–#37:** untouched.
- **#14 (T-tail housekeeping):** docs-truth clause DONE (`80b1d50`). Duplicate Murray file deletion confirmed done (same file as #6's delete) but #14's own committed text still reads "NOT happened" for that specific point — stale, not yet corrected (see Open Flags). Folder renames (`lexicon/`→`stepbible/`, `documents/`→`inbox/`) and the `jewish_perspectives` drop remain genuinely open, untouched.

---

## Open Flags — carried forward, none resolved this close

1. **Rule 10 freeze is a bare-substring match, not an invocation check** (found at #8, 2026-07-12). `check_rule_10_freeze()` in `guard_pretooluse.py` denies any Bash command merely *mentioning* an unconverted script's filename (including harmless `py_compile`/`git diff`/`git status`), and doesn't know when a script has actually been converted mid-session — it kept denying `ingest_magazine.py`'s real-ingest verification even after #8's conversion was complete and correct. **Will recur identically at #9–13.** Known fix: switch to an invocation check (reuse `SCRIPT_INVOCATION_PATTERN`/`is_known_write_script_invocation`'s approach, already used elsewhere in the same file) instead of a bare substring match, and/or drop each script from `UNCONVERTED_INGEST_SCRIPTS` once its conversion is verified. Needs its own harness session — not fixed piecemeal mid-conversion.
2. **Magazine queue hard pre-ingest gate — 27 of 27 (100%) pending articles contaminated** (found at #8, 2026-07-12; corrects an earlier undercount of 24/33 that only checked the fenced ` ```json ` form and missed a bare `{...}` form). Every non-flagged article currently in `sources/magazine/03_approved/` carries JSON-wrapper leakage in its body. **No article in the queue is safe to ingest for real right now** — this blocks any real magazine ingest run, independent of #8's now-working conversion. Likely root cause: the Pass 2/3 extraction pipeline (`extract_magazine.py`), previously fixed once on older files via `fix_article_json.py`, resurfaced on the current pending batch. Needs its own diagnosis session.
3. **`on_existing="reuse"` PATTERN — two known holes** (found at #7, 2026-07-12): (1) unconditional re-chunk/re-insert instead of skipping existing chunks — already in PLAN.md #11's planned scope; (2) document-row build (including `full_text`) skipped entirely on reuse — NOT in #11's current stated scope. Both harmless today (`ingest.py` is the only converted script and never uses `on_existing="reuse"`). Both come due together at #12 (lexicon), the first script to actually exercise this path. Recommend: before #12, widen #11's scope to cover hole (2) explicitly, and promote this from code comments into CLAUDE.md.
4. **Database-number verification gap** (adjacent-and-open since #5.5's exit-condition-(a) close). The harness gate proves a write happened and can independently check what it's *described* as — it does not verify that a claimed reconciliation COUNT (attempted/stored/errored/skipped) is actually correct against the database. Nothing in the harness queries the database to check claimed counts today. Not a regression, not newly introduced — a known, named gap, undecided whether/when to build.
5. **GOVERNED_FILES gap.** `guard_pretooluse.py`/`settings.json` (the harness's own safety machinery) are not themselves in `GOVERNED_FILES` — a subagent editing them would only be logged as a generic write, not denied. Fix: add them. Explicitly scoped as its own separate session, not a rider on any current work.
6. **PLAN.md #5.5 closing line is stale.** PLAN.md's own #5.5 entry still literally ends "#5.5 as a whole is NOT DONE until exit condition (a) also closes" — despite (a) having closed in commit `96bc3ff`. A rewrite was drafted in an earlier session but never confirmed or committed. PLAN.md content is chat-authored/terminal-committed only — needs Alex's explicit go-ahead on replacement wording, not a unilateral terminal edit.
7. **PLAN.md #14 drift.** Same shape as #6 above: #14's own committed text hasn't been updated to reflect that its Murray-duplicate sub-item is done. Folder renames and the `jewish_perspectives` drop are genuinely, separately still open within #14.

---

## Standing Carve-Out (unchanged across many sessions)

Working tree normally carries exactly this and nothing else: modified `SKILL.md` (unrelated pre-existing drift, last touched 2026-07-10/11 on Resend/auth content — not this session's work) + untracked `.agents/`, `.claude/skills/`, `skills-lock.json` (skill-loader paths). Still needs a `.gitignore`-or-commit decision so clean-tree checks stop flagging it. Confirmed present and unchanged at this session's close.

---

## Next Session Should

Open on **#9, diagnostic-first, read-only**: confirm what `psycopg2_batch` actually needs to support (precept austin's batched-chunk insert, later reused by commentaries' connection-reuse pattern) before writing any code. Expect the Rule 10 freeze (flag 1 above) to block real-ingest verification the same way it did at #8 — same main-session workaround applies, still not a harness fix. Everything in "Open Flags" above is carried forward untouched; none of it is this session's or the next session's problem to solve incidentally — each needs its own scoped session when picked up.
