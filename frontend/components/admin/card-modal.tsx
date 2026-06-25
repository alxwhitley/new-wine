"use client";

import { useState, useEffect, useCallback } from "react";
import type { CorpusCard } from "./corpus-types";
import { StatusBadge } from "./status-badge";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className={`shrink-0 px-2 py-1 rounded text-xs font-medium transition-colors ${
        copied ? "bg-primary/25 text-primary" : "bg-muted text-foreground"
      }`}
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

interface CardModalProps {
  card: CorpusCard;
  count: number | null;
  onClose: () => void;
}

export default function CardModal({ card, count, onClose }: CardModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-h-[85vh] overflow-y-auto rounded-lg p-6 bg-card border border-border" style={{ maxWidth: 680 }}>
        {/* Header */}
        <div className="flex items-center gap-3 mb-1">
          <h2 className="text-xl font-semibold font-sans text-foreground">
            {card.name}
          </h2>
          <StatusBadge status={card.status} />
        </div>
        {count !== null && !card.isMaintenance && (
          <p className="text-2xl font-bold mb-2 text-primary">
            {count.toLocaleString()} {card.countLabel ?? (card.specialTable ? "rows" : "documents")}
          </p>
        )}
        <p className="text-sm mb-5 text-muted-foreground">{card.description}</p>

        {/* Progress bar */}
        {card.progressTarget && count !== null && (
          <div className="mb-5">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-muted-foreground">Progress</span>
              <span className="text-primary">
                {count.toLocaleString()} / {card.progressTarget.toLocaleString()}
              </span>
            </div>
            <div className="w-full h-2 rounded-full overflow-hidden bg-border">
              <div
                className="h-full rounded-full transition-all bg-primary"
                style={{ width: `${Math.min((count / card.progressTarget) * 100, 100)}%` }}
              />
            </div>
          </div>
        )}

        {/* Pipeline steps */}
        {card.steps && card.steps.length > 0 && (
          <div className="mb-5">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-2 text-muted-foreground">
              Pipeline Steps
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              {card.steps.map((step, i) => (
                <div key={step.label} className="flex items-center gap-2">
                  <span className="px-3 py-1 rounded text-sm font-medium bg-muted border border-border text-primary">
                    {step.label}
                  </span>
                  {i < card.steps!.length - 1 && (
                    <span className="text-muted-foreground">&rarr;</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Book list */}
        {card.bookList && (
          <div className="mb-5">
            <h3 className="text-xs font-medium uppercase tracking-wider mb-2 text-muted-foreground">
              Titles ({card.bookList.reduce((sum, b) => sum + b.titles.length, 0)})
            </h3>
            <div className="max-h-60 overflow-y-auto rounded p-3 space-y-3 bg-muted border border-border">
              {card.bookList.map((entry) => (
                <div key={entry.author}>
                  <p className="text-sm font-semibold mb-0.5 text-primary">
                    {entry.author}
                  </p>
                  <ul className="list-none space-y-0">
                    {entry.titles.map((title) => (
                      <li key={title} className="text-sm pl-3 text-muted-foreground">
                        {title}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Commands */}
        <div>
          <h3 className="text-xs font-medium uppercase tracking-wider mb-3 text-muted-foreground">
            Commands
          </h3>
          <div className="space-y-2">
            {card.commands.map((cmd) => (
              <div key={cmd.label}>
                <p className="text-xs font-medium mb-1 text-muted-foreground">
                  {cmd.label}
                </p>
                <div className="flex items-start gap-2 rounded p-2 bg-muted border border-border">
                  <code className="text-xs break-all flex-1 font-mono leading-relaxed text-primary">
                    {cmd.command}
                  </code>
                  <CopyButton text={cmd.command} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Close */}
        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded text-sm font-medium bg-border text-foreground hover:bg-accent transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
