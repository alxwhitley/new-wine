# Biblical Depth Phase 2 Hidden Tooling Design

**Date:** 2026-09-01

**Status:** Approved by Alex on 2026-09-01, including the eight implementation
judgments recorded below. This document authorizes repository-only implementation.
It does not authorize any database write, live source registration, ingestion,
visibility change, retrieval or answer-path change, deployment, or doctrinal
content decision.

## Outcome

Build deterministic, manifest-first, zero-database-write tooling that compiles
the approved Phase 0 source dispositions and pinned Phase 2 source samples into
a frozen hidden-registration and ingestion preview.

The tooling establishes a reproducible handoff for later attended registration
and ingestion work. It does not perform that later work and does not provide an
apply mode.

## Acceptance criteria

1. The registration preview exactly reproduces the approved source names,
   slugs, aliases, license metadata, and explicit `visibility: hidden` values
   from the Phase 0 manifests.
2. The TIPNR parser emits only the approved entity type, source identifiers,
   original-language form, and OSIS-reference fields.
3. The OpenBible parser reads only `data/ancient.jsonl` records and emits only
   the approved place identifier, label, type, OSIS-reference, and qualified
   candidate-identification fields.
4. Tyndale content and OpenBible cross references are represented in the
   registration preview but are refused as `prohibited_in_v1` ingestion inputs.
5. Unknown, malformed, doctrinal, free-form, mixed-rights, and otherwise
   unapproved fields fail closed. No unrecognized input field is copied through.
6. Repeated runs over the pinned fixtures produce byte-identical canonical
   output and identical SHA-256 checksums.
7. The dry-run result reports exact `attempted`, `previewed`, `malformed`,
   `duplicate`, `skipped`, and `prohibited` counts and lists deterministic reason
   codes for every non-previewed item.
8. One pinned TIPNR item and one pinned OpenBible item pass isolated single-item
   verification before the aggregate fixture preview is accepted.
9. Tests prove that the Phase 2 tooling makes no database, network, embedding,
   or model calls and imports no retrieval or answer-path module.
10. Existing Phase 0 manifest tests and Phase 1 source-use policy tests remain
    green.

## Non-goals

- No production or local database access or writes.
- No live source registration, alias creation, source correction, or ingestion.
- No database migration or write-capable `--apply` command.
- No live source download or corpus-scale processing.
- No correction of the existing STEPBible source row.
- No passage-policy persistence or classification-table work.
- No source visibility, retrieval, answer-path, prompt, attribution-surface, or
  deployment change.
- No doctrinal position, viewpoint-slot, protected-source, or house-material
  decision.
- No parsing of Tyndale prose, OpenBible cross references, TIPNR descriptions,
  or any other Phase 0 exclusion.

## Governing source policy

The Phase 0 manifests are the machine-readable authority. The parser may not
infer permission from an open license, a source name, or a field that appears
factual. A field is eligible only when its exact raw path and output projection
are allowlisted by an approved manifest disposition.

The two Phase 1 policy axes remain independent and unchanged:

- the source boundary separates `protected_spirit_filled` from `general`; and
- the presentation stance separates house, shared, plural, and uncertain
  treatment.

Phase 2 does not route questions or make source material answer-eligible. The
protected charismatic neighborhood continues to come only through
Alex-approved house material and approved protected sources. General biblical
and historical context, plus plural presentations of other orthodox disputes,
remain governed by the Phase 1 policy and later release gates.

## Architecture

### Manifest compiler

A shared deterministic module loads the four approved Phase 0 YAML manifests,
validates their approval and no-authorization boundaries, and exposes two
projections:

1. a hidden-registration preview containing only exact proposed source rows and
   aliases; and
2. an ingestion policy projection identifying eligible datasets, input files,
   raw-field allowlists, output-field allowlists, and prohibited datasets.

The compiler refuses manifests that are unapproved, authorize a Phase 2 write,
omit explicit visibility, propose non-hidden new rows, or contain an unsupported
schema version.

The registration preview includes every approved proposed hidden row: the two
V1-eligible datasets plus the three provenance-only or prohibited rows. It
labels the latter `prohibited_in_v1` so registration intent cannot be mistaken
for ingestion permission. Phase 2 does not assign source UUIDs; a later attended
registration operation must inspect live state and freeze exact identifiers.

### Dataset parsers

The TIPNR and OpenBible parsers consume explicit input paths and return
canonical in-memory records. They do not discover files, download sources, read
credentials, or connect to services.

Each parser has two layers:

- a single-record parser that validates and projects one source item; and
- an aggregate parser that records counts, duplicates, malformed items, skips,
  prohibitions, reason codes, and an output checksum.

Parser results retain source identity and approved provenance labels but do not
create database-shaped documents, chunks, embeddings, propositions, or passage
policy rows. This avoids prematurely coupling Phase 2 to the later ingestion
schema.

