# Biblical Depth Phase 7 Full-Artifact Parser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task in the
> current isolated worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Account deterministically for the complete pinned TIPNR artifact and
produce a byte-stable, zero-effect eligibility inventory without widening the
approved Phase 0 field boundary.

**Architecture:** Extend the pure TIPNR parser into a two-pass pipeline: an
artifact verifier and structural scanner first classify every marker-delimited
record, then a marker-specific projector emits only approved identifiers,
original-language forms, and OSIS references. A separate CLI compiles an
ignored local inventory and conservative cost projection while importing no
database, model, answer, or deployment capability.

**Tech Stack:** Python 3.12, stdlib `dataclasses`, `hashlib`, `json`, `decimal`,
`pathlib`, and `unittest`; existing canonical JSON/checksum helpers; PyYAML only
through the existing manifest loader.

**Spec:**
`docs/superpowers/specs/2026-09-01-biblical-depth-phase-7-full-artifact-parser-design.md`

## Global Constraints

- Accept only revision `02843f07cbb5009e00999a7c0efead6430dbb6e7`, byte
  length `7916469`, and SHA-256
  `69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e`.
- The 4,262 observed marker records consist of three documentation records and
  4,259 entity records; implementation must prove these counts from structural
  evidence and must not discard records merely to fit the manifest.
- Only `person` and `place` may be eligible; every other recognized marker
  receives an explicit non-eligible outcome.
- Output remains limited to entity type, source identifiers,
  original-language forms, and ordered OSIS references.
- Directive values, display names, descriptions, relationships, ambiguity
  prose, comparisons, inferred facts, and generated text never enter output,
  diagnostic samples, checksums, or fixtures.
- `@Briefest`, `@Brief`, `@Short`, `@Article`, and `@Ambiguity` are recognized
  only as excluded directive keys.
- Unknown marker syntax, primary width, significance/width pair, directive,
  line shape, or reference grammar fails closed.
- Phase 7 has no network, model, database, ingestion, visibility, answer-path,
  feature-flag, deployment, or merge capability.
- `BIBLICAL_CONTEXT_ANSWER_ENABLED` remains default-off; protected and plural
  registries remain empty; all Phase 4 routing boundaries remain unchanged.
- The full inventory lives under gitignored `local/` with create-new or
  byte-identical semantics.
- Build and governing-text commits remain separate.

## File structure

- Modify `scripts/parse_tipnr_context.py`: artifact identity verification,
  structural record profiles, closed grammar, outcome classification, and
  allowlisted projection.
- Create `scripts/inventory_tipnr_context.py`: zero-capability inventory and
  cost compiler plus CLI.
- Modify `scripts/test_biblical_context_parsers.py`: unit, mutation,
  capability, and pinned-artifact integration coverage.
- Create
  `scripts/fixtures/biblical_context/tipnr_full_inventory_expected.json`:
  compact aggregate counts/checksums only; no upstream prose.
- Modify `docs/ingestion/source_manifests/tipnr.yaml`: after the independent
  full-artifact proof, replace the inaccurate record count and describe the
  documentation-record boundary in a docs-only commit.

---

### Task 1: Pinned artifact verifier and structural scanner

**Files:**
- Modify: `scripts/parse_tipnr_context.py`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: an explicit `Path` and raw artifact bytes.
- Produces:
  `verify_tipnr_artifact(path: Path) -> bytes`,
  `split_tipnr_records(text: str) -> tuple[tuple[str, ...], ...]`,
  `scan_tipnr_records(text: str) -> tuple[TipnrStructuralRecord, ...]`, and a
  frozen `TipnrStructuralRecord` with `ordinal`, `marker_shape`,
  `marker_class`, `primary_width`, `form_shapes`, `directive_keys`, and
  `line_shape_codes`.

- [ ] **Step 1: Write failing artifact-identity tests**

Add `hashlib`, `tempfile`, and `from unittest import mock` to the existing
stdlib imports, add imports for the new parser constants/functions, then add:

