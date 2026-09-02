# Biblical Depth Phase 8 Hidden Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task in the
> current isolated worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an execution-ready but unexecuted packet for exactly 10 TIPNR
people and 10 TIPNR places, with zero-effect preview, read-only preflight,
attended apply gating, one atomic transaction, and complete reconciliation.

**Architecture:** A pure packet contract re-derives the Phase 7 inventory and
freezes 20 deterministic projections. Separate preview, preflight, apply, and
reconciliation modules enforce progressively stronger capabilities so model
and write dependencies are unavailable until an exact same-day approval passes.

**Tech Stack:** Python 3.12, stdlib `dataclasses`, `decimal`, `hashlib`, `json`,
`math`, `pathlib`, and `uuid`; existing Phase 6/7 parser, canonical JSON,
embedding adapter, psycopg2 connection patterns, and `unittest` strict fakes.

**Spec:**
`docs/superpowers/specs/2026-09-01-biblical-depth-phase-8-hidden-pilot-design.md`

## Global constraints

- Accept only the pinned TIPNR revision/artifact, Phase 7 inventory hash
  `edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040`,
  eligible checksum
  `1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2`,
  and selection checksum
  `398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b`.
- Select exactly the first 10 people and first 10 places by entity ID after
  excluding `H0175`; no caller selection, offset, limit, or alternate source.
- Preserve only entity type/ID, approved original-language forms, and ordered
  OSIS references; excluded prose never enters output, hashes, or samples.
- Preview has no network, database, model, embedding, answer, proposition, or
  deployment capability.
- Repository implementation performs no production connection, embedding
  request, database write, batch execution, visibility change, deployment,
  feature activation, live answer, registry assignment, or merge.
- Apply requires exactly 20 validated vectors before opening one write
  transaction and cannot insert or update the existing source/alias/H0175 rows.
- Proposition code remains structurally unavailable.
- `BIBLICAL_CONTEXT_ANSWER_ENABLED` remains default-off, the source remains
  hidden, protected/plural source slots remain empty, and Phase 4 boundaries
  remain unchanged.
- Build commits and governing records commits remain separate.

## File structure

- Create `scripts/tipnr_hidden_pilot_contract.py`: immutable selection,
  generalized renderer, UUID/document/chunk/policy projection, packet hashes,
  pricing, and six-item sample identities.
- Create `scripts/preview_tipnr_hidden_pilot.py`: zero-capability canonical
  preview and safe ignored-local publication.
- Create `scripts/preflight_tipnr_hidden_pilot.py`: read-only source/H0175 and
  candidate-state classification.
- Create `scripts/apply_tipnr_hidden_pilot.py`: approval validation, vector
  boundary, and one atomic 60-row writer.
- Create `scripts/reconcile_tipnr_hidden_pilot.py`: fresh exact-state,
  40-probe hidden-retrieval, hard reconciliation, and sample report.
- Create `scripts/test_tipnr_hidden_pilot.py`: all Phase 8 unit/integration
  tests with strict fake connections and clients.
- Create
  `scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json`: exact
  IDs, record hashes, selection checksum, and final preview checksum only.
- Modify `docs/roadmap.md` and `rhemata-status.md` only after all repository
  implementation evidence passes.

---

### Task 1: Pure immutable pilot packet

**Files:**
- Create: `scripts/tipnr_hidden_pilot_contract.py`
- Create: `scripts/test_tipnr_hidden_pilot.py`
- Create: `scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json`

**Interfaces:**
- Consumes: explicit pinned artifact `Path`, Phase 7 classifier/inventory,
  Phase 6 source constants and `stable_uuid()`.
- Produces:
  `PilotItem`, `PilotPacket`,
  `render_pilot_text(record: Mapping[str, object]) -> str`, and
  `build_pilot_packet(root: Path, artifact_path: Path) -> PilotPacket`, and
  `pilot_packet_report(packet: PilotPacket) -> dict[str, object]`.

