# Biblical Depth Phase 2 Hidden Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic, manifest-first, zero-database-write tooling that previews five approved hidden registrations and parses only approved TIPNR people/place and OpenBible geocoding fields from pinned fixtures.

**Architecture:** A shared contract module validates the approved Phase 0 manifests and compiles registration and ingestion-policy projections. Two source-specific parsers return canonical in-memory outcomes, and one zero-write CLI reconciles them into stable JSON without importing database, ingestion, retrieval, answer, model, or embedding code.

**Tech Stack:** Python 3.12 standard library, PyYAML already used by the repository, `unittest`, canonical JSON, SHA-256.

**Spec:** `docs/superpowers/specs/2026-09-01-biblical-depth-phase-2-hidden-tooling-design.md`

## Global Constraints

- No production or local database access or writes.
- No live source registration, alias creation, source correction, or ingestion.
- No database migration or write-capable `--apply` command.
- No live corpus-scale processing, retrieval or answer-path change, visibility change, deployment, or doctrinal decision.
- The protected charismatic neighborhood remains limited to Alex-approved house material and approved protected sources.
- General biblical/history material and plural presentations of other orthodox disputes remain governed by the Phase 1 policy and later release gates.
- The existing STEPBible source row is untouched.
- Tyndale prose and OpenBible cross references remain `prohibited_in_v1`.
- TIPNR `other` records are counted as `skipped:not_v1_entity_type`, not previewed.
- Known excluded fields are discarded explicitly; unknown structural fields fail as schema drift.
- Generated preview artifacts are not committed; operational output belongs under gitignored `local/`.
- Preserve all unrelated working-tree changes and stage only Phase 2 files.
- Any terminal command handed to Alex begins with `cd /Users/alexwhitley/newwine &&`.

---

### Task 1: Manifest compiler and hidden registration preview

**Files:**
- Create: `scripts/biblical_context_tooling.py`
- Create: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: approved YAML manifests from `docs/ingestion/source_manifests/`.
- Produces: `ContractError`, `canonical_json_bytes(value: object) -> bytes`, `canonical_sha256(value: object) -> str`, `load_approved_manifests(manifest_dir: Path) -> dict[str, dict[str, object]]`, `compile_registration_preview(manifests: Mapping[str, Mapping[str, object]]) -> tuple[dict[str, object], ...]`, and `compile_ingestion_policies(manifests: Mapping[str, Mapping[str, object]]) -> dict[str, dict[str, object]]`.

- [ ] **Step 1: Write failing manifest-contract tests**

Add `unittest.TestCase` coverage that loads the real manifests and asserts:

```python
rows = compile_registration_preview(load_approved_manifests(MANIFEST_DIR))
self.assertEqual([row["slug"] for row in rows], [
    "openbible-bible-geocoding",
    "openbible-cross-references",
    "stepbible-tipnr",
    "tyndale-open-bible-dictionary",
    "tyndale-open-study-notes",
])
self.assertTrue(all(row["visibility"] == "hidden" for row in rows))
self.assertNotIn("id", rows[0])
self.assertEqual(
    {row["slug"] for row in rows if row["ingestion_policy"] == "prohibited_in_v1"},
    {
        "openbible-cross-references",
        "tyndale-open-bible-dictionary",
        "tyndale-open-study-notes",
    },
)
```

Clone manifest dictionaries in memory and assert `ContractError` for an unapproved decision, any `authorization` value changed to true, a non-hidden proposed row, an unknown schema version, duplicate slug/alias, or an unsupported dataset ID.

- [ ] **Step 2: Run the test and prove RED**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.ManifestCompilerTests -v`

Expected: FAIL because `scripts.biblical_context_tooling` does not exist.

- [ ] **Step 3: Implement the minimal compiler**

Implement closed constants for the four manifest IDs and the exact eight false authorization keys. Validate data before projection. Registration rows must include only:

```python
{
    "dataset_id": dataset_id,
    "name": source_row["name"],
    "slug": source_row["slug"],
    "license_status": manifest["proposed_registration"]["license_status"],
    "visibility": source_row["visibility"],
    "source_kind": source_row.get("source_kind"),
    "citation_mode": source_row.get("citation_mode"),
    "aliases": tuple(sorted(source_row.get("aliases", ()))),
    "ingestion_policy": source_row.get("ingestion_policy", "eligible_for_phase_2_preview"),
}
```

Sort rows by slug, reject duplicate slugs or normalized aliases, and never synthesize UUIDs. Canonical JSON must use `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=False`, UTF-8, and exactly one trailing newline.

- [ ] **Step 4: Run the manifest tests and prove GREEN**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.ManifestCompilerTests -v`

