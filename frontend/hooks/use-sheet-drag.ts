"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { dragOutcome, dragTranslate, overlayOpacity } from "@/lib/sheet-drag";

/** Movement before the gesture is claimed, so a tap never nudges the sheet. */
const CLAIM_THRESHOLD_PX = 6;

/** Must match the drag-dismiss slide duration in globals.css. */
const DISMISS_ANIMATION_MS = 200;

/**
 * True when the touch started inside a region the user has already scrolled.
 * A drag there belongs to that scroller, not to the sheet -- otherwise reading
 * a long Profile pane and pulling down would throw the whole sheet away.
 */
function isInsideScrolledRegion(target: Element | null, root: Element): boolean {
  let node: Element | null = target;
  while (node && node !== root) {
    if (node.scrollHeight > node.clientHeight + 1 && node.scrollTop > 0) {
      return true;
    }
    node = node.parentElement;
  }
  return false;
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return reduced;
}

interface UseSheetDragOptions {
  /** The host dialog's open state -- used to reset between presentations. */
  open: boolean;
  /** False on desktop, where the surface is an ordinary centred dialog. */
  enabled: boolean;
  onDismiss: () => void;
}

/**
 * Drag-to-dismiss for a bottom sheet: the surface tracks the finger and either
 * springs back or slides away on release. Thresholds live in lib/sheet-drag.ts.
 *
 * Under `prefers-reduced-motion` nothing follows the finger; the same
 * distance/velocity decision still runs on release, so the gesture keeps
 * working, it simply does not animate.
 */
export function useSheetDrag({ open, enabled, onDismiss }: UseSheetDragOptions) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const startRef = useRef<{ y: number; t: number } | null>(null);
  const claimedRef = useRef(false);
  const dismissTimerRef = useRef<number | null>(null);

  const [offset, setOffset] = useState(0);
  // State, not a ref: the overlay's opacity is derived from it during
  // render, and a ref read there is not guaranteed to be consistent.
  const [sheetHeight, setSheetHeight] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  const reduceMotion = usePrefersReducedMotion();

  const reset = useCallback(() => {
    startRef.current = null;
    claimedRef.current = false;
    setDragging(false);
    setOffset(0);
  }, []);

  // A fresh presentation always starts square, whatever ended the last one.
  // Adjusted during render rather than in an effect -- React's documented
  // "adjusting state when a prop changes" pattern, the same shape app/page.tsx
  // uses for pin state. An effect would also leave one painted frame showing
  // the previous gesture's offset before it reset.
  const [resolvedOpen, setResolvedOpen] = useState(open);
  if (open !== resolvedOpen) {
    setResolvedOpen(open);
    if (open) {
      setDismissing(false);
      setDragging(false);
      setOffset(0);
      // The gesture refs need no reset here: onPointerDown re-initialises both
      // unconditionally, so a new gesture can never inherit a stale one.
    }
  }

  useEffect(() => {
    return () => {
      if (dismissTimerRef.current !== null) {
        window.clearTimeout(dismissTimerRef.current);
      }
    };
  }, []);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!enabled || dismissing) return;
      // Touch and pen only: a mouse drag on a dialog is a selection, not a
      // dismissal, and desktop keeps the ordinary centred presentation anyway.
      if (event.pointerType === "mouse") return;
      if (isInsideScrolledRegion(event.target as Element | null, event.currentTarget)) {
        return;
      }
      startRef.current = { y: event.clientY, t: event.timeStamp };
      claimedRef.current = false;
    },
    [enabled, dismissing],
  );

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const start = startRef.current;
      if (!start) return;
      const deltaY = event.clientY - start.y;

      if (!claimedRef.current) {
        // Only a downward move claims the gesture, so upward scrolling and
        // horizontal nav swipes are never stolen.
        if (deltaY < CLAIM_THRESHOLD_PX) return;
        claimedRef.current = true;
        setSheetHeight(event.currentTarget.getBoundingClientRect().height);
        setDragging(true);
        event.currentTarget.setPointerCapture(event.pointerId);
      }

      if (!reduceMotion) setOffset(dragTranslate(deltaY));
    },
    [reduceMotion],
  );

  const onPointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      const start = startRef.current;
      const claimed = claimedRef.current;
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Throws if capture was already lost; nothing to unwind.
      }
      if (!start || !claimed) {
        reset();
        return;
      }

      const deltaY = event.clientY - start.y;
      // Average velocity over the gesture. A flick reads high here; a slow
      // drag reads low but clears the distance threshold on its own.
      const elapsed = Math.max(1, event.timeStamp - start.t);

      if (dragOutcome(deltaY, deltaY / elapsed) === "spring-back") {
        reset();
        return;
      }

      startRef.current = null;
      claimedRef.current = false;
      setDragging(false);

      if (reduceMotion) {
        setOffset(0);
        onDismiss();
        return;
      }

      // Slide the rest of the way out, then close. Closing first would snap
      // the sheet back to rest for a frame before the exit animation ran.
      // Measured fresh here rather than read from sheetHeight: on a very fast
      // flick the claim's state update may not have re-rendered this callback
      // yet, and a zero distance would skip the slide entirely.
      setDismissing(true);
      setOffset(event.currentTarget.getBoundingClientRect().height);
      dismissTimerRef.current = window.setTimeout(onDismiss, DISMISS_ANIMATION_MS);
    },
    [onDismiss, reduceMotion, reset],
  );

  const onPointerCancel = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      try {
        event.currentTarget.releasePointerCapture(event.pointerId);
      } catch {
        // Ignore.
      }
      reset();
    },
    [reset],
  );

  return {
    rootRef,
    dragging,
    dismissing,
    offset,
    overlayOpacity: overlayOpacity(offset, sheetHeight),
    dragHandlers: enabled
      ? { onPointerDown, onPointerMove, onPointerUp, onPointerCancel }
      : {},
  };
}
