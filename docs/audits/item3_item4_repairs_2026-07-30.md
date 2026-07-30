# Item 3 / Item 4 repairs — build session, 2026-07-30

**Plain-English summary:** All three outstanding repairs are done, verified, and committed. The two prompt templates that used to be typed out twice now share one common source of text, so a future change only has to be made in one place instead of two. The wording that told the system to check for a "verbatim" statement — something it could never actually verify, since it never sees a teacher's exact original words — has been changed to something it can honestly check. New automated tests now exist for both behaviors, where none existed before. One honest caveat: testing on real data showed the wording fix, while worth making, does not by itself change the risky over-confident-answer behavior on the Calvinism/predestination case — that remains a separate, already-known open problem, not something this session was meant to solve.

This was a contained build session — no database writes, two small commits.

---

## Repair 1 — deduplicate the prompt templates

**Status: DONE, commit `d023a69`.**

Both prompt templates (`POSITION_PROMPT` for ordinary topics, `TENSION_MODE_PROMPT` for the narrow Calvinism/predestination carve-out) are now built from one shared base template (`BASE_TEMPLATE` in `scripts/positions.py`), with two fill-in points: the shared premise-correction paragraph, and the one paragraph that's supposed to differ between the two modes. Every other paragraph that's supposed to be identical between the two prompts now lives in exactly one place.

Verified to introduce zero behavior change: the ordinary-mode prompt was compared, byte for byte, against its exact pre-refactor version (via a cryptographic fingerprint, not just a visual read) and came back identical.

## Repair 2 — fix the "verbatim stated" wording

**Status: DONE, commit `d023a69`.**

Changed from "unless the teacher has verbatim stated an explicit position" to "unless the statements themselves explicitly state a position." The old wording asked the system to confirm something it structurally cannot check, since it only ever sees already-paraphrased summaries, never a teacher's original wording. The new wording matches what the system can actually verify. The internal version label for this mode was bumped (v2 → v3) so any position written under the old wording can always be told apart from one written under the new wording.

**Real-data check, as required — not assumed safe:** ran the actual generation step three times under the old wording and three times under the new wording, against the same real evidence (Derek Prince's predestination material — the exact case that originally exposed this problem). Result: the confidently-resolved-sounding answer showed up 2 out of 3 times under BOTH the old and the new wording. In plain terms — this specific wording change does not appear to change whether the system over-confidently resolves a doctrinal tension on this real case. It's still worth shipping, because the old instruction was never honestly checkable in the first place, but it is not, by itself, a fix for the over-confidence problem. That problem is tracked separately (PLAN.md Open Decision #20) and remains open.

## Repair 3 — add regression tests

**Status: DONE, commit `d0f2404`, new file `scripts/test_positions.py`.**

Two kinds of tests were added:
- Fast, free checks that run instantly and would catch: the Calvinism/predestination detection breaking, the wrong prompt being selected, a future edit accidentally landing in only one of the two templates instead of the shared source, or the old "verbatim" wording quietly creeping back in.
- Two live checks that actually call the real AI system with real evidence, to catch a regression in actual generated behavior (not just in the underlying text) — one for the tension-mode case, one for the premise-correction case (the "is fasting for weight loss good" example). These are disclosed as imperfect: because real AI output varies run to run, these two checks could occasionally flag a genuinely correct answer as a false alarm, and that's noted directly in the test file itself rather than hidden.

Both fast and slow tests were proven to actually catch a real problem before being trusted: each was deliberately run once against broken/reverted code to confirm it fails, and once against the fixed code to confirm it passes.

---

## Outstanding, not done in this session

**PLAN.md's own written record of Item 4 (line ~382) is now out of date** — it still describes the old mechanism ("f-string substitution") and the old version label ("v2"). Per this project's standing rule, code changes and their written record shouldn't drift apart, but updating PLAN.md is treated as its own small, separate documentation session in this project (a deliberate process rule, not an oversight) rather than something folded into a code-build session. This needs a short follow-up to bring the written record in line with what actually shipped.

---

## Technical detail for reference

- Commits: `d023a69` (dedup refactor + wording fix + version bump, combined into one commit because splitting them would have required fragile line-by-line surgery on intertwined documentation text inside the file — reviewed and endorsed as an acceptable fallback before committing) and `d0f2404` (new test file only).
- `scripts/positions.py`: `BASE_TEMPLATE` (shared template, `.format()`-style, not an f-string, since it needs to be filled in twice), `RESOLUTION_INSTRUCTION_ORDINARY` / `RESOLUTION_INSTRUCTION_TENSION` (the one paragraph that differs per mode), `TENSION_MODE_PROMPT_VERSION = "position_tension_v3"`, `PROMPT_VERSION` unchanged at `"position_v2"`.
- Byte-identity proof (independently reproduced, not just taken on report): `POSITION_PROMPT` SHA-256 before and after the refactor is `af692e4a21fbf1f1d72a7bd38212c632a5ad5dbe00769ec9ac850ff45f39c97d` on both sides. `TENSION_MODE_PROMPT`'s diff against its pre-fix version is exactly one line: the intended phrase change, nothing else.
- Real-data comparison used the real 10-proposition evidence set for `position_calibration_review/batch_results.json`'s `num: 7` entry (Derek Prince, "predestination and unconditional election in the Calvinist sense"), fetched read-only.
- `scripts/test_positions.py`: Tier A (deterministic — topic matcher, prompt/version selector, shared-paragraph identity, wording-fix regression) and Tier B (2 live Anthropic API calls per test run, real small cost — total across the whole build session, roughly 21 live calls, on the order of $0.15–$0.25). Tier B assertions were each revised once during development after a genuine false-failure on correct model output — documented in the test file's own docstrings.
- Zero DB writes anywhere in this session; the only DB activity was read-only `SELECT`s fetching real evidence for the comparison and tests.
- Reviewed by planner-reviewer before commit — verdict: APPROVE, with the PLAN.md staleness noted above as the one non-blocking follow-up.
- Left untouched, as in every prior session: the other in-progress session's pending section in `rhemata-status.md`, and the two frontend commentary files (`commentary-accordion-row.tsx`, `format-commentary-content.tsx`).