- [ ] **Step 1: Write failing selection and projection tests**

Add literal expected `(entity_type, entity_id, record_sha256)` tuples from the
design and tests:

```python
class PilotPacketTests(unittest.TestCase):
    def test_selects_exact_balanced_twenty_and_excludes_h0175(self) -> None:
        packet = build_pilot_packet(ROOT, PINNED_ARTIFACT)
        self.assertEqual(len(packet.items), 20)
        self.assertEqual(
            Counter(item.entity_type for item in packet.items),
            {"person": 10, "place": 10},
        )
        self.assertNotIn("H0175", [item.entity_id for item in packet.items])
        self.assertEqual(packet.selection_checksum, SELECTION_SHA256)
        self.assertEqual(
            [(item.entity_type, item.entity_id, item.record["record_sha256"])
             for item in packet.items],
            EXPECTED_SELECTION,
        )

    def test_projects_one_document_chunk_and_policy_per_item(self) -> None:
        packet = build_pilot_packet(ROOT, PINNED_ARTIFACT)
        self.assertEqual(len({item.document["id"] for item in packet.items}), 20)
        self.assertTrue(all(item.chunk["document_id"] == item.document["id"]
                            for item in packet.items))
        self.assertTrue(all(item.policy["chunk_id"] == item.chunk["id"]
                            for item in packet.items))
        self.assertTrue(all(item.policy["policy_class"] == "general_context"
                            for item in packet.items))
```

Assert the exact sample IDs and that serialized packet data excludes known
fixture sentinel phrases for descriptions, relationships, ambiguity, and
translation comparisons.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPacketTests
```

Expected: import failure for `tipnr_hidden_pilot_contract`.

- [ ] **Step 3: Implement exact selection and contract validation**

Define exact constants from the spec, including all 20 IDs/hashes and:

```python
PACKET_ITEM_COUNT = 20
PERSON_COUNT = 10
PLACE_COUNT = 10
PHASE7_INVENTORY_SHA256 = "edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040"
PHASE7_ELIGIBLE_SHA256 = "1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2"
SELECTION_SHA256 = "398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2b"
MAXIMUM_SPEND_USD = "0.01"
SAMPLE_IDS = ("G0010", "G0132", "G0223J", "G0009", "G0137", "G0494")
```

Call `build_tipnr_inventory()` and refuse unless its payload/eligible hashes,
outcome counts, and artifact identity match Phase 7 compact evidence. Re-run
`classify_tipnr_text()`, group eligible non-H0175 records by type, sort each by
entity ID, take 10, combine people then places, and compare every selected
literal plus `canonical_sha256(selected_records)`.

- [ ] **Step 4: Implement generalized rendering and deterministic projections**

Generalize the Phase 6 fixed field order without accepting new fields:

```python
def render_pilot_text(record: Mapping[str, object]) -> str:
    lines = [
        "Dataset: STEPBible TIPNR",
        f"Revision: {TIPNR_ARTIFACT_REVISION}",
        f"Entity ID: {record['entity_id']}",
        f"Entity type: {record['entity_type']}",
    ]
    forms = record["original_language_forms"]
    for index, form in enumerate(forms, start=1):
        lines.extend((
            f"Form {index} dStrong: {form['dstrong']}",
            f"Form {index} eStrong: {form['estrong']}",
            f"Form {index} source script: {form['source_script_form']}",
            f"Form {index} OSIS references: {'; '.join(form['osis_references'])}",
        ))
    return "\n".join(lines) + "\n"
