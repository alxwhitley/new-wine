# Layer 3 citation-verifier live run — 2026-07-29

Read-only diagnostic per CLAUDE.md's Session Routing table (zero DB writes anywhere in this session — every DB touch is a SELECT). The only writes are this file, a `rhemata-status.md` / `PLAN.md` records update, `.gitignore`, and a local gitignored review file. Session spend ceiling: $5.00 (Alex, pre-authorised). Actual spend: **~$0.44**.

---

## Phase 1 — ground truth on the mechanism

**Call site / entry point:** `scripts/citation_verifier_layers.py::call_layer3_llm(reference, source_text) -> bool`, reached from `verify_reference_grounded(reference, source_text, llm_enabled=True)` only when Layers 1 and 2 both fail to confirm.

**Model / parameters:** `llama-3.3-70b-versatile` via Groq (`pw.EXTRACTION_MODEL`, `pw._get_groq()` — reused, lazy client, no new construction). `temperature=0.0`, `max_tokens=200`.

**Input/output contract:** Input — `LAYER3_PROMPT.format(reference, source_text)`, asking the model to judge whether the teacher genuinely engages the passage (quoting, reading, paraphrasing, or naming it in any recognizable form). Output — strict JSON, `{"engaged": true}` or `{"engaged": false}`, no other fields. `LLMVerificationFailed` is raised (never a guessed verdict) on any network/parse/shape failure.

**Never run live — confirmed, not assumed.** `scripts/test_citation_verifier_layers.py` mocks `call_layer3_llm` for every test (scripted-sequence-with-call-counter pattern, documented at the top of its own Layer 3 section: "every test below mocks the LLM call entirely — zero real network calls anywhere in the test file"). `git log --all -p` on `citation_verifier_layers.py` shows `llm_enabled=True` appearing only inside the module's own docstring, never as an actual call site anywhere in committed history. No premise violation — proceeded.

**Nothing needed to change to run it live.** `GROQ_API_KEY` is already populated in `backend/app/.env` (56 chars, confirmed present without printing the value). `call_layer3_llm()` and `verify_reference_grounded(..., llm_enabled=True)` are both already fully wired — flipping the flag was the only "change" needed. No build commit was made this session; `citation_verifier_layers.py` itself is untouched.

---

## Phase 2 — re-deriving the flagged set fresh

**Do not trust the 38 figure from this morning's cost estimate.** It came from `docs/audits/layer3_llm_cost_estimate_2026-07-28.md`'s Scope A, built by parsing the recheck audit's own "needs fixing" (59) + "needs manual review" (5) markdown tables (79 individual references). Re-parsing those same tables independently this session reproduced 38 exactly (37 confirmed by Layer 1, 1 by Layer 2, 3 hit the dotted-abbreviation parse gap) — so the arithmetic wasn't wrong, but the **scope was incomplete**.

**The authoritative source is `reference_fabrication_review/corpus_findings.jsonl`** — the real, original corpus-wide detection output (72 UNGROUNDED + 6 UNCERTAIN = 78 records, `document_id`/`proposition_id`/`reference`/`status` per record), still present on disk, gitignored, untouched since 2026-07-28. Re-running the CURRENT verifier (Layers 1+2, `llm_enabled=False`) against this exact 78-item baseline — not a table reconstruction — gives:

