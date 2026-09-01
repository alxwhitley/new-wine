# Biblical Depth Source Registration Packet — 2026-09-01

**Status:** APPROVED by Alex Whitley on 2026-09-01
**Scope:** Phase 0 provenance, rights, field boundaries, and governing text
**Not authorized:** ingestion, database writes, source visibility changes,
retrieval or answer-path changes, deployment, or doctrinal content changes

## Recommendation

Build the first biblical-depth lane from narrowly allowlisted structured facts,
not from commentary prose. Approve TIPNR identifiers/forms/references and a
conservative subset of OpenBible place metadata for later hidden proofs. Retain
future hidden Tyndale provenance rows as a proposal and keep their prose out of V1.
Keep OpenBible cross references out of V1 because choosing a cross reference is
interpretive, even when the data format is structural.

This keeps two independent questions separate:

1. **Source boundary:** may this source contribute on a protected Spirit-filled
   topic, or only on a general topic?
2. **Presentation stance:** should the answer state New Wine's approved house
   view, shared Christian ground, multiple named positions, or uncertainty?

Protected topics use only Alex-approved sources. General structured context does
not become eligible merely because it has an open license. No teacher is assigned
to a theological family, and no passage is classified by a model in V1.

## Evidence reviewed

The artifact hashes, revisions, sizes, field exclusions, and license particulars
are recorded in the four manifests under `docs/ingestion/source_manifests/`.
Primary sources reviewed:

- [Tyndale Open Resources](https://tyndaleopenresources.com/) and the
  [CC BY-SA 4.0 legal code](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en)
- [STEPBible Data Repository](https://github.com/STEPBible/STEPBible-Data) at
  commit `02843f07cbb5009e00999a7c0efead6430dbb6e7` and the
  [CC BY 4.0 legal code](https://creativecommons.org/licenses/by/4.0/legalcode.en)
- [OpenBible cross references](https://openbible.info/labs/cross-references/)
  and [Bible Geocoding Data](https://github.com/openbibleinfo/Bible-Geocoding-Data)
  at commit `7eb18a5ee62f27b9b93bd6689ea272d76dd23b8f`

This is an engineering rights review, not legal advice. CC licenses cover only
rights the licensor can grant; embedded third-party rights still require their
own disposition.

## Proposed dataset decisions

| Dataset | V1 ordinary-answer status | Exact V1 boundary | Registration proposal |
|---|---|---|---|
| STEPBible TIPNR | Eligible after later proof/release | Entity ID/type, original-language ID/form, OSIS references only | New `licensed/hidden` dataset row |
| OpenBible geocoding | Eligible after later proof/release | ID, friendly name, place type, OSIS references, qualified candidate identification/confidence | New `licensed/hidden` dataset row |
| Tyndale Open Study Notes | Ineligible | No fields | New `licensed/hidden` work row; provenance only |
| Tyndale Open Bible Dictionary | Ineligible | No fields | New `licensed/hidden` work row; provenance only |
| OpenBible cross references | Ineligible | No fields | Optional `licensed/hidden` dataset row; do not ingest in V1 |
| Existing STEPBible lexicons | Existing behavior only | No new fields | Correct `public_domain` to `licensed` only in a separate attended operation |

### Mandatory exclusions

- All Tyndale prose, including profiles, introductions, theme articles, study
  notes, and dictionary articles.
- All Tyndale pictures, maps, charts, and third-party media.
- TIPNR Claude-generated descriptions, translation-comparison prose, and
  relationship assertions in V1.
- OpenBible images/media, OpenStreetMap-derived geometry/fields, translation
  arrays/counts, free-form descriptions, and coordinates without explicit
  non-OSM provenance.
- OpenBible cross-reference edges and vote scores.
- Any field that is unmapped, mixed-provenance, doctrinal, free-form, or loses a
  source uncertainty marker.

### Machine-enforceable V1 field mappings

The manifests are authoritative; descriptive labels in the decision table are
not parser rules. Every parser must project only the raw paths below, emit only
the named output fields, and reject every unknown field rather than passing it
through.

**TIPNR input:** `Proper Nouns/TIPNR - Translators Individualised Proper Names
with all References - STEPBible.org CC BY.txt`

| Exact raw field | Output | Required transform/provenance boundary |
|---|---|---|
| Entity marker `$========== {PERSON(s)|PLACE|OTHER}` | `entity_type` | Closed three-value mapping; source structural marker |
| Primary-row column 1 `UnifiedName=uStrong`, substring after final `=` | `entity_id` | Keep only uStrong; discard translated-name/reference prefix |
| Non-`Total` form-row column 3 `dStrong«eStrong=Heb/Grk` | `original_language.{dstrong,estrong,source_script_form}` | All three parts must parse; source identifiers/form |
| Non-`Total` form-row column 5 `All Refs` | `osis_references` | Preserve subverse suffixes; reject rather than expand `ff` abbreviations |

All primary-row descriptive/relationship columns, form-row translated-name
fields, `Total` rows, and every `@Briefest`, `@Brief`, `@Short`, and `@Article`
line are excluded.

**OpenBible input:** `data/ancient.jsonl` only

| Exact JSON path | Output | Required transform/provenance boundary |
|---|---|---|
| `$.id` | `place_id` | Exact OpenBible dataset identifier |
| `$.friendly_id` | `place_name` | Exact dataset label; never consult translations, linked data, or `extra` |
| `$.types[]` | `place_types` | Exact strings from OpenBible's documented type vocabulary |
| `$.verses[].osis` | `osis_references` | Copy OSIS only; discard every sibling field |
| `$.modern_associations.<key>` | `candidate_identifications[].modern_id` | Exact OpenBible aggregate identification mapping key; the pinned artifact has no nested `modern_id` field |
| `$.modern_associations.*.name` | `candidate_identifications[].name` | Exact OpenBible aggregate label |
| `$.modern_associations.*.score` | `candidate_identifications[].confidence_score` | Preserve integer; never convert to a probability or categorical fact |

OpenBible describes the identification and score fields as its aggregation of
cited scholarship, with underlying sources cataloged in `data/source.jsonl`;
they must be presented as qualified candidate identifications, not New Wine
facts. The repository applies CC BY 4.0 to its data. This allowlist does not
claim or import upstream commentary prose. It excludes every other root or
nested path, including `extra`, `linked_data`, `identifications`, descriptions,
geometry, coordinates, translation data, media, `modern.jsonl`, and all source
text. If later proof shows any allowed label incorporates a separately governed
third-party asset rather than dataset-authored factual metadata, that field
fails closed and requires a new human disposition.

## Exact proposed registrations

These values are proposals, not SQL and not authorization to write them.
`source_kind` and `citation_mode` are document defaults, not columns on
`sources`.

### Existing source correction

| Field | Current | Proposed |
|---|---|---|
| `sources.name` | `STEPBible` | unchanged |
| `sources.slug` | `stepbible` | unchanged |
| `license_status` | `public_domain` | `licensed` |
| `visibility` | `shown` | `shown` |
| permission terms | null | `STEPBible Data Repository; CC BY 4.0; credit STEP Bible and link www.stepbible.org; identify changes and retain license/source URI.` |
| notes | not relied on | `Repository revision and per-dataset checksums are held in the New Wine source manifests. Dataset-level allowlists still govern answer eligibility.` |

**Behavioral impact:** the live retrieval gate treats `licensed` sources as
retrievable only when safe mode is off and visibility is `shown`. Correcting the
existing row would therefore remove current STEPBible lexicons whenever safe
mode is on. This correction must not be bundled with source registration or
ingestion; Alex must explicitly accept that operational impact first.

### New source rows

| Name / slug | License / visibility | Permission terms | Document defaults | Alias |
|---|---|---|---|---|
| `STEPBible TIPNR` / `stepbible-tipnr` | `licensed` / `hidden` | `CC BY 4.0; credit STEP Bible (www.stepbible.org); identify changes; source revision 02843f…` | `biblical_context`, `citable` | `stepbible tipnr` |
| `OpenBible.info Bible Geocoding Data` / `openbible-bible-geocoding` | `licensed` / `hidden` | `CC BY 4.0; credit OpenBible.info; identify changes; source revision 7eb18a…; excluded ODbL/media fields` | `biblical_context`, `citable` | `openbible geocoding` |
| `OpenBible.info Cross References` / `openbible-cross-references` | `licensed` / `hidden` | `CC BY 4.0; credit OpenBible.info; identify changes; snapshot 2026-08-31` | None; ingestion prohibited in V1 | none |
| `Tyndale Open Study Notes` / `tyndale-open-study-notes` | `licensed` / `hidden` | `CC BY-SA 4.0; exact reviewed notice: Copyright (C) 2022 by Tyndale House Publishers; required adaptation credit is preserved in the manifest; third-party assets excluded` | None; ingestion prohibited in V1 | none |
| `Tyndale Open Bible Dictionary` / `tyndale-open-bible-dictionary` | `licensed` / `hidden` | `CC BY-SA 4.0; exact reviewed notice: Copyright (C) 2023 by Tyndale House Publishers; required adaptation credit is preserved in the manifest; third-party assets excluded` | None; ingestion prohibited in V1 | none |

All proposed new rows are hidden. Under the current retrieval gate, hidden rows
are not retrievable in either safe-mode state.

### Why per-work/per-dataset rows are recommended

Migration 043 describes `sources` as one row per licensable rights holder. That
model is too coarse for these collections: visibility, nested rights,
attribution text, checksums, and release approval differ by work or dataset.
Dedicated rows are the safer staging boundary because hiding TIPNR must not hide
existing STEPBible lexicons, and approving one Tyndale work must not implicitly
approve another. This is a deliberate governing clarification, not an unnoticed
schema convention change.

## Attribution output requirement

Before any eligible dataset is shown, New Wine needs an answer-visible or
directly linked source-details surface that preserves:

- dataset/work title and rights holder;
- canonical source URL and license link;
- required credit;
- pinned revision or snapshot date;
- a notice that New Wine transformed or selected fields, when applicable; and
- the relevant ShareAlike disposition for Tyndale if its prose is ever enabled.

`citation_mode=citable` is proposed because silent use would not satisfy the
product's attribution obligation by itself. A hidden proof may validate storage
without user-visible output, but release cannot precede the attribution surface.

## Exact proposed governing-record text

Do not apply this text during Phase 0. Apply it only with the later code release,
after Alex explicitly approves it and implementation proves the stated behavior.

### Proposed replacement for CLAUDE.md Settled decision #5

> 5. **Commentary remains excluded from ordinary answers; structured biblical
> context is a separate, allowlisted lane** (Alex's call, amended 1 Sep 2026).
> Ordinary answer retrieval continues to hard-exclude `commentary` and
> `word_study` before collapse/rerank and again after neighbor expansion. Study
> Mode remains their only searchable surface. A source is not ordinary-answer
> eligible merely because it is public-domain or openly licensed. The only new
> V1 exception is deterministic, field-allowlisted `biblical_context` whose
> source, rights, passage policy, attribution behavior, and release Alex has
> explicitly approved. Protected Spirit-filled topics structurally exclude all
> general biblical-context sources and may use only Alex-approved protected
> sources. Free-form commentary, study notes, doctrinal dictionary prose, theme
> articles, and model-classified passages remain ineligible. Reopening any of
> them is Triggered future work requiring a separate Alex-approved governing
> change.
> `is_commentary_chunk` / `exclude_commentary_chunks` remains the canonical
> commentary exclusion implementation.

This preserves the existing commentary decision; it does not silently treat
historical or factual-sounding commentary passages as neutral.

### Proposed replacement for ARCHITECTURE.md Retrieval summary

> Query expansion (3 variants via Groq) → vector + FTS per variant → RRF (K=60)
> → disabled-source filter → **hard-exclude commentary and word study**
> (`is_commentary_chunk` / `exclude_commentary_chunks`) → deterministic
> source-use policy filter → top 30 with `SOURCE_KIND_FUSION_WEIGHTS` → Cohere
> rerank → top 8 → neighbor expansion → second commentary strip and source-use
> policy check (defense-in-depth).
>
> The source-use policy has independent source-boundary and presentation-stance
> axes. General routes may admit only explicitly released `biblical_context`
> fields with a current deterministic `general_context` passage policy.
> Protected routes structurally reject all general reference/context material
> and admit only approved protected sources. Missing, mixed, uncertain, or
> model-classified passage policy fails closed. Commentary and `word_study`
> remain outside ordinary answer context and searchable only in Study Mode.

### Proposed addition to ARCHITECTURE.md Standing source policy

> - A `sources` row normally represents a licensable rights holder. An
>   open-licensed collection may instead use explicit per-work or per-dataset
>   rows when nested rights, attribution, visibility, checksums, or release
>   approval must be controlled independently. This is a staging and governance
>   boundary, not permission to fragment a teacher/source identity. Every such
>   row remains hidden until its own dry run, isolated proof, reconciliation,
>   attribution verification, and explicit release approval pass.

## Approved decisions

Alex approved the recommended Phase 0 disposition on 2026-09-01. The resulting
decisions are:

1. Approve the exact TIPNR V1 allowlist and a dedicated hidden dataset row?
   (**Approve.**)
2. Approve the exact OpenBible geocoding V1 allowlist and keep cross references
   un-ingested/ineligible? (**Approve.**)
3. Approve hidden per-work Tyndale registrations for provenance while all
   Tyndale content remains out of V1? (**Approve.**)
4. Approve the per-work/per-dataset clarification to the historical
   one-rights-holder source-row convention? (**Approve.**)
5. Approve the proposed governing text for application only with a later proven
   release? (**Approve.**)
6. Approve changing the existing STEPBible row from `public_domain` to
   `licensed`, knowing safe mode would then suppress its current lexicons?
   (**Defer the write; approve the correction in principle only after a separate
   retrieval-impact decision.**)

Approval of these dispositions records policy and future registration
proposals only. It explicitly authorizes none of the following: source
registration, database writes, ingestion, visibility changes, passage
classification, retrieval changes, answer-path changes, or deployment.

## Continuing constraints

The manifests now record `decision.status: approved`. This approval authorizes
local Phase 1 policy fixtures; it does not authorize source registration,
database writes, parsers, ingestion, passage classification, retrieval or
answer-path changes. The existing STEPBible metadata write remains deferred
until a separate attended retrieval-impact decision.