```python
class TipnrFullArtifactContractTests(unittest.TestCase):
    def test_artifact_verifier_accepts_only_exact_pinned_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tipnr.txt"
            path.write_bytes(b"pinned")
            with mock.patch("parse_tipnr_context.TIPNR_ARTIFACT_BYTES", 6), \
                 mock.patch(
                     "parse_tipnr_context.TIPNR_ARTIFACT_SHA256",
                     hashlib.sha256(b"pinned").hexdigest(),
                 ):
                self.assertEqual(verify_tipnr_artifact(path), b"pinned")
                path.write_bytes(b"mutate")
                with self.assertRaisesRegex(TipnrSchemaError, "artifact_sha256_mismatch"):
                    verify_tipnr_artifact(path)

    def test_scanner_preserves_every_marker_record_in_source_order(self) -> None:
        text = "\n".join((
            "$==========PERSON(s)", "header", "",
            "$========== PERSON(s)", "Name=H0001\t\t\t\t\t\t\t\t",
            "– Named\t\tH0001«H0001=א\t\tGen.1.1",
        ))
        records = scan_tipnr_records(text)
        self.assertEqual([row.ordinal for row in records], [1, 2])
        self.assertEqual(records[0].marker_shape, "person_no_space")
        self.assertEqual(records[1].marker_shape, "person_spaced")
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrFullArtifactContractTests
```

Expected: import failure for `verify_tipnr_artifact` and
`scan_tipnr_records`.

- [ ] **Step 3: Implement exact identity verification and lossless splitting**

Add immutable constants and verify size before checksum:

```python
TIPNR_ARTIFACT_REVISION = "02843f07cbb5009e00999a7c0efead6430dbb6e7"
TIPNR_ARTIFACT_BYTES = 7_916_469
TIPNR_ARTIFACT_SHA256 = "69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e"

def verify_tipnr_artifact(path: Path) -> bytes:
    payload = path.read_bytes()
    if len(payload) != TIPNR_ARTIFACT_BYTES:
        raise TipnrSchemaError("artifact_size_mismatch")
    if hashlib.sha256(payload).hexdigest() != TIPNR_ARTIFACT_SHA256:
        raise TipnrSchemaError("artifact_sha256_mismatch")
    return payload
```

Replace the private splitter with a public tuple-returning splitter that
starts a record on every line beginning exactly `$==========`, retains marker
text for closed-shape validation, and raises `entity_markers_missing` when no
marker exists. Keep `_split_records` as a compatibility wrapper until every
existing caller and Phase 6 regression is green.

- [ ] **Step 4: Implement the closed structural scanner**

Use a frozen dataclass and closed maps for the eight observed exact marker
shapes. Normalize trailing tabs before matching, but distinguish the three
no-space documentation markers from the five spaced entity markers. Record
only keys and shape tokens—never line values:

```python
@dataclass(frozen=True)
class TipnrStructuralRecord:
    ordinal: int
    marker_shape: str
    marker_class: str
    primary_width: int
    form_shapes: tuple[tuple[str, int], ...]
    directive_keys: tuple[str, ...]
    line_shape_codes: tuple[str, ...]
```

The three no-space records at ordinals 1–3 are the only accepted
`documentation` shapes. Spaced primary widths are closed to person 9, place
8, other 9, excluded-other 9, and person+place 8, with the two observed
malformed entity widths (person 13 at ordinal 3,099 and place form-row width 6
at ordinal 3,624) represented as record outcomes rather than accepted schemas.
Allowed directive keys are the five keys named in Global Constraints.

Freeze structural-only profiles for the six pinned records containing non-form
lines (ordinals 792, 869, 1,471, 1,472, 4,250, and the excluded-other tail at
4,262). Their profiles contain only ordinal, marker class, line count,
leading-codepoint/column-width counts, form shapes, and directive keys. They
become `prohibited/excluded_non_form_structure`; their source lines are never
retained. A non-form line at any other ordinal or a mismatch in one of these
profiles raises `TipnrSchemaError("unknown_line_shape")`. A new marker or
directive likewise raises `TipnrSchemaError`.

