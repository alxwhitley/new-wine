"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center">
      <h1 className="text-lg font-medium text-foreground">Something went wrong</h1>
      {/* axe: text-destructive against bg-background measured 4.02:1, short of
          WCAG AA's 4.5:1 -- same scoped override as pastors-notes.tsx, not a
          change to the shared --destructive token. */}
      <p className="text-sm text-[hsl(0_84%_72%)]">
        An unexpected error occurred. You can try again or head back home.
      </p>
      <div className="flex items-center gap-4">
        <button
          onClick={() => unstable_retry()}
          className="text-[13px] text-primary hover:underline transition-colors"
        >
          Try again
        </button>
        <Link href="/" className="text-[13px] text-primary hover:underline transition-colors">
          Back to home
        </Link>
      </div>
    </main>
  );
}
