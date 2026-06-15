"use client";

// Flip to true when Stripe is wired up to enable the upgrade button.
const BILLING_ENABLED = false;

interface WeeklyLimitCardProps {
  limit: number;
  resets: string; // ISO date "YYYY-MM-DD" from 429 body
  onNewChat?: () => void;
}

function formatResetDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function WeeklyLimitCard({ limit, resets, onNewChat }: WeeklyLimitCardProps) {
  const resetLabel = formatResetDate(resets);

  return (
    <div role="alert" className="rounded-xl border border-border bg-card p-4 max-w-prose">
      <p className="text-sm font-semibold text-card-foreground mb-1">
        You&apos;ve reached your weekly limit
      </p>
      <p className="text-sm text-muted-foreground leading-relaxed mb-1">
        You&apos;ve used all {limit} of your free queries this week.
      </p>
      <p className="text-xs text-muted-foreground mb-4">
        Your queries reset {resetLabel}.
      </p>
      <div className="flex items-center gap-3">
        <button
          disabled={!BILLING_ENABLED}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          Upgrade — $8/month
        </button>
        {!BILLING_ENABLED && (
          <span className="text-xs text-muted-foreground">Coming soon</span>
        )}
      </div>
      {onNewChat && (
        <button
          onClick={onNewChat}
          className="mt-3 text-sm text-primary hover:underline transition-colors"
        >
          Start a new conversation →
        </button>
      )}
    </div>
  );
}
