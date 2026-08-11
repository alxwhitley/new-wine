# O4 Git and Filesystem Isolation Design

**Date:** 2026-08-11

**Status:** Approved design; awaiting written-spec review

**Roadmap item:** PLAN.md Phase 0, O4

## Goal

Make packet ownership and integration safety deterministic before any worker is
trusted with unattended repo writes. A write-capable packet may run only in its
declared Git worktree, may change only its declared writable paths, and may
never alter, stage, commit, clean, merge, or overwrite the user's working tree.

O4 remains repo-only. It does not commission a real provider, create a provider
sandbox, access a production database or network, deploy, push, or edit governed
content.

## Decision

Use a coordinator-owned preflight/postflight gate based on direct Git and
filesystem evidence. Worker-reported `changed_files` remains part of the replay
contract, but it is corroborating evidence rather than the authority for what
changed.

The coordinator does not provision, stage, commit, merge, delete, or clean Git
state. An operator provisions the packet branch/worktree and later performs any
approved commit or integration. O4 validates those boundaries and emits a
read-only integration manifest. This preserves the existing constitution that
workers never perform integration actions.

## Trust boundaries

### Operator-owned inputs

Before enrollment, the operator supplies:

- an absolute, canonical repository root;
- an absolute, canonical packet worktree path;
- the expected branch name and 40-character starting revision;
- the packet's normalized writable-path allowlist and forbidden surfaces;
- an optional protected dirty-worktree path whose state must remain unchanged;
- the integration base revision used only for conflict analysis; and
- an optional canonical integration-target worktree path, used only to prove
  whether that target is dirty without mutating it.

The operator is responsible for creating the branch and worktree. Paths are
never inferred from names, environment variables, or worker output.

### Coordinator-owned evidence

The coordinator opens and pins the repository/worktree identity before worker
invocation, records the baseline, derives postflight changes itself, and writes
canonical evidence below the packet's existing state root. It passes only
validated findings into review and reconciliation.

### Untrusted worker output

Worker result JSON, stdout, stderr, claimed changed paths, claimed Git revision,
and claimed verification results cannot establish scope compliance. They may be
compared with coordinator evidence; disagreement fails closed.

## Preflight

Preflight runs before a write-capable packet can move from `READY` to worker
invocation.

1. Resolve the repository root and packet worktree with `realpath`; reject
   symlinks and non-directories.
2. Use Git plumbing without a shell to confirm both paths share the expected
   Git common directory.
3. Parse `git worktree list --porcelain -z` and require exactly one registration
   for the canonical worktree path.
4. Require the registered branch to equal the packet branch and `HEAD` to equal
   `starting_revision`. Detached worktrees are refused for write-capable packets.
5. Require no other enrolled, nonterminal write-capable packet to claim the same
   worktree, branch, or overlapping writable path.
6. Capture the packet-worktree baseline from Git-derived tracked changes,
   untracked files, index state, and submodule state. Ignored files are outside
   the packet change manifest but cannot satisfy declared evidence.
7. If a protected user worktree is supplied, capture its tracked/untracked path
   set and content fingerprints without reading file contents into an artifact.
8. Persist a canonical, SHA-256-bound baseline artifact before invocation. A
   crash before that durable artifact exists leaves the packet `READY`; no worker
   may start.

The baseline records paths, modes, object IDs where Git has them, and SHA-256
fingerprints for filesystem-only content. It never records file contents,
environment values, or credential-like matches.

## Postflight

Postflight runs after every worker terminal outcome, including timeout,
malformed output, and process interruption.

1. Revalidate the pinned worktree/common-directory/branch identity. Replacement,
   detachment, branch movement, or worktree-registration drift is a hard failure.
2. Derive the complete tracked, staged, deleted, renamed, type-changed, untracked,
   and submodule change set relative to the baseline.
3. Normalize every changed path using the existing O2 path-authority rules.
   Absolute paths, traversal, governed paths, forbidden surfaces, and paths
   outside the writable allowlist fail closed.
4. Compare the derived manifest with the worker result. Missing, extra, status-
   mismatched, or digest-mismatched claims become integrity findings.
5. Re-snapshot the protected user worktree. Any path, status, mode, object ID, or
   content-fingerprint change produces `HUMAN_REQUIRED`, regardless of whether
   the packet worktree itself stayed in scope.
6. Scan only the derived packet diff for secret-like additions. Findings record
   rule ID, path, and line number, never the matched value. Binary additions,
   unreadable files, symlinks, and oversized additions are conservatively
   reported for human review rather than copied into evidence.
7. Persist a canonical, SHA-256-bound postflight artifact and attach it to the
   worker result/replay evidence before review can return `ACCEPT`.

An out-of-allowlist edit is not automatically reverted. The packet moves to
`HUMAN_REQUIRED`; its isolated worktree remains intact for inspection.

## Ownership and overlap

Ownership is evaluated over normalized repository-relative prefixes. Two
write-capable nonterminal packets conflict when either owns the same worktree,
the same branch, or writable paths where one path equals or contains the other.
Read-only packets do not claim writable paths.

