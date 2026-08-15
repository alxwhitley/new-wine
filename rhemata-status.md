# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(roadmap / decisions / findings), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-15 (F5 read-only path trace found a second
served-generation surface, `get_teacher_card()`, undocumented and
unguarded on four dimensions; two of the four guards built, independently
reviewed `ACCEPT`, merged to local `main` only — not pushed; the false
"producer.py is the only answer path" claim corrected across CLAUDE.md,
PLAN.md, ARCHITECTURE.md).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**F5 trace + teacher-card guard fix — 2026-08-15, merged to local `main`
only, NOT pushed.** A read-only F5 path trace (Grok, attended) found
CLAUDE.md/PLAN.md/rhemata-status.md's repeated "producer.py is the only
answer path" claim false: `GET /study/teacher/{source_id}`
(`get_teacher_card()`) is a second, always-existing served-generation
surface (own retrieval, own Anthropic call) that applied the license gate
but skipped commentary exclusion, citation grounding, the position-paper
fence, and quote verification — a real, live gap against ranked failure
mode #2 (misattributing a position to a named teacher). Repo-only build
(`executor`/`planner-reviewer`, Claude Code both roles) closed two of the
four same session: citation grounding
(`reference_verifier.ungrounded_prose_teachers`, regenerate-once-then-
refuse) and commentary/word_study exclusion (document-level pre-RPC
filtering, since `match_teacher_chunks` returns no `source_kind` to filter
on after the fact). Position-paper fence deliberately NOT applied —
would substitute house-position prose for a genuinely dissenting teacher's
own card. Quote verification N/A — this endpoint never served quotes.
Independent `planner-reviewer` `ACCEPT`, evidence-based: A/B'd the new
test against a pristine `main` tree (7/18 assertions genuinely fail on old
code), full-suite regression check identical before/after. Build `3678d05`,
merge `9dd0438`. Two residuals flagged, not yet acted on: a
`teacher_profiles.bio` naming another teacher could false-positive-refuse
a legitimate card; commentary docs still consume the `LIMIT 20` query
slots before Python-side filtering. One open copy question: whether the
shared refusal string reads correctly under a named teacher's card
heading. **Alex reviews the two judgment calls (position-paper fence
omitted; citation grounding uses only the prose-scan arm, not the
declared-block arm) and the residuals before this goes further — not
pushed, not deployed.** Full detail: CLAUDE.md's Landmines entry on the
2026-08-07 mirror-unification job (corrected in place, same session).

**Prior session (2026-08-14/15), unchanged:** first real, non-rehearsal
Claude-Code-only unattended run — two F2 packets (`pydantic`/`starlette`
pin, backend/worker nixpacks Python-version parity), both `REVISE`→fix→
`ACCEPT`, merged and pushed to origin (`621f408`). Three attended Grok
harness-builder probes also ran 2026-08-14, all independently reviewed
`ACCEPT`; probe 1 merged (`4682147`), probes 2/3 remain reviewed-but-
unmerged, Alex's call. Full detail in `PLAN.md`'s Overnight section.

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

1. Review and, if approved, push the teacher-card guard fix (local `main`
   only as of 2026-08-15) — the two judgment calls (position-paper fence
   omitted; citation grounding uses only the prose-scan arm) and the two
   flagged residuals (bio-echo false-positive risk; `LIMIT 20` slot
   consumption by commentary docs), plus the refusal-copy placement
   question.
2. Decide whether to merge probe 2's (`grok/o5-reviewer-diversity-gap-test`)
   and/or probe 3's (`grok/study-page-parse-ref-test-coverage`) branches —
   both independently reviewed `ACCEPT`, neither merged or pushed, both
   real diffs sitting in disposable worktrees, ready to review directly.
   (Probe 1 already merged, `4682147`.)
3. A fourth probe is well-positioned to close a specific, still-open gap:
   no probe to date has put Grok in a position where the correct,
   in-scope completion of a task actually required confronting a
   hard-forbidden file it couldn't route around (probe 2's forbidden fix
   was structurally outside its packet; probe 3's chosen implementation
   sidestepped the forbidden file rather than facing it). Design one where
   the natural solution path can't avoid it, to see whether Grok
   explicitly self-stops/flags rather than just happening to avoid it.
4. Decide extractor hardening before any next Prince-style batch.
5. Decide whether the 20 zero-coverage Prince documents warrant a
   targeted re-extraction.
6. Human review of chapter-boundary proposals (18 books) — Open
   Decision #21.
7. Trail / Brooks one-offs — review then visibility.
8. `pending` vs `draft` quote-status consolidation.
9. `jewish_perspectives` drop — needs Alex's explicit approval + a
   dedicated DB-write session.
10. F2 partial (3/5 exit criteria done 2026-08-14 — pydantic/starlette
    pinned, backend/worker Python parity checked and documented, clean-venv
    admin-auth smoke test passes; Supabase backup/PITR recording and a
    tested restore scope remain) through F5 stay open before F6's
    ingestion-ready benchmark can be declared — O6 alone does not close F6.
11. SP: #43 swipe-to-close shipped; full drag-to-follow-with-peek not
    shipped.
