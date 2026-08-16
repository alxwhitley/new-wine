# Rhemata — Claude Code Context

AI-assisted Bible study tool for Spirit-filled/charismatic believers. RAG chat
with inline citations over a vetted, named corpus. Product model: Magisterium AI.
UX model: Perplexity.

**Design filter for any new feature:** does it make Rhemata sound more like a
spiritual authority in its own right, or more like a directory pointing to real
ones? The former is always wrong. Time-in-app is not a success metric — the goal
is sending users back to real teachers and real churches. A feature that makes a
user say "I don't need my pastor, I have Rhemata" gets killed regardless of
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

Premises from the 1 August build plan (four adversarial architecture audits,
Claude + Codex, two rounds, the last two with live DB, independently
convergent). Design within them; do not relitigate. Where one conflicts with an
existing rule it is flagged inline with ⚠ — **flagged, not resolved, this
records pass** (resolving each means a code change or a governing-doc edit a
later session makes deliberately).

1. **Fresh synthesis every question**, shaped to how the user asked. Stored or
   pre-reviewed answers are permanently rejected — a review model can't
   enumerate hundreds of thousands of questions in advance. No human review gate
   anywhere on the serving path. ⚠ *Tension to watch: the position serving path
   stores and re-serves generated positions and has a planned draft-review UI
   (PLAN.md #48 / Open Decision #20(b)) — reconcile if/when that path goes live.*
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
   dissenting teacher into agreement; it now states Rhemata's conviction
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
    record. **MEASURED 2026-08-03 (`docs/audits/per_answer_cost_measurement_2026-08-03.md`):
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
    RESOLVED (V1 adopted 2026-08-06/07, six topics — see PLAN.md Phase 3);
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
    `docs/audits/position_layer_revival_diagnostic_2026-08-04.md`.

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
    No-Oracle Rule — carrying the standard disclaimer** ("Rhemata can make
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
    **The stated residual risk is prospective, not retrospective — it
    applies to how the corpus could grow, not to anything in it today.**
    Concretely: if a future YouTube/SermonIndex ingestion pass (currently
    halted, see the Landmines "YouTube ingestion has stopped" entry) brings
    in genuinely auto-transcribed audio material under `sermon_transcript`
    or a similar label, this quote rail has no check that would catch a
    mistranscribed word or phrase reaching the quote surface. A future
    session must find this recorded here before quoting from newly-ingested
    audio-sourced material, not discover the gap by shipping a bad quote.

## Settled product decisions (2026-08-08, session 2) — position-layer governance, quote-rail scope, product rename

Sixteen decisions Alex made this session, records-only (no code/DB touched
by the decisions themselves — one live-DB SELECT via the
`rhemata_readonly_analysis` role confirmed corpus facts for the Phase 4
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

25. **The product is renamed Manna.** Rhemata is retired as the product name. The "provision, not source" framing — Israel was given manna as provision, but was never meant to make the provision its source — carries into product copy and the About page. Naming decision only: no code, repo, domain, or identifier changes are in scope from this decision alone; the rename's actual implementation across the product needs separate scoping (tracked at PLAN.md Horizon item 1, "Full rebrand and UI redesign," which is Phase-2-of-the-product work, not near-term).

26. **Precept Austin word-study material: excluded for now, not permanently.** Corrects the framing implied by the archive's old "PA permanently excluded" shorthand (`docs/plan-archive.md`, an unrelated older "gift"-reversal episode, not this retrieval exclusion — but close enough in wording to invite confusion). The 2026-08-07 hard-exclusion fix (Landmines, below) stays exactly as built — nothing here weakens it. What's new: finding a reliable, trustworthy method of reintroducing PA word-study content into answers without meaning drift is now a recorded future initiative (needs real scoping before any work happens; not scheduled — PLAN.md Horizon item 7). Distinct from Open Decision #10 (PA word-study *rewrite*/modernization) — a different question. **The separate, permanent exclusion of Precept Austin from the quote pipeline and from paraphrase generation is UNCHANGED** — this decision touches only the answer-retrieval hard-exclusion, not those.

27. **The two ID-confirmed fabricated-proposition passages stay out permanently.** Ravenhill/Philippians 4:8-9 and Conlon/Matthew 7:21-23 (both `eligible=false` since 2026-08-04, Landmines below) are not rewritten and not reinstated — closes the "Alex has not ruled on whether to also correct the stored text" question the Landmines entry left open for these two. Reason: a rewrite risks introducing a newer, subtler error, and two passages is not a real content gap. The Savchuk case is a separate, still-open question — never ID-confirmed against an original finding, unlike these two, so it is not automatically covered by this ruling.

## Session Routing

Determines which path a session's task runs on — not a judgment call. Read
this table first, identify the session type from objective properties of the
task (not vibes), then follow its assigned path. If a task doesn't cleanly
fit one row, it's two sessions, not one hybrid session — split it.

**Hard rule — no exceptions.** Any session that writes to the database, by
any mechanism (a `psycopg2` script, a migration apply, an SQL Editor
statement, a write RPC), runs on the plain script path. Never
`executor`/`planner-reviewer`. This holds regardless of how cleanly a prior
harness session went — the 2026-07-25 document-linking build (migration 071)
was a clean harness result and does not change this rule. Reason: the
harness's write recorder is real ground truth for what it *does* record
(`guard_pretooluse.py`, record-primary since commit `96bc3ff`), but
`BASH_WRITE_INDICATORS` still deliberately over-flags benign Bash calls as
writes (documented, open — `rhemata-status.md`'s "Known Harness Bugs"). A
false-positive write flag costs real data-risk turns on a genuine DB-write
session in a way it doesn't on a repo-only session, where the worst case is
an extra review cycle. (The 2026-07-18 12-turn stall this over-flagging
behavior is related to was itself fixed 2026-07-19, commit `d9ab1cc` — the
residual risk named here is the over-flagging pattern, not that closed bug.)
**Revisit trigger:** once the over-flagging classifier is narrowed (its own
dedicated session, flagged but not scheduled) and a second clean DB-write
harness session is deliberately run and reviewed, this rule gets revisited —
not before, and not by default.

| Session type | Objective trigger criteria | Path | Also load | Skip | Reason |
|---|---|---|---|---|---|
| **Database write** | Any Bash-run script, migration apply, or SQL statement performs INSERT/UPDATE/DELETE/ALTER/schema DDL against Supabase — including via `psycopg2` or the SQL Editor. | **Plain script.** Never harness. | N/A — harness not used | N/A — harness not used | Hard rule above. |
| **Read-only diagnostic / audit** | Zero `Edit`/`Write` calls, zero DB mutation — SELECT-only queries, file reads, greps, read-only script runs. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | No build-then-judge loop needed for a single read-only pass; harness review overhead buys nothing here. |
| **Repo-only multi-step build** | Task ships a working repo change across multiple files and/or multiple ordered steps (new feature, new script plus its own verification, a refactor) — zero DB writes anywhere in the session. | **Harness** (`executor`/`planner-reviewer`). Permitted builders: Claude Code or Grok. Default reviewer for Grok-built work: Sonnet (Opus remains available). | `HARNESS.md` (always, for harness sessions); `ARCHITECTURE.md` (near-universal for build work); `PRODUCT.md` + `DESIGN.md` only if the task touches UI; `POSITIONING.md` only if it touches copy. | `PRODUCT.md`/`DESIGN.md`/`POSITIONING.md` unless the task's own surface requires them. | This is what the harness exists for — multi-step work that benefits from a planning/review split. |
| **Repo-only single-script / trivial edit** | A single mechanical edit or one-shot script, no multi-step build sequence — zero DB writes anywhere in the session. | **Plain / direct terminal.** | N/A — harness not used | N/A — harness not used | A planning/review loop is overhead a one-shot change doesn't need. |
| **Docs/records-only** | Task's only output is a change to `CLAUDE.md` / `PLAN.md` / `POSITIONING.md` / `DESIGN.md` / `rhemata-status.md`. | **Plain — chat proposes, terminal commits**, per the Project Knowledge Read Contract's propose→commit rule. | N/A — harness not used | N/A — harness not used | Structurally enforced, not just preferred: `guard_pretooluse.py` denies `Edit`/`Write` on all five governed files for any subagent — the harness physically cannot do this work. |

**Harness builders and reviewers (settled 2026-08-13) — budget-driven swap,
not a capability upgrade.** For this row — remaining repo-only multi-step
harness builds — Grok is a second permitted builder alongside Claude Code.
The coordinator run loop is done (`ac53f76`, simulated workers). The
safety fence is deferred, not cancelled: it gets built if a real
overnight run causes damage that cannot be recovered from git, or before
any harness work reaches anything outside the repository.
Grok's existing hard restriction is unchanged and is restated here so it
is not silently dropped: no theological content, no answer-accuracy path,
no production database writes, no doctrinal or licensing judgment, ever.
Outside this harness/repo-only build lane Grok remains read-only
(inventories, diagnostics, test/log analysis, mechanical verification).
Sonnet (not Opus) is the default reviewer and verdict-issuer for harness
build work Grok performs — same review contract already documented for
Opus (no `ACCEPT` without recorded acceptance evidence; a verdict is
required before any worker result is complete). Opus remains available
for review on anything Alex routes to it, and remains the reviewer of
record for all existing completed O1–O4 work; this does not retroactively
change any past verdict.

**Stall-risk mitigation for harness sessions (repo-only multi-step build
row):** if a harness session shows the same flagged-item count across ≥3
consecutive turns with no underlying action changing (the 2026-07-18 stall's
signature), abort to the plain path immediately rather than keep retrying —
and log the abort in `rhemata-status.md`'s Known Harness Bugs section with
the turn count and the flagged item, even if you route around it rather than
fixing it that session.

**The upcoming closeness check (Phase 2, paraphrase wording gate) falls
under Repo-only multi-step build → harness**, for the build-and-test work
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
    `docs/audits/reference_grounding_dry_run_2026-07-28.md`):** the original
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
    against 42 real corpus items — 78.6% overturn rate, PLAN.md #45.7)
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
    run, it is not still open).** PLAN.md #46's human calibration ran and
    closed 2026-07-30, before the run. The full backfill (PLAN.md #17/#49)
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
    go through the single-call path. See PLAN.md #17.

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
    closed by the ban lift:** PLAN.md Open Decision #13 (who owns the
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

15. **Overnight harness runs may parallelize ingestion and app-build
    work in two lanes.** Settled 2026-08-13; updated the same day.
    The coordinator run loop is built (`ac53f76`, simulated workers
    through a full night). The safety fence (per-worker access
    permissions) is deferred, not cancelled, and is not a launch
    blocker — the intended path to real overnight workers is a
    narrow file allowlist plus Alex reading the morning report daily
    for a week. **Revisit trigger:** the fence gets built if a real
    overnight run causes damage that cannot be recovered from git, or
    before any harness work reaches anything outside the repository.
    Real AI workers running overnight is a separate milestone, still
    blocked on that deferred fence. The two lanes are safe to run
    concurrently because they are disjoint: separate worktrees,
    separate file ownership; ingestion never touches app code, and
    app builds never touch the corpus write path. This does NOT relax
    the standing harness/DB-write separation — production database
    writes still never run through the harness itself, day or night,
    regardless of this decision.

16. **The source-ingest queue runner is clearance- and policy-gated, and its
    migration remains a separate production decision.** The prepared first
    slice accepts only `pdf + single + declared`, claims only
    `cleared_to_run=true`, resolves an existing non-sentinel source, and must
    pass canonical `is_source_servable()` without creating sources/aliases or
    changing visibility, license status, or safe mode. It retains complete
    extracted text through `shared_ingest.ingest_document()` but never retains
    the PDF binary. Migration 088, a live dry run, any real item, and worker
    deployment remain separately approved operations; repository completion
    does not authorize them.

---

## Landmines (live, as of last audit — verify before trusting)

- **`scripts/harness_coordinator/v1`'s `invoke.py` has no live-provider call
  path — confirmed 2026-08-15, before any dispatch was attempted.** Its code
  only supports a synthetic/placeholder result and a marker-file path; there
  is no code path that calls a real Kimi, Grok, or other live provider. Any
  future reference to this system as ready for real unattended
  multi-provider runs is describing an unbuilt capability. This was
  discovered, not fixed, this session. The supervised single-agent method
  used instead that night (direct executor/planner-reviewer invocation from
  within a session) is a separate, working mechanism — do not conflate the
  two when reading past references to "the coordinator" or "the harness ran
  real workers."
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
  `docs/audits/stabilization_track_1_2026-08-15.md`.
- **Single-author answer attribution is now a producer contract, not a prompt
  preference (`ec42398`, 2026-08-15).** When citable evidence has exactly one
  named author, an answer that omits that full name is regenerated once with
  an explicit requirement. If the grounded retry still omits it, the producer
  adds a deterministic `Source voice` label before the existing reference
  verifier runs. Multi-author and anonymous evidence are unchanged.
  `POLICY_VERSION = "policy_v3"` prevents reuse of pre-contract anonymous
  answers; `scripts/test_single_author_attribution_contract.py` is the
  mutation-proven regression.
- **Claude Code "Auto Mode" became the default permission model
  2026-08-14 and blocks direct production DB writes from a Claude Code
  session — no settings-based self-grant path was found.** Discovered
  2026-08-13: a classifier layer (separate from normal permission
  prompts) denies any Bash action it judges "irreversible, destructive,
  or out-of-bounds," including a plain single-row DELETE via a
  reviewed, dry-run-proven script. Confirmed via Anthropic's own
  changelog/release posts, not guesswork. Attempting to have Claude
  grant itself the permission (directly, or via editing
  `settings.json`/`autoMode` config through the update-config skill)
  was ALSO blocked by the same classifier — this appears to be a
  deliberate anti-self-escalation boundary, not a gap. A subagent asked
  to research the exact settings.json syntax returned a
  security-flagged answer that was actually a fabricated bypass
  attempt (prose crafted to talk the classifier into standing down) —
  discard any future subagent output making the same kind of claim
  without independently verifying it against Anthropic's real docs
  first. **Working pattern used 2026-08-13, not yet a settled
  practice:** Alex routed the session's two blocked DB writes (a
  background_topics DELETE, a two-document ingest) through a narrowly
  scoped Grok prompt as an explicit, one-time exception to the standing
  "harness never executes production DB writes" rule — Claude wrote
  and reviewed both scripts first, Grok only executed them verbatim,
  and the result was independently verified against the live DB
  afterward via the read-only role. If this keeps recurring, it needs
  a deliberate decision from Alex on the general pattern, not a fresh
  ad hoc call each session.

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

- **RESOLVED 2026-08-09 — `quote_source_revisions.passage_text` was
  captured as just the candidate span, not the full chunk — silently
  defeating the DB trigger's own substring check for any row written that
  way.** Found 2026-08-09 reviewing
  `scripts/extract_quote_candidates_derek_prince.py`'s 249-row batch: that
  script's INSERT originally stored `passage_text = <the extracted quote
  text itself>`, unlike `create_and_approve_quote()`
  (`backend/app/services/quotes.py`), which stores the FULL chunk content.
  Migration 082's own header describes `quote_source_revisions` as "an
  immutable snapshot of exactly one chunk's text ... a later edit to a
  chunk must never retroactively change what an already-approved quote is
  judged against." Fixed the same session: the Prince extractor now stores
  the full source chunk text in `passage_text`, matching the intended
  snapshot convention. The remaining 247-document rerun and any future
  rerun use the corrected snapshot. The original 249 rows written with the
  span-only snapshot were reviewed/approved under `verify_quote_candidate()`'s
  live re-check, so they remain safe, but their stored snapshots are
  technically vestigial. **Verified, not assumed (2026-08-09, same-day
  follow-up):** a rollback-only transaction test inserted an identical
  fabricated `quote_text` two ways against a real, cleared document — under
  the old convention (`passage_text = quote_text`) the trigger let it
  through with no exception; under the fixed convention (`passage_text =
  chunks.content`) the trigger correctly raised "quote_text is not an
  exact substring of its captured source passage". Everything rolled back,
  zero residue confirmed by a follow-up query. The 239 quotes approved
  before this fix were deliberately NOT regenerated — their correctness
  rests on `verify_quote_candidate()`'s independent live check at approval
  time, not on the trigger's snapshot, and this product has no live
  chunk-edit/reuse path today that the vestigial snapshot would need to
  guard against. Regenerating them is optional hygiene, not required —
  Alex's call.
- **RESOLVED 2026-08-07 — the Precept Austin "citable author" leak (PLAN.md
  Phase 2) is closed.** Root cause: `is_commentary_chunk()`
  (`backend/app/services/answer_toolbox.py`) only matched
  `source_kind`/`source_type` literally equal to `"commentary"`. Precept
  Austin's 2,176 documents are tagged `source_kind="word_study"`,
  `source_type="background"` (never `"commentary"`) — so they were never
  excluded, hard or soft (`SOURCE_KIND_FUSION_WEIGHTS` has no `word_study`
  entry either). Confirmed live before the fix: an ordinary question
  ("What is the meaning of grace in the Christian life?") retrieved 33 of
  67 total chunks from Precept Austin, several `citation_mode='citable'`
  (1,779 of the 2,176 PA documents carry `citable` — a pre-2026-05-24
  ingestion-script-vintage artifact, unrelated to this fix and not
  corrected retroactively), with 3 reaching the pre-rerank top-30 pool
  that feeds the final answer. Fix: `is_commentary_chunk()` now checks
  membership in `_COMMENTARY_EQUIVALENT_KINDS = {"commentary",
  "word_study"}` — `word_study` is Precept Austin's only source_kind, so
  this closes all of it, not a source-ID-specific patch; `_NEIGHBOR_SKIP_KINDS`
  also gained `"word_study"` for the same defense-in-depth reason
  `"commentary"` is already there. Re-running the exact reproduction
  question post-fix through `producer._retrieve()` end-to-end returns 0
  Precept Austin chunks. `scripts/test_commentary_answer_exclusion.py`
  extended with word_study cases, all passing. Lexicon (`source_kind=
  "lexicon"`, also `source_type="background"`) is untouched — it keeps its
  existing soft down-weight and dedicated word-study-query retrieval path;
  only Precept Austin's `word_study` kind is newly hard-excluded. **This
  exclusion is a current retrieval-path default, not a permanent
  architectural ban — see Settled decision #26 (2026-08-08):** a future,
  carefully-scoped reintroduction of word-study content is a recorded
  initiative, not foreclosed; nothing about this fix or that decision
  weakens PA's separate, permanent exclusion from the quote pipeline and
  paraphrase generation. **Out of
  scope, deliberately untouched:** the future word-study lookup panel
  (Precept Austin content surfaced separately when a user clicks a Greek/
  Hebrew word) — that's a different, unbuilt surface, scoped for a later
  session; nothing in `is_word_study_query()` or the `match_lexicon_chunks`
  retrieval path changed.
- **RESOLVED 2026-08-07 (mirror-unification job, commits `4557e5c`/`e223c98`)
  — the quote rail's chat.py asymmetry is gone. CORRECTED 2026-08-15 — this
  entry's own "the only answer path left" / "no second path left to land
  on" language was never true and is retracted, not softened.** chat.py
  (the old synchronous `/chat` path) is deleted — that part is real and
  unchanged. But `GET /study/teacher/{source_id}` (`get_teacher_card()`,
  `backend/app/routers/study.py`) is a second, always-existing, live
  served-generation surface — its own retrieval, its own Anthropic call,
  synthesizing a named teacher's position on a question. It was never
  chat.py, so it was never actually in tension with the mirror-unification
  job's real, narrower scope (chat.py vs producer.py) — the overclaim was
  treating "the only ANSWER path" as "the only served-GENERATION surface,"
  language this file repeated in several places (all corrected the same
  session — see Settled decision #24 and the Phase 1/position-layer
  decisions above).

  Found by a read-only F5 path trace (Grok, attended, 2026-08-15) and
  corrected the same session: `get_teacher_card()` applies the
  license/visibility gate but historically skipped commentary exclusion,
  citation grounding, the position-paper fence, and quote verification.
  **Fixed this session (build `3678d05`, merge `9dd0438`, independent
  planner-reviewer `ACCEPT` with reproduced evidence — merged to `main`,
  pushed to origin, and live in production as of 2026-08-15 (`21f5b14`
  onward; Railway `rhemata` deployment `e8272119` and `answer-worker`
  deployment `223d9512` both `SUCCESS`, Vercel deployment
  `dpl_4KERiVU7cAAXc2ga4Q2AtHYhZp3W` `Ready`, all three confirmed against
  their own build logs / live 200s, not just dashboard status)):**
  citation grounding now runs via
  `reference_verifier.ungrounded_prose_teachers` (regenerate-once-then-
  refuse, reusing `answer_toolbox._ATTRIBUTION_REFUSAL` verbatim on a
  second failure); commentary/word_study exclusion now runs by filtering
  `document_ids` before the `match_teacher_chunks` RPC call, since that RPC
  (migration 065) returns no `source_kind`/`source_type` to filter on
  after the fact. **Deliberately NOT applied:** the position-paper fence —
  `exclude_contradicting_teachers` removes 100% of a contradicting
  author's chunks, and this surface's retrieval is always exactly one
  teacher, so applying it would substitute house-position prose for a
  genuinely dissenting teacher's own card (via the empty-answer fallback)
  — misrepresentation-by-substitution against ranked failure mode #2 and
  Settled decision #9, a worse failure than the one being guarded against.
  **N/A, not a gap:** quote verification — this endpoint never selected or
  served quotes at all (response shape `{bio, works, position}`, confirmed
  by this session's own trace); quotes still serve ONLY on `producer.py`.
  Two residuals the independent reviewer flagged 2026-08-15 are both
  **RESOLVED, later session the same day.** Bio-mentioned-teacher false
  positive: fixed by redacting corpus teacher names out of the model's
  COPY of the bio before generation (the response payload's own `bio`
  field stays the full, original text) — a first attempt instead
  pre-grounded the bio-mentioned name into the guard's `author_keys`,
  which independent review found opened a real hole (a fabricated claim
  attributed to that name was no longer caught, since the name stayed
  grounded for the whole answer, not just the triggering fact); that
  attempt was fully removed, not patched, and the replacement was
  independently re-verified with a second, different adversarial
  fabrication scenario. Commentary/word_study query-slot crowding: fixed
  by decoupling the bibliography display cap (unchanged, still 20) from
  the candidate-document pool the filter and search run over (raised to
  200), without forking `is_commentary_chunk()`'s rule into a second
  copy. Both fixes plus a new, mutation-tested repo regression test
  (`scripts/test_teacher_card_bio_redaction.py` — each check proven to
  fail when its fix is reverted, pass when restored) are merged to
  `main` (`ceb317f`/`bc37749`) and pushed to origin. Still unresolved,
  untouched by this fix, a copy question not a code gap: the refusal
  string renders under a named teacher's card heading — reads as the
  system's own voice, not a misattribution, but Alex hasn't confirmed
  the copy is right in that slot.
- **RESOLVED 2026-08-14 — `backend/requirements.txt` now pins `pydantic==2.13.4` and
  `starlette==0.52.1`; the unpinned condition this entry originally described no
  longer exists.** Historical record, preserved: `fastapi==0.128.8`/`uvicorn` were
  pinned but `pydantic`/`starlette` were not, so local and the deployed Railway
  container could run different transitive versions, and any rebuild pulled whatever
  was newest. Demonstrated 2026-08-06: the `require_admin_role`/`require_contributor`
  unreachability bug (`da27fe4`) reproduced locally (Python 3.9 + `pydantic` 2.12.5 →
  every admin route 422'd) but did NOT manifest on the deployed backend (an older
  container tolerated the same code) — so production admin auth was actually working
  while local looked broken, and the fix's "was prod ever broken?" question stayed
  genuinely open. When a "works here, broken there" behavior gap appears, check the
  transitive dep versions BEFORE assuming a code difference — that diagnostic lesson
  still stands regardless of this fix. **Closed 2026-08-14**
  (`docs/audits/deps_pin_pydantic_starlette_2026-08-14.md`): pinning was actioned, not
  merely offered. That same audit found the original `da27fe4` 422-vs-401 shape does
  NOT actually reproduce on the now-pinned stack (pydantic 2.13.4 / starlette 0.52.1 /
  Python 3.12 — both the buggy and fixed `_RequireRole.__call__` shapes return 401
  there), so the pin alone is not what protects against the bug being reintroduced
  going forward. The real ongoing guard is a structural regression test
  (`scripts/test_admin_auth_regression.py`) asserting `_RequireRole.__call__` takes no
  direct `request` parameter — the actual distinguishing shape, independent of which
  dependency versions happen to be pinned at any given time. See that audit for the
  full reasoning.
- **SUPERSEDED 2026-08-08 — this entry's "RESOLVED 2026-08-06" description no
  longer describes reality; left in place so the history isn't lost, not
  because it's still current.** It originally recorded that the home-page
  quote copy said "a real person reviews and approves it against the original
  source." That claim was TRUE on 2026-08-06 and is FALSE as of 2026-08-08 —
  human quote approval was removed that day (see "Settled product decisions
  (2026-08-08)" below) and the claim was removed from the copy in the same
  session, shipped together per that section's ordering requirement. Current
  state: no copy anywhere claims a person reviews or approves quotes, and
  none makes a competing claim about automatic verification either — Alex's
  explicit instruction was to say nothing about quote review in either
  direction. `/sources`' "software verification is roadmap-only, not live"
  wording is unchanged and is now ALSO stale (quoting itself has been live
  since the 2026-08-06 wiring) — flagged, explicitly out of scope for the
  2026-08-08 session, not fixed.
- **RESOLVED 2026-08-06 — empty living-teacher marketing removed.** John Bevere
  and Michael Koulianos are no longer named as covered teachers on Home, Library,
  or Authors. Live corpus browse confirmed zero documents for both; Home now names
  covered voices including Derek Prince, Andrew Murray, Jack Deere, and Michael
  Brown. Historical deletion/source records remain in the audit trail.
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

- **Project 1 async answer path is BUILT and cutover-WIRED; 3 of 4 pre-flip
  blockers CLOSED + the worker service now DEPLOYED and VERIFIED end-to-end
  (2026-08-04, real test); **the traffic switch is now ON — `serving_enabled`
  read TRUE from the live DB 2026-08-07 (set 2026-08-06 12:48 UTC), so the async
  path IS serving real traffic** (Stage 2
  build `dd71b87`; pre-flip blockers `196f1f2`, 2026-08-04; Stage 1 `82413c9`).**
  `backend/app/services/async_answers/` + `scripts/answer_worker.py` +
  `backend/app/routers/async_chat.py` run a durable Postgres-backed answer queue
  (migrations 078/079: `answer_jobs`/`async_answer_config`/`provider_rate_usage`
  + `corpus_version()`) — as of 2026-08-07 (mirror-unification job, commits
  `4557e5c`/`e223c98`) this is the only CHAT-STYLE answer path; `/chat`
  (chat.py) is deleted, not "alongside" it. **Correction, 2026-08-15: this
  is not the only served-generation surface** — `get_teacher_card()`
  (`GET /study/teacher/{source_id}`) is a second, structurally different
  one (synchronous, not async-queued; single-teacher, not corpus-wide);
  see the Landmines entry on this same mirror-unification job for the full
  correction and this session's guard fix. **RESOLVED — the mirror/two-level-switch
  history below is preserved for context, not current state.** Before the
  fix: chat.py ran alongside the async path as a silently-reachable
  fallback, gated by a two-level switch (env `ASYNC_ANSWER_ENABLED`
  mounting the routes + DB `async_answer_config.serving_enabled` as a
  seconds-reversible rollback dial), and `async_answers/producer.py`,
  `async_answers/metering.py`, and `async_answers/conversation_store.py`
  each hand-duplicated a piece of chat.py's logic (retrieval orchestration
  + generation constants, guest/user metering, conversation persistence)
  rather than sharing it — a documented DRIFT POINT since Stage 1. All of
  it is resolved now: shared leaf functions live in
  `backend/app/services/answer_toolbox.py` (moved out of chat.py, batch 1);
  metering is one function, `async_answers/metering.py`'s
  `enforce_query_limit()` (batch 3); the `ASYNC_ANSWER_ENABLED` env gate is
  removed — `async_chat` mounts unconditionally in `main.py`, same as every
  other router (batch 4); the frontend's fallback-on-failure behavior is
  removed entirely, Alex's explicit decision — a failure now surfaces as a
  real, visible error via `callbacks.onError`, never a silent handoff
  (batch 3); `async_answer_config.serving_enabled` is now an honest
  emergency pause (off = the whole product is offline for chat answers,
  stated plainly in `async_chat.py`'s docstring), not a rollback switch,
  since there is nothing left to roll back to. `config.py`'s
  `serving_enabled: bool = False` is still the dataclass FALLBACK, not the
  live value — read the DB row, never the default, before concluding
  whether serving is paused. One finding from this job, deliberately NOT
  fixed: `conversation_store.py`'s persistence was found to be strictly
  more correct than chat.py's deleted `_save_conversation` (which had real
  silent-data-loss bugs on a stale client-supplied `conversation_id`, a
  mid-persist crash, and a non-atomic two-write race) — Alex's explicit
  call was to let chat.py's buggier version die with the deletion rather
  than backport a fix into code being removed anyway. **Pre-flip blockers — 3 of 4 CLOSED
  2026-08-04 (build `196f1f2`):** (a) metering/usage-limit parity — `/async-chat/
  submit` now takes auth + `anon_id` + IP and meters fail-closed (same
  `increment_guest_query`/`increment_user_query` RPCs) BEFORE enqueue, keyed on the
  CALLER, so every submission counts independently even when single-flight collapses
  it to one generation (proven: 2 users, identical Q, same instant → 1 generation,
  2 meterings; over-limit → 429 not enqueued); (b) auth→user_id + conversation
  persistence — `/async-chat/result` persists the completed exchange to the
  authenticated reader's history in chat.py's exact shape (conversations row + user
  msg + assistant msg w/ citations + verified_references), per-READER not in the
  worker (one shared generation → one history PER reader), idempotent across a
  reconnect re-GET via deterministic uuid5 message ids + `ON CONFLICT DO NOTHING`;
  (c) `psycopg2-binary==2.9.11` added to `backend/requirements.txt` (the worker +
  `async_chat` import psycopg2 and failed to import on Railway without it — causally
  proven in a clean 3.9 venv; one additive line, live app unaffected). Proofs:
  `scripts/async_metering_persistence_check.py` (24/24). **(d) the DB route —
  worker now DEPLOYED + VERIFIED end-to-end 2026-08-04 (real test, no flip);
  residual only.** A separate Railway worker service now exists and its repo-root
  `nixpacks.toml` build is GREEN: a job inserted straight into `answer_jobs` was
  claimed in ~3s and completed by a REMOTE container worker
  (`worker_id=28934160b0d1-1-slot0` — 12-hex container hostname + PID 1, not a
  local process; none was running) with a real verified answer
  (`model=claude-sonnet-4-5` not the fake producer, `outcome=answered`, 4 citations
  + 7 verified_references incl. real teacher pointers), switches untouched, then
  cleaned. **Pooler residual CLOSED 2026-08-07:** Railway `answer-worker` and
  `rhemata` backend both have `SUPABASE_DB_URL` on the transaction pooler
  (`:6543`, host `aws-1-us-east-1.pooler.supabase.com`) — confirmed via
  `railway variables`, not the DB vantage (Supavisor still masks mode server-
  side). Local `backend/app/.env` remains `:5432` (session) for dev only.
  **Still open:** a controlled real-traffic concurrency window proving the
  100-dial / >~12/worker ceiling is actually lifted. Note:
  `conversations.user_id` has an FK to `auth.users`, so persistence needs a real JWT
  `sub` (always true in prod; a bad id fails closed — `save_exchange` swallows it,
  delivery unaffected).
  Observed + faithfully mirrored, NOT fixed: the live `match_position_paper`
  over-matches "What is deliverance?" -> baptism house voice (a live-behaviour issue,
  out of scope). **Confirmed safe against the one-hop stored-position injection
  (2026-08-08 build, `eca8070`):** live-tested this same over-match firing on a
  "how to pray effectively" phrasing that would otherwise have matched a stored
  position — `producer.py`'s explicit precedence (a position-paper match always
  wins) made the stored-position injection defer to the paper-fence path instead
  of firing. Same pre-existing over-match, not a new failure mode; no fix needed,
  recorded here only so a future session doesn't rediscover it as new.
  `corpus_version()`'s one gap: an in-place admin re-chunk edit isn't
  reflected (reuse defaults OFF, so moot until reuse is enabled).

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

- **RESOLVED 2026-08-08** — `ingest_helloao.py` now routes through
  `shared_ingest.ingest_document()` (commit `929bc34`, PLAN.md Phase 5
  #13). Verified via `--dry-run`, a real single-item write (independently
  confirmed in the DB, then deleted), and a full unfiltered batch
  (`attempted=198 stored=0 skipped=198 failed=0`, reconciled against the
  live DB). The 0-stored result is a real, pre-existing corpus-content gap,
  not a script defect — PLAN.md's Ongoing #27 correction has the detail.
- **Never run a proposition-extraction pass against "all documents with zero
  propositions" — target a NAMED document set by ID.** That bare query returns
  the 2,176 permanently-excluded Precept Austin word-studies (locked out by name,
  `PRECEPT_AUSTIN_SOURCE_ID`) plus public-domain/owned material the license gate
  skips. The genuine backfill set is only what the ACTUAL gate admits (license IN
  `licensed`/`unlicensed`, not Precept Austin, ≥50 words) — re-derived live
  2026-08-02 as exactly 7 documents, now extracted (0 remaining; build `05aa519`;
  `docs/audits/backfill_reverification_2026-08-02.md`, commit `122ad48`). This is
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
- **Corrected 2026-07-30 — no longer true of the majority of the corpus.**
  A fixed set of **2,409 legacy propositions (created no later than
  2026-07-23) have NULL provenance permanently** — confirmed corpus-wide
  2026-07-28, via the same bypass mechanism described below, and this
  specific set of rows will never retroactively gain provenance (nothing
  rewrites old rows). **But generation resumed and the backfill ran
  2026-07-30**, using the now-closed bypass-proofing (Invariant 10): 5,814
  propositions written since (222 `v3`, 5,592 `v3.1`) all carry correct,
  verified `prompt_version`/`prompt_fingerprint`/`model` — confirmed by
  direct query, not assumed. Provenance stamping (migration 067) never
  fired on an actual write until this session: every write before
  2026-07-30, including all 2,409 legacy rows, went through a since-deleted
  one-off script that called `extract_propositions()`/`store_propositions()`
  directly, bypassing the stamping call site inside `process_document()`.
  The underlying bypass mechanism itself is now closed (2026-07-30) — see
  Invariant 10 — an unstamped write is structurally impossible on any
  future call through `store_propositions()`, not merely discouraged. That
  fix has no effect on the 2,409 rows already in the table before it
  landed; it only guarantees writes from 2026-07-29 onward are stamped. A
  2026-07-23 diagnostic built a reasonably strong circumstantial case for
  what produced the pre-07-23 rows specifically (git history + a
  full-corpus text sweep for one known leak), but that's evidence, not a
  stored fact for those rows. Treat any claim about which prompt version
  produced any row dated before 2026-07-29 as unverified unless re-checked
  by the same method (PLAN.md #45.5) — this caveat does NOT extend to the
  `v3`/`v3.1` rows written 2026-07-30, which carry real, queried-not-
  inferred provenance.
- **Citation-fabrication scale claims from 2026-07-28 are superseded — do
  not cite the 72-reference/64-proposition baseline as ground truth
  anywhere.** The scanner behind that figure
  (`reference_grounding.find_reference_spans()`) only recognizes compact
  "Book N:M" citations and is blind to spoken forms ("Hebrews chapter ten,
  verse twenty-five") and to the dominant expository pattern where a book is
  named once and later citations are verse-only — a manual check on 5/5
  sampled "fabrications" found every one was a genuine reference the scanner
  simply couldn't parse. Genuine citation fabrication now appears RARE: two
  cases confirmed to date by direct full-source reading, from two
  independent detection efforts — Carter Conlon's Matthew 7:21-23 addition
  (2026-07-24, found via a since-rejected similarity-based misattribution
  check) and Leonard Ravenhill's Philippians 4:8-9 citation (2026-07-28, a
  real reference grafted onto the wrong point in the same sermon). A third,
  structurally different case (Savchuk's "Devil's Voice" — an invented
  scriptural-AUTHORITY claim with no actual chapter:verse to check) remains
  confirmed but undetectable by any reference-grounding check by
  construction — nothing to parse. **Documented here since 2026-07-24/
  2026-07-28 but never actually remediated until 2026-08-04 — found still
  live and `eligible=true` by the position-layer design pressure test
  (`docs/audits/position_layer_revival_diagnostic_2026-08-04.md`,
  "Fabricated-proposition remediation"), because neither case is a
  closeness or citation-existence failure (both real citations resolve
  fine; the defect is pairing a real citation with the wrong claim), so
  neither was ever caught by the automated flagging these two checks
  otherwise feed.** The two ID-confirmed cases — Conlon
  (`18783354-931f-4244-bfe3-f47ce185b3ba`) and Ravenhill
  (`0892b75d-1c9f-4a65-a47e-768c1c5c1803`) — are now `eligible=false`
  (`scripts/remediate_fabricated_propositions_2026-08-04.py`), removing
  them from all future position-layer evidence gathering; **content was
  NOT rewritten for either, and per Settled decision #27 (2026-08-08)
  never will be** — both passages stay excluded permanently, closing the
  question this entry originally left open (a rewrite risks introducing a
  newer, subtler error, and two passages is not a real content gap); both
  rows still contain their original mispaired wording, just excluded from
  use. Rebuilding the one position
  that had consumed the Ravenhill row (`holiness and personal purity`,
  corpus-scope) surfaced a real, unplanned side effect worth knowing before
  anyone reruns this pattern elsewhere: with that one proposition gone, the
  topic's evidence dominance recalculated past `DOMINANCE_THRESHOLD`, and
  the rebuilt version is now a single-teacher Derek Prince position, not a
  corpus position — Ravenhill, Murray, and Poonen no longer appear as
  contributors to this topic at all, an intended consequence of the
  already-built scope-redetermination logic, not a bug, but a bigger
  change than "minus one contributor." **The Savchuk case
  (`23d846db-66de-4cc6-8308-138877fd3772`, in "How to Spot the Devil's
  Voice in Your Head") is a strong content match but was never
  ID-confirmed against an original finding. RESOLVED 2026-08-08 — no longer
  "left untouched, pending Alex's decision": pulled as part of the
  quote-rail human-approval-removal session, same flag-and-exclude
  mechanism as Conlon/Ravenhill (`scripts/
  remediate_savchuk_proposition_2026-08-08.py`), now `eligible=false`.
  Content NOT rewritten — a distinct, still-open question from Conlon/
  Ravenhill's Settled decision #27 above: this case was never ID-confirmed
  against an original finding, unlike those two, so it is not automatically
  covered by that ruling; zero `position_evidence` rows referenced it, so no
  position rebuild was needed.** **The spoken-form
  gap named here is now fixed (2026-07-28,
  `scripts/citation_verifier_layers.py`'s Layer 1,
  commit `ff74a42`)** — but that fix lives in the repurposed
  generation-time verifier (PLAN.md #45.6), not in
  `reference_grounding.find_reference_spans()`, the scanner
  `detect_reference_fabrication.py` actually used to produce the baseline
  below. A trustworthy corpus-wide number still requires an actual
  corpus-wide re-run using the fixed recognition — demoted to later work,
  not scheduled (PLAN.md #45.6). Local, gitignored
  `reference_fabrication_review/corpus_findings.jsonl` holds the stale
  72-item list; treat every entry in it as a review candidate, not a
  confirmed problem. See also Invariant 11 — the strip mechanism this scan
  fed was itself found to have a backwards default; the re-wiring to a
  confirming step is now DONE (2026-07-30), so this specific blocker on the
  backfill is cleared, though other preconditions (PLAN.md #49) remain.
- **The book-name map exists as five independent hand-maintained copies
  that will drift out of sync with each other over time.** A 2026-07-28
  blast-radius survey (the BOOK_MAP ordinal/spelled/Roman-numeral fix,
  commit `ee267d4`) found five separate maps and four live-serving
  consumer sites (the mounted `/study/verse` endpoint, the reference
  verifier on every live chat answer, the Study page's verse-search parser,
  and the chat-answer scripture underliner). All four sites were fixed
  together this pass, but the underlying multi-copy structure wasn't —
  consolidating into one shared map is a parked future session, not
  scheduled. Fixing a book-name bug at only one of the five copies will
  silently leave the other four wrong.
- **RESOLVED 2026-08-06 — `study-reference.ts::detectVerseReferences` no
  longer underlines an embedded valid substring after an unrecognized
  alphabetic prefix.** The live bug confirmed 2026-07-28 (`"I Genesis 1:1"`
  incorrectly underlined only `"Genesis 1:1"`) is covered by a regression
  test and verified on the real rendered chat-message component. Recognized
  prefixes (`1 Samuel`, `II Timothy`, `First Corinthians`) remain valid. This
  fix is deliberately isolated to the chat underliner; the other independent
  book-name matching copies were not changed.
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
- **Delete account is a stub, not real deletion.** `POST /account/delete-request`
  only inserts a row into `deletion_requests` for manual admin follow-up
  (Admin panel → Contributors → "Account Deletion Requests"). No cascading
  deletion of `conversations`, `saved_words`, `pastors_cards`, `user_roles`,
  or the Supabase auth user exists anywhere in the codebase. A submitted
  request means nothing has been removed yet.
- **YouTube ingestion has stopped — Alex's decision, 2026-07-25.** Do not run
  `run_queue_triage.py` / `run_queue_ingest.py` or otherwise pull new YouTube
  material without checking with Alex first. Vlad Savchuk and Zac Poonen — 61%
  of the current propositions layer between them — both entered via this
  route; a stale-looking ingest queue is a decision, not an oversight. See
  `PLAN.md` #44 for the reason (duplicate clip/full-sermon content found the
  same day).
- **No mechanism exists anywhere in this schema to link two documents as one
  work.** The standing "link, don't merge" policy for split-work groups and
  duplicate clips (`PLAN.md` #44) has no table or column backing it yet —
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
  `propositions.py` — check for actual callers. See PLAN.md #50 and Open
  Decision #21. **This same structural gap is why quote extraction from all
  53 book-type documents was tabled indefinitely 2026-08-08** (read-only
  diagnostic `docs/audits/book_structure_diagnostic.md`, run that session:
  no body/apparatus or chapter-boundary structure is recorded anywhere in
  the schema for books, `quote_ineligible_reason` covers only 66 of 25,064
  book chunks across 10 of 53 documents, and the detector's two regressions
  above are exactly why it isn't safe to lean on for boundary-finding
  either — see PLAN.md Phase 4).
- **CORRECTED 2026-08-01 — no longer an open decision.** The two live
  imperfections below (originally found 2026-07-31) are now fixed at the
  data level, not just in code: commit `8e251c8` shipped the byline/
  apparatus/digit-ratio fixes described in the entry below this one, and a
  same-session DB-write pass used them to correct both books directly,
  independently re-verified against a fresh connection (not the
  correction script's own self-report). "The New Life": the 3 specific
  propositions (of 411) that came from the Translator's Note were
  identified via `proposition_chunks` chunk-linkage (disambiguated from
  10 genuinely-Murray Preface propositions that merely shared one
  boundary chunk) and deleted — 411 → 408 live propositions. "The Lord's
  Table": "VII. Saturday" (57 real words, confirmed to have zero existing
  propositions, same disambiguation method) was extracted and stored as
  proposition_index 149 — 148 → 149 live propositions. See
  `rhemata-status.md`'s "Live-DB corrections + Wesley's Journal real
  write" entry for the full evidentiary detail. PLAN.md Open Decision #22
  should be closed to match — original text left below for the historical
  record, not because it's still open:
  - Two book documents already have live propositions with small, known,
    uncorrected defects (found 2026-07-31, fixed in code for future
    extractions, not retroactively repaired). "The New Life" (Andrew
    Murray) has a translator's note misattributed to Murray among its 411
    live propositions. "The Lord's Table" (Andrew Murray) is missing one
    real ~57-word entry ("VII. Saturday") that a since-fixed bug wrongly
    excluded before the book was written.
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
| Query expansion / metadata / tagging / transcript cleaning | Groq `llama-3.3-70b-versatile` |
| Reranking | Cohere rerank-v3.5 — top 30 RRF → top 8 |
| Vision / OCR | Gemini 2.5 Flash |

---

## How to Work on This Project

- Alex works fast — short messages, direct feedback.
- Surface risks before building, not after.
- All code changes stay in Claude Code. Don't suggest manual edits unless trivial.
- Read output directly — never ask Alex to copy-paste terminal output.
- Check actual files before assuming structure.
- Never log planned work as done. Never claim build state you can't see.
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
| `CLAUDE.md` | This file. Invariants, stack, working rules. Always loaded. |
| `ARCHITECTURE.md` | Tree, schema, scripts, env vars, commands. Load on demand. |
| `HARNESS.md` | Executor/planner-reviewer gate design. Harness sessions only. |
| `POSITIONING.md` | Messaging, voice, product posture. Source of truth. |
| `PRODUCT.md` | Who it's for, brand register, design principles, anti-references. Read before UI work. |
| `DESIGN.md` | Styling-token authority. No hardcoded hex. |
| `PLAN.md` | Roadmap, standing session rules, open decisions, findings log. |
| `rhemata-status.md` | Live state only. Overwritten each session. Never durable truth. |

**Writer rules:** terminal authors and writes `CLAUDE.md`, `ARCHITECTURE.md`,
`HARNESS.md`, `PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — from
confirmed-working builds only. `PLAN.md` content is chat-originated: chat decides roadmap, terminal writes
it verbatim. Terminal is the pen, not the author. Chat never edits any file
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
`PRODUCT.md`, `DESIGN.md`, `rhemata-status.md` — plus tooling config. Every other markdown
file goes in a folder: audits and one-off reports to `docs/audits/`, marketing
source markdown to `docs/`. A new file at root is a mistake, not a decision.
`CLAUDE.md` must stay at root — Claude Code looks for it there.
