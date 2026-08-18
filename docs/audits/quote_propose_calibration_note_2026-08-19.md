# Quote propose calibration note (Task 4)

**Date:** 2026-08-19  
**Status:** Code + unit tests + live **estimate-only** complete. Paid Anthropic dry-run **not run** (Alex: build first).

## What landed

- `backend/app/services/quote_propose.py` — `quote_propose_v1` prompt, JSON parse, strict offset check, `VALID_TAGS` filter via `app.constants`
- `scripts/propose_quotes_dry_run.py` — cost header, `$50` abort, `--estimate-only` / `--run` / `--mock`, zero quote writes
- `scripts/test_quote_propose_unit.py` — parse/taxonomy/offset + mutation proof that dry-run never calls `create_and_approve_quote` / `raw_insert_quote`

## Live cost projection (estimate-only, read-only DB)

Scope: first 3 cleared Derek Prince non-book documents (title order), eligible chunks only.

| Field | Value |
|---|---|
| Documents | 3 (`A Call To Corporate Fasting`, `A Divinely Ordained Exchange`, `A Kingdom of Priests`) |
| Windows (chunks) | 59 |
| Avg window chars | 2020 |
| Model (assumed) | `claude-sonnet-4-5` |
| Pricing assumption | $3/MTok in + $15/MTok out |
| **Projected $** | **~$1.42** |
| Ceiling | $50 |

Well under the plan’s ~$5–12 calibration band and the $50 hard ceiling.

## Next (attended)

1. Alex OK → `python3 scripts/propose_quotes_dry_run.py --limit 3 --run` (optionally `--verify`)
2. Save report under gitignored `quote_propose_review/`
3. Task 5 gold write path (default dry-run; `--apply` only with explicit approval)
