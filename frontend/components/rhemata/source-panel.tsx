"use client";

import { X, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";

interface SourcePanelProps {
  citation: Citation | null;
  citationIndex: number | null;
  isOpen: boolean;
  onClose: () => void;
}

export function SourcePanel({ citation, citationIndex, isOpen, onClose }: SourcePanelProps) {
  if (!isOpen || !citation) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={onClose}
      />

      {/* Panel */}
      <aside className="fixed right-0 top-0 z-50 h-screen w-96 bg-card border-l border-border shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2 text-muted-foreground">
            <BookOpen className="h-4 w-4" />
            <span className="text-xs font-medium uppercase tracking-wider">Source</span>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Close source panel</span>
          </Button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto" style={{ maxHeight: "calc(100vh - 65px)" }}>
          {/* Citation badge */}
          {citationIndex !== null && (
            <div className="mb-4">
              <span className="inline-flex items-center justify-center rounded px-2 py-1 text-xs font-medium bg-citation text-citation-foreground">
                [{citationIndex}]
              </span>
            </div>
          )}

          {/* Title */}
          <h2 className="font-serif text-lg font-semibold text-foreground mb-2 leading-tight">
            {citation.document_title || "Unknown Source"}
          </h2>

          {/* Author */}
          {citation.author && (
            <p className="text-sm text-muted-foreground mb-6">
              {citation.author}
            </p>
          )}

          {/* Excerpt */}
          <div className="rounded-lg bg-background p-4 border border-border">
            <p className="text-sm text-foreground leading-relaxed italic">
              &ldquo;{citation.content}&rdquo;
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
