"use client";

import Link from "next/link";
import { SearchDocument } from "@/lib/api";
import { BookOpen } from "lucide-react";

interface DocumentCardProps {
  document: SearchDocument;
}

export default function DocumentCard({ document }: DocumentCardProps) {
  return (
    <Link
      href={`/document/${document.id}`}
      className="block rounded-lg focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
    >
      <div className="rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary hover:bg-accent">
        <div className="flex items-start gap-3">
          <BookOpen className="h-4 w-4 shrink-0 mt-0.5 text-primary" />
          <div className="flex-1 min-w-0">
            <h3 className="font-sans text-sm font-semibold text-foreground truncate">
              {document.title}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              {document.author}
              {document.year ? ` · ${document.year}` : ""}
              {document.source_type ? ` · ${document.source_type}` : ""}
            </p>
            {document.topic_tags && document.topic_tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2.5">
                {document.topic_tags.map((tag) => (
                  <span
                    key={tag}
                    className="text-xs bg-secondary text-secondary-foreground rounded-md px-2 py-0.5"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
