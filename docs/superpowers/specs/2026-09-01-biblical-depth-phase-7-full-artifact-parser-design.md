# Biblical Depth Phase 7 — Full-Artifact Parser and Inventory Closure

**Date:** 2026-09-01

**Status:** APPROVED by Alex on 2026-09-01. Alex approved the Phase 7 pivot
after the pinned full TIPNR artifact exposed a mismatch between the fixture
grammar and the real artifact, and instructed the session to continue without
additional approval pauses. This approval covers repository-only design,
implementation planning, parser work, fixtures, tests, and zero-effect
inventory generation. It does not authorize an embedding request, database
write, ingestion batch, visibility change, feature enablement, live answer,
deployment, registry assignment, doctrinal decision, or PR merge.

## Outcome

Close the gap between the Phase 2 TIPNR fixture parser and the exact pinned
7,916,469-byte upstream artifact before any multi-item ingestion is designed.
Phase 7 must account deterministically for every marker-delimited record,
project only the existing Phase 0/2 allowlisted structured fields, quarantine
every non-eligible or malformed record with a stable reason, and produce an
immutable zero-write inventory plus embedding-cost projection.

Phase 7 is an ingestion-readiness phase, not an ingestion phase. A later phase
may design a resumable hidden batch only after this inventory closes without an
unexplained record, schema, rights, or count gap.

## Acceptance criteria

1. The only accepted input artifact has revision
   `02843f07cbb5009e00999a7c0efead6430dbb6e7`, byte length `7916469`, and
   SHA-256
   `69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e`.
2. A structural inventory accounts for every marker-delimited record in the
   artifact before projection. It resolves, rather than guesses around, the
   current discrepancy between the manifest's `entity_records: 4263` and the
   artifact's 4,262 observed `$==========` marker lines.
3. Marker syntax, primary-row shape, form-row significance, excluded
   directives, reference grammar, and whitespace variants are closed sets.
   Unknown future variants remain governing-contract failures.
4. Only `person` and `place` records may become eligible. `other`,
   `excluded_other`, `person+place`, headers, documentation records, and any
   unapproved marker class receive explicit non-eligible outcomes; none is
   coerced into an eligible type.
5. Eligible projections contain only entity type, source identifiers,
   original-language forms, and ordered OSIS references already allowed by the
   approved manifest. No display name, description, relationship, ambiguity
   prose, translation comparison, inferred fact, or generated text appears in
   output or diagnostic samples.
6. Known excluded directives such as the description family and
   `@Ambiguity` are recognized only to exclude them. Their values are never
   copied, hashed into public diagnostics, embedded, or used to infer fields.
7. Every record ends in exactly one stable outcome: eligible, skipped,
   malformed, duplicate, or prohibited. Hard schema failures stop the run and
   cannot be represented as a successful inventory.
8. The inventory freezes exact ordered record identities, record checksums,
   outcome reason codes, aggregate counts, aggregate checksum, rendered-byte
   estimate, embedding-request count, and maximum cost. It contains no
   timestamp, random value, machine path, credential, or excluded source text.
9. Repeated runs over the same pinned bytes are byte-identical. A one-byte
   artifact mutation, reordered record, duplicate identity, new directive,
   new significance value, new marker, or row-width change fails or changes the
   exact expected checksum and is caught by tests.
10. The inventory command has no apply flag and cannot import database,
    embedding, proposition, retrieval, answer, or deployment modules. It makes
    no network call; the artifact path is explicit.
11. The existing Phase 6 `H0175` projection remains byte-identical, and all
    Phase 0–6 regression suites remain green.
12. Phase 7 stops at an ingestion-ready inventory. No later batch may begin
    without a separate design, dry run, named cost ceiling, attended approval,
    bounded execution, and fresh reconciliation.

## Non-goals

- No source registration or correction; the hidden `stepbible-tipnr` source
  already exists and remains hidden.
