# Biblical Depth Phase 8 — Hidden Balanced TIPNR Pilot

**Date:** 2026-09-01

**Status:** APPROVED for repository-only design, implementation planning,
tooling, fixtures, tests, dry-run generation, and read-only diagnostics. Alex
instructed the session to continue without additional approval pauses. This
approval does not authorize an embedding request, database write, batch
execution, visibility change, feature enablement, live answer, deployment,
registry assignment, doctrinal decision, or PR merge.

## Outcome

Build an attended, fail-closed packet for exactly 20 additional hidden TIPNR
records: the first 10 eligible people and first 10 eligible places by immutable
entity ID after excluding the already-stored Phase 6 proof `H0175`. Phase 8
must freeze the selection, render and price it exactly, prove the existing
hidden source and `H0175` state read-only, and provide separately gated apply
and reconciliation tooling.

Phase 8 implementation stops at execution readiness. A later attended
production operation requires a same-day approval artifact naming the exact
packet checksum, request count, maximum spend, and one database transaction.

## Acceptance criteria

1. The packet accepts only TIPNR revision
   `02843f07cbb5009e00999a7c0efead6430dbb6e7`, artifact SHA-256
   `69f69d80d8a329576915a397d815bd6ff1849d8954d071c57b0ac4453aee180e`,
   Phase 7 inventory hash
   `edb6dece3a9d2772ec9dfb21a80d192225ec14878084e5b30cb38ea667b80040`,
   and eligible checksum
   `1c7fdf4f7d587fdcfa7cf076732f913ef9b1066d50a0a5de9e227c7c1cf80cc2`.
2. Selection is derived from the full Phase 7 eligible set by excluding
   `H0175`, sorting independently by entity ID within `person` and `place`,
   taking the first 10 of each, then canonicalizing the packet by entity type
   and entity ID. No operator-supplied ID, offset, limit, wildcard, or alternate
   source exists.
3. The packet contains exactly the 20 entity IDs and record checksums frozen in
   this design, with 10 people, 10 places, selection checksum
   `398fa80f93fc4c7464a22ca110d9a4546c60d4667f04ba2a3aebafb18ad8fb2`,
   and Phase 7 canonical projection bytes `8069`.
4. Each item produces exactly one attributed document, one chunk, one
   embedding request, and one current deterministic `general_context` policy
   row. The existing source and alias are verified but never reinserted.
5. Rendering contains only dataset/revision, entity type and ID, approved
   language identifiers and original-script forms, and ordered OSIS
   references. It contains no display name, description, relationship,
   ambiguity value, translation comparison, inference, or generated text.
6. The packet builder freezes deterministic UUIDv5 document/chunk identities,
   file paths, rendered hashes, ordered references, and policy projections for
   all 20 items before any apply-capable dependency is loaded.
7. Zero-effect preview imports no database, model, embedding, proposition,
   retrieval, answer, or deployment module. It reports both authorization
   booleans false and cannot accept an apply flag.
8. A separate read-only preflight proves the exact hidden `stepbible-tipnr`
   source and alias, the exact completed `H0175` proof, all 20 candidate states,
   migration-097 policy availability, default-off feature state, and empty
   protected/plural registries. It opens no write credential and makes no model
   call.
9. Candidate state is accepted only when all 20 items are clean or all 20 are
   exact-complete. A mixture, partial row family, conflicting identity,
   duplicate-current policy, proposition, checksum mismatch, source drift, or
   unstamped document fails before model spend.
10. Apply validates a regular, same-day approval artifact naming Alex, the
    exact packet checksum, 20 embedding requests, `text-embedding-3-small`,
    1536 dimensions, maximum spend USD `0.01`, and one atomic database
    transaction. Repository work and dry-run success are not that artifact.
11. Apply re-runs local validation and read-only preflight before loading model
    or write dependencies. An all-exact-complete retry performs no embedding or
    write and reconciles as attempted `20`, stored `0`, errored `0`, skipped
    `20`.
12. On a clean state, all 20 embeddings are validated in memory before a write
    connection opens. Any request failure or invalid vector prevents every
    database write while reporting the exact completed request count and
    bounded spend exposure.
13. One short transaction inserts exactly 20 documents, 20 chunks, and 20
    current policy rows, stages and verifies all identities/counts/metadata,
    stamps all 20 documents complete, and commits once. Any mismatch rolls back
    all 60 rows.
