"use client";

import { Bookmark } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { referenceKey, referenceLabel, type StudyReference } from "@/lib/study-reference";

interface PinDropdownProps {
  pins: StudyReference[];
  isSignedIn: boolean;
  onSelectPin: (reference: StudyReference) => void;
}

// SP2 Phase 5: replaces the edge-tab re-entry point. Reachable regardless
// of which conversation is active — pins are global, not per-conversation.
// Not itself the guest-prompt surface (that's the pin button inside the
// panel, Task 16) — for a signed-out guest with no pins, this just shows a
// short informational line.
export function PinDropdown({ pins, isSignedIn, onSelectPin }: PinDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          title={pins.length > 0 ? `${pins.length} pinned verse${pins.length === 1 ? "" : "s"}` : "Pinned verses"}
          className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Bookmark className={cn("h-4 w-4", pins.length > 0 && "fill-current")} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        {pins.length === 0 ? (
          <p className="px-2 py-1.5 text-sm text-muted-foreground">
            {isSignedIn ? "No pinned verses yet." : "Sign in to save verses."}
          </p>
        ) : (
          pins.map((pin) => (
            <DropdownMenuItem key={referenceKey(pin)} onSelect={() => onSelectPin(pin)}>
              {referenceLabel(pin)}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