- [ ] **Step 5: Run scanner tests and existing parser regressions**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrFullArtifactContractTests
python3.12 scripts/test_biblical_context_parsers.py TipnrParserTests
```

Expected: both suites pass; the original H0175 projection is unchanged.

- [ ] **Step 6: Commit the scanner increment**

```bash
git add scripts/parse_tipnr_context.py scripts/test_biblical_context_parsers.py
git commit -m "feat: scan pinned TIPNR artifact structure"
```

---

### Task 2: Marker-specific fail-closed projection

**Files:**
- Modify: `scripts/parse_tipnr_context.py`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: `TipnrStructuralRecord` plus its original record lines.
- Produces:
  `classify_tipnr_record(lines: Sequence[str], profile: TipnrStructuralRecord,
  *, artifact_revision: str) -> TipnrRecordOutcome`, where the frozen outcome
  has exactly `ordinal`, `identity`, `status`, `reason`, `entity_type`,
  `projection`, and `canonical_sha256`.

- [ ] **Step 1: Write failing outcome and projection tests**

Add tests proving exact outcomes:

```python
def test_documentation_and_noneligible_markers_are_explicit(self) -> None:
    documentation = classify_tipnr_record(
        ("$==========PERSON(s)", "header"),
        TipnrStructuralRecord(1, "person_no_space", "documentation", 1, (), (), ()),
        artifact_revision=self.REVISION,
    )
    self.assertEqual((documentation.status, documentation.reason),
                     ("skipped", "source_documentation"))

def test_person_place_is_never_split_or_inferred(self) -> None:
    outcome = classify_profile_fixture("person_plus_place")
    self.assertEqual((outcome.status, outcome.reason),
                     ("prohibited", "combined_entity_type"))
    self.assertIsNone(outcome.projection)

def test_group_form_projects_only_when_existing_fields_parse(self) -> None:
    outcome = classify_profile_fixture("person_group_form")
    self.assertEqual(outcome.status, "eligible")
    self.assertEqual(set(outcome.projection), {
        "dataset_id", "artifact_revision", "entity_id", "entity_type",
        "original_language_forms", "record_sha256",
    })
```

Also add mutation cases for `@Doctrine`, `Relationship|5`, `Named|7`, a
13-column person primary row, a six-column form row, `Gen.1.1ff`, missing
forms, invalid Strong IDs, and any ordinary non-form line. Assert no excluded
fixture phrase appears in `canonical_json_bytes(outcome)`.

- [ ] **Step 2: Run the focused classifier tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrRecordOutcomeTests
```

Expected: import failure for `TipnrRecordOutcome` and
`classify_tipnr_record`.

- [ ] **Step 3: Implement stable outcome types and marker policy**

Define the only statuses and reasons as constants. Documentation becomes
`skipped/source_documentation`; `OTHER` and `EXCLUDED OTHER` become
`skipped/not_v1_entity_type`; `PERSON+PLACE` becomes
`prohibited/combined_entity_type`; recognized malformed allowed types become
`malformed/<specific_reason>`. Only a spaced person or place with a valid
primary width proceeds to projection.

Do not put source text in an ineligible outcome. Use the source ordinal plus a
canonical checksum of structural tokens for records without an approved
entity identity.

- [ ] **Step 4: Implement marker-specific primary and form parsing**

Keep the existing person nine-column path byte-identical. Add the ordinary
place eight-column path, selecting the entity identity from column 1 exactly
as the manifest specifies. Accept only five-column output-bearing form rows
whose significance is in this closed set:

```python
OUTPUT_FORM_SIGNIFICANCE = frozenset({
    "Named", "Name combined", "Spelled", "Spelled combined", "Aramaic",
    "Aramaic combined", "Greek", "LXX addition",
    "(same form as previous)", "(same ref[s] with Alt Tags)",
    "(same ref[s] with Variant)", "Form (verb)", "Form (adjective)",
    "Mentioned", "Group",
})
```

`Group` is not interpreted: it is eligible only because its five-column rows
contain the same already-approved dStrong/eStrong/source-script/reference
fields. `Total|5` is the only ordinary excluded form row. Any other
significance/width pair in an entity record fails or quarantines according to
the structural profile; documentation-only width pairs never reach the
projector. Preserve form and OSIS-reference source order.

- [ ] **Step 5: Make duplicate handling symmetric and deterministic**

