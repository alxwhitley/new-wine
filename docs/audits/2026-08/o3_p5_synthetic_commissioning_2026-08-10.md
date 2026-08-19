# O3-P5 Synthetic Commissioning — 2026-08-11

## Boundary

This commissioning used only disposable temporary state roots/worktrees and the fixed local fixtures `synthetic_p5_worker.py` and `synthetic_p5_reviewer.py`. It performed no network, database, provider, deployment, push, merge, or governed-content action.

Synthetic success proves the coordinator's orchestration plumbing. It does **not** prove that a real Kimi, Sonnet, Claude, Grok, or other provider subprocess is safely sandboxed. Real-provider commissioning remains `HUMAN_REQUIRED` until a separately proven pre-execution sandbox constrains filesystem, commands, environment, and network.

The completion receipt closes the tested post-worker crash windows, but this audit does not claim general exactly-once semantics for arbitrary external side effects. A hard process failure in the micro-window after an external effect but before any receipt can exist still requires an idempotent worker effect or a provider-specific transactional protocol. The synthetic marker is deliberately idempotency-observable; real providers remain outside this commissioning.

## TDD evidence

The first commissioning test failed genuinely with:

```text
TypeError: run_once() got an unexpected keyword argument 'worker_adapters'
```

That RED demonstrated that the accepted invocation boundary had no production coordinator caller. The minimum GREEN connected an explicitly supplied operator-owned synthetic `WorkerAdapter` to `run_once`, persisted coordinator-owned attempt evidence through the pinned state-root handle, resolved the durable attempt through the accepted classifier, and archived the completed claim immutably.

Subsequent RED runs exposed and corrected two integration defects:

- `WORKER_RESULT_RECORDED` lacked the canonical raw-byte artifact citation required by review ingestion.
- A completed worker claim remained live and prevented the next retry from being claimed.

## Commissioned scenarios

- enrollment → claim → fixed synthetic worker → pinned result/outcome → `WORKER_RESULT_RECORDED` → REVIEW;
- parent ACCEPT → terminal seal → dependency promotion → child worker/review → child ACCEPT → seal;
- verdict-only output from a predeclared trusted synthetic reviewer identity;
- crash before invocation, followed by one execution of the new attempt only;
- crash after durable outcome publication, followed by classification without reinvocation;
- crash after worker completion but before outcome publication, recovered from an authenticated completion receipt without reinvocation;
- crash during partial result publication, resumed idempotently from the same receipt;
- missing operator adapter while a receipt exists blocks recovery without requeue; supplying the matching adapter later consumes the same attempt;
- failed atomic receipt publication recovers a fully fsynced pending receipt without reinvocation;
- crash after `VERDICT_RECORDED`, followed by seal repair without a duplicate verdict;
- top-level singleton contention and lower-level O_EXCL claim contention as distinct proofs;
- repeated terminal `--once` without duplicate worker markers, attempt/result/verdict/transition events, seals, or reconciliation report events;
- deterministic successful `run_cli --once` result across equivalent disposable empty roots.

## Verification

```text
PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o3_p5_commissioning.py -q
11 passed

PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o3_p5_commissioning.py \
  .claude/harness-selftest/test_o3_p5_claim_root_identity.py \
  .claude/harness-selftest/test_o3_p5_resume.py -q
54 passed

PYTHONPATH=scripts:.claude/harness-selftest python3 -m pytest \
  .claude/harness-selftest/test_o2_*.py \
  .claude/harness-selftest/test_o3_*.py -q
656 passed
```

Final static checks and independent Opus acceptance are recorded in the closing gate below.

## Final gate

Fresh independent Opus review returned `ACCEPT`. It verified the unconditional receipt barrier, missing/mismatched adapter fail-closed behavior, atomic pending-to-final receipt publication and recovery, exact receipt/result identity bindings, sidecar termination boundary, partial-publication recovery, and the explicit limitation on general external exactly-once semantics.

Final static evidence:

```text
scoped py_compile: passed
git diff --check: clean
legacy harness scripts: 3/3 ALL CHECKS PASSED
```
