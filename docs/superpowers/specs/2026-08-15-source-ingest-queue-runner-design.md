# Source Ingest Queue Runner Design

**Date:** 2026-08-15

**Status:** Design approved in chat; written spec awaiting review

**Scope:** First durable backend slice for one cleared, single-PDF,
declared-author queue item

## Objective

Turn the existing `source_ingest_queue` table, admin endpoints, and admin UI
from a holding area into a durable ingestion control plane. A separate worker
will claim approved queue rows, fetch and validate one PDF, prove the planned
write without mutating corpus tables, and then call
`shared_ingest.ingest_document()` as the only document writer.

Success means one eligible row can move from `waiting` to `running` to `done`,
or to a specific `needs_attention`/`failed` state, with crash recovery and
exact reconciliation. It does not mean collections, arbitrary web pages, new
source registration, or automatic rights-holder visibility changes work yet.

## Approved Product Decisions

1. The first release supports only `source_format=pdf`,
   `source_scope=single`, and `attribution_mode=declared`.
2. Every successfully ingested item retains its complete extracted original
   text in the existing `documents.full_text` column. “Original” means the
   extracted text used to build the document, not the PDF binary.
3. A queue row must be explicitly `cleared_to_run=true` before a worker can
   claim it.
4. Declared attribution is authoritative for the author/source identity and
   overrides any model-extracted author value.
5. The declared author must resolve to an existing non-sentinel source. This
   slice does not create source rows or aliases.
6. The resolved source must pass the current canonical
   `is_source_servable()` policy. A hidden or otherwise non-servable source
   becomes `needs_attention`; the worker never changes `sources.visibility`,
   `license_status`, or safe mode.
7. Unsupported shape, unresolved attribution, empty extraction, unsafe fetch,
   and non-servable source are operator decisions, not retryable faults. They
   become `needs_attention` with a bounded reason code.
8. Provider/network transients retry with bounded backoff. Three exhausted
   attempts become `failed`.
9. No frontend work, collection crawling, per-item author inference, source
   creation, visibility mutation, or production deployment belongs to this
   slice.

## Approaches Considered

### Durable worker — selected

Reuse the answer worker’s proven Postgres lifecycle: atomic claim with
`FOR UPDATE SKIP LOCKED`, leases, reclamation, bounded retries, and exact final
state. This survives process death, supports later horizontal scaling, and
keeps expensive fetch/extract/embed work outside request latency.

### Synchronous admin endpoint — rejected

Calling the entire pipeline from an admin HTTP request would inherit Railway’s
request ceiling, lose useful crash semantics, and couple operator interaction
to provider latency.

### Manual cron or one-off script — rejected as the product path

A manual script could process rows, but it would leave the existing queue UI
without trustworthy lifecycle state and make support depend on terminal logs.
The durable worker remains invokable with `--once` for attended operation.

## Architecture

```text
source_ingest_queue
        │ atomic claim + lease
        ▼
source_ingest_worker.py
        │
        ├─ secure_fetch.py       public-IP-pinned bounded PDF fetch
        ├─ existing PDF extractor in a bounded child process
        ├─ dry_run.py            pure validation + predicted counts
        ├─ existing metadata extraction, with declared author override
        └─ shared_ingest.ingest_document()
                    │
                    └─ atomic documents + chunks + propositions write
```

The worker is a separate process, not a FastAPI background task. The existing
answer-worker Railway service and root `nixpacks.toml` remain unchanged. A
future source-worker service can override its start command to
`python3 scripts/source_ingest_worker.py`; deployment is outside this build.

## Components and Interfaces

### Migration 088: execution state

Extend `source_ingest_queue` with new execution-state columns:

- `attempts integer NOT NULL DEFAULT 0`
- `max_attempts integer NOT NULL DEFAULT 3`
- `worker_id text`
- `lease_expires_at timestamptz`
- `run_after timestamptz NOT NULL DEFAULT now()`
- `stage text NOT NULL DEFAULT 'queued'`
- `final_url text`
- `content_sha256 text`
- `fetched_bytes bigint`
- `attempted_documents integer NOT NULL DEFAULT 0`
- `stored_documents integer NOT NULL DEFAULT 0`
- `skipped_documents integer NOT NULL DEFAULT 0`
- `errored_documents integer NOT NULL DEFAULT 0`
- `result_document_id uuid REFERENCES documents(id) ON DELETE SET NULL`

`retain_original_text` is backfilled to `true`, receives `DEFAULT true`, is
made `NOT NULL`, and receives a check requiring `true`. Existing queue rows
have never been processed by a runner, so this changes their future policy but
does not pretend to reconstruct missing historical document text.

