# New Wine A2 — Opus 5 Segmentation, Live End-to-End Test, 2026-08-29

**Status: real, budget-approved live spend. Alex approved a $3.00 ceiling for
this specific test** ("do 3$ for this test. I want to get through a full
issue if possible to see if it works end to end"), following five rounds of
free (zero-cost) fixture-testing against Issue 02-1973 earlier the same
session (chunking and ToC-anchored designs both refuted; a Grok-authored
patch series v1.1→v1.4 revised the marker/folio/resume design against real
data with no live spend — see
`docs/audits/2026-08/new_wine_free_checks_2026-08-29.md` and
`rhemata-status.md`'s Current state section for that trail). **No database
write. No file promotion. This is a segmentation-stage diagnostic only.**

## What actually ran

`local/2026-08/new_wine_opus_e2e_test_2026-08-29.py` — not a modification to
`scripts/magazine_review/articles.py` or `live_providers.py`.
`ARTICLE_MODEL` in `articles.py` is untouched (`"openai/gpt-oss-120b"`). The
script builds its own `AnthropicSegmentationClient` (matching the
`StructuredOutputClient` Protocol exactly: `.complete(request) -> {"output",
"usage", "cost_usd"}`) and calls the **real, unmodified**
`articles.segment_articles(transcript, client)` directly with it — so the
result is checked against the actual shipped production gates (overlap,
`_MAX_ARTICLE_CHARS`, non-article size/fraction caps, the
`foreign_article_title_in_span` title-bleed check, and the full
disjoint-coverage partition check), not a bespoke or relaxed check.

Sequence, each step budget-guarded against the $3 ceiling with a worst-case
pre-call estimate before every request (mirroring the existing
`CostBudget`/`reserve`/`settle` pattern in `live_providers.py`):

1. **Free dry run** — loaded the real cached transcript
   (`docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-27_v6/ocr_manifest.json`
   via `OCRManifest.from_dict()` → `VerifiedIssueTranscript.from_manifest()`)
   and verified the schema-conversion logic (Groq/OpenAI's
   `{"type":"json_schema","json_schema":{"name","strict","schema"}}` → Claude's
   `{"type":"json_schema","schema":{...}}`, with `minimum`/`maximum` stripped
   from integer properties per the CLAUDE.md Landmines gotcha from the earlier
   2026-08-29 overrun) — zero cost, no live calls.
2. **Dummy mechanics test** — a trivial schema/prompt against `claude-opus-5`
   via `client.messages.stream(...)` + `output_config.format` + adaptive
   thinking + `get_final_message()`, to prove the SDK/schema mechanics work
   before spending on the real transcript (the exact discipline the earlier
   overrun's landmine calls for). **Cost: $0.0013.**
3. **Real segmentation call** — the full 121,011-char transcript, `effort:
   "high"` (matching `SEGMENTATION_REASONING="high"` already used for the
   gpt-oss-120b path, for a fair comparison), `max_tokens=64000`.

Both live calls authenticated via the existing `_credential()` helper in
`live_providers.py`, reading `ANTHROPIC_API_KEY` from `backend/app/.env` —
no new credential-handling code.

## Result: segmentation passed real production validation

`segment_articles()` raised no `ArticleReviewError`. **10 articles, 24
non-article spans, zero gate failures** — no overlaps, no
`article_implausibly_long`, no `foreign_article_title_in_span`, full
disjoint coverage of the transcript within tolerance.

| Article | Author | Pages | Span |
|---|---|---|---|
| Health and Healing—it's up to you! (Part I) | Derek Prince | 2–3 | [200:7716) |
| Editorial | Editor | 5 | [11590:13176) |
| Health and Healing—it's up to you! (continued) | Derek Prince | 6–8 | [15927:28738) |
| The Nature of Obedience | Bob Mumford | 9–14 | [28738:53469) |
| Bible Study: The Historic Books — I and II Chronicles | Howard Coffey | 15–16 | [53469:61232) |
| The Call of Love | Lea Kriebs | 17 | [61232:62124) |
| The Apostle—God's Master Builder (Part I) | Derek Prince | 18–22 | [62124:79636) |
| The Apostle—God's Master Builder (continued) | Derek Prince | 22–23 | [80864:88706) |
| Keeping the Unity | New Adventures in Prayer (Prayer Group Newsletter) | 24–25 | [88706:93309) |
| New Wine Forum: Spiritual Potpourri | New Wine Forum | 26–30 | [93309:115889) |

**Every known hard case in this issue, previously documented as a repeated
failure mode across dozens of gpt-oss-120b attempts, was handled correctly
this run:**

- **Health and Healing's interruption** — split into two real spans around
  pages 4–5 (letters/editorial/subscription material), matching what the
  free-check rounds earlier this session hand-derived from the raw
  transcript almost exactly (hand-derived span1 end ≈ 7674; model's actual
  end 7716 — close, plausibly including a bit more trailing context).
- **The Apostle's interruption** — also split in two, with the ~1,228-char
  gap between [79636] and [80864] correctly absorbed as non-article content
  rather than swallowed into either half (confirmed by the fact that the
  full coverage check passed at all — a gap here would have raised
  `article_coverage_incomplete`).
- **Keeping the Unity** — credited to **"New Adventures in Prayer (Prayer
  Group Newsletter)"**, the actual reprint-source publication, not an
  invented person. Matches Check 7's hand-derived fixture from the free-check
  round exactly, with zero coaching toward it in this run's prompt beyond
  the existing shipped instructions.
- **New Wine Forum** — credited to the column's own name, not the
  "Spiritual Potpourri" subtitle (the exact misattribution refuted-design-2
  was built around), and not a single panelist. Matches the already-shipped
  `SEGMENTATION_INSTRUCTIONS` guidance ("use the column's own name... as its
  author") exactly.

## Real usage, honestly logged

```
input_tokens: 52,930
output_tokens: 53,125
segmentation_cost_usd: $1.5928
```

Total spend this run: **$1.5941 of the $3.00 ceiling** (dummy test +
segmentation). **$1.4059 remaining, unspent** — article review and
proposition extraction were not attempted; see "What this does not prove"
below.

**On the disputed $1.4776/52,930/48,518 figure from earlier the same
session** (flagged in the Grok patch-set exchange as not repo-sourced and
likely back-solved to hit the known total): the **input-token count matches
exactly** (52,930 here vs. 52,930 claimed) — meaning that half of the figure
was apparently real, probably genuinely present in whatever brief produced
it. **The output-token count does not match** (53,125 here vs. 48,518
claimed, ~9% higher) — consistent with output being the volatile,
run-to-run-variable half (adaptive thinking scales with the model's own
reasoning depth per call), while input for a fixed transcript + schema +
instructions is stable and reproducible. The two total costs are close
($1.5928 here vs. $1.4776 originally, ~8% apart) — both are plausible,
real-magnitude figures for a one-shot Opus 5 segmentation call on this
issue; neither should be treated as *the* number going forward without
averaging more real runs.

## Real bug found while wiring this up

`segment_articles()` (`scripts/magazine_review/articles.py:880-899`)
constructs the returned `ArticleManifest` with
**`segmentation_model=ARTICLE_MODEL`** — the hardcoded module constant, not
derived from whichever client actually ran the call. This means **the
manifest this run produced carries a false provenance stamp**: its own
`segmentation_model` field reads `"openai/gpt-oss-120b"` even though Claude
Opus 5 actually performed the segmentation. `_stage_identity()` and
`review_articles_against_issue()`'s lineage check
(`manifest.segmentation_model != ARTICLE_MODEL` /
`manifest.reviewer_model != ARTICLE_MODEL`) both key off this same hardcoded
constant — meaning a lineage check comparing "declared model" to "expected
model" would trivially pass here by accident (both sides read the same
wrong constant), not because the provenance is actually correct. **This is a
real gap, not a hypothetical one** — any future run mixing models (which
this test necessarily does, since `ARTICLE_MODEL` has no per-call override)
needs this fixed before its output is trustworthy: `segmentation_model`
should be derived from the client actually used (e.g. a `.model` attribute
on the `StructuredOutputClient`, mirroring `GroqStructuredOutputClient.model`
which already exists), not read from a module-level constant. Not fixed in
this session — flagged for a future one, since it's a real code change to
production validation logic, not a diagnostic script's problem to route
around.

## What this does and does not prove

**Proves:**
- A second real, clean, honestly-logged Opus 5 segmentation pass on this
  issue exists (the first was today's earlier informal comparison,
  mechanism described in `rhemata-status.md`'s Current state section — this
  is a second, independent data point, moving past "n=1, provisional").
- Opus 5's segmentation output, run through the actual production validation
  path unmodified, clears every real gate on the hardest issue this project
  has tested against — including the specific failure classes
  (title-bleed, interrupted articles, panel misattribution, reprint
  misattribution) that dozens of gpt-oss-120b attempts across two sessions
  never cleared simultaneously.
- The Opus SDK/schema mechanics discovered the hard way in the earlier
  overrun (streaming requirement, `minimum`/`maximum` schema rejection,
  exact envelope-key contract) are now correctly handled in reusable code
  and did not recur.

**Does not prove:**
- Nothing about Grok's v1.1–v1.4 marker-exclusion/folio-hatch/resume-2a-2b
  design — this ran against the schema **currently shipped** in `articles.py`
  (flat `author: str`), not that redesign, which remains unimplemented in
  code. The fact that "New Wine Forum" could only be credited to a generic
  column name rather than its four real named panelists (Mumford, Prince,
  Simpson, Basham) is itself a live illustration of why the `authors[]`
  array design matters — the current schema structurally cannot represent
  what actually happened on that page.
- Nothing about article review, proposition extraction, or proposition
  review — none were attempted. The manifest returned here is
  `status="quarantined"`, `quarantine_reasons=("semantic_review_required",)`
  by `segment_articles()`'s own design (semantic review is a separate,
  later stage) — this was never going to reach `status: ok` from
  segmentation alone, full-issue completion was out of reach within the
  approved budget once article review turned out to require the same model
  (a lineage constraint discovered while building this test — see the bug
  above) at an unknown, potentially comparable cost.
- Reliability. n=2 is still a small sample. Nothing here contradicts the
  standing CLAUDE.md Landmines conclusion that segmentation quality is
  dominated by run-to-run model variance, not a single deterministic gap —
  this result is evidence in Opus's favor, not proof it is reliable at any
  particular rate.

## Artifacts

- Script: `local/2026-08/new_wine_opus_e2e_test_2026-08-29.py`
- Raw result: `local/2026-08/new_wine_opus_e2e_segmentation_result_2026-08-29.json`
- Both gitignored under `local/` per existing convention; this document is
  the durable record.
