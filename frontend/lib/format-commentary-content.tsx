import type { ReactElement } from "react";

// SP2 Phase 7: extracted verbatim out of app/study/page.tsx's CommentarySection
// (the header/lemma-splitting block previously inlined in an IIFE) — see
// PLAN.md Task 25. Pure function of the raw commentary content string; no
// dependency on the caller's container shape, so both the standalone Study
// page's detail view and the panel's inline-expand row can share it.

const HEADER_RE = /^\[(.+?)\s*\|\s*(.+?)\]$/;
const LEMMA_SPLIT_RE = /(?<=\. )(?=[A-Z][^.!?\n]{0,55} - )/g;
const LEMMA_START_RE = /^(.{1,60}?) - ([\s\S]*)$/;

export function formatCommentaryContent(content: string): ReactElement[] {
  const blocks = content.split(/\n\n+/).filter((b) => b.trim());
  const elements: ReactElement[] = [];
  let isFirst = true;
  for (let bi = 0; bi < blocks.length; bi++) {
    const trimmed = blocks[bi].trim();
    const headerMatch = trimmed.match(HEADER_RE);
    if (headerMatch) {
      const authorRaw = headerMatch[1].trim();
      const commentator = authorRaw.replace(/[''`]s\s+Commentary.*$/i, '').trim() || authorRaw;
      const verseRef = headerMatch[2].trim();
      elements.push(
        <div key={`h-${bi}`} className={`mb-3${isFirst ? '' : ' border-t border-border/40 pt-4 mt-6'}`}>
          <p className="font-sans text-[11px] uppercase tracking-widest text-muted-foreground">{commentator}</p>
          <p className="font-sans text-sm font-medium text-foreground mt-0.5">{verseRef}</p>
        </div>
      );
      isFirst = false;
      continue;
    }
    const paras = trimmed.split(LEMMA_SPLIT_RE).filter((p) => p.trim());
    for (let pi = 0; pi < paras.length; pi++) {
      const para = paras[pi].trim();
      const lm = para.match(LEMMA_START_RE);
      if (lm) {
        elements.push(
          <p key={`${bi}-${pi}`} className="text-foreground/90 mb-4 text-[15px] leading-relaxed">
            <span className="font-semibold text-foreground">{lm[1]} -</span>{' '}
            {lm[2].trim()}
          </p>
        );
      } else {
        elements.push(
          <p key={`${bi}-${pi}`} className="text-foreground/90 mb-4 text-[15px] leading-relaxed">{para}</p>
        );
      }
    }
  }
  return elements;
}
