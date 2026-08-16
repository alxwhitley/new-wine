# Source Ingest Queue Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a durable, secure worker that processes one cleared,
single-PDF, declared-author queue row through the canonical shared writer with
leases, retries, dry-run proof, original-text retention, and exact
reconciliation.

**Architecture:** Extend `source_ingest_queue` with durable execution state,
then add focused fetch, PDF, processor, lifecycle, and worker modules. The
worker performs all untrusted-input validation before calling
`shared_ingest.ingest_document()` exactly once; the existing answer worker and
FastAPI request path remain unchanged.

**Tech Stack:** Python 3.9, PostgreSQL/psycopg2, Supabase service client,
FastAPI/Pydantic, Python standard-library HTTP/TLS/IP primitives, existing
PyPDF/Groq/OpenAI ingestion helpers.

**Spec:**
`docs/superpowers/specs/2026-08-15-source-ingest-queue-runner-design.md`

## Global Constraints

- Python 3.9 is the compatibility floor; use `Optional[...]` where needed.
- Add no dependency and do not change either existing Nixpacks configuration.
- Support only `pdf + single + declared` in this slice.
- Retain complete extracted source text in `documents.full_text` on success.
- Never create a source/alias, use the sentinel, mutate visibility/license/safe
  mode, or bypass `shared_ingest.ingest_document()`.
- Never log source text, response bodies, credentials, URL query, or fragment.
- Repository implementation uses fake network/provider/database boundaries.
- Do not apply migration 088, fetch a live URL, call a live provider, write the
  production database, create a Railway service, or deploy during this plan.
- Build commits and records commits remain separate; leave
  `Temporary-assets/` untouched.

## File Map

- `migrations/088_source_ingest_runner.sql` — durable queue fields,
  constraints, indexes, retention policy, and rollback notes.
- `scripts/source_ingest_queue/fetcher.py` — SSRF-safe, IP-pinned bounded PDF
  fetch with redirect validation.
- `scripts/source_ingest_queue/pdf.py` — child-process PDF extraction and
  page/text/deadline bounds.
- `scripts/source_ingest_queue/processor.py` — row classification, read-only
  preparation, metadata override, and sole shared-writer call.
- `scripts/source_ingest_queue/jobs.py` — atomic claims, ownership, leases,
  retries, terminal transitions, and reconciliation.
- `scripts/source_ingest_worker.py` — CLI, polling loop, heartbeat, and outcome
  routing.
- `scripts/apply_migration_088.py` — explicit-flag migration application,
  retention snapshot, fresh-connection checks, and real claim proof for a
  separately approved production session.
- `backend/app/routers/ingest_queue.py` — explicitly persist the fixed
  retention policy when rows are created.
- `scripts/test_source_ingest_*.py` — deterministic regressions for each
  boundary.

---

### Task 1: Add the inert migration contract

