# Biblical Depth and Source-Use Policy Design

**Date:** 2026-09-01

**Status:** APPROVED in direction by Alex (2026-09-01); revised after
fresh-context adversarial review to reconcile existing settled decisions.
Design only: no ingestion, database write, retrieval change, answer-path
change, governing-record change, deployment, or source visibility change is
authorized by this approval.

**Product posture:** New Wine is confessional about Spirit-filled
distinctives, historically Christian on shared doctrine, and hospitably plural
on other orthodox disagreements.

## Objective

Increase biblical depth—especially Old Testament coverage, historical context,
book-level context, geography, people, customs, and whole-Bible synthesis—while
preventing general evangelical reference works or commentaries from redefining
New Wine's Spirit-filled convictions.

The system must scale without Alex approving commentary passage by passage.
Alex approves policy boundaries, protected topics, approved house sources, and
sample-based release gates instead.

## Approved doctrinal policy

Policy has two independent axes. Keeping them separate preserves the existing
charismatic debates instead of turning every protected topic into a house view.

**Source boundary:**

1. `protected_spirit_filled` — general commentary/reference works are excluded;
   only Alex-approved protected sources and existing house material may enter.
2. `general` — eligible contextual/reference sources may enter after the
   separate source-use gates pass.

**Presentation stance:**

1. `house_position` — a real position-paper match supplies the house fence.
2. `shared_christian` — state broadly historic Christian teaching directly and
   ground it in Scripture; reference material may add context but cannot be the
   sole basis for a doctrinal conclusion.
3. `plural` — state common ground first, then present registered, historically
   significant orthodox positions fairly without selecting a corpus-majority
   winner.
4. `uncertain` — retain the current safe path and do not unlock commentary.

The protected source boundary takes precedence on overlap, but it does not
decide the stance. A protected question may therefore be `house_position` or
`plural`.

## Protected Spirit-filled registry

The initial fail-closed registry covers the topics Alex named plus their normal
charismatic doctrinal neighborhood:

- continuation or cessation of spiritual gifts;
- tongues, prophecy, interpretation, healing, miracles, discernment, words of
  knowledge, and words of wisdom;
- baptism in the Holy Spirit, subsequence, initial evidence, filling, sealing,
  and receiving the Spirit;
- divine healing and healing in the atonement, while **healing mechanics**
  remains a protected-source plural debate;
- modern apostles and prophets and five-fold ministry, while **apostolic
  authority** remains a protected-source plural debate;
- deliverance, demonization, and spiritual warfare;
- anointing, impartation, laying on of hands, and manifestations;
- hearing God, dreams, visions, and contemporary revelation, while
  **prophetic accountability** remains a protected-source plural debate;
- revival, signs, and wonders;
- cessationism versus continuationism.

This registry is a product-policy artifact owned by Alex. Adding, removing, or
changing a protected topic requires his direct approval. It is not inferred
from corpus popularity.

The existing eight position-paper pillars remain the authoritative house fence
where applicable. This design does not rewrite their doctrine. Healing
mechanics, prophetic accountability, apostolic authority, and eschatological
timing retain their existing debate status; the first three use the protected
source boundary, while eschatological timing uses the general boundary.

A mixed query that contains any protected doctrinal issue uses the protected
source boundary for the entire retrieved writer context. Its stance is then
selected from a real house-paper match, a registered protected debate, or
`uncertain`; the general half of the question never opens a side door for
general commentary.

## Non-protected orthodox disagreements

Examples include sovereignty and human responsibility, election, covenant
systems, water-baptism understandings, communion, church government, women in
ministry, eschatological timing, and disputed authorship questions.

These examples become plural only through an Alex-approved **issue registry**.
Each issue entry defines issue-scoped viewpoint slots and common-ground framing;
it never labels a teacher globally. An unregistered possible dispute routes to
`uncertain`, not automatic plural generation.

A registered topic is served as plural only when at least two distinct
registered viewpoint slots have retrieved evidence. Otherwise deterministic
copy discloses that New Wine does not yet have enough corpus breadth to compare
the registered views.

Fringe or heterodox views are not injected for artificial balance. They may be
described when the user explicitly asks about them, with appropriate labeling.

## Why the policy unit is not an individual commentary passage

