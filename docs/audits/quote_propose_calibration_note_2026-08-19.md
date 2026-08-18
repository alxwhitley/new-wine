# Quote propose calibration note (Task 4)

**Date:** 2026-08-19  
**Status:** Paid calibration **#2 complete** after offset repair. Yield usable for gold-path design.

## What landed

- `backend/app/services/quote_propose.py` — `quote_propose_v1` prompt, JSON parse, `VALID_TAGS` filter via `app.constants`
- Offset handling: prefer declared offsets when exact; else repair from a **unique** exact `quote_text` substring; refuse invent / ambiguous duplicates
- `scripts/propose_quotes_dry_run.py` — cost header, `$50` abort, `--estimate-only` / `--run` / `--mock`, zero quote writes; persists `raw_response` on empty windows
- `scripts/test_quote_propose_unit.py` — parse/taxonomy/offset-repair + mutation proof that dry-run never calls write helpers

## Live cost projection (3 cleared Prince docs)

| Field | Value |
|---|---|
| Documents | 3 (`A Call To Corporate Fasting`, `A Divinely Ordained Exchange`, `A Kingdom of Priests`) |
| Windows (chunks) | 59 |
| Model | `claude-sonnet-4-5` |
| **Projected $** | **~$1.42** (ceiling $50) |

## Paid run #1 (2026-08-19, ~7.5 min, exit 0)

- `windows_attempted=59`, `proposals_parsed=0`, `quote_rows_written=0`
- Model **did** propose (typically 1–3 candidates/window); every candidate failed strict `offset_mismatch` before repair existed
- Dominant errors: `candidate_*_offset_mismatch` (59/53/26 for cand 0/1/2)
- Report (gitignored): `quote_propose_review/propose_dry_run_20260818T202504Z.jsonl`

## Paid run #2 (after offset repair, ~7.6 min, exit 0)

Report: `quote_propose_review/propose_dry_run_20260818T203614Z.jsonl`

| Metric | Count |
|---|---|
| windows_attempted | 59 |
| empty windows (no usable parse) | 26 (dominant: `not_substring` — model paraphrased) |
| proposals_parsed | 47 |
| quality_pass / quality_fail | **34** / 13 (all fails = `length_band`) |
| verify_pass among quality_ok | **27** (6 `boundary_proximity`, 1 `subchunk_exclusion`) |
| windows with ≥1 verify_pass | 21 |
| quote_rows_written | **0** |

Passage tags look on-topic for these sermons (Fasting and Prayer, Atonement, Spiritual Warfare, etc.) — not document-tag inheritance. Residual losses are expected authenticity gates + short spans + invent/paraphrase.

## Next (attended)

1. **Task 5 gold apply on these same 3 docs** — only after Alex’s explicit go in a fresh session. Command:

   `PYTHONUNBUFFERED=1 python3 scripts/extract_quotes_quality_pipeline.py --limit 3 --apply --status pending`

   Expect ~mid-20s pending rows (`quote_quality_v1`, `selection_eligible=true`, `topic_ids` set). Keep `QUOTE_SELECTION_ENABLED` off. Migration 089 already applied; Task 8 Step 1 regressions already landed.
2. Hard reconciliation after apply; then Alex QuoteRail visual sign-off; then attended re-enable.
3. Optional later: prompt nudge against paraphrase / prefer mid-chunk spans to cut `not_substring` + flush-boundary refuses
