"use client";

import ReactMarkdown from "react-markdown";
import type { Citation } from "@/lib/api";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  onCitationClick?: (citation: Citation, index: number) => void;
}

function CitationPill({
  index,
  citation,
  onClick,
}: {
  index: number;
  citation: Citation;
  onClick?: (citation: Citation, index: number) => void;
}) {
  return (
    <button
      onClick={() => onClick?.(citation, index)}
      className="mx-0.5 inline-flex items-center justify-center rounded px-1.5 py-0.5 text-xs font-medium bg-citation text-citation-foreground hover:bg-citation/80 transition-colors cursor-pointer"
    >
      [{index}]
    </button>
  );
}

function renderTextWithCitations(
  text: string,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void
) {
  const parts = text.split(/(\[\d+\])/g);

  return parts.map((part, i) => {
    const match = part.match(/\[(\d+)\]/);
    if (match) {
      const num = parseInt(match[1]);
      const citation = citations[num - 1];
      if (citation) {
        return (
          <CitationPill
            key={i}
            index={num}
            citation={citation}
            onClick={onCitationClick}
          />
        );
      }
    }
    return <span key={i}>{part}</span>;
  });
}

function stripXmlTags(text: string): string {
  // Extract content inside <answer> tags if present
  const answerMatch = text.match(/<answer>([\s\S]*?)<\/answer>/);
  if (answerMatch) {
    return answerMatch[1].trim();
  }
  // Otherwise strip all known XML tags and their content
  let cleaned = text;
  cleaned = cleaned.replace(/<thinking>[\s\S]*?<\/thinking>/g, "");
  cleaned = cleaned.replace(/<research_analysis>[\s\S]*?<\/research_analysis>/g, "");
  // Strip any remaining XML-style tags (opening, closing, self-closing)
  cleaned = cleaned.replace(/<\/?[a-z_]+>/gi, "");
  return cleaned.trim();
}

export function ChatMessage({
  role,
  content,
  citations = [],
  onCitationClick,
}: ChatMessageProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end mb-6">
        <div className="max-w-[75%] rounded-3xl bg-card px-4 py-3">
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {content}
          </p>
        </div>
      </div>
    );
  }

  const cleanedContent = stripXmlTags(content);
  const hasCitations = citations.length > 0;

  return (
    <div className="mb-6">
      <div className="max-w-none prose-rhemata">
        <ReactMarkdown
          components={{
            h2: ({ children }) => (
              <h2 className="font-serif text-[1.1rem] font-semibold text-foreground mt-4 mb-2">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="font-serif text-base font-semibold text-foreground mt-4 mb-2">
                {children}
              </h3>
            ),
            p: ({ children }) => {
              if (!hasCitations) {
                return (
                  <p className="text-sm text-foreground leading-relaxed mb-3">
                    {children}
                  </p>
                );
              }
              return (
                <p className="text-sm text-foreground leading-relaxed mb-3">
                  {processChildren(children, citations, onCitationClick)}
                </p>
              );
            },
            strong: ({ children }) => (
              <strong className="font-semibold text-foreground">{children}</strong>
            ),
            em: ({ children }) => (
              <em className="italic">{children}</em>
            ),
            ol: ({ children }) => (
              <ol className="text-sm text-foreground leading-relaxed mb-4 ml-6 list-decimal space-y-2">
                {children}
              </ol>
            ),
            ul: ({ children }) => (
              <ul className="text-sm text-foreground leading-relaxed mb-4 ml-6 list-disc space-y-2">
                {children}
              </ul>
            ),
            li: ({ children }) => {
              if (!hasCitations) {
                return <li>{children}</li>;
              }
              return <li>{processChildren(children, citations, onCitationClick)}</li>;
            },
          }}
        >
          {cleanedContent}
        </ReactMarkdown>
      </div>
    </div>
  );
}

/**
 * Walk through React children and replace [N] citation markers in text nodes
 * with clickable citation pills.
 */
function processChildren(
  children: React.ReactNode,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void
): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return renderTextWithCitations(children, citations, onCitationClick);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return (
          <span key={i}>
            {renderTextWithCitations(child, citations, onCitationClick)}
          </span>
        );
      }
      return child;
    });
  }

  return children;
}
