# F3 — Ingestion-default contract: recommended policy

**Status:** RECOMMENDATION for Alex's approval. Nothing here is implemented, and this memo is not a decision. No code, schema, or DB row was touched producing it.
**Scope:** the visibility default only. Not the license gate, not `license_status`, not `retrievable`, not serving SQL.
**Date:** 2026-08-17 · **Author:** Opus, per PLAN.md F3's assigned role.
**Companion evidence:** `docs/audits/f3_visible_default_evidence_2026-08-17.md` (live-DB census run as a follow-up the same day; numbers there are more current than any cited here).

---

## 1. Load-bearing correction: F3's exit criteria name the wrong layer

F3's first exit criterion reads: *"Newly registered source classes default to `shown` under a written rule."* I read the chokepoint before drafting, and this cannot be satisfied where F3 implies it should be.

Verified in code:

- **`shared_ingest.ingest_document()` never registers a source and never writes `sources.visibility`.** It resolves an *existing* source through `source_resolver.resolve_source_id()` (alias lookup → `source_name`, then `author`, then sentinel + `ALIAS_MISS`). `resolve_source_id()` contains no INSERT. There is no visibility parameter anywhere in `ingest_document()`'s signature.
- **No backend route creates a `sources` row.** `backend/app/routers/admin.py` has `GET /sources`, `PATCH /sources/{id}`, `GET /license-sources`, `PATCH .../visibility`, `PATCH .../license-status` — no POST/create. A repo-wide grep for `INSERT INTO sources` and `table("sources").insert` returns zero backend hits.
- **Source registration lives entirely in one-off scripts**, and there are five independent hand-copied `INSERT INTO sources (name, license_status, visibility, notes)` statements, each hardcoding its own literal (see the companion evidence file §5 for exact file:line citations).
- **The schema default is `hidden`** — migration 046: `visibility text NOT NULL DEFAULT 'hidden' CHECK (visibility IN ('shown','hidden'))`, with the stated intent *"DEFAULT 'hidden' preserves the fail-closed guarantee."*

**Consequence for F3:** the visible-default policy is a *source-registration* policy, not an *ingestion* policy. The chokepoint has no visibility behavior to fix. Writing the rule into `ingest_document()` would be wrong on two counts — it would fabricate a responsibility the function does not have, and it would collide with Invariant 16, which forbids the source-ingest queue runner (a caller of this exact function) from changing visibility.

Five hand-copied literals is the same drift shape as the five-copy BOOK_MAP landmine. That is the real defect F3 should close.

---

## 2. The policy

### 2.1 The default rule (testable, not "usually")

> **A source-registration path MUST write `sources.visibility` explicitly on every INSERT. The value it writes is `'shown'` unless the source falls into a named exception class in §2.3, in which case it writes `'hidden'` and records why in `sources.notes`.**
>
> **The `sources.visibility` column DEFAULT remains `'hidden'`. An INSERT that omits the column is a defect, not a policy outcome.**

Testable form, for the implementing session's tests:

1. Every `INSERT INTO sources` in the repository names `visibility` in its column list. A registration path that omits it fails the test.
2. For a source in no exception class, the written value is `'shown'`.
3. For a source in an exception class, the written value is `'hidden'` and `notes` names the class.
4. `migrations/046`'s `DEFAULT 'hidden'` is unchanged.

### 2.2 Why the schema default stays `hidden` while the policy default is `shown`

This is the part I would most want Alex to read closely, because it looks contradictory and is not.

The two defaults answer different questions:

| | Question it answers | Correct answer |
|---|---|---|
| **Policy default (`shown`)** | A registration path made a real decision about a real source. What should it decide? | Visible — decision #12. |
| **Schema default (`hidden`)** | A row arrived and *nobody decided anything*. What should happen? | Hidden — unspecified is not consent. |

Decision #12 flips the first. It says nothing about the second, and reading it as flipping both would be a strict weakening: any future script, migration, or endpoint that forgets the column would silently publish unlicensed third-party material with no one having chosen to. There is no invariant that would catch that. Keeping `DEFAULT 'hidden'` costs nothing once every registration path writes explicitly, and it is the only backstop for a path nobody audited — including the orphaned admin PDF endpoint in §5.

