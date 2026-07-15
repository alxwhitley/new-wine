// Kill switch for the whole Inline Study Panel feature. Defaults to enabled
// unless explicitly set to the string "false" — matches this repo's existing
// flag conventions (e.g. BILLING_ENABLED in weekly-limit-card.tsx).
export function isStudyPanelEnabled(): boolean {
  return process.env.NEXT_PUBLIC_STUDY_PANEL_ENABLED !== "false";
}