The apply script must snapshot every row’s prior `retain_original_text` value
to a local gitignored rollback artifact before the backfill. The new execution
columns are additive; the retention-value rewrite is non-destructive but is
value-reversible only with that required snapshot. Rollback removes the new
constraints/default and restores the snapshotted values before dropping the
execution columns.

Add partial indexes for claimable waiting rows and expired running leases.
Migration application remains a separate, explicitly approved production
database-write session. The repository build only prepares the SQL and its
apply/verification script.

### Queue lifecycle module

`scripts/source_ingest_queue/jobs.py` owns database state transitions:

- `claim_next(db, worker_id, lease_seconds)`
- `heartbeat(db, row_id, worker_id, lease_seconds)`
- `needs_attention(db, row_id, worker_id, reason_code, detail)`
- `fail_or_requeue(db, row_id, worker_id, reason_code, detail)`
- `complete(db, row_id, worker_id, result)`
- `reap_expired_leases(db)`

Every ownership-sensitive update includes `WHERE id = ? AND worker_id = ? AND
status = 'running'`. Losing the lease is a hard stop, never a best-effort
completion by a stale worker.

### Secure PDF fetcher

`scripts/source_ingest_queue/fetcher.py` performs one bounded fetch per URL
hop using only the Python standard library:

- Accept `http` and `https`; reject credentials and nonstandard schemes.
- Resolve every redirect target independently.
- Reject every resolved IP that is not globally routable, including private,
  loopback, link-local, multicast, reserved, and unspecified ranges.
- Pin the connection to a validated IP while preserving the original hostname
  for the HTTP `Host` header and TLS SNI/certificate verification. This avoids
  validating one DNS answer and connecting to another.
- Allow at most three redirects and reject HTTPS-to-HTTP downgrade redirects.
- Require `application/pdf` (parameters allowed).
- Enforce a 30-second connect/read timeout and 50 MiB streamed-byte ceiling,
  regardless of `Content-Length`.
- Return immutable bytes, final URL, SHA-256, byte count, and sanitized filename.
- Never log URL query strings, fragments, response bodies, document text, or
  credentials.

```python
@dataclass(frozen=True)
class FetchResult:
    content: bytes
    final_url: str
    sha256: str
    byte_count: int
    filename: str
```

### Extraction boundary

PDF parsing runs in a child process with a 60-second deadline. It rejects more
than 2,000 pages, empty text, and extracted text above 10 million characters.
Timeout, parser fault, and resource-limit outcomes are bounded reason codes;
raw parser exceptions are not exposed to the admin UI.

### Dry-run classifier

`scripts/source_ingest_queue/processor.py` separates pure preparation from the
write:

```python
@dataclass(frozen=True)
class PreparedIngest:
    row_id: str
    source_id: str
    title: str
    author: str
    body_text: str
    filename: str
    source_url: str
    source_type: str
    source_kind: str
    citation_mode: str
    topic_tags: list[str]
    bible_references: list[str]
    chunk_count: int
    content_sha256: str
    fetched_bytes: int
```

Preparation validates queue shape, declared attribution, source resolution,
canonical servability, extracted text, deterministic chunk count, and existing
dedup state before any corpus write. `--dry-run-row` stops here and therefore
makes no provider call. In normal worker mode only, metadata extraction then
proposes title, year, type, and tags; it cannot replace the declared
author/source identity.

The real processing call passes `body_text` unchanged to
`shared_ingest.ingest_document()`, which already stores it as `full_text` and
owns the atomic document/chunk/proposition transaction. No second insert path
is permitted.

### Worker process

`scripts/source_ingest_worker.py` mirrors the operational shape of
`answer_worker.py` but starts with concurrency one because each ingest can
perform expensive extraction, embedding, and proposition generation.

Supported commands:

```bash
python3 scripts/source_ingest_worker.py --once
python3 scripts/source_ingest_worker.py --poll-interval 2 --max-idle 30
python3 scripts/source_ingest_worker.py --dry-run-row <uuid>
```

`--dry-run-row` reads and validates one row without claiming it and without
writing queue or corpus state. Normal worker mode claims rows and therefore is
a database-writing operation.

A heartbeat renews ownership while processing. A dead process leaves the row
`running`; the next worker reclaims it after lease expiry and increments the
attempt count. The worker handles one row at a time; later capacity is a
deployment/concurrency dial, not an architectural rewrite.

## State Machine

```text
waiting + cleared_to_run
          │
          ▼
       running
          ├─ unsupported/policy/attribution issue ──► needs_attention
          ├─ transient fault + attempts remain ─────► waiting(run_after)
          ├─ transient fault + exhausted ──────────► failed
          ├─ duplicate/already ingested ───────────► done(skipped=1)
          └─ atomic shared-ingest success ─────────► done(stored=1)

running + expired lease ──► waiting or failed when attempts exhausted
```

