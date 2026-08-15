# Nixpacks Python-version parity — 2026-08-14

Repo-only, read-and-check task (PLAN.md F2 exit criterion: "Backend and
worker Python-version differences are intentional and documented"). No DB
writes, no manifest edits — `backend/nixpacks.toml` and the repo-root
`nixpacks.toml` were read-only tonight, per the task's forbidden list.

## What both manifests declare today

Both files were read in full this session. Both currently declare the same
Python interpreter, `python312`.

`backend/nixpacks.toml` (used by the backend web service, Railway Root
Directory `backend`):

```toml
[phases.setup]
nixPkgs = ["python312"]
```

`nixpacks.toml` (repo root; used by the async answer worker service,
Railway Root Directory `/` — see CLAUDE.md's Landmine entry "The repo-root
`nixpacks.toml` is the async worker service's build manifest"):

```toml
# Root Nixpacks build config — async answer worker service only
# (scripts/answer_worker.py — Project 1, Stage 1 durable async answer path).
#
# WHY THIS FILE IS AT THE REPO ROOT (and does NOT affect the backend service):
#   The worker's entrypoint (scripts/answer_worker.py) lives at the repo root
#   but imports the backend app (it inserts backend/ onto sys.path and loads
#   backend/app/.env). Its Railway service therefore uses Root Directory "/"
#   (the whole repo). The backend WEB service uses Root Directory "backend", so
#   Nixpacks reads backend/nixpacks.toml for it — this root file is consulted
#   ONLY by a service whose root is "/", i.e. the worker. The backend build is
#   byte-identical after this change.
#
# WHY THE BUILD IS SPELLED OUT EXPLICITLY (unlike backend/nixpacks.toml):
#   At the repo root there is no Python manifest (requirements.txt / pyproject /
#   Pipfile / main.py) for Nixpacks' Python provider to auto-detect, so the
#   provider is forced. A forced provider does not run its auto-generated
#   venv+install step, so the venv is created here explicitly and the install
#   targets backend/requirements.txt via the venv's own pip (absolute /opt/venv
#   paths — the same venv location Nixpacks' Python provider uses).
#
# PARITY WITH THE BACKEND SERVICE (backend/nixpacks.toml + backend/railway.toml):
#   - same interpreter: python312
#   - same dependency set: the SAME backend/requirements.txt, via pip
#   Concurrency is a runtime dial set with the WORKER_CONCURRENCY env var, not
#   baked into the start command (default 4 if unset).

providers = ["python"]

[phases.setup]
nixPkgs = ["python312"]

[phases.install]
cmds = [
  "python3 -m venv --copies /opt/venv",
  "/opt/venv/bin/pip install -r backend/requirements.txt",
]

[start]
cmd = "/opt/venv/bin/python scripts/answer_worker.py"
```

**Both manifests agree with each other today.** There is no live
disagreement between the backend web service and the worker service.

## Git history confirmation

Confirmed directly via `git log --follow -p` and `git show` on both files
(not assumed from CLAUDE.md's prose):

- `backend/nixpacks.toml` was created 2026-04-03 (`066a85f`,
  "Pre-deployment hardening: pin deps, lock Python 3.9, remove localhost
  fallbacks") declaring `nixPkgs = ["python39"]`. It was changed to
  `python312` by commit `a729fba` (2026-06-12, "security: harden backend +
  frontend across 4 areas") — the diff is exactly one line:
  `-nixPkgs = ["python39"]` / `+nixPkgs = ["python312"]`. That commit's
  message body confirms the change was deliberate ("Python 3.9 → 3.12 in
  nixpacks.toml", among four other hardening changes in the same commit).
- The repo-root `nixpacks.toml` was created later, 2026-08-04 (`2ba9f12`,
  "build: add root nixpacks.toml for the async answer worker service"),
  and was **already at `python312` from its very first commit** — it was
  written to match the backend's already-migrated interpreter, not written
  independently and then later reconciled. It has no earlier history to
  check for a prior divergence; this is its only commit.

So: the two manifests have never actually disagreed with each other at any
point either file has existed — the worker manifest was created after, and
explicitly to parity with, the backend's already-completed python39→312
move.

## New check added: `scripts/test_nixpacks_python_parity.py`

A small, dependency-free, standalone script (this repo's `scripts/test_*.py`
convention — a runnable script, not pytest) that reads both manifest files,
extracts each one's declared `nixPkgs` python version via a regex/line-scan
(not `tomllib`), and asserts they match, exiting non-zero with a clear
message if they ever diverge.

**Implementation choice: regex/line-scan, not `tomllib`.** This machine's
default `python3` is 3.9.6 (confirmed via `python3 --version`), and
`tomllib` is stdlib-only from Python 3.11+ — it is not importable on 3.9.
Since this repo's other `scripts/test_*.py` files are run directly via a
bare `python3` invocation (see e.g. `scripts/test_quote_verifier.py`'s own
"Run from project root: python3 scripts/test_quote_verifier.py" docstring
convention) and this check needs to run cleanly on this machine without a
new dependency, a narrow, well-commented regex against the known
`nixPkgs = [...]` line shape was used instead. This is a deliberately
narrow parser (it only understands a `nixPkgs = ["pythonNNN", ...]`
single-line list) — sufficient for what both real manifests actually
contain, not a general TOML parser.

**Verification results:**

1. Direct run (`python3 scripts/test_nixpacks_python_parity.py` from the
   worktree root): exit code 0.
   ```
   backend/nixpacks.toml declares: python312
   nixpacks.toml (repo root) declares: python312

   PASS: backend/nixpacks.toml and nixpacks.toml agree (python312).
   ```
2. Self-test (scratch copies outside the repo, not touching anything in
   the allowlist or worktree): confirmed the script correctly reports
   `FAIL` with a clear mismatch message and exit code 1 when the two
   manifests are deliberately set to different Python versions
   (`python312` vs `python39`). Deleted afterward; no trace left in the
   worktree or elsewhere.
3. Declared verification command, run through
   `scripts/harness_coordinator/v1/verification_commands.py`'s CLI
   (mandatory), from the primary checkout, 30s declared timeout:
   ```
   PYTHONPATH=scripts python3 -m harness_coordinator.v1.verification_commands \
     --command-id nixpacks-parity --timeout-seconds 30 --expected-exit-code 0 \
     --cwd /Users/alexwhitley/rhemata/.worktrees/claude-o5-nixpacks-parity \
     -- python3 scripts/test_nixpacks_python_parity.py
   ```
   Result: `"outcome": "PASSED"`, `"exit_code": 0`.

## Doc-vs-reality finding — flagged for Alex/terminal to correct, not fixed here

**CLAUDE.md Invariant 1** currently reads: *"Python 3.9. Use `Optional[str]`,
never `str | None`. Railway locks 3.9 via `nixpacks.toml`; newer syntax
runs locally and breaks in prod."*

**CLAUDE.md's Tech Stack table** currently reads: *"Backend | Python 3.9 /
FastAPI → Railway"*.

Both statements are stale. Both live Nixpacks manifests (backend and
worker) have declared `python312`, not `python39`, since commit `a729fba`
(2026-06-12) for the backend, and since its creation (`2ba9f12`,
2026-08-04) for the worker. This is not a live infrastructure
disagreement — it's the documentation lagging a deliberate 2026-06-12
change that was never reflected back into CLAUDE.md.

This audit does **not** correct CLAUDE.md — that file is on this task's
forbidden list, and its own hard rule requires Alex's/the terminal's
review before any edit. Proposed correction, for the orchestrator to relay
to Alex:

- Invariant 1: update "Python 3.9" to "Python 3.12" (or otherwise note
  that Railway/Nixpacks builds run 3.12 as of `a729fba`, 2026-06-12), and
  re-check whether the `Optional[str]` vs `str | None` guidance still
  applies — 3.12 supports PEP 604 union syntax (`str | None`) natively, so
  the reason given for the rule ("newer syntax runs locally and breaks in
  prod") may no longer hold if the deployed interpreter is genuinely 3.12
  now. This is a substantive judgment call (does the codebase's actual
  Python version target stay 3.9-compatible syntax by convention, or does
  it get relaxed now that the runtime is 3.12) — not something this task
  resolves; flagging it plainly so it isn't missed.
- Tech Stack table: update "Backend | Python 3.9 / FastAPI → Railway" to
  reflect the actual deployed version.

Whether to also update local dev practices, CI, or any other place that
assumes 3.9 syntax constraints is a separate, larger question outside this
task's scope — flagged, not resolved.

## Scope confirmation

- Neither manifest was edited. Both were read-only this session, as
  required.
- No mismatch was found between the two live manifests — the "Human-stop
  / partial-failure handling" branch of this packet (manifests disagreeing
  with each other) does not apply. This is not marked `HUMAN_REQUIRED`.
- The genuine finding here is documentation staleness in a governed file
  (CLAUDE.md), which is explicitly out of this task's write scope and is
  reported above for Alex/terminal to action.
