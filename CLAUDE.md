# New Wine — Agent Context

AI-assisted Bible study tool for Spirit-filled/charismatic believers. RAG chat
with inline citations over a vetted, named corpus. Product model: Magisterium AI.
UX model: Perplexity.

**Design filter for any new feature:** does it make New Wine sound more like a
spiritual authority in its own right, or more like a directory pointing to real
ones? The former is always wrong. Time-in-app is not a success metric — the goal
is sending users back to real teachers and real churches. A feature that makes a
user say "I don't need my pastor, I have New Wine" gets killed regardless of
quality.

---

## Ranked failure modes (2026-08-01)

Judge every answer-path change against these, in this order. An accuracy fix
that trades one of these for another has improved nothing:

1. **Theologically wrong answers.** Worst outcome; would make Alex consider the
   product broken.
2. **Misrepresenting a teacher** — putting a position in a real, often living
   minister's mouth that he does not hold.
3. **Generic answers** — reading as interchangeable AI output rather than
   specific to how the question was asked. Fresh per-question synthesis was
   chosen precisely to avoid this; a correctness fix that makes every answer
   uniform has traded failure mode 1 for failure mode 3.

Most questions are general and topical ("what is deliverance"), not
teacher-specific — weight accordingly.

## Settled product decisions (2026-08-01) — do not reopen

Premises from the 1 August build plan (four adversarial architecture audits
across two independent coding-agent tools, two rounds, the last two with live
DB, independently convergent). Design within them; do not relitigate. Where one conflicts with an
existing rule it is flagged inline with ⚠ — **flagged, not resolved, this
records pass** (resolving each means a code change or a governing-doc edit a
later session makes deliberately).