This also satisfies F3's second exit criterion honestly: schema and registration paths *agree* precisely because they cover disjoint cases, and this memo is the written statement of that.

### 2.3 The exception classes — closed list

A source registers `hidden` if and only if it is in one of these four classes. The list is closed: adding a class requires a decision recorded in PLAN.md, not a judgment call at registration time.

**E1 — The sentinel source (`267a09ac-76f3-43fb-901f-3015aef88e22`).**
Stays `unlicensed` / `hidden`, permanently, and is never a registration target — no code creates it (Invariant 3). Already hard-guarded: `set_source_visibility` and `set_source_license_status` both return 403 for this ID before any validation or DB read. The visible-default must never be extended to it. No change required; stated so no future "flip everything hidden to shown" backfill sweeps it up. **A backfill that flips hidden→shown MUST exclude this ID by literal, and its test must assert that.**

**E2 — Unresolved-alias documents.** *Not actually a visibility exception — the class exists to say so explicitly.*
An unresolved alias is a *document* attribution failure, not a source registration. It has no source to register and therefore no visibility to default. It is already handled correctly and fail-closed at three layers, all verified:
- `ingest_document(allow_sentinel=False)` (the default) raises `SilentSentinelRefused` on a resolver `MISS` before anything is written.
- If a caller passes `allow_sentinel=True`, the document lands on the sentinel, which is `unlicensed/hidden` → `is_source_servable()` returns False → never served.
- `documents.source_id`'s column DEFAULT (migration 049) is the sentinel, so even an INSERT omitting the column fails closed.

Policy statement: `allow_sentinel=True` remains an explicit per-call caller choice and must never become the default, and no registration path may create a real source row to "rescue" an unresolved alias without an alias being seeded deliberately.

**E3 — Tier-2-conditioned sources.** Register `hidden`. Enumerated by name, matching PLAN.md's existing Tier 2 gate:
- SermonIndex-derived sources. ARCHITECTURE is already explicit that SermonIndex's "public domain where applicable" is intent, not a legal grant. Stays `unlicensed/hidden` until attorney review — unchanged by this memo and unchanged by decision #12.
- STEPBible-derived sources (CC-BY-NC use and attribution unaudited).
- openbible.info-derived sources (attribution surface unbuilt).

A source in E3 leaves `hidden` only by satisfying its own Tier 2 gate line item and an explicit recorded decision — never as a side effect of a backfill or a re-registration.

**E4 — Empty-shell sources.** *Recommended: NOT an exception. Register `shown` like anything else.*

I considered making empty shells (a `sources` row with zero documents) an exception and rejected it, for three reasons:

1. **It is inert.** Every user-facing surface is document-derived and independently gated: `library.py` gates each document through `is_source_servable()`; `search.py` pre-resolves servable `source_id`s and filters; `/sources` is static prose with no source listing at all. No surface enumerates `sources` rows. A shown source with zero documents renders nowhere.
2. **The empty-teacher-page risk it was meant to guard against is a copy problem, not a visibility problem.** The 2026-08-06 Bevere/Koulianos landmine was hardcoded marketing copy naming teachers with zero documents — visibility was never involved and a visibility rule would not have prevented it.
3. **Making it an exception creates a deadlock.** The source-ingest queue runner requires `is_source_servable()` to pass *before* ingesting (`processor.py` → `AttentionRequired("source_not_servable")`). An unlicensed empty shell registered `hidden` can never receive its first document, and Invariant 16 forbids the runner from flipping visibility to unblock itself. Any auto-flip-on-first-document mechanism would violate Invariant 16 directly.

Standing requirement instead of an exception: **no product surface may list a source that has zero servable documents.** That is already true in code; it should be stated so a future browse/authors feature does not break it.

