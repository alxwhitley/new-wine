"use client";

// Long-conversation-handoff nudge (docs/superpowers/specs/2026-08-26-long-
// conversation-handoff.md). Trigger threshold lives here, not scattered
// across callers -- one number to change if Alex revises it.
//
// Deliberately says nothing about dollars or tokens: the trigger is cost-
// based server-side (Alex is covering beta spend directly), but the reason
// this is a nudge and not a hard cap is product philosophy, not cost
// (CLAUDE.md: "the goal is sending users back to real teachers... a feature
// that makes a user say 'I don't need my pastor, I have New Wine' gets
// killed") -- so the copy stays about conversation focus, never spend.
//
// Copy reviewed 2026-08-26 against PRODUCT.md Section 8 (voice: Grounded,
// Convinced, Warm, Unhurried -- plain and direct, never SaaS-speak) and
// POSITIONING.md's anti-reference to generic AI chat ("could be talking to
// anyone about anything"). The first draft ("keeps each one focused and
// easy to come back to") was exactly that -- boilerplate productivity-app
// copy with no New Wine identity, and no honest claim behind it. This
// version instead states a real, verifiable fact about the product (past
// conversations stay in the sidebar history) rather than a vague
// convenience claim. "Start a new conversation ->" is copied verbatim from
// WeeklyLimitCard's existing button -- Design Principle #4, earned
// familiarity: same action, same words, every time it appears. Approved by
// Alex 2026-08-26 (spec Open question 5, closed).
export const CONVERSATION_LENGTH_NUDGE_THRESHOLD_USD = 0.5;

interface ConversationLengthNudgeProps {
  onNewChat: () => void;
  onDismiss: () => void;
}

export function ConversationLengthNudge({ onNewChat, onDismiss }: ConversationLengthNudgeProps) {
  return (
    <div role="status" className="rounded-xl border border-border bg-card p-4 max-w-prose">
      <p className="text-sm font-semibold text-card-foreground mb-1">
        This has been a long conversation
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        Starting fresh for your next question keeps things clear — this one
        stays in your history if you want it again.
      </p>
      <div className="flex items-center gap-3">
        <button
          onClick={onNewChat}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:opacity-90"
        >
          Start a new conversation →
        </button>
        <button
          onClick={onDismiss}
          className="text-xs text-muted-foreground hover:underline transition-colors"
        >
          Not now
        </button>
      </div>
    </div>
  );
}
