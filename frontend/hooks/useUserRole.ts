import { useState, useEffect } from "react";

interface CacheEntry {
  role: string;
  displayName: string | null;
}

// Module-level cache keyed by access token — survives component remounts
const _cache = new Map<string, CacheEntry>();

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
    if (entry) {
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
        _cache.set(token, { role: r, displayName: d });
        setRole(r);
        setDisplayName(d);
      })
      .catch(() => {
        _cache.set(token, { role: "user", displayName: null });
        setRole("user");
        setDisplayName(null);
      });
  }, [token]);

  function updateDisplayName(name: string) {
    if (!token) return;
    const entry = _cache.get(token);
    if (entry) _cache.set(token, { ...entry, displayName: name });
    setDisplayName(name);
  }

  return { role, displayName, updateDisplayName };
}
