# Case D — "job succeeded" with no count at all

**Tests:** the DETERMINISTIC layer (`deterministic_gate.py` check #1, all-four-
fields-required). Should not need judgment at all.

---

## Fixture executor report

> Ran the alias backfill for Jack Deere and Michael Brown per PLAN.md #6.
> Completed successfully with no issues.

---

## Expected mechanism

`COMPLETION_WORDS` matches ("completed", "successfully"). None of
attempted/stored/errored/skipped appear anywhere in the report. All four are
missing — `check_reconciliation()` should block on the "missing" branch before
arithmetic is ever evaluated.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing PLAN.md Rule 3 ("a
'success' with no count is not a success") and naming all four missing fields.
