"use client";

import { useState, useRef, memo } from "react";
import { ThumbsUp, ThumbsDown, Quote } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useResolvedQuotes } from "@/hooks/useResolvedQuotes";
import type { Citation, ResolvedQuote } from "@/lib/api";
import {
  detectVerseReferences,
  isVerified,
  detectTeacherReferences,
  isTeacherVerified,
  type StudyReference,
  type VerifiedReference,
  type CuratedTeacher,
} from "@/lib/study-reference";
import { isStudyPanelEnabled } from "@/lib/study-panel-flag";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  question?: string;
  accessToken?: string | null;
  onCitationClick?: (citation: Citation, index: number) => void;
  /** question is only ever populated for a teacher click (the current
   * turn's user question, for the panel's position-synthesis fetch) — verse
   * clicks call this with a single argument, same as before. */
  onVerseClick?: (reference: StudyReference, question?: string) => void;
  /** True only while this specific message is still streaming in. Verse
   * underlines fade in only once streaming finishes (spec: "never mid-stream"). */
  isStreaming?: boolean;
  /** SP1's verified pointers for this message. A detected verse candidate
   * only renders as an underline if it matches one of these by identity. */
  verifiedReferences?: VerifiedReference[];
  /** SP4: the small, known curated-teacher list (GET /study/teachers),
   * fetched once at the page level. A detected name only renders as an
   * underline if it's in this list AND SP1 verified it for this message. */
  curatedTeachers?: CuratedTeacher[];
  /** Quote IDs from the answer's async meta frame (empty for most answers).
   * Resolved client-side via useResolvedQuotes; never text from the model. */
  quoteIds?: string[];
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
      data-study-trigger
      className="animate-in fade-in-0 duration-300 motion-reduce:animate-none text-foreground underline decoration-primary/50 decoration-[1px] underline-offset-4 hover:decoration-primary transition-colors cursor-pointer"
    >
      {reference.raw}
    </button>
  );
}

