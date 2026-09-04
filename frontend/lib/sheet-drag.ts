/**
 * Pure geometry and decision logic for the drag-to-dismiss sheet gesture.
 *
 * Kept free of React and the DOM so the thresholds are directly testable --
 * the same split as composer-viewport.ts. The hook in hooks/use-sheet-drag.ts
 * owns pointer plumbing and calls into this.
 */

/** A drag this far dismisses on distance alone, however slowly it was made. */
export const DISMISS_DISTANCE_PX = 120;

/** A flick at or above this speed dismisses early. */
export const DISMISS_VELOCITY_PX_PER_MS = 0.5;

/**
 * A flick must still have travelled this far. Without it, the velocity spike
 * at the end of a tap reads as a dismissal.
 */
export const FLICK_MIN_DISTANCE_PX = 40;

/** How much an upward drag is damped. Higher is stiffer. */
export const UPWARD_RESISTANCE = 4;

/**
 * Screen offset for a given finger delta. Downward tracks 1:1; upward is
 * damped so the sheet resists rather than detaching from the top edge.
 */
export function dragTranslate(deltaY: number): number {
  return deltaY >= 0 ? deltaY : deltaY / UPWARD_RESISTANCE;
}

/**
 * What should happen when the finger lifts. `velocityPxPerMs` is signed the
 * same way as `deltaY` -- positive is downward.
 */
export function dragOutcome(
  deltaY: number,
  velocityPxPerMs: number,
): "dismiss" | "spring-back" {
  if (deltaY >= DISMISS_DISTANCE_PX) return "dismiss";
  if (
    velocityPxPerMs >= DISMISS_VELOCITY_PX_PER_MS &&
    deltaY >= FLICK_MIN_DISTANCE_PX
  ) {
    return "dismiss";
  }
  return "spring-back";
}

/**
 * Multiplier for the backdrop's opacity as the sheet is dragged away, so the
 * background reappears in step with the gesture rather than snapping at the
 * end. Returns 1 (fully dimmed) when the height is unknown.
 */
export function overlayOpacity(translateY: number, sheetHeight: number): number {
  if (sheetHeight <= 0) return 1;
  const progress = Math.min(1, Math.max(0, translateY / sheetHeight));
  return 1 - progress;
}
