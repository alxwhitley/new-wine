# Reference-grounding fix: does it drop genuine scripture references? — dry-run audit

**Date:** 2026-07-28
**Session type:** Read-only diagnostic. Zero database writes. 20 real Groq extraction calls made for dry-run comparison only — nothing generated in this session was stored to the database or to the real (gitignored) review log.
**Author:** Claude Code, proposing findings for Alex's decision. Nothing in this report has been applied to CLAUDE.md, PLAN.md, or rhemata-status.md.

---

## TL;DR

- **This is a backfill-only risk, not a live corpus defect.** No proposition currently in the database was written under the changed code — see Step 1.
- **The premise needs a correction: there is no "old prompt vs. new prompt."** The extraction prompt never changed. The fix is a deterministic, post-generation filter. See "A correction to the framing" below.
- **The dry run (20 real documents, 215 references found in raw model output) found the filter drops far more genuine references than it catches fabrications.** Of the 39 references it stripped, direct reading of the source confirmed **33 (85%) were genuinely given by the teacher and wrongly dropped**, **3 (8%) were correctly removed** (the model appears to have added a citation the source didn't give), and **3 (8%) were genuinely ambiguous**.
- **The filter, as wired today, structurally cannot detect a confirmed fabrication at all** — it can only ever output GROUNDED or UNCERTAIN in production, never UNGROUNDED (explained below). Every miss and every genuine catch look identical to it.
- **Recommendation: do not run the backfill against the current wiring.** See Step 5.

---

## A correction to the framing this session started from

The session brief (and the standing narrative in `rhemata-status.md`) frames this as "generation instructions were changed... if that change made generation over-cautious." Reading the actual commit (`93d59a5`, 2026-07-28) shows that framing needs a correction before anything else:

**The extraction prompt (`EXTRACTION_PROMPT` / `EXTRACTION_PROMPT_V4` in `scripts/propositions.py`) has not changed.** Both prompt versions have told the model "capture every [reference] the source gives, invent none it doesn't... do NOT supply the reference, even if you recognize the verse" since their first commit. This is confirmed both by `rhemata-status.md`'s own prior finding ("not a prompt gap... the Groq extraction call sometimes violates it anyway") and by direct inspection of `git log -- scripts/propositions.py`.

**What actually shipped is a deterministic, code-level post-processing filter**, `_apply_reference_grounding()`, that runs unconditionally after every `extract_propositions()` call, regardless of prompt version. It:

1. Finds every scripture-reference-shaped substring in the model's raw output (`reference_grounding.find_reference_spans()` — requires colon form, e.g. `Book N:M`).
2. For each one, checks whether an equivalent citation exists in the source text (same colon-form scanner, run against `text`).
3. If no exact match is found, strips only that reference substring from the proposition's content. Everything else survives untouched.

There is no second prompt to compare against. So "run generation once under current instructions, once under prior wording" (the brief's Step 3 design) doesn't apply as specified — there's only one prompt. **The correct dry-run comparison is: one real Groq call, then compare its raw output to what the deterministic filter does to that same output.** That's what this audit ran.

---

## Step 1 — Is this live or pre-emptive? Live query, plain fact

```
SELECT prompt_version, prompt_fingerprint, model, count(*), min(created_at), max(created_at)
FROM propositions GROUP BY prompt_version, prompt_fingerprint, model;
```
Result: **one row.** `('legacy_unknown', NULL, NULL, 2409, 2026-06-25 22:07:50 UTC, 2026-07-23 22:15:03 UTC)`.

Two independent facts close this question without needing fingerprint comparison at all:

1. Every one of the 2,409 live propositions is `prompt_version='legacy_unknown'`, NULL fingerprint, NULL model — already known from prior sessions, reconfirmed here.
2. **`max(created_at)` across the entire table is 2026-07-23 22:15 UTC** — before generation even stopped (2026-07-25), and **five days before the reference-grounding fix landed** (commit `93d59a5`, 2026-07-28 16:47 UTC).

No live row could possibly have been written under the changed code, full stop. **This is a backfill-only risk.** Step 2 (before/after density comparison by fingerprint) is therefore moot — not because provenance is missing, but because there is nothing to compare: no row was ever written under the new code, and (per the correction above) there was never a second prompt version to begin with.

---

## Step 3 — Dry-run design and execution

**Selection (20 documents, verified by reading, not assumed):** weighted toward Derek Prince (10 of 20 — largest expository block, confirmed in `rhemata-status.md`), plus Vlad Savchuk (3), Zac Poonen (3), Leonard Ravenhill (2), Doug Kreighbaum (1), Jack Deere (1). Candidates were ranked by a rough regex scan for reference density in `chunks.content`, then spot-verified by reading actual source excerpts before inclusion — confirmed genuine, dense, verified scripture citation in every sampled document (both colon-form outline style, e.g. Prince's "Deliverance And Demonology," and heavy spoken-form style, e.g. "Romans chapter three and verse 20," "Hebrews chapter 10").

**Harness:** one real Groq call per document via the actual `scripts/propositions.py::extract_propositions()` (model `llama-3.3-70b-versatile`, same as production), with `_apply_reference_grounding()` wrapped (not replaced) to capture both its input (raw model output) and output (post-strip) from the same real call. `_write_grounding_review_records()` was monkeypatched to a no-op so this diagnostic left no trace in the real gitignored review log. Nothing was written to the database. All 20 calls succeeded on the first attempt.

**Result, aggregated:**

| | count |
|---|---|
| References found in raw model output | 215 |
| GROUNDED (citation-string match found in source) | 176 |
| UNGROUNDED (confirmed absent) | **0** |
| UNCERTAIN (not found by the one check that ran) | 39 |
| Stripped (UNGROUNDED + UNCERTAIN) | 39 |

**Zero UNGROUNDED verdicts occurred across all 215 references.** This is not a sampling accident — it's structural, and it's the single most important mechanical finding of this audit (see next section).

**Strip rate varies enormously by source style**, and the pattern is exactly what the prior spoken-form survey (`rhemata-status.md`, 2026-07-28) predicted:

| Teacher / document | refs found | stripped | rate |
|---|---:|---:|---:|
| Prince, "Deliverance And Demonology" (outline, colon-cited) | 18 | 0 | 0.0% |
| Prince, "The Rebellion Of Lucifer" | 5 | 0 | 0.0% |
| Prince, "The Cross Canceled Satan's Claims" | 7 | 0 | 0.0% |
| Kreighbaum, "The Holy Spirit" (outline, colon-cited) | 42 | 1 | 2.4% |
| Prince, "Use And Abuse Of The Tongue" | 20 | 1 | 5.0% |
| Prince, "Israel In The End Times" | 13 | 1 | 7.7% |
| Prince, "God's Purpose For The New Race" | 15 | 2 | 13.3% |
| Prince, "The Conditions" | 4 | 1 | 25.0% |
| Savchuk, "Fall Asleep in God's Presence" | 20 | 5 | 25.0% |
| Poonen, "Holy Spirit Shows Us How Jesus Lived" | 4 | 1 | 25.0% |
| Poonen, "Great Mystery of the Church" | 8 | 3 | 37.5% |
| Prince, "Why The Law?" (heavy spoken-form) | 23 | 10 | **43.5%** |
| Ravenhill, "Are We Longing for Repentance" | 3 | 1 | 33.3% |
| Ravenhill, "A Burning Heart" | 2 | 1 | 50.0% |
| Savchuk, "The Rapture Won't Happen" | 5 | 3 | **60.0%** |
| Poonen, "Eight Valuable Truths" (heavy spoken-form) | 12 | 8 | **66.7%** |

Written-outline-style documents (Prince's and Kreighbaum's citation-outline material) lose almost nothing. Sustained spoken-form expository sermons — exactly the style the backfill is weighted toward (Derek Prince, 429+ documents) — lose 25–67% of the references the model correctly extracted.

---

## Why zero UNGROUNDED verdicts is the real finding

`reference_grounding.check_reference_grounded()` has two independent arms:

1. **Citation-string arm** (always runs): scans `source_text` for a colon-form reference with the same parsed (book, chapter, verse) value. If found → GROUNDED.
2. **Wording arm** (only runs if the caller supplies `verse_lookup`, a live WEB-verse lookup table): searches for the verse's actual wording in `source_text`, independent of any citation string. Can catch a teacher who quotes a verse without ever naming it.

**`extract_propositions()` never supplies `verse_lookup`** — confirmed directly in the code and its own docstring ("`extract_propositions()` has no DB connection of its own to build one"). So in the live-wired production path, **the wording arm can never run.** The only two possible outcomes at this call site are GROUNDED or UNCERTAIN. UNGROUNDED — "checked both arms, confirmed absent" — is architecturally unreachable here.

This matters because the corpus-wide 72-reference figure that motivated this whole fix (`scripts/detect_reference_fabrication.py`) **does** supply `verse_lookup` and runs both arms. **The tool used to scope the problem is strictly more capable than the fix that was wired to solve it.** In production, the fix cannot distinguish "the model invented this" from "the model correctly identified something the source says in a form the citation-string scanner doesn't recognize, or in a different verse-range granularity than the source used." Both collapse to the same UNCERTAIN → strip outcome.

Two distinct failure modes were confirmed by this audit, both invisible to the current wiring:

- **Spoken-form blind spot** (already known, e.g. `citation_verifier_layers.py`'s documented Pattern-A gap) — the dominant cause. "Romans chapter three and verse 20" in source, model correctly writes "Romans 3:20," citation-string scanner finds nothing colon-shaped in source to match against.
- **Granularity/format mismatch — not previously documented for this call site.** Even when *both* source and model use colon form, an exact-tuple match is required. Source cites `Acts 2:4` and `Acts 2:2,3` separately; model correctly merges them into `Acts 2:2-4`; no single source citation has that exact (start, end) pair, so it strips. Same pattern with `Colossians 1:15–18` (source) vs. `Colossians 1:18` (model, citing the specific verse whose content it's summarizing) and `2Corinthians 5:17` "read through verse 20" (source) vs. `2 Corinthians 5:17-20` (model). This is a second, independent hole in the same mechanism, not a restatement of the spoken-form gap.

---

## Step 4 — Reading the 39 stripped references

Every reference present in the raw model output but absent from the filtered output was read against its actual source document (not an excerpt) and classified:

| Bucket | Count | % |
|---|---:|---:|
| (a) Teacher genuinely gave it — wrongly dropped | 33 | 85% |
| (b) Teacher never gave it — correctly removed | 3 | 8% |
| (c) Genuinely ambiguous | 3 | 8% |

**Bucket (a) — representative examples (spoken-form and format-granularity, both root causes):**
- Prince, "Why The Law?": *"Turn to Ephesians chapter 2, beginning at verse 14. We have to read verses 14, 15 and 16"* → model wrote `Ephesians 2:14-16`, stripped. All 10 of this document's 10 stripped references verified genuine on direct reading — a 100% false-positive rate for this single document.
- Poonen, "Eight Valuable Truths": *"Turn to Acts of the Apostles, chapter 7... verse 23... after another 40 years, verse 30, now Moses is 80 years old"* → model wrote `Acts 7:23-30` (both endpoints independently confirmed in source), stripped.
- Savchuk, "The Rapture Won't Happen": *"1 Corinthians 15 51 and 52 Paul says behold I tell you a mystery"* → model wrote `1 Corinthians 15:51-52`, stripped.
- Kreighbaum, "The Holy Spirit": source cites `Acts 2:4` and `Acts 2:2,3` separately (both present); model correctly merged to `Acts 2:2-4`; stripped for exact-tuple mismatch, not for being wrong.
- Ravenhill, "Are We Longing for Repentance": the KJV text of John 7:37 is quoted **verbatim** in full ("Jesus stood and cried with a loud voice, saying, 'If any man thirst, let him come unto me and drink'"), but the transcript's own spoken verse-number citation reads "verse 7" (very likely a dropped digit for "verse 37," a source-transcription artifact, not a model error) — the model's citation is correct; the source's own citation string is broken. This is exactly the case the wording arm exists to rescue, and exactly the case that never gets a chance to run.

**Bucket (b) — the 3 confirmed correct removals, examined carefully, not just counted:**
- Poonen, "Eight Valuable Truths," `Matthew 5:27-30`: source discusses "lusting with the eyes is as bad as adultery" purely thematically, with no chapter:verse or even the word "Matthew" anywhere near that passage. Looks like the model supplied a citation from its own general Bible knowledge.
- Prince, "The Conditions," `2 Corinthians 9:6-7`: source's actual two verses for this exact point ("faith is exercised in giving before receiving") are explicitly named as `2Corinthians 8:9` and `9:8` — different verses from what the model cited. A real mismatch, not a format issue.
- Savchuk, "Fall Asleep in God's Presence," `Psalm 55:22`: no occurrence of Psalm 55, "cast," or "burden" language anywhere in the source; the adjacent (and genuinely grounded) `1 Peter 5:7` covers near-identical content, suggesting the model added a well-known parallel reference the source never gave.

**Bucket (c) — genuinely ambiguous, reported separately per the brief's instruction, not forced:**
- Prince, "Israel In The End Times," `Matthew 25:31-46`: source explicitly quotes `Matthew 25:31` and says "in Matthew 25, the last section of that great chapter" (which does end at v46) — but never cites verses 32–46 explicitly; Prince narrates the sheep/goats content in his own words after v31.
- Poonen, "Eight Valuable Truths," `John 7:38-39`: source explicitly cites and quotes `John 7:38` ("rivers of living water will flow from you"); verse 39 is never independently cited or quoted in the visible text, though it is the standard companion verse.
- Ravenhill, "A Burning Heart," `Joel 2:12-17`: `Joel 2:12` is quoted verbatim with citation; `Joel 2:13`'s exact wording ("Rend your hearts, and not your garments") follows immediately afterward as running narration; verses 14–17 are not shown as quoted or cited anywhere in the source.

---

## Step 5 — Is the trade-off worth it?

**No, not as currently wired.** Three things point the same direction:

1. **The false-positive rate is extreme.** 33 wrongly-dropped references for every 3 confirmed-correct removals — an 11:1 ratio in this sample. For sustained expository preaching (the backfill's dominant material), the loss rate reaches 25–67% of genuine references per document.
2. **Genuine fabrication already looks rare.** Per the standing context this session started from, exactly one case has ever been confirmed by direct full-source reading (the Ravenhill Philippians 4:8-9 case), and every larger fabrication count since has turned out to be measurement error. This audit adds to that picture: 0 of 215 references in a fresh, independent 20-document sample resolved to a confirmed fabrication (UNGROUNDED) — though see the structural caveat above, since UNGROUNDED can't fire at this call site regardless of the true rate.
3. **The mechanism can't currently tell the difference anyway.** Because the wording arm never runs and the citation-string arm requires exact-tuple colon-form matches, "correctly caught a fabrication" and "wrongly dropped a genuine spoken-form or reformatted reference" produce the identical UNCERTAIN → strip outcome. There is no confidence signal to lean on even if you wanted to accept some false positives for the catches.

**If the backfill runs against the current wiring unchanged, expect roughly a quarter to two-thirds of genuine scripture references to silently vanish from freshly-generated statements on Derek Prince's material specifically** — the teacher supplying the largest single block of the backfill and the one whose preaching style (book named once, verses cited afterward) is most exposed to this gap.

## What would need to change before the backfill (proposed, not implemented)

Not prescribing a fix — flagging what the evidence points to, for Alex's call:

- **Supply `verse_lookup` to `check_reference_grounded()` inside `extract_propositions()`.** This is the single highest-leverage change: it activates the wording arm, which would have independently rescued the verbatim-quote case (Ravenhill/John 7:37) and likely several of the spoken-form cases whose content matches WEB wording closely enough. This does cost a DB round-trip inside a function that currently has none — an architectural change, not a one-line fix.
- **Extend the citation-string arm to recognize spoken forms** — this is already-known, already-scoped work (`citation_verifier_layers.py`'s Layer 1, and its own documented Pattern-A gap: "Hebrews chapter 10:25" with no literal "verse" token still fails even there). That work is deliberately parked pending this session's outcome; this audit's evidence argues for prioritizing it.
- **Consider overlap/subset matching instead of exact-tuple matching** for the citation-string arm, so a model-merged range (`Acts 2:2-4`) credits against source citations that jointly cover the same verses (`Acts 2:4` + `Acts 2:2,3`), rather than requiring byte-identical boundaries.

## Scope and limitations of this audit, disclosed

- 20 documents, 215 references — a real sample, not the whole corpus. Concentrated on already reference-dense documents by design (per the brief's instruction to weight toward verse-heavy material); strip rates on sparser documents are unmeasured and could differ.
- Bucket (a)/(b)/(c) classification was done by direct reading of full reconstructed source text for every one of the 39 stripped references, not by sampling — but reading judgment is still judgment; the 3 ambiguous cases are reported as such rather than forced, and Alex may read any of the 33 "(a)" cases differently.
- This audit did not re-examine whether the 3 bucket-(b) removals reflect a real prompt-obedience failure worth investigating on its own (why did the model attach `Matthew 5:27-30` to an uncited thematic discussion?) — flagged, not chased, consistent with this session's read-only/measure-only scope.
- Raw dry-run data (all 20 documents' pre/post-strip propositions, the full 215-reference classification, and the 39-reference source-context readings) is held in this session's scratch directory only, not committed — available on request if a future session wants to re-derive or extend this analysis without re-running the Groq calls.