```

Create frozen `PilotItem` with `entity_id`, `entity_type`, `record`, `document`,
`chunk`, `policy`, `text`, `rendered_sha256`, and `identity`. Create frozen
`PilotPacket` with `source`, `alias`, `items`, `selection_checksum`,
`rendered_bytes`, `estimated_tokens`, `estimated_cost_usd`,
`maximum_spend_usd`, `sample_ids`, and `packet_sha256`. Use Phase 6
`stable_uuid()` for document and chunk identities, exact hidden Phase 6 source
and alias projections, one chunk, and the existing deterministic policy fields.
Compute exact rendered bytes, conservative token/cost projection, item hashes,
and a packet hash over the complete canonical packet report.

- [ ] **Step 5: Freeze compact expected evidence and run GREEN**

Create the compact JSON with the exact selection literals and hashes derived
independently in the design diagnostic. Add packet/preview hashes only after
the implementation output is reconciled twice byte-for-byte; never include
excluded source prose.

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPacketTests
python3.12 scripts/test_biblical_context_ingest.py AaronProjectionTests
```

Expected: all pass and Phase 6 H0175 remains byte-identical.

- [ ] **Step 6: Commit the pure packet increment**

```bash
git add scripts/tipnr_hidden_pilot_contract.py scripts/test_tipnr_hidden_pilot.py scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json
git commit -m "feat: freeze balanced TIPNR hidden pilot"
```

---

### Task 2: Zero-effect preview and safe publication

**Files:**
- Create: `scripts/preview_tipnr_hidden_pilot.py`
- Modify: `scripts/test_tipnr_hidden_pilot.py`

**Interfaces:**
- Consumes: `build_pilot_packet()` and `pilot_packet_report()` from Task 1.
- Produces:
  `build_pilot_preview(root: Path, artifact_path: Path) -> dict[str, object]`,
  `write_new_pilot_preview(path: Path, payload: bytes) -> None`, and
  `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing preview/capability tests**

```python
class PilotPreviewTests(unittest.TestCase):
    def test_preview_freezes_zero_effect_boundary(self) -> None:
        report = build_pilot_preview(ROOT, PINNED_ARTIFACT)
        self.assertIs(report["database_write_authorized"], False)
        self.assertIs(report["external_model_call_authorized"], False)
        self.assertEqual(report["counts"], {
            "items": 20, "documents": 20, "chunks": 20,
            "policy_rows": 20, "embedding_requests": 20,
        })
        self.assertEqual(report["maximum_spend_usd"], "0.01")
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 0, "errored": 0, "skipped": 20,
            "reason": "preview_only",
        })

    def test_preview_runs_with_network_and_late_import_tripwires(self) -> None:
        # Invoke real main(["--artifact", ...]) while socket.socket and imports
        # of psycopg2/openai/anthropic/supabase/app.services.embeddings raise.
        self.assertEqual(exit_code, 0)
```

Also assert `--apply`, `--limit`, `--offset`, and `--entity-id` are rejected,
and output outside repository `local/` fails.

- [ ] **Step 2: Run preview tests and confirm RED**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPreviewTests
```

Expected: import failure for `preview_tipnr_hidden_pilot`.

- [ ] **Step 3: Implement canonical preview and safe output**

Require only `--artifact PATH` and optional `--output local/...`. Reuse
`write_new_preview()` create-new/byte-identical mode-0600 semantics. Emit exact
packet report, count/cost/reconciliation blocks, sample IDs, and a final
`payload_sha256`. Print canonical JSON and never discover or download files.

- [ ] **Step 4: Run preview twice and confirm byte identity**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPreviewTests
python3.12 scripts/preview_tipnr_hidden_pilot.py \
  --artifact /absolute/path/to/tipnr.txt \
  --output local/2026-09/tipnr_hidden_pilot_preview.json
