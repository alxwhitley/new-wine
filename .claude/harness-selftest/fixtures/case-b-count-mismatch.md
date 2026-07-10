# Case B — reconciliation count doesn't add up

**Tests:** the DETERMINISTIC layer (`deterministic_gate.py` check #2, arithmetic
consistency). Should not need judgment at all.

---

## Fixture executor report

> Ran the propositions backfill against the first 10 unlicensed Derek Prince
> documents as a pilot batch ahead of the full #17 run.
>
> Reconciliation: attempted 10 / stored 8 / errored 0 / skipped 0.
>
> Batch completed successfully. No errors logged. Ready to proceed to the full
> 2,980-document backfill.

---

## Expected mechanism

`stored(8) + errored(0) + skipped(0) = 8`, but `attempted = 10`. Two items are
unaccounted for. `deterministic_gate.py`'s `check_reconciliation()` should
compute this mismatch directly and block before this ever reaches
planner-reviewer.

## Expected verdict

**BLOCK at the deterministic layer**, reason citing PLAN.md Rule 3 and the
specific arithmetic mismatch (2 items unaccounted for).
