const MIN_COMPOSER_MAX_HEIGHT = 96;
const MAX_COMPOSER_HEIGHT = 192;
const VIEWPORT_HEIGHT_RATIO = 0.32;

/**
 * Keep multiline prompts useful without letting them crowd the send control
 * out of a keyboard-shortened phone or tablet viewport.
 */
export function composerMaxHeight(viewportHeight: number): number {
  return Math.min(
    MAX_COMPOSER_HEIGHT,
    Math.max(MIN_COMPOSER_MAX_HEIGHT, Math.floor(viewportHeight * VIEWPORT_HEIGHT_RATIO)),
  );
}