```

Expected: tests pass; preview reports both authorization booleans false. A
second run to a new ignored filename must compare byte-identical with `cmp`.

- [ ] **Step 5: Commit the preview increment**

```bash
git add scripts/preview_tipnr_hidden_pilot.py scripts/test_tipnr_hidden_pilot.py scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json
git commit -m "feat: preview balanced TIPNR hidden pilot"
```

---

### Task 3: Read-only preflight and single-item verification

**Files:**
- Create: `scripts/preflight_tipnr_hidden_pilot.py`
- Modify: `scripts/test_tipnr_hidden_pilot.py`

**Interfaces:**
- Consumes: `PilotPacket`, Phase 6 `ProofProjection`, identity/retrieval
  connection factories.
- Produces:
  `CandidateState(kind: str, policy_id: str | None)`,
  `inspect_pilot_item(cursor, item: PilotItem) -> CandidateState`, and
  `preflight_pilot(identity_factory, retrieval_factory, packet, proof)
  -> dict[str, object]`.

- [ ] **Step 1: Write failing all-clean/all-complete/conflict tests**

Use strict fake cursors with exact query tags and complete row shapes:

```python
class PilotPreflightTests(unittest.TestCase):
    def test_all_clean_requires_exact_h0175_verification(self) -> None:
        report = preflight_pilot(identity_factory, retrieval_factory, packet, proof)
        self.assertEqual(report["candidate_state"], "all_clean")
        self.assertEqual(report["counts"], {"clean": 20, "exact_complete": 0})
        self.assertEqual(report["single_item_verification"]["status"], "verified")

    def test_mixed_state_fails_closed(self) -> None:
        with self.assertRaisesRegex(PilotPreflightError, "candidate_state_mixed"):
            preflight_pilot(mixed_factory, retrieval_factory, packet, proof)
```

Add separate mutations for partial document/chunk/policy rows, proposition
count, wrong source/alias, missing completion stamp, wrong vector dimensions,
duplicate current policy, non-read-only session, wrong analysis role, one
H0175 retrieval match, enabled default constant, and populated protected or
plural source slots.

- [ ] **Step 2: Run preflight tests and confirm RED**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPreflightTests
```

Expected: import failure for `preflight_tipnr_hidden_pilot`.

- [ ] **Step 3: Implement exact candidate inspection**

Query by deterministic document ID/file path and chunk ID/document ID, fetch
all current policies, and count propositions. Return `clean` only when all row
families are absent. Return `exact_complete` only when document, completion
stamp, chunk content/references/dimensions, source attribution, and exactly one
policy match the item projection with zero propositions. Raise
`candidate_state_conflict` for every other state.

- [ ] **Step 4: Implement read-only preflight orchestration**

Enforce `transaction_read_only='on'` and role
`newwine_readonly_analysis` before identity queries. Reuse Phase 6
`reconcile_single_proof()` for exact H0175 identity and retrieval verification.
Verify source and alias once, inspect all items, and allow only unanimous clean
or unanimous exact-complete. Assert repository code invariants for default-off
feature and empty source slots through imported real policy/producer objects;
do not read or mutate environment feature state.

- [ ] **Step 5: Implement dependency loader and CLI**

Require `--artifact PATH --verify`. Load `.env.readonly-analysis` and the Phase
6 retrieval verifier connection only after local packet construction. Set both
sessions read-only before queries. Print canonical report; provide no approval,
apply, write, or model argument.

- [ ] **Step 6: Run GREEN and commit**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotPreflightTests
python3.12 scripts/test_biblical_context_ingest.py ReconciliationTests
```

Expected: all pass with no real connection.

```bash
git add scripts/preflight_tipnr_hidden_pilot.py scripts/test_tipnr_hidden_pilot.py
git commit -m "feat: preflight balanced TIPNR hidden pilot"
```

---

### Task 4: Attended approval gate and atomic writer

**Files:**
- Create: `scripts/apply_tipnr_hidden_pilot.py`
- Modify: `scripts/test_tipnr_hidden_pilot.py`

**Interfaces:**
- Consumes: exact `PilotPacket`, preflight report, connection and embedding
  factories, same-day approval JSON.
- Produces:
  `validate_pilot_approval(path, packet, today) -> dict[str, object]` and
  `apply_pilot(connection_factory, embed_fn, packet, approval,
  preflight_fn) -> dict[str, object]`.

- [ ] **Step 1: Write failing approval and dependency-order tests**

```python
class PilotApplyTests(unittest.TestCase):
    def test_approval_must_match_exact_packet_and_day(self) -> None:
        self.assertEqual(validate_pilot_approval(path, packet, TODAY), expected)
        for key, wrong in APPROVAL_MUTATIONS:
            with self.subTest(key=key):
                with self.assertRaisesRegex(PilotApprovalError, "approval_scope_mismatch"):
                    validate_pilot_approval(mutated_path(key, wrong), packet, TODAY)

    def test_all_vectors_finish_before_write_connection(self) -> None:
        report = apply_pilot(factory, embed_fn, packet, approval, clean_preflight)
        self.assertEqual(events[:20], [f"embed:{item.entity_id}" for item in packet.items])
        self.assertEqual(events[20], "connect:write")
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 20, "errored": 0, "skipped": 0,
        })
