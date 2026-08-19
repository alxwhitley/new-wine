# `pydantic`/`starlette` pin — 2026-08-14

Branch: `claude/o5-deps-pin` (worktree `.worktrees/claude-o5-deps-pin`,
started from `19980c5`). PLAN.md F2 exit criterion: "Production-relevant
versions that caused divergence, especially pydantic and starlette, are
deterministic" + "Clean-environment backend and admin-auth smoke tests
pass."

**Revision note (2026-08-15):** this doc was revised after a
planner-reviewer REVISE verdict on the first draft. Two defects were fixed:
(1) the original regression test could not actually distinguish the
pre-`da27fe4` code shape from the fixed shape on this pinned stack — a
structural `inspect.signature()` check was added, proven discriminating
against the real historical source; (2) a "console output" block in this
doc did not match what the script actually prints — replaced below with
real, verbatim-captured output. Both fixes, and the reproduction proving
them, are documented in full below; nothing from the original pin/version
findings changed (those were independently reproduced and confirmed
correct by the reviewer).

## What changed

`backend/requirements.txt` now pins:

```
pydantic==2.13.4
starlette==0.52.1
```

Added directly under the existing `fastapi==0.128.8` line, same `==` pin
style as every other entry in the file. No other line touched.

## How the resolved versions were determined

A fresh `python3.12 -m venv` (see "Python version finding" below) had the
**unpinned** `backend/requirements.txt` (as it stood before this change)
installed into it, then `pip show pydantic starlette` was read directly —
not assumed from CLAUDE.md's Landmines note, which cited `pydantic 2.12.5`
as of 2026-08-06 and is now stale:

- `pydantic` resolved to **2.13.4** (pulled in transitively by fastapi,
  anthropic, cohere, google-genai, groq, openai, postgrest, pyiceberg,
  realtime, storage3, supabase-auth — `pip show` confirms all of those as
  `Required-by`).
- `starlette` resolved to **0.52.1** (pulled in transitively by fastapi
  only).

`fastapi==0.128.8`'s own declared constraints (`importlib.metadata`
`Requires-Dist`) are `starlette<1.0.0,>=0.40.0` and `pydantic>=2.7.0` — both
pinned versions satisfy these comfortably, so the new pins do not fight
fastapi's own requirement. `pip check` on the fully-pinned clean install
reports "No broken requirements found."

## Python version finding (verified, not taken on faith)

The packet flagged a suspected doc/reality drift and asked me to confirm it
independently before proceeding. Confirmed:

