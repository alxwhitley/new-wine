/**
 * Time-paced staging for the answer-wait indicator.
 *
 * The steps communicate the answer path's real ORDER of work, not its exact
 * completion timing -- nothing here is synchronized to the backend, and the
 * answer arriving remains the only true completion signal. The last step is
 * therefore never "finished"; it stays active until the answer replaces the
 * whole indicator.
 */

export const LOADING_STEPS = [
  "Searching the corpus",
  "Reading relevant sources",
  "Building from the evidence",
  "Checking names and attributions",
  "Verifying source references",
] as const;

/**
 * Elapsed time at which each step becomes the active one.
 *
 * Paced so the final step is active by ~18.4s, just inside the ~20s median
 * answer. Stated as explicit onsets rather than derived from an easing curve:
 * a step list has no arc to ease, and the boundaries are the design decision,
 * so they belong in the open where they can be read and re-tuned.
 */
const STEP_ONSETS_MS = [0, 1_700, 4_900, 9_500, 18_400] as const;

/** Index into LOADING_STEPS of the step currently being worked on. */
export function activeStepIndex(elapsedMs: number): number {
  const elapsed = Math.max(0, elapsedMs);
  let index = 0;
  for (let i = 0; i < STEP_ONSETS_MS.length; i++) {
    if (elapsed >= STEP_ONSETS_MS[i]) index = i;
  }
  return index;
}
