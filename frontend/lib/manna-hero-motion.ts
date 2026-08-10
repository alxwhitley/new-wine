export type MannaHeroTransforms = {
  backgroundScale: number;
  backgroundY: number;
  copyOpacity: number;
  copyY: number;
  productScale: number;
  productY: number;
  foregroundOpacity: number;
  foregroundScale: number;
  foregroundY: number;
};

const STATIC_TRANSFORMS: MannaHeroTransforms = {
  backgroundScale: 1,
  backgroundY: 0,
  copyOpacity: 1,
  copyY: 0,
  productScale: 1,
  productY: 0,
  foregroundOpacity: 0.78,
  foregroundScale: 1,
  foregroundY: 0,
};

export function clampHeroProgress(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function lerp(start: number, end: number, progress: number): number {
  return Number((start + (end - start) * progress).toFixed(4));
}

export function getMannaHeroTransforms(
  progress: number,
  reducedMotion = false,
): MannaHeroTransforms {
  if (reducedMotion) return STATIC_TRANSFORMS;

  const value = clampHeroProgress(progress);
  const foregroundReveal = clampHeroProgress(value / 0.35);

  return {
    backgroundScale: lerp(1, 1.08, value),
    backgroundY: lerp(0, -3, value),
    copyOpacity: lerp(1, 0, value),
    copyY: lerp(0, -24, value),
    productScale: lerp(0.82, 1, value),
    productY: lerp(34, 0, value),
    foregroundOpacity: lerp(0, 0.78, foregroundReveal),
    foregroundScale: lerp(1, 1.08, value),
    foregroundY: lerp(12, -4, value),
  };
}
