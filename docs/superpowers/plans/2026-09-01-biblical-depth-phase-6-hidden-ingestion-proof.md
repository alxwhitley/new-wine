# Biblical Depth Phase 6 Hidden Ingestion Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task in the
> current isolated worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tested, fail-closed tooling that previews and prepares exactly
one hidden STEPBible TIPNR Aaron ingestion proof, stopping before model spend or
any production write.

**Architecture:** A pure contract module derives the immutable Aaron projection
from the existing Phase 2 parser. A preview CLI has no database-write or model
capability. A separate approval-gated apply module owns one embedding call and
one short atomic source/alias/document/chunk/policy transaction, while an
independent read-only reconciler verifies any later approved run.

**Tech Stack:** Python 3.12, stdlib `dataclasses`/`hashlib`/`json`/`uuid`,
existing PyYAML parser tooling, psycopg2 loaded only inside apply/reconcile
entrypoints, existing OpenAI `text-embedding-3-small` helper, `unittest` with
strict fakes.

**Spec:**
`docs/superpowers/specs/2026-09-01-biblical-depth-phase-6-hidden-ingestion-proof-design.md`

## Global Constraints

- The only proof input is TIPNR Aaron entity `H0175`, upstream revision
  `02843f07cbb5009e00999a7c0efead6430dbb6e7`, record SHA-256
  `78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6`.
- Preview makes zero network, model, embedding, write-credential, or write-DB
  access and reports both authorization booleans false.
- Apply supports exactly one item and requires a matching attended approval
  file; implementation and dry run do not constitute that approval.
- Exactly one source, alias, document, chunk, and current `general_context`
  policy row are projected; no propositions are generated.
- The source is `licensed` and explicitly `hidden`; the answer feature remains
  default-off and protected/plural registries remain empty.
- No source registration, embedding request, production write, visibility
  change, live answer, deployment, or batch is authorized during plan
  execution.
- Build and docs commits remain separate.

---

### Task 1: Pure Aaron proof contract

**Files:**
- Create: `scripts/biblical_context_ingest_contract.py`
- Create: `scripts/test_biblical_context_ingest.py`
- Read: `scripts/biblical_context_tooling.py`
- Read: `scripts/parse_tipnr_context.py`
- Read: `scripts/fixtures/biblical_context/tipnr_minimal.txt`
- Read: `scripts/fixtures/biblical_context/tipnr_minimal.meta.json`

**Interfaces:**
- Consumes: `load_approved_manifests()`, `compile_registration_preview()`,
  `parse_tipnr_file()`, and `canonical_sha256()` from Phase 2.
- Produces:
  `ProofProjection`, `build_aaron_projection(root: Path) -> ProofProjection`,
  `canonical_proof_text(record: Mapping[str, object]) -> str`, and
  `projection_report(projection: ProofProjection) -> dict[str, object]`.

- [ ] **Step 1: Write failing contract tests**

Add tests that assert the exact fixed boundary:

```python
class AaronProjectionTests(unittest.TestCase):
    def test_builds_exact_single_row_projection(self) -> None:
        proof = build_aaron_projection(ROOT)
        self.assertEqual(proof.entity_id, "H0175")
        self.assertEqual(proof.source["name"], "STEPBible TIPNR")
        self.assertEqual(proof.source["slug"], "stepbible-tipnr")
        self.assertEqual(proof.source["visibility"], "hidden")
        self.assertEqual(proof.alias["alias_key"], "stepbible tipnr")
        self.assertEqual(proof.document["source_kind"], "biblical_context")
        self.assertEqual(proof.document["citation_mode"], "citable")
        self.assertEqual(len(proof.chunks), 1)
        self.assertEqual(proof.chunks[0]["chunk_index"], 0)
        self.assertEqual(proof.policy["policy_class"], "general_context")
        self.assertEqual(proof.policy["protected_topic_keys"], [])
        self.assertIsNone(proof.policy["issue_key"])
        self.assertIsNone(proof.policy["viewpoint_key"])

    def test_projection_is_byte_stable(self) -> None:
        first = projection_report(build_aaron_projection(ROOT))
        second = projection_report(build_aaron_projection(ROOT))
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))

    def test_refuses_mutated_or_non_aaron_record(self) -> None:
        with self.assertRaisesRegex(ProofContractError, "proof_record_mismatch"):
            validate_aaron_record({"entity_id": "H0071"})
```

