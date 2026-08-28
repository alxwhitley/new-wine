const START_PROGRESS = 0.06;
const MAX_PROGRESS = 0.94;
const TIME_CONSTANT_MS = 20_000;

export const LOADING_PHRASES = [
  "Searching the corpus…",
  "Reading relevant sources…",
  "Building from the evidence…",
  "Checking names and attributions…",
  "Verifying source references…",
] as const;

/**
 * Approximate wait progress from elapsed time alone. Eases toward, but
 * never reaches, MAX_PROGRESS -- the real completion signal is the
 * answer arriving, not this estimate.
 */
export function estimateLoadingProgress(elapsedMs: number): number {
  const safeElapsed = Math.max(0, elapsedMs);
  const eased = 1 - Math.exp(-safeElapsed / TIME_CONSTANT_MS);
  const progress = START_PROGRESS + (MAX_PROGRESS - START_PROGRESS) * eased;
  return Math.min(MAX_PROGRESS, progress);
}

export function loadingPhraseIndex(progress: number): number {
  const bucket = Math.floor(progress * LOADING_PHRASES.length);
  return Math.min(LOADING_PHRASES.length - 1, Math.max(0, bucket));
}
