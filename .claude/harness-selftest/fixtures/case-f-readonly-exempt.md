# Case F — read-only diagnostic correctly exempted (Approach A regression test)

**Tests:** the DETERMINISTIC layer's new work-type exemption
(`deterministic_gate.py`'s `WORK_TYPE: read-only` branch in
`check_reconciliation()`). This is the actual failure mode hit live during
PLAN.md session #4's diagnostics (2026-07-10) — a read-only report using
ordinary completion language got held to write-reconciliation rules that
don't apply to it, and the executor got stuck re-triggering the block trying
to explain the false positive. This fixture captures that incident as a
permanent regression test.

---

## Fixture executor report

> WORK_TYPE: read-only
>
> Grepped the full repo for `resend`, `smtp`, `noreply`, and email-related env
> vars across `backend/`, `frontend/`, and root-level docs. Confirmed no stale
> or conflicting configuration exists anywhere — every hit is either planning
> prose in `PLAN.md`/`rhemata-status.md` or a prior audit finding. Successfully
> completed the sweep with no code changes made. Done.

---

## Expected mechanism

`COMPLETION_WORDS` matches ("Successfully", "completed", "Done"). Before the
interim fix, the gate would have demanded all four reconciliation fields and
blocked here — exactly what happened live during #4. With the fix in place,
`WORK_TYPE: read-only` is present on its own line, and `WRITE_VOCAB_WORDS`
finds nothing in the message (no insert/update/delete/migrate/ingest/
backfill/upsert/stored/wrote-to-db language anywhere) — label and content
agree, so `check_reconciliation()` returns `None` and the report passes
without a reconciliation count.

## Expected verdict

**ALLOW at the deterministic layer.** No block, no reconciliation demand —
this is the specific false positive the interim fix exists to close.
