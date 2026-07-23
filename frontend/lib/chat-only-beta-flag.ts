// Kill switch for full navigation (Study + Discover) during the chat-only
// beta. Inverse of study-panel-flag.ts's convention: this one defaults to
// HIDDEN when unset, so production ships beta-correct with no env change
// required. Set NEXT_PUBLIC_FULL_NAV_ENABLED=true to restore the bottom
// tab bar and the desktop sidebar nav (Chat/Discover/Study links).
export function isFullNavEnabled(): boolean {
  return process.env.NEXT_PUBLIC_FULL_NAV_ENABLED === "true";
}
