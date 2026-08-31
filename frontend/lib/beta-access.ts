/**
 * Beta access gate.
 *
 * The code literal lives here, alone and exported, so that a future
 * product-name sweep breaks `beta-access.test.mts` instead of production.
 * It was silently rewritten once already (`rhema` -> `newwine`, commit
 * a6f1575) and shipped broken, because a password literal does not read as
 * a product-name reference when scanning a rename diff.
 */
export const BETA_ACCESS_CODE = "rhema";

/** Follows the existing `newwine_anon_id` client-storage convention. */
export const BETA_ACCESS_STORAGE_KEY = "newwine_beta_access";

/** Pre-migration per-tab key. Read for upgrade only; never written. */
export const LEGACY_SESSION_KEY = "beta_access";

const GRANTED = "1";

type ReadableStore = { getItem(key: string): string | null };
type WritableStore = ReadableStore & { setItem(key: string, value: string): void };

export type BetaAccessStores = {
  local: WritableStore | null;
  session: ReadableStore | null;
};

/**
 * Every storage touch is guarded: Safari private mode throws on access, and a
 * gate that crashes the page is strictly worse than one that re-prompts.
 */
function read(store: ReadableStore | null, key: string): string | null {
  if (!store) return null;
  try {
    return store.getItem(key);
  } catch {
    return null;
  }
}

function write(store: WritableStore | null, key: string, value: string): void {
  if (!store) return;
  try {
    store.setItem(key, value);
  } catch {
    // Access is still granted for this render; it just will not persist.
  }
}

export function browserStores(): BetaAccessStores {
  if (typeof window === "undefined") return { local: null, session: null };
  return {
    local: (() => { try { return window.localStorage; } catch { return null; } })(),
    session: (() => { try { return window.sessionStorage; } catch { return null; } })(),
  };
}

/**
 * Codes are handed out verbally and by message, so they arrive with stray
 * whitespace and inconsistent case. Normalizing cannot cause a false accept:
 * the comparison target is a single lowercase word.
 */
export function normalizeBetaCode(input: string): string {
  return input.trim().toLowerCase();
}

export function isBetaCodeValid(input: string): boolean {
  return normalizeBetaCode(input) === BETA_ACCESS_CODE;
}

/**
 * True when this device has already cleared the gate. A session gated under
 * the old per-tab key is upgraded in place, so the move to per-device memory
 * re-prompts nobody who was already through.
 */
export function hasBetaAccess(stores: BetaAccessStores = browserStores()): boolean {
  if (read(stores.local, BETA_ACCESS_STORAGE_KEY) === GRANTED) return true;
  if (read(stores.session, LEGACY_SESSION_KEY) === GRANTED) {
    write(stores.local, BETA_ACCESS_STORAGE_KEY, GRANTED);
    return true;
  }
  return false;
}

export function grantBetaAccess(stores: BetaAccessStores = browserStores()): void {
  write(stores.local, BETA_ACCESS_STORAGE_KEY, GRANTED);
}