```

Add failures for nonregular/oversized/extra-field approval, item/hash/count/
model/dimension/ceiling/date drift, all-complete zero-call skip, request 1 and
20 failures, invalid dimension/NaN/bool vectors, write connection failure,
state change after preflight, each insert/staged-check/stamp failure, rollback,
and commit ambiguity. Assert proposition imports/calls are impossible.

- [ ] **Step 2: Run apply tests and confirm RED**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotApplyTests
```

Expected: import failure for `apply_tipnr_hidden_pilot`.

- [ ] **Step 3: Implement exact approval validation**

Accept a regular, single-link JSON file no larger than 8192 bytes with exactly
the fields specified by the design. Compare the entire mapping to a derived
literal using `date.today()`, packet hash/count, model/dimensions, request
ceiling `20`, maximum spend `0.01`, and both authorization booleans true.

- [ ] **Step 4: Implement vector boundary and report**

Run local validation and injected read-only preflight first. If all complete,
return skipped 20. If clean, call `embed_fn(item.text, model=..., dimensions=...)`
in packet order, validating 1,536 finite non-bool numeric values each. Track
requests attempted/completed and expose the bounded ceiling; on any error open
no write connection and return errored `20` because the atomic packet was not
stored.

- [ ] **Step 5: Implement one atomic 60-row transaction**

Open one write connection only after all vectors validate. Set 30-second
statement and 5-second lock timeouts, recheck exact source/alias and all-clean
candidate state, insert 20 documents, 20 chunks, and 20 policies in packet
order, query every staged row back, stamp all documents, verify again, and
commit once. Roll back on any exception. Never insert source/alias, update
H0175, or import propositions.

- [ ] **Step 6: Implement CLI dependency gate without executing it**

Require only `--artifact PATH --approval-file PATH`. Build packet and validate
approval before loading the Phase 6 embedding adapter or write credential.
After apply, invoke the separate reconciler and preserve both reports if
verification fails. Write a final report only under ignored `local/` when
verified.

- [ ] **Step 7: Run GREEN and commit**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotApplyTests
python3.12 scripts/test_biblical_context_ingest.py
```

Expected: all pass with strict fakes and zero external calls.

```bash
git add scripts/apply_tipnr_hidden_pilot.py scripts/test_tipnr_hidden_pilot.py
git commit -m "feat: gate atomic TIPNR hidden pilot"
```

---

### Task 5: Fresh reconciliation and deterministic sampling

**Files:**
- Create: `scripts/reconcile_tipnr_hidden_pilot.py`
- Modify: `scripts/test_tipnr_hidden_pilot.py`
- Modify: `scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json`

**Interfaces:**
- Consumes: exact packet and fresh identity/retrieval factories.
- Produces:
  `reconcile_pilot(identity_factory, retrieval_factory, packet)
  -> dict[str, object]` and `build_sample_report(packet) -> dict[str, object]`.

- [ ] **Step 1: Write failing reconciliation and sample tests**

```python
class PilotReconciliationTests(unittest.TestCase):
    def test_verified_report_reconciles_every_item_and_probe(self) -> None:
        report = reconcile_pilot(identity_factory, retrieval_factory, packet)
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 20, "errored": 0, "skipped": 0,
        })
        self.assertEqual(report["retrieval_probes"], {
            "vector_attempted": 20, "vector_matches": 0,
            "fts_attempted": 20, "fts_matches": 0,
        })

    def test_sample_is_exact_first_middle_last_per_type(self) -> None:
        sample = build_sample_report(packet)
        self.assertEqual([row["entity_id"] for row in sample["items"]],
                         list(SAMPLE_IDS))
