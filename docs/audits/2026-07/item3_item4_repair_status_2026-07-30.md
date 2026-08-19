# Item 3 / Item 4 repair status — 2026-07-30

**Plain-English summary:** Of the three repairs a prior review said should happen before Item 4, none of them actually happened. The two prompt templates are still mostly duplicated — only one small piece was factored out to be shared, and that happened to be handled carefully this one time, but nothing stops a future change from being added to only one copy and not the other. The specific wording the review flagged as unprovable ("verbatim stated") is still exactly there, unchanged, in the code. And there are no automated tests at all for either the tension-mode behavior or the premise-correction behavior — none exist, so nothing would catch a regression in either one today.

This is a read-only status check. Nothing was changed, fixed, or refactored.

---

## (1) Deduplication of the two prompt templates

**Status: NOT done — one small piece shared, the rest still fully duplicated.**

`scripts/positions.py` has two full prompt templates: `POSITION_PROMPT` (lines 205–220) and `TENSION_MODE_PROMPT` (lines 251–266). Comparing them paragraph by paragraph:

| Paragraph | Shared or duplicated? |
|---|---|
| Opening ("You are writing a stored position...") | Duplicated — identical text typed twice |
| "You will be given the teacher's name..." | Duplicated — identical text typed twice |
| FOUR CORNERS governing rule | Duplicated — identical text typed twice |
| Premise-correction clause | **Shared** — both templates insert the same `PREMISE_CORRECTION_CLAUSE` constant via an f-string reference, so this one paragraph genuinely has a single source of truth |
| "Write ONE position..." (the resolution instruction) | Intentionally different between the two — this is the one sentence that's supposed to vary, and it does correctly |
| Paraphrase instruction | Duplicated — identical text typed twice |
| Single-teacher-only hedge | Duplicated — identical text typed twice |
| Closing "no preamble" line | Duplicated — identical text typed twice |

So 4 of the 5 paragraphs that are supposed to be identical between the two modes are typed out twice, as two separate literal blocks of text, not built from one shared source. Only the premise-correction paragraph was actually pulled out into its own single, reusable piece.

**What this means concretely:** the exact risk the original review was worried about — a future instruction getting added to one template but silently missed in the other — still exists. It didn't cause a problem this time only because whoever added the premise-correction paragraph was careful to add it to both templates by hand and used a shared reference for that one piece specifically. There is nothing in the code structure that would force or guarantee the same care next time.

## (2) Wording change: "verbatim stated" → "explicitly states"

**Status: NOT done — the exact original wording is still there.**

`scripts/positions.py` line 260 (inside `TENSION_MODE_PROMPT`) still reads:

> "...without resolving it into a side the teacher didn't take — unless the teacher has verbatim stated an explicit position, in which case state that position."

This is character-for-character the same phrasing the review flagged as a problem — the concern being that the system only ever sees already-paraphrased summaries of what a teacher said, never the teacher's exact original words, so asking it to confirm something was stated "verbatim" isn't a question it can actually answer honestly. A nearby code comment (line 250) uses the same word ("genuinely, verbatim, taken an explicit position"). Neither has been touched.

## (3) Regression tests for Item 3 (tension mode) and Item 4 (premise-correction)

**Status: NOT done — no tests exist for either.**

There is no test file anywhere in the repository for `scripts/positions.py` or `scripts/generate_teacher_positions.py` — confirmed by searching the whole repo for any file with "position" in the name, and separately by checking every commit that has ever touched either of those two files (only four commits total: the original foundation build, a threshold adjustment, the tension-mode commit, and the premise-correction commit — none of the four adds or touches a test file).

Several test files do exist for a *different* part of the codebase (citation/reference-checking and the propositions pipeline) — `test_citation_verifier_layers.py`, `test_propositions_closeness_gate.py`, `test_propositions_reference_grounding.py`, `test_reference_grounding_unit_proof.py`, `test_reference_verifier.py`, `test_rewrite_flagged_statement.py`, `test_closeness_check_unit_proof.py` — but none of them reference tension mode, premise-correction, Calvinism, or predestination in any way. They cover a genuinely separate feature.

There is no automated check that would catch a future change accidentally breaking: which topics trigger tension mode, whether the two templates still match on their shared portions, whether the premise-correction paragraph still reaches both templates, or what version/fingerprint gets stored on a written row.

---

## Technical detail for reference

- File checked: `/Users/alexwhitley/rhemata/scripts/positions.py` (506 lines, current HEAD, commit `94b1ee7` is the last one to touch it).
- `POSITION_PROMPT`: lines 205–220. `TENSION_MODE_PROMPT`: lines 251–266. `PREMISE_CORRECTION_CLAUSE`: lines 196–202, referenced by both templates via f-string substitution at lines 212 and 258.
- `is_calvinism_predestination_topic()`: lines 269–281. `_prompt_and_version_for_topic()`: lines 284–292 — the single function that decides both which prompt is sent and which version/fingerprint is stamped, so generation and provenance can't disagree (this part is genuinely a single source of truth, separate from the template-duplication issue above).
- "verbatim" occurrences in the file: line 216 (unrelated — "do not quote the statements verbatim at length," a paraphrase-discipline instruction, not the tension-mode exception), line 250 (a code comment), line 260 (the tension-mode prompt text itself — the one the review flagged).
- Test search method: `find` for any filename containing "position" (repo-wide, excluding `node_modules`/`.git`); grep of every existing `test_*.py` file under `scripts/` for "positions", "tension", "premise", "Calvinism", "predestination" (all matches were confirmed false positives — either the unrelated `propositions` module/table name, or literal string-index fields named "positions" in `test_reference_verifier.py`); and `git log --oneline --all` scoped to `scripts/positions.py`, `scripts/generate_teacher_positions.py`, and `scripts/position_content_verifier.py`, which returned exactly four commits (`5d6b428`, `b9e20b8`, `b9f9a45`, `94b1ee7`), none of which touches any test file.