Also assert the canonical text excludes `description`, `relationship`,
`comparison`, and every non-allowlisted fixture phrase already covered by the
Phase 2 tests.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py
```

Expected: import failure for `biblical_context_ingest_contract`.

- [ ] **Step 3: Implement the immutable projection**

Create a frozen `ProofProjection` dataclass containing only serializable source,
alias, document, chunk, policy, hash, and identity values. Define exact
constants:

```python
ENTITY_ID = "H0175"
UPSTREAM_REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"
RECORD_SHA256 = "78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6"
SOURCE_SLUG = "stepbible-tipnr"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_SPEND_USD = "0.01"
POLICY_RULE_VERSION = "biblical_context_structural_v1"
POLICY_REASON = "phase0_allowlisted_structural_fields"
```

Use one fixed UUID namespace and derive IDs with:

```python
def stable_uuid(kind: str, identity: str) -> str:
    return str(uuid.uuid5(PHASE6_NAMESPACE, f"{kind}:{identity}"))
```

Select Aaron from `parse_tipnr_file()` only after matching the exact revision,
record checksum, entity type, and ID. Render a stable factual text block in a
fixed order. Compute `rendered_sha256` from its UTF-8 bytes. Derive document and
chunk IDs from the immutable identity string
`stepbible-tipnr:<revision>:H0175:<record_sha256>:<rendered_sha256>`.

The source projection must include explicit ID, name, slug, `licensed`,
`hidden`, CC BY 4.0 permission terms, and provenance notes. The document
projection must contain exactly the fields named in the spec. The policy
projection must contain exact deterministic metadata and reference the stable
chunk ID.

- [ ] **Step 4: Run focused and Phase 2 tests and confirm GREEN**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py
python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/test_biblical_source_manifests.py
```

Expected: all pass, with no network or database access.

---

### Task 2: Zero-effect preview CLI

**Files:**
- Create: `scripts/preview_biblical_context_ingest.py`
- Modify: `scripts/test_biblical_context_ingest.py`

**Interfaces:**
- Consumes: `build_aaron_projection()` and `projection_report()` from Task 1.
- Produces:
  `build_preview(root: Path) -> dict[str, object]`,
  `write_new_preview(path: Path, payload: bytes) -> None`, and CLI
  `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing preview tests**

```python
class PreviewTests(unittest.TestCase):
    def test_preview_reports_exact_zero_effect_contract(self) -> None:
        report = build_preview(ROOT)
        self.assertFalse(report["database_write_authorized"])
        self.assertFalse(report["external_model_call_authorized"])
        self.assertEqual(report["counts"], {
            "sources": 1, "aliases": 1, "documents": 1,
            "chunks": 1, "policy_rows": 1,
        })
        self.assertEqual(report["embedding"]["request_count"], 1)
        self.assertEqual(report["embedding"]["maximum_spend_usd"], "0.01")
        self.assertEqual(report["reconciliation"], {
            "attempted": 1, "stored": 0, "errored": 0, "skipped": 1,
            "reason": "preview_only",
        })

    def test_preview_has_no_dangerous_imports(self) -> None:
        source = PREVIEW_PATH.read_text(encoding="utf-8")
        for forbidden in ("psycopg2", "openai", "embeddings", "propositions"):
            self.assertNotIn(forbidden, source)
```

Monkeypatch `socket.socket`, common database modules, and model modules with
tripwires while invoking `main(["--fixtures"])`.

- [ ] **Step 2: Run the focused preview tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py PreviewTests
```

Expected: import failure for `preview_biblical_context_ingest`.

- [ ] **Step 3: Implement the preview CLI**

Require `--fixtures`. Optionally accept `--output` only under `local/`, using
the immutable create-or-byte-identical behavior from
`preview_biblical_context_tooling.write_new_preview()`. Output canonical JSON
with:

```python
{
    "schema_version": "biblical_context_phase6_ingest_preview.v1",
    "database_write_authorized": False,
    "external_model_call_authorized": False,
    "proof": projection_report(proof),
    "counts": {"sources": 1, "aliases": 1, "documents": 1,
               "chunks": 1, "policy_rows": 1},
    "embedding": {"model": "text-embedding-3-small", "dimensions": 1536,
                  "request_count": 1, "maximum_spend_usd": "0.01",
                  "input_utf8_bytes": len(proof.text.encode("utf-8"))},
    "reconciliation": {"attempted": 1, "stored": 0, "errored": 0,
                       "skipped": 1, "reason": "preview_only"},
}
```