Classify all occurrences of a repeated eligible entity identity as
`duplicate/duplicate_entity_id`; do not preserve the first as eligible and do
not merge forms. Implement duplicate resolution after classification so the
result is independent of which duplicate appears first.

- [ ] **Step 6: Run focused, Phase 2, and Phase 6 stability tests**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrRecordOutcomeTests
python3.12 scripts/test_biblical_context_parsers.py TipnrParserTests
python3.12 scripts/test_biblical_context_ingest.py AaronProjectionTests
```

Expected: all pass and H0175 retains record SHA-256
`78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6`.

- [ ] **Step 7: Commit the projection increment**

```bash
git add scripts/parse_tipnr_context.py scripts/test_biblical_context_parsers.py
git commit -m "feat: classify complete TIPNR record grammar"
```

---

### Task 3: Zero-capability inventory compiler and CLI

**Files:**
- Create: `scripts/inventory_tipnr_context.py`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: `verify_tipnr_artifact()`, `scan_tipnr_records()`, and
  `classify_tipnr_record()`.
- Produces:
  `build_tipnr_inventory(path: Path) -> dict[str, object]`,
  `write_new_inventory(path: Path, payload: bytes) -> None`, and
  `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write failing inventory and capability tests**

```python
class TipnrInventoryTests(unittest.TestCase):
    def test_inventory_has_one_outcome_per_structural_record(self) -> None:
        inventory = build_fixture_inventory(PROFILE_FIXTURE)
        counts = inventory["outcome_counts"]
        self.assertEqual(sum(counts.values()), inventory["structural_records"])
        self.assertEqual(inventory["database_write_authorized"], False)
        self.assertEqual(inventory["external_model_call_authorized"], False)

    def test_cli_has_no_network_database_or_model_capability(self) -> None:
        source = INVENTORY_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "socket", "requests", "httpx", "urllib", "psycopg2", "supabase",
            "openai", "anthropic", "embedding", "ingest", "answer_worker",
        ):
            self.assertNotIn(f"import {forbidden}", source)
            self.assertNotIn(f"from {forbidden}", source)
```

Tripwire `socket.socket`, `psycopg2.connect`, and model client constructors
while invoking the CLI against a patched small pinned fixture.

- [ ] **Step 2: Run inventory tests and confirm RED**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrInventoryTests
```

Expected: import failure for `inventory_tipnr_context`.

- [ ] **Step 3: Implement canonical inventory aggregation**

Emit this fixed top-level shape:

```python
inventory = {
    "schema_version": "biblical_context_tipnr_inventory.v1",
    "artifact": {"revision": TIPNR_ARTIFACT_REVISION,
                 "bytes": TIPNR_ARTIFACT_BYTES,
                 "sha256": TIPNR_ARTIFACT_SHA256},
    "database_write_authorized": False,
    "external_model_call_authorized": False,
    "structural_records": len(outcomes),
    "entity_records": sum(row.marker_class != "documentation" for row in profiles),
    "outcome_counts": sorted_counts,
    "reason_counts": sorted_reasons,
    "eligible_by_type": sorted_types,
    "records": canonical_record_outcomes,
    "eligible_checksum": canonical_sha256(eligible_projections),
    "rendering": rendering_projection,
}
inventory["payload_sha256"] = canonical_sha256(inventory)
```

Sort record outcomes by immutable source identity when one exists and then by
ordinal; retain form/reference order inside each projection. Include only
identity, status, reason, entity type, and canonical checksum per record. Do
not include a timestamp, path, machine data, source line, directive value, or
excluded text.

- [ ] **Step 4: Implement conservative cost projection without tokenization or calls**

Render each eligible projection through one existing pure canonical renderer
and report exact UTF-8 bytes plus one predicted request per eligible record.
Record price metadata as `text-embedding-3-small`, USD `0.02` per 1,000,000
input tokens, source URL
`https://developers.openai.com/api/docs/models/text-embedding-3-small`, and
price review date `2026-09-01`. Estimate tokens conservatively as
`ceil(utf8_bytes / 3)` and compute estimated cost with `Decimal`; set the later
approval ceiling to the greater of twice the estimate or USD `0.01`. This is
planning evidence only and never authorizes a request.