Manual passage approval does not scale. Source reputation alone also does not
make every passage neutral: history, chronology, cross-references, and word
meaning can become doctrinally load-bearing.

The scalable control unit is therefore:

- a protected-topic registry approved by Alex;
- an approved-source registry for protected topics;
- deterministic source/field classification for the narrow first release;
- route-specific retrieval and generation rules;
- deterministic provenance checks at the answer boundary; and
- bounded, stratified release sampling rather than a permanent manual queue.

## Source classes

### Scripture and existing approved New Wine material

Primary evidence for doctrine. Existing citation, attribution, position-paper,
and source-visibility protections remain in force.

### Structured biblical context

People, places, geography, language data, manuscript/reference identifiers, and
cross-reference datasets may contribute to ordinary answers after dataset- and
field-level rights and reliability review.

Structured does not mean neutral. Disputed chronology, authorship, geography,
or cross-reference judgments must be qualified or withheld.

### General reference works

Bible dictionaries, book introductions, theme articles, and study notes may
contribute outside protected Spirit-filled topics after licensing and
classification gates pass. They are supporting evidence, not an unnamed
magisterium and not the sole support for a doctrinal conclusion.

### Commentaries

The current production rule hard-excludes commentary and word-study material
from ordinary answers. That rule remains live until a separately authorized,
tested, reversible implementation replaces it.

Under the approved target policy, eligible commentary may support ordinary
answers outside protected Spirit-filled topics. Precept Austin remains excluded
under its existing separate rule. Commentary remains ineligible for the quote
rail.

## Source candidates and rights gates

### Tyndale Open Resources

Initial modern baseline candidate:

- Open Bible Dictionary;
- book introductions and profiles;
- theme articles; and
- study notes only after the narrower resources prove safe and useful.

The published CC BY-SA 4.0 posture is not, by itself, the ingestion release.
Before any write, record attribution requirements, license link, modification
notice requirements, ShareAlike implications for adaptations, nested Scripture
translation rights, third-party material, version, retrieval date, and source
checksum. Seek explicit AI/RAG permission if ordinary-answer use remains legally
ambiguous. Read-only evidence collection ends in a **HUMAN_REQUIRED** licensing
disposition from Alex; an implementation worker does not choose the source's
`license_status`, visibility, citation mode, or nested-rights disposition.

### STEPBible, TIPNR, and OpenBible

Reuse the already-ingested STEPBible lexicon/interlinear material rather than
duplicating it. Correct or reconcile the current source metadata before adding
new STEPBible data: the live source record says `public_domain`, while the
current official repository advertises CC BY 4.0.

TIPNR people/place data and OpenBible cross-reference/geography data require
dataset-specific and field-specific rights review. A site's general license
statement is not assumed to cover every bundled or upstream dataset.

Before parser or ingestion execution, Alex must approve a source-registration
packet naming the exact source row/alias behavior, `license_status`, explicit
visibility, citation mode, nested-rights disposition, and safe-mode
retrievability. This resolves the repository's visible-default versus hidden-
staging tension per source; the worker cannot infer the answer.

## Policy architecture

```text
Question
  -> source-boundary router (protected/general; fail closed)
  -> stance router (house/shared/registered plural/uncertain)
      -> protected + house: approved house fence + approved source IDs
      -> protected + plural: registered protected debate + approved IDs
      -> general + shared: Scripture + eligible reference context
      -> general + plural: registered viewpoint slots with evidence
  -> candidate passage policy filter
      -> protected/ambiguous passage from general source: drop
      -> eligible context/reference passage: retain with provenance
  -> generation contract for selected mode
  -> deterministic source/provenance checks
  -> citation/reference verification
  -> answer or honest refusal/disclosure
```

### 1. Query routing

Routing returns `QueryPolicy(source_boundary, stance, issue_key?, pillar_key?)`.
Protected ambiguity selects the protected boundary. Other uncertainty selects
the existing safe path and does not unlock commentary.

Protected routing should reuse the existing position-paper matching and
contrast infrastructure where possible, but the protected registry must have
one canonical implementation. New classifiers must be versioned and observable.

### 2. Passage classification

New general-reference and commentary passages receive a versioned policy
classification before ordinary-answer eligibility:

- `general_context`;
- `orthodox_viewpoint` with an approved `issue_key` and `viewpoint_key`;
- `protected_spirit_filled` with one or more protected topic keys;
- `mixed`;
- `uncertain`.

`general_context` is eligible only as supporting context. `orthodox_viewpoint`
is eligible only for its registered issue/viewpoint slot on a plural route.
`mixed`, protected, and uncertain passages remain searchable in Study Mode but
are excluded from ordinary answers unless an Alex-approved protected-source
rule admits them.

The first release uses only deterministic source structure and field mapping:
for example, a cleared people/place field can map to `general_context`, while
doctrinal dictionary entries and free-form commentary remain ineligible. There
is no model-based passage judge in V1.

A later model-assisted classifier requires a separate Alex-approved exception
to the repository's model-judge rule. That approval must define its exact
scope, accepted false-positive/negative behavior, labeled evaluation threshold,
logging, and prohibition on post-answer truth judging. Until then, ambiguous or
unmapped passages simply lose ordinary-answer eligibility without entering a
manual queue.

Every classification stores the rule version, timestamp, and reason codes. A
future approved model classifier must also store model and prompt fingerprint.
History is append-only; a new classifier contract creates a new version rather
than overwriting the old one.

### 3. Viewpoint handling without a teacher taxonomy

New Wine must not persist labels such as “Reformed teacher” or “Arminian
teacher.” That would violate the existing no-teacher-taxonomy decision and
would misrepresent teachers whose positions vary by issue.

For a registered plural query, retrieved passages may fill only the
issue-scoped viewpoint slot recorded on that passage. The answer attributes
each position to the actual named sources supporting it. A viewpoint key means
“this passage supports this view on this issue,” never “this teacher belongs to
this theological family.”

Requirements:

- common ground appears first;
- at least two distinct registered, evidence-backed viewpoint slots are required before the answer
  calls the issue a debate;
- each position is labeled and attributed;
- corpus frequency is never described as truth or consensus;
- no winner is declared unless New Wine has an Alex-approved house position;
- if a registered slot lacks evidence, use deterministic corpus-gap disclosure;
  and
- never invent a second side from model memory to satisfy the format.

### 4. Generation contracts

`shared_christian` answers preserve the existing one-named-voice contract.
Doctrinal claims must be grounded in Scripture or the one selected approved
teacher's evidence. Reference works may clarify context and history, must be
separately attributed, and never become a second doctrinal voice.

Every protected-boundary answer receives only approved source IDs. A house
fence appears only on a real position-paper match. A registered protected
debate instead uses the plural presentation contract without inventing a house
conclusion.

`plural` is the only multi-position exception to one named voice. It receives
evidence in distinct registered issue slots and must compare them fairly. A
single commentary cannot masquerade as consensus.

### 5. Deterministic boundary checks

The serving boundary checks what can be proven mechanically:

- a protected answer cites or consumes only approved protected source IDs;
- a commentary/reference passage has an eligible policy classification and
  an allowed source/license/visibility state;
- a plural answer has evidence from at least two distinct registered viewpoint
  slots before using the plural template;
- every named teacher is in the existing permitted-name grounding set;
- references and citations pass the existing verifier; and
- policy/classifier versions are attached to logs needed for reconstruction.

These checks do not claim to prove theological truth or semantic faithfulness.
The repository's accepted limits on model judgment and invented claims remain
honestly disclosed.

## Data/interface direction

Implementation planning should prefer a small policy module and additive
metadata rather than overloading `source_kind` as a safety verdict.

Conceptual interfaces:

```python
class SourceBoundary(str, Enum):
    PROTECTED_SPIRIT_FILLED = "protected_spirit_filled"
    GENERAL = "general"

class PresentationStance(str, Enum):
    HOUSE_POSITION = "house_position"
    PLURAL = "plural"
    SHARED_CHRISTIAN = "shared_christian"
    UNCERTAIN = "uncertain"

class PassagePolicy(str, Enum):
    GENERAL_CONTEXT = "general_context"
    ORTHODOX_VIEWPOINT = "orthodox_viewpoint"
    PROTECTED_SPIRIT_FILLED = "protected_spirit_filled"
    MIXED = "mixed"
    UNCERTAIN = "uncertain"
```