Expected: PASS with all five hidden registration rows and three explicit prohibitions.

- [ ] **Step 5: Commit the manifest compiler slice**

```bash
cd /Users/alexwhitley/newwine && git add scripts/biblical_context_tooling.py scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && git commit -m "feat(ingestion): compile hidden biblical source previews"
```

### Task 2: TIPNR entity parser and pinned fixture

**Files:**
- Create: `scripts/parse_tipnr_context.py`
- Create: `scripts/fixtures/biblical_context/tipnr_minimal.txt`
- Create: `scripts/fixtures/biblical_context/tipnr_minimal.meta.json`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: an explicit TIPNR text path and the `stepbible_tipnr` ingestion policy from Task 1.
- Produces: `TipnrSchemaError`, `TipnrItemError`, `parse_tipnr_entity(lines: Sequence[str], *, artifact_revision: str) -> dict[str, object]`, and `parse_tipnr_file(path: Path, *, artifact_revision: str) -> dict[str, object]`.

- [ ] **Step 1: Pin the smallest real-format fixture**

Obtain a minimal person, place, and other record from the official TIPNR artifact at revision `02843f07cbb5009e00999a7c0efead6430dbb6e7`. Store only the lines needed to exercise marker, primary row, non-`Total` form row, excluded generated-prose line, and record boundary. Record fixture byte length, SHA-256, official source URL, revision, and selected entity IDs in `tipnr_minimal.meta.json`.

- [ ] **Step 2: Write failing TIPNR tests**

Assert one entity output with this shape:

```python
{
    "dataset_id": "stepbible_tipnr",
    "artifact_revision": "02843f07cbb5009e00999a7c0efead6430dbb6e7",
    "entity_id": "H0175",
    "entity_type": "person",
    "original_language_forms": [
        {
            "dstrong": "H0175",
            "estrong": "H0175",
            "source_script_form": "אַהֲרֹן",
            "osis_references": ["Exo.4.14", "Exo.4.27"],
        }
    ],
}
```

The pinned fixture uses Aaron (`H0175`) for person, Abana (`H0071`) for place, and Abaddon (`H0011`) for `OTHER`. Trim the Aaron reference list in the fixture to `Exo.4.14; Exo.4.27` while retaining the original row grammar and record that fixture selection in metadata. Also assert: generated prose and `Total` rows never appear; Abana previews with both source forms; Abaddon increments `skipped` with `not_v1_entity_type`; duplicate entity IDs increment `duplicate`; `ff`, malformed Strong/form syntax, unknown marker types, unexpected row shapes, and new directive names raise stable errors; repeated parse bytes and checksums match.

- [ ] **Step 3: Run TIPNR tests and prove RED**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.TipnrParserTests -v`

Expected: FAIL because `scripts.parse_tipnr_context` does not exist.

- [ ] **Step 4: Implement the TIPNR parser**

Split records only at `$==========` markers. Accept exactly `PERSON`, `PERSONS`, `PLACE`, or `OTHER` after normalizing the source marker punctuation documented by the real fixture. Extract the primary-row entity ID only from column 1 after the final `=`. Accept form rows only when the significance column is recognized, column 3 splits exactly as `dstrong«estrong=source_script_form`, and column 5 contains explicit OSIS tokens without `ff`.

Explicitly discard the four known generated-prose directives and the documented primary-row descriptive columns. Reject any new directive or row grammar. Preserve source order for forms and references; never merge duplicate entities.

Return aggregate counts with the exact keys `attempted`, `previewed`, `malformed`, `duplicate`, `skipped`, and `prohibited`, plus sorted reason-code counts and a checksum over previewed records.

- [ ] **Step 5: Run TIPNR tests and prove GREEN**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.TipnrParserTests -v`

Expected: PASS, including one isolated person item, one isolated place item, and the excluded `OTHER` count.

- [ ] **Step 6: Commit the TIPNR slice**

```bash
cd /Users/alexwhitley/newwine && git add scripts/parse_tipnr_context.py scripts/fixtures/biblical_context/tipnr_minimal.txt scripts/fixtures/biblical_context/tipnr_minimal.meta.json scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && git commit -m "feat(ingestion): parse approved TIPNR context fields"
```

### Task 3: OpenBible geocoding parser and pinned fixture

