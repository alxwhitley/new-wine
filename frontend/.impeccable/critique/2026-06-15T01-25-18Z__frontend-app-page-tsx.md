---
target: frontend/app/page.tsx
total_score: 27
p0_count: 0
p1_count: 0
p2_count: 3
p3_count: 2
timestamp: 2026-06-15T01-25-18Z
slug: frontend-app-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | chatError now SR-announced; streaming has no cancel indicator |
| 2 | Match Between System / Real World | 4 | Theological language and chat metaphor both on point |
| 3 | User Control and Freedom | 2 | No streaming cancel; WeeklyLimitCard has no inline new-chat escape |
| 4 | Consistency and Standards | 4 | Hamburger/aria-label fixed, text-destructive fixed; border-b gap remains (minor) |
| 5 | Error Prevention | 2 | No progressive usage warning before 6-search anonymous limit |
| 6 | Recognition Rather Than Recall | 3 | Suggestions now visible on mobile; history behind hamburger on mobile |
| 7 | Flexibility and Efficiency | 2 | No / keyboard shortcut; sidebar is the only new-chat path |
| 8 | Aesthetic and Minimalist Design | 3 | Clean and focused; text-balance on h2 now correct |
| 9 | Error Recovery | 2 | chatError visible + SR-announced; no retry CTA or next step |
| 10 | Help and Documentation | 1 | No help system, no onboarding, citations not signaled as interactive |
| **Total** | | **27/40** | **Acceptable** |

## Anti-Patterns Verdict

**LLM assessment**: No slop. Floating panel + gradient scroll fade + time-aware greeting + domain-specific suggestion chips are all considered choices. No gradient text, no side-stripe cards, no hero-metric blocks. Mobile top bar (hamburger + spacer + ring, no identity) is the only place the page reads as unfinished.

**Deterministic scan**: detect.mjs → [] — clean. No hardcoded hex, no inline style props, no banned hover handlers.

## Overall Impression

All four P1/P2 issues from the previous run are fixed. Score moves from 25 → 27. Remaining gaps: error recovery offers no action, weekly limit card dead-ends on mobile, no keyboard shortcut. Everything left is fast-fix polish or H10 (help/onboarding) investment.

## What's Working

1. **Mobile suggestions unblocked** — Removing the !isMobile guard was the right call. Three chips appear on mobile as full-width stacked buttons.
2. **Floating panel with gradient scroll fade** — sticky top gradient is subtle, intentional, product-grade.
3. **role="alert" aria-live="polite" on errors** — Both error locations now SR-announced. Biggest a11y gap from last run, cleanly resolved.

## Priority Issues

**[P2] Chat errors offer no recovery path**
chatError renders as text-destructive with role="alert" — correctly visible. But input is not disabled on error, so the user CAN type again; they just don't know that.
Why: Error text with no affordance is discovery-dependent recovery. Mobile users close the tab.
Fix: Store lastQuery in state. Show "Try again" button below error that calls handleSend(lastQuery).
Command: /impeccable harden

**[P2] WeeklyLimitCard is a dead end on mobile**
When weeklyLimitDetail fires, only escape is sidebar hamburger → tap "New Chat" — 3 taps, zero discoverability.
Why: Casey sees a blocked card and doesn't find the sidebar. Closes the tab.
Fix: Add inline "Start a new conversation →" link at bottom of WeeklyLimitCard. Passed onNewChat prop or Link href="/".
Command: /impeccable polish

**[P2] Home top bar missing border-b border-border**
Authors page (app/library/authors/page.tsx:66): border-b border-border on h-14 top bar. Home page: none. Identical element, different treatment. Visible when navigating between pages.
Fix: Add border-b border-border to home top bar div.
Command: /impeccable polish

**[P3] No / keyboard shortcut to focus chat input**
Library search wires / keydown to its input. Home page — primary interaction surface — does not.
Fix: useEffect for keydown on "/", gated on activeElement not being input/textarea.
Command: /impeccable polish

**[P3] UsageRing on mobile has no accessible label**
No aria-label on wrapper, no role="img". SR users hear nothing.
Fix: aria-label="{used} of {limit} queries used this week" on the md:hidden div wrapper.
Command: /impeccable audit

## Persona Red Flags

**Jordan (Confused First-Timer, mobile)**: Sees error text, doesn't know to type again. Abandons. Root: error with no recovery CTA.

**Alex (Power User)**: Reaches for / key — nothing. After weekly limit, 3-tap detour to start over. Both friction points compound across sessions.

**Casey (Mobile, church)**: Hits weekly limit, sees disabled upgrade button and "Coming soon", no forward path. Closes tab. Root: no inline escape from limit card.

## Minor Observations

- bottomRef scrollIntoView smooth fires on every messages/chatLoading change — yanks users back while reading. Fix: only scroll when within ~100px of bottom.
- key={i} on message list uses array index instead of message.messageId — fragile.
- Greeting flashes on hydration (SSR renders default, useEffect updates to time-specific). Fix with suppressHydrationWarning on h2.
- SUGGESTIONS hardcoded in component — belongs in config for seasonal updates.

## Questions to Consider

- "What if the error state matched iMessage's failed SMS pattern — query bubble grayed out, tap-to-retry arrow attached?"
- "Would '8 / 50' text next to the ring be more honest than the ring metaphor alone on mobile?"
- "What if WeeklyLimitCard's CTA changed based on auth state — 'Create a free account' for guests, 'Start a new conversation' for metered users?"
