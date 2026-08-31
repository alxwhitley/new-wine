"use client";

// SP2 Phase 6: new, small component — the lexicon-only subset of what
// app/study/page.tsx's InlineWordPanel renders (word, transliteration,
// Strong's number, gloss, definition, usage). Deliberately excludes the
// Precept Austin excerpt block and the "From the Library" corpus-results
// section — those stay exclusively in the standalone page's InlineWordPanel,
// untouched. See PLAN.md Task 21.

export interface WordDefinition {
  strongs: string;
  word: string;
  transliteration: string;
  gloss: string;
  lexiconDefinition: string;
  meaning: string;
}

export function WordDefinitionCard({ definition }: { definition: WordDefinition | null }) {
  return (
    <div>
      {definition ? (
        <>
          <p className="font-sans text-2xl text-foreground">{definition.word}</p>
          <p className="text-sm text-muted-foreground mt-0.5">
            {definition.transliteration}
            {definition.transliteration && " · "}
            {definition.strongs}
            {definition.gloss && ` · ${definition.gloss}`}
          </p>
        </>
      ) : (
        <p className="text-sm text-muted-foreground">Loading definition…</p>
      )}

      {definition?.lexiconDefinition && (
        <>
          <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground pt-5 mb-1.5">Definition</p>
          <p className="text-base font-medium text-foreground leading-relaxed">{definition.lexiconDefinition}</p>
        </>
      )}
      {definition?.meaning && (
        <>
          <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground pt-5 mb-1.5">Usage</p>
          <p className="text-sm text-muted-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}
    </div>
  );
}
