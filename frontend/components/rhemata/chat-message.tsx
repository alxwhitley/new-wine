"use client";

import { useState, useRef } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { Citation } from "@/lib/api";
import { detectVerseReferences, type StudyReference } from "@/lib/study-reference";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  question?: string;
  accessToken?: string | null;
  onCitationClick?: (citation: Citation, index: number) => void;
  onVerseClick?: (reference: StudyReference) => void;
  /** True only while this specific message is still streaming in. Verse
   * underlines fade in only once streaming finishes (spec: "never mid-stream"). */
  isStreaming?: boolean;
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
      className="mx-0.5 text-xs font-medium text-primary underline-offset-4 hover:underline transition-colors cursor-pointer"
    >
      [{index}]
    </button>
  );
}

function VerseReferenceSpan({
  reference,
  onClick,
}: {
  reference: Extract<StudyReference, { type: "verse" }>;
  onClick?: (reference: StudyReference) => void;
}) {
  // Spec: "same text color as the rest of the sentence... a thin
  // warm-colored underline... strengthens slightly on hover. Nothing
  // shouts." Deliberately NOT text-primary like citations — the color must
  // stay identical to surrounding prose; only the underline is warm-toned.
  return (
    <button
      onClick={() => onClick?.(reference)}
      className="animate-in fade-in-0 duration-300 motion-reduce:animate-none text-foreground underline decoration-primary/50 decoration-[1px] underline-offset-4 hover:decoration-primary transition-colors cursor-pointer"
    >
      {reference.raw}
    </button>
  );
}

/**
 * Splits a text node on BOTH citation markers ([1], [2]...) and detected
 * verse references in a single ordered pass, so the two interleave
 * correctly regardless of which appears first in the sentence.
 */
function renderMessageText(
  text: string,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void,
  onVerseClick?: (reference: StudyReference) => void,
  detectVerses?: boolean
): React.ReactNode[] {
  type Match = { start: number; end: number; render: () => React.ReactNode };
  const matches: Match[] = [];

  const citationRe = /\[(\d+)\]/g;
  let cm: RegExpExecArray | null;
  while ((cm = citationRe.exec(text)) !== null) {
    const num = parseInt(cm[1], 10);
    const citation = citations[num - 1];
    if (!citation) continue;
    const start = cm.index;
    const end = start + cm[0].length;
    matches.push({
      start,
      end,
      render: () => (
        <CitationPill key={`c-${start}`} index={num} citation={citation} onClick={onCitationClick} />
      ),
    });
  }

  if (detectVerses) {
    for (const ref of detectVerseReferences(text)) {
      const start = ref.index;
      const end = start + ref.raw.length;
      // A verse reference should never overlap a citation marker, but stay
      // safe rather than risk mangled interleaving if it ever did.
      if (matches.some((m) => start < m.end && end > m.start)) continue;
      matches.push({
        start,
        end,
        render: () => (
          <VerseReferenceSpan key={`v-${start}`} reference={ref} onClick={onVerseClick} />
        ),
      });
    }
  }

  matches.sort((a, b) => a.start - b.start);

  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  for (const m of matches) {
    if (m.start > cursor) nodes.push(<span key={`t-${cursor}`}>{text.slice(cursor, m.start)}</span>);
    nodes.push(m.render());
    cursor = m.end;
  }
  if (cursor < text.length) nodes.push(<span key={`t-${cursor}`}>{text.slice(cursor)}</span>);
  return nodes;
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

function FeedbackModal({
  onSubmit,
  onClose,
}: {
  onSubmit: (comment: string) => void;
  onClose: () => void;
}) {
  const [comment, setComment] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div
        className="w-full max-w-md mx-4 rounded-lg border bg-popover border-border p-6"
      >
        <h3 className="font-sans text-lg text-foreground">What went wrong?</h3>
        <p className="text-xs text-muted-foreground mt-1 mb-4">
          Your feedback helps improve Rhemata
        </p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Describe the issue..."
          rows={4}
          className="w-full rounded-lg border bg-background border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary resize-none"
        />
        <div className="flex justify-end gap-3 mt-4">
          <button
            onClick={() => onSubmit("")}
            className="px-4 py-2 text-sm rounded-lg cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip
          </button>
          <Button onClick={() => onSubmit(comment)}>
            Submit
          </Button>
        </div>
      </div>
    </div>
  );
}