- `backend/nixpacks.toml` (live, current file): `nixPkgs = ["python312"]`.
- Repo-root `nixpacks.toml` (the async worker's build manifest — see
  CLAUDE.md Landmines, "The repo-root `nixpacks.toml` is the async worker
  service's build manifest"): also `nixPkgs = ["python312"]`.
- `git log -1 a729fba` (full SHA `a729fbac1a6c751505025f6576c151ee068b39b3`,
  2026-06-12, "security: harden backend + frontend across 4 areas"):
  `git show a729fba -- backend/nixpacks.toml` shows the diff
  `-nixPkgs = ["python39"]` / `+nixPkgs = ["python312"]`, and the commit
  message's own bullet list states "Python 3.9 → 3.12 in nixpacks.toml" —
  a deliberate, intentional change, not drift or an accident.

**CLAUDE.md Invariant 1 ("Python 3.9... Railway locks 3.9 via
nixpacks.toml") and the Tech Stack table ("Backend | Python 3.9 / FastAPI →
Railway") are stale as of 2026-06-12 and need correction.** This file
cannot make that correction itself (governed doc, `Edit`/`Write` denied by
`guard_pretooluse.py`) — flagging here for Alex/terminal to action. Local
system `python3` is 3.9.6 (`/usr/bin/python3`); this is NOT what Railway
actually runs. Per the packet's instruction, and because the entire point
of this task is proving the pin matches what actually runs in production,
the clean venv for this task was built with `/opt/homebrew/bin/python3.12`
(Homebrew, confirmed present, version 3.12.13), not the system `python3`.

## Real finding: the da27fe4 historical bug does NOT reproduce on this pinned stack

Independently verified 2026-08-15, in response to the planner-reviewer's
first-round finding (which was reproduced here from scratch, not taken on
trust): the real pre-`da27fe4` source
(`git show da27fe4^:backend/app/auth.py`) was loaded as a `sys.modules`
override — never written to the tracked `backend/app/auth.py`, which is
outside this task's writable allowlist — and mounted against the real
`app.routers.admin` router, in the same pinned venv used for every other
check in this doc (pydantic 2.13.4 / starlette 0.52.1 / fastapi 0.128.8 /
Python 3.12.13). Result:

```
=== PRE-FIX shape (da27fe4^) ===
  /admin/sources -> 401 {'detail': 'Authentication required'}
  /admin/stats   -> 401 {'detail': 'Authentication required'}
  _RequireRole.__call__ signature: (self, request: 'Request') -> 'str'
  'request' in parameters: True
=== CURRENT shape (tracked backend/app/auth.py) ===
  /admin/sources -> 401 {'detail': 'Authentication required'}
  /admin/stats   -> 401 {'detail': 'Authentication required'}
  _RequireRole.__call__ signature: (self, user_id: 'Optional[str]' = Depends(dependency=<function get_optional_user at 0x...>, use_cache=True, scope=None)) -> 'str'
  'request' in parameters: False
```

**Both the pre-fix and the current shape return 401, not 422, for a
no-token request on this pinned stack.** The historical `da27fe4` failure
mode (every admin/contributor-gated request 422'ing with "field required:
query.request" before `_RequireRole`'s own auth logic ever ran) does not
reproduce here at all — something about the newly-pinned pydantic/starlette
combination resolves the bound method's `Request`-typed parameter
correctly even in the pre-fix shape, unlike whatever combination was live
when `da27fe4` was originally diagnosed. This is directly relevant to F2's
"production-relevant versions... are deterministic" criterion: it is a real,
disclosed fact about this specific version combination, not buried.

**Consequence for what actually guards against regression:** an HTTP
status-code check alone (401 vs. 422) CANNOT distinguish the buggy shape
from the fixed shape on this pinned stack — both give 401. Protection
against reintroducing the bug's root cause therefore rests on the new
structural signature check in `scripts/test_admin_auth_regression.py`
(`test_require_role_signature_excludes_request_param`), not on the HTTP
status code — see "New file" section below for the check itself and its
own independent discrimination proof.

## Verification commands (all run via the mandatory CLI)

All three run via
`PYTHONPATH=scripts python3 -m harness_coordinator.v1.verification_commands`
from the primary checkout (`/Users/alexwhitley/rhemata`, where `scripts/`
lives), each with `--cwd /Users/alexwhitley/rhemata/.worktrees/claude-o5-deps-pin`.
The CLI's own contract only surfaces `stdout_sha256`/`stderr_sha256`
(a deliberate integrity-attestation design per the module's own docstring,
not raw text) — full JSON results below. Where real console output is also
included for readability, it is captured verbatim from an adjacent,
untimed run of the exact identical command (same script, same venv,
run immediately before/after the timed CLI invocation) — it is NOT
asserted to be byte-identical to the specific bytes the CLI hashed, since
`unittest`'s own summary line embeds wall-clock duration ("Ran N tests in
X.XXXs") that varies slightly run to run by definition; the CLI JSON's
`exit_code`/`outcome` is the authoritative pass/fail record in every case.

Preconditions: `.venv-clean` was deleted and rebuilt from scratch
(`/opt/homebrew/bin/python3.12 -m venv .venv-clean`) immediately before the
final `install-clean` run below, so it is a true from-scratch install
against the pinned `backend/requirements.txt`. All three commands below
were run in sequence against that same single fresh venv.

### 1. `install-clean` (timeout_seconds=480)

Command: `.venv-clean/bin/python -m pip install -r backend/requirements.txt`

```json
{"argv": [".venv-clean/bin/python", "-m", "pip", "install", "-r", "backend/requirements.txt"], "command_id": "install-clean", "cwd": "/Users/alexwhitley/rhemata/.worktrees/claude-o5-deps-pin", "exit_code": 0, "outcome": "PASSED", "stderr_sha256": "e5d49979d5c44ecfb1079e49a5e2b758f5f2f3a0c5b9f93bb077be2e47a0b559", "stdout_sha256": "72e9c17b32eeb6db94eddf4c5fefb2885ccfa43348f973d75fe6a16077818f10", "timestamps": {"finished_at": "2026-08-15T01:40:38Z", "started_at": "2026-08-15T01:40:25Z"}}
```

Result: **PASSED**, exit 0, ~13s wall time (well under the 480s declared
timeout). Both the hashes above match byte-for-byte the earlier
first-draft run of the identical command against an independently
recreated clean venv — a from-scratch install is deterministic here.
Post-install spot checks (both run directly, not through the timed CLI —
informational only): `pip show pydantic starlette` reports `Version:
2.13.4` / `Version: 0.52.1` exactly matching the new pins; `pip check`
reports "No broken requirements found."

### 2. `import-sanity` (timeout_seconds=60)

Command: `.venv-clean/bin/python -c "..."` — sets dummy
`SUPABASE_JWT_JWKS_URL`/`SUPABASE_URL` (via `setdefault`, so a real
`backend/app/.env` would still win if present — this worktree has none),
adds `backend/` to `sys.path`, then `from app.auth import get_optional_user;
from app.routers import admin`.

```json
{"argv": [".venv-clean/bin/python", "-c", "import os, sys; os.environ.setdefault('SUPABASE_JWT_JWKS_URL', 'https://example.invalid/jwks'); os.environ.setdefault('SUPABASE_URL', 'https://example.invalid'); sys.path.insert(0, 'backend'); from app.auth import get_optional_user; from app.routers import admin; print('import-sanity: OK')"], "command_id": "import-sanity", "cwd": "/Users/alexwhitley/rhemata/.worktrees/claude-o5-deps-pin", "exit_code": 0, "outcome": "PASSED", "stderr_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "stdout_sha256": "36f82a42f73fe31117063b3d8832953c91f57d53d4601a460e641ed336958bd9", "timestamps": {"finished_at": "2026-08-15T01:40:49Z", "started_at": "2026-08-15T01:40:46Z"}}
```

Result: **PASSED**, exit 0. Prints `import-sanity: OK`.

Why a router-level import, not `app.main`: importing `app.main` mounts
every router (search, document, ingest, ingest_queue, study, admin,
feedback, library, pastors_notes, usage, account, quotes, answer_quotes,
async_chat), several of which have their own module-level requirements
beyond what a dummy JWKS/Supabase URL satisfies. `backend/app/routers/admin.py`
imports only `app.auth`, `app.db.supabase` (whose `get_supabase()` is
lazy — called inside route handlers, never at import time),
`app.services.chunker` (module-level `tiktoken.get_encoding("cl100k_base")`
— network-free if already locally cached, which it is on this machine; no
stall observed), and `app.services.embeddings` (`OpenAI` client
construction is lazy, inside `_get_client()`). `jwt.PyJWKClient.__init__`
does not make a network call at construction — only
`get_signing_key_from_jwt` does, which this test never reaches — so the
dummy JWKS URL never needs to resolve to anything real.

### 3. `admin-auth-regression` (timeout_seconds=120)

Command: `.venv-clean/bin/python scripts/test_admin_auth_regression.py`

```json
{"argv": [".venv-clean/bin/python", "scripts/test_admin_auth_regression.py"], "command_id": "admin-auth-regression", "cwd": "/Users/alexwhitley/rhemata/.worktrees/claude-o5-deps-pin", "exit_code": 0, "outcome": "PASSED", "stderr_sha256": "e19e86343fe7ad5cbfcc1f5c6855458cc698e8fdefa4d66f13c567b4230c5d00", "stdout_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", "timestamps": {"finished_at": "2026-08-15T01:41:00Z", "started_at": "2026-08-15T01:40:59Z"}}
```

Result: **PASSED**, exit 0. Real, verbatim console output from an adjacent
untimed run of the identical command (immediately preceding the timed CLI
run above, same venv, same script — `unittest` writes its summary to
stderr by default, matching the empty-string `stdout_sha256` above,
`e3b0c44...`, the well-known SHA-256 of the empty byte string):

```
...
----------------------------------------------------------------------
Ran 3 tests in 0.021s

OK
```

(Three dots, one per test method, `unittest`'s default verbosity-1 output
— the script defines exactly three test methods: see "New file" below.
Wall-clock duration will differ trivially run to run; that is why this
block's bytes are not asserted to be identical to the specific bytes the
CLI hashed above, per the note at the top of this section.)

## New file: `scripts/test_admin_auth_regression.py`

Follows `scripts/test_async_serving_gate.py`'s convention: standalone
`unittest`-based script (not pytest), in-process `fastapi.testclient.TestClient`
against a minimal `FastAPI()` app that mounts only the router under test
(here, `backend/app/routers/admin.py`), no live server, no live Supabase.

**Three test methods**, not two (a second one was added in this revision):

1. **`test_require_role_signature_excludes_request_param` — the actual,
   durable regression guard for `da27fe4`.** A structural check using
   `inspect.signature(_RequireRole.__call__)`, asserting `'request' not in
   sig.parameters`. This is the real distinguishing fact between the
   pre-fix and fixed shapes (see the "Real finding" section above): the
   buggy `__call__(self, request: Request)` has a `request` parameter, the
   fixed `__call__(self, user_id: Optional[str] = Depends(get_optional_user))`
   does not. Unlike the HTTP-level checks below, this distinguishes the two
   shapes unconditionally, regardless of which pydantic/starlette/fastapi
   versions happen to be pinned when it runs.

   **Independently proven discriminating, not just asserted to be:** the
   real `da27fe4^` source was loaded (again via a `sys.modules` override,
   never touching the tracked file) and the exact same assertion used
   inside this test was run against it directly. It failed exactly as
   expected:

   ```
   === Structural check against PRE-FIX shape (da27fe4^) ===
   pre-fix: ASSERTION FAILED (as expected if pre-fix) -- _RequireRole.__call__ has reverted to taking a direct `request` parameter -- this is the exact da27fe4 shape. -- sig=(self, request: 'Request') -> 'str'

   === Structural check against CURRENT tracked auth.py ===
   current: ASSERTION PASSED (no 'request' param) -- sig=(self, user_id: 'Optional[str]' = Depends(dependency=<function get_optional_user at 0x1008d09a0>, use_cache=True, scope=None)) -> 'str'

   PROOF SUMMARY
     pre-fix shape  -> assertion passed: False  (expected False)
     current shape  -> assertion passed: True  (expected True)

   CONFIRMED: the structural check is genuinely discriminating.
   ```

2. **`test_no_token_returns_401_not_422` — smoke test only, NOT proof of
   the `da27fe4` shape being fenced.** Sets dummy `SUPABASE_JWT_JWKS_URL`/
   `SUPABASE_URL` (`setdefault`, so a real `backend/app/.env` would still
   win if present), hits `GET /admin/sources` with no Authorization header,
   asserts 401 with `{"detail": "Authentication required"}`. Confirms the
   route is reachable and correctly gated — a real, useful thing to check —
   but per the "Real finding" section above, this assertion passes
   identically whether `_RequireRole.__call__` has the buggy or fixed
   shape, on this pinned stack. The docstring and the module-level
   docstring both say this explicitly now; the original first-draft
   version of this file and this doc both overclaimed that this check
   "proves" the fix — corrected.

3. **`test_no_token_never_422s_across_multiple_admin_routes` — same
   smoke-test caveat, exercised against a second, independently-defined
   admin route (`GET /admin/stats`, a different function object, same
   `require_admin_role` dependency) to rule out a single-route fluke in
   the reachability/gating check specifically, not the `da27fe4` shape.

Per the packet's explicit scoping (both original and unchanged by this
revision): the 403 wrong-role path is deliberately NOT covered — reaching
it requires a live `get_user_role()` Supabase call (`_RequireRole.__call__`
raises 401 out of `get_optional_user` returning `None` before that call is
ever made on the no-token path this script exercises).

## Scope note — other `scripts/test_*.py` files

Per the packet's explicit instruction, no other `scripts/test_*.py` file
was run this session — most require live Supabase/API credentials or
exercise corpus-track/ingestion paths, out of scope for this
structurally-DB-free task. If broader coverage is wanted later: a
`scripts/test_*` run that exercises the 403 wrong-role branch (would need a
live or mocked `get_user_role()`/Supabase call — a bigger, deliberately
out-of-scope change here) would close the one gap named above.

## Human-stop check

Nothing broke. The pin did not require loosening any test, deleting
anything, or picking a different version to force green — `pip show`
matched exactly what the unpinned resolution already produced, `pip check`
reports no conflicts, and all three tests pass clean on the pinned,
from-scratch venv, including the newly added structural check that was
independently proven (not just asserted) to catch the historical bug shape
if reintroduced. The one genuinely surprising finding — the historical
422 does not reproduce on this pinned stack via HTTP status code alone —
is disclosed plainly above, not buried; it changes what the durable
regression guard actually is (the structural check, not the status code),
but does not change the correctness of the pin itself. Not a
`HUMAN_REQUIRED` case.
