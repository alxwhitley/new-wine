import { useState, useEffect } from "react";

interface CacheEntry {
  role: string;
  displayName: string | null;
  timestamp: number;
}

// Module-level cache keyed by access token — survives component remounts.
// Entries expire after 5 minutes so a newly-approved contributor sees their
// updated role without having to sign out and back in.
const _cache = new Map<string, CacheEntry>();
const ROLE_CACHE_TTL_MS = 5 * 60 * 1000;

export function useUserRole(accessToken: string | null | undefined) {
  const token = accessToken ?? null;

  const cached = token ? _cache.get(token) : null;
  const [role, setRole] = useState<string | null>(cached?.role ?? null);
  const [displayName, setDisplayName] = useState<string | null>(
    cached?.displayName ?? null
  );

  // Resolve synchronously during render when token changes to null
  // (React's documented "adjusting state when a prop changes" pattern).
  // Date.now() is impure and can't be called during render
  // (react-hooks/purity), so the cache-freshness check itself stays in
  // the effect below, not here.
  const [resolvedToken, setResolvedToken] = useState(token);
  if (token !== resolvedToken) {
    setResolvedToken(token);
    if (!token) {
      setRole(null);
      setDisplayName(null);
    }
  }

  useEffect(() => {
    if (!token) return;
    const entry = _cache.get(token);
    if (entry && Date.now() - entry.timestamp < ROLE_CACHE_TTL_MS) {
      // Still deferred to a microtask, not a bare synchronous call, to
      // satisfy react-hooks/set-state-in-effect the same way the real
      // fetch path below already does via .then().
      Promise.resolve().then(() => {
        setRole(entry.role);
        setDisplayName(entry.displayName);
      });
      return;
    }
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/pastors-notes/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        const r = data.role ?? "user";
        const d = data.display_name ?? null;
        _cache.set(token, { role: r, displayName: d, timestamp: Date.now() });
        setRole(r);
        setDisplayName(d);
      })
      .catch(() => {
        _cache.set(token, { role: "user", displayName: null, timestamp: Date.now() });
        setRole("user");
        setDisplayName(null);
      });
  }, [token]);

  function updateDisplayName(name: string) {
    if (!token) return;
    const entry = _cache.get(token);
    if (entry) _cache.set(token, { ...entry, displayName: name, timestamp: Date.now() });
    setDisplayName(name);
  }

  return { role, displayName, updateDisplayName };
}
