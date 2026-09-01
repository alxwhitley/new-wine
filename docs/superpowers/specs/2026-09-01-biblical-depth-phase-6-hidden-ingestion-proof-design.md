# Biblical Depth Phase 6 — Hidden Single-Slice Ingestion Proof

**Date:** 2026-09-01

**Status:** COMPLETE through the attended hidden production proof. Alex
separately approved the exact hidden `stepbible-tipnr` registration, one
`text-embedding-3-small` request under `$0.01`, and one atomic `H0175`
transaction on 2026-09-01. Alex then separately approved the repository-only
reconciliation remediation and this governing-text replacement. No larger
batch, visibility change, feature enablement, live answer, deployment, registry
assignment, or PR merge is authorized.

## Outcome

Build and execute one attended, fail-closed ingestion proof for the
already-approved STEPBible TIPNR structured-data boundary. The proof stores
exactly one eligible entity, Aaron (`H0175`), in one atomic hidden transaction
while keeping all retrieval and answer behavior unchanged.

## Acceptance criteria

1. The only eligible proof input is the Phase 2 canonical TIPNR Aaron record
   with entity ID `H0175` and its pinned record checksum.
2. The dry run predicts exactly one source, one alias, one document, one chunk,
   and one current passage-policy row without making a database write, network
   request, embedding request, proposition request, or answer request.
3. The proposed source is exactly `STEPBible TIPNR` / `stepbible-tipnr`, with
   alias `stepbible tipnr`, `license_status='licensed'`, and explicit
   `visibility='hidden'`.
4. The document is exactly `source_kind='biblical_context'`,
   `citation_mode='citable'`, is attributed to the exact new source ID, and
   contains only the Phase 0/2 allowlisted entity type, identifiers, original-
   language forms, and OSIS references.
5. The document produces exactly one canonical chunk and one embedding request
   using `text-embedding-3-small`, with a declared maximum spend of `$0.01`.
6. Proposition extraction is structurally unavailable on this path; no
   proposition, paraphrase, doctrinal interpretation, or generated enrichment
   can be written.
7. The chunk receives exactly one current deterministic
   `policy_class='general_context'` row in the same transaction, with no
   protected topic, issue, viewpoint, model, or prompt metadata.
8. Registration, alias creation, document insertion, chunk insertion, policy
   insertion, and ingestion-completion stamping either commit together or roll
   back together.
9. A retry recognizes the exact completed proof as a verified no-op and fails
   closed on every partial, conflicting, duplicate-current-policy, or checksum-
   mismatched state.
10. A fresh `newwine_readonly_analysis` connection can reconcile an approved
    single-item run as attempted `1`, stored `1`, errored `0`, skipped `0`, and
    can prove exact identity, attribution, row counts, classification
    provenance, and hidden visibility.
11. The hidden source cannot appear through the existing retrieval RPC gates in
    either safe-mode state. `BIBLICAL_CONTEXT_ANSWER_ENABLED` remains
    default-off, and protected/plural registries remain empty.
12. Existing Phase 0–5 tests remain green.

## Non-goals

- No additional production execution is authorized by the completed proof.
- No OpenBible item, second TIPNR entity, full batch, backfill, or download.
- No source visibility change, retrieval release, answer-path enablement, live
  answer, deployment, or attribution-surface release.
- No proposition extraction or other generative model call.
- No doctrinal decision, protected-source assignment, viewpoint-slot naming,
  source-to-viewpoint assignment, or house-paper change.
- No change to Phase 4's pre-writer routing, exact protected-source boundary,
  general-context labeling, two-distinct-source plural rule, cache isolation,
  neighbor rechecking, or house-paper-as-fence-only behavior.
- No correction of the existing `STEPBible` license row.
- No migration or schema change. Migration 097 is already applied and remains
  unchanged.
- No deletion or mutation of committed passage-policy history.

## Read-only findings

- The Phase 2 fixture preview emits Aaron as one deterministic `person` record
  containing Hebrew form `H0175`, Greek form `G0002`, four OSIS references,
  and record checksum
  `78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6`.
- The approved source-registration packet defines the exact source name, slug,
  alias, license, visibility, document defaults, credit, and pinned upstream
  STEPBible revision `02843f07cbb5009e00999a7c0efead6430dbb6e7`.
- Fresh production reads found no collision for the proposed source name, slug,
  alias, or proof-document identity. `source_passage_policy_versions` was
  empty at the diagnostic boundary.
- `sources.retrievable` is generated from license status; hidden containment is
  enforced by the existing RPC requirement that licensed sources also have
  `visibility='shown'`. The proof therefore sets `visibility='hidden'`
  explicitly and verifies the RPC boundary rather than asserting that the
  generated `retrievable` column is false.
- `scripts/shared_ingest.py` always passes licensed sources through
  `propositions.process_document()`. Thin text currently avoids the model by a
  word-count gate, but relying on content length is not a safe or durable
  prohibition on proposition generation.
