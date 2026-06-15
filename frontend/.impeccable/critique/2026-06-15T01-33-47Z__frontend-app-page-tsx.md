---
target: frontend/app/page.tsx
total_score: 29
p0_count: 0
p1_count: 0
p2_count: 1
p3_count: 2
timestamp: 2026-06-15T01-33-47Z
slug: frontend-app-page-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | UsageRing now SR-labeled; streaming state still has no cancel indicator |
| 2 | Match Between System / Real World | 4 | Theological language and chat metaphor both solid |
| 3 | User Control and Freedom | 3 | WeeklyLimitCard now has inline escape; error has retry; no streaming cancel |
| 4 | Consistency and Standards | 4 | Top bar border-b now matches authors page; all token usage consistent |
| 5 | Error Prevention | 2 | No progressive usage warning for anonymous users approaching 6-search limit |
| 6 | Recognition Rather Than Recall | 3 | Suggestions visible on mobile; history behind hamburger on mobile |
| 7 | Flexibility and Efficiency | 3 | / shortcut now wired; sidebar still the only new-chat accelerator |
| 8 | Aesthetic and Minimalist Design | 3 | Clean and focused; nothing extraneous |
| 9 | Error Recovery | 3 | "Try again" button next to chatError; clear label; action available |
| 10 | Help and Documentation | 1 | No help system, no onboarding, no contextual guidance |
| **Total** | | **29/40** | **Good** |

## Anti-Patterns Verdict

**LLM assessment**: No slop. Floating panel, gradient scroll fade, time-aware greeting, domain-specific suggestion chips — all deliberate. No reflex patterns.

**Deterministic scan**: detect.mjs → [] — clean for the third consecutive run.

## Overall Impression

Three critique passes: 25 → 27 → 29. Fixes have been systematic; page has moved from Acceptable to Good. Remaining ceiling is H5 (no anonymous usage feedback) and H10 (no help at all). Both require features, not polish.

## What's Working

1. **/ shortcut now live** — pressing / anywhere focuses the chat textarea. Right shortcut for the right surface.
2. **WeeklyLimitCard "Start a new conversation →"** — dead-end card now has a forward path. One tap, clear label, wired to handleNewChat.
3. **"Try again" next to errors** — transforms passive error text into actionable state. handleRetry correctly clears messages before re-firing.

## Priority Issues

**[P2] No progressive usage signal for anonymous users**
Anonymous users get 6 searches before the login wall fires with zero feedback about consumption. weeklyUsage ring only shown for authenticated users.
Why: Surprise walls cause abandonment. User who knows they're on last search can make it count.
Fix: Add guest_usage: { used, limit } to SSE meta. Surface "2 of 6 free searches used" below suggestions in empty state or after each response.
Command: /impeccable harden

**[P3] Auto-scroll fights users reading long responses**
bottomRef.current?.scrollIntoView fires on every messages/chatLoading change. Users scrolled up to re-read get yanked back.
Why: Scholarly users reading long theological responses scroll up. Getting yanked back mid-read is jarring.
Fix: Track isNearBottom ref. Only scrollIntoView when near bottom (scrollTop + clientHeight >= scrollHeight - 150px).
Command: /impeccable harden

**[P3] Greeting h2 flashes on hydration**
SSR renders the useState default; useEffect updates to time-specific string. One-frame flash on first paint.
Fix: Add suppressHydrationWarning to the greeting <h2>.
Command: /impeccable polish

## Persona Red Flags

**Jordan (Confused First-Timer, mobile)**: Hits login wall on 7th search with no warning. Confused why it stopped working. Root: no progressive signal.

**Alex (Power User)**: / shortcut works. No Cmd+K, no conversation search, no bulk paths. Thin accelerator set.

**Riley (Stress Tester)**: Scrolls up during streaming, gets yanked back. Repeats. Root: unconditional auto-scroll.

## Minor Observations

- key={i} on message list still uses array index instead of message.messageId.
- "Try again" button in empty state (lines 218-220) almost never visible — errors surface in chat view. Consider removing.
- SUGGESTIONS still hardcoded in component body.
- Citation number pills have no tooltip — new users don't know to click them.

## Questions to Consider

- "The auto-scroll problem is solvable in 15 lines. What's blocking it?"
- "Would a '2 searches left — sign up for free' nudge convert users, or feel pushy in a church context?"
- "Is H10 at 1 acceptable for a trusted community tool, or does someone in the audience need hand-holding?"