TIPNR emits one entity record with an ordered list of its original-language
forms rather than one record per form. `person` and `place` are V1-eligible;
recognized `other` entities are parsed sufficiently to account for them and
then recorded as `skipped:not_v1_entity_type`.

Known excluded source fields are explicitly recognized and discarded. A newly
appearing structural field that is absent from the pinned schema aborts parsing
as schema drift; it is not silently ignored. This distinction permits the
approved source format while preventing future upstream additions from
quietly widening the projection.

### Preview orchestration

A zero-write CLI compiles the registration preview and parser summaries into
canonical JSON. Its default mode prints the result. An optional output path may
write only a local preview artifact using create-new semantics: it refuses to
replace a file whose bytes differ.

The preview is not an ingestion manifest for an apply command. It is evidence
for the later design of Phase 6 and carries an explicit
`database_write_authorized: false` boundary.

Generated previews are not committed. Tests compare canonical bytes and pinned
checksums in memory; later operational artifacts belong under gitignored
`local/`. Phase 2 intentionally contains no apply mode, so Phase 6 requires a
separately reviewed write-capable workflow.

## File scope

Expected implementation files:

- `scripts/biblical_context_tooling.py`
- `scripts/parse_tipnr_context.py`
- `scripts/parse_openbible_context.py`
- `scripts/preview_biblical_context_tooling.py`
- `scripts/test_biblical_context_parsers.py`
- pinned fixtures under `scripts/fixtures/biblical_context/`

Phase 0 manifests may be modified only if implementation exposes an internal
inconsistency in an already approved disposition. Any such change must preserve
Alex's recorded decision and requires an explicit explanation before editing.

No existing production code, migration, retrieval module, answer module,
governing record, or deployment configuration is in scope.

## Canonical output and identity

Canonical JSON uses UTF-8, sorted keys, compact separators, and one trailing
newline. Arrays whose source order is not meaningful are sorted by stable source
identity before hashing. Arrays whose order carries source meaning preserve that
order and document the rule in their parser.

Every eligible output record includes:

- the manifest `dataset_id`;
- the pinned source artifact revision or snapshot identifier;
- the source item identity;
- the exact projected fields;
- deterministic reason codes, when applicable; and
- a SHA-256 checksum over its canonical representation.

The aggregate checksum covers the ordered canonical eligible records, not
diagnostic timestamps or machine-specific paths. Phase 2 output contains no
wall-clock timestamp, random identifier, or environment-dependent value.

## Fail-closed behavior

Validation errors are data outcomes when they concern one source item and hard
failures when they concern the governing contract.

- A malformed eligible record increments `malformed` with a stable reason code.
- A repeated source identity increments `duplicate`; it is never merged.
- An explicitly prohibited dataset increments `prohibited`; no parser is called.
- A structurally recognized but intentionally excluded item increments
  `skipped` with its exclusion reason.
- An unknown dataset, manifest schema, approval state, visibility, raw field,
  output field, or authorization boundary aborts the preview.

The preview exits nonzero on a governing-contract failure, checksum mismatch, or
unexpected count. Item-level refusals may be represented in a successful dry
run only when their exact expected counts and reasons are pinned by the fixture
test.

## Test design

Tests follow red-green-refactor in three increments:

1. Manifest compilation and hidden-registration projection.
2. Single-item TIPNR and OpenBible parsing, including fail-closed mutation
   fixtures.
3. Aggregate preview, reconciliation counts, duplicate handling, and
   byte-identical repeatability.

The tests monkeypatch or tripwire common database, network, model, embedding,
and ingestion entry points where applicable. Static assertions also ensure the
tooling does not import `shared_ingest`, Supabase clients, retrieval modules, or
answer modules.

Pinned happy-path fixtures are minimal excerpts from the real approved source
formats and record their upstream revision and checksum. Synthetic fixtures
cover malformed rows, schema drift, excluded fields, duplicates, and other
mutations without expanding the licensed source excerpt.

The coherent verification cycle is:

```text
python3.12 scripts/test_biblical_source_manifests.py
python3.12 scripts/test_source_use_policy.py
python3.12 scripts/test_biblical_context_parsers.py
python3.12 scripts/preview_biblical_context_tooling.py --fixtures
```

When commands are handed to Alex, each command will begin with
`cd /Users/alexwhitley/newwine &&` as required.

## Stop condition and later handoff

Phase 2 stops when all acceptance criteria pass and the canonical fixture
preview is reported. The result does not authorize a full batch or any database
operation.

Before a later batch, the repository contract still requires a separately
designed and approved write-capable workflow, a zero-write dry run, one isolated
hidden proof, exact reconciliation from a fresh read, and Alex's explicit
attended approval. Source visibility, retrieval eligibility, and answer-path
release remain separate gates after ingestion.