Add a canonical `payload_sha256` after building the rest of the object.

- [ ] **Step 4: Run preview tests and the real zero-effect preview**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py PreviewTests
python3.12 scripts/preview_biblical_context_ingest.py --fixtures
```

Expected: tests pass; JSON reports the exact `1/1/1/1/1` projection and both
authorization booleans false.

---

### Task 3: Approval-gated atomic writer and read-only reconciler

**Files:**
- Create: `scripts/ingest_biblical_context_batch.py`
- Create: `scripts/reconcile_biblical_context_batch.py`
- Modify: `scripts/test_biblical_context_ingest.py`

**Interfaces:**
- Consumes: `ProofProjection` and `build_aaron_projection()` from Task 1.
- Produces:
  `validate_approval(path: Path, proof: ProofProjection, today: date) -> dict`,
  `inspect_state(cursor, proof: ProofProjection) -> StateVerdict`,
  `apply_single_proof(connection_factory, embed_fn, proof, approval) -> dict`,
  `reconcile_single_proof(connection_factory, proof) -> dict`, and two CLIs.

- [ ] **Step 1: Write failing approval and preflight tests**

Test an approval file with the exact schema:

```json
{
  "schema_version": "biblical_context_phase6_approval.v1",
  "approved_by": "Alex Whitley",
  "operation_date": "2026-09-01",
  "source_slug": "stepbible-tipnr",
  "entity_id": "H0175",
  "record_sha256": "78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6",
  "maximum_spend_usd": "0.01",
  "source_registration_authorized": true,
  "embedding_request_authorized": true,
  "single_database_transaction_authorized": true
}
```

Assert missing, false, additional, stale-date, wrong-identity, or wrong-cost
fields raise `ApprovalError`. Assert `inspect_state()` returns only `clean`,
`exact_complete`, or raises `StateConflictError`; partial state and duplicate
current policy are conflicts.

- [ ] **Step 2: Write failing transaction-order and failure tests**

Use strict fake connection/cursor objects to record SQL, `commit()`, and
`rollback()`. Use fake `embed_fn(text, *, model, dimensions)` implementations.
Assert:

```python
def test_embedding_failure_opens_no_write_connection(self) -> None:
    factory = Mock()
    with self.assertRaisesRegex(RuntimeError, "embedding_failed"):
        apply_single_proof(factory, failing_embed, self.proof, self.approval)
    factory.assert_not_called()

def test_exact_complete_skips_before_embedding(self) -> None:
    embed = Mock()
    result = apply_single_proof(exact_complete_factory, embed,
                                self.proof, self.approval)
    embed.assert_not_called()
    self.assertEqual(result["reconciliation"], {
        "attempted": 1, "stored": 0, "errored": 0, "skipped": 1,
    })

def test_policy_insert_failure_rolls_back_everything(self) -> None:
    connection = transaction_fake(fail_on="policy_insert")
    result = apply_single_proof(lambda: connection, successful_embed,
                                self.proof, self.approval)
    self.assertEqual(connection.commit_count, 0)
    self.assertEqual(connection.rollback_count, 1)
    self.assertEqual(result["reconciliation"], {
        "attempted": 1, "stored": 0, "errored": 1, "skipped": 0,
    })
```

Assert successful SQL ordering is preflight, source, alias, document, chunk,
policy, staged reconciliation, completion stamp, commit. Assert all SQL uses
parameters and the transaction executes `SET LOCAL statement_timeout`.

- [ ] **Step 3: Run the focused writer tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py ApprovalTests WriterTests
```

Expected: import failures for the apply and reconcile modules.

- [ ] **Step 4: Implement approval and state validation**

The apply module must import no `argparse` source selector and expose no batch
size. `main()` accepts only `--approval-file`. Validate the exact JSON key set,
values, operation date, and regular-file/no-symlink boundary before importing
database or embedding dependencies.

`inspect_state()` queries exact UUIDs plus name, slug, alias key, file path, and
current-policy count. It returns `exact_complete` only when every expected row
and metadata value exists and no proposition references the document; it
returns `clean` only when all are absent. Every other combination raises.

- [ ] **Step 5: Implement the one-call, one-transaction writer**

