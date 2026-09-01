# Biblical coverage baseline — 2026-08-31

## Outcome

New Wine has **strong pockets of biblical material, not broad biblical depth**.
Of 48 representative retrieval questions, 14 were strong, 19 thin, 2 empty,
and 13 misretrieved. The weak areas are concentrated exactly where Alex wants
to deepen the product: Old Testament passage interpretation, biblical context,
and whole-Bible synthesis.

The 12-case real-answer sample confirms that adding more material alone will
not resolve this. Retrieval routing and source concentration materially shape
the answer after relevant content is already present.

## Audit contract and reconciliation

- **Question:** Where is New Wine's biblical coverage strong, thin, or empty?
- **Surfaces:** the real answer retrieval function, commentary/word-study
  exclusions, and the full guarded producer on a stratified answer sample.
- **Non-goals honored:** no database writes, ingestion, retrieval change,
  deployment, doctrinal-content edit, or automated theology judge.
- **Retrieval:** attempted 48, completed 48, errored 0, skipped 0.
- **Paid answers:** attempted 12, completed 12, errored 0, skipped 0.
- **Anthropic cost:** **$0.488215** against Alex's explicitly approved $1.50
  ceiling. Pilot $0.071359; remaining batch $0.416856.
- **Outputs:** complete JSONL artifacts remain under `local/2026-08/` because
  they contain bounded corpus excerpts and generated answers. They are not
  committed or published.

The retrieval runner wrapped the Supabase client in a fail-closed allowlist:
known SELECT chains and the three retrieval RPCs were permitted; insert,
update, upsert, delete, unknown tables, unknown query methods, and unknown RPCs
raised before I/O. Deterministic tests proved these boundaries before the
single-item live proof.

## Classification method

- **Strong:** relevant evidence from at least two documents; never awarded from
  counts alone.
- **Thin:** relevant evidence exists but is narrow, incomplete, or dominated by
  one voice/work.
- **Empty:** no usable material returned.
- **Misretrieved:** returned material does not answer the question.

This is a relevance/depth review, not an independent ruling on doctrine. Where
an answer adopts a contested interpretation, this report records that the
framing is narrower than the requested broad-Christian posture; it does not
adjudicate which interpretation is correct.

## Retrieval baseline

| Domain | Strong | Thin | Empty | Misretrieved |
|---|---:|---:|---:|---:|
| Biblical storyline and covenant | 0 | 4 | 0 | 2 |
| God, Christ, and the Holy Spirit | 2 | 3 | 0 | 1 |
| Creation, sin, and salvation | 3 | 3 | 0 | 0 |
| Formation, wisdom, and suffering | 3 | 1 | 0 | 2 |
| Church, worship, and mission | 4 | 2 | 0 | 0 |
| Old Testament passages | 0 | 2 | 1 | 3 |
| New Testament passages | 1 | 3 | 0 | 2 |
| Language, history, and context | 1 | 1 | 1 | 3 |
| **Total** | **14** | **19** | **2** | **13** |

Percentages: strong 29.2%, thin 39.6%, empty 4.2%, misretrieved 27.1%.
Only 29.2% met the strong bar. Treating every non-empty result as coverage
would inflate the apparent success rate to 95.8% and conceal the 13
misretrievals.

### All 48 cases

| Case | Classification |
|---|---|
| `storyline_bible_overview` | Misretrieved |
| `storyline_abrahamic_covenant` | Thin |
| `storyline_exodus_pattern` | Thin |
| `storyline_kingdom_of_god` | Thin |
| `storyline_exile_return` | Misretrieved |
| `storyline_old_new_testaments` | Thin |
| `god_trinity` | Thin |
| `god_attributes` | Thin |
| `christ_identity` | Misretrieved |
| `christ_resurrection` | Strong |
| `spirit_work` | Strong |
| `spirit_scripture_church` | Thin |
| `creation_image_of_god` | Thin |
| `creation_goodness_stewardship` | Thin |
| `sin_fall` | Strong |
| `salvation_grace_faith` | Thin |
| `salvation_justification_sanctification` | Strong |
| `salvation_new_creation` | Strong |
| `formation_prayer` | Misretrieved |
| `formation_forgiveness` | Strong |
| `formation_wisdom` | Misretrieved |
| `formation_suffering` | Thin |
| `formation_money` | Strong |
| `formation_character` | Strong |
| `church_identity` | Strong |
| `church_baptism` | Strong |
| `church_lords_supper` | Thin |
| `church_leadership` | Thin |
| `church_worship_gathering` | Strong |
| `church_mission` | Strong |
| `ot_genesis_22` | Misretrieved |
| `ot_exodus_12` | Thin |
| `ot_psalm_23` | Misretrieved |
| `ot_isaiah_53` | Thin |
| `ot_micah_6_8` | Empty |
| `ot_daniel_7` | Misretrieved |
| `nt_matthew_5_7` | Thin |
| `nt_john_1` | Misretrieved |
| `nt_romans_8` | Misretrieved |
| `nt_1_corinthians_13` | Strong |
| `nt_james_2` | Thin |
| `nt_revelation_21` | Thin |
| `context_proverbs_genre` | Empty |
| `context_apocalyptic_genre` | Thin |
| `context_agape` | Misretrieved |
| `context_covenant_word` | Strong |
| `context_second_temple` | Misretrieved |
| `context_biblical_geography` | Misretrieved |

## Full-answer sample

