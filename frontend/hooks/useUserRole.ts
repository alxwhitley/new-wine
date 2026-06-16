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

  useEffect(() => {
    if (!token) {
      setRole(null);
      setDisplayName(null);
      return;
    }
    const entry = _cache.get(token);
    if (entry && Date.now() - entry.timestamp < ROLE_CACHE_TTL_MS) {
      setRole(entry.role);
      setDisplayName(entry.displayName);
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
