# Rhemata — Live Status

Point-in-time state only. Overwritten each session. Never durable truth.
Corpus counts are not recorded here — query live.

Last verified: 2026-07-24 (claim-to-source verification check: built, tested, rejected — see directly below).
Records reconciled: 2026-07-23 (fix commit `0e2f32c` for the textarea-focus-blocks-panel bug — see the section five below the new one).

---

## Claim-to-source verification check: similarity method rejected after corpus-wide test; Bevere attribution risk found (session state, 2026-07-24)

Follow-on from the provenance-stamping work: with no mechanical check ever having verified a stored proposition against its actual source, this session built and tested one. Read-only throughout — nothing in the corpus was written, deleted, or flagged in the database.

**The similarity-based check is REJECTED as a flagging mechanism, not shelved as unfinished — a real result, not a lack of time.** Built two things: comparing a proposition's meaning against the single best-matching passage in its own document, and the same thing compared to its own document's *other* propositions (to correct for different teachers' speaking styles naturally scoring differently in absolute terms). The relative version looked genuinely promising on its first test — the one known real fabrication (Leonard Ravenhill's actual teaching, wrongly attached to a Derek Prince document about demons) scored dramatically lower than every real proposition on that same document. But run across the whole corpus and checked against real reading, not just re-tested on the one case it was built to catch: **at a cutoff loose enough to flag that real fabrication, two separately-confirmed-accurate propositions scored even more extreme than the fabrication did.** No line separates them — a stricter cutoff excludes the good ones only by also excluding the fabrication. Confirmed with real numbers, not a guess: 32 propositions across Derek Prince, Leonard Ravenhill, Zac Poonen, Vlad Savchuk, and Carter Conlon were read in full against their actual source text. 31 were genuinely accurate, faithful paraphrases that simply scored low on this method for reasons unrelated to accuracy (register mismatch, multi-passage synthesis, natural variation). Exactly one was a real, confirmed problem — Carter Conlon's proposition adding a specific chapter-and-verse citation (Matthew 7:21-23) that the speaker alluded to but never stated aloud, a real violation of the extraction prompt's own rule against supplying an unstated reference. **A coarse, whole-document version of this same signal (is this document's overall proposition set unusually disconnected from its own source, as a crude backstop against a whole document being systematically wrong) remains available at effectively zero additional cost, since the underlying numbers are already computed — but it is unbuilt and unvalidated, since no known whole-document failure case currently exists to test it against. Shelved, not built, pending Alex's call on whether it's worth the (small) engineering time for an unproven backstop.**

**What's still worth building: the check that verifies every name, number, and scripture reference in a proposition actually appears in its source.** It's the one thing that caught the real problem in the 32 read above. **But it is blind to the actual demonstrated failure this whole effort exists to catch** — the Ravenhill-into-Prince fabrication contains no checkable names, numbers, or citations at all, just a plausible-sounding claim with nothing to verify against. **No cheap check currently covers that failure class — a real, accurate claim from one named teacher, attached to a different named teacher's document.** This is the open gap. Nothing built this session closes it.

**Separately: a live, currently-uncaught guest-speaker attribution risk found in John Bevere's material, ahead of any backfill decision.** Bevere's 219 sermon documents were attributed to him purely by which YouTube channel published them ("John Bevere TV"), with no per-video speaker verification — recorded in the ingest queue itself as `channel_name → resolved_source`, automatic, no check. This is the exact mechanism that has already caused real, corrected problems elsewhere in this project. The July 16 "0a" review did cover Bevere's material — all 221 documents that existed at the time — but only by reading each document's first two chunks, and removed 2 for a confirmed co-hosted video naming Rick Renner as a joint speaker. **A title and content scan this session found a second, still-live document — "The Antichrist, Nephilim & the State of the Church w/ Rick Renner," 17 chunks, zero propositions yet — that the same review pattern should have caught and didn't.** A close sibling of the video that WAS removed (same guest, same apocalyptic-teaching format, same channel), still sitting in the corpus attributed solely to Bevere. One more candidate ("The Man Who Will Fool The Entire World Is Alive Today") shows dialogue-format language ("that's what I was going to ask you") alongside a Rick Renner citation — genuinely ambiguous from a partial read, not confirmed either way, flagged for a closer look rather than asserted as a problem. Everything else the scan surfaced (assorted "with," "interview," "joining me" hits) was checked and came back benign — Bevere referencing another teacher's work or addressing his live audience, not a co-speaker. **Net finding: the risk is real and at least one live instance of it currently exists in the corpus, unresolved, in the single largest block (219 of 781) of what's still awaiting the eventual propositions backfill.** Neither found document has been touched — no deletions, no changes, per instruction.

**Cost of a more thorough Bevere check, if wanted:** reading each full document (not just its first two chunks) and asking explicitly whether it shows signs of a second speaker, rather than the lighter check the July review used. Same rough shape and cost as the extraction step itself, just for classification instead of writing propositions — cheap in absolute terms (low single-digit dollars, well under an hour) relative to the fact that this is the largest remaining block of backfill material.

---

## Propositions provenance stamping shipped (session state, 2026-07-23)

Follows directly from the same day's backfill-scope diagnostic and fabrication sweep (recorded further below): that sweep found zero contamination in the live corpus, but only by manually searching text and reconstructing prompt history from git, because nothing recorded which prompt version or model produced any given row. This closes that gap going forward.

**What's recorded now.** Every proposition written from this point on carries three new pieces of information: a human-chosen label for which named revision of the extraction instructions was used; a fingerprint — a short digital signature computed automatically from the exact, literal wording of those instructions at the moment of the call, never hand-typed; and which AI model answered the call. **The fingerprint is authoritative whenever it and the label disagree** — deliberately, because the label already proved unreliable within this same session: today's two tuning passes both kept calling themselves "v4" while the actual instruction wording changed twice. A future investigation should trust the fingerprint, not the label, when the two don't match.

**Existing rows.** All 2,413 propositions written before this change now carry an explicit, clearly-named "unknown" marker — deliberately NOT a guess at which version actually produced them, even though today's earlier diagnostic built a reasonably strong circumstantial case for that (git history plus a corpus-wide text search). A guessed value would be worse than an honest blank, because the entire reason this field exists is to be trusted during a future investigation — and a field that sometimes contains a guess can't be trusted blindly. If a real answer is ever needed for a specific pre-existing row, the git-history/text-search method from today's diagnostic is still the way to get it — it's just not stored as a database fact.

**Where this is wired.** Every real way a proposition gets written funnels through exactly one place in the code, so stamping that one place covers the entire live pipeline — the standalone document importer, the magazine importer, the Precept Austin importer, the lexicon importer, the YouTube pipeline, and the HelloAO commentary script (currently a no-op since its sources are public domain, but fully wired and will start writing real, stamped rows automatically the moment that changes). Confirmed by a full-codebase search before building anything — no admin button, API route, or database-level automation was ever found to generate a proposition outside this one path.

**Standing expectation going forward:** any new way of writing propositions — a new ingest script, the eventual full backfill, or any code that calls the underlying storage function directly rather than through the shared entry point — must pass real values for all three fields. A write that skips this silently reopens the exact gap this closed. (This is now also recorded as a standing invariant in `CLAUDE.md`.)

**Today's throwaway 5-teacher sample-test script (used for the three tuning-pass comparisons recorded below) was deleted rather than stamped**, per Alex's instruction — its purpose was already served, and there was no reason to carry it forward as a fifth thing to maintain.

**Honesty note on how this was verified.** Rather than writing any real new proposition content to prove the mechanism works, verification used a synthetic insert-then-immediately-delete cycle through the real storage function, confirmed net-zero row change before and after. One thing worth flagging plainly: the document used for that throwaway test happened to be a Precept Austin document, picked automatically by a query that filtered for "no propositions yet" but didn't think to also exclude Precept Austin by name. Precept Austin is permanently locked out of real propositions by design — bypassing that lock wasn't the point of the test and the real lock (which lives one level up, in the normal write path, not in the raw storage function) was never touched or weakened, and the test row was fully deleted and confirmed gone. But a more careful first pick would have avoided a Precept Austin document entirely, and that's noted here rather than smoothed over.

**Migration:** applied manually by Alex in the Supabase SQL Editor, per this project's standing practice — three new fields added to the table that stores propositions, all optional, so nothing existing was put at risk.

**Open item, NOT addressed by this work — logged so it isn't mistaken for closed:** nothing in this system mechanically verifies that a stored proposition actually matches what its source document says. Today's sweep confirmed one specific, already-known bug (a leaked worked example) did not spread beyond the small test batch where it was first found — it did NOT establish that the corpus is free of other, unrelated fabrication. Worth being precise about why this matters here specifically: the one confirmed failure was real Leonard Ravenhill teaching, wrongly attributed by name to Derek Prince. A future safeguard that only checks "is this teacher's name one who was actually retrieved" would NOT have caught that — the name attached was a real, retrieved teacher's name, just the wrong one. Whatever mechanism eventually gets built to guard against this needs to check that a claim traces back to its OWN attributed teacher's material, not merely that the name belongs to someone in the batch.

---

## v4 propositions prompt — passes 2 & 3 (sentence structure, terminology rename), still NOT a backfill decision (session state, 2026-07-23)

Two more tuning passes on top of the pass-1 checkpoint recorded below, run against the identical 15-document/5-teacher sample (clear-then-write per document each time, so each pass's numbers are a clean apples-to-apples overwrite of the same set — nothing outside it touched, Ravenhill untouched).

**Pass 2 (commit `8f65f1c`) — sentence structure.** Manual review of pass 1's raw output found the likely cause of the short/inconsistent length: propositions were written as one run-on sentence chaining claims with repeated "and that... and that...". Added an explicit 2-4-sentence requirement plus a thin/run-on/well-formed contrast example. Result: grand mean word count barely moved (65.1 words vs pass 1's 62.2), but sentence structure genuinely improved for most documents (avg 2-3 sentences, matching the target). **Found a serious unplanned bug while reviewing pass 2's output: in 4 of the 15 documents (Prince, Deere ×2, Kreighbaum), the model's first proposition was a near-verbatim copy of the prompt's own concrete worked example** ("{Teacher} teaches that prayer matters more than preaching...") with only the speaker's name swapped in — fabricated content wrongly attributed to a real teacher, a direct four-corners violation.

**Pass 3 (commit `5bc4916`) — terminology rename + leakage fix.** Alex's hypothesis: the word "proposition" carries a strong competing RAG-literature meaning (atomic/minimal/indivisible single-fact statement — Chen et al. 2023) that fights the 80-150-word, multi-sentence, voiced target. Renamed all model-facing prose to "teaching passage"/"passage" (the JSON output key `proposition_index` deliberately left untouched — structural, not prose, per instruction). Also fixed pass 2's leakage bug by replacing the concrete worked example with a bracketed structural template that has no real sentence left to copy.

Result, reconciled directly against the DB (one document needed a manual retry — see below): **15 documents, 107 propositions, grand mean 70.7 words** — the best of the three passes, though still under the 80-150 floor. Per-teacher averages: Jack Deere 83.4 (now the strongest teacher, was weakest in pass 1), Doug Kreighbaum 75.9, Charles Simpson 66.9, Derek Prince 66.4, Daniel Kolenda 61.7. **Leakage bug: zero instances across all 15 documents** — confirmed fixed.

**Operational finding, not prompt-quality: one genuine transient failure.** Derek Prince's "Deliverance And Demonology" hit a JSON parse error on the first pass-3 attempt (`Expecting ',' delimiter`) — a Groq generation glitch, not a systematic issue. Because `store_propositions()` only runs on a successful extraction, the failure silently left pass 2's *stale, leak-contaminated* propositions live in the table for that one document, masquerading as current data until caught by re-querying and cross-checking timestamps. A manual retry (same script, same doc) succeeded on the first attempt and produced clean pass-3 output. **This is worth carrying into the eventual full backfill (#17): a failed extraction currently leaves old data in place rather than either blocking or clearing it — fine for a hand-verified sample where the discrepancy gets caught, but worth deciding on purpose for an unattended batch run.**

**New finding pass 3 surfaced: the run-on ban is not universally obeyed.** Two of the 15 documents reverted to full run-on structure despite the explicit ban — Daniel Kolenda's "Cessationism 5" is still built from literal "and that... and that..." chains (the exact banned pattern), and Doug Kreighbaum's "Leadership in the House of God" produces one 100-120-word sentence per passage using different connective tissue ("as seen in... where... and as described in...") to route around the letter of the rule while keeping its run-on spirit. The other 13 of 15 documents show genuine 2-4-sentence structure. **Net read: real improvement, not a full fix — the underlying tendency to chain rather than segment is suppressed most of the time, not eliminated.**

**Voice and specifics — held up across all three passes, no regression from the rename.** Named-speaker attribution stays 100% (zero "the author" across all runs). Concrete names/numbers/citations (David Hume, Benjamin Warfield, Jack Deere's son, Charles Simpson's "seven practical steps") continue to survive paraphrase. Per-teacher voice stays distinct.

**Not decided by this session:** whether v4 proceeds to full backfill (#17), gets a fourth tuning pass, or is discarded. Alex has not yet reviewed raw sample output himself.

---

## v4 propositions prompt — pass 1, 5-teacher sample checkpoint (session state, 2026-07-23)

Ran `scripts/sample_v4_propositions_2026-07-23.py` (commit `07d53ee`) — a throwaway, standalone script, not a change to `propositions.py`/`shared_ingest.py`/`ingest.py` — against 15 documents across 5 teachers currently at zero propositions: **Derek Prince** (3 docs), **Daniel Kolenda** (3), **Jack Deere** (3), **Doug Kreighbaum** (3), **Charles Simpson** (3). Selected specifically for stylistic contrast from each other and from Ravenhill (already validated separately, 766 propositions live). Wrote real rows through the same `extract_propositions()`/`store_propositions()` every ingest script uses — reconciled directly against the DB post-run: 15/15 documents stored, 0 errors, 114 propositions, all 5 sources confirmed to have had zero propositions before this run.

**Named-speaker attribution and specifics-preservation — both hold up.** Zero instances of "the author" across all 114 propositions (grep-confirmed). Concrete names/numbers/scripture citations survive per teacher (e.g. Kolenda naming David Hume and Benjamin Warfield by name and characterizing their actual arguments; Deere's account of his son's death; Simpson's "seven practical steps"). Voice reads as genuinely distinct teacher-to-teacher — Kolenda combative/polemical, Deere testimonial, Kreighbaum textbook-structured, Simpson pastoral/relational, Prince systematic-doctrinal.

**Length target (80-150 words) is NOT reliably met.** Grand mean across all 114 propositions: **~62 words** — below the low end of the stated target. Per-teacher averages: Prince 76, Simpson 65, Kolenda 57, Deere 58, Kreighbaum 55. One single document — Kreighbaum's "Ministry of God's Word: Speaking, Preaching and Teaching" — averaged **40.3 words**, matching the exact pre-retune defect the v4 prompt was built to fix.

**New, narrower framing pattern, not caught by the original bug report.** All 114 propositions use an explicit attributive opener — "{Teacher} teaches/argues/explains/emphasizes/shares/warns/criticizes that..." or "According to {Teacher}..." (grep-confirmed, 0 exceptions). The v4 prompt explicitly permits dropping the attributive frame entirely for direct-voice statements (its own worked example: "Prayer matters more than preaching, because...") — that option was never exercised in this sample. Reads as a smaller, more varied version of the original "the author teaches that" problem, not a full fix of the underlying pattern.

**Not decided by this session:** whether v4 proceeds to full backfill (#17), gets iterated again, or is discarded. Alex has not yet reviewed the raw sample output himself.

---

## Chat input: shine-border/holy-glow removed (session state, 2026-07-23)

Alex asked for the glowing gold border effect on the chat input removed, keeping the normal border. The effect was actually two stacked pieces (`frontend/app/globals.css`): an animated warm-gradient shimmer ring (`.shine-border::before`, ramping in on hover/focus-within) and a separate pulsing box-shadow halo (`holy-glow` keyframes, only while `streaming`). DESIGN.md documented both together as the product's one deliberate "Signature Flourish," so scope was confirmed with Alex before touching anything — **both removed entirely**, not just the streaming pulse, per his choice.

**Changed:** `chat-input.tsx` — dropped the `shine-border`/`streaming` classes from the input container (now plain `rounded-2xl border border-border bg-card`), removed the now-unused `streaming` prop from `ChatInputProps` and the `cn` import. `page.tsx` — dropped `streaming={chatLoading}` at both call sites (empty-state and active-conversation input), since that was its only consumer. `globals.css` — deleted the `.shine-border`/`holy-glow`/`shimmer` rules and keyframes outright (grepped repo-wide first — confirmed zero other usages outside `.next` build cache). `DESIGN.md` — removed the now-inaccurate "Signature Flourish — Shine Border" section describing a feature that no longer exists, rather than leaving stale doc alongside the removal.

**Verified live (Playwright, against the already-running local dev server on port 3000, not restarted):** at the real chat input (`/`, guest empty-state), computed `box-shadow` is `none` and there's no `::before` overlay at rest, on hover, and while focused (typing) — all three states identical: plain `1px solid` `border-border`-colored outline, no shimmer, no pulse. Screenshots at rest and focused confirm visually flat borders. `tsc --noEmit` clean. Pre-existing, unrelated lint findings in `page.tsx` (an unused `UsageRing` import, two `set-state-in-effect` warnings at lines 130/356) and a CORS console error against the production `/study/teachers` endpoint were confirmed via diff to be outside this change's two touched lines — not introduced here.

**Reconciliation.** Four files touched: `frontend/components/rhemata/chat-input.tsx`, `frontend/app/page.tsx`, `frontend/app/globals.css`, `DESIGN.md`. One commit, per instruction.

---

## Landing page footer: Product list now reflects available-now vs coming-soon, standalone Study retired from footer (session state, 2026-07-23)

Resolves open question #3 logged in the "Chat-only beta" session entry further down this file ("The landing page footer's 'Product' link list still lists 'Study'/'Discover' as labels... copy decision, out of scope, per instruction") — that footer copy decision is now made.

**Change, frontend-only, `frontend/app/home/page.tsx` (footer's "Product" `<ul>` only):** "Study" removed as a standalone footer item — permanently, not deferred; the in-chat Study Panel (verse cards, word study, teacher cards, Pastors' Notes) supersedes standalone Study, and no footer link points to a standalone Study route. "Chat" stays available-now, now carries a sub-line ("Study tools built into every conversation") communicating that Bible study tooling lives inside the chat experience, not a separate destination. "Pastors' Notes" stays available-now, grouped directly under Chat, now carries a sub-line ("A small, growing collection") — accurate about the current small note count without overselling or apologizing. "Discover" moved to a visually distinct coming-soon treatment: a non-link `<span>` (no href, not focusable, no hover state), muted color, with a small rounded-full "Coming soon" tag — reuses the same treatment already shipped at `weekly-limit-card.tsx`'s billing-disabled state rather than inventing a new pattern, and matches DESIGN.md's "pills/badges: rounded-md or rounded-full for tags only" rule.

**Explicitly untouched, per instruction:** `NEXT_PUBLIC_FULL_NAV_ENABLED` and all navigation-gating/routing logic; the landing page's `MockSidebar` illustration (still shows Study/Discover, still stale — a separately logged, later design pass, not this one). Chat and Pastors' Notes both still link to `/` — the same pre-existing placeholder href noted (not fixed) in the Chat-only-beta entry further down; out of scope for this copy/markup-only change.

**Verified live, real browser (Playwright, against the local dev server already running on port 3000 — not restarted):** at both 1440×900 and 390×844, the Product list renders exactly three items — Chat (+ sub-line), Pastors' Notes (+ sub-line), Discover (+ "Coming soon" tag) — no "Study" item, confirmed by reading the live DOM, not just the diff. Chat and Pastors' Notes confirmed as real `<a href="/">` elements with a working hover color transition (computed `color` genuinely changed on hover, not just a class name check). Discover confirmed as a `<span>` — zero `<a>` elements inside its `<li>`, not keyboard-focusable (`tabIndex` not ≥0) — so it cannot be clicked or tabbed to. Screenshots taken at both widths confirm no overflow or awkward wrapping.

**Reconciliation.** One file touched: `frontend/app/home/page.tsx` (footer Product list only, confirmed by diff — no other line changed). One commit, bundling this status update with the code change per this session's own instruction — a deliberate exception to the usual separate build/records-commit pattern used elsewhere in this file.

---

## Mobile study panel: swipe-to-close + bottom safe-area, Phases 0-3 (session state, 2026-07-23)

A read-only audit of this surface ran immediately before this session and is not re-litigated here (its findings were treated as current, verified only where a phase called for it). Two independent, narrowly-scoped fixes to the mobile sheet, one commit each.

**Phase 0 confirmed all three pre-build facts directly from the code** (not from the audit's memory of it): the grab handle at `study-panel.tsx` renders only under `{isMobile && (...)}`, structurally unreachable on desktop; the single shared close path (`Root`'s `onOpenChange` → `onClose` prop) was intact; the handle's existing tap-to-close (`PanelPrimitive.Close asChild`) worked as described. No stop triggered.

**Phase 1 (`ee351bb`) — swipe-to-close, deliberately reduced from roadmap #43.** #43's written spec describes drag-to-follow (the sheet tracks the finger) with chat peeking mid-drag underneath. **This is NOT what shipped, and #43 is NOT met as originally written.** What shipped: pointer-event tracking on the grab handle only (not `Content`, not `PanelBody`, not either scrollable region) — a downward release past a 44px threshold (matching this codebase's existing min-touch-target convention, not a new number) calls the exact same `onClose` every other close path already uses. Below threshold, or upward: true no-op — no animation, no snap-back, the sheet never moves. **Reason for the reduction, stated plainly:** the fuller drag-to-follow spec cannot be honestly verified without a physical touchscreen (a still-image drag position can be faked by nudging DOM style in a script; a discrete "did it close or not" outcome from a real dispatched touch sequence cannot), and per the pre-session audit would very likely require either a new gesture-tracking dependency or re-platforming this sheet onto a different drawer library (e.g. `vaul`) to get physics-correct follow behavior — both explicitly out of this session's "no new dependencies" rule. **Whether the remainder of #43 (drag-to-follow, chat-peek) stays open as future work, or the reduced scope shipped here is considered the closing word on #43, is Alex's decision — NOT YET MADE as of this record.** The grab handle itself was not new: it already existed with tap-to-close and a code comment explicitly marking drag as a deferred follow-up (`"drag-to-dismiss is a follow-up (no drag dependency in this project yet)"`) — this session completed that exact follow-up, at the reduced scope above, not a new feature invented from nothing.

**Phase 1's hard constraint held:** `handlePointerDownOutside`, `handleFocusOutside`, and `onCloseAutoFocus` on the shared `Content` element — the mechanisms behind Escape, outside-click, and swap-in-place, all three desktop-reachable — were not touched, confirmed by diff. The gesture handlers live entirely on the mobile-only handle button.

**Phase 1's REAL STOP — desktop regression check — passed with real evidence, not inference.** Re-ran the same real-browser test suite from the prior (geometry v3) session: Escape closes (0 open dialogs after); outside-click closes (0 open dialogs after); swap-in-place shows the same DOM node before/after a second-reference click, zero `data-state` transitions through `"closed"` via a live `MutationObserver` (no close-then-reopen flicker). All three PASS, matching the prior session's own results exactly — no drift.

**Phase 1 mobile self-verify used genuine touch emulation, not mouse events standing in for touch** — Chromium's CDP `Input.dispatchTouchEvent` for real multi-phase touch sequences, `hasTouch: true` browser context. All six checks (a–f) passed: swipe down past threshold closes; a swipe clearly-a-drag but below threshold is a true no-op (dialog bounding box byte-identical before/after, not just "still open"); swipe up does nothing; a tap still closes; dragging to scroll inside BOTH the main row view and the word-study sub-view does not close the sheet (the critical scroll-vs-swipe check, the one this whole gesture design exists to get right); the X button still closes.

**Phase 2 (`eb0ad36`) — bottom safe-area clearance, a deliberate bounded exception to the no-bundling rule, not drift.** Pre-existing, independent of the swipe work: `Content`'s `pt-[env(safe-area-inset-top)]` had no bottom equivalent, and `Content` is `inset-0` (extends to the true viewport bottom), so scrolled-to-end content could sit in the home-indicator strip. Fixed by composing `env(safe-area-inset-bottom)` directly into the padding of both scrollable regions (main row view + word-study sub-view) — not an outer static wrapper, since clearance has to live IN the scrolled region for reaching max-scroll to actually clear the indicator. Both divs are shared, unbranched, with desktop — confirmed by diff that only the className changed — where `env()` naturally resolves to `0` and the computed value degrades to exactly today's `16px`, unchanged.

**Phase 2 verified with genuine notch emulation, not a guessed inset number** — Chromium CDP `Emulation.setSafeAreaInsetsOverride` (`top: 59px, bottom: 34px`, an actual iPhone-shaped inset). Computed `padding-bottom` = `50px` (16px + 34px), confirmed. Scrolled to true max-scroll in the realistic **as-shipped default-open state** (Interlinear open, matching what a fresh panel open actually renders): last content element's bottom edge sits at 707px, well clear of the 810px indicator-zone start. Word-study sub-view behaves identically. Desktop re-confirmed unchanged at exactly 16px. A screenshot confirms real, visible margin below the last accordion before the screen edge.

**NEW FINDING, discovered during Phase 2 verification, NOT fixed this session — pre-existing, unrelated to either Phase 1 or Phase 2's own changes, reported per this project's standing honesty practice rather than smoothed over.** The mobile sheet's scrollable container can grow past the true viewport's fixed bottom edge when enough accordion content is expanded simultaneously — confirmed directly: with only the default Interlinear section open, the container correctly stays within the 844px viewport (`bottom: 844`, exactly at the edge, no overflow). With Commentaries and Pastors' Notes ALSO expanded (even with near-empty mock content), the same container's own `getBoundingClientRect().bottom` grows to `872px` — **28px past the true screen edge**, into space that does not exist on a real device. This is the classic Tailwind flex-overflow trap: a `flex-1 overflow-y-auto` child without `min-h-0` on itself or an ancestor defaults to `min-height: auto`, which can grow to the intrinsic content height and break out of its flex parent's allocated space instead of clipping and internally scrolling. `Content` itself has no `overflow-hidden` to catch this, so when it triggers, content genuinely renders below the visible screen — unreachable, not just improperly padded. **Because this session's padding fix (Phase 2) lives on the same growing container, it does NOT protect against this case** — no amount of internal padding helps once the container itself has broken out of the viewport's true bounds. Confirmed via direct DOM measurement (`getBoundingClientRect()`, CDP-verified notch emulation), not assumed. Out of scope for this session's explicit no-bundling rule (Phase 2 was safe-area padding only, not flex containment) — flagged here as a new, real, unfixed defect for a future session, not silently absorbed into Phase 2's "done" claim.

**HONESTY BAR, unsoftened.** Browser device mode with CDP-dispatched touch events genuinely exercises real touch semantics — multi-phase `touchstart`/`touchmove`/`touchend` sequences, real gesture recognition by the browser engine, not synthetic mouse-event substitutes. **The swipe gesture itself IS meaningfully verified** by this method — this is a materially different and stronger claim than "I read the code and it looks right." Equally plainly: **no physical device was used anywhere in this session.** Bottom safe-area clearance is verified against Chromium's CDP-level safe-area-inset override, which produces a real, correct `env()` value for the CSS engine to resolve against — but it is still emulation, not hardware, and remains unproven on a real notched iPhone, exactly as it was for the two prior mobile-adjacent sessions (chat-only-beta gating, Study Panel geometry v3) that logged the same caveat. Nothing in this session closes that hardware gap; it only adds one more layer of increasingly faithful emulation on top of it.

**Reconciliation.** Files touched, confirmed by `git diff --stat` across both build commits: `frontend/components/rhemata/study-panel.tsx` only. Commits, each confirmed landed by `git show --stat` immediately after committing: `ee351bb` (Phase 1, swipe-to-close), `eb0ad36` (Phase 2, bottom safe-area). This records entry is its own separate commit, after both build commits. **Push state, reported not acted on:** `main` is already 7 commits ahead of `origin/main` before this records commit (`ee351bb`, `eb0ad36`, plus the 5 already-ahead commits from the two prior sessions today — the textarea-focus fix and its own records commit, plus the Study Panel geometry v3 session's three commits) — will be 8 once this commit lands. None of today's work has been pushed yet.

---

## Study Panel geometry v3: nested-in-card, capped reading column (session state, 2026-07-23)

**This is the THIRD geometry for this surface, and it REPLACES the previous one — it is not a refinement of it.** History: floating overlay (`bb5cdc0`, zero layout shift, panel covers the chat) → side-by-side chat-narrowing (`d2c31e1`, panel reflows the chat card via `main`'s padding-right) → **now: nested-inside-card with a capped reading column.** Why the replacement, stated plainly: both earlier versions made the reader pay a cost every time the panel opened — the floating overlay covered content outright, and the chat-narrowing version compressed the reading text to a variable, panel-dependent width. This version spends *reserved margin* instead: the reading column is capped at a fixed width whether or not the panel exists, and the panel takes the slack that was already being left empty. Validated in a static mockup at real laptop width before this session; the exact numbers below came from that mockup and were implemented verbatim, not re-derived.

**Exact geometry shipped:**
- Chat reading column: `max-w-2xl` (672px), centered, `px-4 md:px-12` (~48px desktop gutter) — DESIGN.md's existing reader-content pattern, applied to chat. Desktop only; mobile (`px-4`) unaffected.
- Panel: rendered as a real DOM child inside the chat card (not a portal-to-`document.body` overlay), separated by a single `border-left: 1px solid`. No outer gap, no second rounded corner, no separate shadow — the card's own `rounded-xl`/`border`/`overflow-hidden` clips and unifies both.
- Panel width: `clamp(340px, calc(100% - 720px), 440px)`, `100%` = the card's own inner width.
- Panel background: flat, matches the card (`bg-background`, unchanged token). Section cards inside (Interlinear/Commentaries/Pastors' Notes) keep their existing `bg-popover` treatment — untouched, confirmed by not touching `PanelBody` at all.
- Transition: 300ms, same duration as before, now driving the slot's `width` (0 ↔ the clamp formula) instead of `main`'s `padding-right`.

**The permanent, deliberate tradeoff:** with the panel closed, the chat column no longer fills the available card width — there's now visible empty margin on a wide viewport, which is exactly the space the panel occupies when open. Accepted on purpose; this is what makes the open/closed transition genuinely zero-reflow for the reading column, the whole point of this rebuild.

**How it was built (`f120fff`, `b18fca9` — both local, not yet pushed, see reconciliation at the end):** Phase 1 applied the reading cap to `app/page.tsx`'s message list, empty-state composer wrapper, and `chat-input.tsx`'s own form — all three already shared one measure, kept that way. Phase 2 restructured the chat card into a flex row (chat region | panel slot) and redirected `study-panel.tsx`'s Radix `Portal` to mount into that slot via its `container` prop, instead of the Radix default (`document.body`). This was the key design decision: desktop keeps using **real Radix `Dialog.Content`** — only where its Portal mounts and how `Content` is styled changed — so every primitive-provided behavior (Escape, outside-click dismiss, the swap-in-place suppression, the `Title`/`Description` aria wiring) stayed intact automatically, with zero reimplementation. Mobile's branch (`Root`/default-`Portal`/`Overlay`/`Content`) was not touched at all.

**Phase 0 behaviour list** (carried forward for Phase 3 to verify against): (a) Escape closes the panel — primitive-provided, no override in this file. (b) Outside-click closes it — primitive base (`DismissableLayer`) + a hand-written exception for `data-study-trigger` elements. (c) Second-reference swap-in-place — hybrid: the swap itself is plain app state, but only works because the primitive's default dismiss is suppressed for trigger elements. (d) Focus/keyboard/aria — mostly primitive (`Title`/`Description` auto-wire `aria-labelledby`/`describedby`; `role="dialog"` is automatic), with one hand-written override (`onCloseAutoFocus`, since this panel has no `Trigger` for Radix to restore focus to by default).

**Phase 3 result, per behaviour, with evidence (real headless-browser interaction against the local dev server, `/chat` intercepted with a shape-accurate SSE test double — same established pattern as Phase 2's own verification):**
- **(a) Escape — PASS.** Opened via a real click, pressed Escape, confirmed zero `[role="dialog"][data-state="open"]` elements remained.
- **(b) Outside-click — PASS.** Opened, clicked empty chat-card background (not a trigger), confirmed zero open dialogs afterward.
- **(c) Swap-in-place — PASS, strongest evidence of the three.** Mocked an answer with two distinct verse references. Tagged the actual `Content` DOM node before clicking the second reference, confirmed it was the *exact same node* afterward (no unmount/remount). A live `MutationObserver` on the node's `data-state` attribute recorded **zero transitions** during the swap — it never touched `"closed"`, let alone flickered. Title text correctly moved from one reference to the other in place. This is the exact mechanism that broke twice in production before this session (see the pin-dropdown-closes-panel entry below) — confirmed intact after the restructuring.
- **(d) Aria wiring — PASS.** `role="dialog"` present; `aria-modal` correctly absent (non-modal); `aria-labelledby`/`aria-describedby` both resolve to real, correct live text.
- **(d) Focus restoration — FAIL.** See Open Blocker below.

**Phase 0 self-correction, logged as a correction, not a restatement:** Phase 0 reported that the non-modal desktop panel (`modal={false}`) has "no automatic focus trap." That claim was inferred from reading the prop, not from testing it, and it was **wrong**. Direct testing — 25 real Tab presses — showed focus looping indefinitely within the dialog (Close → Interlinear → Commentaries → Pastors' Notes → Pin → Close → ...), never once escaping. Radix evidently loops Tab navigation within `Content` regardless of `modal`. This is reasoned, not re-verified against the pre-session baseline, to be pre-existing rather than something this session's Portal-container change caused — React effect/focus-scope behavior is a function of the component tree, not where its DOM output is portaled — but that reasoning has not been empirically confirmed the way the textarea-blur bug below was.

**Open Blockers — both real, both confirmed pre-existing, neither caused by this session. Evidence levels differ; not flattened into one claim:**

- **BLOCKER — panel fails to open when the chat textarea has focus. BETA-BLOCKING. FIXED same day, commit `0e2f32c`.** Clicking a verse/teacher reference while the chat textarea is focused silently does nothing — no panel opens, no error. Traced with full event instrumentation: `pointerdown` → `mousedown` → `focusout` (textarea) fire, then **nothing** — no `mouseup`, no `click`, no `focusin` on the reference button. **Real root cause, found by tracing DOM node identity across the click, not by guessing again:** `react-markdown`'s default `<Markdown>` component recreates its whole processor and output from scratch on every render, unconditionally (confirmed directly from its own source via Context7 — `createProcessor()` runs fresh every call, no internal memoization for the sync export). `ChatMessage` was never memoized, so any unrelated ancestor re-render — including `ChatFocusContext`'s `inputFocused` toggling on the textarea's blur — remounted every rendered message's DOM, including the verse/teacher reference `<button>`s nested inside paragraphs. A direct DOM-node-marker check proved this: the button element was **destroyed and replaced** between mousedown and mouseup, so the browser had no valid click gesture left to complete — not a timing race (confirmed by testing 0-200ms artificial delays between mousedown/mouseup, all failed identically). Original hypothesis (blur handler racing the click) was directionally right but incomplete; the actual mechanism is this remount. **Fix:** wrapped `ChatMessage` in `React.memo`, plus `useCallback` on `handleCitationClick` (`page.tsx`) so it stays reference-stable — required for the memo's shallow prop comparison to actually hold. Verified: the delay-matrix repro now succeeds at every delay; the button survives the blur-triggered re-render (direct marker check); the full Phase 3 behavior suite (Escape, outside-click, swap-in-place with `MutationObserver` evidence, aria wiring) re-run clean; the panel geometry regression suite re-run clean, no side effects; citation-click path independently re-verified against the real `Citation` shape. **Confirmed pre-existing via an isolated git worktree** at `a60cc22` before the fix was written — identical repro, identical failure signature, on code neither the beta-nav nor the geometry session touched.
- **BLOCKER — focus restoration on panel close lands on `<body>`, not the trigger. CLOSED as a side effect of the fix above, same commit `0e2f32c` — confirmed, not assumed.** Original hypothesis (`previouslyFocusedRef` capturing the wrong element due to effect-ordering) was reasoned, not proven, per this entry's own original text. Re-ran the exact same focus-restoration test after the `React.memo` fix above: **it now passes** — closing the panel correctly returns focus to the original trigger button. Since the button element is no longer destroyed/recreated mid-interaction, `previouslyFocusedRef` now captures and restores the correct, stable node. The original effect-ordering hypothesis for this specific blocker was not independently re-confirmed as the mechanism — it's reported as fixed on the strength of the before/after test result, not a proven causal chain distinct from the node-replacement fix above.

**HONESTY BAR.** Phase 3 used real browser interaction and live DOM inspection — a materially stronger verification standard than the previous session's (chat-only-beta gating), which relied on `curl` against SSR HTML plus diff review with no real browser at all. Say what was still *not* done, equally plainly: no physical device was used at any point; no screen reader (VoiceOver/NVDA) was run; and the two keyboard findings above (Tab-loop, focus-restoration) were reasoned to be pre-existing but **not** independently re-verified against the pre-session baseline the way the textarea-blur bug was — that specific distinction matters and should not be flattened into "everything here was confirmed against baseline."

**Reconciliation.** Files touched, confirmed by `git diff --stat` across both build commits: `frontend/app/page.tsx`, `frontend/components/rhemata/chat-input.tsx`, `frontend/components/rhemata/study-panel.tsx`. Commits, each confirmed landed by `git show --stat` immediately after committing: `f120fff` (Phase 1, reading-width cap), `b18fca9` (Phase 2, nest panel inside card). No Phase 3 commit — verification only, no code changed. This records update is commit-separate from both build commits, per the session's own rule. **Push state, reported not acted on:** `main` is 2 commits ahead of `origin/main` (`f120fff`, `b18fca9`, plus this records commit once made) — none of this session's work has been pushed. The prior session's chat-only-beta commits (`b531215` through `893bf0b`) **were** pushed before this session began — this work was built on top of pushed, not unverified-and-unpushed, prior work.

---

## Chat-only beta: gate Study/Discover navigation, Phases 0-5 (session state, 2026-07-23)

Ships a chat-only beta: Study and Discover become unreachable from the UI on every platform, behind one reversible flag. Routes/pages/components/data untouched — only the ways in were removed. Two prior read-only audits (mobile drawer clipping bug, then entry-point mapping) ran earlier this session and are not re-litigated here; this is the build.

**The switch — `NEXT_PUBLIC_FULL_NAV_ENABLED`, `frontend/lib/chat-only-beta-flag.ts`.** `isFullNavEnabled()` returns `process.env.NEXT_PUBLIC_FULL_NAV_ENABLED === "true"` — **defaults to the beta (hidden) state when unset**, inverse of `study-panel-flag.ts`'s convention, so production ships correctly with zero env change. Set the var to `"true"` to restore full navigation exactly as it was.

**Phase 0 (read-only) found real risk and stopped the session, as designed.** Grepped the whole frontend for `env(safe-area-inset-top)`/`.pt-safe`: zero matches anywhere — nothing in this codebase had ever compensated for a top inset. Four elements sit flush at the true device top with no such compensation: the landing page's `fixed top-0` nav (`app/home/page.tsx`), the chat page's floating circular drawer-open button (`app/page.tsx`, the *only* way to open the drawer once the tab bar is gone), the study panel's mobile close control (`study-panel.tsx`), and the mobile drawer's wordmark/close row (`sidebar.tsx`, already a non-safe-area-aware fixed 24px). Session halted per its own contract — one designated stop — rather than shipping `viewport-fit=cover` with this unreviewed. Alex reviewed and chose to fold the fix into Phase 4 rather than defer the switch: deferring would have meant Phases 2-3's new bottom clearance silently resolves to zero on physical devices (no `viewport-fit=cover` → `env()` always falls back to `0px`), leaving the original drawer-clipping bug from the first audit **still unfixed** in production. Folding it in was the only path that actually closes that bug this session.

**Phase 1 (`b531215`) — the flag + all six entry points, one commit.** Gated: `mobile-tab-bar.tsx`'s Study and Discover tabs (Chat tab stays, via a `requiresFullNav` filter); the *entire* desktop sidebar nav block in `sidebar.tsx` (`hidden md:block`, all three links including Chat — with Study/Discover gone there's nowhere else to navigate to, so a single always-active Chat link is dead weight; flag-on restores all three unchanged); the landing page's "Study" nav-bar link and "Explore Study →" CTA (`app/home/page.tsx`). `isDiscover` checked and left alone — still referenced inside the (flag-on-preserved) Discover link, never became genuinely unused. Verified: default state confirmed live via `curl` against the already-running dev server on port 3000 (all six doors absent from rendered HTML); flag-on state confirmed by diffing every preserved branch against pre-edit `git show` — byte-identical, wrapped not altered.

**Phase 2 (`3194966`) — gate the whole tab bar, fix its dead spacing.** `MobileTabBar` now returns `null` outright in beta state (Phase 1 alone would have left a Chat-only single-tab bar). Chat page's bottom padding (`app/page.tsx`) no longer reserves 56px for a bar that isn't there — beta state uses `pb-safe`; flag-on is byte-identical to today's `inputFocused ? pb-0 : pb-14` toggle. `useChatFocus` itself untouched, per instruction — the chat page still reads `inputFocused`, just only in the flag-on branch now. Verified live via curl: default state's chat `<main>` carries `pb-safe`, not `pb-14`/`pb-0`.

**Phase 3 (`d1a0be2`) — drawer footer clearance, unconditional.** This is the fix for the bug the first audit found: the account row / sign-in button had zero bottom offset in *either* flag state. New mobile-scoped CSS (`.pb-drawer-footer-safe`, `.pb-drawer-footer-safe-tabbar`, both inside `@media (max-width: 767px)` — matching `use-mobile.ts`'s own breakpoint) composes the tab bar's existing 56px with `env(safe-area-inset-bottom)` rather than guessing a new number. Had to be media-query-scoped, not just unlayered like the existing `.pb-safe`: this footer div is shared markup between the desktop aside and the mobile drawer, and per this codebase's own documented CSS fact (see the iOS-input-zoom-fix comment already in `globals.css`) unlayered rules beat Tailwind utilities *unconditionally*, regardless of media query — without the 767px wrapper this would have shrunk the **desktop** sidebar's `pb-4` too, an unreviewed visual change nobody asked for. Verified live: default state's footer div carries `pb-drawer-footer-safe` (confirmed via curl, both the desktop-aside and mobile-aside render paths). Signed-in vs. signed-out not independently live-tested — same div/class applies to both by construction (`isLoggedIn` only swaps the children, never the wrapper's className), and this session had no backend to authenticate against.

**Phase 4 (`eebbf32`) — `viewport-fit: "cover"` + all four Phase 0 fixes, one commit.** Landing nav: `h-14` became the *content* box via `pt-[env(safe-area-inset-top)]` plus a matching height increase, so the logo/links/CTA sit at today's exact visual position — only the translucent background now extends up under the notch. Floating menu button: `top-3` → `top-[calc(0.75rem+env(safe-area-inset-top))]`, same reasoning. Study panel close control: `pt-[env(safe-area-inset-top)]` added to the mobile-only branch of its className (desktop's floating card, which never touches the top edge, is untouched). Drawer top block: `pt-6` → `pt-[max(1.5rem,env(safe-area-inset-top))]` — **not additive**, per instruction — so it's pixel-identical to today wherever the real inset is ≤24px, and only grows on devices where 24px genuinely wasn't enough. All four degrade to their exact current value when the inset resolves to `0` (desktop, non-notched phones) **by construction of the CSS**, not by assumption. Verified live via curl: the viewport meta tag now reads `viewport-fit=cover`; all four elements' new classes/styles render exactly as written; Phases 2-3's classes re-confirmed still present and unbroken now that insets are live.

**Standalone Study vs. Discover — different lifespans, one shared switch, logged as ARRIVED not decided.** This session's framing (Study hidden because the in-chat panel now supersedes it; Discover hidden because it's simply unfinished) is the first real arrival of the long-flagged "does standalone Study survive" founder checkpoint referenced in this file's Study Panel history. Nothing was decided about Study's page ever being deleted — it stays live, fully functional, reachable by direct URL/bookmark, its `isStudy`-gated Saved Words sidebar content untouched — this session only removed the navigational doors, per the explicit "hidden not deleted" brief. Whether standalone Study is ever formally retired is a separate, future decision.

**Open, logged, deliberately NOT done this session (per explicit scope lock):**
- Dead static `pb-24` bottom-padding reservations on `app/study/page.tsx`, `app/library/page.tsx` (×2), `app/library/authors/page.tsx` — these pages are nav-unreachable in beta, so a stale bar-height gap on them was accepted rather than fixed.
- `useChatFocus`'s `inputFocused` value is now read by only one real consumer (the chat page's flag-on padding branch) instead of two — the tab bar's own use of it disappeared with the bar. Provider, hook, and `chat-input.tsx`'s focus/blur handlers all untouched, exactly as instructed.
- The landing page's `MockSidebar` illustration (`app/home/page.tsx`) still visually shows Discover/Study as mock nav items — cosmetic only, contradicts the real product now, logged as a future design pass.
- The landing page footer's "Product" link list still lists "Study"/"Discover" as labels (though both already pointed at `/` pre-session, a separate pre-existing issue) — copy decision, out of scope, per instruction.

**HONESTY BAR — stated plainly, not softened.** No physical device was used this session, and no real browser (mobile or desktop emulation, DevTools, Playwright) was launched either — a second `next dev` instance for this project directory is blocked by Next's own single-instance-per-directory dev lock, and the alternative (restarting Alex's own already-running dev server with a different env var) risked disrupting a session he might have had open, so it wasn't done. Every "live" verification this session claims is `curl` against the SSR HTML of that already-running dev server (default/beta flag state only) plus `git diff` review confirming flag-on branches are byte-identical to pre-edit code. `env(safe-area-inset-*)` cannot be exercised this way at all — it is a real-device/real-Safari runtime value that curl, SSR, and even Chrome DevTools' device-toolbar emulation cannot produce; only genuine iOS Safari hardware can. **Concretely unproven and owed:** whether the drawer footer actually clears the home indicator on a real iPhone (Phase 3's actual fix target); whether all four Phase 4 elements actually render at pixel parity with today on a real notched/Dynamic-Island device; whether the mobile tab bar's absence in beta state looks correct in a real mobile viewport (untestable by curl regardless of my changes, since `useIsMobile()` was already client-hydration-gated before this session and is unmodified). This is the same class of gap this file's own prior sessions have hit before (see the pin-dropdown bug above, where local-dev/isolated verification passed while the real bug persisted) — flagging it here rather than letting a curl-clean result read as more proof than it is.

**Reconciliation.** All 8 touched files, confirmed by `git diff --stat` across all 4 build commits: `frontend/lib/chat-only-beta-flag.ts` (new), `frontend/components/rhemata/sidebar.tsx`, `frontend/components/rhemata/mobile-tab-bar.tsx`, `frontend/components/rhemata/study-panel.tsx`, `frontend/app/home/page.tsx`, `frontend/app/page.tsx`, `frontend/app/layout.tsx`, `frontend/app/globals.css`. All six Phase-1-listed entry points confirmed closed (see Phase 1 above). Explicit DO-NOT-TOUCH list from the brief — library breadcrumbs, the admin edit redirect, the landing footer Product list, `MockSidebar`, the study/library `pb-24` reservations, `useChatFocus`'s own chain — confirmed untouched, none appear in the 8-file diff. Working tree clean after each commit (`git status --short`, empty every time). Commits, in order, each confirmed landed by `git show --stat` immediately after committing: `b531215` (Phase 1), `3194966` (Phase 2), `d1a0be2` (Phase 3), `eebbf32` (Phase 4). This records update is its own separate commit, after all four build commits, per the session's own rule.

---

## Study Panel refinement v2 — Phases 0-5 (session state, 2026-07-22)

Five fully-specified UX refinements, executed as six numbered phases (0 = read-only audit, 1-5 = build, each its own commit with a live-check stop). **All commits through the records commit (`fbd6c56`) are on `origin/main`** — Phases 4-5 (`23a845d`, `f1ee036`) went up in the same push as the records commit itself.

**Phase 0 audit — the fe310e2 discrepancy, resolved by explanation, not a bug fix.** Alex's live screen showed a split-view reflow (sidebar disappearing, chat narrowing) despite records saying "floating overlay" shipped 2026-07-21 (`fe310e2`). Direct code read found both things were true at once: `fe310e2` genuinely gave the panel `Content` element floating-card CSS (`inset-y-2 right-2 rounded-xl`, no scrim) — but `app/page.tsx` still actively collapsed the sidebar (`collapsed={studyPanelOpen}`) and reserved chat padding-right sized to the panel's width, **by design** — the commit's own message states it grew that reservation "so the chat card actually resizes to 'about two-thirds' per spec." Not half-landed, not a regression: `fe310e2` fully shipped what it intended (a floating-*styled* card that still reflows layout), satisfying an older "chat keeps two-thirds" spec goal that this session's Phase 1 set out to supersede.

**Also re-checked and found already-correct, no bug:** the swap-in-place mechanism (shell never unmounts/re-slides on a target change, only content resets) was flagged going into this session as a possible "recorded shell re-slide" regression to fix. Direct code read of `fe310e2` and this file's own prior entry (below) found neither ever described shell re-sliding — `fe310e2`'s `handlePointerDownOutside` suppression of Radix's dismiss-on-outside-click for `data-study-trigger` elements was *always* genuine swap-in-place from the moment it shipped, and this file's existing "Reset-on-swap" note (below) already correctly described content-only reset (`key`-forced remount of the inner content div), not shell remounting. **Correction to the record is: there was nothing to correct here** — stated plainly rather than inventing a fix for a premise that didn't hold up.

**Phase 1 → live design reversal (both pushed, both real commits, not a false start):**
- Built as specified: a true floating overlay, zero layout shift ever (`bb5cdc0`) — sidebar's `collapsed` prop removed entirely, `main` permanently `md:ml-64`, panel background switched to `bg-sidebar`, desktop slide 300ms→200ms.
- Alex reviewed live on `rhemata.app` and disliked it. New direction, decided live: sidebar still never collapses, but the chat card narrows via `padding-right` (not a true overlay) so the two read as side-by-side — reverses Phase 1's own "zero layout shift" acceptance criterion, by design (`d2c31e1`). Panel background reverted to `bg-background` (matches the chat card it now sits beside, not the sidebar); slide duration reverted to 300ms (matches `main`'s transition timing so both motions read as one).
- **Net effect for anyone reading Phase 1's original spec text later: its "true overlay" geometry decision is superseded by `d2c31e1`. Its "sidebar never collapses" piece stands.**

**Phase 2 (`c3659cd`, pushed) — Interlinear-open default state.** Dismiss-anywhere, sidebar-click-closes-and-navigates-in-one-click, and Escape-to-close all turned out to already be correct (Radix non-modal defaults, unoverridden) — zero code changed for those. The one real gap: `fe310e2`'s swap-reset effect closed Interlinear on every fresh open and swap; flipped to open by default (Commentaries/Pastors' Notes still default closed, via the existing `key`-remount). Also fixed both `interlinearOpen`'s and its `page.tsx` mirror's initial `useState` default to `true`, closing a first-open flash window.

**Phase 3 (`a60cc22`, pushed) — fixed width, Interlinear wraps.** Panel width is now permanently `w-[33vw] min-w-[380px] max-w-[480px]` — the old 50vw Interlinear-open expansion is gone, along with all the plumbing (`interlinearWide`, the external `onInterlinearOpenChange` callback chain) that existed only to mirror it into `page.tsx`'s reservation. `InterlinearBlocks` switched from `overflow-x-auto` to `flex-wrap` (both the loading skeleton and the real token row) — applied universally, not desktop-gated, since it's shared with the standalone `/study` page and is a strict improvement on any width. STEPBible CC BY attribution line untouched.

**Phase 4 (`23a845d`) — section cards.** Interlinear/Commentaries/Pastors' Notes are now distinct `bg-popover` cards (`rounded-lg`, bordered, `space-y-3` gaps) instead of a flat `border-b` divider stack. `bg-popover` was chosen over `bg-card` specifically because DESIGN.md documents `--card` as deliberately flat/identical to `--background` ("no color elevation") — it would have produced zero visible separation; `--popover` is DESIGN.md's one token that's a genuinely lighter "lifted surface," already paired with `text-popover-foreground` by `DropdownMenuContent` elsewhere in this codebase. Visual restyle only — confirmed `CommentaryAccordionRow` (nested per-excerpt expand inside Commentaries results) is a separate implementation that doesn't import this component.

**Phase 5 (`f1ee036`) — pin icon family.** The pinned-verses collection trigger (top-bar dropdown) changed from a `Bookmark` glyph to the same outline `Pin` icon as the panel's own header pin-this action, plus a live count badge hidden at 0. Went straight to the badge option (no fallback needed) since Phase 0 confirmed `pins.length` was already read at the trigger's render site for its tooltip — zero new data plumbing. Badge styling (`bg-primary` pill, `h-4 min-w-4`, `text-[10px]`) matches `AdminModal.tsx`'s existing pending-count badge exactly, rather than inventing new values. The standalone `/study` page's own, unrelated `Bookmark` usage (a "save word study" feature) was confirmed out of scope and left untouched.

**Mobile: untouched and deliberately out of scope this entire track**, per every phase's own instruction — tracked separately as PLAN.md #43 (SP5). Nothing here should be read as mobile progress.

**Verification method and its real limits, stated plainly:** every phase was `tsc --noEmit`-clean and diff-reviewed before commit. Beyond that, this session's own verification was a local-dev Playwright smoke test confirming only the closed-panel baseline (sidebar at its fixed `x:0`/256px position, `main`'s margin/padding math, zero new console errors) — **opening the panel itself was never independently driven end-to-end by this session**, since local dev cannot reach the production backend for real chat/verse data (CORS-blocked, the same pre-existing gap noted in every prior SP2 session below). Alex closed that gap directly: reviewed Phases 1 (both the original overlay build and the live reversal) through 5 live on `rhemata.app`, confirming each as it shipped, plus an explicit post-push pass on Phases 4 and 5 confirming the section cards read as clearly separated when two are open and the pin badge shows and updates the correct live count. **Every phase now has a real live confirmation, not just a local-dev proxy.**

---

## Pin-dropdown-closes-panel bug — found post-ship, fixed in two rounds (session state, 2026-07-22)

Alex found this live right after the Phase 0-5 work above shipped: selecting a pinned verse from the top-bar `PinDropdown` opened the Study Panel, then it closed itself again within about half a second. Not covered by any of the five phases' own acceptance checks (none of them exercised the pin-dropdown-to-panel path specifically) — a real gap this session's own "every phase now has a real live confirmation" claim above didn't anticipate, since the *phases'* content was confirmed but this specific cross-feature interaction wasn't.

**Root cause:** Radix's `DismissableLayer` (underlying `Dialog.Content`) fires `onFocusOutside` — and dismisses on it, same as `onPointerDownOutside` — for *any* `focusin` event whose target isn't already inside the layer's own subtree, not just the interaction that opened it. Selecting a `DropdownMenuItem` closes that Radix `DropdownMenu`, and Radix's own default close behavior restores focus afterward — landing on elements outside the Study Panel's `Content`, which its (until now unhandled) default `onFocusOutside` read as a dismiss signal.

**Round 1 (`722f4ee`):** added an `onFocusOutside` handler mirroring the existing `onPointerDownOutside` swap-in-place suppression, and marked the `PinDropdown` trigger button `data-study-trigger`. Verified working via a real isolated reproduction (temporary local route mounting the actual `PinDropdown`/`StudyPanel` with fixture data, Playwright-driven, before/after via `git stash`) — genuinely fixed the mechanism as understood at that point. **Did not fix the live bug** — Alex reported it was still broken after this deployed.

**Round 2 (`e9c736b`) — found by tracing real DOM events live, not by guessing again.** Created a disposable admin-created test account via the Supabase Admin API (service-role key, `email_confirm: true`, no real email needed) and seeded one real `study_pins` row (`ROM.8.28`) directly via SQL. Signed in through the real `LoginModal` on `rhemata.app` with Playwright, instrumented `focusin`/`focusout`/`pointerdown`/`click` at the document level via `page.addInitScript` (armed before any app code runs), then drove the actual interaction. The real event sequence on selecting a pinned verse: **item → `DropdownMenuContent`'s own portal container → trigger button** — an intermediate focus stop on the dropdown's own content div, a separate Radix portal that is not a DOM ancestor of the trigger button, so round 1's marker never covered it. That intermediate `focusin` dismissed the panel before focus ever reached the trigger. Fix: `DropdownMenuContent` now also carries `data-study-trigger`.

**Verified with the same live method, confirmed working:** re-ran the identical Playwright trace against production after deploy — confirmed `[role="menu"][data-study-trigger]` present (new code actually deployed, not stale cache) and the panel's `data-state` stayed `"open"` across a full 3-second window (screenshot: verse text, Interlinear open with real Greek tokens, Commentaries/Pastors' Notes closed — all Phase 0-5 work rendering correctly together). **This is the strongest verification in this session** — real signed-in production session, real seeded data, real DOM event trace, not local-dev fixtures or code-reading inference.

**Test account cleanup, confirmed:** the disposable account and its pin were deleted after verification via the same Admin API + direct SQL — `SELECT count(*)` on both `study_pins` and `auth.users` for that `user_id` returned 0 before this record was written. No residual test data.

**Lesson for future sessions on this panel, stated plainly:** local-dev fixture testing (as used in round 1, and throughout Phases 0-5 above) can miss real bugs that only manifest from the actual deployed app's specific DOM/portal structure — round 1's isolated reproduction *passed* even though the live bug wasn't actually fixed yet. When a fix is verified only in an isolated harness, say so, and treat a subsequent "still doesn't work" report as new information, not user error — the live DOM trace in round 2 found the real cause in one pass where more guessing would not have.

---

## Records reconciliation — push ladder + SP4 sign-off closure (session state, 2026-07-21)

**Push ladder, verified against git, not assumed:** `git rev-parse main` and `git rev-parse origin/main` are identical (`5f2c125`) after an explicit `git fetch`; `git branch -vv` confirms `main` tracks `origin/main` with nothing ahead or behind. Every commit from this cycle — `3f68ddc` (teachers-on-verse removal), `ae7e583`, `65b36e2` (chrome cleanup), `916c883`, `fe310e2` (Phase 2 floating overlay), `5f2c125` — is already on `origin/main`. **This corrects an assumption otherwise carried into this reconciliation that the Phase 2 build might be unpushed/hard-stopped locally — it was not; nothing from this cycle is sitting local-only.**

**SP4 sign-off, confirmed complete:** Alex signed in on `rhemata.app` and ran the full authenticated verification pass. All four checks passed: real card content for a signed-in user, the honest-empty state, nested back-return, and keyboard-only navigation. This closes SP4 teacher-card verification — the "NOT verified this session — needs Alex's own pass" framing in the 2026-07-18 SP4 entry below is superseded by this pass (closing note added there), not deleted.

**This same pass also confirmed, live in production, the two same-day removals below:**
- "Your teachers on this verse" is genuinely gone on `rhemata.app` — closes that section's own "full authenticated production re-verification... has not been done" caveat (closing note added there).
- The dev-trigger button + shortcut and the "Open in Study" link are genuinely gone on `rhemata.app`, and STEPBible/Tyndale attribution still renders correctly — closes that section's equivalent gap (closing note added there).

**Not closed by this pass — stays open:** the Phase 2 floating-overlay build (`fe310e2`) **shipped after** this sign-off pass and has only been verified against local-dev route-interception doubles (see that section's own caveat below, left as-is — still accurate). Its "shipped, build commit `fe310e2`" status is a different claim from "signed off" — don't conflate them. A hands-on authenticated `rhemata.app` pass on the overlay itself is still owed.

**Forward:** SP5 (mobile bottom-sheet, roadmap #43) is next and reuses the overlay's shared open/swap/close model (`page.tsx` state + `PanelBody`'s swap-reset), built presentation-agnostic for exactly this reuse. Two long-standing items remain open, untouched by this session: no real screen-reader pass has ever been run (Open blockers #13), and the Hebrew lexicon permission gate from Online Bible has not been obtained (Open blockers #14).

---

## SP panel refinement — Phase 2: floating overlay (session state, 2026-07-21)

**Superseded 2026-07-22 — read the new entry at the top of this file first.** "Desktop presentation" below is no longer current: `page.tsx` never stopped reflowing the sidebar/chat around this "floating" card (confirmed by direct code read, not a regression — this commit's own reservation-growing change was intentional), and the geometry itself was replaced twice more since (a true zero-reflow overlay, then a live reversal to side-by-side chat-narrowing). "Non-modal + swap-in-place" and "Reset-on-swap" below both held up under re-audit and are still accurate as descriptions of what shipped, except "Reset-on-swap" collapsing Interlinear on swap — Phase 2 of the 2026-07-22 session flipped that default to open. Kept below verbatim for provenance.

Shipped, build commit `fe310e2` — `frontend/app/page.tsx`, `frontend/components/rhemata/chat-message.tsx`, `frontend/components/rhemata/study-panel.tsx` only. Alex's SP4 sign-off (the gate this phase was waiting on) cleared before this session started. **Goes further than the original Phase 2 scope** (`docs/superpowers/plans/2026-07-19-study-panel-refinement.md`, Tasks 6-9), which was margin/rounding only — this session's explicit spec added non-modal desktop interaction and swap-in-place, superseding that plan's narrower Task 9 assumption (default Radix modal dismiss unmodified).

**Desktop presentation:** the panel is a floating card — `inset-y-2 right-2 rounded-xl border border-border`, reusing the existing `shadow-lg` (all values already in use elsewhere in this codebase, per DESIGN.md's "no new shadows/radii/colors" rule and its own "popovers/sheets are the only lifted surfaces" carve-out) — instead of a docked column flush against the screen edge. `page.tsx`'s reserved-width clamps grew by `+1rem` per bound (`clamp(496px,calc(50vw+1rem),736px)` / `clamp(396px,calc(33vw+1rem),496px)`) so a real gap shows between the chat card and the panel, not an overlap.

**Non-modal + swap-in-place:** `PanelPrimitive.Root` now takes `modal={isMobile}` — desktop is non-modal (Radix's documented `DialogContentNonModal` path, confirmed via `/radix-ui/primitives` docs and the installed `@radix-ui/react-dialog@1.1.16` type declarations before writing any code), and desktop renders no `Overlay` at all. Chat stays fully visible and interactive behind it. `VerseReferenceSpan`/`TeacherReferenceSpan` (`chat-message.tsx`) get a `data-study-trigger` marker; `Content`'s `onPointerDownOutside` checks for it via `event.detail.originalEvent.target.closest(...)` and calls `event.preventDefault()` only for those, letting a second underline click swap `reference` in place (page.tsx's `handleVerseClick` already did this unconditionally — no page.tsx change was needed there) instead of racing Radix's default dismiss into a close-then-reopen. Everything else outside the panel still closes it normally — no blocking layer anywhere (confirmed by grep and by reading the full diff).

**Reset-on-swap:** `PanelBody` now collapses Interlinear and resets scroll to top on every genuine target-identity change (`referenceKey(reference)`, a content-identity string — re-clicking the same target is correctly a no-op), and fades the content subtree in via a `key`-forced remount. This supersedes the old "leave Interlinear open across a verse switch" decision from SP2 Phase 8.

**Shared-model note for SP5:** the target/open/close state (`page.tsx`) and the swap-reset behavior (`PanelBody`) are presentation-agnostic and were already shared between mobile/desktop (single `<StudyPanel>`, branching only on `useIsMobile()`); only the modal/overlay/positioning pieces differ now. A future mobile bottom-sheet build can reuse both without touching this logic — the desktop side-slide and a future mobile bottom-rise are presentation layers over the same shared behavior.

**Live-verified, real evidence (Playwright, local dev, route-interception test doubles for `/chat` and `/study/interlinear` only — same CORS-driven method as the two sessions above):** chat textarea stayed typeable while the panel was open; clicking a second, different verse underline while open swapped content to it in place (screenshot: same panel shell, new verse text, Interlinear auto-collapsed, no flicker/stack); scroll position confirmed reset to 0 after a swap; the X button closed the panel; clicking plain chat text (not a trigger) closed the panel; mobile (iPhone 13 emulation) confirmed **completely unaffected** — full-screen sheet, dark scrim, no rounded corners, no gap, chat hidden underneath, byte-for-byte the same presentation as before.

**Caveat, stated plainly:** as with the two sessions above, this is local-dev verification against route-interception doubles, not a full authenticated pass against `rhemata.app`. That full production re-verification (still owed from the "your teachers on this verse" removal earlier this session too) has not been run yet.

---

## SP2 — Panel chrome cleanup (session state, 2026-07-21)

Three approved UI-only changes, build commit `65b36e2`, `frontend/app/page.tsx` + `frontend/components/rhemata/study-panel.tsx` only:

1. **Removed the floating "Study preview" dev-trigger button and its Cmd/Ctrl+Shift+S shortcut** (`app/page.tsx`) — collided with the chat button and duplicated the panel's one real open path. The panel now opens **only** via a verse/teacher underline click. `NEXT_PUBLIC_STUDY_PANEL_ENABLED` and the underline click-path (`onVerseClick`/`onSelectPin` wiring into `handleVerseClick`) are untouched — confirmed by diff, not by inference.
2. **Removed the "Open in Study" link** from the bottom of the panel (`study-panel.tsx`). The standalone `/study` page remains live and reachable by direct URL as the fallback — confirmed by direct navigation, untouched by this diff.
3. **STEPBible/Tyndale House attribution (CC BY 4.0 license condition) retained, no restyling needed.** All four rendering surfaces — `InterlinearBlocks` (shared by the panel's Interlinear row and the standalone page), the panel's own `WordStudyView`, and the standalone page's `WordStudyPanel`/`InlineWordPanel` — already use `text-xs text-muted-foreground`, DESIGN.md's own documented low-prominence pattern (line 120, same class used for verse-number superscripts). No code changed on this point.

**Live verification method, since local dev is CORS-blocked from the production backend for `/chat`, `/study/interlinear`, and `/study/lexicon` (the same pre-existing constraint noted in the "your teachers on this verse" removal above and in Phase 7/8/9's history):** used Playwright route interception as network-level test doubles for those three endpoints only (synthetic but shape-accurate SSE/JSON responses) — every other request (Commentaries, Pastors' Notes, pins) hit the real backend unmodified. This produced a **genuine click on a real verse-underline** (not the removed dev button) that opened the panel, expanded Interlinear with real-shaped tokens, and opened the word-study view — confirming the attribution renders correctly in both panel surfaces by direct observation, not class-name inspection. Pin click showed the expected guest Beta Access gate, no crash. Standalone `/study` loaded directly with no crash.

**Not touched:** SP4's curated `TeacherCard` path, Commentaries, Pastors' Notes, pins, and all interlinear/lexicon *data* fetching — chrome only, per scope lock.

**Production confirmation, 2026-07-21:** Alex's SP4 authenticated sign-off pass confirmed all three changes live on `rhemata.app` — dev-trigger button and shortcut gone, "Open in Study" link gone, STEPBible/Tyndale attribution still renders correctly. Full detail in the reconciliation entry at the top of this file.

---

## SP2 — "Your teachers on this verse" removed (session state, 2026-07-21)

**Removed, build commit `3f68ddc`, frontend-only diff (99 deletions, `frontend/components/rhemata/study-panel.tsx` only):** `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, and the "Your teachers on this verse" render block. **Reason:** verse-anchored nearest-chunk matching (`source_kind_filter=sermon_transcript`) surfaced irrelevant excerpts under teacher names. Retired pending a possible theme-based approach via the SP4 teacher-card path instead, not replaced same-session.

Preceded by a read-only removal-footprint audit (previous session) that traced the feature to commits `af5be46` (Task 9, backend filter param) and `8698e4a` (Task 11, the panel wiring), then classified every symbol it introduced as UNIQUE (safe to remove) or NOW-SHARED (must stay). That classification held with zero surprises during execution.

**Intentionally preserved as shared infrastructure — zero backend changes this session:**
- `/study/commentary` endpoint, `source_kind_filter` param, and both its conditional branches (`commentary` / `sermon_transcript`) — the sermon-results code path predates this feature entirely (`git log -S match_sermon_chunks_by_ref` traces it to `1375b3f`, well before `af5be46`); the standalone Study page's default (unfiltered) query depends on both branches running together, and `CommentaryAccordionRow` depends on the explicit `commentary` filter.
- The `accessToken` prop chain (`app/page.tsx` → `StudyPanel` → `PanelBody`) — now feeds `TeacherCard`, `CommentaryAccordionRow`, `PastorsNotesSection`, and `useLexiconDefinition`.
- `verseIdStr` — feeds `useInterlinear` and the `selectedStrongs`-reset effect; only the `useTeachersOnVerse` reference to it was removed.

**Proof performed before commit:**
- Zero-hit greps repo-wide for `useTeachersOnVerse`, `TeacherOnVerseResult`, `isVerseRef`, `teacherResults`, `teachersLoading` — confirmed clean.
- `tsc --noEmit` clean; `next build` production build clean.
- Live against local dev (`localhost:3000`, Playwright, guest session): verse card, Interlinear, Commentaries, Pastors' Notes, and pin-click (guest → Beta Access gate, not a crash) all render correctly; "Your teachers on this verse" text confirmed absent; a real Commentaries-row fetch was observed carrying `source_kind_filter=commentary` with **no accompanying `sermon_transcript` request** — direct proof the removed hook no longer fires, not just a code-reading inference. Standalone `/study` page loaded without error, same fail-quiet "No commentary found"/"Couldn't load notes" states as the panel (consistent with this environment's known local-dev-to-production CORS block, not a regression).
- **Caveat, stated plainly:** local dev cannot reach the production backend for authenticated calls (CORS-blocked, a pre-existing constraint this project has hit before — see Phase 7/8/9 entries below, which all needed a real `rhemata.app` session to verify auth-gated behavior). This session's live checks are real but guest/local-only; a full authenticated production re-verification (real commentary/sermon results, Pastors' Notes content) has **not** been done post-removal and would need a push + a real signed-in session on `rhemata.app`, the same as prior SP2/SP4 sessions did.
  - **Closed 2026-07-21** — Alex's SP4 authenticated sign-off pass confirmed this removal live in production (the text is genuinely gone). Full detail in the reconciliation entry at the top of this file.

**Not touched:** SP4's curated `TeacherCard` path (`reference.type === "teacher"`) — a different feature, confirmed unrelated during the audit (disjoint code path, coincidentally similar name).

---

## SP panel refinement — Phase 1: reference-persistence fix (session state, 2026-07-19)

Shipped per `docs/superpowers/plans/2026-07-19-study-panel-refinement.md` (PLAN.md #42.5), following a grill-me interview session that resolved the "clicking does nothing" premise in code before any build work started.

**Root cause, confirmed by direct code trace, not assumed:** `verified_references` (SP1's fail-quiet reference data) and `citations` were computed fresh every chat turn and attached only to that turn's SSE `meta` event (`chat.py:1026-1031`) — never written to the database. `_save_conversation` (`chat.py:445-479`) inserted only `id`, `conversation_id`, `role`, `content` per message; there is no backend `/conversations` endpoint at all — the frontend reads conversation history straight from Supabase (`useConversations.ts`), requesting only `role, content`. Consequence: every reopened conversation lost 100% of its verse/teacher underline clickability and citation pills, regardless of signed-in/guest state or reference type — not the signed-in/guest or verse/teacher distinction the inherited notes assumed. `message_id` turned out to already survive (it's the message row's own `id`); it just wasn't being selected on reload.

**Shipped, commits in order:** plan doc + PLAN.md `#42.5` entry (`0285920`, `166c238`); `.gitignore` entry for `.worktrees/` (`cd9ccd6`); migration `066_messages_reference_data.sql` (`98bb59e` — nullable `messages.citations`, `messages.verified_references` jsonb columns, applied and verified on a fresh connection before commit); `chat.py`'s `_save_conversation` persisting both on the assistant row only (`08b2a7d` — bundled per Alex's explicit call, citations had the identical bug for the identical reason); `useConversations.ts`'s `loadMessages` selecting `id, role, content, citations, verified_references` and mapping them into `Message`'s existing optional fields (`b19f6d0`); this record itself (`a775f86`). Underline's own visual treatment deliberately unchanged (Alex's explicit call — the "not looking tappable" complaint was very likely this same persistence bug, not a separate design issue).

**Live-verified, real evidence (Playwright against `rhemata.app` production, disposable admin-created test account, deleted after — zero residual rows confirmed):**
- Fresh answer to "What does Derek Prince teach about deliverance, based on Romans 8:28?": 4 real underlined spans rendered post-stream (Derek Prince, Romans 8:28 ×2, Joel 2:32); clicking one opened the panel correctly.
- **The actual bug, proven fixed:** clicked "New Chat," then reselected the same conversation from the sidebar — the identical 4 underlines were still present and still genuinely opened the panel on click. This is the literal scenario that was broken before this fix.
- Direct DB query on the same row: `citations` had 8 entries, `verified_references` had 3 (matching the 4 rendered spans — "Romans 8:28" occurs twice in text but resolves to one verified identity, reconciling exactly).
- Guest (unauthenticated) chat streaming confirmed unaffected on production — guests never call `_save_conversation` (`chat.py`'s `if user_id:` branch), so this fix has zero guest-facing surface, confirmed live not just by code-reading.
- Simulated a pre-migration row (nulled `citations`/`verified_references` directly in the DB on a real assistant message) and reloaded it live: zero underlines, plain answer text rendered normally, zero console/page errors. Confirms graceful degradation — this is NOT the same as the spec's "retrofitting old conversations" exclusion (which stays correctly out of scope), it's proof the new code path fails safe on old data shapes.

**Process note:** executed in an isolated git worktree (`.worktrees/sp-panel-refinement-phase1`, branch `sp-panel-refinement-phase1`) per Alex's explicit choice this session (departure from this repo's usual direct-to-main convention), fast-forward-merged into `main` and pushed only after Alex confirmed that was the right way to reach a real deploy for live verification. Worktree removed after merge; branch fully merged, safe to delete.

**Left open, for whoever (or whichever panel) picks this up next:** Phase 2 (floating overlay, desktop only) is scoped and ready in the plan doc but explicitly gated on Alex's own SP4 sign-off (see below) — do not start it before that sign-off is confirmed. Isolated worktree (`sp-panel-refinement-phase1`) and its branch were removed after the fast-forward merge to `main`; nothing dangling. This session did not touch `HARNESS.md` or `ARCHITECTURE.md` — the concurrent records-cleanup session's note below already flags `ARCHITECTURE.md`'s missing `messages.citations`/`verified_references` columns; still true after this session.

---

## Records cleanup + harness write-detection loop fix (session state, 2026-07-19)

Ran chronologically before the SP panel refinement session above (commits
land 15:03–16:02 vs. that session's 17:57–18:44) — inserted here, not at the
top, to keep this file's ordering true to when the work actually happened,
not when it was logged.

**Records-only cleanup — commit `b510b31`.** Reconciled three places PLAN.md
contradicted itself or reality: `sources/` backup marked DONE 2026-07-19
(Google Drive; restore explicitly flagged unverified — not tested), SP2 status
in `docs/inline-study-panel-spec.md` corrected from "NOT yet scheduled or
built" to reflect its actual shipped state, and harness `#5.5` exit condition
(a) corrected from PLAN.md's stale "OPEN" to the CLOSED state confirmed by
direct code read + `git log` (commit `96bc3ff`). No logic/DB changes.

**Read-only PLAN.md-vs-live-DB audit — no file changes, findings unaddressed.**
Compared every DB-checkable claim in PLAN.md against direct live queries.
Most drift is honestly dated-and-labeled (chunk/doc/proposition totals aging
since the 2026-07-14 refresh). Two live findings Alex hasn't acted on yet:
(1) New Wine's "33 articles/9 issues" claim is now 15 docs/8 issues — matches
the SP4 pre-build fix's own 33→15 number below, just never folded back into
PLAN.md `#26`. (2) SermonIndex's "#34 still open" framing is *more* wrong
than PLAN.md itself knows — Carter Conlon (`visibility='shown'`, unlicensed)
now has 6 real ingested documents, contradicting the "only ingested speaker
is hidden, structurally blocked" note under SP2 Phase 7. Propositions count
also dropped 2,488→2,306 since the 07-14 refresh with no documented cause —
worth a look. Full comparison table not persisted anywhere; re-run the audit
if this matters before relying on any PLAN.md count.

**Executor write-detection infinite loop — diagnosed then fixed, commits
`d9ab1cc` (build) + `f1e5184` (records).** Root-caused the 2026-07-18 bug
below by reading the real surviving `/tmp/rhemata-harness-writes` log from
that incident: a benign grep for a bare SQL-verb-shaped pattern
(`"ALTER TABLE..."`) against a directory-only target got recorded as a write
with zero extractable referents, so it could never be "accounted for" by any
report, ever; retries piled up undeduplicated copies of the same
unsatisfiable record forever. Fixed in `deterministic_gate.py` only
(`guard_pretooluse.py` and `check_reconciliation()`'s fallback both
untouched, per explicit scope lock): referent extraction now always yields
something meaningful, and accounting checks the cumulative, deduped text of
everything the finishing agent has said all session, not just its latest
message. Proven via a new `.claude/harness-selftest/test_write_accounting_loop_fix.py`
against the real recorded incident command — loop converges and stays
converged; a genuine undisclosed write still blocks; a genuine disclosed
write still passes. `BASH_WRITE_INDICATORS` deliberately left over-flagging
benign searches (the safe default) — narrowing it is flagged below as its
own future session, not done here.

**Left open, not done this session — flagged for whoever picks this up
next:** `HARNESS.md`'s "Closed" section still doesn't list the loop fix
above (`d9ab1cc`) — that's the durable home for it per HARNESS.md's own
eviction rule; right now the only record is in this file, which gets
reshuffled every session (see this section's own insertion above).
`ARCHITECTURE.md`'s `## Database` table list is also stale — missing
`jewish_perspectives` (still live, 2 rows, confirmed by the audit above),
`study_pins` (SP2 Phase 5), `teacher_profiles` (SP4), and the new
`messages.citations`/`messages.verified_references` columns from the panel
refinement session above. Neither touched this session — Alex hadn't
confirmed he wanted them done yet when this session closed.

---

## SP4 — Teacher Cards (session state, 2026-07-18)

Built per `docs/superpowers/plans/2026-07-18-sp4-teacher-cards.md` (11 tasks),
following the pre-build data fix recorded below. Shipped: migrations `064`
(`teacher_profiles` table + 9-row seed) and `065` (`match_teacher_chunks`
RPC, license-gated); `app/services/llm_client.py` (extracted shared
Anthropic client + guardrails-text loader, also now used by `chat.py`);
`GET /study/teachers` + `GET /study/teacher/{source_id}` (combined
bio/works/live-position-synthesis endpoint, own similarity floor since the
RPC supplies none); frontend curated-teacher detection/verification
(`study-reference.ts`), underline rendering (`chat-message.tsx`), the
`TeacherCard` component, and full wiring through `study-panel.tsx` /
`page.tsx`. All 10 build commits pushed; `origin/main` confirmed at each
step.

**Live-verified, real evidence:**
- Backend: `curl https://rhemata-production.up.railway.app/study/teachers`
  returns all 9 curated teachers with correct `source_id`s, live in
  production — confirmed directly, not assumed from a successful deploy.
- The `TEACHER_POSITION_SIMILARITY_FLOOR = 0.3` value is empirically
  validated against this corpus's real score distribution, not a guess:
  `scripts/test_teacher_card.py` shows an on-topic query's best similarity
  at 0.508 (clears the floor) and an off-topic query's best score at 0.152
  (stays well below it) — this directly closes the gap the 2026-07-18
  pre-build diagnostic flagged (no threshold exists in `match_chunks`/
  `match_teacher_chunks` themselves).
- Frontend, live on `rhemata.app` (real Playwright session, guest/no
  auth): asked "What does Derek Prince teach about deliverance?", waited
  for the real streamed answer to fully stabilize (not a fixed timeout —
  polled until page text stopped changing), confirmed **2 real underlined
  "Derek Prince" buttons** in the rendered answer, exact class match to
  `TeacherReferenceSpan`'s styling. Clicked one: the panel opened with
  header "TEACHER" / "Derek Prince" (confirms correct mode-switch, not the
  verse card, no nesting/back-stack residue). As a guest (no access token),
  the card body read "This teacher's card isn't available right now" —
  honest and non-crashing, not a silently-swallowed fake-empty state (the
  exact bug class Phase 7 found in `pastors_notes.py`), though it doesn't
  specifically prompt sign-in the way some other gated surfaces do — see
  Open Flags below.

**NOT verified this session — needs Alex's own pass, blocked by the Beta
Access gate:** signing up a real disposable test account to check requires
a beta access code this session doesn't have (`Become a test user` → a
`BetaGate` code-entry screen, dead end without the code). Specifically
unverified: (1) real card content for a signed-in user — actual bio text,
a real works-in-corpus list, a real synthesized position; (2) the
Interlinear-width-collapse fix (Task 9) — switching from a verse card with
Interlinear open to a teacher card should snap the panel back to 33vw, not
stay at 50vw; (3) the fail-quiet floor behavior live, end-to-end, on an
authenticated off-topic question (Task 5's script validates the floor
value itself against real scores, but not the full authenticated request
path). None of these are new risks invented for this note — they're the
literal gaps left by not being able to sign in.

**Closed 2026-07-21** — Alex signed in and ran the full authenticated pass:
real card content, the Interlinear-width-collapse behavior, the fail-quiet
floor end-to-end, back-navigation, and keyboard-only nav all confirmed.
Full detail in the reconciliation entry at the top of this file.

---

## SP2 — Inline Study Panel (session state, 2026-07-17)

Phase 7 (Commentaries + Pastors' Notes accordion rows) shipped and live-verified
on `rhemata.app`. Commits `69df175`, `063fcab`, `5c82975`, `0c8b75f`. Separately:
`32f5b25` fixed a Phase 5 defect (pin-cap tooltip still checked `>= 4` after the
real cap moved to 8).

**Found during Phase 7, then fixed same session:** `backend/app/routers/pastors_notes.py`
never imported `get_user_role`, called at 3 sites (`list_cards`, `create_card`,
`update_card`). NameError → 500 on every authenticated `/pastors-notes/cards`
call, 100% reproducible; guests unaffected (they skip that branch). The
frontend's `.catch(() => setCards([]))` silently repainted every crash as an
honest-looking empty state — broken for every signed-in user on the standalone
Study page too, not just the new panel row, for as long as the import gap
existed. Fixed in `5d430b7` (one-line import, plus closes the read-path
silent-swallow with a distinct error state; add/edit/delete already surfaced
real errors correctly and were untouched). Proven live, not just a 200 —
full round trip on `rhemata.app` with a disposable test account (created,
elevated to admin, deleted after): note added, visible after a fresh reload
(real server persistence, not local state), edited, edit visible after a
fresh reload, deleted. Zero residual test data confirmed.

**Attribution correction:** an earlier note this session described leaving
this bug unfixed as "Alex's explicit call." That was wrong — the actual answer
was to a narrower question about touching the backend in that specific moment,
not a decision to leave the bug open. Corrected here; the bug is now fixed.

**Phase 8 (Interlinear + lexicon word study, moved in from the dissolved SP3)
shipped and live-verified on `rhemata.app`, same session.** Commit `9415f11`
— Tasks 28–30 combined into one commit rather than three: the `AccordionRow`
controlled-mode extension and lifting `interlinearOpen` up through
`StudyPanel` to `page.tsx` serve both the row's mount and the width-borrowing
together, and weren't cleanly separable after the fact without redoing
already-correct, already-typechecked work.

- **Interlinear row (Task 28):** `useInterlinear` + `InterlinearBlocks`
  (both Phase 6 extractions), mounted first, before Commentaries. Live on
  Romans 8:28: 18 real Greek tokens rendered, STEPBible/Tyndale House
  attribution visible.
- **Word-study view (Task 29):** tapping a token opens the panel's one
  back-button surface — `WordDefinitionCard` + `useLexiconDefinition`,
  object construction copied exactly from `study/page.tsx`'s own
  interlinear-tap call site (`selectedToken ? {...} : selectedStrongs &&
  lexiconEntry ? {...} : null`). Live: tapped a real token (Strong's
  `G6063`), word-study view opened, Back button returned to the normal row
  view with Interlinear still expanded. STEPBible attribution added to this
  view directly (Phase 2's Task 4 had deferred the panel's copy here) —
  deliberately not baked into `WordDefinitionCard` itself, keeping Phase 6's
  file as Phase 6 left it.
- **Width-borrowing (Task 30):** confirmed live both directions — 422px
  (33vw clamp) collapsed, 640px (50vw clamp) while Interlinear is open,
  automatic, no user toggle.
- **Task 31 (grep):** zero `Translations`/`Cross-references` references
  anywhere in the frontend.
- **Task 32, live, not just structural:** a real, SP1-verified "Genesis
  1:1" underline (from a real streamed chat answer, not the hardcoded dev
  demo reference) opened the panel and showed the honest "No interlinear
  data available for this verse" message — zero fake "coming soon" copy,
  zero Greek tokens for an OT verse. Precept Austin / "From the Library"
  confirmed absent both structurally (`WordDefinitionCard` has no such code
  path — verified by reading its source, not inferred) and live (zero
  matches after tapping a real Greek word).
- **One judgment call made without a plan citation, flagged here rather than
  silently decided:** the word-study view's header has only a Close button,
  no Pin — pins are verse-scoped and still one tap away via Back, so nothing
  is actually lost, just an extra tap. The plan's Task 29 doesn't specify
  either way.

**Phase 9 (keyboard + screen-reader verification) shipped and live-verified on
`rhemata.app`, same session.** Commit `bb8aa43`. Diagnostic-first: audited
read-only, reported 5 confirmed gaps plus 4 confirmed-clean surfaces, stopped
for Alex's go-ahead before touching anything — all 5 confirmed gaps approved
for a fix, all additive, none of the 4 clean surfaces touched.

- **Gap 1 — accordion rows didn't announce open/closed state.** `aria-expanded`
  added to all three `AccordionRow` triggers (Interlinear/Commentaries/
  Pastors' Notes) and to Commentaries' nested per-excerpt toggle. Live,
  before/after a real keyboard toggle: all four went `false → true` correctly.
- **Gap 2 — closing the panel dropped focus to `<body>`.** This panel has no
  `Dialog.Trigger` (opened from verse-underline clicks, the dev button, or a
  keyboard shortcut), so Radix had nothing to restore focus to. Now captures
  `document.activeElement` on open and restores it via `onCloseAutoFocus`
  (Radix's own override point — doesn't touch the focus-trap mechanism, a
  separate concern), falling back to the chat textarea if the original
  element is gone. Live, both close paths tested: clicking the panel's own
  Close button and pressing Escape each correctly returned focus to the
  actual triggering element (the dev button, in both tests).
- **Gap 3 — word-study view lost focus to a generic container, both
  directions.** Entering now focuses the Back button (the one actionable
  element at the top of this back-stack surface); leaving via Back now
  refocuses the *specific* token that was tapped, not just "the row" —
  `data-strongs-token` added to the shared `InterlinearBlocks` (inert
  markup, zero behavior change for the standalone page's existing use),
  read by a `PanelBody` effect that fires once after Back clears the word
  view. Live: tapped a real token (Strong's `G6063`), confirmed focus
  landed on "← Back" on entry, confirmed focus returned to the *exact same*
  `G6063` token button on exit (`data-strongs-token` matched exactly, not
  just "some token"). Falls back to the row view's own container
  (`tabIndex={-1}`) if the exact token isn't found — not separately
  exercised live (no known way to force that path without breaking the
  fetch deliberately), but the fallback ref is real and typechecked.
- **Gap 4 — pin button had no real accessible name, only a `title`
  fallback.** Added `aria-label` mirroring the existing title text. Live:
  confirmed `aria-label="Pin limit reached (8)"` on the live DOM in the
  cap-reached state.
- **Gap 5 — pin-cap message wasn't announced.** Added `role="alert"` (implies
  assertive live-region semantics, fires on insertion — correct for a
  message that auto-dismisses in ~2.5s and can't rely on the user already
  being focused on it). Live: confirmed `role="alert"` on the live DOM
  element, using a real 9th-pin-attempt trigger (8 real seeded pins, a real
  refusal).
- **All 4 previously-clean surfaces re-confirmed unaffected, live:** focus
  trap (25 tabs, no leak), `aria-labelledby`/`aria-describedby` panel
  labeling both present, pin dropdown (real `role="menu"`, opens/closes via
  keyboard), verse underlines (real, keyboard-activatable buttons in a
  fresh answer).
- **Honesty bar, explicit:** every claim above is either real keyboard
  interaction (Tab/Enter/Escape driving the actual page) or live
  accessibility-tree/DOM attribute inspection (`aria-expanded`, `aria-label`,
  `role`, `data-*`) on the deployed site — not source-code inference and not
  a screen-reader run. **No actual screen reader (VoiceOver/NVDA) has been
  run against this panel.** That remains a genuinely open, unproven check —
  logged as a new open flag below, not closed by this session.

**Phase 10 (records correction) DONE, same session — commit `a7417eb`.**
Task 35 (PLAN.md): appended the Phase 7/8/9 completion record to #40 (Steps
1–5 of the task were already recorded by earlier sessions, verified against
PLAN.md's live content rather than assumed — #41's supersession, the
teacher-tap decision, the pin-system redesign, the Precept Austin deferral,
and the Hebrew permission gate were all already present); added the two
still-missing pieces — Step 6 (#33's STEPBible half marked closed, the
openbible.info half stays open) and Step 7 (the SP track intro's "old
/study page untouched" wording marked superseded by Phase 4 + Phase 6,
with the same "behaviorally, not literally" distinction those two phases
already proved live). Task 36 (this file): Open Flags 16/17 were already
closed by the sessions that shipped Phase 1/3 — PLAN.md's own #40 entry
already carries "closes Open Flag 17" inline, nothing further to do there;
added Blocker #14 for the Hebrew permission gate, cross-referencing PLAN.md
Open Decisions #11 per the task's explicit instruction.

**SP2 is now fully done, all 10 phases.** The only two things this build
leaves genuinely open are Blocker #13 (no real screen-reader pass) and
Blocker #14 (Hebrew lexicon permission) — both real, both already logged,
neither invented for this closing note.

---

## SP4 pre-build data fix (session state, 2026-07-18)

5 teachers (Bob Mumford, Ern Baxter, Charles Simpson, Don Basham, Oswald J.
Smith) had no `sources` row and no `source_aliases` entry — all their
documents carried the shared New Wine Magazine `source_id`
(`72b2f583-d7f9-4361-be1c-6d5aebe59fac`). Derek Prince additionally had 5
articles mis-attributed to the same magazine bucket despite having his own
resolved source. Fixed via direct `psycopg2` transactions (one per teacher),
each verified live: licensing columns (`license_status`, `visibility`,
`permission_granted_at`, `permission_contact`, `permission_terms`) copied
verbatim from the magazine row, alias resolution replicated
`reference_verifier.py`'s exact path, identity counts matched, spot-checked
chunks/embeddings unchanged. Independently re-verified against a fresh DB
connection before this record was written, not just taken from the
executor's own report.

- Bob Mumford → new source `e2a4babd-c49f-46b2-940e-9771b95e695f`, 4 docs moved
- Ern Baxter → new source `63bdb33a-f672-415e-a209-0dd12fdf29de`, 2 docs moved
- Charles Simpson → new source `c39c4e62-59f3-4a51-9f86-6d1fbcdc6758`, 4 docs moved
- Don Basham → new source `1870bc05-2583-4f88-a6c3-0f5bd31212b9`, 2 docs moved
- Oswald J. Smith → new source `9baaf49f-f9cd-463c-af8b-88ed5b976eb5`, 1 doc moved
- Derek Prince → 5 stray docs re-pointed to his existing source
  `17be391b-d025-4178-8543-3e84da675c5d`, no new source/alias

New Wine Magazine bucket: 33 → 15 documents. Total `documents` row count
unchanged at 3,817 (no rows created or deleted — every write was a
single-column `source_id` UPDATE). Full 9-teacher audit (identity count vs.
name count) re-run after the fix: every alias resolves, every delta is 0.
SP4 build (#42, teacher card content) is now unblocked on this front — no
remaining hardcoded-bio teacher shares another entity's source_id.

## Known Harness Bugs

- **Executor loop, 2026-07-18 diagnostic — FIXED 2026-07-19, commit
  `d9ab1cc`.** Write-detection gate flagged an already-fully-disclosed
  benign action (failed grep + scratchpad cleanup) for 12 consecutive
  turns, alternating "1 of 9"/"2 of 9" flagged-item counts with no change
  in actions between turns. Root cause, confirmed against the real
  surviving 2026-07-18 write-state log: a benign grep for a bare
  SQL-verb-shaped pattern against a directory-only target got recorded as
  a write with zero extractable referents, so it could never be
  "accounted for" by any report text, and retries piled up undeduplicated
  copies of the same unsatisfiable record forever. Fixed by making
  referent extraction always yield something meaningful (never empty) and
  by checking disclosure cumulatively against everything the finishing
  agent has said all session, deduped, instead of only the latest
  message per turn. Proven via `.claude/harness-selftest/test_write_accounting_loop_fix.py`
  (loop converges and stays converged; a genuine undisclosed write still
  blocks; a genuine disclosed write still passes) — only this is claimed
  fixed, nothing broader. **Does not alter #5.5** — exit condition (a)
  stays closed exactly as PLAN.md records it; this session touched
  neither of its two named bridges. **Does not touch**
  `check_reconciliation()`'s fail-closed fallback (missing session_id /
  unreadable state file) — left exactly as-is, the safe-direction default
  for a different, narrower case.

- **Future session flag: `BASH_WRITE_INDICATORS` still over-flags benign
  searches on purpose.** A grep for a bare SQL-verb-shaped word (e.g.
  "ALTER TABLE") still gets recorded as a write — the 2026-07-19 fix above
  only made that already-flagged record satisfiable and non-looping, it
  did not reduce what gets flagged; over-flagging remains the deliberate
  safe direction (principle 5). Narrowing that classifier so harmless
  searches stop being flagged at all is a separate, higher-risk decision
  (it trades against the explicit "over-recording is safe" design intent)
  — its own dedicated session, weighed on its own, not bundled here.

---

## Open blockers

**1. Dead `~/Desktop/rhemata` path — 8 scripts — DONE 2026-07-22.**
3 scripts (`scrape_youtube.py`, `clean_transcripts.py`, `ingest.py`'s
`DOCS_FOLDER`) had it hardcoded as an actual runtime constant — now derived
from the script's own file location at runtime (`Path(__file__).resolve()`
or the equivalent `os.path` form), so a future repo move can't reintroduce
this. The other 5 (`ingest_tahot.py`, `generate_excerpts.py`,
`extract_book_quotes.py`, `ingest_interlinear.py`,
`test_excerpt_generation.py`) already derived the real path correctly at
runtime — the dead path only appeared in a docstring usage example, replaced
with a relative "run from repo root" instruction. Verified live: each script
runs clean (`--help` or module-level import) from repo root post-fix.
Commit `5bdf720`.

**2. `CommandBlock.tsx` hardcodes `/Users/alexwhitley` — DONE 2026-07-22.**
The file itself no longer exists — it was refactored at some point into
`frontend/components/admin/corpus-data.ts` (data) + `card-modal.tsx`
(rendering), and this blocker's filename had gone stale along with the path
it named. Fixed at the actual current location: 75 command strings in
`corpus-data.ts` had the dead path baked in; centralized into one exported
`REPO_ROOT` constant so a future move is a one-line change instead of a
75-line find/replace. Commit `5bdf720`.

**3. `sources/` backup — DONE 2026-07-19.** Corpus + `ingest_queue.xlsx`
backed up to Google Drive (PLAN.md #1). Restore not yet verified — do not
assume a restore would work until tested. `recovery/` remains a separate,
narrower backup of specific deleted rows only, not the corpus — the two are
not the same thing.

**4. `ingest_helloao.py` unconverted.** Own Supabase REST `.insert()` path, not
routed through `shared_ingest`. Live API, resume-safe, genuinely blocks the 8
further HelloAO commentaries in PLAN.md #27. This is the real chokepoint gap.

**5. `ingest_commentaries.py` — RESOLVED 2026-07-22, retired.** Read a
hardcoded `/tmp` SQLite dump that no longer exists; hard-shaped to one
collection's schema, no scraping or generic-format capability. Script
deleted, all dead references removed (commit `d4826dc`). **Framing:**
HistoricalChristianFaith commentary GROWTH is DEFERRED, not cut — rebuildable
from scratch later against a real source if Alex wants more from this
collection. The 307 documents already ingested (Augustine, Chrysostom,
Desert Fathers, Wesley, C.S. Lewis, etc. — under the `HistoricalChristianFaith
Commentaries Database` source) are untouched, remain live in the corpus, and
have no overlap with the HelloAO public-domain commentary set. See #15/#16
below for two findings about those 307 documents that surfaced during the
retirement audit and still need review.

**6. Guest→account conversion unlinked.** Email-confirmation session handoff
likely broken (cookie-vs-localStorage mismatch). Trace in `docs/audits/GUEST_AUTH_AUDIT.md`.

**7. Auth CTA inconsistencies.** `/library/authors` bypasses BetaGate and opens
the wrong modal mode; `/home` shows signup CTAs to logged-in users; dead
`AuthButton.tsx`. Trace in `docs/audits/BUTTON_AUTH_UX_AUDIT.md`.

**8. Proposition backfill gap.** Unlicensed docs ingested before the wiring have
no propositions. Alias gaps remain for several entities — re-ingesting their
content sentinels silently. Counts unverified; query live.

**9. v4 propositions prompt — decision pending.**
`propositions.py::EXTRACTION_PROMPT_V4` exists (line 76), committed `ff0652c`,
but unwired. v3 remains the default (line 139). Calling v4 requires
`prompt_version="v4"` explicitly. Tested on 18 documents
(`docs/audits/proposition-v3-v4-comparison-2026-07-16.md`): median word count 40 → 60,
still short of the 80–150 target. Adopt, iterate, or discard — and if adopt,
decide on backfill.

**10. Precept Austin raw-source gap.** Fewer raw scrape files remain in
`sources/precept_austin/raw/` than there are ingested documents — some documents
have no local raw backing if re-verification is ever needed. Not cross-checked
against the excerpt-less figure in #8.

**11. `verify_chunk_alignment.py` docstring is stale.** Describes
`shared_ingest.py` insert modes (`psycopg2_batch` / `rest_per_chunk`) that no
longer exist — `insert_mode` was introduced in `fb575ae` (2026-07-13) and
collapsed away in the all-or-nothing rewrite.

**12. `jewish_perspectives` table is orphaned.** 2 rows, zero code references
outside migrations and docs.

**13. SP2 Study Panel — no real screen-reader pass has ever been run.**
Phase 9 (2026-07-17) fixed 5 real keyboard/ARIA gaps and verified them via
real keyboard interaction plus live accessibility-tree/DOM inspection
(`aria-expanded`, `aria-label`, `role`, `data-*` attributes) — that is a
genuine, live-proven check of what a screen reader *would* consume, but it
is not the same as actually running one. No VoiceOver, NVDA, or other
screen reader has been used against this panel. Don't treat Phase 9 as
having closed this — it closed the 5 gaps the structural/keyboard audit
could find and prove; a real screen-reader listen could still surface
things that audit can't (announcement phrasing, reading order, timing).

**14. Hebrew lexicon permission gate — SP2 Study Panel excludes Hebrew
entirely because of this, do not assume it's cleared.** The Hebrew brief
lexicon (TBESH) is NOT covered by the same CC BY 4.0 grant that clears
Greek (TBESG, TFLSJ) — its definitions are third-party (Abridged BDB,
Online Bible) and need Online Bible's own permission before use in any
project. Greek is unaffected; SP2's Interlinear/word-study rows already
only ever render Greek, structurally (confirmed live, Phase 8). Full
reasoning: PLAN.md Open Decisions #11. Gates any future Hebrew
interlinear/word-study work specifically — do not build against TBESH
until that permission is obtained.

**15. Attribution-mode mismatch on the 307 HistoricalChristianFaith
documents (found 2026-07-22, during `ingest_commentaries.py` retirement
audit — not touched, logged for a future session).** The importer's insert
set `citation_mode='citable'` on every row, but all 307 live rows are
actually `silent_context` — named historical authors (Augustine, Chrysostom,
Wesley, C.S. Lewis, etc.) currently serving as unattributed background
rather than cited by name. Unclear whether this is intentional (same
posture as other silent-context sources) or a bug that silently dropped
attribution for named, identifiable authors — given attribution is core to
Rhemata's positioning (CLAUDE.md invariant 7), this needs a real decision,
not an assumption either way.

**16. Possible copyright flag: C.S. Lewis document marked public_domain
(found 2026-07-22, same audit as #15).** One of the 307 documents is
attributed to C.S. Lewis (d. 1963), sitting under a source marked
`license_status='public_domain'`, `visibility='shown'`. Lewis's death year
makes public-domain status doubtful in most jurisdictions — this wants a
fail-closed review (verify the actual copyright status of this specific
text, or gate it) before treating it as safely servable at face value.

---

## Resolved — removed from the blocker list 2026-07-17

- **Quote verifier "blocker" — premise dissolved.** Commit `0af69a6`
  (2026-07-10) retired the verified-verbatim-quote claim from the product
  entirely. `system_prompt.txt`, `POSITIONING.md`, and
  `docs/how-rhemata-handles-sources.md` now state paraphrase-and-cite as the
  live posture and verbatim quoting as future/planned. Nothing is waiting on a
  verifier. The old CLAUDE.md decision entry permitting "verbatim retrieval
  quotes up to 50 words" is stale and was removed.
- **Migration 058 "uncommitted"** — false. Committed `72476b7` (2026-07-09),
  working tree clean.
- **"Only ingest.py converted"** — false. `ingest.py`, `ingest_magazine.py`,
  `ingest_preceptaustin.py`, `ingest_lexicon.py` all route through
  `shared_ingest`. See blockers #4 and #5 for what actually remains.
- **v4 prompt "uncommitted"** — false. Committed `ff0652c`. Unwired is still
  true; see #9.

---

## Undocumented, now known

- `scripts/ingest_lexicon_runner.py` (2026-07-14) — batching/pacing driver over
  `ingest_lexicon`, drives `shared_ingest.ingest_document()` in checkpointed
  slices. Committed, was absent from the scripts table.
- `scripts/verify_chunk_alignment.py` — standalone embedding/content alignment
  spot-checker. Committed, was absent from the scripts table. See #11.

---

## Mobile UI

- **Pass A shipped:** floating-panel chat layout, full-bleed mobile shell,
  bottom tab bar (Study · Chat · Discover) hiding on keyboard focus via
  `ChatFocusContext`, circular floating menu button. **Correction
  2026-07-23:** the tab bar itself is now gated off by default behind
  `NEXT_PUBLIC_FULL_NAV_ENABLED` (chat-only beta, see the session entry at
  the top of this file) — this line describes what Pass A originally
  built, not what currently renders by default. `NEXT_PUBLIC_FULL_NAV_ENABLED=true`
  restores it exactly as described here.
- **Pass B pending:** `UsageRing` was pulled from the mobile top bar and has not
  been remounted in the sidebar drawer.

---

## Next

1. **#13 — route `ingest_helloao.py` through `shared_ingest`.** Sole remaining
   chokepoint conversion. Unblocks HelloAO commentary growth (#27) only, not
   corpus growth generally.
2. **#14 remainder — folder renames** (`lexicon/`→`stepbible/`,
   `documents/`→`inbox/`) + drop `jewish_perspectives` table.
3. **#15 — staging Supabase + backup/restore test.** Gates the core-serving
   band (#16–20).

(#1 — `sources/` backup — DONE 2026-07-19, restore not yet verified; see Open
blockers #3. Oldest item on the plan, no longer next.)

SP track: SP2 done (Phases 1–9), SP3 dissolved 2026-07-15 (absorbed into SP2
Phase 8, shipped `9415f11`). SP4 (teacher card content) shipped 2026-07-18 and
is now fully signed off (Alex's authenticated production pass, 2026-07-21 — all
four checks passed; see the reconciliation entry at the top of this file). SP
panel refinement (#42.5) is also done: Phase 1 (reference-persistence fix)
shipped 2026-07-19; Phase 2 (floating overlay) shipped 2026-07-21 (`fe310e2`),
built but not yet production-verified itself (see above). **Next SP item is #43
(SP5, mobile bottom-sheet)**, which reuses the overlay's shared open/swap/close
model. #38 (SP0 mobile mockup) completion status unverified — confirm before assuming.

#11/#12 are DONE (reuse path resolved 2026-07-13). The old "#11 → #12 → SP3"
chain no longer holds — all three links resolved.