1. **Fresh synthesis every question**, shaped to how the user asked. Stored or
   pre-reviewed answers are permanently rejected — a review model can't
   enumerate hundreds of thousands of questions in advance. No human review gate
   anywhere on the serving path. ⚠ *Tension to watch: the position serving path
   stores and re-serves generated positions and has a planned draft-review UI
   (`docs/plan-archive.md` #48 / archived Open Decision #20(b)) — reconcile if/when that path goes live.*
2. **Launch bar is "materially safer,"** not a demonstrated error rate. No public
   claim about fabrication frequency. Deterministic correctness where it can be
   guaranteed; honest disclosure where it cannot.
3. **Eliminating invented claims is accepted as impossible.** Misattribution to a
   name is solvable deterministically (the permitted-name set is finite and
   computed before the answer is written); inventing the substance is not, at any
   timeline. Reinforces the Landmines fabrication findings and Open Decision #20.
4. **The probabilistic claim-support checker is HELD, pending measurement.** Do
   not build one. Do not propose a model-based judge anywhere — that shape has
   failed five times (Open Decision #20).
5. **Commentaries are excluded from answers; searchable only** (Alex's call,
   1 Aug). **RESOLVED in code 2026-08-06/07** — answer retrieval hard-excludes
   `source_kind`/`source_type` commentary at Step 2.6 (before collapse/rerank),
   with a second strip after neighbor expansion. Soft down-weight +
   `COMMENTARY_CONTEXT_CAP=3` retired. Study Mode (`/study/commentary`,
   `match_commentary_*` RPCs) is unchanged and remains the searchable surface.
   Helpers: `is_commentary_chunk` / `exclude_commentary_chunks` in
   `backend/app/services/answer_toolbox.py` (moved out of the now-deleted
   chat.py, 2026-08-07 mirror-unification job) — one implementation, not two.
6. **Paragraphs that cannot be tied to a specific statement still display** — not
   flagged, not logged, not blocked. Deliberate, to avoid drowning in false
   positives from connective prose. Alex will revisit.
7. **No teacher taxonomy** — teachers are never labeled into theological
   families; contributors are always derived from the evidence at question time.
   *(Already enforced as Invariant 13's standing rule — restated here as a
   product premise, not a second rule.)*
8. **Position Papers are doctrinal grounding, not served answers.** Hand-authored
   by Alex on the charismatic pillars; they constrain what an answer may claim
   and must never supply its phrasing; triggered deterministically by topic,
   never by the system self-assessing "doubt" (unreliable, and would skip the
   paper exactly when it mattered most). **RESOLVED 2026-08-06 (Alex's ruling;
   built, not just decided) — the conflict this decision flagged since
   2026-08-01 is closed in this decision's favor, not left standing.** A
   position-paper match no longer bypasses retrieval: the paper's own body is
   injected as bounding `[House Position]` silent context (never cited, named,
   quoted, or copied), and the answer is generated from real retrieved teacher
   material with real citations, through the normal guarded answer path.
   Invariant 12's note (b) and ARCHITECTURE's "Position papers" section are
   corrected to match, not left blessing the retired mechanism. See Settled
   decisions #16/#17 below for the two rulings that came with this (exclude
   contradicting teachers; paper-voice-plus-disclaimer fallback when exclusion
   empties the answer) and `backend/app/services/position_paper_exclusion.py`.
9. **House view and teacher view are two visibly separate things in an answer,
   never blended.** **RESOLVED 2026-08-06, alongside decision #8** — the
   flagged guardrail (`system_prompt.txt`'s conviction-first self-check) no
   longer instructs the model to silently rewrite an already-attributed
   dissenting teacher into agreement; it now states New Wine's conviction
   alongside a named source's own view, never instead of it. The deeper case
   this guarded against — a genuinely contradicting teacher reaching the
   writer for a position-paper-matched topic — is now handled upstream by
   decision #16's exclusion mechanism, so the writer rarely even sees one to
   begin with.
10. **Tongues is a house position, not a debate** (Alex's ruling, 1 Aug): not
    required as initial evidence of Spirit baptism, but reasonably expected for
    all. The neutrality list shrinks by one.
11. **Healing mechanics, prophetic accountability, apostolic authority, and
    eschatological timing stay debates** (eschatological timing added
    2026-08-05) — presented with named teachers on both sides. Alex has no
    settled view and will let the corpus inform it over time. Caveat on
    record: what the corpus says is a function of who is in it, not of what
    is true — a corpus majority must never quietly become a house position
    without a deliberate decision. **Sanctification models is NOT a debate
    topic** (Alex's ruling, 2026-08-05) — it was a candidate under
    consideration during Project 2 phase 1 design but was determined not to
    be a genuine live debate; it is an ordinary topic with no standing
    exception, same as any topic without one. This is a removal, not a
    deferral — do not re-add it as a pending/future anchor.
12. **Hidden-by-default is reversed: new material defaults to visible**, and
    everything currently hidden becomes visible. Safe now only because there are
    no users; it buys time, not a pass — known quality problems still clear
    before launch. ⚠ *Conflict flag: contradicts ARCHITECTURE's "Standing source
    policy" ("new unlicensed sources register hidden") and the "DEFAULT hidden =
    fail-closed" source design. The license gate SQL (Invariant 2) is unchanged —
    only the default visibility flips. Phase 1 item 1.3 is the code change +
    inventory; the ARCHITECTURE update is flagged, not made this pass.*

---

## Settled product decisions (2026-08-03) — build-plan reset; do not reopen

From two external adversarial reviews (one correctness-focused, one scope-cutting)
of a written proposal, plus Alex's decisions. These supersede parts of the
2026-08-01 plan; design within them. Full roadmap detail: PLAN.md "CURRENT BUILD
SEQUENCE (2026-08-03)".

13. **Build order is three projects, in sequence: (1) scalable async answer
    execution → (2) one named voice per answer → (3) hand-curated, server-gated
    quote rail.** Supersedes the 2026-08-01 phase ordering and PLAN.md Ordering
    Call G.

14. **Capacity target = 100 simultaneous generations, as a DIAL not a ceiling.**
    Exceeding 100 must mean running more workers, never a rebuild; any design
    choice that forecloses horizontal scaling is flagged and refused at review.
    Real per-answer COST must be measured before Project 1 is designed — cost may
    be the true ceiling; do NOT size from the partial extraction-cost figure on
    record. **MEASURED 2026-08-03 (`docs/audits/2026-08/per_answer_cost_measurement_2026-08-03.md`):
    median normal answer $0.039 (house-voice ~$0.015; teacher card ~$0.015/open)
    — cost is comfortable, NOT the ceiling; the real open ceiling at 100
    concurrent is provider rate limits (RPM/ITPM/OTPM), unchecked from the repo
    — a commercial conversation. The instruction block is already cached (~25%
    saving at scale); the per-question retrieved context (~50% of cost) is the
    un-cacheable driver. This figure replaces the partial-extraction number as
    the sizing basis.** The reveal moves to the CLIENT after the checked answer is delivered;
    no client connection ever owns a generation worker; retries must not skip the
    accuracy check. One app / one queue / one DB / one scalable worker
    deployment — not microservices.

15. **One named voice per answer — the writer gets ONE teacher's propositions
    per answer, for single-teacher topics. The safety goal is achieved by
    narrowing what material reaches the writer, not by relocating who writes
    the attribution.** **Corrected 2026-08-06 (Project 2 phase 1 design
    session), decided not deferred** — this decision's original wording, "the
    RENDERER (not the model) attaches names and links," is RETIRED as a build
    target, not left as unmet future work. Reasoning, recorded so it is not
    re-litigated: (a) the real product goal is preventing a claim being
    credited to the wrong teacher, not relocating who writes the attribution —
    the original wording conflated mechanism with goal; (b) locking retrieval
    to one teacher does NOT make the model's self-attribution correct by
    construction — it retains parametric knowledge of other charismatic
    teachers, the exact mechanism behind the documented tongues-answer
    fabrication ("not a retrieval gap... it knew too much"); (c) the existing
    `reference_verifier.py` guard (`_ungrounded_reference_teachers` /
    `ungrounded_prose_teachers` → regenerate-once-then-refuse) already catches
    this and gets strictly MORE precise with a size-1 permitted-name set — no
    new machinery needed; (d) true renderer-side injection would require either
    rewriting the entire citation-instruction surface to produce unattributed
    prose, or post-hoc sentence-level name insertion — the latter directly
    contradicts the standing "never surgically edit prose (mangling risk)" rule
    and Settled decision #6. This IS the source-blind path; do not build
    "source-blind generation" as a separate project. It structurally closes
    claim-level A2 misattribution (the other teacher's material is never in the
    generation) — a failure previously logged as uncatchable. **Phase 1 scope
    (confirmed):** single-teacher topics only, enforced at retrieval/context-
    assembly (`producer.py` -- the primary chat-style answer path since
    chat.py's deletion, 2026-08-07 mirror-unification job; a second,
    structurally different served-generation surface, `get_teacher_card()`,
    exists too — corrected in full at the Landmines entry on that job);
    in-house-debate topics
    (decision #11) are OUT of phase 1 and keep working unchanged — full design
    in PLAN.md's CURRENT BUILD SEQUENCE, Project 2. Teacher profile pages
    precompute instead of regenerating from source text per view
    (`get_teacher_card()` is the standing live-synthesis leak — found this
    session to be per-(teacher, question), not per-teacher, so its fix is NOT
    independent of phase 1 as originally assumed; it needs the same
    topic-classification layer phase 1 must build for debate-topic detection —
    see PLAN.md).

16. **Quote rail is manual-approval only; automated extraction is deferred.**
    **REVERSED 2026-08-08 (Alex's explicit decision, per-quote review did not
    scale) — see "Settled product decisions (2026-08-08)" below. The "manual-
    approval only" sentence and the "auto-transcripts are ineligible unless a
    human checked the passage against the audio" sentence immediately below
    are BOTH superseded: approval is now automatic (verifier-gated, not
    human-gated), and the transcript-ineligibility rule was deliberately not
    built (2026-08-08 decision 19) — do not read either as current. Every
    other sentence in this item (no-trimming, affirmative clearance, the
    per-work cap, quote-IDs-not-text, the single resolution point,
    revocation-as-state-change) still stands, unchanged by the reversal.** An
    AI may PROPOSE quote candidates, never APPROVE one. Eligibility, all binding:
    auto-transcripts are ineligible unless a human checked the passage against the
    audio (~61% of the current evidence layer is auto-transcript from two LIVING
    ministers — a mistranscribed sentence in quotation marks under a living
    minister's name is the worst failure available to this product); also
    initially ineligible — OCR, translations, anthologies/compilations,
    interviews, guest-speaker material, mixed-author magazine pages, scraped
    reposts, any unresolved nested quotation. The real boundary is CONFIDENCE THAT
    THE STORED TEXT IS THE ACTUAL AUTHORED TEXT — not spoken-vs-written. A
    translation is never a teacher's exact words. A quote never appears without its
    restated point beside it. **NO words trimmed at either end — whitespace and
    punctuation only** (SUPERSEDES the earlier "any trimming is recorded" rule;
    the front of a sentence is where negations/conditionals live, and a trim can
    reverse meaning while passing every check). A source must be AFFIRMATIVELY
    cleared — absence of a known problem is not clearance. Cumulative unique
    approved-quote text per work is capped AT APPROVAL TIME (not render-time
    counting). Generated answers carry quote IDs, never text; one server-side
    resolution point serves every surface; revocation is a state change.

17. **The enforceable quote claim.** "A quote cannot be fabricated because the
    model never generates one" is NOT enforceable — withholding source text does
    not stop the writer emitting quotation marks, attribution language, or wording
    recalled from training. Do not record, ship, or publish it. The ONLY permitted
    claim: *text receives verified-quote treatment only through the verified-quote
    component, authorized by a current, approved provenance record.* Supporting
    controls: the prose channel must be prevented from rendering quotation
    typography and verbatim-attribution language; restated points must be
    prevented from carrying quotation markup or first-person teacher
    impersonation.

18. **Position layer cut down — durable stored positions deferred. UN-DEFERRED
    2026-08-04 (Alex's explicit call) — see below.** The single-voice half is
    Project 2; persistence, rebuild triggers, replace-vs-version, review UI,
    and empty-state redesign were DEFERRED pending real usage. The 2026-08-01
    corpus-ban lift STANDS (not re-imposed); corpus positions were simply not
    built on. Foundation stays as built.
    **Un-deferred 2026-08-04, then substantially revised the same day.**
    Steps 1-3 of the original 4-step revival plan (inventory, speed, license
    gate) were built and verified. Step 4 (connect + prove) mapped the
    answer path and proposed a deterministic groundedness check — then,
    before any of it was built, an adversarial pressure test of the whole
    store-then-synthesize (two-hop) shape found it FATALLY flawed: a check
    on the generated answer cannot see drift already baked into the stored
    position (proven live, not hypothetically — a documented fabrication,
    Ravenhill/Philippians 4:8-9, was found still `eligible=true` and
    already feeding a real stored position's evidence); reactive
    invalidation is not computable from what's recorded today and
    structurally cannot detect corpus material being ADDED, the dominant
    real case (517 new eligible propositions landed 2026-08-03); no
    concurrency guard or failure memory existed for either hop.
    **The accepted direction is now ONE hop, not two:** a matched
    position's underlying PROPOSITIONS — never its rendered text — feed
    the answer path's existing, already-hardened retrieval/generation/
    verification pipeline directly (`producer.py` -- the primary chat-style
    answer path since chat.py's deletion, 2026-08-07 mirror-unification
    job); the
    position's own generated text
    becomes a build-time human-review artifact only, never served. Same
    day, narrowly scoped: 2 of the 3 documented fabrication cases (Conlon,
    Ravenhill) are now `eligible=false` (content not rewritten — undecided;
    the third, Savchuk's "Devil's Voice", is a strong content match, never
    ID-confirmed, deliberately left untouched) — and rebuilding the one
    dependent position demonstrated the layer's real volatility live:
    removing one bad proposition flipped `holiness and personal purity`
    from a 4-teacher corpus position to a Prince-only teacher position, not
    a minor drift. **Corrected 2026-08-08 — no longer true: the revised
    one-hop design IS now built.** Open Decision #16 (topic list) is
    RESOLVED (V1 adopted 2026-08-06/07, six topics — see `docs/plan-archive.md`);
    the matcher (`match_stored_position()`) shipped 2026-08-07; the
    evidence-injection wiring itself shipped 2026-08-08 (commit `eca8070`,
    `backend/app/services/stored_position_evidence.py` + `producer.py`) and
    is verified end-to-end with real generation on all six seeded topics —
    zero stored-position-text leakage into any served answer. Built and
    verified. **Confirmed pushed to origin and live in production as of
    2026-08-13** — supersedes this entry's earlier "NOT pushed to origin as
    of 2026-08-08" note, which is stale; `eca8070` is confirmed an ancestor
    of `origin/main`. Full current status, including what's still
    deliberately out of scope (production concurrency/rollout): PLAN.md
    Phase 3 item 5.
    **Open Decisions #14 (refresh trigger) and #15 (replace-vs-version) are
    RESOLVED 2026-08-08 — see Settled decisions #21/#22 below.** This
    paragraph's own earlier "#14 now answered by... / #15 unchanged...
    remain ACTIVE" language was self-contradictory (described an answer,
    then called the question still open) — corrected here rather than left
    standing. Full diagnostic,
    pressure test, remediation, and revised design (with a ranked list of
    what's still weak even after the revision):
    `docs/audits/2026-08/position_layer_revival_diagnostic_2026-08-04.md`.

## Settled product decisions (2026-08-06) — position papers as fence; do not reopen

Alex's ruling, resolving Settled decisions #8/#9's flagged 2026-08-01 conflict
(see those decisions above — RESOLVED in place, not superseded). Built the same
session: `backend/app/services/position_paper_exclusion.py`,
`backend/app/services/position_papers.py`'s `render_paper_voice_with_disclaimer()`,
and the retrieval-path wiring in `producer.py` (originally also wired into
chat.py; that side is moot since chat.py's deletion, 2026-08-07
mirror-unification job — `producer.py` is the primary chat-style answer
path now; the position-paper fence is deliberately NOT extended to
`get_teacher_card()`'s second served-generation surface — see the
Landmines correction on that job for why).

16. **Retrieved teacher material that contradicts a matched house position is
    excluded from the answer, never presented alongside it and never silently
    reframed into agreement.** Whether a teacher "contradicts" is a per-answer
    model judgment, not a deterministic check, and will sometimes be wrong in
    both directions — Alex was told this directly and accepts it; this is an
    explicit, authorized exception to this codebase's usual posture against
    LLM-based judgment calls (Open Decision #20's five failed attempts were at
    a different problem, post-hoc claim-support verification on an unmatched
    answer — this is a pre-generation content filter with a narrow, structured
    per-teacher verdict, not the same shape). Every exclusion is logged
    (question, teacher, topic, reason) so the false-exclusion rate is
    measurable later, per the same measure-before-building discipline used
    elsewhere. This makes answers on house-position topics read more like
    consensus than the corpus's full range of material would otherwise show —
    accepted, not an oversight. Do not build a corrective for either point
    without Alex revisiting it first.
17. **If excluding every retrieved teacher would leave an empty answer, fall
    back to the position paper's own voice — a sanctioned form under the
    No-Oracle Rule — carrying the standard disclaimer** ("New Wine can make
    mistakes. Please let us know if you see any."), appended deterministically
    in code, never left to the model to phrase. This is the ONLY sanctioned
    reason for this fallback: never thin retrieval, never a match failure,
    never an error — those keep using the product's existing graceful-
    degradation / clean-error handling, unchanged. Every time this fallback
    fires is logged.

## Settled product decisions (2026-08-08) — quote rail: human approval removed; do not reopen

Alex's explicit decision, reversing the 2026-08-03 section's decision #16
("Quote rail is manual-approval only... every quote must be manually
reviewed and approved by a person, never generated or approved by AI") —
that item is annotated REVERSED in place, not deleted, so the history of
what changed and why is visible rather than silently dropped. Reason for
the reversal, stated by Alex directly: per-quote human review did not
scale. Built the same session: migration 085 (schema), the tightened
`backend/app/services/quote_verifier.py`, the reworked
`backend/app/services/quotes.py`, `scripts/apply_migration_085.py`
(6/6 live-DB checks passed), extended `scripts/test_quote_verifier.py`
(22/22 checks passed, including a live re-check that both quotes already
approved in production still pass every tightened rule), and
`scripts/remediate_savchuk_proposition_2026-08-08.py`.

18. **A quote is now approved automatically — the moment it passes
    `verify_quote_candidate()`, with no person confirming it.** Nothing here
    is an LLM/AI judgment call either; every check is deterministic (string
    matching, position arithmetic, a document lookup), the same posture as
    the exact-substring check that already existed. **The architecture no
    longer guarantees a served quote was human-verified — say this plainly,
    don't soften it.** What replaced the human backstop, in exchange:
    - The database trigger's admin-role approver gate (migration 082's
      Gate 1) is REMOVED (migration 085) — `enforce_quote_approval_gates()`
      no longer checks that `approved_by` is a currently-admin-role user.
      `approved_by`/`created_by` stay NOT NULL FK columns (unchanged table
      CHECK + FK) — every row still names a real authenticated caller for
      provenance, it just no longer has to be admin-role for the row to
      become approved. This was the actual enforcement — migration 082's
      own header claimed "no code path anywhere can set status='approved'
      without a real admin-role user_id attached"; that guarantee is
      intentionally retired.
    - A new speaker-confirmation gate is ADDED, at both layers: the
      attributed `teacher_source_id` must equal the source document's own
      `source_id`, checked in `verify_quote_candidate()` and, structurally,
      in the same database trigger (migration 085) — a content match is not
      confirmation, per the Savchuk case below.
    - A new boundary-proximity / sentence-completeness check is ADDED,
      Python-only (an accepted narrower boundary, same posture as the
      per-work quote-text cap): a candidate must not sit flush against
      either edge of its chunk, must open immediately after another
      sentence's terminal punctuation, and must itself end on terminal
      punctuation. The automatic form of "no words trimmed at either end."
    - Commentary exclusion, the document-clearance requirement, the
      exact-substring match, the two-teacher scope limit, and the per-work
      quote-text cap are UNCHANGED.
    - Every acceptance and refusal is written to `quote_verification_log`
      (migration 085, new table) — a record, not a review queue. Nobody
      reads it routinely; it exists so a served quote's approval path is
      reconstructable if one ever needs checking.
    - The Derek Prince "fasting" quote (already approved, `source_kind=
      sermon_transcript`) STAYS approved — see decision 19 below for why a
      transcript-status gate was considered and explicitly not built.

19. **No protection exists against auto-transcribed material being quoted
    verbatim — deliberate, not an oversight.** A transcript-status gate
    (refuse any candidate from an auto-generated transcript unless a human
    confirmed it against the audio) was drafted for this session and
    dropped on Alex's explicit ruling: the `sermon_transcript` label on
    Derek Prince's documents does not mean auto-transcribed audio for this
    corpus — it's a historical label on written content, not a signal that
    the text needs audio confirmation. Nothing was relabeled; no audio-
    verification mechanism was built; nothing gates on transcript status.
    **REALIZED 2026-08-29 — the risk is no longer prospective. This
    corrects the entry's own earlier "prospective, not retrospective —
    applies to how the corpus could grow, not to anything in it today"
    framing in place, rather than stacking a note on top of it.** The CLF
    Church ingestion (56 YouTube sermons — see the Landmines entry below)
    put genuinely auto-transcribed audio into the corpus under
    `sermon_transcript`, and a mistranscription is confirmed present in it:
    one sermon's captions render "ceasing" as "seizing", found while
    auditing that document's `1 Thessalonians 5:17` reference. Nothing
    gates on transcript status, so this quote rail still has no check that
    would stop a garbled phrase reaching the quote surface. There is no
    live exposure today only because `QUOTE_SELECTION_ENABLED=false`
    (Settled #30). Before that flag is flipped back on, CLF material must
    be either excluded from quoting or given an audio-confirmation step —
    do not discover this by shipping a bad quote.

## Settled product decisions (2026-08-08, session 2) — position-layer governance, quote-rail scope, product rename

Sixteen decisions Alex made this session, records-only (no code/DB touched
by the decisions themselves — one live-DB SELECT via the
`newwine_readonly_analysis` role confirmed corpus facts for the Phase 4
rescope below). Eight are architecture/product-shape calls, recorded here.
Four are doctrinal framing calls for named position papers — recorded
directly in the papers (`docs/position_papers/`), not restated here. Three
are pure roadmap/operational calls (20s latency target, next quote-curation
priority, merging two overlapping checks) — recorded in PLAN.md only. One
(a Precept Austin "sourcing leak downgrade") was found already resolved
2026-08-07 and was skipped rather than re-recorded as still-open — see
PLAN.md's Open Decisions note.

20. **Teacher-dominance threshold (`DOMINANCE_THRESHOLD=0.60`, Invariant 13) gets no manual override mechanism.** Closes Open Decision #13. The threshold stays exactly as-is; there is no per-case runtime override path. Near-boundary cases get logged for later review instead. Reason: an override path means stored exceptions, ongoing maintenance, and re-review as the corpus grows — real cost against a problem that hasn't actually been observed yet. Revisit only after real usage produces real edge cases. This does not freeze the constant itself — Invariant 13's "reasoned, overrulable starting point, not a calibrated constant" framing still stands for Alex revising the number in code later; what's closed here is a *runtime* override mechanism, a different thing.

21. **Stored-position refresh: automatic re-check, escalate only meaningful shifts — new admin-panel notification dependency.** Closes Open Decision #14. When new material lands that touches a stored position, the system re-checks on a schedule automatically; routine, non-material drift updates silently. A MEANINGFUL shift — one that would change the position's substance, flip single-teacher to blended, or introduce a real contradiction — must be flagged to Alex, specifically as a notification inside the ADMIN PANEL, not email. **Admin-panel notifications do not exist as a feature today** — this is now a real, separate build dependency of the refresh mechanism (PLAN.md Horizon item 4 depends on the same not-yet-designed surface). This also corrects Settled decision #18 above, whose "now answered by periodic re-gather-and-diff... remain ACTIVE" language was self-contradictory — periodic re-gather-and-diff with a severity-tiered response IS the accepted shape; it just hadn't actually been decided until now.

22. **Rebuilt positions keep version history.** Closes Open Decision #15. Not a reversal of anything live: no document in this repo ever recorded "replace" as the decided default (Open Decision #15 read "Not decided" continuously since 2026-07-28), and the code already does this — `scripts/positions.py::_insert_position_version()` never overwrites a prior version, flips `is_current=false`, and inserts a new row (`supersedes_id` set, `lineage_id` shared, `version` incremented). This decision formally closes the open question in favor of the versioning behavior already built, and states the reason for the record: the product's entire positioning is accountability and traceability, and silently discarding what a position used to say contradicts that.

23. **Quote review tool stays admin-only.** No broader access, including now that quote approval is automatic (Settled decisions #18/#19 above). Confirmed unchanged: every route in `backend/app/routers/quotes.py` already gates on `Depends(require_admin_role)`. Reason: broader access multiplies who can introduce a bad quote candidate with no corresponding benefit.

24. **Quotes serve on `producer.py` only — the sole chat-style/async answer path, not the sole served-generation surface.** Corrected 2026-08-15: this decision originally read "there is exactly one answer path today, and it always runs quote selection," which was never true of `get_teacher_card()` (`GET /study/teacher/{source_id}`), a second, always-existing served-generation surface — full correction at the Landmines entry on the 2026-08-07 mirror-unification job. `chat.py` (the synchronous fallback this decision originally distinguished against) is still deleted — that part stands. What's actually true: quote selection is wired into `producer.py` alone; `get_teacher_card()` never selected or served quotes and still doesn't (confirmed 2026-08-15 — out of scope for that session's guard work, since there was nothing there to guard). If a second synchronous CHAT-STYLE path is ever reintroduced, this decision's original policy (quotes on the primary/proven path only, revisit after concurrency is proven at the 100-dial) governs again.

25. **The product is renamed New Wine** (Alex's direction, 2026-08-31). Rhemata is retired as the product name. **This supersedes the "Manna" naming this decision carried from 2026-08-08 — corrected in place, not stacked, because a stale target name is exactly the kind of thing a future session would act on.** **Correction, 2026-08-31 (this entry previously claimed "Manna was never implemented anywhere; the only trace is one unbuilt hero plan" — that was false and is corrected in place, not stacked).** Manna WAS built and shipped: the dawn hero landed 2026-08-10 (`df27425`, `d3f7dbf`, `6e9ff7a`) as `manna-dawn-hero.tsx` + `manna-hero-motion.ts` + `--manna-*` CSS variables, and was live on `/home` until the 2026-08-31 rename pass renamed it to `newwine-dawn-hero`. The "provision, not source" framing does die with the name. **A THIRD legacy name also existed and no document recorded it: UpperWord.** The marketing surface was rebranded Rhemata → UpperWord on 2026-08-13 (`8795384`), so the homepage wordmark, nav, hero copy and CTA read "UpperWord" — the first thing any visitor to `newwine.app` saw — until the same pass. Both are now New Wine. `newwine.app` is registered, DNS-live on Cloudflare → Vercel, and serving. **The name collision with the New Wine magazine corpus source (Invariant 17, `scripts/magazine_review/`, roadmap A2) is ACCEPTED, not overlooked** — Alex's ruling: it is New Wine *magazine* vs New Wine *app*, uncopyrighted. Do not re-raise it. Naming decision only: renaming the repo, the Vercel/Railway projects, the `newwine_readonly_analysis` role, or any identifier is separate work — full scoping in `docs/audits/2026-08/rename_inventory_2026-08-31.md` — but **read that inventory's scope before trusting its counts: it searched "rhemata" only, so its 972 hits across 219 files missed every "UpperWord" and "Manna" instance entirely**, including the live homepage wordmark. Any future name sweep must search all legacy names, not just the most recent one. Of the three traps recorded there, two are now spent: the `ῥήματά`/John 6:63 tagline was replaced with Luke 5:38 and the five localStorage keys were renamed (guests logged out, approved). **The third stands permanently: a `chunks` row in a public-domain Jamieson-Fausset-Brown commentary contains the transliterated Greek "ta rhemata" and must never be swept** — it is Greek, not the product name. Corpus data generally is off-limits to any name sweep: `sources/` carries "rhema" as a lexical entry and "manna" as the biblical food throughout.

26. **Precept Austin word-study material: excluded for now, not permanently.** Corrects the framing implied by the archive's old "PA permanently excluded" shorthand (`docs/plan-archive.md`, an unrelated older "gift"-reversal episode, not this retrieval exclusion — but close enough in wording to invite confusion). The 2026-08-07 hard-exclusion fix (Landmines, below) stays exactly as built — nothing here weakens it. What's new: finding a reliable, trustworthy method of reintroducing PA word-study content into answers without meaning drift is now a recorded future initiative (needs real scoping before any work happens; not scheduled — PLAN.md Horizon item 7). Distinct from Open Decision #10 (PA word-study *rewrite*/modernization) — a different question. **The separate, permanent exclusion of Precept Austin from the quote pipeline and from paraphrase generation is UNCHANGED** — this decision touches only the answer-retrieval hard-exclusion, not those.

27. **The two ID-confirmed fabricated-proposition passages stay out permanently.** Ravenhill/Philippians 4:8-9 and Conlon/Matthew 7:21-23 (both `eligible=false` since 2026-08-04, Landmines below) are not rewritten and not reinstated — closes the "Alex has not ruled on whether to also correct the stored text" question the Landmines entry left open for these two. Reason: a rewrite risks introducing a newer, subtler error, and two passages is not a real content gap. The Savchuk case is a separate, still-open question — never ID-confirmed against an original finding, unlike these two, so it is not automatically covered by this ruling.

## Settled product decisions (2026-08-19) — quote teacher scope

28. **Teacher scope for served quotes is OPEN** (Alex's decision,
    2026-08-19) — a relevant quote may appear on any answer about the
    subject regardless of which teacher's material the answer prose was
    generated from. Closes the teacher-scope question PLAN.md W7–W8 left
    open. The accepted risk, recorded verbatim, not softened: Alex was
    told directly that a quote appearing beside prose built from a
    different teacher's material can read to a user as that teacher
    endorsing a claim he did not make — ranked failure mode #2, teacher
    misrepresentation, and worst with living ministers. Alex accepts
    this.

    The consequence, recorded as a requirement, not a suggestion: under
    open scope the entire safety burden falls on PRESENTATION — a served
    quote must be visually separated from the answer and carry its own
    teacher and source attribution attached to the quote itself, never
    inferred from surrounding prose. Presentation must be designed and
    settled BEFORE the quote rail is re-enabled.

    Also record: open scope makes match quality load-bearing in a way
    teacher-locked scope did not — under locked, a weak match is a
    slightly-off quote from the right teacher; under open, a weak match
    puts the wrong teacher's name beside a claim.

    **Corpus concentration, confirmed live 2026-08-19 via the
    `newwine_readonly_analysis` role:** of 793 quotes in the corpus, all
    but one are Derek Prince's; Andrew Murray has exactly 1. A 20-quote
    random sample drew 20 Derek Prince quotes, consistent with that
    distribution. Consequence, recorded so a future session does not read
    "open scope" more generally than it operates: with this corpus, open
    teacher scope means in practice that Derek Prince quotes may appear
    beneath answers generated from every other teacher's material,
    because there are no other teachers' quotes to serve. Every
    cross-teacher quote appearance is Prince's name beside another
    teacher's teaching. Alex confirmed the open-scope decision after
    being told this directly. This raises the presentation requirement's
    importance rather than changing it — the requirement above (visual
    separation, teacher and source attribution attached to the quote
    itself, settled before the quote rail is re-enabled) is unchanged.

29. **Model-involved quote quality / serveability gating is an authorized
    exception** (Alex's decision, 2026-08-19) — parallel posture to Settled
    decision #16's contradiction filter, not a silent revival of Open
    Decision #20's failed claim-support judges. Standing rule (Settled #4 /
    Open Decision #20): do not build a model-based judge on the answer path;
    that shape failed five times. Settled #16 already allows an AI to
    *propose* quote candidates. What this decision additionally authorizes:
    a quality / serveability gate on the quote extract path that may use
    model proposals and/or model-shaped structured fields to decide whether
    a candidate may proceed toward pending/approved — a **taste** judgment
    ("worth serving as a standalone quote"), not a truth/claim-support
    judgment on a served answer.

    Recorded honestly, not softened: this gate will be wrong in both
    directions (over-refuse good quotes; under-refuse weak ones). Alex was
    told that and accepts it. Every accept/refuse must be logged with enough
    detail to reconstruct why; prefer named rubric dimensions over opaque
    scores. Authenticity remains solely
    `verify_quote_candidate()` / Settled #18 (deterministic). Quality does
    **not** live inside that verifier.

    Controlled topic labels for new-pipeline quotes are the existing product
    taxonomy — canonical `scripts/taxonomy.py` `VALID_TAGS` (258 tags, 15
    categories); `docs/taxonomy.md` is the generated human reference; keep
    `backend/app/constants.py` in sync. Do **not** invent a second quote-only
    vocabulary. Passage-level tags must be chosen from that closed list,
    never inherited from `documents.topic_tags[0]`. Soft tag-boost in
    selection is deferred from v1 (display/browse only); question ↔
    `quote_text` remains the selection signal until a later measured
    enhancement. Full design:
    `docs/superpowers/specs/2026-08-19-quote-quality-and-topic-design.md`.

## Settled product decisions (2026-08-25) — quote rail contained

30. **The user-facing quote rail is OFF until its accuracy and relevance are
    repaired** (Alex's decision, 2026-08-25). This supersedes PLAN.md's former
    launch posture that beta ships with quoting on; it does not weaken any
    authenticity, attribution, presentation, eligibility, or provenance rule
    governing a future re-enable. Production `QUOTE_SELECTION_ENABLED` is
    `false` on both `rhemata` and `answer-worker`, so the worker does not select
    quote IDs and delivery suppresses IDs persisted by earlier jobs. Quote rows
    remain intact; the admin quote tooling and library excerpts are not hidden
    by this chat-rail decision. Repair is Scheduled in `docs/roadmap.md`.
    Re-enablement remains an attended gate requiring reproduced failure cases,
    acceptance evidence against the repaired behavior, and Alex's explicit
    approval.

## Session Routing

Determines which path a session's task runs on — not a judgment call. Read
this table first, identify the session type from objective properties of the
task (not vibes), then follow its assigned path. If a task doesn't cleanly
fit one row, it's two sessions, not one hybrid session — split it.

**Current operating decision, 2026-08-17:** one designated coding-agent
session is the primary working surface. Its native agents and worktrees may
support bounded repo work. The custom multi-provider coordinator and
overnight harness are retired from active development; the historical detail
below no longer authorizes dispatch, commissioning, adapter work, or
safety-fence work. This retirement is scoped to the custom multi-provider
coordinator and its unattended dispatch mechanism only. It places no
restriction on ordinary sessions on that designated surface continuing
bounded repo-only work while Alex is away from the keyboard; a normal
working session is not an overnight harness run.

**Hard rule — no exceptions.** Any session that writes to the database, by
any mechanism (a `psycopg2` script, migration apply, SQL statement, or write
RPC), runs as an attended, explicitly approved plain-script operation. Never
delegate a production database write to a subagent or automated coordinator;
execute it only in the one designated primary coding-agent session.

**One narrow, explicit carve-out from that rule (Alex, 2026-08-25):**
`source_ingest_queue` web-article writes made by `scripts/
site_ingest_crawler.py` may run unattended — no per-item human review —
provided every one of its deterministic gates passes: the existing
processor gates (license, hidden visibility, format/scope, source
resolution — unchanged) plus a new automated byline-verification gate
(`source_ingest_queue/byline_verify.py`) that hard-refuses on any mismatch
or on finding no confirming signal at all — never a guess. This is the
only carve-out; every other write in this repo — migrations, admin
actions, every other table — stays under the hard rule above, unchanged.
Live-proved once (2026-08-25, Craig Keener): the crawler correctly
byline-confirmed and queued a real post, then the existing content gate
correctly refused it downstream (`article_too_thin` — checked against the
live page, a real ~15-word video wrapper, not an extraction bug); zero
documents written. **This proves the refusal path, not the success path —
the crawler has not yet actually stored a document.** Its input is
restricted to `docs/ingestion/master_ingestion_queue_approved_sites.tsv`
(the former `Approved Sites` tab of a shared `.xlsx` workbook, converted
2026-08-26 to one plain-text file per former tab — see the Landmines entry
below), and only a row with `approved` literally `TRUE` — Alex controls
that list directly. **`--site NAME` is optional as of
2026-08-25** — omitting it loops the crawler over every `approved=TRUE`
row in one invocation, each still gated independently (own crawl, own
byline check, own `--max-candidates`/`--max-pages` caps); scope is
unchanged, this only removes the need to name a site per run. Full
mechanism: Invariant 16.

Separately, and unchanged by the carve-out above: the interactive
chat-session tool's own permission-classifier layer still blocks that kind
of session from executing the write itself, reconfirmed 2026-08-25 across
reformulated retries (see the Landmines entry on this). The crawler code
can be built and reviewed in a chat-session tool's session; the actual
`--apply` execution still has to happen somewhere that block doesn't apply
— a plain terminal, the designated primary coding-agent session, or (as
done 2026-08-25, second occurrence of the 2026-08-13 pattern) a handoff to
an alternate agent tool without that restriction, script written and
reviewed here, executed verbatim, result independently re-verified after.

| Session type | Objective trigger criteria | Path | Also load | Skip | Reason |
|---|---|---|---|---|---|
| **Database write** | Any Bash-run script, migration apply, or SQL statement performs INSERT/UPDATE/DELETE/ALTER/schema DDL against Supabase — including via `psycopg2` or the SQL Editor. | **Plain script.** Never harness. | N/A — harness not used | N/A — harness not used | Hard rule above. |
| **Read-only diagnostic / audit** | Zero `Edit`/`Write` calls, zero DB mutation — SELECT-only queries, file reads, greps, read-only script runs. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | No build-then-judge loop needed for a single read-only pass; harness review overhead buys nothing here. |
| **Repo-only multi-step build** | Task ships a working repo change across multiple files and/or ordered steps, with zero DB writes. | **The designated coding-agent session's native workflow.** One primary agent; bounded subagents only when tasks are independent and ownership is explicit. | `ARCHITECTURE.md` for architecture; `PRODUCT.md` + `DESIGN.md` for UI; `POSITIONING.md` for copy. | Unrelated governing docs and historical harness material. | Keeps execution on the supported surface without multiplying discovery. |
| **Repo-only single-script / trivial edit** | A single mechanical edit or one-shot script, no multi-step build sequence — zero DB writes anywhere in the session. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | A planning/review loop is overhead a one-shot change doesn't need. |
| **Docs/records-only** | Task's only output is a change to `CLAUDE.md` / `PLAN.md` / `POSITIONING.md` / `DESIGN.md` / `rhemata-status.md`. | **Plain — chat proposes, terminal commits**, per the Project Knowledge Read Contract's propose→commit rule. | N/A — harness not used | N/A — harness not used | Structurally enforced, not just preferred: `guard_pretooluse.py` denies `Edit`/`Write` on all five governed files for any subagent — the harness physically cannot do this work. |

**Historical harness builders and reviewers — retired 2026-08-17.** The
following records the former model and is not an active instruction. For this row — remaining repo-only multi-step
harness builds — a second, alternate agent tool is a permitted builder
alongside the chat-session tool. The coordinator run loop is done
(`ac53f76`, simulated workers). The safety fence is deferred, not
cancelled: it gets built if a real overnight run causes damage that
cannot be recovered from git, or before any harness work reaches anything
outside the repository.
That alternate tool's existing hard restriction is unchanged and is
restated here so it is not silently dropped: no theological content, no
answer-accuracy path, no production database writes, no doctrinal or
licensing judgment, ever. Outside this harness/repo-only build lane it
remains read-only (inventories, diagnostics, test/log analysis,
mechanical verification).
A mid-tier model is the default reviewer and verdict-issuer for harness
build work that alternate tool performs — same review contract already
documented for the higher tier (no `ACCEPT` without recorded acceptance
evidence; a verdict is required before any worker result is complete). A
higher-tier model remains available for review on anything Alex routes to
it, and remains the reviewer of record for all existing completed O1–O4
work; this does not retroactively change any past verdict.

**Historical stall-risk evidence:** if an agent workflow shows the same
flagged-item count across three consecutive turns with no underlying action
changing (the 2026-07-18 stall's signature), stop retrying. Under the current
rule, classify and park the finding unless it satisfies the Blocker gate.

**The upcoming closeness check (Phase 2, paraphrase wording gate) falls
under Repo-only multi-step build → the designated coding-agent session's
native workflow**, for build-and-test work
itself (new detection script, its own verification pass, no DB write). If a
later session runs that check against real corpus data and writes
flags/results back to the database, *that* session is a **Database write**
session and moves to the plain path — same project, different session,
different row, per the hard rule above.

---

## Invariants — violating these reopens a closed hole

1. **Python 3.12.** Railway builds via `nixpacks.toml` — both `backend/nixpacks.toml`
   and the repo-root worker manifest declare `nixPkgs = ["python312"]`, confirmed live
   and guarded by an automated parity check (`scripts/test_nixpacks_python_parity.py`).
   This has been true since commit `a729fba` (2026-06-12, "security: harden backend +
   frontend across 4 areas"); this invariant wrongly said 3.9 for two months after that
   change. PEP 604 union syntax (`str | None`) is fine to use now — the earlier
   `Optional[str]`-only restriction is lifted, since the deployed runtime supports it
   natively. Residual caution, still real: this dev machine's own default `python3` is
   3.9.6 (macOS system Python), not 3.12 — use `python3.12` explicitly for anything
   meant to match what's actually deployed, and don't assume local and prod share a
   Python version just because both "work."

2. **License gate SQL — preserve in every future RPC edit:**
   ```sql
   EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id
     AND (s.license_status IN ('public_domain','owned')
          OR (NOT safe_mode_on AND s.visibility = 'shown')))
   ```
   `safe_mode_on` is read ONCE per plpgsql call. There is NO `IS NULL` arm —
   migration 049 removed it and made `source_id` NOT NULL. Re-adding one is
   fail-open. Gate keys on the entity.

3. **Never delete the sentinel source** `267a09ac-76f3-43fb-901f-3015aef88e22`
   ("Unassigned — needs source", unlicensed/hidden). It is the FK DEFAULT target
   for `documents.source_id`. Deleting it breaks every document resolving to it.
   It looks like an orphaned row during cleanup. It is not. Admin UI hard-guards
   against its deletion.

4. **`is_copyrighted` is unreliable and the gate ignores it on purpose.** Derived
   from folder path; wrong in practice (Derek Prince docs read `false`). Do NOT
   "fix" the gate to read it. Reading the code alone makes this look like an
   obvious improvement. It is a bug.

5. **Propositions are per-script, not DB-enforced.** Unlike `source_id` (NOT NULL
   + sentinel default), nothing stops a new ingest script from skipping
   propositions silently. Any new write path must route through
   `shared_ingest.ingest_document()`. **Verify by grepping the real call site —
   comments and docstrings lie** (`youtube_ingest.py:15` claimed propositions
   "auto-fire"; the call was one level down in `ingest_file()`).

6. **Never fork `normalize_alias_key`.** It must match migration 050's seed
   normalization exactly (lowercase + strip + collapse whitespace) or aliases
   miss silently. One shared implementation in `scripts/source_resolver.py` is
   the contract.

7. **Citable requires a real attributable name.** `citation_mode='citable'` only
   if a real name attaches as source or author. Anonymous/pseudonymous stays
   `silent_context` permanently, even with a real servable `sources` row. "The
   Kneeling Christian" → "An Unknown Christian" (public_domain/shown) is
   deliberately `silent_context`. Do not read it as a sentinel artifact and flip
   it.

8. **Never label a paraphrase rewrite as `owned`.** A rewrite of copyrighted
   source is a derivative. Labeling it owned serves it as safe verbatim and opens
   a hole safe_mode cannot close.

9. **No semicolons inside `--` SQL comments in migrations.** The multi-statement
   runner treats them as terminators; the batch rolls back silently. Verify with
   `SELECT to_regclass('public.<table>')` on a FRESH connection.

10. **An unstamped proposition write is now structurally impossible, not
    merely required.** Added 2026-07-23 as a convention (every proposition
    write must stamp provenance — prompt version label, a fingerprint of the
    exact instruction wording, model — after a leaked worked example required
    a manual text search across every stored row plus git archaeology,
    because nothing recorded which prompt produced what). That convention
    was not enough: the now-deleted `sample_v4_propositions_2026-07-23.py`
    called `store_propositions()` directly with none of the three supplied,
    landing NULL rows — the confirmed reason every one of the 2,409
    pre-2026-07-25 live propositions has NULL provenance (Landmines).
    **Fixed 2026-07-29 (bypass-proofing build):** `store_propositions()` now
    takes `prompt_version` as a REQUIRED parameter — omitting it is an
    immediate `TypeError`, before any DB call happens, never a silent NULL
    write. `fingerprint`/`model` are no longer caller-suppliable at all;
    both are derived internally, deterministically, from `prompt_version`
    (`prompt_fingerprint(prompt_version)` / `EXTRACTION_MODEL`) — the
    fingerprint stays authoritative over the hand-maintained label when the
    two disagree (labels drift; a value computed fresh from the literal
    template text each time cannot), and there is now exactly one place in
    the codebase that decides what gets stamped, not each caller separately
    re-deriving (and potentially mismatching) it. **What remains unclosed,
    disclosed not hidden:** the `propositions` table's provenance columns
    are still NULLABLE at the schema level (unlike `positions`' `NOT NULL`
    columns, Invariant 14) — this enforcement lives at the
    `store_propositions()` function boundary, not a database constraint; a
    caller executing raw SQL directly against the table still bypasses it
    entirely. Any future proposition-writing path must call
    `store_propositions()` itself — never reimplement the insert — to
    inherit this guarantee.

11. **Scripture-reference grounding inside `extract_propositions()` must stay
    unconditional — never make it opt-in — but its strip CRITERION was found
    backwards and is now reversed.** A now-deleted one-off script
    (`sample_v4_propositions_2026-07-23.py`) proved `extract_propositions()`/
    `store_propositions()` are directly callable, bypassing
    `process_document()`'s gates entirely — an opt-out parameter here would
    reopen exactly the hole this fix exists to close, so the check stays
    wired inside `extract_propositions()` itself, no bypass flag, regardless
    of the correction below.

    **The correction (2026-07-28 dry-run,
    `docs/audits/2026-07/reference_grounding_dry_run_2026-07-28.md`):** the original
    design stripped a reference whenever it could NOT be confirmed
    grounded — which also silently strips references the source genuinely
    gives but the scanner just can't recognize (spoken forms, "chapter N"
    named once with bare verse numbers after). A dry run against 20 real
    documents, before this design was ever used on a live row, found this
    backwards in practice: 85% of what it stripped (33/39) were genuine
    references wrongly removed, running 25–67% loss per document on
    verse-by-verse expository material — exactly Derek Prince's style, the
    corpus's largest block. **No live proposition was ever affected**
    (generation stopped 2026-07-25, before this fix landed 2026-07-28).
    **Standing decision: a reference may only be removed when the source is
    CONFIRMED NOT to contain it — never on mere failure to confirm.** This
    session's own re-wiring precondition is now DONE (2026-07-29
    bypass-proofing build): `extract_propositions()`'s strip step arbitrates
    every UNGROUNDED/UNCERTAIN reference through the three-layer citation
    verifier (`scripts/citation_verifier_layers.py`, live-tested 2026-07-29
    against 42 real corpus items — 78.6% overturn rate, `docs/plan-archive.md` #45.7)
    before stripping: confirmed-absent (arbiter denies) strips as before;
    confirmed-present (arbiter overturns) is kept and logged as an overturn.
    Supersedes the 2026-07-28 "strip on mere failure to confirm" posture
    this invariant originally corrected — that posture is retired, not
    revived. **One narrow, deliberate, disclosed exception:** if the arbiter
    itself cannot run (a live call fails, or the reference genuinely can't
    be parsed even after normalization), the reference still strips,
    fail-safe — judged a lesser harm than a fabricated reference reaching
    users, for this specific, now-rare case only. This is NOT the old
    design revived: the old design stripped on ANY failure to confirm (the
    common case, since no `verse_lookup` was ever available on this call
    path) — the new exception fires only when the much stronger three-layer
    check itself cannot run at all. Provenance is now structural (Invariant
    10) and the allowed-reference-list upstream constraint plus this
    arbitrated strip both live unconditionally inside `extract_propositions()`
    itself — confirmed live, on the exact deleted-script call shape, to hold
    even for a caller that skips `process_document()` entirely.
    **Generation has now resumed and the backfill has run (2026-07-30,
    corrects this invariant's own earlier "still unresolved before
    generation resumes" framing — that precondition language predated the
    run, it is not still open).** `docs/plan-archive.md` #46's human calibration ran and
    closed 2026-07-30, before the run. The full backfill (`docs/plan-archive.md` #17/#49)
    processed 515 documents, 508 succeeded — see rhemata-status.md for the
    complete accounting. **What remains genuinely unresolved, unchanged by
    that run:** the license gate and Precept-Austin lockout are still only
    inside `process_document()`, not structural — a direct caller still
    skips them. **What the run newly surfaced, not previously known:**
    book-length documents (`source_type='book'`) structurally break the
    current single-call, `max_tokens=8192` extraction design — 2 of the 7
    backfill residuals were this class, not the known JSON-escaping defect
    the other 5 share. **All 7 since extracted 2026-08-02** (the 5 sermons via
    the now-fixed parser, the 2 books via the multi-call `process_book_document`
    path): the single-call limitation itself STANDS — the books simply no longer
    go through the single-call path. See `docs/plan-archive.md` #17.

12. **Position generation must stay structurally source-blind.**
    `scripts/positions.py` has TWO — and only two — functions that call the
    LLM to write a position: `generate_position_text()` (teacher scope) and
    `generate_corpus_position_text()` (corpus scope, added 2026-08-01 with the
    corpus serving path). Each takes only a topic, already-paraphrased
    evidence-proposition content (`propositions.content`), and — as plain
    public NAME strings — the teacher(s) that content is attributed to (a
    single `teacher_name` for the teacher function; per-statement `teacher`
    labels for the corpus function, which the divergence rule needs to name
    who holds which view). Neither has a `document_id`/`source_id` parameter,
    and neither opens a database connection, so there is no argument through
    which source/chunk text could reach either. This is enforced by the
    functions' own signatures, not by a prompt instruction telling the model
    to ignore something it was handed. A teacher NAME is not source text —
    passing it, or per-statement teacher labels, does not breach this; the
    breach would be source/chunk TEXT, which no signature here admits. Any
    future position-generation caller, or any future generator, must preserve
    this — a caller that "just needs a bit more context" and adds a chunk-text
    parameter reopens the same live-answer leak the position layer exists to
    close.

    **Naming caution — "position" now names three unrelated things; this
    invariant governs only (a).** (a) The teacher/corpus `positions` table +
    `positions.py`'s generation functions (`generate_position_text` /
    `generate_corpus_position_text`) — the source-blind mechanism described
    above. (b) `backend/app/services/position_papers.py` — the "position
    papers" feature (baptism/tongues pillars). **Corrected 2026-08-06
    (Settled decisions #8/#16/#17): no longer a house-voice full-bypass
    answer path.** `get_paper_body()` still reads a paper's own document/
    chunk text, but only to inject it as bounding `[House Position]` silent
    context around a normal, retrieved, cited answer — never to phrase a
    served answer directly, except through the narrow, disclosed,
    disclaimer-carrying fallback (`render_paper_voice_with_disclaimer()`)
    for the specific case where contradiction-exclusion (decision #16) empties
    an otherwise-real retrieval. This remains a different mechanism from (a)
    — it still reads chunk text, which (a)'s functions structurally cannot —
    but it is **no longer the routine path it once was; it is now the
    exception path**, and (a)'s source-blindness is still not violated by
    it. (c) `docs/position_papers/` — **updated 2026-08-13: all eight
    charismatic pillars are now registered/live** (baptism_holy_spirit,
    speaking_in_tongues, deliverance_and_spiritual_warfare,
    prosperity_and_faith_teaching, divine_healing,
    gifts_of_the_spirit_overview, prophecy_and_the_prophetic,
    five_fold_ministry). The three that had previously failed first-pass
    calibration were given real iteration this pass, not a quick fix — see
    ARCHITECTURE.md, "Position papers (fence + guarded retrieval)," for
    what was found and how it was fixed. five_fold_ministry's editorial
    question (restoration-after-a-gap vs. never-ceased) was resolved by
    Alex the same session (the offices never ceased, only neglected)
    before registering. No draft remains unregistered in
    `docs/position_papers/`.

13. **Position scope is locked to exactly two values (`'teacher'` |
    `'corpus'`), double-locked — a third scope is still refused twice.** A
    `positions` row's scope is enforced in two independent places that must
    agree: `write_position()` (teacher) and `write_corpus_position()` (corpus)
    reject any other scope via `_assert_permitted_scope()` before opening a
    transaction, AND `positions.kind` carries a
    `CHECK (kind IN ('teacher','corpus'))` constraint (migration 076, widened
    from 073's teacher-only lock) that rejects the insert even if that
    application gate were bypassed or forked. Widening to a THIRD scope
    requires a deliberate code change AND a migration, never a runtime flag.
    **Corpus-wide was BANNED until 2026-08-01, then UNBANNED on Alex's
    explicit decision that day** — **(2026-08-03 posture, per the build-plan settled
    decisions above: that lift STANDS — not re-imposed, constraint not narrowed,
    existing rows not deleted; corpus positions are simply not being BUILT ON,
    because the durable-stored-positions work is deferred — a product posture,
    not a re-ban.)** the #49 backfill (850/857 eligible
    documents, incl. 477 of Derek Prince's) satisfied the precondition this
    invariant originally named. Recorded so a future session reads the widened
    CHECK as a decision, not drift: the original teacher-only lock existed
    because a corpus position authored before Prince's material landed would
    have named whichever teachers happened to already have statements as "the
    corpus" and inverted the day his documents were processed. A teacher
    position names exactly one source (`source_id` NOT NULL); a corpus position
    names none (`source_id` NULL) and derives its contributing teachers from
    its evidence — enforced by migration 076's scope/source coupling CHECK, so
    the schema itself cannot drift into an averaged, unattributed position.
    Contributors are ALWAYS derived from a position version's evidence at
    build/serve time (`contributor_breakdown_from_db()`), NEVER a stored
    taxonomy of which teacher belongs to which family — that standing rule
    (PLAN.md track PL) is unchanged and non-negotiable. **Still open, NOT
    closed by the ban lift:** archived Open Decision #13 in `docs/plan-archive.md` (who owns the
    teacher-vs-corpus scope-boundary judgment call) remains unresolved; the
    threshold that actually decides teacher vs corpus for a topic question
    (`positions.DOMINANCE_THRESHOLD` = 0.60 — a single teacher supplying ≥60%
    of gathered evidence is teacher scope) is a reasoned, overrulable starting
    point, not a calibrated constant — see PLAN.md.

14. **`positions.prompt_version`/`prompt_fingerprint`/`model` are `NOT NULL`
    — keep this discipline for any future LLM-generated-content table.**
    Unlike `propositions`' nullable provenance columns (the reason a fixed
    set of 2,409 legacy propositions has NULL provenance permanently — see
    the Landmines section; every proposition written since 2026-07-29's
    bypass-proofing build, 5,814 and counting as of 2026-07-30, is
    correctly stamped `v3`/`v3.1` and not part of this gap), an unstamped
    `positions` write is impossible at the schema level, not just
    discouraged by convention. Don't relax this for a future table "just to
    unblock a migration" — nullable provenance is exactly how Invariant
    10's hole opened in the first place.

15. **The custom multi-provider coordinator and overnight harness are
    retired from active development.** Settled 2026-08-17. Existing code,
    branches, tests, and historical evidence remain intact, but no current
    task may extend, commission, or depend on them without Alex explicitly
    reversing this decision. Repo work defaults to the designated
    coding-agent session's native workflow. Production database writes
    remain attended plain-script operations in the one designated primary
    coding-agent session and are never delegated to a subagent or automated
    coordinator. This retirement is scoped to the custom multi-provider
    coordinator and its unattended dispatch mechanism only — it does not
    restrict an ordinary session on that designated surface from continuing
    bounded repo-only work while Alex is away from the keyboard; a normal
    working session is not an overnight harness run.

16. **The source-ingest queue runner is clearance- and policy-gated; migration
    088 is already applied. Widened 2026-08-18 (PLAN.md W1–W4, PR #1
    `harness/quote-containment-and-staging`, merge `923f1ed`, closing commit
    `a8a7731`) to accept a second source format, gated differently from the
    first — read the whole entry, not just the opening clause.** The
    deployed-but-inert slice accepts `pdf + single + declared` OR
    `web_page + single + declared`
    (`scripts/source_ingest_queue/processor.py::_SOURCE_FORMATS`), claims only
    `cleared_to_run=true`, and resolves an existing non-sentinel source. A PDF
    row still must pass canonical `is_source_servable()`, unchanged. A
    web-article row instead requires the resolved source to already have
    `license_status IN ('licensed','unlicensed')` AND `visibility='hidden'` —
    hidden staging exists so preparing a web article can never make it
    retrievable; the runner never creates sources/aliases and never itself
    changes visibility, license status, or safe mode for either format. It
    retains complete extracted text through `shared_ingest.ingest_document()`
    but never retains the PDF binary. Live worker execution is further
    restricted: `scripts/source_ingest_worker.py --row-id UUID` requires
    `--once` and is parameterized straight into `claim_next(...,
    only_row_id=...)` (`scripts/source_ingest_queue/jobs.py`) — the claiming
    SQL adds `AND id = %s` to the ready-row query, so a target row that isn't
    claimable returns no row rather than silently claiming a different one (no
    fallback/silent document substitution). A full-compute, zero-database-write
    preview pipeline (`scripts/source_ingest_queue/preview.py`) computes
    metadata, chunks, embeddings, propositions/provenance, usage/cost evidence,
    and proposal-only quote spans for a queued row before any write is made —
    mutation-tested to prove `shared_ingest.ingest_document`,
    `propositions.store_propositions`, and `quotes.create_and_approve_quote`
    are never called (`scripts/test_source_ingest_preview.py`). One isolated
    processor proof (PDF path) completed 2026-08-17. **Corrected 2026-08-25
    — the line that stood here since 2026-08-18 ("no web-article row has
    been run for real yet") went stale the very next day and was never
    fixed: PLAN.md's W5/W9 (2026-08-19) already ran real, attended
    web-article writes through this exact runner (one Savchuk article, then
    a 3-article batch).** Any further real item or web-article production
    write remains a separately approved operation by default; merging this
    repository code does not authorize them on its own — **except through
    the narrow, explicit exception recorded in the Session Routing "Hard
    rule" section above (2026-08-25): `scripts/site_ingest_crawler.py` may
    write through this same runner unattended, for web-article rows only,
    gated by an added deterministic byline-verification step
    (`source_ingest_queue/byline_verify.py`).** Never reapply migration 088.

17. **New Wine review is issue-level, fail-closed, and never authorizes its
    own write or file promotion.** Every page image, including advertisements
    and other non-article material, must pass OCR-completeness review; one
    failed page gets exactly one targeted repair, and a second failure
    quarantines the entire issue. Article review uses the complete verified
    issue transcript, and every substantive article must have at least one
    reviewed proposition whose exact evidence offsets round-trip and whose
    support, qualification, overstatement, and attribution verdicts all pass.
    One failed page, article, or proposition makes every article in that issue
    ineligible—partial-issue ingestion is forbidden. An approved reviewed
    ingest must revalidate the issue, article, proposition-artifact, model,
    prompt, and evidence lineage before database access; it passes the exact
    approved proposition text through `shared_ingest.ingest_document()` and
    the existing storage path byte-for-byte, with no regeneration. Review and
    dry-ingest preview make no database or embedding calls. Any real database
    ingest remains a separately named, attended, explicitly approved operation
    with hard reconciliation. Neither review nor reviewed ingest automatically
    moves, renames, archives, deletes, or promotes an issue or source file;
    source promotion is a separate explicit operation. The credential-free
    fake-provider proof in `scripts/test_magazine_review_end_to_end.py` builds
    confidence in this mechanism but does not open roadmap trigger A2 or select
    an OCR model. **Planning snapshot, 2026-08-25, corrected 2026-08-27 — still
    explicitly unstable:** the initial OCR winner is still pending among Gemini
    2.5 Flash, Google Enterprise Document OCR, and Gemini 3.6 Flash;
    page-completeness review and the one permitted targeted retry use Gemini
    3.6 Flash; segmentation uses Groq `openai/gpt-oss-120b` at **high**
    reasoning (raised low→medium→high, 2026-08-27, New Wine A2 live
    validation — low silently under-covered a real 32-page issue, medium
    still produced an implausibly-large single/few-article segmentation in
    roughly half of live attempts; full trail in `rhemata-status.md`'s
    2026-08-27 entry and commits `37e2746`..`683b973`), while issue-wide
    article review uses it at medium reasoning; proposition extraction
    remains the existing GPT-OSS 120B v3.1 path and support review uses
    GPT-OSS 120B at medium reasoning. The Groq planning price snapshot is
    **$0.15 per million input tokens and $0.60 per million output tokens**.
    The accepted design's Google snapshot points to the official Gemini API
    pricing, Gemini Batch API, and Google Document AI pricing sources:
    Enterprise Document OCR is priced per page, and eligible Gemini
    Batch/Flex processing is discounted; no Google dollar amount is made
    durable here. Recheck every model's availability and all provider prices
    at the official sources before the paid blind benchmark
    or any paid review run.

---

## Landmines (live, as of last audit — verify before trusting)

- **A blanket product-name sweep corrupts four things that look like the
  product name and are not — proven by doing it, 2026-08-31.** The
  Rhemata -> New Wine rename (`a6f1575`) is done; what survives is the rule
  for any future rename. (1) **Data-matching code:** `COLLECTION_SOURCE_HINTS`
  in `scripts/corpus_data_quality_sweep.py` and the `teachers` provenance in
  `scripts/data/common_religious_vocab.json` both contain `rhemata` because
  they name the live `sources` row (`bf6d9e28-...`, still "Rhemata"), not the
  product — sweeping them silently stops source-name matching. They move when
  that DB row moves, never before. (2) **Corpus text:** `sources/` carries
  "rhema" as a Greek lexical entry and "manna" as the biblical food; a
  public-domain Jamieson-Fausset-Brown `chunks` row contains "ta rhemata".
  Never in scope. (3) **Historical records:** this same sweep mangled
  CLAUDE.md's own Settled #25 (inverted "rebranded Rhemata -> UpperWord",
  rewrote the inventory's search term, and turned that entry's own "ta
  rhemata" warning into "ta newwine") and DESIGN.md's reference to the
  retired `rhemata-brand.md`. Those were caught and repaired the same
  session, but only because they were re-read afterwards. (4) **Credentials
  and other literals that merely look like prose** — the category the same-day
  review MISSED, and the reason this entry no longer claims the damage was
  contained. The sweep rewrote the beta gate's password (`code === "rhema"`
  -> `"newwine"`, `BetaGate.tsx`) and shipped it, so every beta tester was
  locked out of production until Alex hit it himself and it was fixed in
  `5473265`. A password, token, or fixture value does not read as a
  product-name reference when scanning a rename diff, and no test covered it.
  It now lives alone in `frontend/lib/beta-access.ts` under a test asserting
  the literal, which is the general fix: **a swept literal must be pinned by a
  test, because reading the diff demonstrably does not catch this class.**
  **Applied migrations, dated `docs/` audits, and `scripts/archive/` were
  excluded up front and are the reason the damage stayed as small as it did**
  — exclude them by default, diff every governing-doc sweep before trusting
  it, and grep the result for string comparisons, not just prose.

- **Rotating `CURRENT_SUBJECT_KEY_VERSION` is no longer an outage — that
  exposure is genuinely closed, 2026-08-31 (B7 item 2, commit `f2ee6ff`).
  Recorded as a correction, not a standing warning, because the stale form
  of this warning ("a bump takes the product down") would now send a future
  session chasing a risk that no longer exists.** What was true until B7:
  a version bump sent every consented user's next submission through an
  UNGUARDED `derive_subject_key()` in `async_chat.py`'s `/submit`, so if
  `ANALYTICS_HMAC_SECRET_V{n+1}` was not configured,
  `MissingHmacSecretError` escaped as an unhandled 500 and a rotation was a
  live outage. `search_analytics/recording.py` now absorbs it: no key means
  no write, and the answer is served regardless. **Proven, not assumed** —
  `scripts/test_analytics_answer_decoupling.py` drives the REAL
  `consent.get_or_rotate_subject_key()` with a deliberately stale row and
  the secret removed from the environment, and asserts it still raises
  (unchanged), that `recording.py` absorbs it, and that the outcome is
  `skipped_key_unavailable` rather than an exception.

  **What genuinely remains, and it is a data risk rather than an
  availability one:** bumping the version without configuring the new
  secret first silently stops recording for EVERY consented account. No
  error, no outage, no answer lost — just no analytics, indefinitely, until
  someone notices. Set `ANALYTICS_HMAC_SECRET_V{n+1}` BEFORE bumping the
  constant, never after. That silence is visible in
  `answer_jobs.analytics_outcome` (`skipped_key_unavailable`) via
  `scripts/analytics_health_report.py` — migration 095 is applied and
  deployed as of 2026-08-31, so that check works today. **Run it after any
  rotation**: a bump that quietly stopped all recording looks identical to a
  quiet week until someone reads that column.
  Also unchanged and still load-bearing: `consent.withdraw()` finds rows by
  the current key plus every entry in `retired_subject_keys`, so a rotation
  that loses the outgoing key makes its rows undeletable — never write a
  rotation path that skips preserving it.

- **An LLM told to "preserve ALL content verbatim" will quietly rewrite
  instead, and nothing compared stored text against source — RESOLVED
  2026-08-29 (commit `617341c`); recorded because the failure class outlives
  the fix.** `youtube_ingest.py` fetched captions with `--convert-subs srt`,
  which flattens YouTube's rolling-window cue format into literally
  TRIPLICATED text (a 9,327-word sermon arrived as 27,783 words), then relied
  on a Groq model to undo that while "preserving ALL theological content
  verbatim." Measured on one real 6,000-word chunk: `openai/gpt-oss-120b`
  kept 38%, `openai/gpt-oss-20b` 7.5%, and `qwen/qwen3.6-27b` was accurate but
  truncated mid-transcript after spending its whole budget on hidden
  reasoning. 49 live documents sat at roughly a third of true length and
  nothing noticed, because no check ever compared stored text to its source.
  Four durable lessons: (1) the native **`json3`** sub-format carries each
  word exactly once — the duplication was never in the source data, the
  pipeline manufactured it; never write a dedup pass for SRT triplication,
  avoid creating it. `_parse_json3()` must INCLUDE `aAppend` events, which
  carry the `\n` separators — dropping them glues words across cue boundaries.
  (2) **`--print` implies `--simulate` in yt-dlp** and silently suppresses the
  subtitle write; `--no-simulate` is required alongside it, or every video
  falls through to Whisper. (3) Every model on the current Groq roster is a
  reasoning model and none is safe for a copy-don't-rewrite task — a model
  swap alone converted a working pipeline into a silently destructive one.
  (4) A historical control is the fastest way to date a regression: the same
  code under the older `llama-3.3-70b-versatile` had preserved ~100%, which
  located the fault in the model swap, not the code. Guards now in place:
  `scripts/test_youtube_caption_extraction.py` (mutation-proven) and a
  coverage gate requiring captions to span ≥85% of the real video duration or
  fall back to Whisper rather than store short. **Deliberately left alone:**
  `scripts/clean_transcripts.py`, a separate legacy script wired into
  `youtube_pipeline.sh`, still hardcodes the dead `llama-3.3-70b-versatile`
  AND performs the same destructive rewrite — it fails loudly on the dead
  model rather than corrupting anything.
- **New-provider structured-output integration must be mechanics-tested on a
  trivial dummy request before spending on the real large document —
  2026-08-29.** Testing Claude Opus 5 as an alternate New Wine segmentation
  candidate burned real money debugging SDK/schema mechanics against the
  full 121K-char Issue 02-1973 transcript instead of a cheap dummy call
  first. Three concrete gotchas, now known: (1) `messages.create()` refuses
  a large `max_tokens` outright (client-side, unbilled) — use
  `messages.stream()` + `.get_final_message()` instead. (2) Claude's
  `output_config.format.schema` 400s on `minimum`/`maximum` on an integer
  property, which OpenAI/Groq accept — strip them before reuse; this
  pipeline's own Python validation (`articles.py`'s `segment_articles()`)
  already enforces the same bounds independently, so nothing is lost. (3)
  Any client implementing this pipeline's `StructuredOutputClient` Protocol
  must return EXACTLY `{output, usage, cost_usd}` —
  `_response_envelope()`'s `_require_exact_keys` check rejects an otherwise-
  valid, already-billed response for carrying one extra key (a test
  client's own diagnostic field, in this case). A separate, earlier attempt
  at a smaller `max_tokens` almost certainly also cost real money (hit the
  cap before emitting any output) with usage never captured, because the
  test harness's own error handling didn't capture usage on that failure
  path. Total estimated spend against a $1 approved ceiling: ~$2.5.
- **The article-review stage's own `missing_substantive_spans` complaint has
  a confirmed false-positive mode — do not trust it without checking
  `non_article_spans` first, 2026-08-29.** In the same live Opus 5 review
  test above, both "missing" spans it flagged (a page-4 Letters-to-the-
  Editor department, a page-22 conference advertisement) were independently
  confirmed present the whole time — correctly classified as
  `non_article_spans`, contiguous, zero coverage gap either side. The
  reviewer appears to compare only against `manifest.articles`, not the
  full `articles + non_article_spans` partition the schema's coverage
  design actually uses. This does not mean the reviewer's OTHER complaint
  classes (split-article disagreement, page-marker-past-true-end) are also
  false — those remain unverified — only that `missing_substantive_spans`
  specifically needs a manual cross-check against `non_article_spans`
  before being treated as a real content gap. Full detail:
  `docs/audits/2026-08/new_wine_opus_review_e2e_test_2026-08-29.md`.
- **The `claude_ai_Supabase` MCP tool is connected to an unrelated Supabase
  account, not New Wine's — 2026-08-28.** `list_projects` returns exactly one
  project, "Grocery App" (`waljyghafnwrawijmqhe`, created 2026-08-24) — not
  the New Wine production project. Any read (backup config, table list,
  advisors) via this MCP tool during a session on this repo is checking the
  wrong database entirely; it will not error, it will just silently answer
  about a different project. Use the real `psycopg2`/`SUPABASE_DB_URL`
  connection (`app.services.async_answers.db.connect()`) for real read-only
  checks against New Wine's actual database instead.
- **New Wine article-segmentation guardrails are reactive, not proven
  exhaustive — and the recurrence is dominated by run-to-run model variance at
  "high" reasoning, not one deterministic gap.** Live validation against Issue
  02-1973 found at least seven distinct ways the model could technically satisfy
  "full coverage" while producing wrong output, each discovered live and fixed
  with a targeted deterministic check as it appeared, never designed upfront:
  `scripts/magazine_review/articles.py`'s `_COVERAGE_GAP_TOLERANCE_CHARS`,
  `_OTHER_NON_ARTICLE_MAX_CHARS`, `_NAMED_NON_ARTICLE_MAX_CHARS`,
  `_NON_ARTICLE_TOTAL_FRACTION_MAX`, and `_MAX_ARTICLE_CHARS`; plus
  `foreign_article_title_in_span` (a span opening with a DIFFERENT article's own
  title and credit — two independent real occurrences, a genuine content
  misattribution rather than ad-bundling); plus a requirement that a span carry
  actual promotional content (named product, service, event, subscription,
  price, or response address) before it may be categorized `advertisement` —
  added after three consecutive spans totalling 16,788 chars of a real reader
  Q&A column were filed as three separate fake ads, with zero commercial
  language anywhere in them. Two ordering/anchoring bugs were fixed alongside:
  the article-overlap check compared each article only to the PREVIOUS one in
  the model's raw return order rather than sorted by position (false positives
  3 of 4 runs), and boundaries were being anchored on bare page markers and on
  standalone all-caps in-article subheadings.

  **Three things a future session must not assume.** (1) These checks are not
  exhaustive — a new gaming pattern needs a new targeted check built from real
  numbers in a real failure, not a guessed threshold. (2) Fail-closed guarantees
  that SOMETHING catches an unsafe case eventually, not that every layer catches
  every case: a single article spanning the whole 121,011-char issue passed the
  semantic reviewer with `verdict=True`, `status=passed`. (3) **The semantic
  reviewer is confirmed non-deterministic on byte-identical input** — four
  live calls against a pinned segmentation caught a real misattribution once and
  missed it three times, and an identical 10-article input produced
  `article_failure_reasons_invalid` twice then a clean pass on the third
  attempt. It is not a reliable backstop for any defect class. Separately, its
  `missing_substantive_spans` complaint has a confirmed false-positive mode —
  see the entry above. Issue 02-1973 still has not cleared the article gate
  end-to-end. Full trail: `rhemata-status.md`'s 2026-08-27 entry and commits
  `37e2746`..`683b973`, `d011fac`, `ae37d3b`, `3bc8780`, `d5420e3`, `4bad5b5`.
- **The master ingestion spreadsheet is four plain-text TSVs under
  `docs/ingestion/`, layered on top of `source_ingest_queue` (Invariant 16), not
  a replacement for it.** Converted from a binary `.xlsx` 2026-08-26 so git can
  diff it; deliberately tracked in git, unlike the gitignored YouTube/magazine
  trackers — git history is this data's backup and recovery mechanism. The
  files: `master_ingestion_queue_read_me.tsv`, `..._discovery.tsv` (raw,
  unvetted candidates), `..._queue.tsv` (vetted rows shaped to match
  `source_ingest_queue`), and `..._approved_sites.tsv`
  (`site_ingest_crawler.py`'s sole input). **One shared module,
  `scripts/ingestion_sheet_io.py`, is the only place that knows the TSV
  encoding** — every script reading or writing one of these must go through it,
  the same "one shared implementation" discipline as `normalize_alias_key`.

  **Alex's explicit, standing decision: this data is the single master source of
  truth for ingestion candidates; on any disagreement with the database it
  silently overwrites.** `scripts/sync_master_ingestion_queue.py` is
  dry-run-by-default (`--apply` required to write), creates missing Queue rows
  and overwrites differing fields but never deletes (an orphan database row is
  reported for a manual decision, never removed), and structurally never opens
  the Discovery file — so a Discovery row cannot reach the database through it,
  proved by mechanism 2026-08-26. It has been run with `--apply` exactly once
  and that run was a genuine no-op, so **the real-write path is still unproven
  against an actual change.**

  **The admin panel's ingest-queue submission form is a deliberately accepted
  trap, not a bug**: it writes straight to `source_ingest_queue`, is NOT part of
  the sync, and anything submitted through it will be silently overwritten by
  the next `--apply` unless someone also adds it to the Queue file by hand.
  Raised to Alex directly and left as-is on purpose.

  **Trust levels inside Discovery.** Fields named with a `claimed_` prefix are
  guesses from automated research passes, never a confirmed site visit — treat
  as unverified regardless of how confident the wording sounds. The four
  human-clearance booleans (`site_visited_by_human`, `author_identity_confirmed`,
  `licensing_posture_confirmed`, `content_type_confirmed`) plus
  `clearance_checked_at` are blank/FALSE on every pre-existing row; nothing was
  retroactively marked as checked. At least two rows are flagged known-suspect
  and unchecked: Loren Cunningham and Reinhard Bonnke, both deceased, both
  listed with clean, live-looking personal domains — a specific red-flag pattern
  in this data, not yet manually verified either way.

  **Review tooling already exists — check before rebuilding any of it.**
  `scripts/review_discovery_candidates.py` (local FastAPI, one candidate at a
  time, Yes writes an Approved Sites row and marks the row `verified`, No marks
  it `rejected`; mtime-based `StaleFileError` guard refuses a write if either
  target file changed on disk since it was read),
  `scripts/check_discovery_blog_links.py` (one-shot live fetch + link check,
  reusing the crawler's SSRF-safe fetch, cached in `auto_link_check`), and
  `tools/discovery-review-extension/` (unpacked MV3 extension, closed Shadow
  DOM, capability-gated `http://127.0.0.1:8765/api/review/*` contract, opaque
  revision token bound to the fresh TSV bytes so a changed candidate returns 409
  with no write; no database or ingestion authority whatsoever). A real run
  against all 109 unverified candidates returned only 26 `looks_like_blog`, 2
  `no_blog_detected`, and **81 `check_failed`** — mostly sites bot-blocking the
  fetch, most likely because `source_ingest_queue/fetcher.py` sends no
  `User-Agent` header at all. Not fixed: it would likely raise the crawler's own
  real success rate too, but it touches shared SSRF-hardened fetch
  infrastructure and wants a deliberate decision first. A `check_failed` is
  never treated as "no blog" — it stays visible for manual review.

- **Quote selection is contained behind `QUOTE_SELECTION_ENABLED`, and the
  current production posture is OFF** on both Railway `rhemata` and
  `answer-worker` (Alex, 2026-08-25 — the user-facing rail was insufficiently
  accurate and relevant; Settled #30, repair Scheduled in `docs/roadmap.md`).
  `quote_selection_enabled()` requires the exact string `"true"`; anything else,
  including case variants, is off. With it off the producer never calls the
  selector and emits no `quote_ids`; the reuse/dedup key (`current_policy()`'s
  `policy_version`) changes with the flag so a cached or reused answer can never
  cross flag state; and SSE delivery re-checks the flag at read time, so an
  already-completed job's persisted `quote_ids` are suppressed. Proven in
  `scripts/test_quote_selection_gate.py`. Flipping the flag is the
  seconds-reversible kill switch in both directions.

  **Why it was contained: a systemic RELEVANCE defect, not a finding that
  quoting itself is unsafe.** Matching keyed off the inherited document-level
  `quotes.topic` rather than the quoted passage — 636 approved quotes spanned
  only 115 topics ("Holiness" alone covering 49 across 12 documents), and 14
  real quotes tied exactly against one real baptism question, several on
  passages with nothing to do with it. Fixed (`82ec0f5`): relevance now scores
  each candidate's own `quote_text`; selection is a strict `(score, id)` total
  order with no DB row-order dependence; `create_and_approve_quote()` returns an
  existing matching row instead of duplicating. Its check-then-insert race is
  closed by a Postgres session-level advisory lock keyed on the exact
  `(chunk_id, quote_text, teacher_source_id)` triple (`quotes.py::_creation_lock`),
  mutation-proven with real racing threads — there is **no unique constraint of
  any kind** on `quotes` or `quote_source_revisions` behind it (an earlier claim
  that migration 088 provided one was false; 088 is the unrelated source-ingest
  runner). Selection additionally requires `status=approved AND
  selection_eligible AND quality_pipeline_version IS NOT NULL`, so legacy rows
  stay unserved. **Still queued:** re-auditing existing approved/pending quotes
  as untrusted legacy data (PLAN.md W7) and everything in W8.
- **Railway `rhemata` service builder can silently drift to Railpack without
  `rootDirectory=/backend`.** Observed 2026-08-19: GitHub-triggered deploys
  after `ad0dc0a` failed with connect-deadline / snapshot errors while the
  service manifest showed `RAILPACK` and no backend root — prior SUCCESS
  deploys had been NIXPACKS + `backend/` + `/backend/railway.toml`. Brief
  production API outage until rollback, then `serviceInstanceUpdate` restored
  NIXPACKS + `/backend` + railway.toml fields and `serviceInstanceDeployV2`
  at `ad0dc0a` succeeded. `answer-worker` (repo-root Nixpacks) was unaffected
  in kind. Before trusting a failed `rhemata` deploy as a code problem, check
  builder + rootDirectory on the deployment meta; do not flip quote or other
  env gates onto an older live image that lacks the matching code.
- **PARKED — `scripts/harness_coordinator/v1` and its unmerged CLI adapter.**
  The following is historical evidence, not authorized follow-up work.
  `scripts/harness_coordinator/v1`'s `invoke.py` had no live-provider call
  path as of 2026-08-15 — corrected 2026-08-17, not still fully true as
  originally stated. A real (not synthetic) CLI-based worker/reviewer
  adapter for an agentic coding tool now exists on unmerged branch
  `claude/harness-claude-cli-adapter`
  (commit `ca5101e`, 2026-08-16, real `Alex Whitley`-authored commit, verified
  directly): additive to `invoke.py`'s existing synthetic-only path, opt-in
  (`run_cli.py --enable-claude-workers`, off by default), hardcoded model/
  permission-flag ceilings a packet's own content cannot widen, and
  verification derived from real git diffs/file hashes rather than trusting
  the CLI's self-report. It went through one independent fresh-context review
  round (`REVISE`, with reproduced findings, fixed) — its own commit message
  states a second independent review round is required before it is
  considered ready for the attended real-CLI commissioning probe or human
  integration, and that second round has **not** happened. Do not treat this
  branch as ready or merged; it is neither. Any future reference to real
  unattended multi-provider runs as proven is still describing an unbuilt
  capability — only the adapter code itself is new. The supervised
  single-agent method (direct executor/planner-reviewer invocation from
  within a session) remains the separate, working, proven mechanism — do not
  conflate the two when reading past references to "the coordinator" or "the
  harness ran real workers." Full detail: `rhemata-status.md`'s Retired harness
  evidence, 2026-08-17.
- **A single, confirmed ingestion-chokepoint bypass exists and was
  deliberately left in place — 2026-08-15 diagnostic.** An admin-only
  single-PDF-upload endpoint on the backend inserts `documents`/`chunks`
  rows directly, entirely outside `shared_ingest.ingest_document()`
  (Invariant 5). If ever actually invoked, it would silently skip
  proposition generation (nothing else backfills them later), the license
  gate, the permanent Precept-Austin lockout, and source/author
  attribution — a document created this way lands on the sentinel
  "Unassigned — needs source" row (Invariant 3) with no propositions ever.
  A read-only, exhaustive repo-wide audit (every ingest script, every
  backend router) found this to be the ONLY real bypass — a preliminary
  "six bypass paths" figure from an earlier trace does not hold up; the
  other five candidates were misclassified (three write to unrelated
  tables with no proposition/license concept, two route through the
  compliant importer transitively, one has no processor built yet, so
  nothing to bypass today). A live signature check found zero documents
  anywhere in the corpus bear this endpoint's telltale insert shape, and
  no frontend caller was found either — it appears never to have actually
  been used. **Decision (Alex, 2026-08-15): left in place, not removed or
  routed through the shared writer.** Its remaining operability gap was
  closed by `ec42398`: every unexpected failure now logs bounded upload/title
  identity, source type, processing stage, attempted document ID, and exact
  attempted/stored chunk counts without document contents; a simulated
  second-batch failure is mutation-proven in
  `scripts/test_ingest_failure_reconciliation.py`. Full detail:
  `docs/audits/2026-08/stabilization_track_1_2026-08-15.md`.
- **Single-author answer attribution is now a producer contract, not a prompt
  preference (`ec42398`, 2026-08-15).** When citable evidence has exactly one
  named author, an answer that omits that full name is regenerated once with
  an explicit requirement. If the grounded retry still omits it, the producer
  adds a deterministic `Source voice` label before the existing reference
  verifier runs. Multi-author and anonymous evidence are unchanged.
  `POLICY_VERSION = "policy_v3"` prevents reuse of pre-contract anonymous
  answers; `scripts/test_single_author_attribution_contract.py` is the
  mutation-proven regression.
- **NEVER write a comma-joined `documents.author` ("Paul Kidd, Shabaka
  Williams") — it silently breaks attribution grounding, 2026-08-31.**
  `reference_verifier.build_retrieval_grounding()` builds `author_keys` via
  `normalize_alias_key(author)` on the WHOLE string and matches it exactly
  (`normalize_alias_key(name) in grounding.author_keys`); there is no comma
  splitting anywhere on that path. So a joined author permits only that
  literal joined string as a name: a *correct* "Paul Kidd" attribution
  normalizes to `paul kidd`, misses, and drives regenerate-once-then-refuse.
  `producer.py`'s `permitted_names` inherits the same flaw, and the per-author
  3-chunk cap treats the joined string as a separate author. `documents.author`
  is a single text column with no multi-author support — a genuinely
  two-speaker document must go `citation_mode='silent_context'`, not carry
  both names. Three CLF documents were found in this state and silenced
  2026-08-31. The same sweep found title-prefixed duplicates (`Pastor Paul
  Kidd` vs `Paul Kidd`) each drawing their own share of the 3-chunk cap, and a
  parser artifact author of `Sunday` (taken from "… | Sunday Message") sitting
  in the permitted-name set — **check `documents.author` after any
  title-derived ingest; the speaker parser is not reliable.**
- **A permission-classifier layer built into the interactive chat-session
  tool became the default permission model 2026-08-14 and blocks direct
  production DB writes from a session on that tool — no settings-based
  self-grant path was found.** Discovered 2026-08-13: the classifier
  (separate from normal permission prompts) denies any Bash action it
  judges "irreversible, destructive, or out-of-bounds," including a
  plain single-row DELETE via a reviewed, dry-run-proven script.
  Confirmed via the tool vendor's own changelog/release posts, not
  guesswork. Attempting to have the chat-session tool grant itself the
  permission (directly, or via editing `settings.json`/`autoMode` config
  through the update-config skill) was ALSO blocked by the same
  classifier — this appears to be a deliberate anti-self-escalation
  boundary, not a gap. A subagent asked to research the exact
  settings.json syntax returned a security-flagged answer that was
  actually a fabricated bypass attempt (prose crafted to talk the
  classifier into standing down) — discard any future subagent output
  making the same kind of claim without independently verifying it
  against the tool vendor's real docs first. **Working pattern used
  2026-08-13, not yet a settled practice:** Alex routed the session's
  two blocked DB writes (a background_topics DELETE, a two-document
  ingest) through a narrowly scoped prompt to an alternate agent tool
  without this classifier, as an explicit, one-time exception to the
  standing "harness never executes production DB writes" rule — the
  chat-session tool wrote and reviewed both scripts first, the alternate
  tool only executed them verbatim, and the result was independently
  verified against the live DB afterward via the read-only role. If
  this keeps recurring, it needs a deliberate decision from Alex on the
  general pattern, not a fresh ad hoc call each session. **It recurred,
  2026-08-25** (a source visibility flip plus a
  `site_ingest_crawler.py --apply` run, both blocked consistently across
  multiple genuinely-reformulated retries, not just one attempt) — same
  pattern, same shape, Alex's explicit call again in the moment. Still
  not promoted to a standing practice with its own procedure; still one
  explicit call at a time.

- **Auto Mode misfire on harmless prose mentioning "SQL"/"migration" —
  2026-08-14, upgraded same day.** A separate behavior of the same Auto
  Mode classifier from the entry above — that one blocks real DB writes;
  this one is a false-positive misfire with no real write involved. First
  observed earlier that session as pure reporting noise (misfired on
  report prose, zero effect). Later the same session, a real
  counterexample: the misfire can genuinely stall work, not just decorate
  a log. During a real-worker harness probe, a live `executor` subagent
  hit this classifier while running Python `time.sleep` verification
  commands — semicolons in the test one-liners, combined with the
  executor's own loaded SQL-comment/semicolon instructions (the Migration
  051 gotcha), triggered a defensive loop explaining a phantom
  SQL-migration flag instead of running the task. Nothing SQL- or
  migration-related was actually present. Worked around per the
  stall-risk rule: did not retry the identical prompt, removed the
  semicolons, reran once — cleared. **A future session must not assume
  this misfire is always harmless** — it can consume a full turn and
  block real work; reformulate, don't just retry.

- **`quote_source_revisions.passage_text` must store the FULL chunk text, never
  just the candidate span** — a span-only snapshot silently defeats the database
  trigger's own substring check, proven directly in a rollback-only transaction
  (identical fabricated `quote_text` passed under the old convention, correctly
  raised under the fixed one). Migration 082 describes this column as "an
  immutable snapshot of exactly one chunk's text." The 239 quotes approved
  before the 2026-08-09 fix were deliberately NOT regenerated: their correctness
  rests on `verify_quote_candidate()`'s independent live check at approval time,
  not on the trigger's snapshot, and there is no live chunk-edit path today for
  the vestigial snapshot to guard against. Regenerating them is optional hygiene.
- **Precept Austin's 2,176 documents are `source_kind="word_study"`, never
  `"commentary"` — `is_commentary_chunk()` must keep matching
  `_COMMENTARY_EQUIVALENT_KINDS = {"commentary", "word_study"}`,** or the whole
  set leaks back into answers as citable. Confirmed live before the 2026-08-07
  fix: one ordinary grace question retrieved 33 of 67 chunks from Precept
  Austin, several `citation_mode='citable'` — 1,779 of the 2,176 carry
  `citable`, a pre-2026-05-24 ingestion-script artifact never corrected
  retroactively, so the exclusion is the only thing standing between them and an
  answer. `_NEIGHBOR_SKIP_KINDS` carries `"word_study"` for the same
  defence-in-depth reason. Lexicon (`source_kind="lexicon"`) is deliberately NOT
  hard-excluded — it keeps its soft down-weight and its own word-study retrieval
  path. This is a retrieval-path default, not a permanent architectural ban
  (Settled #26); PA's separate, permanent exclusion from the quote pipeline and
  from paraphrase generation is unchanged by either.
- **`GET /study/teacher/{source_id}` (`get_teacher_card()`) is a SECOND
  served-generation surface — never write that `producer.py` is the only one.**
  chat.py is genuinely deleted (2026-08-07 mirror-unification), so `producer.py`
  is the only CHAT-STYLE answer path; but `get_teacher_card()` has always
  existed alongside it, synchronous rather than async-queued, with its own
  retrieval and its own Anthropic call. This file repeated "the only answer
  path" in several places and every one of them was wrong.

  It historically applied the license/visibility gate but skipped commentary
  exclusion, citation grounding, the position-paper fence, and quote
  verification. **Fixed 2026-08-15, live in production:** citation grounding
  runs via `reference_verifier.ungrounded_prose_teachers`
  (regenerate-once-then-refuse, reusing `answer_toolbox._ATTRIBUTION_REFUSAL`
  verbatim on a second failure); commentary/word_study exclusion runs by
  filtering `document_ids` BEFORE the `match_teacher_chunks` RPC, since that RPC
  returns no `source_kind`/`source_type` to filter on afterward. Corpus teacher
  names are redacted from the model's COPY of the bio before generation (the
  response payload's own `bio` field stays original) — an earlier attempt that
  instead pre-grounded the bio-mentioned name into the guard's `author_keys`
  opened a real hole (a fabricated claim under that name was no longer caught)
  and was fully removed, not patched.

  **Deliberately NOT applied: the position-paper fence.**
  `exclude_contradicting_teachers` removes 100% of a contradicting author's
  chunks, and this surface's retrieval is always exactly one teacher — so
  applying it would substitute house-position prose for a genuinely dissenting
  teacher's own card via the empty-answer fallback: misrepresentation-by-
  substitution, against ranked failure mode #2 and Settled #9, a worse failure
  than the one being guarded against. **N/A, not a gap:** quote verification —
  this endpoint never selected or served quotes and still doesn't. **Still open,
  a copy question not a code gap:** the refusal string renders under a named
  teacher's card heading.
- **When a behavior gap is "works here, broken there," check transitive
  dependency versions BEFORE assuming a code difference.** `backend/requirements.txt`
  now pins `pydantic==2.13.4` and `starlette==0.52.1`, but the pin is NOT what
  guards the admin-auth bug that taught this lesson — the original 422-vs-401
  shape does not reproduce on the pinned stack at all (both the buggy and fixed
  `_RequireRole.__call__` shapes return 401 there). The real ongoing guard is
  `scripts/test_admin_auth_regression.py`, asserting `_RequireRole.__call__`
  takes no direct `request` parameter — the actual distinguishing shape,
  independent of which versions happen to be pinned. Full reasoning:
  `docs/audits/2026-08/deps_pin_pydantic_starlette_2026-08-14.md`.
- **Stale chat-side figures/premises — verify against the repo/live DB before
  recording.** Twice on 2026-08-03 a confident chat-side assertion was falsified by
  the repo: the "781 / 91%-Prince+Bevere" backfill figure (already retired) and the
  corpus-ban "still in force" premise (lifted 2026-08-01). When a prompt or chat
  asserts a count, a decision-state, or a plan premise, the repo/live DB is
  authoritative on what currently EXISTS — check before writing it down. Related:
  the scale-deferral trap — the current ~40-concurrent ceiling was never decided,
  it emerged from repeated "defer scale until users" choices; any proposal to defer
  scale work "until there are users" repeats exactly that reasoning (Project 1's
  100-concurrent dial exists to end it).

- **The async answer path is the only chat-style answer path, it IS serving real
  traffic, and `config.py`'s `serving_enabled: bool = False` is only the
  dataclass FALLBACK — read the DB row, never the default, before concluding
  whether serving is paused.** `backend/app/services/async_answers/` +
  `scripts/answer_worker.py` + `backend/app/routers/async_chat.py` run a durable
  Postgres-backed answer queue (migrations 078/079: `answer_jobs`/
  `async_answer_config`/`provider_rate_usage` + `corpus_version()`).
  `async_chat` mounts unconditionally in `main.py` — the old
  `ASYNC_ANSWER_ENABLED` env gate is gone — and the frontend's
  fallback-on-failure behavior was removed entirely (Alex's explicit call): a
  failure now surfaces as a real, visible error via `callbacks.onError`, never a
  silent handoff. With chat.py deleted there is nothing left to roll back to, so
  `async_answer_config.serving_enabled` is an honest emergency pause — off means
  the product is offline for chat answers — not a rollback dial.

  **Load-bearing details.** Metering happens BEFORE enqueue and is keyed on the
  CALLER, so single-flight collapsing two identical questions into one
  generation still meters both independently. Conversation persistence happens
  per-READER at `/async-chat/result`, not in the worker (one shared generation →
  one history per reader), and is idempotent across a reconnect re-GET via
  deterministic uuid5 message ids + `ON CONFLICT DO NOTHING`;
  `conversations.user_id` FKs to `auth.users`, so a bad id fails closed
  (`save_exchange` swallows it, delivery unaffected). Both Railway services run
  `SUPABASE_DB_URL` on the transaction pooler (`:6543`); local
  `backend/app/.env` stays `:5432` session mode for dev only.

  **Still open:** a controlled real-traffic concurrency window proving the
  100-dial / >~12-per-worker ceiling is actually lifted. **Known and
  deliberately unfixed:** the live `match_position_paper` over-matches ("What is
  deliverance?" → baptism house voice); `producer.py`'s explicit precedence
  means a paper match always wins over stored-position injection, so this is
  contained rather than a new failure mode. `corpus_version()` does not reflect
  an in-place admin re-chunk edit (reuse defaults OFF, so moot until reuse is
  enabled).

- **The repo-root `nixpacks.toml` is the async worker service's build manifest —
  load-bearing, NOT a stray duplicate of `backend/nixpacks.toml`.** Added
  2026-08-04 (`2ba9f12`, pushed). The worker's Railway service uses Root Directory
  `/` (its entrypoint `scripts/answer_worker.py` sits at repo root but imports
  `backend/`), where no Python manifest exists for Nixpacks to auto-detect — so
  this file FORCES the Python provider, pins `python312` (matching backend),
  creates the venv at `/opt/venv`, installs the same `backend/requirements.txt`,
  and sets the worker start command. It is read ONLY by a service rooted at `/`
  (the worker); the backend web service is rooted at `backend/` and reads
  `backend/nixpacks.toml`, so the backend build is byte-identical/unaffected. Do
  NOT delete it in a root-cleanup as a "duplicate" (the repo-root-reserved rule's
  "plus tooling config" clause covers it). **Its build is now PROVEN** — the worker
  service was created in Railway 2026-08-04, built GREEN via this manifest, and runs
  as a container that completed a real verified generation (see the Project 1 async
  landmine's blocker (d)). Pooler port residual closed 2026-08-07; remaining residual
  is a real concurrency window at the 100-dial.

- **Never run a proposition-extraction pass against "all documents with zero
  propositions" — target a NAMED document set by ID.** That bare query returns
  the 2,176 permanently-excluded Precept Austin word-studies (locked out by name,
  `PRECEPT_AUSTIN_SOURCE_ID`) plus public-domain/owned material the license gate
  skips. The genuine backfill set is only what the ACTUAL gate admits (license IN
  `licensed`/`unlicensed`, not Precept Austin, ≥50 words) — re-derived live
  2026-08-02 as exactly 7 documents, now extracted (0 remaining; build `05aa519`;
  `docs/audits/2026-08/backfill_reverification_2026-08-02.md`, commit `122ad48`). This is
  the concrete danger the long-stale "781-docs" figure created: a future run must
  enumerate its targets, never sweep the zero-prop set.
- **The corpus has NO record of extraction attempts** — no completion timestamp
  (`documents.ingest_completed_at` is NULL corpus-wide), no status column, no log
  table. "Never attempted" and "attempted and failed" are indistinguishable from
  the database — which is exactly why the stale backfill-target figure survived
  undetected. NOT being fixed (recorded, not built): treat any zero-proposition
  document's history as unknown, never as "awaiting a first attempt."
- **A long model stall can outlast the DB connection and drop it mid-extraction.**
  Observed 2026-08-02: one sermon's reference-grounding stalled ~26 min, the
  Supabase pooler dropped the idle connection, and it succeeded instantly on a
  fresh-connection retry. Any future large extraction run needs reconnect
  resilience (reopen on `psycopg2` `OperationalError`/`InterfaceError` and
  continue), as `scripts/run_full_backfill.py` already does — never run one on a
  single bare connection.
- **A fixed set of 2,409 legacy propositions (created no later than 2026-07-23)
  have NULL provenance permanently** — nothing rewrites old rows. Treat any
  claim about which prompt version produced a row dated before 2026-07-29 as
  unverified unless re-checked by the method in `docs/plan-archive.md` #45.5.
  Every proposition written since 2026-07-29's bypass-proofing build carries
  real, queried-not-inferred `prompt_version`/`prompt_fingerprint`/`model`
  (Invariant 10) — this caveat does not extend to those.
- **Do not cite the 2026-07-28 "72 fabricated references / 64 propositions"
  baseline anywhere — it is superseded.** The scanner behind it
  (`reference_grounding.find_reference_spans()`) only recognizes compact
  "Book N:M" citations and is blind to spoken forms ("Hebrews chapter ten,
  verse twenty-five") and to the dominant expository pattern where a book is
  named once and later citations are verse-only. A manual check found 5 of 5
  sampled "fabrications" were genuine references the scanner simply could not
  parse. The local, gitignored `reference_fabrication_review/corpus_findings.jsonl`
  still holds the stale list — treat every entry as a review candidate, never a
  confirmed problem. A trustworthy corpus-wide number requires a re-run using
  the fixed recognition in `scripts/citation_verifier_layers.py`'s Layer 1; not
  scheduled.

  **Genuine citation fabrication appears RARE — three cases, all now excluded
  from evidence gathering.** Conlon/Matthew 7:21-23
  (`18783354-931f-4244-bfe3-f47ce185b3ba`) and Ravenhill/Philippians 4:8-9
  (`0892b75d-1c9f-4a65-a47e-768c1c5c1803`) are both a REAL citation paired with
  the wrong claim — which is exactly why no closeness or citation-existence
  check ever caught them, and why they sat live and `eligible=true` for months
  after being documented. Savchuk's "Devil's Voice"
  (`23d846db-66de-4cc6-8308-138877fd3772`) is an invented scriptural-AUTHORITY
  claim with no chapter:verse to check — undetectable by any reference-grounding
  check by construction. All three are now `eligible=false`. None was rewritten;
  per Settled #27 the two ID-confirmed ones never will be. Savchuk's stored text
  remains a separate open question, being the one case never ID-confirmed
  against an original finding.

  **The side effect worth knowing before rerunning this pattern elsewhere:**
  removing the single Ravenhill proposition recalculated the topic's evidence
  dominance past `DOMINANCE_THRESHOLD`, turning `holiness and personal purity`
  from a 4-teacher corpus position into a Derek Prince-only teacher position —
  Ravenhill, Murray, and Poonen stopped appearing as contributors at all.
  Intended behavior of the already-built scope-redetermination logic, but a far
  bigger change than "minus one contributor."
- **`backend/app/constants.py::BOOK_MAP`/`ABBREV_TO_NAME` is the single
  canonical book-name map — do not hand-type a fourth copy.**
  `frontend/app/study/page.tsx` and `frontend/app/library/page.tsx` import the
  generated `frontend/lib/generated/book-maps.ts` (produced by
  `scripts/generate_book_maps_ts.py`, which has a `--check` drift gate);
  `study.py::parse_ref` and `reference_verifier.py` both call the shared
  `app.constants.resolve_book_abbrev()` rather than each re-deriving the
  ordinal-strip-then-normalize-then-lookup sequence.
  `scripts/test_book_maps_consolidation.py` (34 checks, mutation-proven) covers
  cross-language byte-identity, the drift gate, and that no consumer still
  hand-types a local copy. **One deliberate non-union, flagged so it is not read
  as leftover drift:** `frontend/lib/study-reference.ts` imports the generated
  module for code/full-name identity but keeps its own narrower `BOOK_ABBREVS`
  overlay hand-maintained — its detector is intentionally more conservative than
  the search-box parsers (no bare "Jos"/"Ezr"/"Act"-style compact forms) and its
  ordinal-literal forms ("1st Samuel") are load-bearing there in a way they are
  not on the backend, which strips ordinals via `resolve_book_abbrev()` first.
- Some sources have no alias rows; re-ingesting their content sentinels
  silently. `ALIAS_MISS` is the grep-able breadcrumb.
- **No cheap check exists for the demonstrated fabrication class: real,
  accurate content correctly sourced from one named teacher, attached to a
  different named teacher's document.** Tested 2026-07-24: a similarity-based
  check (does a proposition's meaning match something in its own document)
  was built, run corpus-wide, and rejected — confirmed-accurate propositions
  routinely scored as extreme as or more extreme than the one known real
  fabrication, so no cutoff separates them. A names/numbers/citations-present
  check remains worth building but is blind to this exact failure by
  construction — the known fabrication contains no checkable specifics at
  all. Don't treat either check, if one gets built, as covering this failure
  class without re-confirming against it directly.
- **Delete account is still a stub, not real deletion — but the database-level
  blocker that would have prevented it is gone.** `POST /account/delete-request`
  only inserts a row into `deletion_requests` for manual admin follow-up
  (Admin panel → Contributors → "Account Deletion Requests"). No cascading
  deletion of `conversations`, `saved_words`, `pastors_cards`, `user_roles`,
  or the Supabase auth user exists anywhere in the codebase. A submitted
  request means nothing has been removed yet. **What changed 2026-08-19**
  (migration 090, `docs/audits/2026-08/b4_account_deletion_scope_2026-08-19.md`):
  `pastors_cards.user_id`, `quotes.{created_by,approved_by,revoked_by}`,
  `quote_source_revisions.captured_by`, and
  `document_quote_clearance.cleared_by` used to `REFERENCES auth.users(id)`
  with no `ON DELETE` action (`NO ACTION`) — deleting either of the 2 real
  admin accounts referenced across those tables would have raised a live
  FK-violation error, not just "the feature isn't built." Each actor column
  now has a companion `NOT NULL *_email` snapshot captured at write time
  (`app.auth.resolve_user_email()`), and the FK itself is `ON DELETE SET
  NULL`; `quotes.approved_by`'s CHECK + `enforce_quote_approval_gates()`
  trigger were narrowed to require a real `approved_by` only at the moment a
  row transitions into `'approved'`, not forever after. This closes the
  schema-level blocker only — a real deletion implementation (the Supabase
  Admin API call, ordering, audit-trail snapshot before the
  `deletion_requests` row itself cascades away) is still unbuilt.
- **YouTube ingestion is still gated on Alex — his decision 2026-07-25,
  narrowly and deliberately reversed 2026-08-29 for ONE channel only.** Do not
  run `run_queue_triage.py` / `run_queue_ingest.py` or otherwise pull new
  YouTube material without checking with Alex first. Vlad Savchuk and Zac
  Poonen — 61% of the current propositions layer between them — both entered
  via this route; a stale-looking ingest queue is a decision, not an
  oversight. See `docs/plan-archive.md` #44 for the reason (duplicate
  clip/full-sermon content found the same day). **The exception, already
  executed:** Alex explicitly reversed this for his own church's material
  (Christian Life Fellowship, Raleigh) on 2026-08-29 — two playlists,
  56 sermons total, every one verified verbatim against source: 49 from
  "Sermons" (ingested, then re-ingested after the caption defect below) and
  7 from "Sermon Archive". That reversal covers CLF Church alone; it does not
  reopen the queue for any other channel. **The 15 further CLF recordings left
  at `ingest=FALSE` are held PERMANENTLY — Alex's ruling 2026-08-30. Do not
  ingest them, and do not reopen this as a runtime/length question: length does
  not discriminate them** (7 of 14 carry fewer words than the largest CLF
  document already ingested). They are whole-service uploads carrying
  **named-congregant pastoral material** — prayer over a named member covering
  her wayward children and health, a baby dedication naming the infant in full,
  a woman walked forward and described live — which under a named minister as
  `sermon_transcript` becomes retrievable teaching material. **No trimming step
  may be built to salvage them**: the sustained-speech block contains the
  offering, dedications, and altar calls, so trimming does not isolate the
  message, and a model deciding where a message ends is the mechanism that
  discarded 60–75% of every sermon before `617341c`. Evidence:
  `docs/audits/2026-08/clf_held_recordings_review_2026-08-30.md`. **Both stages are `--sheet`-scoped
  (`youtube_triage.py --sheet NAME --add URL`, then `youtube_ingest.py
  --sheet NAME`) — that is what keeps a CLF run off the other tabs.** The
  `run_queue_*.py` wrappers are the all-tabs form: a bare `run_queue_ingest.py`
  would ingest every `ingest=TRUE`+`triaged` row in the workbook, which as of
  2026-08-29 is 731 videos across Sermonindex, Philip Anthony Mitchell, and
  Gabriel Heights — all outside the reversal, and all on non-`owned` sources,
  so they would also fire proposition extraction. Never run the bare form to
  ingest one channel. Related trap: `documents.url` carries **no unique
  constraint**, so nothing in the schema stops the same video becoming two
  documents — any new ingest path must dedup for itself.

  **Four traps when verifying a YouTube ingest — the first two burned two
  sessions as false alarms.** (1) Chunks OVERLAP (`chunk_target=550,
  overlap=80`), so concatenating stored chunks inflates the text by ~17% and
  can never be compared against source length; check each chunk is a verbatim
  substring instead. (2) Chunk 0 carries the metadata header, so compare
  against the COMPOSED file in `sources/youtube/ingested/`, not the raw
  captions. (3) **Never split a filename on `_` to recover a video id** — ids
  contain underscores (`Al_a7taOEo0`); match the `{video_id}_` prefix. (4) A
  successful ingest MOVES its transcript to `sources/youtube/ingested/` and
  only a FAILED one deletes (`5c94b3c`), so presence in that directory means
  "this is in the corpus" — `sources/web/` is a different lane (web scrapes)
  and never holds YouTube material.
- **No mechanism exists anywhere in this schema to link two documents as one
  work.** The standing "link, don't merge" policy for split-work groups and
  duplicate clips (`docs/plan-archive.md` #44) has no table or column backing it yet —
  confirmed by a direct schema check 2026-07-25. Don't assume a linked-work
  concept is queryable; it has to be designed and built first.
- **Book-length extraction now has a real, committed path — but it only
  reliably covers 8 of the corpus's 53 book documents.** `split_book_into_chapters()`/
  `_extract_and_store_book_chapters()`/`is_front_back_matter()` (commits
  `d7c46f5`/`b4ab601`, plus the byline/apparatus/digit-ratio correction
  pass `8e251c8` below) chapter-scope extraction for books whose real
  chapters repeat their own title — proven live on 7 public-domain books
  (the original 6, plus John Wesley's "The Journal of John Wesley" —
  1,249 propositions, real write, 2026-08-01), now real propositions. A
  second detector for the other 45 (roman-numeral or bare "Chapter N"
  headings) exists in the working tree but is **deliberately uncommitted
  and has zero production callers** — it found a confident-wrong-answer
  failure mode twice (fixed once, a second mechanism found no clean fix)
  and is not safe to wire in without per-book verification. Do not assume
  `detect_book_chapters()` is live just because it exists in
  `propositions.py` — check for actual callers. See `docs/plan-archive.md` #50
  and `docs/roadmap.md` Decision 21. **This same structural gap is why quote extraction from all
  53 book-type documents was tabled indefinitely 2026-08-08** (read-only
  diagnostic `docs/audits/2026-08/book_structure_diagnostic.md`, run that session:
  no body/apparatus or chapter-boundary structure is recorded anywhere in
  the schema for books, `quote_ineligible_reason` covers only 66 of 25,064
  book chunks across 10 of 53 documents, and the detector's two regressions
  above are exactly why it isn't safe to lean on for boundary-finding
  either — see archived PLAN Phase 4 in `docs/plan-archive.md`).
- **The third-party-attribution byline detector built to fix the Wesley
  misattribution bug is over-broad and unproven beyond one book — still
  true after committing.** `_has_third_party_byline()` (now committed,
  `8e251c8`, 2026-08-01 — no longer sitting uncommitted as this entry
  originally said) fires on any short line-start "By [phrase]" that
  shares no words with the document's known author — NOT specifically a
  named-person credit. Confirmed it would also fire on "By faith alone"
  or "By the grace of God." No false positive occurred on the one book
  tested (Wesley's "Journal," now proven twice: the original storage-
  disabled dry run, and the real storage-enabled write, 1,249
  propositions, 2026-08-01 — 3 of its front-matter exclusions fire via
  this exact detector, independently re-confirmed against the live DB via
  `proposition_chunks`), but a genuine content span opening with a short
  "By..." epigraph or hymn line would be wrongly excluded by this exact
  mechanism. Do not extend this to more books without hardening it first
  (e.g. requiring the credited phrase to look like a capitalized personal
  name).

**Corpus counts are never documented here.** Query live — any static number rots
within days and has already caused one round of false blockers.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (React 19), Tailwind 4 → Vercel |
| Backend | Python 3.12 / FastAPI → Railway |
| Database | Supabase (PostgreSQL + pgvector) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, set explicitly) |
| Answer generation | Anthropic `claude-sonnet-4-5` via `anthropic` SDK |
| Query expansion / metadata / tagging / transcript cleaning | Groq — **query expansion, metadata, and proposition extraction use `openai/gpt-oss-120b`**. Query expansion moved on 2026-08-25 after a paid B6 run confirmed the former `llama-3.3-70b-versatile` returned 404 on the current key; paid B6 runs now preflight expansion and fail before retrieval/generation on silent fallback. |
| Reranking | Cohere rerank-v3.5 — top 30 RRF → top 8 |
| Vision / OCR | Gemini 2.5 Flash |

---

## How to Work on This Project

- Alex works fast — short messages, direct feedback.
- Surface risks before building, not after.
- The designated coding-agent session is the primary working surface. Use
  native subagents only for bounded, independent work; do not revive the
  custom coordinator by default.
- Read output directly — never ask Alex to copy-paste terminal output.
- Check actual files before assuming structure.
- Never log planned work as done. Never claim build state you can't see.
- Follow `AGENTS.md`'s Beta Critical Path: discovery does not authorize an
  investigation, every finding is classified, and the active session stops
  when its original acceptance criteria pass.
- **When an explicit instruction conflicts with what you directly know to be
  true from evidence already in hand, stop and report the conflict — do not
  silently decide which is right and act on your own resolution, even if
  your resolution later turns out to be factually correct.** Being right on
  the facts does not make unilateral resolution the correct move; the
  authority to resolve the conflict is Alex's, not the executor's. This
  matters most on unattended/overnight runs, where no one is present to
  catch a wrong resolution either way. (2026-08-15 incident: a session-close
  instruction to record two checks as unverified conflicted with directly-
  observed evidence in the same session that they'd both genuinely
  succeeded. The facts were later confirmed correct — but the instruction
  should have been flagged and held for Alex to resolve, not overwritten
  unilaterally in the permanent record. See rhemata-status.md's 2026-08-15
  entry.)
- **Any LLM run with meaningful per-item cost across the corpus** — surface
  a cost estimate to Alex BEFORE running, design it to run once rather than
  iterate live against the corpus, and treat $50 as a hard ceiling unless
  Alex explicitly approves exceeding it.

---

## Project Knowledge Read Contract

State lives in repo files. No Notion mirroring, no sync step (retired 2026-07-09).

| File | Owns |
|---|---|
| `CLAUDE.md` | Product invariants, stack, and landmines. Load implicated sections; read in full for governing changes. |
| `ARCHITECTURE.md` | Tree, schema, scripts, env vars, commands. Load on demand. |
| `HARNESS.md` | Historical custom-harness design. Load only if Alex explicitly reopens that work. |
| `POSITIONING.md` | Messaging, voice, product posture. Source of truth. |
| `PRODUCT.md` | Who it's for, brand register, design principles, anti-references. Read before UI work. |
| `DESIGN.md` | Styling-token authority. No hardcoded hex. |
| `PLAN.md` | Current private-beta Blockers only. Always read before non-trivial work. |
| `docs/roadmap.md` | Scheduled, Triggered, and Parked work. Load only for planning, classification, or trigger checks. |
| `docs/plan-archive.md` | Completed, superseded, and historical plan reasoning. Load only when history is needed. |
| `rhemata-status.md` | Live state only. Overwritten each session. Never durable truth. |

**Writer rules:** terminal authors and writes `CLAUDE.md`, `ARCHITECTURE.md`,
`HARNESS.md`, `PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — from
confirmed-working builds only. `PLAN.md` and `docs/roadmap.md` content is
chat-originated: chat decides priority and classification, terminal writes it
verbatim. Terminal is the pen, not the author. Chat never edits any file
directly.

**Eviction rule for this file:** every line must change what you'd do on a normal
task. If a line describes the codebase accurately but wouldn't stop a mistake,
it belongs in ARCHITECTURE.md. If a decision is superseded, **delete it** — do
not stack a correction on top. Git is the provenance record. This file reached
12,000 words because nothing was ever removed, only appended to.

**Session close contract** lives in `.claude/skills/session-close/SKILL.md`
(load on "update the files to close the session" / "close out the session") —
not always-loaded here; procedure unchanged, only the load path.

**Repo root is reserved.** Only these markdown files may live at root:
`CLAUDE.md`, `ARCHITECTURE.md`, `HARNESS.md`, `PLAN.md`, `POSITIONING.md`,
`PRODUCT.md`, `DESIGN.md`, `rhemata-status.md`, `AGENTS.md` — plus tooling config. Every other markdown
file goes in a folder: audits and one-off reports to `docs/audits/YYYY-MM/`
(month-bucketed as of the 2026-08-19 reorg — new audits should follow the
same convention going forward), marketing source markdown to `docs/marketing/`.
One-off scripts that have finished their job go to `scripts/archive/YYYY-MM/`,
not `scripts/` itself — reserve the flat `scripts/` root for live/reusable
modules, documented commands, production entrypoints, and the `test_*.py`
regression suite. Already-gitignored local-only scratch (review queues, run
logs, working sets) consolidates under `local/YYYY-MM/` rather than scattering
at repo root. A new file at root is a mistake, not a decision. `CLAUDE.md`
must stay at root — this project's coding-agent tooling looks for it there
by convention.
