"use client";

import { BookOpen, ExternalLink } from "lucide-react";
import {
  Sheet,
  SheetContent,
} from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import type { Citation } from "@/lib/api";

interface SourcePanelProps {
  citation: Citation | null;
  citationIndex: number | null;
  isOpen: boolean;
  onClose: () => void;
}

export function SourcePanel({ citation, citationIndex, isOpen, onClose }: SourcePanelProps) {
  const isMobile = useIsMobile();
  return (
    <Sheet open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <SheetContent
        side={isMobile ? "bottom" : "right"}
        className={isMobile ? "h-[85vh] overflow-y-auto rounded-t-xl p-0 bg-popover" : "w-96 max-w-96 p-0 bg-popover"}
        showCloseButton={true}
      >
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-border px-6 py-4">
          <BookOpen className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Source</span>
        </div>

        {/* Content */}
        {citation && (
          <div className="p-6 overflow-y-auto max-h-[calc(100vh-65px)]">
            {/* Citation badge */}
            {citationIndex !== null && (
              <div className="mb-4">
                <span className="inline-flex items-center justify-center rounded px-2 py-1 text-xs font-medium bg-secondary text-secondary-foreground">
                  [{citationIndex}]
                </span>
              </div>
            )}

            {/* Title */}
            <h2 className="font-sans text-lg font-semibold text-foreground mb-2 leading-tight">
              {citation.document_title || "Unknown Source"}
            </h2>

            {/* Author */}
            {citation.author && (
              <p className="text-sm text-muted-foreground mb-6">
                {citation.author}
              </p>
            )}

            {/* Source link */}
            {citation.url && (
              <a
                href={citation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="mb-6 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline transition-colors"
              >
                View source
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}

            {/* Excerpt */}
            <div className="rounded-lg bg-background p-4 border border-border">
              <p className="text-sm text-foreground leading-relaxed italic">
                &ldquo;{citation.content}&rdquo;
              </p>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