**Files:**
- Create: `migrations/088_source_ingest_runner.sql`
- Create: `scripts/test_source_ingest_migration.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: migration 075’s `source_ingest_queue` columns and statuses.
- Produces: the exact columns/indexes/constraints consumed by
  `source_ingest_queue.jobs` in Task 5.

- [ ] **Step 1: Write the failing structural regression**

Create `scripts/test_source_ingest_migration.py` with a `main()` that reads
the migration and asserts all of the following literal contracts:

```python
required = {
    "attempts integer NOT NULL DEFAULT 0",
    "max_attempts integer NOT NULL DEFAULT 3",
    "worker_id text",
    "lease_expires_at timestamptz",
    "run_after timestamptz NOT NULL DEFAULT now()",
    "stage text NOT NULL DEFAULT 'queued'",
    "final_url text",
    "content_sha256 text",
    "fetched_bytes bigint",
    "attempted_documents integer NOT NULL DEFAULT 0",
    "stored_documents integer NOT NULL DEFAULT 0",
    "skipped_documents integer NOT NULL DEFAULT 0",
    "errored_documents integer NOT NULL DEFAULT 0",
    "result_document_id uuid REFERENCES documents(id) ON DELETE SET NULL",
    "source_ingest_queue_claim_idx",
    "source_ingest_queue_lease_idx",
    "CHECK (retain_original_text = true)",
}
missing = sorted(fragment for fragment in required if fragment not in sql)
assert not missing, "missing migration contracts: %r" % missing
assert "UPDATE source_ingest_queue SET retain_original_text = true" in sql
assert "ALTER COLUMN retain_original_text SET NOT NULL" in sql
```

Also assert the file contains rollback instructions that drop the two indexes,
drop every new column, remove the retention constraint/default/NOT NULL, and
state that prior retention values must be restored from the apply-script
snapshot before rollback completes.

- [ ] **Step 2: Run the regression and confirm the red baseline**

Run:

```bash
python3 scripts/test_source_ingest_migration.py
```

Expected: failure because `migrations/088_source_ingest_runner.sql` does not
exist.

- [ ] **Step 3: Write migration 088**

Use one idempotent migration with these operations:

```sql
UPDATE source_ingest_queue SET retain_original_text = true
WHERE retain_original_text IS DISTINCT FROM true;

ALTER TABLE source_ingest_queue
  ALTER COLUMN retain_original_text SET DEFAULT true,
  ALTER COLUMN retain_original_text SET NOT NULL,
  ADD CONSTRAINT source_ingest_queue_retain_original_text_true
    CHECK (retain_original_text = true),
  ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3,
  ADD COLUMN IF NOT EXISTS worker_id text,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS run_after timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS stage text NOT NULL DEFAULT 'queued',
  ADD COLUMN IF NOT EXISTS final_url text,
  ADD COLUMN IF NOT EXISTS content_sha256 text,
  ADD COLUMN IF NOT EXISTS fetched_bytes bigint,
  ADD COLUMN IF NOT EXISTS attempted_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS stored_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS skipped_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS errored_documents integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS result_document_id uuid
    REFERENCES documents(id) ON DELETE SET NULL;

ALTER TABLE source_ingest_queue
  ADD CONSTRAINT source_ingest_queue_attempts_nonnegative CHECK (attempts >= 0),
  ADD CONSTRAINT source_ingest_queue_max_attempts_positive CHECK (max_attempts > 0),
  ADD CONSTRAINT source_ingest_queue_counts_nonnegative CHECK (
    attempted_documents >= 0 AND stored_documents >= 0
    AND skipped_documents >= 0 AND errored_documents >= 0
  );

CREATE INDEX IF NOT EXISTS source_ingest_queue_claim_idx
  ON source_ingest_queue (run_after, created_at)
  WHERE status = 'waiting' AND cleared_to_run = true;

CREATE INDEX IF NOT EXISTS source_ingest_queue_lease_idx
  ON source_ingest_queue (lease_expires_at)
  WHERE status = 'running';
```

Guard named constraint creation with `DO $$ ... IF NOT EXISTS ... $$` so a
re-run is idempotent. Include exact non-destructive rollback instructions in
SQL comments.

Add `source_ingest_runner_review/` to `.gitignore`; this is where the apply
script will later write pre-backfill snapshots.

- [ ] **Step 4: Run the migration regression**

Run:

```bash
python3 scripts/test_source_ingest_migration.py
git diff --check
```

Expected: all migration contract assertions pass and no whitespace errors.

- [ ] **Step 5: Commit the migration contract**

```bash
git add .gitignore migrations/088_source_ingest_runner.sql \
  scripts/test_source_ingest_migration.py