*(The follow-up census in the companion evidence file §3 confirms this in practice: 13 unlicensed/shown empty shells already exist alongside 10 unlicensed/hidden ones, and both groups are equally inert today.)*

---

## 3. Reconciling decision #12 with ARCHITECTURE.md

### 3.1 The conflict is narrower than the flag suggests

ARCHITECTURE's "Standing source policy" currently contains two bullets that are already in tension with *each other*, before decision #12 enters:

- Bullet 1: *"New unlicensed sources register `hidden`."*
- Bullet 2: *"Tier-1 beta (≤20 users) has unlicensed sources deliberately `shown` as accepted risk."*

So at Tier 1 the end state for a non-exception unlicensed source is `shown` **either way**. Bullet 1 does not produce a safer outcome than decision #12 does — it produces the same outcome via a manual flip step. That intermediate step is exactly the friction that leaves new material silently invisible until someone remembers to flip it, which is what decision #12 exists to remove.

**Decision #12 therefore collapses a two-step dance into one step. It does not lower the Tier-1 risk posture, because the Tier-1 risk posture was already "shown."** The named legal exception (SermonIndex) survives untouched, because #12 flips a *default*, and a named exception is not a default.

That is the whole reconciliation. Nothing needs to be weakened for the two documents to agree.

### 3.2 The rule carries its own expiry — this is #12 implemented faithfully, not reopened

Decision #12 states its own limit: *"Safe now only because there are no users; it buys time, not a pass."* PLAN.md's private-beta convergence gate is that condition beginning to expire. The rule must therefore be written with the trip line in it, and ARCHITECTURE already names the trip line: *"At the Tier-1→Tier-2 trip line, every one goes back through the gate."*

So: **the `shown` default holds while Tier-1 conditions hold (≤~20 beta users, no public signup). At the Tier-1→Tier-2 trip line, the default for `unlicensed` sources reverts to `hidden` and every currently-shown unlicensed source is re-reviewed individually.** Writing that down is implementing #12 including its own caveat, not relitigating it.

### 3.3 Proposed replacement text for ARCHITECTURE.md's "Standing source policy"

For the docs close, replacing the current section verbatim:

> ## Standing source policy
>
> - **Registration default (Tier 1): a new source registers `visibility='shown'`, written explicitly** (CLAUDE.md Settled decision #12; PLAN.md F3). Every `INSERT INTO sources` must name the `visibility` column — an INSERT that omits it is a defect.
> - **The `sources.visibility` column DEFAULT stays `'hidden'`** (migration 046). The policy default governs a path that made a decision; the column default governs a row where nobody did. Unspecified is not consent, and this is the only backstop for an unaudited write path.
> - **Four named exception classes register `hidden`,** and only these: the sentinel source (permanent, Invariant 3, never a registration target); SermonIndex-derived sources; STEPBible-derived sources; openbible.info-derived sources. A source in an exception class records the reason in `sources.notes` and leaves `hidden` only by satisfying its Tier 2 gate line item plus an explicit recorded decision.
> - **Empty-shell sources are not an exception** — they register `shown` and are inert, because every serving surface is document-derived and gated. Standing requirement: no product surface may list a source with zero servable documents.
> - **Unresolved aliases are a document-attribution failure, not a visibility question.** `allow_sentinel=False` is the default and stays the default; sentinel-landed documents are `unlicensed/hidden` and never serve.
> - SermonIndex's "public domain where applicable" is intent, not a legal grant — it doesn't own third-party preachers' copyrights. Stays `unlicensed/hidden` until attorney review. Do NOT upgrade without legal confirmation.
> - **Tier-1→Tier-2 trip line:** at public signup or >~20 beta users, the `shown` default reverts to `hidden` for `unlicensed` sources and every currently-shown unlicensed source is re-reviewed individually. Canonical list is the live DB, never a static list here: `SELECT name FROM sources WHERE license_status='unlicensed' AND visibility='shown'`.
> - Entity consolidation lives in `source_aliases`: re-upload venues → speaker; name variants → canonical; co-authored → primary. Ruth Prince is her own entity, NOT folded into Derek Prince.

---

## 4. Explicit confirmation: nothing here touches the license gate

Stated affirmatively, per the F3 exit criterion:

- **Invariant 2's gate SQL is unchanged, verbatim.** No RPC is edited. The `EXISTS (SELECT 1 FROM sources s WHERE s.id = d.source_id AND (s.license_status IN ('public_domain','owned') OR (NOT safe_mode_on AND s.visibility = 'shown')))` predicate keeps both arms, keeps the single-read `safe_mode_on`, and gains no `IS NULL` arm. `is_source_servable()` (`backend/app/services/source_resolver.py`), the Python mirror of that predicate, is likewise untouched.
- **`license_status` is untouched.** No registration path changes what it writes; no source's rights truth changes. This memo decides a visibility default and nothing else.
- **`retrievable` is untouched.** It remains `GENERATED ALWAYS AS (license_status IN ('public_domain','owned','licensed')) STORED`, informational only, and still not read by the gate.
- **`citation_mode` is untouched.** `ingest_document()`'s default stays `'silent_context'`. A visible-default change must not tempt a builder into also flipping `citation_mode` — Invariant 7 stands: citable requires a real attributable name, and anonymous/pseudonymous stays `silent_context` permanently, including for a `public_domain/shown` source.
- **Invariant 3 is untouched and reinforced** — the sentinel's exclusion from any hidden→shown backfill is now an explicit, testable requirement.
- **Invariant 16 is untouched.** The source-ingest queue runner still never creates sources or aliases and never changes visibility, license status, or safe mode. This policy deliberately puts nothing in `ingest_document()` that would breach that.

**One real behavioral consequence Alex should approve knowingly, stated plainly rather than buried:** with the default at `shown`, a newly registered unlicensed source now passes `is_source_servable()` immediately, so material that previously stopped at the queue runner's `source_not_servable` check will now proceed, and material previously invisible in answers will now serve. The gate itself is unchanged and just as strong — more sources simply pass it. This trades a structural guarantee ("new unlicensed material cannot serve until a human flips it") for a procedural one ("a human maintains the exception list and honors the Tier-2 trip line"). That is the actual cost of decision #12, and it is the cost #12 already accepted; it is named here so approving this memo is an informed act.

---

## 5. The accepted chokepoint bypass (orphaned admin PDF upload)

**Recommendation: explicitly OUT of scope for this policy, with one exception that is already satisfied.**

Reasoning:

- This policy governs **source registration**. The bypass endpoint does not register sources. It inserts `documents`/`chunks` rows directly and, per the 2026-08-15 diagnostic, lands them on the sentinel via `documents.source_id`'s DEFAULT. There is no `sources` row created, so there is no visibility default for the policy to apply to.
- The bypass's outcome is already the safest one available: sentinel → `unlicensed/hidden` → `is_source_servable()` returns False → never served, under safe mode or not. The visible-default policy neither improves nor worsens this.
- Alex's 2026-08-15 decision was to leave the endpoint in place as a named exception, with its operability gap closed by `ec42398`. Re-scoping it into F3 would reopen a closed decision, and F3's build work does not need it.

**The one thing this policy does contribute to it, already satisfied by §2.2:** because the schema `DEFAULT 'hidden'` is retained rather than flipped to `'shown'`, this endpoint — the one confirmed unaudited write path in the codebase — cannot become a publishing path by accident. Had the recommendation been "flip the column default too," this endpoint would have been the most likely place for that to bite. It is a concrete reason the §2.2 split is the right call, not a reason to bring the endpoint into F3's scope.

*(The follow-up census in the companion evidence file §7 confirms this directly: the bypass endpoint's containment is a side effect of the sentinel staying hidden, not an independent guard — reinforcing why §2.2's split matters.)*

---

## 6. What implementation looks like (for the build session, not decided here)

F3 assigns the build to Kimi and the review to Opus. Scoping only:

1. **One shared `register_source()` helper**, in `scripts/source_resolver.py` (which already owns `SENTINEL_SOURCE_ID` and imports the canonical `normalize_alias_key`). The policy default and the E1–E3 exception check live there, once. This mirrors Invariant 6's "one shared implementation is the contract" pattern and closes the five-copy drift hazard.
2. **Repoint all five `register_*.py` scripts** to that helper. Note that `register_sermonindex_speakers.py` is an E3 source and correctly stays `hidden` — its literal does not change, but it should be `hidden` *because it is E3*, not because it hand-copied a literal.
3. **A structural regression test** asserting every `INSERT INTO sources` in the repo names the `visibility` column — the shape-based guard, in the same spirit as `scripts/test_admin_auth_regression.py`. Mutation-proven per standing practice.
4. **The hidden→shown backfill** required by decision #12's second clause ("everything currently hidden becomes visible"), excluding E1 and E3 by literal ID/name. **This is a Database-write session and routes to the plain script path, never the harness**, per CLAUDE.md's hard rule — a separate session from items 1–3, which are repo-only.
5. **A live census before and after that backfill** — `SELECT name, license_status, visibility FROM sources` — reconciled row by row. This memo deliberately cited no corpus counts when first drafted; the companion evidence file now provides a live 2026-08-17 census, but it will drift — re-run before the actual backfill rather than trusting either document's numbers by then.

---

## 7. Where I am genuinely uncertain — Alex's call, not mine

Three items. I have taken a position on each so the memo is decision-ready, but each is a product/risk judgment that belongs to Alex, and I would not treat my position as settled without a yes.

**7.1 — Whether the `shown` default should apply to `unlicensed` at all, this close to a private beta.** My position: yes, per §3.1 — at Tier 1 the end state is `shown` either way, so #12 removes friction without changing exposure. But decision #12 was made on 2026-08-01 when "there are no users" was flatly true, and PLAN.md is now converging on a beta with real people. If Alex's read is that the private beta *is* the trip line rather than something before it, then the honest rule is `hidden` for `unlicensed` starting now, and #12 has simply reached its stated expiry. **That would be #12 expiring on its own terms, not being overturned** — but it is a different rule from the one I have recommended, and only Alex can say which side of the line the private beta sits on.

**7.2 — Whether the E3 list is complete.** I derived it from PLAN.md's Tier 2 gate (STEPBible, openbible.info, SermonIndex). The companion evidence file's census (§4) surfaces one thing worth Alex's eyes here: SermonIndex-derived sources with real content aren't the only unlicensed/shown material sitting in the Tier-1→Tier-2 re-review queue — Precept Austin (2,176 docs, separately and permanently excluded from answer retrieval already), Derek Prince (496), Vlad Savchuk (126), Leonard Ravenhill (117), Zac Poonen (50), and 14 smaller sources are all there too, unlicensed/shown, none in E3. That's expected under this policy (E3 is a *legal*-risk list, not a *quality*-risk list), not a defect in it — but it's the concrete size of what "re-review at the trip line" will actually mean.

**7.3 — Whether "no product surface may list a source with zero servable documents" (§2.3 E4) should be a tested guard or just a written rule.** My position: written rule for now, because no such surface exists today and the failure mode it guards against (the 2026-08-06 Bevere/Koulianos episode) was hardcoded copy, which no test of this kind would have caught. But if Alex wants an authors/teachers browse page in the private beta, it becomes a real guard and should be tested when that page is built — not retrofitted after.

---

## 8. Approval

This memo satisfies F3's **first** exit criterion (a written visible-default rule with explicit sentinel, unresolved-alias, empty-shell, and Tier 2 exceptions) and specifies the **second** (schema/registration agreement, without weakening `license_status`, `retrievable`, or serving-gate SQL). It does not satisfy the **third** (dry run + isolated real registration pass) or the **fourth** (the ARCHITECTURE.md update) — those are build and docs-close work that follows approval. §3.3 is drafted so the docs close is a paste, not a fresh decision.

Requested from Alex: **approve / approve-with-changes / reject**, plus a ruling on §7.1, which is the only item that could change the policy's shape rather than its detail.
