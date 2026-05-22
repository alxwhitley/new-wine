"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

const ADMIN_EMAIL = "alxwhitley@gmail.com";

interface SourceToggle {
  id: string;
  source_identifier: string;
  identifier_type: string;
  label: string;
  enabled: boolean;
  doc_count: number | null;
}

function ToggleSwitch({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="relative inline-flex h-6 w-11 items-center rounded-full transition-colors cursor-pointer"
      style={{ backgroundColor: enabled ? "#b49238" : "#3c3c38" }}
    >
      <span
        className="inline-block h-4 w-4 rounded-full bg-white transition-transform"
        style={{ transform: enabled ? "translateX(24px)" : "translateX(4px)" }}
      />
    </button>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-3">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg border p-4 animate-pulse"
          style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
        >
          <div className="space-y-2">
            <div className="h-3.5 rounded bg-border w-48" />
            <div className="h-3 rounded bg-border w-24" />
          </div>
          <div className="h-6 w-11 rounded-full bg-border" />
        </div>
      ))}
    </div>
  );
}

export default function AdminPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const router = useRouter();
  const [sources, setSources] = useState<SourceToggle[]>([]);
  const [loading, setLoading] = useState(true);

  // Auth guard
  useEffect(() => {
    if (authLoading) return;
    if (!user || user.email !== ADMIN_EMAIL) {
      router.replace("/");
    }
  }, [user, authLoading, router]);

  // Fetch sources
  useEffect(() => {
    if (!accessToken) return;

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/admin/sources`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch sources");
        return res.json();
      })
      .then((data) => setSources(data.sources ?? []))
      .catch(() => setSources([]))
      .finally(() => setLoading(false));
  }, [accessToken]);

  const handleToggle = useCallback(
    async (id: string) => {
      if (!accessToken) return;

      // Optimistic update
      setSources((prev) =>
        prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
      );

      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/admin/sources/${id}`,
          {
            method: "PATCH",
            headers: { Authorization: `Bearer ${accessToken}` },
          }
        );
        if (!res.ok) throw new Error("Toggle failed");
      } catch {
        // Revert on failure
        setSources((prev) =>
          prev.map((s) => (s.id === id ? { ...s, enabled: !s.enabled } : s))
        );
      }
    },
    [accessToken]
  );

  // Don't render until auth check completes
  if (authLoading || !user || user.email !== ADMIN_EMAIL) {
    return null;
  }

  const globalToggles = sources.filter((s) => s.identifier_type === "global");
  const sourceToggles = sources.filter((s) => s.identifier_type !== "global");

  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: "#1f1e1d", color: "#e6e6e6" }}
    >
      <div className="mx-auto max-w-2xl px-6 py-12">
        <a
          href="/study"
          className="text-sm hover:underline"
          style={{ color: "#c1c1b8" }}
        >
          &larr; Back to Study
        </a>

        <h1
          className="mt-6 mb-10 text-3xl font-serif"
          style={{ color: "#b49238" }}
        >
          Admin
        </h1>

        {loading ? (
          <SkeletonRows />
        ) : (
          <>
            {/* Global settings */}
            {globalToggles.length > 0 && (
              <section className="mb-10">
                <h2
                  className="text-xs font-medium uppercase tracking-wide mb-4"
                  style={{ color: "#c1c1b8" }}
                >
                  Global Settings
                </h2>
                <div className="space-y-3">
                  {globalToggles.map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center justify-between rounded-lg border p-4"
                      style={{
                        borderColor: "#3c3c38",
                        backgroundColor: "#262624",
                      }}
                    >
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {s.label}
                        </p>
                      </div>
                      <ToggleSwitch
                        enabled={s.enabled}
                        onToggle={() => handleToggle(s.id)}
                      />
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Source toggles */}
            <section>
              <h2
                className="text-xs font-medium uppercase tracking-wide mb-4"
                style={{ color: "#c1c1b8" }}
              >
                Source Toggles
              </h2>
              <div className="space-y-3">
                {sourceToggles.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between rounded-lg border p-4"
                    style={{
                      borderColor: "#3c3c38",
                      backgroundColor: "#262624",
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        {s.label}
                      </p>
                      {s.doc_count !== null && (
                        <p className="text-xs mt-0.5" style={{ color: "#c1c1b8" }}>
                          {s.doc_count.toLocaleString()} document{s.doc_count !== 1 ? "s" : ""}
                        </p>
                      )}
                    </div>
                    <ToggleSwitch
                      enabled={s.enabled}
                      onToggle={() => handleToggle(s.id)}
                    />
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