git commit -m "feat: define source ingest runner state"
```

### Task 2: Build the secure pinned-address PDF fetcher

**Files:**
- Create: `scripts/source_ingest_queue/__init__.py`
- Create: `scripts/source_ingest_queue/fetcher.py`
- Create: `scripts/test_source_ingest_fetcher.py`

**Interfaces:**
- Consumes: one queue URL string.
- Produces: `FetchResult`, `FetchRejected`, `FetchTransient`,
  `resolve_public_addresses()`, and `fetch_pdf()` for Task 4.

- [ ] **Step 1: Write failing URL/address tests**

Test these exact public functions with injected resolver and connection
factory:

```python
from source_ingest_queue.fetcher import (
    FetchRejected, FetchResult, FetchTransient,
    fetch_pdf, resolve_public_addresses,
)

assert resolve_public_addresses(
    "example.com", 443,
    getaddrinfo=lambda *args, **kwargs: [
        (2, 1, 6, "", ("93.184.216.34", 443)),
    ],
) == ("93.184.216.34",)

for unsafe in ("127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "fc00::1"):
    try:
        resolve_public_addresses(
            "blocked.test", 443,
            getaddrinfo=lambda *args, _ip=unsafe, **kwargs: [
                (2, 1, 6, "", (_ip, 443)),
            ],
        )
        raise AssertionError("unsafe address accepted: %s" % unsafe)
    except FetchRejected as exc:
        assert exc.code == "unsafe_url"
```

Add cases for mixed public/private answers, embedded credentials, unsupported
scheme, missing host, and explicit URL fragments.

- [ ] **Step 2: Run the address tests and confirm they fail**

Run:

```bash
PYTHONPATH=scripts python3 scripts/test_source_ingest_fetcher.py
```

Expected: import failure because `source_ingest_queue.fetcher` is absent.

- [ ] **Step 3: Implement address validation and error types**

Define immutable output and bounded errors:

```python
@dataclass(frozen=True)
class FetchResult:
    content: bytes
    final_url: str
    sha256: str
    byte_count: int
    filename: str

class FetchRejected(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail[:240]
        super().__init__("%s: %s" % (code, self.detail))

class FetchTransient(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail[:240]
        super().__init__("%s: %s" % (code, self.detail))
```

`resolve_public_addresses()` must deduplicate every `getaddrinfo()` result,
parse it with `ipaddress.ip_address()`, and reject the whole hostname if any
answer is not `is_global`.

- [ ] **Step 4: Write failing fetch/redirect/bounds tests**

Use fake connections/responses to assert:

- the connection factory receives both original hostname and validated IP;
- HTTPS SNI/host identity remains the hostname while the socket target is IP;
- each redirect invokes the resolver again;
- HTTPS-to-HTTP redirect, fourth redirect, and loop are `unsafe_url`;
- non-PDF MIME is `not_pdf`;
- declared or streamed size over `50 * 1024 * 1024` is `pdf_too_large`;
- 500/502/503/504 are `http_5xx` transient errors;
- connect/read timeout codes are distinct;
- the result SHA-256, byte count, final URL, and sanitized filename are exact;
- query and fragment never appear in a value passed to the injected log hook.

- [ ] **Step 5: Implement the pinned fetch loop**

Implement `fetch_pdf()` with these defaults:

```python
def fetch_pdf(
    url: str,
    *,
    resolver=resolve_public_addresses,
    connection_factory=_open_pinned_connection,
    timeout_seconds: float = 30.0,
    max_bytes: int = 50 * 1024 * 1024,
    max_redirects: int = 3,
) -> FetchResult:
```

For each hop: parse and validate URL, resolve all addresses, open a connection
pinned to one validated address, request only the path/query, read in 64 KiB
chunks with a hard cumulative ceiling, close in `finally`, and revalidate any
`Location` using `urljoin`. `_open_pinned_connection()` must override the
connection’s socket creator so TCP targets the validated IP while
`HTTPSConnection` retains the original host for TLS verification and SNI.

- [ ] **Step 6: Run fetcher tests and mutation probes**

Run the green test, then temporarily neutralize (one at a time) the unsafe-IP
rejection and streamed-size increment. Each mutation must fail its targeted
case; restore both and rerun green.

```bash
PYTHONPATH=scripts python3 scripts/test_source_ingest_fetcher.py
```

- [ ] **Step 7: Commit the fetch boundary**

```bash
git add scripts/source_ingest_queue/__init__.py \
  scripts/source_ingest_queue/fetcher.py scripts/test_source_ingest_fetcher.py
git commit -m "feat: add bounded source PDF fetcher"
```

### Task 3: Isolate and bound PDF extraction

**Files:**
- Create: `scripts/source_ingest_queue/pdf.py`
- Create: `scripts/test_source_ingest_pdf.py`

**Interfaces:**
- Consumes: PDF bytes from `FetchResult.content`.
- Produces: `ExtractedPdf`, `PdfRejected`, and `extract_pdf_bounded()` for
  Task 4.

- [ ] **Step 1: Write failing validation tests**

Define fixtures through injected child results rather than real files. Assert
the following interface:

```python
result = extract_pdf_bounded(
    b"pdf",
    timeout_seconds=1.0,
    runner=lambda content, deadline: ("Body text", 12),
)
assert result.text == "Body text"
assert result.page_count == 12
```

Add cases for zero/blank text (`pdf_empty`), page count 2,001
(`pdf_page_limit`), text length 10,000,001 (`pdf_text_limit`), child timeout
(`pdf_extract_timeout`), and child parser exception (`pdf_parse_failure`).

- [ ] **Step 2: Run the tests and confirm the missing-module failure**

```bash
PYTHONPATH=scripts python3 scripts/test_source_ingest_pdf.py
```

- [ ] **Step 3: Implement bounded extraction**

Define:

```python
@dataclass(frozen=True)
class ExtractedPdf:
    text: str
    page_count: int

class PdfRejected(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail[:240]
        super().__init__("%s: %s" % (code, self.detail))

def extract_pdf_bounded(
    content: bytes,
    *,
    timeout_seconds: float = 60.0,
    max_pages: int = 2000,
    max_chars: int = 10_000_000,
    runner=_run_extractor_child,
) -> ExtractedPdf:
```

The default runner uses `multiprocessing.get_context("spawn")` and a one-way
pipe. In the child, instantiate `pypdf.PdfReader` once, reject the page count
before extraction, then concatenate page text with the same semantics as
`app.services.extractor.extract_text_from_pdf()`. The parent terminates and
joins the child on deadline, accepts only a bounded `(ok, text, page_count)`
payload, and never exposes raw parser output as an operator-facing detail.

- [ ] **Step 4: Prove time/page/text guards are discriminating**

Run green, temporarily raise the page limit and remove the text-length check,
confirm the corresponding cases fail, restore, and rerun:

```bash
PYTHONPATH=scripts python3 scripts/test_source_ingest_pdf.py
```

- [ ] **Step 5: Commit PDF isolation**

```bash
git add scripts/source_ingest_queue/pdf.py scripts/test_source_ingest_pdf.py
git commit -m "feat: bound queued PDF extraction"
```

### Task 4: Build read-only preparation and sole-writer execution

**Files:**
- Create: `scripts/source_ingest_queue/processor.py`
- Create: `scripts/test_source_ingest_processor.py`

**Interfaces:**
- Consumes: `FetchResult`, `ExtractedPdf`, queue row, Supabase client, direct
  DB parameters, and injected existing helpers.
- Produces: `PreparedIngest`, `ProcessOutcome`, `AttentionRequired`,
  `RetryableIngestError`, `prepare_ingest()`, and `execute_ingest()` for Task 6.

- [ ] **Step 1: Write failing row-classification tests**

Use this exact pure contract:

```python
assert classify_row({
    "source_format": "pdf",
    "source_scope": "single",
    "attribution_mode": "declared",
    "attribute_to": "Derek Prince",
    "retain_original_text": True,
}) is None
assert classify_row({"source_format": "web_page"}) == "unsupported_source_format"
```

Add one case for each unsupported shape, false/missing retention, and blank
declared author.

- [ ] **Step 2: Run the processor test and confirm red**

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_processor.py
```

- [ ] **Step 3: Implement types, classification, and preparation**

Define `AttentionRequired` and `RetryableIngestError` with bounded `code` and
`detail`, plus immutable dataclasses matching the spec. Implement:

```python
def prepare_ingest(
    row: dict,
    *,
    db,
    db_params: dict,
    dry_run: bool,
    fetch_fn=fetch_pdf,
    extract_fn=extract_pdf_bounded,
    resolve_fn=resolve_source_id,
    servable_fn=is_source_servable,
    dedup_fn=shared_ingest.already_ingested,
    metadata_fn=extract_metadata,
) -> PreparedIngest:
```

The exact order is: classify row → fetch → extract → resolve declared author
→ reject sentinel/MISS → canonical servability check → chunk/count → read-only
dedup check → return immediately for `dry_run` → metadata call for normal mode
→ overwrite metadata author/source name with declared author. Map fetch/PDF
policy errors to `AttentionRequired` and provider/network transient errors to
`RetryableIngestError`.

- [ ] **Step 4: Add preparation tests**

Assert unsupported rows call neither fetch nor writer; sentinel and
non-servable sources stop before dedup/write; dry-run calls no metadata,
embedding, proposition, or writer function; declared author wins over a fake
metadata author; and chunk count/hash/byte count remain exact.

- [ ] **Step 5: Implement and test the sole writer call**

Define:

```python
@dataclass(frozen=True)
class ProcessOutcome:
    status: str
    reason: str
    document_id: Optional[str]
    attempted: int
    stored: int
    skipped: int
    errored: int

def execute_ingest(
    prepared: PreparedIngest,
    *,
    db,
    db_params: dict,
    writer_fn=shared_ingest.ingest_document,
) -> ProcessOutcome:
```

Pass `body_text` byte-for-byte as `body_text`, set `allow_sentinel=False`, use
the pre-resolved `source_id`, and preserve URL/hash metadata outside corpus
content. Map shared writer `processed`, `skipped`, and `failed` to `(1,1,0,0)`,
`(1,0,1,0)`, and `(1,0,0,1)` respectively. Raise on any non-reconciling shape.

- [ ] **Step 6: Run processor tests and mutation proof**

Temporarily change `allow_sentinel=False` to true and author override to the
model value. Each targeted test must fail; restore and rerun:

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_processor.py
```

- [ ] **Step 7: Commit processor behavior**

```bash
git add scripts/source_ingest_queue/processor.py \
  scripts/test_source_ingest_processor.py
git commit -m "feat: prepare queued sources for shared ingest"
```

### Task 5: Add durable queue lifecycle operations

**Files:**
- Create: `scripts/source_ingest_queue/jobs.py`
- Create: `scripts/test_source_ingest_jobs.py`

**Interfaces:**
- Consumes: migration 088 columns and `Db.run()` transactional callback API.
- Produces: `get_row()`, `claim_next()`, `heartbeat()`, `set_stage()`,
  `needs_attention()`, `fail_or_requeue()`, `complete()`, and
  `reap_expired_leases()` for Task 6.

- [ ] **Step 1: Write failing SQL-contract tests**

Use a recording fake `Db`/cursor and assert claim SQL contains all of:

```python
required_claim_sql = (
    "status = 'waiting'",
    "cleared_to_run = true",
    "run_after <= now()",
    "FOR UPDATE SKIP LOCKED",
    "LIMIT 1",
    "RETURNING *",
)
```

Assert ownership-sensitive SQL contains `id = %s`, `worker_id = %s`, and
`status = 'running'`. Add pure reconciliation cases accepting only zero-attempt
attention or `attempted == stored + skipped + errored`.

- [ ] **Step 2: Run jobs tests and confirm red**

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_jobs.py
```

- [ ] **Step 3: Implement claim, read, stage, and heartbeat**

Follow the answer-job pattern but keep this module independent. Claim must call
`reap_expired_leases()`, then execute one parameterized
`UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`.
Heartbeat and stage updates return `False` when no owned running row was
updated.

- [ ] **Step 4: Implement terminal and retry transitions**

`needs_attention()` clears ownership/lease and writes bounded
`flag_reason="<code>: <detail>"`. `fail_or_requeue()` increments attempts and
uses backoff `min(300, 2 ** attempts * 5)` seconds; it returns `waiting` until
the next attempt reaches `max_attempts`, then `failed` with
`errored_documents=1` when a corpus attempt occurred. `complete()` validates
reconciliation before issuing SQL and stores final URL/hash/bytes/document ID.

Lease reaping uses the same attempt rule and never claims or completes work in
the same transaction.

- [ ] **Step 5: Run tests and mutate ownership/reconciliation guards**

Disable the `worker_id` SQL predicate and the reconciliation equality one at a
time; targeted cases must fail. Restore and rerun:

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_jobs.py
```

- [ ] **Step 6: Commit durable lifecycle behavior**

```bash
git add scripts/source_ingest_queue/jobs.py scripts/test_source_ingest_jobs.py
git commit -m "feat: add source ingest job lifecycle"
```

## Checkpoint 1: Foundations

- [ ] Tasks 1–5 each have a green focused test and atomic commit.
- [ ] Fetcher and processor mutation probes fail when their safety control is
  disabled and pass after restoration.
- [ ] Migration 088 remains unapplied.
- [ ] No live URL, provider, or production write occurred.
- [ ] `git status --short` shows only known unrelated user files.

### Task 6: Integrate the worker and fixed retention API

**Files:**
- Create: `scripts/source_ingest_worker.py`
- Create: `scripts/test_source_ingest_worker.py`
- Create: `scripts/test_source_ingest_queue_retention.py`
- Modify: `backend/app/routers/ingest_queue.py`

**Interfaces:**
- Consumes: Task 4 processor functions, Task 5 job transitions,
  `app.services.async_answers.db.Db`, `get_supabase()`, and environment DB URL.
- Produces: `Worker.tick()`, `Worker.run()`, `--once`, `--max-idle`,
  `--poll-interval`, and read-only `--dry-run-row`.

- [ ] **Step 1: Write failing router retention test**

Call `create_queue_row()` with a fake Supabase client and assert the
`source_ingest_queue` insert contains:

```python
assert inserted_row["retain_original_text"] is True
```

Also assert domain-memory behavior and existing response shape remain intact.

- [ ] **Step 2: Persist the fixed retention policy**

Add exactly one field to the existing insert dictionary:

```python
"retain_original_text": True,
```

Run:

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_queue_retention.py
```

- [ ] **Step 3: Write failing worker tick tests**

With fake jobs/processor dependencies, prove:

- no claim returns `False` without processor calls;
- success performs claim → stage updates → complete;
- `AttentionRequired` calls `needs_attention` and does not retry;
- `RetryableIngestError` and unknown exceptions call `fail_or_requeue`;
- ownership loss prevents stale completion;
- one processor fault does not terminate the polling loop;
- `--dry-run-row` calls only `get_row()` and `prepare_ingest(dry_run=True)`.

- [ ] **Step 4: Implement worker orchestration**

Use constructor injection so tests need no environment:

```python
class Worker:
    def __init__(
        self,
        *,
        db_factory=Db,
        supabase_factory=get_supabase,
        prepare_fn=prepare_ingest,
        execute_fn=execute_ingest,
        poll_interval: float = 2.0,
        once: bool = False,
        max_idle: Optional[float] = None,
        worker_id: Optional[str] = None,
    ):
```

Default concurrency is one. Start a heartbeat helper with its own `Db` while a
row is processed; stop/join it before any terminal transition. Parse
`SUPABASE_DB_URL` locally into the dictionary required by `shared_ingest`.
Sanitize logs to row/worker ID, hostname/path without query, stage, reason code,
durations, and counts.

- [ ] **Step 5: Implement CLI modes**

Normal mode supports:

```bash
python3 scripts/source_ingest_worker.py --once
python3 scripts/source_ingest_worker.py --poll-interval 2 --max-idle 30
```

`--dry-run-row UUID` opens read-only job/Supabase access, never claims or
transitions the row, and prints only source identity, final URL without query,
hash, bytes, page/chunk counts, resolved source ID, and duplicate classification.

- [ ] **Step 6: Run worker, router, and existing endpoint regressions**

```bash
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_worker.py
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_queue_retention.py
python3 scripts/test_async_serving_gate.py
```

Expected: all pass without network/provider/database access.

- [ ] **Step 7: Commit worker integration**

```bash
git add backend/app/routers/ingest_queue.py scripts/source_ingest_worker.py \
  scripts/test_source_ingest_worker.py \
  scripts/test_source_ingest_queue_retention.py
git commit -m "feat: run cleared source ingest jobs"
```

### Task 7: Prepare the explicitly gated migration apply verifier

**Files:**
- Create: `scripts/apply_migration_088.py`
- Create: `scripts/test_apply_migration_088.py`

**Interfaces:**
- Consumes: migration 088, Task 5 claim SQL, `SUPABASE_DB_URL`, and the
  gitignored `source_ingest_runner_review/` directory.
- Produces: a script that does nothing without `--apply`, snapshots retention
  values before mutation, applies once, verifies fresh connections, and emits
  hard reconciliation for the separately approved production session.

- [ ] **Step 1: Write failing safety and snapshot tests**

Import the script module with fake connections and assert:

- argument parsing without `--apply` exits before `get_db_conn()`;
- `_snapshot_rows()` preserves UUID plus true/false/null exactly;
- `_write_snapshot()` uses a caller-provided path under
  `source_ingest_runner_review/` and writes no secrets;
- `_restore_retention_values()` uses parameterized updates;
- validation rejects an empty/outside-root snapshot path;
- cleanup targets only the generated verification fixture UUID.

- [ ] **Step 2: Run apply-script tests and confirm red**

```bash
PYTHONPATH=backend:scripts python3 scripts/test_apply_migration_088.py
```

- [ ] **Step 3: Implement explicit apply and fresh verification**

`main()` must require `--apply`, open a fresh preflight connection, snapshot
`SELECT id, retain_original_text FROM source_ingest_queue ORDER BY id`, write
the JSON artifact with mode `0600`, apply the migration in one transaction,
close it, and verify on a fresh connection:

- all columns/types/defaults/nullability;
- named retention/count constraints;
- claim and lease indexes;
- RLS remains enabled and existing policies remain present;
- current queue count is unchanged;
- every retention value is true after migration.

- [ ] **Step 4: Add the real concurrent-claim verifier without running it**

During an approved apply session only, select one existing `auth.users.id`,
insert one uniquely generated uncleared test row, then set only that row
cleared. Start two connections on a barrier and call `jobs.claim_next()` with
different worker IDs. Assert exactly one receives the fixture and the other
does not. Validate the UUID and URL marker before deleting only that fixture;
if cleanup fails, stop without broadening the delete. Report attempted=1,
claimed=1, double_claimed=0, cleaned=1.

No part of repository implementation invokes `main()` or supplies `--apply`.

- [ ] **Step 5: Run deterministic apply-script tests**

```bash
PYTHONPATH=backend:scripts python3 scripts/test_apply_migration_088.py
```

- [ ] **Step 6: Commit the apply verifier**

```bash
git add scripts/apply_migration_088.py scripts/test_apply_migration_088.py
git commit -m "feat: verify source ingest runner migration"
```

## Checkpoint 2: Integrated repository build

- [ ] Tasks 6–7 have green focused tests and atomic commits.
- [ ] `--dry-run-row` is structurally read-only and tested against mutation.
- [ ] The apply script refuses to mutate without `--apply`.
- [ ] Migration 088 remains unapplied and no source-worker service exists.
- [ ] No production state, deployment, answer path, or frontend changed.

### Task 8: Run the full local gate and close records

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `CLAUDE.md`
- Modify: `PLAN.md`
- Modify: `rhemata-status.md`
- Modify: this plan’s checkboxes as evidence is completed

**Interfaces:**
- Consumes: all implementation commits and fresh command output.
- Produces: one separate records-only commit describing the built-but-unapplied
  runner and the exact next production decision.

- [ ] **Step 1: Run focused and compatibility tests**

```bash
python3 scripts/test_source_ingest_migration.py
PYTHONPATH=scripts python3 scripts/test_source_ingest_fetcher.py
PYTHONPATH=scripts python3 scripts/test_source_ingest_pdf.py
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_processor.py
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_jobs.py
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_worker.py
PYTHONPATH=backend:scripts python3 scripts/test_source_ingest_queue_retention.py
PYTHONPATH=backend:scripts python3 scripts/test_apply_migration_088.py
python3 scripts/test_nixpacks_python_parity.py
python3 scripts/test_ingest_failure_reconciliation.py
```

- [ ] **Step 2: Compile every changed Python file**

```bash
PYTHONPYCACHEPREFIX=/private/tmp/rhemata_pycache python3 -m py_compile \
  scripts/source_ingest_worker.py \
  scripts/source_ingest_queue/__init__.py \
  scripts/source_ingest_queue/fetcher.py \
  scripts/source_ingest_queue/pdf.py \
  scripts/source_ingest_queue/processor.py \
  scripts/source_ingest_queue/jobs.py \
  scripts/apply_migration_088.py \
  backend/app/routers/ingest_queue.py
```

- [ ] **Step 3: Review the build across five axes**

Review correctness, readability, architecture, security, and performance.
Required review questions:

- Can any URL validation/connect path reach a non-global address?
- Can a stale worker complete or mutate a row after ownership loss?
- Can any normal worker path write corpus state without the shared writer?
- Can any terminal attempted row fail reconciliation?
- Can dry-run call metadata/embedding/proposition providers or mutate state?
- Can logs expose URL query, document content, or credentials?
- Did any dependency, answer path, frontend, source visibility, or licensing
  behavior change?

Resolve every required finding before records close.

- [ ] **Step 4: Update governing records**

Record:

- runner code and migration prepared but migration unapplied;
- supported first-slice shape and explicit unsupported cases;
- original extracted text retention and no binary retention;
- source visibility remains separately controlled;
- security limits and failure taxonomy;
- exact test/mutation evidence;
- next step is a separately approved migration apply, read-only dry run, and
  one isolated real item before any batch or worker deployment.

- [ ] **Step 5: Verify and commit records separately**

```bash
git diff --check
git status --short
git add ARCHITECTURE.md CLAUDE.md PLAN.md rhemata-status.md \
  docs/superpowers/plans/2026-08-15-source-ingest-queue-runner.md
git diff --cached --check
git commit -m "docs: record source ingest runner build"
```

## Final Repository Checkpoint

- [ ] Every task has its red → green evidence recorded.
- [ ] Every safety-critical mutation probe failed when disabled and passed after
  restoration.
- [ ] All focused, compatibility, compile, and diff checks are green.
- [ ] Build and records commits are separate.
- [ ] `Temporary-assets/` is the only allowed unrelated untracked path.
- [ ] Migration 088 is unapplied; no live fetch/provider/DB write/deploy ran.
- [ ] The repository is ready for Alex’s separate production migration decision.
