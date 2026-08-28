import { useEffect, useState } from "react";

// SP2 Phase 6: extracted the fetch + colon/dot parsing logic that appeared
// twice, verbatim, in app/study/page.tsx — see PLAN.md Task 21. Deliberately
// scoped to just the parsed pieces ({gloss, lexiconDefinition, meaning}), not
// a full WordDefinition: the two call sites construct materially different
// final objects from these same pieces (one populates lexiconDefinition, the
// other always leaves it "" and uses gloss instead) — that's current,
// intentional behavior, not something this extraction unifies.

export interface LexiconEntry {
  gloss: string;
  lexiconDefinition: string;
  meaning: string;
}

export function useLexiconDefinition(
  strongs: string | null,
  accessToken: string | null
): LexiconEntry | null {
  const [lexiconContent, setLexiconContent] = useState<string | null>(null);

  // Reset synchronously during render when strongs becomes falsy (React's
  // documented "adjusting state when a prop changes" pattern) instead of
  // as the effect's first statement. The fetch path below is unchanged --
  // it still doesn't pre-clear content between two different truthy
  // `strongs` values, matching existing behavior exactly.
  const [resolvedStrongs, setResolvedStrongs] = useState(strongs);
  if (strongs !== resolvedStrongs) {
    setResolvedStrongs(strongs);
    if (!strongs) setLexiconContent(null);
  }

  useEffect(() => {
    if (!strongs) return;
    const params = new URLSearchParams({ strongs });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/lexicon?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setLexiconContent(data?.content ?? null))
      .catch(() => setLexiconContent(null));
  }, [strongs, accessToken]);

  if (!lexiconContent) return null;

  let lexDef = "";
  let lexUsage = "";
  const colonIdx = lexiconContent.indexOf(":");
  const afterColon = colonIdx >= 0 ? lexiconContent.slice(colonIdx + 1).trim() : lexiconContent;
  const dotIdx = afterColon.indexOf(".");
  if (dotIdx >= 0) {
    lexDef = afterColon.slice(0, dotIdx).trim();
    const rest = afterColon.slice(dotIdx + 1).trim();
    lexUsage = rest.length > 200 ? rest.slice(0, 200).trimEnd() + "…" : rest;
  } else {
    lexDef = afterColon;
  }

  return { gloss: lexDef, lexiconDefinition: lexDef, meaning: lexUsage };
}