14. Fresh reconciliation uses the dedicated analysis role for exact identity
    and a separate connection forced read-only for retrieval probes. It reports
    attempted, stored, errored, and skipped with a hard sum check, proves zero
    propositions, and executes vector and FTS hidden-retrieval probes for every
    new document (40 probes total).
15. Quality evidence mechanically validates all 20 projections and freezes a
    six-item human-readable sample: person IDs `G0010`, `G0132`, `G0223J` and
    place IDs `G0009`, `G0137`, `G0494`. Sampling checks attribution, type,
    identifiers, forms, references, and exclusion of non-allowlisted text; it
    makes no doctrinal judgment.
16. Phase 0–7 tests and exact Phase 6 `H0175` identities remain unchanged.
    `BIBLICAL_CONTEXT_ANSWER_ENABLED` remains default-off, the source remains
    hidden, protected/plural registries remain empty, and Phase 4 routing,
    cache, neighbor, plurality, and house-paper boundaries remain intact.

## Non-goals

- No production embedding request, database connection, write, or pilot
  execution during repository implementation.
- No full 3,959-item TIPNR batch and no automatic continuation to the remaining
  3,938 not-yet-stored eligible items after the 20-item pilot.
- No retry, mutation, or re-ingestion of the existing `H0175` proof.
- No OpenBible item, malformed TIPNR remediation, or reconsideration of
  skipped/prohibited records.
- No source or alias creation; the exact hidden Phase 6 rows must already exist.
- No proposition extraction, paraphrase, summary, inferred fact, or other
  generative call.
- No source visibility, retrieval policy, prompt, answer-path, cache,
  feature-flag, deployment, attribution-surface, or release change.
- No doctrinal decision, protected-source assignment, viewpoint-slot naming,
  source-to-viewpoint assignment, or house-paper change.
- No weakening of the pre-writer fail-closed route, exact protected-source
  boundary, separately labeled general-reference context, two-distinct-source
  plural rule, cache-state isolation, neighbor rechecking, or
  house-paper-as-fence-only rule.
- No deletion, update, or replacement of committed documents, chunks, or
  append-only passage-policy history.

## Read-only findings

Phase 7 accounted for all 4,262 structural records and yielded 3,959 eligible
projections: 3,055 people and 904 places. Full execution is inexpensive but
operationally broad: its proposed maximum is USD `0.02441808` across 3,959
document/chunk/policy row families.

The balanced 20-item selection has Phase 7 canonical projection bytes `8069`.
Using the same conservative `ceil(bytes / 3)` estimate gives 2,690 input tokens
and an estimated standard embedding cost of USD `0.00005380` at USD `0.02` per
million input tokens. The packet uses a much higher USD `0.01` attended ceiling
to contain tokenizer and retry uncertainty without implying execution
authority.

The selected immutable records are:

| Type | Entity ID | Record SHA-256 |
|---|---|---|
| person | `G0010` | `5f791ad27a2902eb4422435b006cbb883899743b809f6786d7367d56183217b6` |
| person | `G0013` | `f0b76e34a79d674af2d1362600b2b50bc63d7715e64a6c70e43dac4b35ff1565` |
| person | `G0078` | `40c276c2fe9f9ee8fb54e9367953c3f3512be8218d56f143a8f82a446b16d4e5` |
| person | `G0107` | `53988a7194f676b6b05db7f4fad96c9fd39d4e1821d3ac0087302c285b9cb2d7` |
| person | `G0132` | `49c0e19a38133366a95c02ccaf036912c121692a98c5f9929a91aeb64f06e52d` |
| person | `G0207` | `524273dd4cdb03f65a55eb1d05b5b4b84cacd46695058eb801005ec0362832fb` |
| person | `G0223G` | `1037130044b799c3ac8e53248595278e2fc36210f54fb46873f218c6018ed5fa` |
| person | `G0223H` | `1a8187197a906d2a7f2159b2d5a200ecaeb1cb068af85c2edc5d4aa0dd0a7255` |
| person | `G0223I` | `71af8b3d2f8436c87836813f8b397051f7bbf15dba4461f637d4fdc4702927c1` |
| person | `G0223J` | `3d965783438391d723cbaf1c3e4d52852f6fb45c8a6c0c6d3dbf41a54f8b1274` |
| place | `G0009` | `b8db1dee76c7416fba5d45e3ad29f56951340cd4d23417c181364ed82b665614` |
| place | `G0098` | `1ae34ab14cf2cda6ddf7928bcdf071cdcf4b4fbfe47862f44656cc6125fd6dd0` |
| place | `G0099` | `4a034fd1f32510a0b56656ecd3c4b962de07dac64bb432073d624a43ea855698` |
| place | `G0116` | `7b18e321b2ce1694ce2e5b08df32e4763f75626045cdebb184d310af30bfcb2d` |
| place | `G0137` | `02c22cb23dfcd7855010bbc6478f9b82fc3516adfba4eb120c2215d917d906c3` |
| place | `G0222` | `b5c77b572a3c906e9ab698f75a70892a5be0eb1734bf73733ea8397639a1c533` |
| place | `G0295` | `bb0148822af539bab599009b7edcdbfc964f1907543971ddf22075e3ced2b326` |
| place | `G0490G` | `379c668f35076ec02f97c9064088096d382a69f9bf74dbe86d1331e5c8c3d54f` |
| place | `G0490H` | `2ed5af6fa2fe7126c2d992a3547255d28e8d231cc31f42abaf594532a1f39dd0` |
| place | `G0494` | `28664288bc469b0f425f6855f909748296de5d1015821c5b99591acd107c9d24` |

