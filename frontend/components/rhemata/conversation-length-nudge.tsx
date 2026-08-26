"use client";

// Long-conversation-handoff nudge (docs/superpowers/specs/2026-08-26-long-
// conversation-handoff.md). Trigger threshold lives here, not scattered
// across callers -- one number to change if Alex revises it.
//
// Deliberately says nothing about dollars or tokens: the trigger is cost-
// based server-side (Alex is covering beta spend directly), but the reason
// this is a nudge and not a hard cap is product philosophy, not cost
// (CLAUDE.md: "the goal is sending users back to real teachers... a feature
// that makes a user say 'I don't need my pastor, I have Rhemata' gets
// killed") -- so the copy stays about conversation focus, never spend. Draft
// copy, not yet reviewed by Alex (spec Open question 5).
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
        Starting a new conversation for your next question keeps each one
        focused and easy to come back to.
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
