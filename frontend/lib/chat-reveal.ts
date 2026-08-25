const BASE_CHARS_PER_SECOND = 250;
const MAX_REVEAL_SECONDS = 6;

export function revealCharsPerSecond(answerLength: number): number {
  return Math.max(
    BASE_CHARS_PER_SECOND,
    Math.ceil(Math.max(0, answerLength) / MAX_REVEAL_SECONDS),
  );
}