```

Mutate every exact-state field and each of 40 retrieval results. Assert one
match fails with `hidden_retrieval_leak`. Assert absent/mixed candidates cannot
be represented as verified. Assert sample serialization contains only approved
record/projection fields.

- [ ] **Step 2: Run reconciliation tests and confirm RED**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt \
  python3.12 scripts/test_tipnr_hidden_pilot.py PilotReconciliationTests
```

Expected: import failure for `reconcile_tipnr_hidden_pilot`.

- [ ] **Step 3: Implement fresh exact-state reconciliation**

Use one enforced analysis-role read-only session to verify source/alias and all
20 exact-complete candidates with zero propositions. Use a separate enforced
read-only retrieval session and call vector RPC plus FTS RPC once per item,
requiring zero matches. Hard-check attempted equals stored + errored + skipped.

- [ ] **Step 4: Implement sample and final report**

Select exact `SAMPLE_IDS` in the specified order. Emit entity type/ID, record
and rendered hashes, source attribution, forms/references, and policy class.
Reject any item with additional fields. Add packet, preflight, apply,
reconciliation, retrieval, and sample checksums to the final canonical report.

- [ ] **Step 5: Run full Phase 8 and Phase 0–7 regression suite**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt python3.12 scripts/test_tipnr_hidden_pilot.py
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/test_biblical_context_ingest.py
python3.12 scripts/test_biblical_source_manifests.py
python3.12 scripts/test_source_passage_classification.py
python3.12 scripts/test_source_use_policy.py
python3.12 scripts/test_source_use_routing.py
python3.12 scripts/test_source_use_generation_contract.py
```

Expected: every suite passes with no real model or database call.

- [ ] **Step 6: Commit final build evidence**

```bash
git add scripts/reconcile_tipnr_hidden_pilot.py scripts/test_tipnr_hidden_pilot.py scripts/fixtures/biblical_context/tipnr_hidden_pilot_expected.json
git commit -m "test: prove TIPNR hidden pilot reconciliation"
```

---

### Task 6: Governing records and final stop

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `rhemata-status.md`

**Interfaces:**
- Consumes: passing Phase 8 packet/preview/tooling evidence.
- Produces: execution-ready, explicitly unexecuted Phase 8 status.

- [ ] **Step 1: Replace current A4 and session state**

Record the exact 20-item packet/preview hashes, request count, rendered bytes,
estimate, USD `0.01` ceiling, six sample IDs, and passing test counts. State
that no production preflight, embedding, database write, or batch ran and that
the next action is an attended same-day execution decision. Preserve all
default-off/hidden/empty-registry/no-release boundaries.

- [ ] **Step 2: Verify records and commit separately**

Run:

```bash
git diff --check
python3.12 scripts/test_biblical_source_manifests.py
rg -n "Phase 8|20|0.01|BIBLICAL_CONTEXT_ANSWER_ENABLED|hidden|protected|plural|not executed" docs/roadmap.md rhemata-status.md
```

Expected: consistent execution-ready wording and no widened authorization.

```bash
git add docs/roadmap.md rhemata-status.md
git commit -m "docs: record TIPNR hidden pilot readiness"
```

- [ ] **Step 3: Run final verification and stop before external effects**

Repeat the Task 5 test commands, compile all five Phase 8 modules, run
`git diff --check`, inspect commit separation, and confirm `git status --short`
is empty. Push the commits to the existing PR #3 branch only; do not merge,
deploy, connect to production, create an approval artifact, request embeddings,
or execute the pilot.