- No embedding request, database connection, database write, policy-row write,
  ingestion-completion stamp, batch, backfill, or retry of Phase 6.
- No OpenBible ingestion or parser expansion.
- No source visibility, retrieval, prompt, generation, answer-path, cache,
  feature-flag, deployment, or attribution-surface change.
- No doctrinal decision, protected-source assignment, viewpoint-slot naming,
  source-to-viewpoint assignment, or house-paper change.
- No widening of Phase 4's protected-source boundary, separately labeled
  general-reference context, two-distinct-source plural rule, neighbor
  rechecking, cache isolation, or house-paper-as-fence-only rule.
- No extraction of excluded prose or use of an LLM to interpret ambiguous
  records.
- No silent correction of the governing manifest. A manifest count or grammar
  replacement must be evidence-backed, preserve the approved field boundary,
  and live in a docs-only commit separate from parser code.

## Read-only discovery

The exact artifact was downloaded from the approved STEPBible revision into a
temporary directory. Its byte length and SHA-256 match the approved manifest.
No repository source file, database, model, or production service was changed.

The artifact contains 4,262 marker lines with this exact-syntax distribution:

- 3,132 `$========== PERSON(s)` markers;
- 1,003 `$========== PLACE` markers;
- 102 `$========== OTHER` markers;
- 12 `$========== EXCLUDED OTHER` markers;
- 10 `$========== PERSON+PLACE` markers;
- one `$==========PERSON(s)` marker;
- one `$==========PLACE` marker; and
- one `$==========OTHER` marker.

The Phase 2 aggregate parser stops on the first `row_shape_changed`. A
diagnostic-only per-record pass, which is not an accepted inventory, reached
2,928 records and refused 1,334: 1,009 row-shape failures, 173 unknown
significance values, 58 unknown directives, 22 unknown entity markers, 62
invalid form identities, eight invalid OSIS-reference values, and two invalid
entity identities. Of the records reached by the existing parser, 2,830 were
people and 98 were `other`; ordinary place records were not reached because
their primary rows use the real artifact's eight-column shape while the fixture
contract requires nine.

The discovery proves that selecting the currently parseable subset would make
implementation accidents decide corpus coverage. It also proves that a full
batch cost cannot be named honestly until parser coverage and deterministic
quarantine outcomes close.

## Considered approaches

### 1. Full-artifact structural inventory, then allowlisted projection — chosen

Use a two-pass pipeline. The first pass validates and inventories every
record's structural grammar without retaining excluded content. The second
pass projects only records whose marker, row shape, identifiers, form rows, and
references satisfy the existing field allowlist. Every other known record is
reason-coded; any unknown schema aborts.

This makes the eligible set a reviewable result of the approved contract rather
than a side effect of which records happen to parse.

### 2. Batch the currently parseable subset — rejected

This would privilege 2,830 people merely because the fixture resembles their
rows, exclude places because of an unmodeled column count, and conceal 1,334
known failures behind a superficially successful batch.

### 3. Select an arbitrary fixed tranche — rejected

A hand-picked first 100 or 500 records could cap cost, but it would defer the
known global grammar mismatch and provide no principled proof that later
records share the same rights, structure, or error behavior.

## Architecture

### Pinned artifact verifier

The command accepts one explicit path and validates byte length and SHA-256
before parsing. It does not discover directories or download content. A
different revision, checksum, or size is refused before any record is read.

### Structural scanner

The scanner splits marker-delimited records and produces a closed structural
profile containing only:

- normalized marker class and exact marker-shape identity;
- primary-row column count;
- form-row significance token and column count;
- excluded-directive key, never its value;
- presence of unrecognized line shapes; and
- source-order record ordinal.

The scanner must distinguish source documentation/header material from entity
records using explicit evidence from the pinned artifact. It cannot discard a
leading or trailing record merely to make the manifest count agree.

### Allowlisted projector