## Considered approaches

### 1. Balanced 20-item pilot — chosen

Select 10 people and 10 places deterministically. This tests both real primary
row schemas, UUID/rendering behavior, multi-request spend accounting, one
multi-item transaction, exact reconciliation, and sampling while keeping the
first post-proof write small enough to inspect exhaustively.

### 2. Full 3,959-item batch — rejected for Phase 8

The spend is trivial, but the first generic writer execution would create
11,877 document/chunk/policy rows and make rollback, discrepancy triage, and
manual evidence unnecessarily broad. Full scale should follow a verified
multi-item pilot rather than double as one.

### 3. First 20 globally sorted records — rejected

A single global prefix is simpler but may exercise only one entity schema. A
balanced prefix has the same deterministic and bounded properties while proving
both person and place projections.

## Architecture

### Immutable packet contract

A pure contract module consumes the exact pinned artifact and Phase 7 parser.
It re-derives the full eligible set and refuses unless the Phase 7 inventory
identity, eligible checksum, outcome counts, and selected 20 projections match
the committed compact evidence and this design.

For each selected record, the module renders the same allowlisted fields as the
Phase 6 proof, generalized without its `H0175` constants. It derives document
and chunk UUIDs from the existing Phase 6 namespace and the immutable string:

`stepbible-tipnr:<revision>:<entity-id>:<record-sha256>:<rendered-sha256>`

The source and alias IDs must equal the Phase 6 IDs. Each document remains
hidden through that source, uses one chunk at index zero, and receives the same
deterministic `general_context` policy metadata as `H0175`.

### Zero-effect preview

Preview requires the explicit pinned artifact path and produces canonical JSON
containing packet identity, item projections, UUIDs, hashes, exact rendered
bytes, embedding request count, cost estimate/ceiling, reconciliation target,
and six-item sample identity. It may write only create-new or byte-identical
bytes below ignored `local/`.

Preview has no approval input, apply flag, database import, model import,
network access, or credential loading. Both authorization booleans are false.

### Read-only preflight and single-item verification

A separate preflight command loads only the analysis credential plus the
existing Phase 6 retrieval-verifier connection where required. Before any
later apply, it:

1. asserts both sessions are transaction-read-only before queries;
2. proves the existing source and alias exactly match Phase 6 hidden metadata;
3. runs the exact Phase 6 `H0175` reconciliation as the required single-item
   verification and confirms its vector/FTS counts remain zero;
4. inspects every candidate document/chunk/current-policy/proposition family;
5. confirms the feature defaults off and committed registry constants remain
   empty; and
6. returns only `all_clean`, `all_exact_complete`, or a hard conflict.

No mixed candidate state is resumable because a legitimate Phase 8 commit is
atomic. Mixed state indicates outside interference, a historical partial, or a
contract defect and must stop before spend.

### Attended apply boundary

Apply is a separate module with no selection arguments. It validates a small
regular JSON approval file containing exactly:

- schema version and same-day operation date;
- `approved_by: Alex Whitley`;
- source slug, artifact revision, Phase 7 inventory hash, packet checksum, and
  item count `20`;
