"use client";

import { useState, useEffect, useCallback } from "react";
import type { CorpusCard } from "./types";

const COLORS = {
  surface: "#262624",
  border: "#3c3c38",
  text: "#e6e6e6",
  textSecondary: "#c1c1b8",
  gold: "#b49238",
  citationGold: "#d4b96a",
  codeBg: "#1b1b19",
};

function StatusBadge({ status }: { status: CorpusCard["status"] }) {
  const colorMap: Record<string, { bg: string; text: string }> = {
    Complete: { bg: "rgba(34,197,94,0.15)", text: "#22c55e" },
    Ongoing: { bg: "rgba(180,146,56,0.15)", text: "#d4b96a" },
    "Not Started": { bg: "rgba(156,163,175,0.15)", text: "#9ca3af" },
    Partial: { bg: "rgba(245,158,11,0.15)", text: "#f59e0b" },
  };
  const c = colorMap[status];
  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ backgroundColor: c.bg, color: c.text }}
    >
      {status}
    </span>
  );
}

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
      className="shrink-0 px-2 py-1 rounded text-xs font-medium transition-colors"
      style={{
        backgroundColor: copied ? "rgba(34,197,94,0.2)" : "rgba(180,146,56,0.15)",
        color: copied ? "#22c55e" : COLORS.citationGold,
      }}
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
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full max-h-[85vh] overflow-y-auto rounded-lg p-6"
        style={{
          maxWidth: 680,
          backgroundColor: COLORS.surface,
          border: `1px solid ${COLORS.border}`,
        }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-1">
          <h2
            className="text-xl font-semibold font-serif"
            style={{ color: COLORS.text }}
          >
            {card.name}
          </h2>
          <StatusBadge status={card.status} />
        </div>
        {count !== null && !card.isMaintenance && (
          <p
            className="text-2xl font-bold mb-2"
            style={{ color: COLORS.citationGold }}
          >
            {count.toLocaleString()} {card.specialTable ? "rows" : "documents"}
          </p>
        )}
        <p className="text-sm mb-5" style={{ color: COLORS.textSecondary }}>
          {card.description}
        </p>

        {/* Progress bar for excerpts */}
        {card.progressTarget && count !== null && (
          <div className="mb-5">
            <div className="flex justify-between text-xs mb-1">
              <span style={{ color: COLORS.textSecondary }}>Progress</span>
              <span style={{ color: COLORS.citationGold }}>
                {count.toLocaleString()} / {card.progressTarget.toLocaleString()}
              </span>
            </div>
            <div
              className="w-full h-2 rounded-full overflow-hidden"
              style={{ backgroundColor: COLORS.border }}
            >
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min((count / card.progressTarget) * 100, 100)}%`,
                  backgroundColor: COLORS.citationGold,
                }}
              />
            </div>
          </div>
        )}

        {/* Pipeline steps */}
        {card.steps && card.steps.length > 0 && (
          <div className="mb-5">
            <h3
              className="text-xs font-medium uppercase tracking-wider mb-2"
              style={{ color: COLORS.textSecondary }}
            >
              Pipeline Steps
            </h3>
            <div className="flex items-center gap-2 flex-wrap">
              {card.steps.map((step, i) => (
                <div key={step.label} className="flex items-center gap-2">
                  <span
                    className="px-3 py-1 rounded text-sm font-medium"
                    style={{
                      backgroundColor: COLORS.codeBg,
                      color: COLORS.citationGold,
                      border: `1px solid ${COLORS.border}`,
                    }}
                  >
                    {step.label}
                  </span>
                  {i < card.steps!.length - 1 && (
                    <span style={{ color: COLORS.textSecondary }}>
                      &rarr;
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Book list (Public Domain Books) */}
        {card.bookList && (
          <div className="mb-5">
            <h3
              className="text-xs font-medium uppercase tracking-wider mb-2"
              style={{ color: COLORS.textSecondary }}
            >
              Titles ({card.bookList.reduce((sum, b) => sum + b.titles.length, 0)})
            </h3>
            <div
              className="max-h-60 overflow-y-auto rounded p-3 space-y-3"
              style={{
                backgroundColor: COLORS.codeBg,
                border: `1px solid ${COLORS.border}`,
              }}
            >
              {card.bookList.map((entry) => (
                <div key={entry.author}>
                  <p
                    className="text-sm font-semibold mb-0.5"
                    style={{ color: COLORS.citationGold }}
                  >
                    {entry.author}
                  </p>
                  <ul className="list-none space-y-0">
                    {entry.titles.map((title) => (
                      <li
                        key={title}
                        className="text-sm pl-3"
                        style={{ color: COLORS.textSecondary }}
                      >
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
          <h3
            className="text-xs font-medium uppercase tracking-wider mb-3"
            style={{ color: COLORS.textSecondary }}
          >
            Commands
          </h3>
          <div className="space-y-2">
            {card.commands.map((cmd) => (
              <div key={cmd.label}>
                <p
                  className="text-xs font-medium mb-1"
                  style={{ color: COLORS.textSecondary }}
                >
                  {cmd.label}
                </p>
                <div
                  className="flex items-start gap-2 rounded p-2"
                  style={{
                    backgroundColor: COLORS.codeBg,
                    border: `1px solid ${COLORS.border}`,
                  }}
                >
                  <code
                    className="text-xs break-all flex-1 font-mono leading-relaxed"
                    style={{ color: COLORS.citationGold }}
                  >
                    {cmd.command}
                  </code>
                  <CopyButton text={cmd.command} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Close button */}
        <div className="mt-5 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded text-sm font-medium transition-opacity hover:opacity-80"
            style={{
              backgroundColor: COLORS.border,
              color: COLORS.text,
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
