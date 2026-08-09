"use client";

import { useRef } from "react";
import { BookOpen, ExternalLink } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetClose,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import type { Citation } from "@/lib/api";

interface SourcePanelProps {
  citation: Citation | null;
  citationIndex: number | null;
  isOpen: boolean;
  onClose: () => void;
}

function SourcePanelContent({
  citation,
  citationIndex,
}: {
  citation: Citation;
  citationIndex: number | null;
}) {
  return (
    <>
      {/* Citation badge */}
      {citationIndex !== null && (
        <div className="mb-4">
          <span className="inline-flex items-center justify-center rounded px-2 py-1 text-xs font-medium bg-secondary text-secondary-foreground">
            [{citationIndex}]
          </span>
        </div>
      )}

      {/* Title */}
      <h2 className="font-sans text-lg font-semibold text-foreground mb-2 leading-tight">
        {citation.document_title || "Unknown Source"}
      </h2>

      {/* Author */}
      {citation.author && (
        <p className="text-sm text-muted-foreground mb-6">
          {citation.author}
        </p>
      )}

      {/* Source link */}
      {citation.url && (
        <a
          href={citation.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-6 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline transition-colors"
        >
          View source
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}

      {/* Excerpt */}
      <div className="rounded-lg bg-background p-4 border border-border">
        <p className="text-sm text-foreground leading-relaxed italic">
          &ldquo;{citation.content}&rdquo;
        </p>
      </div>
    </>
  );
}

function SourcePanelHeader() {
  return (
    <div className="flex items-center gap-2 border-b border-border px-6 py-4">
      <BookOpen className="h-4 w-4 text-muted-foreground" />
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Source</span>
    </div>
  );
}

export function SourcePanel({ citation, citationIndex, isOpen, onClose }: SourcePanelProps) {
  const isMobile = useIsMobile();

  // Swipe-to-close (mobile grab handle only) — mirrors study-panel.tsx #43.
  // Pointer Events are used because React marks touch listeners passive by
  // default, which would silently break preventDefault; pointer events are not.
  // 44px threshold matches this codebase's existing min touch-target convention.
  const swipeStartYRef = useRef<number | null>(null);
  const SWIPE_CLOSE_THRESHOLD_PX = 44;

  function handleHandlePointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    swipeStartYRef.current = event.clientY;
    // Capture the pointer so move/up events keep firing on this element even if
    // the pointer leaves the grab handle during the swipe.
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function handleHandlePointerMove(event: React.PointerEvent<HTMLButtonElement>) {
    if (swipeStartYRef.current === null) return;
    // Suppress incidental native touch behavior only while a drag is tracked;
    // a plain tap never reaches a meaningful delta, so the tap-to-close path
    // (SheetClose onClick) keeps firing normally.
    event.preventDefault();
  }

  function handleHandlePointerUp(event: React.PointerEvent<HTMLButtonElement>) {
    const startY = swipeStartYRef.current;
    swipeStartYRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // releasePointerCapture throws if capture was already lost; safe to ignore.
    }
    if (startY === null) return;
    const deltaY = event.clientY - startY;
    // Downward swipe past threshold closes; upward or below threshold is a no-op.
    if (deltaY >= SWIPE_CLOSE_THRESHOLD_PX) {
      onClose();
    }
  }

  function handleHandlePointerCancel(event: React.PointerEvent<HTMLButtonElement>) {
    swipeStartYRef.current = null;
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Ignore.
    }
  }

  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent
        side={isMobile ? "bottom" : "right"}
        className={isMobile ? "h-[85vh] overflow-hidden rounded-t-xl p-0 bg-popover" : "w-96 max-w-96 p-0 bg-popover"}
        showCloseButton={!isMobile}
      >
        <SheetTitle className="sr-only">
          {citation?.document_title || "Source"}
        </SheetTitle>
        <SheetDescription className="sr-only">
          Source details and excerpt
        </SheetDescription>
        {isMobile ? (
          <div className="flex h-full flex-col">
            {/* Mobile grab handle — tap closes (SheetClose, untouched); a
                downward swipe past threshold also closes, reusing the same
                onClose. touch-none keeps incidental native gestures off this
                one element while a drag is tracked. */}
            <SheetClose asChild>
              <button
                className="flex shrink-0 items-center justify-center py-3 touch-none"
                aria-label="Close"
                onPointerDown={handleHandlePointerDown}
                onPointerMove={handleHandlePointerMove}
                onPointerUp={handleHandlePointerUp}
                onPointerCancel={handleHandlePointerCancel}
              >
                <span className="h-1 w-10 rounded-full bg-border" />
              </button>
            </SheetClose>
            <SourcePanelHeader />
            {citation && (
              <div className="flex-1 overflow-y-auto px-6 pt-4 pb-[calc(1rem+env(safe-area-inset-bottom))]">
                <SourcePanelContent citation={citation} citationIndex={citationIndex} />
              </div>
            )}
          </div>
        ) : (
          <>
            <SourcePanelHeader />
            {citation && (
              <div className="p-6 overflow-y-auto max-h-[calc(100vh-65px)]">
                <SourcePanelContent citation={citation} citationIndex={citationIndex} />
              </div>
            )}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