Dependency order does not waive overlap. A later packet may reuse ownership only
after the earlier packet is terminal and the operator enrolls it from an explicit
new starting revision.

## Integration manifest

For an accepted packet, O4 emits a read-only manifest containing:

- packet ID, branch, worktree, and starting revision;
- coordinator-derived changed paths, statuses, modes, and before/after digests;
- verification evidence identifiers;
- protected-worktree preservation result;
- secret-scan result;
- integration-base ancestry and overlap result;
- required human action.

Integration analysis is conservative and mutation-free:

- the integration base must descend from the packet's starting revision;
- if the integration base changed none of the packet's derived paths, the
  manifest reports `CLEAN_CANDIDATE`;
- any overlapping path, non-descendant base, missing object, dirty integration
  target, or inconsistent evidence reports `HUMAN_REQUIRED`;
- the coordinator never resolves a conflict or produces an integration commit.

`CLEAN_CANDIDATE` is advice, not authority to stage, commit, merge, or push.

## State and error behavior

Preflight refusal leaves the packet uninvoked and records a stable reason code.
Postflight scope, identity, protected-tree, secret, or integration uncertainty
prevents acceptance and routes to `HUMAN_REQUIRED`. Evidence corruption remains
an integrity error under the existing O3 reconciliation model.

Required reason-code families are:

- `WORKTREE_IDENTITY_*`
- `OWNERSHIP_CONFLICT_*`
- `ALLOWLIST_VIOLATION_*`
- `WORKER_MANIFEST_MISMATCH_*`
- `PROTECTED_WORKTREE_CHANGED_*`
- `SECRET_LIKE_DIFF_*`
- `INTEGRATION_CONFLICT_*`

Messages name paths and rule IDs but never include file contents, matched secret
values, environment values, or prompt payloads.

## Components

O4 should extend the current coordinator rather than create another harness:

- a focused workspace-evidence module for Git identity, snapshots, manifests,
  and protected-tree comparison;
- a focused integration-analysis module for ancestry/path-overlap decisions and
  manifest construction;
- coordinator wiring that makes durable preflight evidence a prerequisite for
  invocation and durable postflight evidence a prerequisite for acceptance;
- reconciliation checks that rehash both artifacts and reject missing or
  contradictory ownership evidence;
- fixture-only tests under `.claude/harness-selftest/`.

Exact file/function boundaries belong in the implementation plan after the
existing coordinator interfaces are mapped in detail.

## Verification design

All tests use disposable local repositories and worktrees. They must not use the
current repository as a mutation target.

Required scenarios:

1. Correct branch/worktree/revision passes preflight.
2. Symlink, detached head, wrong branch, wrong revision, foreign common
   directory, and duplicate registration fail before invocation.
3. Two packets with the same worktree, branch, equal path, parent path, or child
   path cannot both own write scope.
4. Allowed modification, creation, deletion, rename, mode change, staged change,
   and untracked file are derived accurately.
5. An undeclared path, forbidden path, governed path, path escape, symlink, and
   submodule drift prevent acceptance and are not reverted.
6. Worker omissions, invented files, wrong statuses, and wrong digests are
   detected against coordinator evidence.
7. A protected dirty worktree with pre-existing tracked and untracked changes is
   unchanged after an isolated packet; a simulated cross-worktree edit is caught.
8. Secret-like additions are reported without persisting the matched value;
   binary/oversized/unreadable additions route to human review.
9. A descendant integration base with disjoint paths is `CLEAN_CANDIDATE`; path
   overlap, divergent ancestry, dirty target, or missing evidence is
   `HUMAN_REQUIRED`.
10. Crash before baseline publication prevents invocation; crash after worker
    exit resumes postflight without losing or duplicating evidence.
11. Reconciliation rejects missing, altered, or cross-packet baseline/postflight
    artifacts.
12. Existing O2/O3 tests and the three legacy harness self-tests remain green.

## Acceptance criteria

O4 is complete only when:

- every write-capable packet is proven to use its own registered branch and
  worktree at its declared starting revision;
- coordinator-derived evidence, not worker claims, enforces file ownership;
- out-of-scope changes stop acceptance without cleanup or overwrite;
- a protected dirty user worktree is proven unchanged by disposable tests;
- integration conflicts become `HUMAN_REQUIRED` and no O4 code stages, commits,
  merges, pushes, cleans, deletes, or resolves conflicts;
- build commits and the final records commit remain separate;
- the full O2/O3/O4 and legacy harness verification passes.

## Explicit non-goals

- Real Kimi, Sonnet, Claude, Grok, or other provider commissioning.
- An OS-level subprocess sandbox or general network/filesystem containment.
- Automatic worktree/branch creation or cleanup.
- Automatic staging, committing, merging, rebasing, pushing, or conflict
  resolution.
- Production database or network access, deployment, migrations, governed
  content, doctrinal decisions, or licensing decisions.
- O5 turn/time/retry/output/queue budgets beyond the bounded subprocess timeout
  already required by O3.
