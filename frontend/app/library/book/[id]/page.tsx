"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { getBookExcerpts } from "@/lib/api";
import type { BookExcerptResponse } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

function cleanChunkContent(raw: string): string {
  const lines = raw.split("\n");
  const clean: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      clean.push("");
      continue;
    }
    if (trimmed.startsWith("[")) continue;
    if (trimmed.startsWith("#")) continue;
    if (trimmed.startsWith("---")) continue;
    if (trimmed.includes("|") && trimmed.split("|").length >= 3) continue;
    if (trimmed === trimmed.toUpperCase() && trimmed.length > 3 && /[A-Z]/.test(trimmed)) continue;
    clean.push(trimmed);
  }
  return clean.join("\n").trim();
}

export default function BookExcerptPage() {
  const { id } = useParams<{ id: string }>();
  const { accessToken, loading: authLoading } = useAuth();
  const [data, setData] = useState<BookExcerptResponse | null>(null);
  const [loading, setLoading] = useState(true);

  // Resets loading synchronously during render when the effect's own
  // trigger condition newly becomes true (React's documented "adjusting
  // state when a prop changes" pattern) instead of as the effect's own
  // first statement.
  const loadKey = id && !authLoading ? `${id}|${accessToken ?? ""}` : null;
  const [resolvedLoadKey, setResolvedLoadKey] = useState<string | null>(null);
  if (loadKey !== resolvedLoadKey) {
    setResolvedLoadKey(loadKey);
    if (loadKey) setLoading(true);
  }

  useEffect(() => {
    if (!id || authLoading) return;
    getBookExcerpts(id, accessToken)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id, accessToken, authLoading]);

  // Use quotes if available, otherwise fall back to cleaned chunks
  const excerpts: { id: string; text: string }[] = data
    ? data.quotes && data.quotes.length > 0
      ? data.quotes.map((q) => ({ id: q.id, text: q.quote_text }))
      : (data.chunks || [])
          .map((c) => ({ id: c.id, text: cleanChunkContent(c.content) }))
          .filter((c) => c.text.length >= 100)
    : [];

  const doc = data?.document;

  return (
    <div className="min-h-screen bg-background">
      {/* Sticky header */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 50,
          backgroundColor: "#1f1e1d",
          borderBottom: "1px solid #3c3c38",
          padding: "14px 24px",
          display: "flex",
          alignItems: "center",
        }}
      >
        <Link
          href="/library"
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-gold transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Library
        </Link>
        <div className="flex-1 text-center">
          {doc && (
            <span className="font-sans text-lg" style={{ color: "#e6e6e0" }}>
              {doc.title}
            </span>
          )}
        </div>
        <div style={{ minWidth: "120px", textAlign: "right" }}>
          {doc && (
            <span className="text-sm" style={{ color: "#888880" }}>
              {doc.author}
            </span>
          )}
        </div>
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="mx-auto" style={{ maxWidth: "720px", padding: "40px 24px" }}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ padding: "32px 0", borderBottom: i < 2 ? "1px solid #2a2926" : "none" }}>
              <div className="animate-pulse" style={{ height: "16px", backgroundColor: "#2a2926", borderRadius: "4px", width: "90%", marginBottom: "12px" }} />
              <div className="animate-pulse" style={{ height: "16px", backgroundColor: "#2a2926", borderRadius: "4px", width: "80%", marginBottom: "12px" }} />
              <div className="animate-pulse" style={{ height: "16px", backgroundColor: "#2a2926", borderRadius: "4px", width: "70%" }} />
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      {!loading && doc && (
        <div className="mx-auto" style={{ maxWidth: "720px", padding: "40px 24px" }}>
          {/* Hero heading */}
          <h1 className="font-sans text-3xl font-semibold" style={{ color: "#e6e6e0", lineHeight: 1.3 }}>
            {doc.title}
          </h1>
          <p className="mt-3" style={{ fontSize: "16px", color: "#d4b96a" }}>
            {doc.author}
          </p>
          <div style={{ borderTop: "1px solid #3c3c38", margin: "32px 0" }} />

          {/* Excerpt feed */}
          {excerpts.length === 0 ? (
            <p className="text-center" style={{ color: "#888880", marginTop: "40px" }}>No excerpts available</p>
          ) : (
            excerpts.map((item, idx) => (
              <div
                key={item.id}
                style={{
                  padding: "32px 0",
                  borderBottom: idx < excerpts.length - 1 ? "1px solid #2a2926" : "none",
                }}
              >
                <p style={{ color: "#c1c1b8", fontSize: "16px", lineHeight: 1.8, whiteSpace: "pre-wrap" }}>
                  {item.text}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
