# New Wine — Live Status

Point-in-time state only. Overwritten each session, never appended to. Durable
truth lives in code, git history, `PLAN.md`, `docs/roadmap.md`,
`docs/plan-archive.md`, and `CLAUDE.md`.

Last verified: 2026-09-04. **PLAN.md has one active blocker (B8), promoted this
session.**

---

## Current state

**A read-only quality diagnostic turned into four production corpus changes, a
graded quality baseline, and one self-inflicted live defect.** Four commits,
nothing pushed; local `main` is 28 commits ahead of `origin/main`.

**What changed in the live corpus** (corpus data has no deploy step — all of
this is serving now):

- `b641898` — **79 sermon documents rebuilt.** Re-fetching every pre-fix
  video's real json3 captions and comparing against stored text found 14
  documents holding under 55% of what was said (worst 37%) and 65 holding
  55–80%. Rebuild recovered **+139,669 words (1.48x)**, 79/79 present, zero
  duplicates. One document failed mid-run at the proposition step (which rolls
  back after the old row is already deleted) and was retried successfully.
- `b641898` — **four stored positions rebuilt** after 18 `position_evidence`
  rows were removed with their truncated-text propositions. All four went from
  10–12 evidence rows to 15, no scope change, prior versions retained.
- `c852963` — **one guest interview silenced.** "The Truth About Nephilim,
  Watchers, and Demons" is Savchuk-hosted with the guest's doctrinal claims
  attributed to the host; now `silent_context`.
- `bacbe84` — two stale CLAUDE.md landmines corrected (the prose quotation
  guard is deployed, not pending; the caption defect is not closed).

**The graded baseline.** 30 sermon passages that genuinely reached the top-8
evidence pool of real answers, graded blind by Alex: **20 keep, 2 borderline,
8 kill**. Source predicted the grades better than any measured text feature —
Derek Prince 9/9 keep, CLF Church 0/5. Alex has ruled out excluding sources, so
any future solution must work per passage. Full evidence and per-passage table:
`docs/superpowers/specs/2026-09-04-sermon-passage-quality-design.md`.

**No filter was built, deliberately.** Four mechanical detectors were tried and
all four failed, each with convincing in-sample numbers that dissolved on
inspection. The `>>`-marker rule looked perfect (3 of 8 kills, 0 of 20 keeps)
and is wrong — see the new CLAUDE.md landmine. Every real finding this session
came from reading the material.

**Two independent cross-model reviews** (one forming its own view from the
evidence, one attacking the recommendation) converged on the same two
conclusions: hard-exclude rather than soft down-weight, and build nothing until
there is a retrieval-weighted, CLF-oversampled labelled set.

**Not deployed.** Vercel and Railway are unchanged from the 2026-09-03 release.
No code on the serving path changed this session; the corpus underneath it did.

---

## Session outcome and measures

- Shipped: four commits — one ingest/repair build, one corpus fix, two docs.
- Acceptance: passed for the rebuild (79/79 reconciled, zero duplicates, all
  author damage repaired and verified) and the position rebuild (4/4, no scope
  change). The original diagnostic question is answered.
- Unplanned investigations started: **1** — the caption-retention measurement,
  which began as a bounded check and became a 381-document probe plus a
  79-document production rebuild. Alex approved each escalation explicitly.
- Findings promoted to Blocker: **1** (B8, below). Two classified Scheduled
  (Ravenhill revert; the labelled-set draw). One Parked (the repetition signal
  — mostly genuine preaching repetition, not corruption).
- Scope changes approved by Alex: the full measurement, the re-ingest, the
  position rebuild, and the commits.
- Original outcome completed: **yes**, and it produced more work than it closed.
- Active critical-path item count: **1** — B8.

---

## Next single item

**B8 — the punctuation-induced refusal risk, which this session created.**

Rebuilding from raw json3 captions removed sentence punctuation: 20 of the 79
rebuilt documents are wholly unpunctuated, and 391 unpunctuated chunks were
added to the 337 already present. `prose_quotation_guard.normalize_for_match()`
folds quote characters, dashes, ellipsis and whitespace but **not sentence
punctuation**, so a writer quoting accurately and punctuating naturally fails
the substring match and drives regenerate-once-then-refuse.

Verified live against a rebuilt Kolenda chunk: quoted verbatim it passes; the
same words with a comma and a full stop added are flagged ungrounded; with only
a full stop added, flagged. Quotation appeared in 4 of 7 answers in an earlier
real sample, so this is not a rare path.

Deliberately not fixed unilaterally — the narrow option is folding sentence
punctuation on both sides of that comparison, which *widens* a safety guard and
needs Alex's decision, not an executor's. **The classification itself is also
Alex's to confirm:** it was promoted to Blocker this session on the documented
bar (concrete failure, live evidence, affected beta surface, named closure
condition) with no current item to displace, and can be downgraded.

Then, in order: revert the ~20 Leonard Ravenhill documents rebuilt from
captions that cannot transcribe 1960s tape ("the lowing of the auction" for
"the lowing of the oxen") — backups exist; and the labelled-set draw that gates
any future filter work.

The review document at
`docs/superpowers/specs/2026-09-04-sermon-passage-quality-design.md` is written
for a fresh reviewer and carries six explicit questions, including whether the
79-document rebuild was correct at all given it did not measurably improve
graded quality (62% keep on rebuilt passages vs 68% untouched).