The producer returned 11 `answered` outcomes and one `no_material`. Across the
12 answers it used 131 retrieved chunks and exposed 69 citations. **44 of 69
citations (63.8%) were Derek Prince.** The remaining 25 comprised six with no
author, Shabaka Williams 5, Andrew Murray 4, Scott Woodard 3, Daniel Kolenda 2,
Paul Kidd 2, and one each from Jack Deere, Ruth Prince, and Wayne Conrad.

This concentration is not confined to explicitly Pentecostal questions. It
shaped answers about justification/sanctification, the Abrahamic covenant,
Isaiah 53, the Trinity, and the whole biblical story.

### What the answer sample demonstrated

1. **Strong retrieval does not mean broad framing.** The Holy Spirit answer
   used nine citations but centered subsequent Spirit baptism and continuing
   gifts. The 1 Corinthians 13 answer treated love as the channel for continuing
   gifts, with five of six citations from Derek Prince. The baptism answer
   stated a particular relationship between water baptism and salvation as a
   "crucial New Testament distinction." These may faithfully represent their
   sources, but they do not constitute a neutral baseline shared across broad
   Christian traditions.

2. **A narrow route can replace broader corpus evidence.** The retrieval scan
   found direct Robert Trail material comparing justification and
   sanctification. The full producer instead matched the stored-position topic
   `holiness and personal purity`, narrowed the evidence to 15 Derek Prince
   citations, explicitly admitted that those sources did not directly cover
   justification, and then supplied the entire justification half from outside
   the retrieved evidence. This is a routing-policy gap, not an ingestion gap.

3. **Thin evidence becomes confident doctrinal synthesis.** The Isaiah 53
   answer used six Derek Prince citations and presented physical healing in the
   atonement as the passage's settled conclusion. The Abrahamic-covenant answer
   used five citations, three from Prince, and incorporated a particular view of
   Israel's land and future into a general overview. The whole-Bible answer made
   a minority restoration/gap reading of Genesis 1:2 the organizing frame for
   creation-to-new-creation.

4. **Empty handling is inconsistent.** Proverbs genre returned the clean
   65-character `no_material` response. Micah 6:8 had zero retrieved chunks and
   zero citations, correctly disclosed the library gap, but then supplied an
   uncited explanation of Micah's covenant-lawsuit context anyway and returned
   `answered`. The distinction is user-visible and cannot be explained by corpus
   coverage alone.

5. **One retrieval run is not a stable verdict.** `nt_john_1` was
   misretrieved in the 48-case scan, but the full producer's later retrieval
   found six relevant chunks and produced a direct incarnation answer. Some
   difference comes from the full producer's routing/context stages; provider
   variance may also contribute. This baseline identifies coverage risk, not a
   deterministic per-question SLA.

6. **Reference verification is not the same as coverage.** The 12 answers
   recorded 46 verified references, but two substantial answers with multiple
   explicit verse references recorded zero verified references. Conversely,
   Micah recorded one verified reference with zero retrieved chunks and zero
   citations. Reference counts cannot substitute for source-grounded depth.

## What this means for ingestion

Bulk YouTube ingestion is not the next best move. It would add more sermon
material to a system already producing broad biblical answers primarily from
one sermon teacher. The measured gaps are passage exegesis, literary genre,
historical/geographical context, and whole-Bible synthesis.

The highest-leverage next measurement is a **read-only commentary
counterfactual** using these same 48 questions:

1. Compare current answer-eligible retrieval against the existing Study Mode
   commentary/reference corpus.
2. Determine how many of the 15 empty/misretrieved cases already have relevant
   material among the 493 commentary documents, 2,176 word-study documents,
   lexicons, and reference datasets that normal answers exclude.
3. Only after that comparison decide whether the shortage is ingestion,
   classification, or a deliberately narrow serving policy.

If new ingestion is still needed after the counterfactual, prioritize curated
public-domain biblical reference works organized by passage and topic—not more
general sermon transcripts. Any later decision to let interpretive reference
material influence answers requires Alex's explicit product/doctrinal approval;
this audit does not authorize it.

## Findings and classification

- **Scheduled — A1/A4 corpus measurement:** run the 48-case Study Mode /
  commentary counterfactual before selecting new sources. Smallest closure:
  current-vs-reference coverage table with the same relevance rubric.
- **Scheduled — product-track answer grounding:** distinguish clean
  `no_material` from "disclose the gap, then answer from model knowledge."
  Evidence: `context_proverbs_genre` versus `ot_micah_6_8`. Smallest closure:
  an explicit product decision plus a deterministic acceptance case for both.
- **Scheduled — routing-policy review:** measure whether stored-position
  narrowing discards stronger directly relevant evidence on ordinary biblical
  questions. Evidence: `salvation_justification_sanctification`. Smallest
  closure: reproduce the case with route stages exposed and decide intended
  precedence; no fix is authorized here.
- **Parked — retrieval variance:** `nt_john_1` changed from misretrieved to
  relevant between the scan and producer sample. One occurrence does not justify
  a blocker or reliability project; revisit only if repeat measurement shows a
  material rate.
- **Parked — verified-reference count mismatch:** zero verified references on
  two verse-rich answers and one on the zero-evidence Micah answer. This audit
  did not inspect raw mention-block output, so mechanism and consequence remain
  incomplete.

No finding is promoted to Blocker by this audit. The credible user-facing
consequence is broad biblical questions receiving narrow or unsourced framing,
but the existing beta gate is frozen and Alex has not designated this new
baseline as displacing another item.

## Process measures

- Original outcome completed: **yes**.
- Unplanned investigations started: **0**.
- Findings promoted to Blocker: **0**.
- Active critical-path item count during audit: **1**.