The projector consumes validated structural records. It has marker-specific
closed schemas instead of one assumed universal row width. It extracts only the
already-approved identity, type, original-language form, and OSIS-reference
fields.

Known non-output structures are handled explicitly:

- `Total` rows are excluded;
- description and ambiguity directives are discarded by key;
- `OTHER` and `EXCLUDED OTHER` are skipped;
- `PERSON+PLACE` is quarantined rather than split or inferred;
- group-like, reused-form, variant, or abbreviated-reference structures are
  eligible only when the existing allowed fields can be recovered without
  interpreting a relationship or ambiguity; otherwise the whole record is
  quarantined with one stable reason.

The design does not pre-approve `Group` or any other newly observed
significance value. Implementation must characterize each value structurally
and either map it to the already-approved form-row grammar or quarantine it.

### Inventory compiler

The compiler sorts eligible records by their immutable source identity while
preserving form and reference order inside each record. It emits:

- artifact identity and checksum;
- total structural records;
- exact outcome counts and reason counts;
- eligible counts by entity type;
- per-record identity, outcome, reason, and canonical checksum;
- aggregate eligible checksum;
- canonical rendered bytes and predicted one-embedding-per-record count; and
- cost projection using a separately recorded price and conservative ceiling.

The full per-record inventory is written only under gitignored `local/` with
create-new semantics. A compact repository fixture freezes expected counts,
reason codes, and checksums without including excluded prose.

### Cost boundary

Phase 7 performs no embedding. After eligible inventory closes, cost is
computed from the exact canonical rendered bytes and a documented current
`text-embedding-3-small` price. The inventory reports both the mathematical
estimate and a higher explicit maximum ceiling for a later approval packet.
No cost estimate authorizes a model call.

## Error and containment behavior

- **Artifact mismatch:** stop before parsing.
- **Known non-eligible structure:** record one deterministic outcome and
  continue.
- **Malformed allowed fields:** quarantine the whole record; never retain a
  partial projection.
- **Duplicate entity identity:** quarantine every conflicting occurrence or
  fail the inventory according to one frozen rule; never merge.
- **Unknown marker, directive, significance, row width, or line shape:** hard
  fail as schema drift.
- **Count or checksum disagreement:** hard fail; do not regenerate expected
  values automatically.
- **Manifest discrepancy:** report both observed and recorded counts until the
  evidence-backed governing replacement is committed; never normalize one to
  the other in code.

## Testing strategy

Implementation follows red-green-refactor in four increments:

1. Artifact identity and structural-scanner tests using compact structural
   fixtures for every observed marker and row profile.
2. Marker-specific allowlisted projection tests, including explicit exclusion
   and quarantine cases for every newly observed structural variant.
3. Full pinned-artifact inventory tests proving exact counts, reason counts,
   deterministic checksums, and no excluded text in output.
4. Capability and regression tests proving zero network/database/model access,
   exact Phase 6 `H0175` stability, and all Phase 0–6 contracts.

Mutation tests must show that removing each closed-set guard admits a fixture
the suite rejects. Tests must not calculate expected values with the production
parser or assert merely that source code contains a string.

## Commit and execution boundaries

- This design and its later implementation plan are docs-only work.
- Parser, fixtures, inventory compiler, and tests form one or more build
  commits, separate from governing records.
- Any necessary manifest or roadmap replacement is a docs-only commit after
  exact full-artifact evidence exists.
- Generated full inventories remain ignored under `local/`.
- No commit or push authorizes model spend, database access, ingestion,
  visibility, feature activation, deployment, or merge.

## Stop condition

Phase 7 stops when the exact pinned artifact is fully accounted for, every
record has one deterministic outcome, all eligible projections preserve the
existing field boundary, the inventory and cost projection are byte-stable,
and all Phase 0–6 regressions pass. The next item is a separately designed and
approved hidden batch packet, not automatic execution.
