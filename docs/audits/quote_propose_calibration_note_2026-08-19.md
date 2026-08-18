# Quote propose calibration note (Task 4)

**Date:** 2026-08-19  
**Status:** Paid calibration #1 complete; **parser offset repair** landed after 0/59 usable proposals; re-run pending Alex OK.

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

## Next (attended)

1. Re-run after offset repair: `python3 scripts/propose_quotes_dry_run.py --limit 3 --run --verify` (~$1.42 again)
2. Rate quality/tag precision on the new report
3. Task 5 gold write path (default dry-run; `--apply` only with explicit approval)
