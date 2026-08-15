# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (F5 read-only path trace found a second
served-generation surface, `get_teacher_card()`, undocumented and
unguarded on four dimensions; two of the four guards built, independently
reviewed `ACCEPT`, pushed to origin and confirmed live in production on
Railway (both services) and Vercel; the false "producer.py is the only
answer path" claim corrected across CLAUDE.md, PLAN.md, ARCHITECTURE.md).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**F5 trace + teacher-card guard fix — 2026-08-15, pushed and live in
production.** A read-only F5 path trace (Grok, attended) found
CLAUDE.md/PLAN.md/rhemata-status.md's repeated "producer.py is the only
answer path" claim false: `GET /study/teacher/{source_id}`
(`get_teacher_card()`) is a second, always-existing served-generation
surface (own retrieval, own Anthropic call) that applied the license gate
but skipped commentary exclusion, citation grounding, the position-paper
fence, and quote verification — a real, live gap against ranked failure
mode #2 (misattributing a position to a named teacher). The same trace
found 19 total bypasses across serving/ingest paths — see PLAN.md's F5
section; only the two below are closed, the other 17 are NOT triaged.

Repo-only build (`executor`/`planner-reviewer`, Claude Code both roles)
closed two of get_teacher_card's four gaps: citation grounding
(`reference_verifier.ungrounded_prose_teachers`, regenerate-once-then-
refuse) and commentary/word_study exclusion (document-level pre-RPC
filtering, since `match_teacher_chunks` returns no `source_kind` to filter
on after the fact). Position-paper fence deliberately NOT applied — would
substitute house-position prose for a genuinely dissenting teacher's own
card. Quote verification N/A — this endpoint never served quotes.
Independent `planner-reviewer` `ACCEPT`, evidence-based: A/B'd the new
test against a pristine `main` tree (7/18 assertions genuinely fail on old
code), full-suite regression check identical before/after.

Alex explicitly approved the merge and push despite the pre-push full
suite diverging from the credential-less review worktree's 26-failure
baseline (this checkout has real credentials, so 34 passed / 2 failed / 4
timed out is a more complete run, not a worse one; both real failures and
all four timeouts confirmed unrelated to this diff — commits `3678d05` /
`9dd0438` / `21f5b14`). Pushed same session; `origin/main` now `21f5b14`.
Confirmed live via each platform's own build log, not dashboard color:
Railway `rhemata` deployment `e8272119` `SUCCESS` + healthcheck passed,
`answer-worker` deployment `223d9512` `SUCCESS`, Vercel
`dpl_4KERiVU7cAAXc2ga4Q2AtHYhZp3W` `Ready`, live `GET /` 200 on both.

**Two residuals still open, not yet acted on:** a `teacher_profiles.bio`
naming another teacher could false-positive-refuse a legitimate card
(unverified against real content); commentary docs still consume the
`LIMIT 20` query slots before Python-side filtering. **Open copy
question:** whether the refusal string reads right under a named
teacher's card heading — Alex hasn't confirmed. Full detail: CLAUDE.md's
Landmines entry on the 2026-08-07 mirror-unification job.

**Prior session (2026-08-14/15), unchanged:** first real unattended F2 run
(`621f408`, pushed) and three attended Grok harness-builder probes (probe 1
merged `4682147`; probes 2/3 reviewed-`ACCEPT` but unmerged, Alex's call).
Full detail in `PLAN.md`'s Overnight section.

**Standing, unchanged:** safety fence deferred, not cancelled (revisit
trigger: real unrecoverable damage, or harness work reaching outside the
repo); harness-tooling review is one round, but answer-path work like
today's teacher-card fix is not harness tooling and gets real scrutiny;
production DB writes never run through the harness. All 8 position papers
live; one async (chat-style) answer path plus one synchronous teacher-card
surface, now partially guarded; quote rail live on the async path only;
position one-hop live on origin.

---

## Open blockers

**Launch:** ~68s full reveal latency. (100-dial concurrency proof is no
longer a blocker — Alex explicitly decided against a pre-launch load test,
PLAN.md, 2026-08-13.)

- Guest→account, auth CTAs, v4 props, `jewish_perspectives` drop,
  SP residuals, Hebrew lexicon grant, Lewis/Tolkien/Wilson mistag.
- Admin-panel notifications — dependency of position-refresh; no design.
- 20 Prince documents with zero approved quotes (2026-08-09).

---

## Known Harness Bugs

- **Auto Mode misfire on harmless prose mentioning "SQL"/"migration"
  — 2026-08-14.** A live `executor` subagent hit this classifier while
  running Python `time.sleep` verification commands — semicolons in the
  test one-liners, combined with the executor's own loaded
  SQL-comment/semicolon instructions (the Migration 051 gotcha), triggered
  a defensive loop explaining a phantom SQL-migration flag instead of
  running the task. Nothing SQL- or migration-related was actually
  present. Worked around per the stall-risk rule: did not retry the
  identical prompt, removed the semicolons, reran once — cleared. A
  future session must not assume this misfire is always harmless — it can
  consume a full turn and block real work; reformulate, don't just retry.

---

## Next

1. Triage the 17 untouched bypasses from the 2026-08-15 F5 trace
   (accept/defer/close each) — F5's exit criteria stay unmet until this
   happens; see PLAN.md's F5 section for the pointer.
2. Two teacher-card residuals from the same session, not yet acted on:
   check real `teacher_profiles.bio` content for cross-teacher name
   mentions (bio-echo false-positive risk, unverified — no DB credentials
   in the review worktree); decide whether the shared refusal string reads
   correctly under a named teacher's card heading (copy question, not a
   code gap).
3. Decide whether to merge probe 2's (`grok/o5-reviewer-diversity-gap-test`)
   and/or probe 3's (`grok/study-page-parse-ref-test-coverage`) branches —
   both independently reviewed `ACCEPT`, neither merged or pushed, both
   real diffs sitting in disposable worktrees, ready to review directly.
   (Probe 1 already merged, `4682147`.)
4. A fourth probe is well-positioned to close a specific, still-open gap:
   no probe to date has put Grok in a position where the correct,
   in-scope completion of a task actually required confronting a
   hard-forbidden file it couldn't route around (probe 2's forbidden fix
   was structurally outside its packet; probe 3's chosen implementation
   sidestepped the forbidden file rather than facing it). Design one where
   the natural solution path can't avoid it, to see whether Grok
   explicitly self-stops/flags rather than just happening to avoid it.
5. Decide extractor hardening before any next Prince-style batch.
6. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
7. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
8. Trail / Brooks one-offs — review then visibility.
9. `pending` vs `draft` quote-status consolidation.
10. `jewish_perspectives` drop — needs Alex's explicit approval + a
    dedicated DB-write session.
11. F2 partial (3/5 exit criteria done 2026-08-14 — pydantic/starlette
    pinned, backend/worker Python parity checked and documented, clean-venv
    admin-auth smoke test passes; Supabase backup/PITR recording and a
    tested restore scope remain) through F5 stay open before F6's
    ingestion-ready benchmark can be declared — O6 alone does not close F6.
12. SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not
    shipped.