function TeacherReferenceSpan({
  reference,
  question,
  onClick,
}: {
  reference: Extract<StudyReference, { type: "teacher" }>;
  question?: string;
  onClick?: (reference: StudyReference, question?: string) => void;
}) {
  // Same visual treatment as VerseReferenceSpan — nothing in the design doc
  // calls for teacher underlines to look different from verse underlines.
  return (
    <button
      onClick={() => onClick?.(reference, question)}
      data-study-trigger
      className="animate-in fade-in-0 duration-300 motion-reduce:animate-none text-foreground underline decoration-primary/50 decoration-[1px] underline-offset-4 hover:decoration-primary transition-colors cursor-pointer"
    >
      {reference.name}
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
  onVerseClick?: (reference: StudyReference, question?: string) => void,
  detectVerses?: boolean,
  verifiedReferences: VerifiedReference[] = [],
  question?: string,
  curatedTeachers: CuratedTeacher[] = []
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
      if (!isVerified(ref, verifiedReferences)) continue;
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

  if (detectVerses && curatedTeachers.length > 0) {
    for (const ref of detectTeacherReferences(text, curatedTeachers)) {
      if (!isTeacherVerified(ref, verifiedReferences)) continue;
      const start = ref.index;
      const end = start + ref.name.length;
      if (matches.some((m) => start < m.end && end > m.start)) continue;
      matches.push({
        start,
        end,
        render: () => (
          <TeacherReferenceSpan key={`tch-${start}`} reference={ref} question={question} onClick={onVerseClick} />
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

function QuoteRail({ quoteIds }: { quoteIds?: string[] }) {
  const quotes = useResolvedQuotes(quoteIds);
  // teacher_name is required for display -- a quote whose backend source
  // lookup failed (teacher_name: null) must never render, since named-voice
  // attribution is the entire reason this surface exists (CLAUDE.md).
  const attributed = quotes.filter((q): q is ResolvedQuote & { teacher_name: string } => !!q.teacher_name);
  if (attributed.length === 0) return null;

  return (
    <aside
      className="mt-4 space-y-3 border-t border-border pt-4"
      aria-label="Verified quotes"
    >
      {attributed.map((q) => {
        const topicLabel = (q.topic_ids && q.topic_ids[0]) || q.topic;
        return (
          <figure
            key={q.id}
            className="rounded-lg border border-border bg-muted/40 px-4 py-3 shadow-sm"
          >
            <div className="flex gap-2.5">
              <Quote className="h-4 w-4 text-primary shrink-0 mt-0.5" aria-hidden="true" />
              <div className="min-w-0 space-y-2">
                <blockquote className="font-serif italic text-sm text-foreground leading-relaxed m-0">
                  {q.quote_text}
                </blockquote>
                {q.restated_point ? (
                  <p className="text-xs text-muted-foreground leading-relaxed not-italic m-0">
                    {q.restated_point}
                  </p>
                ) : null}
                <figcaption className="flex items-center gap-2 flex-wrap text-xs text-muted-foreground">
                  <span className="font-medium text-foreground/80">{q.teacher_name}</span>
                  {q.work_title ? (
                    <>
                      <span aria-hidden="true">·</span>
                      <span className="truncate max-w-[18rem]" title={q.work_title}>
                        {q.work_title}
                      </span>
                    </>
                  ) : null}
                  {topicLabel ? (
                    <Badge variant="secondary" className="rounded-md text-xs font-normal">
                      {topicLabel}
                    </Badge>
                  ) : null}
                </figcaption>
              </div>
            </div>
          </figure>
        );
      })}
    </aside>
  );
}

// Memoized: react-markdown's own <Markdown> component re-creates its whole
// processor and output from scratch on every render, unconditionally — it
// does not check whether `children`/`components` changed (confirmed via
// its source: createProcessor() runs fresh every call, no internal
// memoization for the sync export). That means it remounts the DOM subtree
// it renders, including any verse/teacher reference <button> nested in a
// paragraph, every single time this component re-renders for ANY reason —
// including an unrelated ancestor re-render (ChatFocusContext's
// inputFocused toggling on the chat textarea's blur). If a click is
// mid-flight on a reference button when that remount lands, the browser's
// click gesture is tied to the now-destroyed node and never fires — the
// Study Panel silently fails to open. Root-caused 2026-07-23. `memo` stops
// this component from re-rendering at all when its own props haven't
// changed, which is the only place this can actually be fixed — react-
// markdown itself doesn't offer a memoized synchronous variant. Requires
// every prop here to stay reference-stable across an unrelated parent
// re-render for the shallow-compare to hold: onVerseClick and
// onCitationClick must be useCallback in page.tsx (onCitationClick fixed
// alongside this), citations/verifiedReferences/curatedTeachers must stay
// the same array reference from message/state data, which they already do.
export const ChatMessage = memo(function ChatMessage({
  role,
  content,
  citations = [],
  messageId,
  question,
  accessToken,
  onCitationClick,
  onVerseClick,
  isStreaming = false,
  verifiedReferences = [],
  curatedTeachers = [],
  quoteIds,
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
  // never mid-stream. Also forced off entirely when the Study Panel kill
  // switch is off — an underline that opens to nothing is worse than none.
  const detectVerses = !isStreaming && isStudyPanelEnabled();

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
                {processChildren(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}
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
              <li>{processChildren(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}</li>
            ),
          }}
        >
          {cleanedContent}
        </ReactMarkdown>
      </div>
      <QuoteRail quoteIds={quoteIds} />
      <FeedbackButtons
        messageId={messageId}
        question={question}
        accessToken={accessToken}
        isComplete={isComplete}
      />
    </div>
  );
});

/**
 * Walk through React children and replace [N] citation markers and detected
 * verse references in text nodes with clickable inline elements.
 */
function processChildren(
  children: React.ReactNode,
  citations: Citation[],
  onCitationClick?: (citation: Citation, index: number) => void,
  onVerseClick?: (reference: StudyReference, question?: string) => void,
  detectVerses = false,
  verifiedReferences: VerifiedReference[] = [],
  question?: string,
  curatedTeachers: CuratedTeacher[] = []
): React.ReactNode {
  if (!children) return children;

  if (typeof children === "string") {
    return renderMessageText(children, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers);
  }

  if (Array.isArray(children)) {
    return children.map((child, i) => {
      if (typeof child === "string") {
        return (
          <span key={i}>
            {renderMessageText(child, citations, onCitationClick, onVerseClick, detectVerses, verifiedReferences, question, curatedTeachers)}
          </span>
        );
      }
      return child;
    });
  }

  return children;
}