- model `text-embedding-3-small`, dimensions `1536`, request ceiling `20`, and
  maximum spend USD `0.01`;
- `embedding_requests_authorized: true`; and
- `single_database_transaction_authorized: true`.

The apply module repeats local packet construction and read-only preflight
before importing the embedding client or write credential. `all_exact_complete`
is a zero-call verified skip. `all_clean` proceeds to embedding.

### Embedding and atomic write

Embeddings run in immutable packet order. The writer tracks requested,
completed, failed, and validated vector counts. It validates exactly 1,536
finite numeric values for every result. No write connection opens until all 20
vectors are validated.

One transaction sets statement and lock timeouts, rechecks the source/alias and
all candidate states, inserts 20 documents, 20 chunks, and 20 policy rows,
queries all staged rows back, verifies exact identities and dimensions, stamps
all documents complete, performs a final staged check, and commits once.
Proposition code is structurally unavailable. Any exception rolls back all 60
rows.

### Fresh reconciliation and sampling

After commit, fresh read-only identity reconciliation proves exact counts,
content hashes, attribution, hidden source, ordered references, policy metadata,
embedding dimensions, completion stamps, and zero propositions. Retrieval
reconciliation executes one vector and one FTS probe per new document and
requires all 40 results to be zero.

The final local evidence includes hard reconciliation counts and canonical
hashes. It also renders the six predetermined sample records for review. The
sample contains only allowlisted output and checks the exact source projection;
it never presents or judges excluded descriptions or relationships.

## Retry, failure, and containment behavior

- **Artifact/inventory/packet mismatch:** stop locally before credentials.
- **Source, alias, or H0175 mismatch:** stop during read-only preflight.
- **All candidates clean:** eligible to continue only with exact same-day
  approval.
- **All candidates exact-complete:** make no model or write call; run fresh
  reconciliation and return skipped `20`.
- **Mixed, partial, conflicting, proposition-bearing, or duplicate-policy
  state:** stop before model spend; do not repair automatically.
- **Embedding failure:** open no write connection; report the exact request at
  which processing stopped and prior bounded spend exposure; do not retry.
- **Write failure:** roll back the one transaction, close it, and reconcile
  fresh before any decision. Do not re-embed automatically.
- **Ambiguous commit result:** preserve apply evidence and reconcile fresh; never
  assume success or retry.
- **Post-commit reconciliation failure:** report
  `committed_reconciliation_failed`, preserve the hidden/default-off
  containment, and stop. Do not delete or mutate append-only history.
- **Any retrieval match:** fail the proof and keep the source hidden and feature
  off; no release action follows.

## Testing strategy

Implementation follows red-green-refactor in five increments:

1. Exact balanced selection, packet checksum, generalized rendering, UUIDs,
   and H0175 exclusion.
2. Zero-effect preview, cost boundary, safe local publication, and forbidden
   capability tripwires.
3. Read-only all-clean/all-complete/conflict preflight plus exact H0175
   single-item verification.
4. Approval validation, 20-vector boundary, transaction ordering, rollback,
   retry, and ambiguous-outcome behavior using strict fakes.
5. Fresh reconciliation, 40 retrieval probes, six-item sample, full pinned
   artifact integration, and Phase 0–7 regressions.

Mutation checks must prove that changing the selection order/count, admitting
`H0175`, accepting one wrong hash, loading a dangerous dependency early,
opening a write connection before vector completion, permitting mixed state,
committing a partial set, tolerating a proposition/current-policy mismatch, or
accepting one retrieval result causes a specific test failure.

## Commit and execution boundaries

- Design and implementation plan are docs-only commits.
- Pure packet/preview, preflight, apply, reconciliation, fixtures, and tests are
  build commits, separate from governing records.
- Full previews and any eventual proof report remain ignored under `local/`.
- No implementation commit or push authorizes model spend, database writes,
  batch execution, visibility, feature activation, deployment, or merge.
- Before any production operation, run the zero-effect dry run, then the fresh
  read-only preflight and exact `H0175` single-item verification. Production
  execution still requires a separately supplied same-day approval artifact.

## Stop condition

Phase 8 repository work stops when the exact 20-item packet, preview,
read-only preflight, approval gate, atomic writer, reconciliation, sampling,
and regression evidence are complete and pushed, with no external model or
database write performed. The next action is an attended decision whether to
execute that exact hidden pilot; it is not automatic batch authority.