| | Count |
|---|---|
| Baseline items (72 UNGROUNDED + 6 UNCERTAIN) | 78 |
| Resolved automatically by the current fix (confirmed by Layer 1 or 2) | 30 (29 via Layer 1, 1 via Layer 2) |
| Unparseable — dotted-abbreviation gap, unrelated pre-existing defect (PLAN.md #45.5) | 6 (100% of the original UNCERTAIN items) |
| **Genuinely still Layer-3-reachable** | **42** |
| Arithmetic check | 30 + 6 + 42 = 78 — matches |

**Why 42, not 38:** diffing the two reference sets directly — 8 references are in the real baseline but were missing from the table-derived 79 (5 of them are genuinely-UNGROUNDED references that live in the closeness-check's *quote-candidate* bucket instead of the "needs fixing" bucket, annotated inline in that bucket's own table but never pulled into Scope A's count; 3 are additional Derek Prince dotted-abbreviation UNCERTAIN references the manual-review table only partially listed). 9 references were in the table-derived 79 but aren't part of the real flagged baseline at all (already-GROUNDED context references bundled into the same table rows as a genuinely-flagged one). Net: 79 − 9 + 8 = 78 (checks out), and of the 42 real Layer-3-reachable items, 9 weren't in the 38.

**Breakdown by teacher (42 reachable items):** Zac Poonen 19, Vlad Savchuk 12, Leonard Ravenhill 8, Derek Prince 1, Jack Deere 1, Doug Kreighbaum 1.

**Dotted-abbreviation count:** all 6 originally-UNCERTAIN baseline items (100%) — `Prov. 16:32`, `Deut. 18:9-14`, `Eph. 5:18`, `Jer. 6:14`, `Matt. 12:43-45`, `1 Cor. 9:26`, all Derek Prince / "Deliverance And Demonology". None of the 72 originally-UNGROUNDED items are affected by this defect (it only ever pushes toward UNCERTAIN, never masks a real UNGROUNDED — consistent with the existing disclosed note).

---

## Phase 3 — cost estimate (real token counts, two representative items)

Tokenized with `tiktoken` `cl100k_base` (disclosed proxy for the real Llama tokenizer — validated this session, see Phase 4). Fixed `LAYER3_PROMPT` overhead measured directly: **158 tokens**.

- **Short representative item:** Zac Poonen, "The Balance of Strictness and Compassion in Gods Prophet's" (1,556-token document) → ~1,721 input tokens, **$0.00102**.
- **Long representative item:** Doug Kreighbaum, "Leadership in the House of God" (37,858-token document, the longest in the pool) → ~38,023 input tokens, **$0.02244**.

**Full 42-item projection:** 366,578 total input tokens, 252 output tokens (6/call floor) → **$0.2165**. Well under the $5.00 session ceiling — proceeded to Phase 4 without stopping.

---

## Phase 4 — demo run: 5 items, live

Selected to span the range: 5 distinct teachers, document length from 3,767 to 37,858 tokens (the longest in the pool), and one hypothesized false-positive shape (a genuine KJV-worded quotation).

| Teacher | Reference | Automated status | Model verdict | Model's stated reason |
|---|---|---|---|---|
| Vlad Savchuk | Galatians 5:1 | ungrounded | **engaged=true** (disagrees) | "The text explicitly mentions Galatians 5.1 and quotes its wording." |
| Zac Poonen | James 1:26 | ungrounded | **engaged=true** (disagrees) | "The text engages James 1:26 by quoting and discussing its concept of controlling the tongue as a path to perfection." |
| Leonard Ravenhill | Romans 8:26 | ungrounded | **engaged=false** (agrees) | "The text does not mention or reference Romans 8:26 in any recognizable form." |
| Doug Kreighbaum | Acts 15:1-35 | ungrounded | **engaged=true** (disagrees) | "The text mentions Acts 15:1-35 in the context of discussing biblical eldership... specifically referencing Acts 15:2, 4, 6, 22-23." |
| Derek Prince | Genesis 14:18-20 | ungrounded | **engaged=true** (disagrees) | "The teacher engages Genesis 14:18-20 by referencing the story of Abraham and Melchizedek... in the context of tithing." |

**Note on the hypothesized false-positive:** the Ravenhill/Romans 8:26 item was selected because its proposition text quotes clearly KJV-worded scripture ("The Spirit also helpeth our infirmities"), hypothesized as a likely false-positive shape (WEB-only wording gap tricking the automated check). **The hypothesis was wrong, reported honestly, not cherry-picked** — the model agreed with the automated flag on this specific item; the actual source document does not engage Romans 8:26 at all. (A genuine KJV-quote false-positive DID turn up elsewhere in Phase 6 — see below.)

4 of 5 API calls succeeded with `engaged=true` (model overturns the automated flag); 1 of 5 with `engaged=false` (model agrees). Zero errors, zero parse failures, zero empty/truncated/ambiguous responses across all 5. Measured cost: $0.092 combined (official-contract-shaped estimate + diagnostic-call actual).

---

## Phase 5 — hard gate

All conditions checked, none triggered:
- No call errored, timed out, or was refused. ✅ clear
- No response failed to parse against the declared `{"engaged": bool}` contract. ✅ clear
- No response was empty, truncated, or ambiguous. ✅ clear
- Actual per-item cost did not materially exceed the Phase 3 estimate — Kreighbaum's actual input-token count (38,082, measured via the API's own `usage.prompt_tokens`) was within 0.15% of the `tiktoken` proxy's 38,025 estimate, validating the estimation method itself. ✅ clear

**Gate passed. Proceeded to Phase 6.**

---

## Phase 6 — full run across the remaining 37 items

All 42 items (5 demo + 37 remaining) reconciled together below.

**Reconciliation:** 42 attempted, 42 completed, 0 errored, 0 skipped. Arithmetic: 42 = 42.

**Verdict distribution:**

| | Count | % |
|---|---|---|
| Model confirms genuine engagement (disagrees with the automated `ungrounded` flag) | 33 | 78.6% |
| Model denies engagement (agrees the flag is real) | 9 | 21.4% |

**By teacher:**

| Teacher | Total | Model confirms (flag likely wrong) | Model denies (flag holds) |
|---|---|---|---|
| Zac Poonen | 19 | 19 | 0 |
| Vlad Savchuk | 12 | 10 | 2 |
| Leonard Ravenhill | 8 | 1 | 7 |
| Doug Kreighbaum | 1 | 1 | 0 |
| Derek Prince | 1 | 1 | 0 |
| Jack Deere | 1 | 1 | 0 |

**This is a real, sharp, teacher-specific skew, not noise.** Ravenhill's flagged items are disproportionately genuine (87.5% denied); Poonen's flagged items are disproportionately scanner false positives (0% denied). Consistent with Ravenhill's preaching register (dense, often KJV-quoting, aphoristic) differing structurally from Poonen's (plainer, more paraphrastic spoken-transcript style) — the same kind of per-teacher register difference CLAUDE.md Invariant 11 and PLAN.md #46 already document for the closeness check.

**The 9 items where the model denies engagement (still genuinely flagged after Layer 3):**

| Teacher | Document | Reference | Model's reason |
|---|---|---|---|
| Leonard Ravenhill | Paul's Passion, Preaching, and Praying | Romans 8:26 | Not mentioned or referenced in any recognizable form. |
| Vlad Savchuk | Should Christians Support 'Death with Dignity'? | Exodus 20:13 | Text mentions Exodus 20:3, not 20:13 — a different, nearby verse. |
| Leonard Ravenhill | The Cost Of Discipleship | Matthew 3:13-4 | Not mentioned or alluded to. |
| Leonard Ravenhill | The Cost Of Discipleship | Luke 3:21-22 | Not mentioned or alluded to. |
| Leonard Ravenhill | Laodicean Church | Revelation 3:18 | **Internal disagreement — see below.** Official call denied; diagnostic call confirmed with a specific KJV-worded quote. |
| Leonard Ravenhill | Paul's Passion, Preaching, and Praying | Philippians 4:11-12 | Not mentioned or alluded to. |
| Leonard Ravenhill | Paul's Passion, Preaching, and Praying | Philippians 3:10 | Not mentioned or engaged with. |
| Vlad Savchuk | Don't Take Communion Lightly | 1 Corinthians 11:30 | Text discusses 1 Cor 11:20 and 11:29, not 11:30. |
| Leonard Ravenhill | God is Worthy of Worship | Revelation 4:11 | Not mentioned or alluded to. |

**A genuine reliability caveat: 2 of 42 items (4.8%) disagreed internally between two prompt phrasings of the identical live call, at temperature=0.** The shipped `call_layer3_llm()`'s minimal boolean-only prompt and this session's diagnostic variant (identical model/temperature/input, only difference: the diagnostic also asks for a one-line reason) gave opposite verdicts on the same reference/document pair, twice:

- Zac Poonen, "True Riches and Wise Fathers", Hebrews 12:8 — official=confirmed, diagnostic=denied ("Hebrews 12:8 is not mentioned or referenced in the provided text, only Hebrews 12:5 and Hebrews 12:7 are discussed").
- Leonard Ravenhill, "Laodicean Church", Revelation 3:18 — official=denied, diagnostic=confirmed ("The text quotes and discusses Revelation 3:18, citing its wording and applying its message to the church" — this is the genuine KJV-quote false-positive case: "buy gold tried in the fire... white raiment").

Since temperature is 0 for both calls, this is measured prompt-sensitivity, not sampling randomness — asking the model to justify itself changed its answer on ~1 in 20 items in this run. This is real signal about how much to trust a single boolean-only Layer 3 call at scale, not a hypothetical concern.

**Actual money spent:** official-call cost (validated-proxy-based, since the shipped function doesn't expose token usage) + diagnostic-call cost (measured directly via the API's `usage` field) across all 42 items + the bonus illustrative item = **$0.4387** total, against the $5.00 session ceiling (8.8% used) and the $50 standing ceiling (0.9% used).

---

## Review file

`layer3_llm_reading_pass_review/layer3_live_run_2026-07-29.jsonl` (gitignored) — one record per item: document title/id, teacher, proposition id/index/full text, reference, pre-Layer-3 automated status, the shipped function's own verdict, the diagnostic variant's verdict + reason, and whether the two disagreed. 43 lines: 42 real Layer-3-reachable candidates + 1 clearly-labeled illustrative UNCERTAIN item (a dotted-abbreviation reference that structurally can never reach Layer 3 through the real pipeline, run out-of-band to show what the model says about it anyway). Line count confirmed against the reported totals above.

---

## What this does and doesn't establish

**Established:** Layer 3, as shipped, runs cleanly against a real model with zero mechanical failures across 42 live calls. Most of the 42 flagged items (78.6%) are very likely scanner false positives, not real citation problems — consistent with the corpus-wide pattern CLAUDE.md's Landmines section already documents (genuine fabrication is rare). A real, teacher-specific pattern in where the flag holds up (Ravenhill) vs doesn't (Poonen) is now measured, not assumed. A concrete, measured reliability gap (prompt-sensitivity, ~5% of items) is now documented instead of theoretical.

**Not established:** this is 42 items from the existing, mostly short-form corpus (Savchuk/Poonen/Ravenhill/Deere/Kreighbaum/Prince's short pieces) — not yet run against the long-form Derek Prince backfill population (#49) that PLAN.md already flags as a structurally different register. A single boolean-only call's accuracy at full backfill scale (~364 projected calls) is not yet measured — only demonstrated not to break mechanically. Whether the ~5% prompt-sensitivity rate found here is acceptable for a fully-automated backfill gate, or whether the confirming step needs the reason-capturing variant (at roughly double the cost and latency) is a design decision for whoever wires Layer 3 into the reversed anti-fabrication filter (CLAUDE.md Invariant 11) — not resolved by this session.
