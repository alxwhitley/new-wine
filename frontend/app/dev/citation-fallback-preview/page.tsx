"use client";

import { notFound } from "next/navigation";
import { ChatMessage } from "@/components/rhemata/chat-message";
import type { Citation } from "@/lib/api";

/**
 * Local-only visual check for the collapsed-by-default Sources disclosure
 * on the citation fallback (answers with citations but no inline [N]
 * markers detected in the text). Not wired to any backend call.
 */
const FIXTURE_CITATIONS: Citation[] = [
  {
    chunk_id: "fixture-1",
    document_title: "You Can Come Through Victorious",
    author: "Derek Prince",
    content: "",
  },
  {
    chunk_id: "fixture-2",
    document_title: "Analysis of Hebrews: Chapter 11 & 12",
    author: "Derek Prince",
    content: "",
  },
  {
    chunk_id: "fixture-3",
    document_title: "How To Recognize And Expel Demons",
    author: "Derek Prince",
    content: "",
  },
  {
    chunk_id: "fixture-4",
    document_title: "Is Oneness (Apostolic, or Jesus Only) Pentecostalism Christian?",
    author: "",
    content: "",
  },
  {
    chunk_id: "fixture-5",
    document_title: "Analysis of Hebrews: Chapter 11 & 12",
    author: "Derek Prince",
    content: "",
  },
  {
    chunk_id: "fixture-6",
    document_title: "How To Recognize And Expel Demons",
    author: "Derek Prince",
    content: "",
  },
];

const SAMPLE_ANSWER = `identification with Christ's death and resurrection. Two distinct baptisms, one Jordan River moment, both essential to understanding what it means to follow him.`;

export default function CitationFallbackPreviewPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-2xl px-4 py-8 space-y-6">
        <header className="space-y-2 border-b border-border pb-4">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">
            Dev preview · Sources disclosure
          </p>
          <h1 className="text-lg font-semibold">Collapsed-by-default Sources</h1>
          <p className="text-sm text-muted-foreground">
            The Sources list should render as a closed disclosure button, not
            an open list.
          </p>
        </header>

        <section aria-label="Citation fallback">
          <div className="rounded-xl border border-border bg-card px-4 py-2">
            <ChatMessage role="assistant" content={SAMPLE_ANSWER} citations={FIXTURE_CITATIONS} />
          </div>
        </section>
      </div>
    </main>
  );
}