For this one-document slice, every terminal row must reconcile exactly:

```text
attempted_documents = stored_documents
                    + skipped_documents
                    + errored_documents
```

`needs_attention` before a corpus attempt may record all four counts as zero;
its stage and reason code explain why no attempt occurred.

## Error Taxonomy

Operator-actionable `needs_attention` reasons:

- `unsupported_source_format`
- `unsupported_source_scope`
- `unsupported_attribution_mode`
- `retention_policy_missing`
- `declared_author_missing`
- `source_unresolved`
- `source_not_servable`
- `unsafe_url`
- `not_pdf`
- `pdf_too_large`
- `pdf_page_limit`
- `pdf_empty`
- `pdf_text_limit`

Retryable failures:

- `dns_failure`
- `connect_timeout`
- `read_timeout`
- `http_5xx`
- `metadata_provider_failure`
- `embedding_provider_failure`
- `proposition_provider_failure`
- `database_transient`

Unknown exceptions fail closed as `internal_error`, with full exception detail
only in protected service logs and a bounded message in queue state.

## API Compatibility

The existing queue endpoints and response shapes remain valid because new
columns are additive. `create_queue_row()` explicitly writes
`retain_original_text=true`; the database default independently enforces the
same policy for other callers. Existing rows receive the migration backfill.

The admin UI does not need a new control for retention because the policy is
no longer optional. It can display the new lifecycle fields without being
required for this backend slice. No existing endpoint will trigger ingestion;
only the worker consumes cleared rows.

## Project Structure

```text
migrations/088_source_ingest_runner.sql
scripts/apply_migration_088.py
scripts/source_ingest_worker.py
scripts/source_ingest_queue/__init__.py
scripts/source_ingest_queue/fetcher.py
scripts/source_ingest_queue/jobs.py
scripts/source_ingest_queue/processor.py
scripts/test_source_ingest_fetcher.py
scripts/test_source_ingest_jobs.py
scripts/test_source_ingest_processor.py
scripts/test_source_ingest_worker.py
```

Existing files changed narrowly:

- `backend/app/routers/ingest_queue.py` — persist the now-fixed retention policy.
- `ARCHITECTURE.md`, `CLAUDE.md`, `PLAN.md`, `rhemata-status.md` — separate
  records-only close after implementation.

No dependency, frontend, answer-generation, retrieval, doctrinal, position-
paper, licensing-status, or source-visibility code changes are planned.

## Code Style

Python 3.9 is the compatibility floor. Use typed dataclasses for boundaries,
small pure classifiers, dependency injection for network/database tests, and
explicit state-transition functions. Do not introduce a generic job framework
or refactor the answer worker.

```python
def classify_row(row: dict) -> Optional[str]:
    if row.get("source_format") != "pdf":
        return "unsupported_source_format"
    if row.get("source_scope") != "single":
        return "unsupported_source_scope"
    if row.get("attribution_mode") != "declared":
        return "unsupported_attribution_mode"
    if not (row.get("attribute_to") or "").strip():
        return "declared_author_missing"
    return None
```

## Testing Strategy

Development is test-first. All tests use fake database/network/provider
boundaries; none fetch live URLs, call Groq/OpenAI, or write production data.

### Fetcher tests

- Public IPv4 and IPv6 addresses are accepted through an injected resolver.
- Private/loopback/link-local/reserved/mixed DNS answers are refused.
- Redirect targets are revalidated; downgrade and redirect loops are refused.
- TLS uses the original hostname while the socket connects to the pinned IP.
- MIME, timeout, `Content-Length`, streamed-size, filename, and hash behavior
  are mutation-sensitive.

### Job lifecycle tests

- The claim statement structurally uses one parameterized
  `UPDATE ... FOR UPDATE SKIP LOCKED ... RETURNING` transaction; the migration
  apply verifier later proves two real claimers cannot obtain the same row.
- Uncleared and non-waiting rows are never claimed.
- Heartbeat and completion require current ownership.
- Expired leases requeue or fail at the attempt ceiling.
- Transient failures back off; operator conditions do not retry.
- Every terminal one-document result reconciles.

### Processor tests

- Unsupported shapes stop before fetch/write.
- Declared attribution overrides extracted metadata.
- Sentinel and non-servable sources stop before corpus writes.
- Dry run calculates counts and dedup outcome without calling the writer.
- Real mode calls `shared_ingest.ingest_document()` exactly once with
  `allow_sentinel=false` and unchanged `body_text`.