- [ ] **Step 5: Implement safe local output**

Require `--artifact PATH`; accept optional `--output` only below repository
`local/`. Reuse the Phase 2 create-new or byte-identical semantics: mode 0600,
no symlink, no multi-link target, no replacement of different bytes, and an
fsync before close. Provide no download, apply, write-database, retry, or batch
flag.

- [ ] **Step 6: Run focused tests and a fixture CLI preview**

Run:

```bash
python3.12 scripts/test_biblical_context_parsers.py TipnrInventoryTests
python3.12 scripts/inventory_tipnr_context.py --artifact scripts/fixtures/biblical_context/tipnr_minimal.txt
```

Expected: tests pass; the fixture invocation is refused by the production
artifact identity guard unless the test-only identity constants are patched.
This confirms the CLI cannot silently treat a fixture as the full artifact.

- [ ] **Step 7: Commit the inventory increment**

```bash
git add scripts/inventory_tipnr_context.py scripts/test_biblical_context_parsers.py
git commit -m "feat: compile zero-effect TIPNR inventory"
```

---

### Task 4: Full pinned-artifact closure and compact evidence fixture

**Files:**
- Create: `scripts/fixtures/biblical_context/tipnr_full_inventory_expected.json`
- Modify: `scripts/test_biblical_context_parsers.py`
- Generated, ignored: `local/2026-09/tipnr_full_inventory.json`

**Interfaces:**
- Consumes: the exact pinned artifact at an explicit operator-supplied path.
- Produces: full ignored canonical inventory plus a compact checked-in JSON
  contract containing artifact identity, structural/entity counts, aggregate
  outcome/reason counts, eligible checksums, rendering counts, and payload
  checksum.

- [ ] **Step 1: Run the full inventory as a read-only diagnostic**

Run with the actual local path substituted for `/absolute/path/to/tipnr.txt`:

```bash
python3.12 scripts/inventory_tipnr_context.py \
  --artifact /absolute/path/to/tipnr.txt \
  --output local/2026-09/tipnr_full_inventory.json
```

Expected: either one complete 4,262-record inventory or a hard schema failure.
If it fails, add only the exact observed structural shape to the compact test
fixture, write a failing test, and decide from the approved field allowlist
whether it is a recognized non-eligible outcome or governing schema drift.
Never copy the source line or excluded value into a test.

- [ ] **Step 2: Reconcile the inventory arithmetic and boundaries**

Run:

```bash
python3.12 -c 'import json,pathlib; p=json.loads(pathlib.Path("local/2026-09/tipnr_full_inventory.json").read_text()); assert p["structural_records"] == 4262; assert p["entity_records"] == 4259; assert sum(p["outcome_counts"].values()) == 4262; assert p["database_write_authorized"] is False; assert p["external_model_call_authorized"] is False; print(p["outcome_counts"], p["reason_counts"], p["eligible_by_type"], p["payload_sha256"])'
```

Expected: assertions pass and print only aggregate evidence and checksums.

- [ ] **Step 3: Freeze compact aggregate evidence independently**

Create `tipnr_full_inventory_expected.json` by manually transcribing only the
aggregate keys named in this task's Interfaces from the completed inventory.
Do not copy its `records` array. Add a test that recomputes the full inventory
from an explicit `TIPNR_TEST_ARTIFACT` path when that environment variable is
present and otherwise skips with `pinned TIPNR artifact unavailable`. Compare
each compact value directly; do not generate expected values with the
production parser during the assertion.

- [ ] **Step 4: Prove determinism and mutation resistance**

Run the inventory twice to two new temporary local filenames and compare bytes
with `cmp`. In unit tests, mutate one byte, reorder two compact fixture records,
duplicate an identity, replace one directive key, replace one significance,
alter one marker, and change one row width. Assert identity mismatch, schema
drift, duplicate, or checksum disagreement as appropriate.

- [ ] **Step 5: Run focused and complete biblical-context regressions**