**Files:**
- Create: `scripts/parse_openbible_context.py`
- Create: `scripts/fixtures/biblical_context/openbible_ancient_minimal.jsonl`
- Create: `scripts/fixtures/biblical_context/openbible_ancient_minimal.meta.json`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: an explicit `ancient.jsonl` path and the `openbible_structured_data:bible_geocoding` ingestion policy from Task 1.
- Produces: `OpenBibleSchemaError`, `OpenBibleItemError`, `parse_openbible_place(value: Mapping[str, object], *, artifact_revision: str) -> dict[str, object]`, and `parse_openbible_file(path: Path, *, artifact_revision: str) -> dict[str, object]`.

- [ ] **Step 1: Pin the smallest real-format fixture**

Obtain two minimal records from official `data/ancient.jsonl` at revision `7eb18a5ee62f27b9b93bd6689ea272d76dd23b8f`: one with candidate identifications and one without. Preserve the complete real records so the known-excluded root and nested keys are proven discardable. Record byte length, SHA-256, official URL, revision, and place IDs in the metadata file.

- [ ] **Step 2: Write failing OpenBible tests**

Assert an output shape containing only:

```python
{
    "dataset_id": "openbible_structured_data",
    "artifact_revision": "7eb18a5ee62f27b9b93bd6689ea272d76dd23b8f",
    "place_id": "aea17b7",
    "place_name": "Abana",
    "place_types": ["river"],
    "osis_references": ["2Kgs.5.12"],
    "candidate_identifications": [
        {
            "modern_id": "m39ac0b",
            "name": "Barada River",
            "confidence_score": 1000,
        }
    ],
}
```

Use Azazel (`ab9a5ec`) as the association-free record. Assert that coordinates, geometry, translations, counts, descriptions, linked data, media, readable verse text, association siblings, and `extra` never appear. Assert a new root key or new nested key raises schema drift; missing/invalid required fields count as malformed; duplicate `place_id` counts as duplicate; score must remain an integer; output is byte/checksum stable.

- [ ] **Step 3: Run OpenBible tests and prove RED**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.OpenBibleParserTests -v`

Expected: FAIL because `scripts.parse_openbible_context` does not exist.

- [ ] **Step 4: Implement the OpenBible parser**

Pin the complete known root-key set and the known key sets for `verses[]` and `modern_associations.*`. Refuse any field outside those pinned schemas. Project only `id`, `friendly_id`, `types[]`, `verses[].osis`, and the three approved association fields. Discard all known excluded fields explicitly.

Require non-empty string IDs/names/types/OSIS values, integer confidence scores excluding booleans, and deterministic association ordering by source mapping key while preserving source order for `types` and `verses`. Return the same aggregate count/reason/checksum contract as TIPNR.

- [ ] **Step 5: Run OpenBible tests and prove GREEN**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.OpenBibleParserTests -v`

Expected: PASS with both isolated real records and every exclusion/schema-drift mutation.

- [ ] **Step 6: Commit the OpenBible slice**

```bash
cd /Users/alexwhitley/newwine && git add scripts/parse_openbible_context.py scripts/fixtures/biblical_context/openbible_ancient_minimal.jsonl scripts/fixtures/biblical_context/openbible_ancient_minimal.meta.json scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && git commit -m "feat(ingestion): parse approved OpenBible place fields"
```

### Task 4: Zero-write preview CLI and reconciliation

**Files:**
- Create: `scripts/preview_biblical_context_tooling.py`
- Modify: `scripts/test_biblical_context_parsers.py`

**Interfaces:**
- Consumes: Task 1 compiler projections, Task 2/3 fixture parsers, explicit fixture metadata.
- Produces: `build_fixture_preview(root: Path) -> dict[str, object]`, `write_new_preview(path: Path, payload: bytes) -> None`, and CLI `main(argv: Sequence[str] | None = None) -> int` supporting only `--fixtures` and optional `--output PATH`.

- [ ] **Step 1: Write failing orchestration and tripwire tests**

Assert `build_fixture_preview(ROOT)` has exact reconciliation counts:

```python
preview = build_fixture_preview(ROOT)
self.assertEqual(preview["schema_version"], "biblical_context_phase2_preview.v1")
self.assertIs(preview["database_write_authorized"], False)
self.assertEqual(len(preview["registration_rows"]), 5)
self.assertEqual(preview["datasets"]["stepbible_tipnr"]["counts"], {
    "attempted": 3, "previewed": 2, "malformed": 0,
    "duplicate": 0, "skipped": 1, "prohibited": 0,
})
self.assertEqual(
    preview["datasets"]["openbible_structured_data:bible_geocoding"]["counts"],
    {"attempted": 2, "previewed": 2, "malformed": 0,
     "duplicate": 0, "skipped": 0, "prohibited": 0},
)
for dataset_key in (
    "openbible_structured_data:cross_references",
    "tyndale_open_resources:open_bible_dictionary",
    "tyndale_open_resources:open_study_notes",
):
    self.assertEqual(preview["datasets"][dataset_key]["counts"], {
        "attempted": 1, "previewed": 0, "malformed": 0,
        "duplicate": 0, "skipped": 0, "prohibited": 1,
    })
self.assertEqual(preview["totals"], {
    "attempted": 8, "previewed": 4, "malformed": 0,
    "duplicate": 0, "skipped": 1, "prohibited": 3,
})
self.assertRegex(preview["payload_sha256"], r"^[0-9a-f]{64}$")
```