- `processed`, `skipped`, and `failed` shared-writer results map to exact queue
  outcomes.

### Worker tests

- One tick performs claim → heartbeat → process → terminal transition.
- A processor exception cannot kill the loop.
- `--once` drains currently eligible work and exits.
- `--dry-run-row` performs no database mutation.

Verification commands:

```bash
python3 scripts/test_source_ingest_fetcher.py
python3 scripts/test_source_ingest_jobs.py
python3 scripts/test_source_ingest_processor.py
python3 scripts/test_source_ingest_worker.py
PYTHONPYCACHEPREFIX=/private/tmp/rhemata_pycache python3 -m py_compile \
  scripts/source_ingest_worker.py scripts/source_ingest_queue/*.py
python3 scripts/test_nixpacks_python_parity.py
git diff --check
```

Before any real batch, the standing repository contract still requires a
read-only diagnostic, full dry run, one isolated real item, and hard
attempted/stored/errored/skipped reconciliation against the live database.

## Security Review

- Treat URLs, redirects, headers, PDF bytes, extracted text, metadata output,
  and database rows as untrusted.
- Fetches send no application cookies, authorization headers, service keys, or
  internal network credentials.
- The fetcher pins connections to validated public addresses and revalidates
  every redirect.
- Parser work is bounded by bytes, pages, text length, process deadline, and
  child-process isolation.
- Logs contain row ID, worker ID, sanitized host/path identity, stage, reason
  code, and counts—never source text, response bodies, secrets, or URL query.
- Database updates are parameterized and ownership-scoped.
- The worker uses existing service-role/database credentials only through the
  established environment-loading pattern; no credential is copied into code
  or durable artifacts.
- Corpus writes remain atomic and sentinel-refusing through the canonical
  shared writer.

## Performance and Operations

- Default concurrency is one.
- Maximum fetched bytes: 50 MiB.
- Maximum pages: 2,000.
- Maximum extracted characters: 10 million.
- Network timeout: 30 seconds.
- Extraction deadline: 60 seconds.
- Redirect limit: three.
- Attempts: three with bounded exponential backoff.
- Lease: five minutes, renewed every minute while current ownership holds.

The worker logs stage durations and final reconciliation. Provider token/cost
instrumentation is not added in this first slice because existing ingest
helpers do not expose it; adding a second estimator would be false precision.

## Boundaries

### Always

- Route every corpus write through `shared_ingest.ingest_document()`.
- Require explicit queue clearance and declared attribution.
- Retain extracted original text on every success.
- Validate/pin every network hop and bound every untrusted input.
- Use leases, ownership checks, bounded retry, and exact reconciliation.
- Keep build and records commits separate.

### Ask first

- Apply migration 088 or perform any production database write.
- Create/deploy a Railway source-worker service.
- Change the retention policy, supported formats/scopes, source visibility,
  license status, safe mode, or automatic source registration behavior.
- Add a dependency or change the existing answer-worker deployment.

### Never

- Run production DB writes through the harness.
- Fetch private/internal addresses or forward credentials to source URLs.
- Infer an unresolved author, proceed through the sentinel, or auto-show a
  source.
- Log document contents or URL secrets.
- Add collection crawling, web-page ingestion, per-item attribution, frontend
  work, doctrinal content, or position-paper changes to this slice.

## Success Criteria

- Migration 088 is non-destructive, locally verified, and unapplied; its apply
  script captures the required pre-backfill snapshot and proves rollback
  restoration on test data.
- The repository regression proves the atomic claim SQL and ownership guards;
  the unapplied migration’s verification script contains the real concurrent-
  claimer proof required during the separately approved apply session.
- A killed worker’s row is recoverable after lease expiry.
- All unsupported or policy-blocked rows stop before corpus writes.
- Secure-fetch tests prove public-address pinning and rejection of unsafe hops.
- Dry-run mode makes zero queue/corpus writes and zero embedding/proposition
  provider calls.
- A successful fake-backed integration follows
  `waiting → running → done`, calls the shared writer once, retains unchanged
  extracted text, and reconciles `1 = 1 + 0 + 0`.
- Duplicate input follows `waiting → running → done` and reconciles
  `1 = 0 + 1 + 0`.
- A writer/provider failure leaves no partial corpus state and either retries or
  terminates with `1 = 0 + 0 + 1`.
- Existing queue endpoints, answer worker, backend imports, and deterministic
  serving guards remain green.
- No production fetch, provider call, database write, deployment, or unrelated
  file change occurs during the repository build.

## Open Questions

None for this slice. Later slices must separately decide collection semantics,
web-page extraction, per-item attribution, automatic source registration, and
whether the admin UI should expose richer run controls.