- Migration 097 makes policy history append-only and gives its chunk foreign key
  `ON DELETE RESTRICT`. Transaction rollback is available before commit; after
  commit, hidden containment and separately approved corrective history are the
  safe response to a discrepancy.

## Chosen architecture

### Dedicated proof writer

Use a dedicated structured-context proof module instead of adding a generic
"skip propositions" switch to `shared_ingest.py`. The module may reuse narrow,
pure helpers such as the shared embedding client, but it owns its database
transaction and never imports or calls `scripts/propositions.py`.

This keeps the new exception unavailable to ordinary licensed prose. It also
lets passage-policy persistence participate in the same transaction as the
document and chunk, which the existing shared writer does not support.

### Rejected alternatives

1. **Extend `shared_ingest.py` with a proposition-disable flag.** Rejected
   because a broad caller-controlled bypass would weaken the existing licensed-
   prose contract and expand Phase 6 beyond one structured dataset proof.
2. **Use the existing writer and insert the policy row afterward.** Rejected
   because licensed content could reach proposition extraction and a second
   transaction could leave a committed chunk without its required current
   policy row.
3. **Mislabel the source as public-domain to reuse the existing proposition
   gate.** Rejected because it would record false rights metadata and conflict
   with the approved CC BY 4.0 registration packet.

## Canonical proof artifact

The proof builder consumes the existing Phase 2 canonical parser output, never
the raw TIPNR file directly. It selects the record only when all of these match:

- source slug: `stepbible-tipnr`;
- entity ID: `H0175`;
- entity type: `person`;
- upstream revision:
  `02843f07cbb5009e00999a7c0efead6430dbb6e7`;
- record SHA-256:
  `78d6effc18c08911639e0e7240070564eed755037124268a4824cf3c719cc4d6`.

The canonical renderer has a fixed field order and emits only:

1. dataset title and pinned revision;
2. entity ID and type;
3. each approved language identifier and original-language form in parser
   order; and
4. each approved OSIS reference in parser order.

It emits no descriptions, relationships, translation comparisons, inferred
facts, coordinates, cross references, or generated prose. The exact rendered
bytes and their SHA-256 are reported by dry run and become the immutable
document identity for reconciliation.

The proposed document path includes the dataset slug, upstream revision,
entity ID, and record checksum. This makes provenance inspectable without a new
schema column. The document uses the official dataset URL already preserved by
the approved manifest and registration packet.

## Deterministic database projection

The plan must freeze exact UUIDs for the source, alias relationship, document,
and chunk before any apply-capable implementation is considered complete.
UUIDs are derived with UUIDv5 from a repository-owned Phase 6 namespace and
immutable identity strings. The policy row may use a generated UUID because its
unique current-row identity is the deterministic chunk ID plus `is_current`,
but the apply report must capture its resulting ID.

The English label “Aaron” is used only to identify the chosen fixture in this
design. It is not present in the Phase 2 canonical record and must not be
recovered from an excluded raw field or stored. The single document has:

- title derived only from the TIPNR dataset name, entity type, and `H0175`;
- `source_name='STEPBible TIPNR'`;
- `source_type='reference'`;
- `source_kind='biblical_context'`;
- `citation_mode='citable'`;
- `is_copyrighted=true`;
- exact source UUID, approved canonical URL, canonical file path, ordered Bible
  references, and canonical rendered text;
- exactly one chunk at `chunk_index=0`; and
- `ingest_completed_at` set only after all staged row checks pass.

The current passage-policy row has:

- `policy_class='general_context'`;
- `protected_topic_keys='{}'`;
- `issue_key=NULL` and `viewpoint_key=NULL`;
- `classifier_kind='deterministic'`;
- `rule_version='biblical_context_structural_v1'`;
- `model=NULL` and `prompt_fingerprint=NULL`;
- `reason_codes=ARRAY['phase0_allowlisted_structural_fields']`;
- `is_current=true`.

## Command and authorization contract

The CLI has two modes with different capabilities.

### Preview mode

Preview is the default and has no apply flag. It:

- loads only pinned fixtures and approved manifests;
- builds and validates the canonical projection;
- uses the read-only analysis role only when live collision checks are
  explicitly requested;
- never reads a write-capable database credential;
- never imports the embedding client;
- prints exact identities, hashes, counts, estimated input size, embedding-call
  count `1`, and maximum spend `$0.01`;
- reports `database_write_authorized=false` and
  `external_model_call_authorized=false`.

### Apply mode

Apply is a separate command/module, not a preview flag. It refuses to start
unless an attended approval artifact names the exact source slug, entity ID,
record checksum, maximum spend, and operation date. Repository implementation
and a successful dry run are not that approval artifact.

The apply command first repeats every local validation and read-only collision
check. It then makes the one embedding request before opening a write
transaction. If the embedding request fails, no database write connection is
opened.

No batch option, wildcard, directory discovery, limit parameter greater than
one, source-selection argument, or alternate entity ID exists in Phase 6.

## Atomic transaction and reconciliation

