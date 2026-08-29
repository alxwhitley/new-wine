# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-29. **PLAN.md has zero active blockers.** The
2026-08-27→29 back-to-back completion queue closed earlier this session
(Packet 6, commit `9fcbdc2`). Everything below is this session's separate New
Wine A2 work — no production code changed; three documents written, two of
them refuted before Alex saw them; real evidence gathered on model choice.

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

**New Wine A2 remains NOT ingestion-ready.** This session tried two more
segmentation-redesign proposals, refuted both, then pivoted to a question
that had never actually been tested: whether the MODEL, not the
architecture, was the real lever.

1. **Chunked-segmentation design — refuted the same day it was proposed**
   (`15f6b1d` → refuted `4f96a09`,
   `docs/superpowers/specs/2026-08-29-new-wine-chunked-segmentation-design.md`).
   Its own stated premise (positional grounding degrades late in a long
   transcript) was directly falsified by measurement: every boundary in the
   back 40% of the transcript sat within 31 chars of a real page marker.
2. **ToC-anchored segmentation design — refuted the same day, before Alex
   saw it** (`docs/superpowers/specs/2026-08-29-new-wine-toc-anchored-segmentation-v2.md`,
   commit `44e726d`; adversarially reviewed proactively this time, not on
   request). Real defects, independently reverified: a `[VERIFIED]`-tagged
   claim was false (Issue 02-1980 does have a ToC, a 7th distinct format);
   the proposed article-end marker (a `☐` glyph) is also a literal
   subscription-form checkbox in the same issue; the discontiguous-span
   schema had no algorithm that would ever populate more than one span; it
   contradicted an already-shipped instruction (`d011fac`) for Forum-style
   columns. Third confidently-written design refuted in one session —
   recorded plainly, not smoothed over.
3. **Model choice was never actually benchmarked for this task — only
   discovered this session.** `openai/gpt-oss-120b` was a forced
   substitution when Groq retired the prior default model, never evaluated
   against alternatives, unlike OCR (which got a real blind benchmark
   before a model was picked, `docs/audits/2026-08/new_wine_ocr_benchmark_2026-08-25/`).
   A live comparison call today (Claude Opus 5, direct Anthropic API, same
   cached transcript, same schema, same deterministic validation) produced
   the **first clean deterministic pass on Issue 02-1973 recorded across
   the whole A2 effort** — zero article-span overlaps, correctly split "The
   Apostle" into two discontiguous parts around a real interruption,
   correctly attributed "Keeping the Unity" to its real reprint source,
   used an honest collective label for the Forum's multi-speaker panel
   instead of fabricating a single person as author. One run only — not
   proof of reliability, same caveat that already applies to gpt-oss-120b's
   own occasional clean passes on this same transcript.
4. **The comparison overran its approved budget — a process mistake, not a
   product finding.** Alex approved $1 for this test. Confirmed spend:
   **$1.4776** for the one successful call, plus an unmeasured ~$1 estimate
   from an earlier attempt that hit `max_tokens` before emitting any text
   block (the test harness's own error handling didn't capture usage on
   that failure path — a real gap, not just an estimate problem). Cause:
   iterated through genuine SDK/schema debugging (a streaming requirement,
   an unsupported JSON Schema keyword, a strict envelope key mismatch)
   against the full 121K-char real transcript instead of a trivial dummy
   request first. Recorded as a new CLAUDE.md landmine.
5. **A summary was handed to Alex in-chat (not saved as a file) to get a
   second opinion from Grok on model choice.** Not yet acted on.

**Quote rail:** still off (`QUOTE_SELECTION_ENABLED=false`), unchanged.

---

## Findings surfaced, not yet acted on

- **Scheduled**: quote accuracy/relevance repair before any attended
  re-enable.
- **Live account-deletion verification** — genuinely blocked, needs Alex to
  create a real disposable test account first (Session Routing hard rule).
- **Analytics production smoke sequence** — deferred, Alex's explicit
  decision, not run.
- Carried, not re-checked this session: `scripts/test_metering.py` writes
  live to production despite the `test_*.py` naming (self-cleans, verified
  zero residual); staging source name still reads `"Vlad Savchuk (web
  staging)"`; Bonnke URL suspect; `rhemata_readonly_analysis` has no grant
  on PII/user tables.

---

## Next single item

**New Wine A2 model choice — waiting on Alex's decision, not a code task
yet.** Alex is getting a second opinion from Grok using this session's
summary before deciding how to proceed. **Do NOT spend more live-call
budget on a model comparison without Alex's explicit renewed approval** —
this session's $1 ceiling was already overrun by roughly 2.5x. If Alex
approves continuing: a second Claude Opus 5 run would confirm or contradict
today's single clean pass before anything gets written up as a real design.
If Alex picks a different model or a different direction entirely, that
supersedes this.