function FeedbackButtons({
  messageId,
  question,
  accessToken,
  isComplete,
}: {
  messageId?: string | null;
  question?: string;
  accessToken?: string | null;
  isComplete: boolean;
}) {
  const [rating, setRating] = useState<"thumbs_up" | "thumbs_down" | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [showThanks, setShowThanks] = useState(false);

  if (!isComplete) return null;

  async function submitFeedback(r: "thumbs_up" | "thumbs_down", comment?: string) {
    setRating(r);
    setShowThanks(true);
    setTimeout(() => setShowThanks(false), 2000);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

      const body: Record<string, unknown> = {
        rating: r,
        question: question || "",
      };
      if (messageId) body.message_id = messageId;
      if (comment) body.comment = comment;
      if (!accessToken) {
        body.anon_id = localStorage.getItem("rhemata_anon_id") || undefined;
      }

      await fetch(`${process.env.NEXT_PUBLIC_API_URL}/feedback`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
    } catch {
      // Non-blocking — don't disrupt UX
    }
  }

  if (showThanks) {
    return (
      <div className="flex items-center gap-1 mt-2">
        <span className="text-xs text-muted-foreground">Thanks for the feedback</span>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-1 mt-2">
        <button
          onClick={() => { if (!rating) submitFeedback("thumbs_up"); }}
          className="group p-1 rounded-md transition-colors cursor-pointer"
          title="Good answer"
        >
          <ThumbsUp
            className={cn(
              "h-4 w-4 transition-colors",
              rating === "thumbs_up" ? "text-primary fill-primary" : "text-muted-foreground fill-none",
              !rating && "group-hover:text-primary"
            )}
          />
        </button>
        <button
          onClick={() => { if (!rating) setShowModal(true); }}
          className="group p-1 rounded-md transition-colors cursor-pointer"
          title="Bad answer"
        >
          <ThumbsDown
            className={cn(
              "h-4 w-4 transition-colors",
              rating === "thumbs_down" ? "text-destructive fill-destructive" : "text-muted-foreground fill-none",
              !rating && "group-hover:text-destructive"
            )}
          />
        </button>
      </div>
      {showModal && (
        <FeedbackModal
          onSubmit={(comment) => {
            setShowModal(false);
            submitFeedback("thumbs_down", comment || undefined);
          }}
          onClose={() => {
            setShowModal(false);
            submitFeedback("thumbs_down");
          }}
        />
      )}
    </>
  );
}

export function ChatMessage({
  role,
  content,
  citations = [],
  messageId,
  question,
  accessToken,
  onCitationClick,
  onVerseClick,
  isStreaming = false,
}: ChatMessageProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end mb-4">
        <div className="max-w-[75%] rounded-3xl bg-accent border border-border px-4 py-3">
          <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
            {content}
          </p>
        </div>
      </div>
    );
  }

  const cleanedContent = stripXmlTags(content);
  const isComplete = content.length > 0;
  // Spec: verse underlines fade in only once the answer finishes streaming,
  // never mid-stream.
  const detectVerses = !isStreaming;

  return (
    <div className="mb-4 border-t border-border pt-3">
      <div className="max-w-none">
        <ReactMarkdown
          components={{
            h2: ({ children }) => (
              <h2 className="font-sans text-[1.1rem] font-semibold text-foreground mt-4 mb-2">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="font-sans text-base font-semibold text-foreground mt-4 mb-2">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="text-sm text-foreground leading-relaxed mb-3">
                {processChildren(children, citations, onCitationClick, onVerseClick, detectVerses)}
              </p>
            ),
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
            li: ({ children }) => (
              <li>{processChildren(children, citations, onCitationClick, onVerseClick, detectVerses)}</li>
            ),
          }}
        >
          {cleanedContent}
        </ReactMarkdown>
      </div>
      <FeedbackButtons
        messageId={messageId}
        question={question}
        accessToken={accessToken}
        isComplete={isComplete}
      />
    </div>
  );
}

/**
 * Walk through React children and replace [N] citation markers and detected
 * verse references in text nodes with clickable inline elements.
 */
function processChildren(
  children: React.ReactNode,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void,
  onVerseClick?: (reference: StudyReference) => void,
  detectVerses = false
): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return renderMessageText(children, citations, onCitationClick, onVerseClick, detectVerses);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return (
          <span key={i}>
            {renderMessageText(child, citations, onCitationClick, onVerseClick, detectVerses)}
          </span>
        );
      }
      return child;
    });
  }

  return children;
}
