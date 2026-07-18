"use client";

import { useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

// SP2 Phase 7: generic replacement for study-panel.tsx's old ToolRowStub —
// same visual shape (border-b, chevron rotation), but renders real children
// instead of hardcoded "coming soon" copy.
//
// SP2 Phase 8: optionally controlled (open/onOpenChange), for the Interlinear
// row specifically — its open state needs to be visible to page.tsx for
// width-borrowing (Task 30). Uncontrolled usage (Commentaries, Pastors' Notes)
// is unchanged: omit both props and it manages its own state exactly as before.

export function AccordionRow({
  label,
  children,
  open: controlledOpen,
  onOpenChange,
}: {
  label: string;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  function toggle() {
    const next = !open;
    if (isControlled) {
      onOpenChange?.(next);
    } else {
      setInternalOpen(next);
    }
  }

  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={toggle}
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
