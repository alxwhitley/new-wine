"use client";

import type { StatusBadge as StatusBadgeType } from "./corpus-types";

const cls: Record<string, string> = {
  Complete: "bg-primary/15 text-primary",
  Ongoing: "bg-secondary text-secondary-foreground",
  Partial: "bg-muted text-muted-foreground",
  "Not Started": "bg-muted/50 text-muted-foreground/50",
};

export function StatusBadge({ status }: { status: StatusBadgeType }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cls[status] ?? ""}`}>
      {status}
    </span>
  );
}