Run:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/test_biblical_context_ingest.py
python3.12 scripts/test_biblical_source_manifests.py
python3.12 scripts/test_source_passage_classification.py
python3.12 scripts/test_source_use_policy.py
python3.12 scripts/test_source_use_routing.py
python3.12 scripts/test_source_use_generation_contract.py
```

Expected: all pass, including exact H0175 stability, default-off generation,
empty registries, pre-writer fail-closed routing, cache isolation, neighbor
rechecking, two-source plurality, and house-paper fencing.

- [ ] **Step 6: Commit build evidence separately**

```bash
git add scripts/fixtures/biblical_context/tipnr_full_inventory_expected.json scripts/test_biblical_context_parsers.py
git commit -m "test: freeze complete TIPNR inventory contract"
```

Do not add the full ignored inventory or upstream artifact.

---

### Task 5: Evidence-backed governing record replacement

**Files:**
- Modify: `docs/ingestion/source_manifests/tipnr.yaml`
- Modify: `docs/roadmap.md`
- Modify: `rhemata-status.md`

**Interfaces:**
- Consumes: the passing compact inventory fixture and ignored full inventory.
- Produces: corrected manifest record accounting and a closed Phase 7 roadmap
  state; no executable behavior.

- [ ] **Step 1: Replace, rather than stack, the manifest count contract**

Change the reviewed artifact entry from the unsupported single
`entity_records: 4263` assertion to evidence-backed fields:

```yaml
    structural_marker_records: 4262
    documentation_records: 3
    entity_records: 4259
```

Extend `record_grammar` to state that the three no-space marker records at
source ordinals 1–3 are source documentation and are never eligible. Preserve
every authorization value as false and do not widen allowed fields,
visibility, or disposition.

- [ ] **Step 2: Update the owning records**

Replace the Phase 7/A4 current entry in `docs/roadmap.md` with the achieved
inventory-ready state, exact aggregate checksum, classifications, and the next
single item: a separately designed hidden batch packet. Overwrite the Current
state section of `rhemata-status.md` with original outcome achieved,
unplanned investigations `0`, findings promoted to Blocker `0`, and active
critical-path items `1`. Do not append a competing status entry.

- [ ] **Step 3: Verify docs and manifest consistency**

Run:

```bash
git diff --check
python3.12 scripts/test_biblical_source_manifests.py
rg -n "4263|4262|4259|BIBLICAL_CONTEXT_ANSWER_ENABLED|protected_source|plural" docs/ingestion/source_manifests/tipnr.yaml docs/roadmap.md rhemata-status.md
```

Expected: no whitespace errors; manifest tests pass; old `4263` is absent from
the governing current state; safety boundaries remain explicit.

- [ ] **Step 4: Commit records separately from all build work**

```bash
git add docs/ingestion/source_manifests/tipnr.yaml docs/roadmap.md rhemata-status.md
git commit -m "docs: record complete TIPNR inventory closure"
```

---

### Task 6: Final verification and stop

**Files:**
- Verify only; no planned edits.

**Interfaces:**
- Consumes: all Phase 7 commits.
- Produces: completion evidence only.

- [ ] **Step 1: Run the coherent final verification cycle**

Run with the explicit pinned artifact path:

```bash
TIPNR_TEST_ARTIFACT=/absolute/path/to/tipnr.txt python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/test_biblical_context_ingest.py
python3.12 scripts/test_biblical_source_manifests.py
python3.12 scripts/test_source_passage_classification.py
python3.12 scripts/test_source_use_policy.py
python3.12 scripts/test_source_use_routing.py
python3.12 scripts/test_source_use_generation_contract.py
git diff --check HEAD~5..HEAD
git status --short
```

Expected: all tests pass, the diff check is clean, and only intentionally
ignored local inventory/upstream bytes remain outside Git.

- [ ] **Step 2: Inspect commit separation**

Run:

```bash
git log --oneline --name-only -6
```

Expected: parser/test build commits contain no roadmap/status/manifest files;
the final docs commit contains no Python or fixture implementation.

- [ ] **Step 3: Stop at ingestion readiness**

Report exact attempted/eligible/skipped/malformed/duplicate/prohibited counts,
the aggregate and payload checksums, rendered-byte/token estimate, and maximum
cost ceiling. Do not request an embedding, connect to production, run a batch,
change visibility, enable the feature, deploy, merge, or begin the next phase.
