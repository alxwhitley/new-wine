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

interface FeedbackEntry {
  id: string;
  question: string;
  rating: string;
  comment: string | null;
  created_at: string;
  user_id: string | null;
  anon_id: string | null;
  source_type: string | null;
  source_document_id: string | null;
}

type FeedbackTab = "chat_answer" | "commentary" | "word_study";

const FEEDBACK_TABS: { key: FeedbackTab; label: string }[] = [
  { key: "chat_answer", label: "Chat Answers" },
  { key: "commentary", label: "Commentary" },
  { key: "word_study", label: "Word Studies" },
];

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
  const [feedbackEntries, setFeedbackEntries] = useState<FeedbackEntry[]>([]);
  const [feedbackLoading, setFeedbackLoading] = useState(true);
  const [feedbackTab, setFeedbackTab] = useState<FeedbackTab>("chat_answer");

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

  // Fetch feedback (re-fetch on tab change)
  useEffect(() => {
    if (!accessToken) return;

    setFeedbackLoading(true);
    const params = new URLSearchParams();
    params.set("source_type", feedbackTab);

    fetch(`${process.env.NEXT_PUBLIC_API_URL}/feedback?${params}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch feedback");
        return res.json();
      })
      .then((data) => setFeedbackEntries(data.feedback ?? []))
      .catch(() => setFeedbackEntries([]))
      .finally(() => setFeedbackLoading(false));
  }, [accessToken, feedbackTab]);

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
  const commentaryToggles = sources.filter(
    (s) => s.identifier_type === "source_name" && s.label.includes("Commentary")
  );
  const commentaryIds = new Set(commentaryToggles.map((s) => s.id));
  const sourceToggles = sources.filter(
    (s) => s.identifier_type !== "global" && !commentaryIds.has(s.id)
  );

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
            <section className="mb-10">
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

            {/* Commentary toggles */}
            {commentaryToggles.length > 0 && (
              <section className="mb-10">
                <h2
                  className="text-xs font-medium uppercase tracking-wide mb-4"
                  style={{ color: "#c1c1b8" }}
                >
                  Commentaries
                </h2>
                <div className="space-y-3">
                  {commentaryToggles.map((s) => (
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
            )}

            {/* Feedback */}
            <section>
              <h2
                className="text-xs font-medium uppercase tracking-wide mb-4"
                style={{ color: "#c1c1b8" }}
              >
                Feedback
              </h2>

              {/* Tabs */}
              <div className="flex gap-6 mb-6" style={{ borderBottom: "1px solid #3c3c38" }}>
                {FEEDBACK_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setFeedbackTab(tab.key)}
                    className="pb-2 text-sm font-medium cursor-pointer transition-colors"
                    style={{
                      color: feedbackTab === tab.key ? "#b49238" : "#888780",
                      borderBottom: feedbackTab === tab.key ? "2px solid #b49238" : "2px solid transparent",
                      marginBottom: "-1px",
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {feedbackLoading ? (
                <SkeletonRows />
              ) : feedbackEntries.length === 0 ? (
                <div
                  className="rounded-lg border p-6 text-center"
                  style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
                >
                  <p className="text-sm" style={{ color: "#c1c1b8" }}>No feedback yet</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {feedbackEntries.map((f) => (
                    <div
                      key={f.id}
                      className="rounded-lg border p-4"
                      style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
                    >
                      <div className="flex items-start gap-3">
                        <span
                          className="mt-1.5 inline-block h-2 w-2 rounded-full shrink-0"
                          style={{
                            backgroundColor: f.rating === "thumbs_up" ? "#4ade80" : "#ef4444",
                          }}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-foreground">{f.question}</p>
                          {f.comment && (
                            <p className="text-xs mt-1" style={{ color: "#c1c1b8" }}>
                              {f.comment}
                            </p>
                          )}
                          <p className="text-xs mt-2" style={{ color: "#888780" }}>
                            {new Date(f.created_at).toLocaleDateString("en-US", {
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
