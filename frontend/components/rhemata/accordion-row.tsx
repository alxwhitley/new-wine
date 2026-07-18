"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// SP2 Phase 7: generic replacement for study-panel.tsx's old ToolRowStub —
// same visual shape (border-b, chevron rotation), but renders real children
// instead of hardcoded "coming soon" copy.

export function AccordionRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between py-3 text-sm text-foreground hover:text-foreground/80 transition-colors cursor-pointer"
      >
        {label}
        <ChevronDown
          className={cn(
            "h-4 w-4 text-muted-foreground transition-transform motion-reduce:transition-none",
            open && "rotate-180"
          )}
        />
      </button>
      {open && <div className="pb-3">{children}</div>}
    </div>
  );
}
