"use client";

import { Pin } from "lucide-react";
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
//
// Panel refinement Phase 5: same outline Pin icon as the panel's own
// header pin-this action (visually ties the two together as "pin family"
// rather than one being a bookmark and the other a pin) plus a live count
// badge — pins.length was already read right here for the title tooltip,
// so no new data plumbing was needed. Badge styling matches the existing
// pending-count convention in AdminModal.tsx (bg-primary pill, hidden at
// zero) rather than inventing a new one. Icon, badge, and tooltip only —
// zero change to pin behavior/storage/caps below.
export function PinDropdown({ pins, isSignedIn, onSelectPin }: PinDropdownProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          title={pins.length > 0 ? `${pins.length} pinned verse${pins.length === 1 ? "" : "s"}` : "Pinned verses"}
          data-study-trigger
          className="relative flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Pin className="h-4 w-4" />
          {pins.length > 0 && (
            <span className="absolute -right-0.5 -top-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
              {pins.length}
            </span>
          )}
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
