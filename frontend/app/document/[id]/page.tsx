"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, BookOpen, Loader2 } from "lucide-react";
import { getDocument, Document, Chunk } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export default function DocumentPage() {
  const params = useParams<{ id: string }>();
  const { accessToken, loading: authLoading } = useAuth();
  const [document, setDocument] = useState<Document | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Resets loading synchronously during render when the effect's own
  // trigger condition newly becomes true (React's documented "adjusting
  // state when a prop changes" pattern) instead of as the effect's own
  // first statement.
  const loadKey = params.id && !authLoading ? `${params.id}|${accessToken ?? ""}` : null;
  const [resolvedLoadKey, setResolvedLoadKey] = useState<string | null>(null);
  if (loadKey !== resolvedLoadKey) {
    setResolvedLoadKey(loadKey);
    if (loadKey) setLoading(true);
  }

  useEffect(() => {
    if (!params.id || authLoading) return;
    getDocument(params.id, accessToken)
      .then((res) => {
        setDocument(res.document);
        setChunks(res.chunks);
      })
      .catch(() => setError("Failed to load document"))
      .finally(() => setLoading(false));
  }, [params.id, accessToken, authLoading]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !document) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
        <p className="text-sm text-destructive">{error || "Document not found"}</p>
        <Link href="/" className="text-[13px] text-primary hover:underline transition-colors">
          Back to home
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto max-w-[620px] px-8 py-10">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-primary transition-colors mb-10"
        >
          <ArrowLeft className="h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
          Back
        </Link>

        <div className="flex items-start gap-3.5 mb-2">
          <BookOpen className="h-5 w-5 shrink-0 mt-1 text-primary" strokeWidth={1.8} />
          <div>
            <h1 className="font-sans text-2xl font-semibold leading-snug text-foreground text-balance">
              {document.title}
            </h1>
            <p className="text-sm text-muted-foreground mt-1.5">
              {document.author}
              {document.year ? ` · ${document.year}` : ""}
              {document.source_type ? ` · ${document.source_type}` : ""}
            </p>
          </div>
        </div>

        {document.topic_tags && document.topic_tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-5 mb-10 ml-9">
            {document.topic_tags.map((tag) => (
              <span key={tag} className="text-xs bg-secondary text-secondary-foreground rounded-md px-2 py-0.5">
                {tag}
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-3.5 mt-8">
          {chunks.map((chunk) => (
            <div key={chunk.id} className="rounded-lg p-5 bg-card text-sm text-foreground leading-[1.8]">
              {chunk.content}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
