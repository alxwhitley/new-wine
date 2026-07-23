Inline Study Panel — Full Context Summary
For any Claude session picking this up cold. This is the original design spec for Rhemata's inline study panel, decision-complete as of July 2026 — now shipped as SP2 (see Status below). Read this in full for the design rationale before doing anything; for current build status and where the shipped version superseded this original spec, see PLAN.md #40 and rhemata-status.md.

What this is
Rhemata currently has two equal-weight surfaces: Chat (RAG Q&A) and Study Mode (interlinear, commentary, word study). This feature is an experiment in collapsing that split — chat stays the main surface, and a study panel slides in from the right when the user taps something in a chat answer, so the app never feels like it's navigating away from the conversation.
This is additive, not a replacement. The existing Study page survives untouched as a fallback. If the experiment doesn't work, nothing is lost. Ships behind a flag; beta users see it (not just Alex).
Status: SHIPPED as SP2 — all 10 phases DONE, live-verified (2026-07-17; PLAN.md #40, rhemata-status.md). This line originally read "decision-complete, not scheduled" when the spec was written (July 2026, pre-build) — kept below verbatim as historical design rationale, not current status. Word-level original-language study (this doc's Phase 3) shipped too, absorbed into SP2 Phase 8. Mobile (this doc's Phase 6, tracked as PLAN.md's SP5) remains genuinely unscheduled.
Two implementation details below are now stale after the 2026-07-22 panel refinement (PLAN.md #42.5, rhemata-status.md) — flagged here rather than rewritten, since the rest of this doc's design rationale still holds: (1) "nav slides away" in The core interaction, below — the sidebar no longer collapses when the panel opens; it stays fixed, and the chat card narrows instead. (2) "automatically borrows extra width... shrinks back... width follows need" in The interlinear, below — the panel's width is now fixed permanently regardless of which section is open; Interlinear wraps to new rows instead of expanding the panel or scrolling horizontally.

The core interaction
Verse references ("Romans 8:26") and named teacher mentions ("Derek Prince") inside chat answers get a subtle visual treatment — a thin warm-colored underline, same text color as the rest of the sentence, that strengthens slightly on hover. Nothing shouts. Tap one, and:

The left navigation sidebar and the study panel move at the same time, in one motion — nav slides away, panel slides in from the right to about a third of the screen. Chat keeps about two-thirds and stays where it is, still scrollable.
The panel shows a verse card (verse text, then "your teachers on this verse" — paraphrased positions from named teachers in the corpus, the one thing no generic Bible app offers) or a teacher card (bio, works held in the corpus, their position on the topic at hand).
Closing the panel reverses the motion exactly: panel slides out, nav slides back in.

The navigation model (important — this changed mid-design)
There is no back-button stack. The panel is one card that unfolds, not a series of screens you navigate through. Teacher notes expand inline inside the verse card. Cross-referenced verses expand their text inline in the same card. Depth = scrolling further down a richer card, not jumping between screens.
The one exception: tapping a specific word inside the interlinear (see below) opens a deep word-study view, and that's the only place in the panel with a back button.
The interlinear
The verse card has three expandable rows: Interlinear, Translations, Cross-references — in that order, with Interlinear meant to be the visually obvious thing to try first. Expanding it breaks the verse into original-language words, each shown as a three-layer stack (original word / transliteration / short English gloss). Greek reads left-to-right; Hebrew reads right-to-left (word order), with each word's transliteration and gloss still reading normally — this is the standard convention used by real Hebrew interlinears, confirmed via research, not assumed.
Tapping a word opens the deep-study view: lexical root, a Strong's-style ID, grammatical parsing, plain-language definition, and a notable-frequency note when relevant (e.g. "occurs only here in the New Testament" — this kind of detail is a strong engagement point for this audience).
The panel automatically borrows extra width while the interlinear is open, and shrinks back to a third when it's collapsed. Width follows need; there's no user-managed "wide mode."
Hard dependency: this whole capability requires the original-language lexicon/dictionary corpus fully ingested with word-level tagging, which is gated on the ingest_lexicon.py chokepoint conversion (the highest-risk item in the current ingest band) plus a licensed word-level text source. Do not build Phase 3 before that's confirmed done. Hebrew (OT) is scoped as its own work item beyond Greek (NT) within that phase.
Reference detection rules (what gets underlined, what doesn't)

Verse ranges (e.g. "Romans 8:26–28") get one underline; the interlinear pages through the range one verse at a time.
Vague references ("verse 26," "that chapter") never get underlined — only exact resolved verses do.
Biblical figures (Paul, Moses, etc.) are never tappable — only named teachers actually in the corpus are.
User's own chat messages are never underlined. But if a user mentions a verse, the answer generation is required to explicitly name that verse back so it gets underlined in the response.
Every occurrence of a repeated verse reference gets underlined.
Teacher names: first mention in an answer is the full name and underlined; every mention after that in the same answer is a short form with no underline. Verse abbreviations ("Rom 8:26"), by contrast, get underlined every time.
Fail-quiet is a hard rule: a reference only gets underlined if it resolves with high confidence to a real verse or a real teacher entity already in the corpus. No confident match = plain prose text, no exception. An underline that opens to nothing is treated as a trust failure, especially since beta users will see this.
Underlines fade in only after an answer finishes streaming — never mid-stream.

Pinning
Small stack, cap of 4. Tapping a pinned item's chip again unpins it. Pins are scoped to the current conversation and are saved — they survive closing and reopening the app, but don't follow you to a different conversation.
Important: once the panel is closed, the only way back in is clicking an underlined reference again — unless pins exist. When pins exist, a small quiet tab sits on the right edge of the screen showing pin access; tapping it reopens the panel straight to the pinned items. No pins, no tab. This makes pins load-bearing, not a nice-to-have — they ship in the same phase as the panel shell itself.
The verse card, exactly

Verse text — one fixed translation only for now, no user choice yet.
"Your teachers on this verse" — 2–3 paraphrased positions, most-relevant-first when determinable, with "more" if others exist. If no teacher in the corpus addresses the verse, the panel says so directly ("None of your teachers address this verse directly yet") and adds that content is added daily — chosen deliberately over silently hiding the section, because hiding gaps would be a small betrayal of the product's whole anti-flattening thesis.
The three expandable rows described above.

The panel never acts on its own
This is a hard rule, stated explicitly by the founder: the panel changes only when the user directly interacts with it. It never auto-opens, auto-updates, or reacts to what's happening in the chat on its own — even if a whole new answer is about one verse. The moment the panel starts deciding what to show, it becomes the "synthetic oracle" this whole product is positioned against.
The escape hatch
No expanded/full-width panel mode exists in this design. Instead the panel offers a quiet "Open in Study" action that jumps to the full Study page with context carried over. Study's job during this experiment is to catch the deep sessions the panel is too small for.
Checkpoint, deliberately placed after Phase 4 of the build: review whether the standalone Study page is still being used at all. Any decision to fold Study permanently into this panel is made explicitly by the founder at that point — never by drift.
Mobile (last phase, not yet mocked)
Opens as a full-screen bottom sheet over the chat when a reference is tapped — chat is not visible while the sheet is up (a deliberate override of an earlier multi-height sheet concept). Drag down to close; chat may peek through only mid-drag as a hint that it's still there underneath. Typing in chat requires closing the sheet first. This is the one part of Phase 0 not yet prototyped as an HTML mockup.
Explicitly out of scope for this track

Opening the actual cited source document/passage behind a chat answer's paraphrase (a different, harder feature — "citation-to-source-passage" — possibly a future track on its own).
Retrofitting old conversations so past answers get clickable references — only new answers, generated after this ships, carry the reference data.
Selecting text inside the panel to ask a follow-up question in chat (a natural next idea, deliberately deferred).
User-selectable Bible translations.

Build phases (each sized to one load-bearing change per work session, per house discipline)

Phase 0 — Chat-based HTML mockups. Desktop version (underlines, panel slide, verse card, interlinear, pins) is built and approved. Mobile full-screen sheet mockup is the one remaining piece.
Phase 1 — Backend only: new answers generate hidden pointers linking specific words to exact verses/teachers, with fail-quiet resolution and the answer-writing rules (always name referenced verses, first-mention-full-name for teachers). No visible change yet.
Phase 2 — Frontend build: underlines, the sliding panel, the verse card with inline teacher expansion and the honest empty state, the pin system with its edge-tab re-entry, the Open-in-Study handoff, keyboard/screen-reader support. This is the first version beta users see, behind a kill switch.
Phase 3 — The three tool rows built out for real: Interlinear (Greek, then Hebrew as separate scoped work), Translations, Cross-references, the width-borrowing behavior, the word deep-study view. Hard-gated on the lexicon ingest conversion finishing first.
Phase 4 — Teacher card content built out in full.
Phase 6 — Mobile full-screen sheet with the drag-to-close gesture. (Phase 5 was folded into Phase 2 since pins are load-bearing for the panel shell.)


Why this design, in one paragraph
The product's whole thesis is anti-flattening: named human voices with citations, not a synthetic oracle answering from nowhere. The risk of a chat-first redesign is that it looks and feels more like the oracle it argues against. The mitigations threaded through every decision above — fail-quiet underlines that never lie, a panel that only moves when the user moves it, an honest empty state instead of a hidden gap, and citations that open into the actual named teacher's real position — are all there so that this UX experiment makes the thesis more visible, not less.
