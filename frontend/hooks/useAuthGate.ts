"use client";

import { useCallback, useState } from "react";

export type AuthMode = "signin" | "signup";

/**
 * Single owner of auth-modal state.
 *
 * This replaces four hand-copied `openAuthGate` functions that had already
 * drifted apart — one page skipped the beta gate entirely. The beta code is
 * no longer a separate modal, so there is nothing left to branch on here:
 * the auth card asks for the code itself when the device still needs it.
 *
 * `defaultMode` is the entry point's intent. Marketing surfaces open on
 * signup; in-app surfaces open on signin, because anyone already inside the
 * app has an account.
 */
export function useAuthGate(defaultMode: AuthMode = "signin") {
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState<AuthMode>(defaultMode);
  const [authReason, setAuthReason] = useState<string | undefined>(undefined);

  const openAuth = useCallback(
    (mode: AuthMode = defaultMode, reason?: string) => {
      setAuthMode(mode);
      setAuthReason(reason);
      setAuthOpen(true);
    },
    [defaultMode],
  );

  const closeAuth = useCallback(() => {
    setAuthOpen(false);
    setAuthReason(undefined);
  }, []);

  return { authOpen, authMode, authReason, openAuth, closeAuth };
}