Assert two calls return identical canonical bytes. Assert `--output` creates a new file, permits an identical existing file, and refuses different bytes, symlinks, and non-regular paths. Parse the Phase 2 source files with `ast` and fail on imports or calls containing `supabase`, `psycopg`, `shared_ingest`, `embedding`, `proposition`, `retrieval`, `producer`, or `answer_toolbox`.

- [ ] **Step 2: Run preview tests and prove RED**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.PreviewCliTests -v`

Expected: FAIL because `scripts.preview_biblical_context_tooling` does not exist.

- [ ] **Step 3: Implement minimal orchestration and safe local publication**

Build the preview entirely from approved manifests and pinned fixture paths. Prohibited datasets are counted without opening a source content file or calling a parser. Compute `payload_sha256` over the preview without the checksum field, then serialize the complete preview canonically.

For `--output`, require the path to be under `local/`, create parents only under that resolved directory, open new files with exclusive creation and mode `0600`, and accept an existing regular single-link file only when its bytes are identical. Do not expose `--apply`, database parameters, URLs, or discovery options.

- [ ] **Step 4: Run preview tests and prove GREEN**

Run: `cd /Users/alexwhitley/newwine && python3.12 -m unittest scripts.test_biblical_context_parsers.PreviewCliTests -v`

Expected: PASS with exact counts, a stable checksum, three prohibitions, and no write-capable imports.

- [ ] **Step 5: Run the required dry run and isolated single-item verification**

Run: `cd /Users/alexwhitley/newwine && python3.12 scripts/preview_biblical_context_tooling.py --fixtures`

Expected: exit 0; canonical JSON reports five hidden registration rows, the exact reconciliation tuple, `database_write_authorized=false`, and the stable payload checksum. The test output must separately name the passing one-item TIPNR and OpenBible checks before the aggregate preview.

- [ ] **Step 6: Commit the preview slice**

```bash
cd /Users/alexwhitley/newwine && git add scripts/preview_biblical_context_tooling.py scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && git commit -m "feat(ingestion): preview biblical context tooling"
```

### Task 5: Coherent Phase 0–2 verification and scope audit

**Files:**
- Modify only if verification exposes an in-scope Phase 2 defect: files created in Tasks 1–4.

**Interfaces:**
- Consumes: all Phase 0–2 local artifacts.
- Produces: one verification record in the terminal handoff; no generated file or governing-record update.

- [ ] **Step 1: Run the complete required verification once**

```bash
cd /Users/alexwhitley/newwine && python3.12 scripts/test_biblical_source_manifests.py
cd /Users/alexwhitley/newwine && python3.12 scripts/test_source_use_policy.py
cd /Users/alexwhitley/newwine && python3.12 scripts/test_biblical_context_parsers.py
cd /Users/alexwhitley/newwine && python3.12 scripts/preview_biblical_context_tooling.py --fixtures
```

Expected: every command exits 0; the three test scripts print zero failures; preview counts and checksum match the pinned expectations.

- [ ] **Step 2: Verify forbidden scope is absent**

Run: `cd /Users/alexwhitley/newwine && git diff --check HEAD~3..HEAD`

Run: `cd /Users/alexwhitley/newwine && git diff --name-only HEAD~3..HEAD`

Expected: only Phase 2 scripts and fixtures appear; no migration, backend production module, governing record, retrieval/answer file, deployment file, or generated preview appears.

- [ ] **Step 3: Inspect the working tree without disturbing unrelated changes**

Run: `cd /Users/alexwhitley/newwine && git status --short`

Expected: no uncommitted Phase 2 files; pre-existing unrelated changes remain untouched. Do not stage or commit those unrelated paths.

- [ ] **Step 4: Stop at the Phase 2 boundary**

Report the exact acceptance results, reconciliation tuple, checksum, and commits. State explicitly that no database write, live registration, ingestion, visibility change, retrieval/answer-path change, deployment, or doctrinal decision occurred. Do not begin Phase 3 or Phase 6.