Inside one short transaction, the writer:

1. sets a local statement timeout;
2. rechecks source name/slug, alias, document identity, chunk identity, and
   current-policy collisions under the write connection;
3. inserts the exact hidden source and alias;
4. inserts the exact document and its one embedded chunk;
5. inserts the exact deterministic general-context policy row;
6. queries the staged rows back and verifies all identities, counts, foreign
   keys, visibility, classification metadata, and embedding dimensions;
7. stamps `ingest_completed_at`; and
8. commits.

Any exception or mismatch before commit rolls back all six row families. The
writer returns a hard reconciliation object with `attempted`, `stored`,
`errored`, and `skipped`; it asserts that their sum equals `attempted`.

After commit, exact row and metadata reconciliation uses a fresh
`newwine_readonly_analysis` connection. The two retrieval RPC probes use a
separate fresh service-database connection because both security-invoker RPCs
read `app_settings`, which the analysis role cannot select. Both
connections call `set_session(readonly=True, autocommit=True)` before their
first query and must independently observe `transaction_read_only='on'`.
Together they verify:

- exact source, alias, document, chunk, and current-policy counts;
- exact hashes, source attribution, license metadata, and hidden visibility;
- exactly one 1536-dimension embedding and no propositions for the document;
- the same four ordered OSIS references on both the document and its single
  chunk;
- no protected topics, issue, or viewpoint metadata;
- no second current policy row;
- no visibility or feature-flag change; and
- nonappearance through the existing retrieval boundary.

The final report must be retained at
`local/2026-09/biblical_context_v1_proof.json`; `local/` remains uncommitted.

## Retry, discrepancy, and containment behavior

- **Clean state:** insert the exact proof.
- **Exact complete state:** perform no model call and return attempted `1`,
  stored `0`, errored `0`, skipped `1`, reason `exact_proof_already_complete`.
- **Any partial state:** fail before model spend and write nothing.
- **Any identity or checksum conflict:** fail before model spend and write
  nothing.
- **Embedding succeeds but transaction fails:** report the bounded spend and
  errored `1`, then use a fresh read-only connection to distinguish clean
  rollback from an ambiguous commit that actually landed.
- **Fresh reconciliation fails after commit:** emit a structured
  `committed_reconciliation_failed` report that preserves the apply result,
  stop, and never retry the embedding or transaction. Do not delete or rewrite
  append-only policy history. The hidden source and default-off feature contain
  the data while a separately approved remediation is designed.

## Production proof result

The approved operation committed exactly one hidden source, one alias, one
attributed `biblical_context` document, one 1536-dimension chunk, and one
current deterministic `general_context` policy row. The policy ID is
`4e3169db-2aaf-4f0f-91e0-fc7c3a234625`; no proposition row exists for the
document.

The initial post-commit verifier stopped because `newwine_readonly_analysis`
could execute the retrieval RPCs but could not read their security-invoker
`app_settings` dependency. No write or embedding retry occurred. Build commit
`494175e` split exact-state and retrieval verification across two enforced
read-only sessions and preserved structured apply evidence on any future
verifier failure. Fresh production reconciliation then passed with attempted
`1`, stored `1`, errored `0`, skipped `0`; vector and full-text retrieval each
returned zero. The canonical ignored reconciliation artifact is retained at
`local/2026-09/biblical_context_v1_proof.json` with SHA-256
`fc749e7b68db61c0984073a13ed298027d7ca775679f37130bd2959547de368f`.

## Test contract

Implementation follows red-green-refactor and must prove:

- exact Aaron selection and rejection of every other or mutated record;
- byte-identical canonical rendering and hashes across repeated runs;
- exact UUID/document/chunk identity derivation;
- exact source/document/policy projection;
- preview makes no network, model, embedding, write-credential, or write-DB
  access;
- the apply module cannot select more than Aaron or operate without an exact
  approval artifact;
- proposition code is neither imported nor called;
- embedding failure precedes any write connection;
- transaction ordering, staged reconciliation, commit, and rollback behavior;
- exact-complete retry skips before embedding;
- partial/conflicting state fails before embedding;
- fresh reconciliation detects every count, metadata, visibility, policy, and
  proposition violation;
- the default-off answer flag and empty registries remain unchanged; and
- all Phase 0–5 regression suites pass.

Production is never used as a test environment. Database transaction tests use
fakes that record SQL order and commit/rollback behavior; live access before
approval is read-only diagnostics only.

## Commit and execution boundaries

- The approved design and implementation plan form one docs-only commit.
- Phase 6 code and tests form a separate build commit.
- Any later session/status closure is a separate docs-only commit.
- No commit or push implies authorization to run apply mode.
- Before any later batch, the project-wide dry-run and single-item verification
  rule applies again. This Phase 6 proof is not batch authorization.

## Stop condition

Repository work stops when the tooling is implemented, the complete local test
suite passes, and the zero-write/zero-model-spend preview produces its expected
single-item report. The next step is an attended production-operation packet,
not automatic execution.