Perform a read-only preflight using the apply connection, close it, and stop on
`exact_complete` or conflict. On `clean`, call the injected embedding function
once and verify exactly 1536 finite floats. Only then open a fresh write
connection with autocommit false.

Repeat collision checks inside the transaction and execute parameterized
inserts for:

```sql
INSERT INTO sources
  (id, name, slug, license_status, visibility, permission_terms, notes)
VALUES (%s, %s, %s, 'licensed', 'hidden', %s, %s)
```

then the exact alias, document, one chunk, and migration-097 policy row. Store
the vector using psycopg2's validated bracket representation. Query every staged
row back, assert exact counts/metadata/dimensions, stamp
`documents.ingest_completed_at=now()`, and commit. Never import
`scripts/propositions.py`.

Return a canonical report containing approval identity, proof identity, model,
bounded spend, generated policy-row ID, and hard reconciliation counts whose sum
equals attempted.

- [ ] **Step 6: Implement independent read-only reconciliation**

The reconcile CLI accepts no write credential and loads only
`backend/app/.env.readonly-analysis` / `READONLY_ANALYSIS_DB_URL`. Set the
connection read-only and autocommit true, verify `current_user` is
`newwine_readonly_analysis`, then query the expected source, alias, document,
chunk, policy, proposition absence, default-off app setting/environment-facing
configuration evidence available to the script, and retrieval exclusion.

Return status `verified` only when all checks pass and hard counts are exactly
attempted `1`, stored `1`, errored `0`, skipped `0`. The apply CLI invokes this
module through a fresh connection after commit and writes the final canonical
report only to an immutable file under `local/2026-09/`.

- [ ] **Step 7: Run focused tests and static capability checks**

Run:

```bash
python3.12 scripts/test_biblical_context_ingest.py
rg -n "propositions|--source|--entity|--limit|--batch-size" \
  scripts/ingest_biblical_context_batch.py
```

Expected: all tests pass; any `propositions` occurrence is only an explicit
absence query or safety comment, and no source/entity/limit/batch selection
argument exists.

---

### Task 4: Full verification and repository handoff

**Files:**
- Modify only if verification exposes a defect:
  `scripts/biblical_context_ingest_contract.py`
  `scripts/preview_biblical_context_ingest.py`
  `scripts/ingest_biblical_context_batch.py`
  `scripts/reconcile_biblical_context_batch.py`
  `scripts/test_biblical_context_ingest.py`
- Create locally, never commit:
  `local/2026-09/biblical_context_v1_proof.json`

**Interfaces:**
- Consumes all Task 1–3 deliverables.
- Produces a verified code commit and a zero-effect preview artifact; no
  production effect.

- [ ] **Step 1: Run the focused Phase 6 suite**

```bash
python3.12 scripts/test_biblical_context_ingest.py
```

Expected: all Phase 6 contract, preview, writer, failure, retry, and reconcile
tests pass.

- [ ] **Step 2: Run the Phase 0–5 biblical-depth regression suites**

```bash
python3.12 scripts/test_biblical_source_manifests.py
python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/test_source_use_policy.py
python3.12 scripts/test_position_paper_routing.py
python3.12 scripts/test_source_use_routing.py
python3.12 scripts/test_biblical_context_generation.py
```

Expected: all pass without external model spend.

- [ ] **Step 3: Run the real zero-effect preview**

```bash
python3.12 scripts/preview_biblical_context_ingest.py \
  --fixtures \
  --output local/2026-09/biblical_context_v1_proof.json
```

Expected: exact `1/1/1/1/1` projection, one predicted embedding request,
maximum spend `$0.01`, both authorization booleans false, and no DB/model call.

- [ ] **Step 4: Inspect and commit the build separately**

```bash
git diff --check
git status --short
git diff -- scripts/
git add scripts/biblical_context_ingest_contract.py \
  scripts/preview_biblical_context_ingest.py \
  scripts/ingest_biblical_context_batch.py \
  scripts/reconcile_biblical_context_batch.py \
  scripts/test_biblical_context_ingest.py
git diff --staged --check
git commit -m "feat: add hidden biblical context ingestion proof"
```

Expected: one build-only commit; `local/` is not staged.

- [ ] **Step 5: Stop at the production gate**

Report the preview hash, exact row projection, test totals, and commit ID. Do
not create an approval artifact, run the apply command, make an embedding
request, connect with a write credential, register the source, or write any
production row. The next action requires Alex's separate explicit approval.