The implementation plan defines the additive schema. It must not:

- treat `source_kind=commentary` as sufficient proof of eligibility;
- use `citation_mode` as doctrinal safety metadata;
- permanently classify a teacher into a theological family;
- overwrite historical classification provenance; or
- make new material answer-eligible before classification completes.

## Staged delivery

### Stage A — Reference baseline, no ordinary-answer change

1. Collect rights evidence, then stop for Alex's source-registration and
   licensing disposition.
2. Build parsers and provenance manifests locally.
3. Start with structurally identifiable people/place/geography fields from
   Tyndale, TIPNR, and OpenBible that clear rights review; doctrinal dictionary
   entries and free-form book-introduction prose remain ineligible in V1.
4. Dry run, validate exact counts/checksums, then perform one isolated hidden
   proof only after Alex separately approves the production write.
5. Keep new material hidden/search-only until classification and evaluation
   pass.

### Stage B — Policy routing and classification

1. Implement the canonical protected registry and route contract.
2. Implement deterministic, versioned source-field classification for V1.
3. Keep all new general reference/commentary material fail-closed by default.
4. Prove protected-source exclusion and plural evidence requirements locally.

### Stage C — Narrow ordinary-answer release

1. Enable only eligible, deterministically mapped structured context first.
2. Do not enable all verse notes or legacy commentary at once.
3. Evaluate the 15 weakest coverage cases, all protected-topic adversarial
   cases, and the full 48-case biblical-coverage suite.
4. Require no protected-source leak, no false consensus from a one-sided
   corpus, and measurable improvement in weak context/OT cases.
5. Release behind a seconds-reversible policy flag, attended by Alex.

### Stage D — Commentary expansion

Only after Stage C succeeds, classify and evaluate selected commentary sets.
Expansion is **Triggered** on either a deterministic mapping adequate for the
selected source or Alex's separately recorded model-classifier exception.
Expand source by source. Precept Austin and quote-rail eligibility remain out of
scope.

### Governing-record gate

Before any executor changes retrieval or answer generation, present the exact
proposed replacement to CLAUDE.md Settled decision #5 and any implicated
ARCHITECTURE text for Alex's explicit approval. These design documents record a
target; they do not silently supersede the currently binding blanket commentary
exclusion.

## Acceptance criteria

The design is ready for a bounded V1 implementation plan. Commentary expansion
is not implementation-ready until its Triggered classifier condition fires.

The implementation is releasable only when:

1. Protected-topic tests show zero general-commentary/reference source IDs in
   the writer context and served citations.
2. Ambiguous protected queries fail closed.
3. Plural answers require at least two distinct registered, evidence-backed
   viewpoint slots and disclose a one-sided corpus.
4. No permanent teacher-family taxonomy is introduced.
5. Every new source has recorded rights, attribution, version, checksum, and
   nested-rights disposition.
6. New material routes through `shared_ingest.ingest_document()` and retains
   provenance.
7. Dry run -> isolated hidden proof -> hard reconciliation -> explicit release
   is followed for every production batch.
8. The 15 weakest cases improve without a protected-topic regression, followed
   by a clean full 48-case run.
9. A kill switch restores the current blanket commentary exclusion without a
   deploy or data deletion.

## Explicit non-goals

- No passage-by-passage approval workflow for Alex.
- No claim that “historical context” is automatically doctrinally neutral.
- No permanent teacher taxonomy.
- No model-based post-hoc truth judge.
- No replacement of Scripture or approved teachers with commentary prose.
- No mass commentary enablement.
- No production DB write, source visibility flip, deploy, or answer-path change
  under this design approval alone.

## Finding classification

- **Scheduled:** STEPBible live metadata says public domain while the current
  official data repository advertises CC BY 4.0; reconcile before adding or
  releasing further STEPBible material.
- **Scheduled:** Tyndale CC BY-SA and nested-rights/AI-use posture must be
  recorded before ingestion or ordinary-answer use.
- **Triggered:** broad legacy-commentary classification; do not start until the
  narrow modern-reference release proves the policy architecture and either a
  deterministic mapping exists or Alex approves the bounded model-classifier
  exception.
- **Parked:** any commentary modernization or paraphrase program; not required
  for biblical coverage.
