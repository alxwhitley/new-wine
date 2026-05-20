"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { ModeToggle } from "@/components/rhemata/mode-toggle";

interface WordToken {
  greek: string;
  transliteration: string;
  english: string;
  strongs: string;
  morph: string;
}

interface CorpusQuote {
  text: string;
  author: string;
  source: string;
}

interface WordDefinition {
  strongs: string;
  word: string;
  transliteration: string;
  gloss: string;
  meaning: string;
  corpusQuotes: CorpusQuote[];
}

// Placeholder: John 1:1 interlinear
const PLACEHOLDER_TOKENS: WordToken[] = [
  { greek: "\u1F18\u03BD", transliteration: "En", english: "In", strongs: "G1722", morph: "PREP" },
  { greek: "\u1F00\u03C1\u03C7\u1FC7", transliteration: "arch\u0113", english: "the beginning", strongs: "G0746", morph: "N-DSF" },
  { greek: "\u1F26\u03BD", transliteration: "\u0113n", english: "was", strongs: "G2258", morph: "V-IXI-3S" },
  { greek: "\u1F41", transliteration: "ho", english: "the", strongs: "G3588", morph: "T-NSM" },
  { greek: "\u03BB\u03CC\u03B3\u03BF\u03C2", transliteration: "logos", english: "Word", strongs: "G3056", morph: "N-NSM" },
  { greek: "\u03BA\u03B1\u1F76", transliteration: "kai", english: "and", strongs: "G2532", morph: "CONJ" },
  { greek: "\u1F41", transliteration: "ho", english: "the", strongs: "G3588", morph: "T-NSM" },
  { greek: "\u03BB\u03CC\u03B3\u03BF\u03C2", transliteration: "logos", english: "Word", strongs: "G3056", morph: "N-NSM" },
  { greek: "\u1F26\u03BD", transliteration: "\u0113n", english: "was", strongs: "G2258", morph: "V-IXI-3S" },
  { greek: "\u03C0\u03C1\u1F78\u03C2", transliteration: "pros", english: "with", strongs: "G4314", morph: "PREP" },
  { greek: "\u03C4\u1F78\u03BD", transliteration: "ton", english: "the", strongs: "G3588", morph: "T-ASM" },
  { greek: "\u03B8\u03B5\u03CC\u03BD", transliteration: "theon", english: "God", strongs: "G2316", morph: "N-ASM" },
];

const PLACEHOLDER_DEFINITIONS: Record<string, WordDefinition> = {
  G0746: {
    strongs: "G0746",
    word: "\u1F00\u03C1\u03C7\u03AE",
    transliteration: "arch\u0113",
    gloss: "beginning, origin, first cause",
    meaning:
      "From G0756; a commencement, or (concrete) chief (in various applications of order, time, place or rank). Used of the beginning of the world (John 1:1), of the Gospel (Mark 1:1), and of the first principles of a matter (Hebrews 5:12).",
    corpusQuotes: [
      { text: "The word arch\u0113 points us back before time began \u2014 to the eternal origin of the Logos, who was already there when everything else started.", author: "John Wimber", source: "The Word Made Flesh (sermon)" },
      { text: "Genesis 1:1 and John 1:1 both open with this word, tying creation to the pre-existence of Christ.", author: "Gordon Fee", source: "New Testament Exegesis" },
    ],
  },
  G3056: {
    strongs: "G3056",
    word: "\u03BB\u03CC\u03B3\u03BF\u03C2",
    transliteration: "logos",
    gloss: "word, speech, reason",
    meaning:
      "From G3004; something said (including the thought); by implication a topic, also reasoning or motive. In John\u2019s prologue, Logos denotes the pre-existent divine Word, the second person of the Trinity, through whom all things were made.",
    corpusQuotes: [
      { text: "Logos is not merely a spoken word \u2014 it is the self-expression of God, the living Word who took on flesh and walked among us.", author: "Sam Storms", source: "The Hope of Glory" },
      { text: "John chose logos deliberately: for Greeks it meant cosmic reason, for Jews the creative word of Yahweh. Both meanings converge in Jesus.", author: "D.A. Carson", source: "The Gospel According to John" },
      { text: "When we preach, we are not merely sharing ideas. We are releasing the logos \u2014 the living, active Word that carries the power to transform.", author: "Bill Johnson", source: "The Supernatural Power of a Transformed Mind" },
    ],
  },
  G2316: {
    strongs: "G2316",
    word: "\u03B8\u03B5\u03CC\u03C2",
    transliteration: "theos",
    gloss: "God, a deity",
    meaning:
      "Of uncertain affinity; a deity, especially the supreme Divinity. In the NT used of the one true God, the Father (John 17:3), and applied to Christ (John 1:1, 20:28, Romans 9:5).",
    corpusQuotes: [
      { text: "The Word was not merely divine \u2014 He was God. John\u2019s grammar is precise: theos without the article stresses the nature of the Word, not His identity with the Father.", author: "Gordon Fee", source: "Pauline Christology" },
      { text: "Thomas\u2019 confession \u2018My Lord and my God\u2019 is the climax of the Fourth Gospel \u2014 the moment a disciple finally sees Jesus for who He truly is.", author: "N.T. Wright", source: "Simply Jesus" },
    ],
  },
};

function InterlinearBlocks({
  tokens,
  selectedStrongs,
  onSelect,
}: {
  tokens: WordToken[];
  selectedStrongs: string | null;
  onSelect: (strongs: string | null) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {tokens.map((token, i) => {
        const isSelected = selectedStrongs === token.strongs;
        return (
          <button
            key={i}
            onClick={() => onSelect(isSelected ? null : token.strongs)}
            className="flex flex-col items-center rounded-lg border px-3 py-2 transition-colors min-w-[64px]"
            style={{
              borderColor: isSelected ? "#b49238" : "#3c3c38",
              backgroundColor: isSelected ? "rgba(180, 146, 56, 0.1)" : "#262624",
            }}
          >
            <span className="font-serif text-lg text-foreground">{token.greek}</span>
            <span className="text-xs font-medium mt-1" style={{ color: "#d4b96a" }}>
              {token.english}
            </span>
            <span className="text-[10px] text-muted-foreground mt-0.5">{token.strongs}</span>
          </button>
        );
      })}
    </div>
  );
}

function DefinitionPanel({ definition }: { definition: WordDefinition | null }) {
  if (!definition) {
    return (
      <div className="border-t border-border pt-6 text-center">
        <p className="text-muted-foreground text-sm">Select a word to view its definition</p>
      </div>
    );
  }
  return (
    <div className="border-t border-border pt-6">
      <p className="font-serif text-3xl text-foreground">{definition.word}</p>
      <p className="text-sm text-muted-foreground mt-1">
        {definition.transliteration} &middot; {definition.strongs}
      </p>

      <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2" style={{ color: "#c1c1b8" }}>
        Definition
      </p>
      <p className="text-sm text-foreground leading-relaxed">{definition.gloss}</p>

      <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2" style={{ color: "#c1c1b8" }}>
        Usage
      </p>
      <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
    </div>
  );
}

function CorpusPanel({ definition }: { definition: WordDefinition | null }) {
  if (!definition) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground text-sm">Select a word to see how it appears in the corpus</p>
      </div>
    );
  }
  return (
    <>
      <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "#c1c1b8" }}>
        From the corpus
      </p>
      <p className="font-serif text-lg mt-1 mb-6" style={{ color: "#d4b96a" }}>
        {definition.word} ({definition.transliteration})
      </p>

      <div className="space-y-4">
        {definition.corpusQuotes.map((quote, i) => (
          <div key={i} className="rounded-lg border border-border bg-card p-4">
            <p className="text-sm text-foreground leading-relaxed">&ldquo;{quote.text}&rdquo;</p>
            <div className="mt-3">
              <p className="text-xs font-medium text-foreground">{quote.author}</p>
              <p className="text-xs text-muted-foreground">{quote.source}</p>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function VerseSearch({
  verseRef,
  onChange,
}: {
  verseRef: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={verseRef}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Enter verse reference (e.g. John 1:1)"
        className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
      />
      <button className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium hover:bg-gold-hover transition-colors">
        <Search className="h-4 w-4" />
      </button>
    </div>
  );
}

export default function StudyPage() {
  const [verseRef, setVerseRef] = useState("John 1:1");
  const [selectedStrongs, setSelectedStrongs] = useState<string | null>(null);

  const definition = selectedStrongs
    ? PLACEHOLDER_DEFINITIONS[selectedStrongs] ?? null
    : null;

  return (
    <div className="flex h-dvh-safe flex-col bg-background">
      {/* Top Bar */}
      <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6">
        <div className="flex-1" />
        <ModeToggle />
        <div className="flex-1" />
      </div>

      {/* Desktop: two-column layout */}
      <div className="hidden md:flex flex-1 min-h-0">
        {/* Left Column: Search + Interlinear + Definition (380px fixed) */}
        <div
          className="w-[380px] shrink-0 flex flex-col overflow-y-auto"
          style={{ borderRight: "0.5px solid #3c3c38" }}
        >
          <div className="px-4 pt-6 pb-16">
            <VerseSearch verseRef={verseRef} onChange={setVerseRef} />

            <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-4" style={{ color: "#c1c1b8" }}>
              {verseRef}
            </p>

            <InterlinearBlocks
              tokens={PLACEHOLDER_TOKENS}
              selectedStrongs={selectedStrongs}
              onSelect={setSelectedStrongs}
            />

            <div className="mt-8">
              <DefinitionPanel definition={definition} />
            </div>
          </div>
        </div>

        {/* Right Column: Corpus Quotes (flex: 1) */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 pt-6 pb-16">
            <CorpusPanel definition={definition} />
          </div>
        </div>
      </div>

      {/* Mobile: single-column stacked layout */}
      <div className="flex flex-1 flex-col overflow-y-auto md:hidden">
        <div className="px-4 pt-6 pb-16">
          <VerseSearch verseRef={verseRef} onChange={setVerseRef} />

          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-4" style={{ color: "#c1c1b8" }}>
            {verseRef}
          </p>

          <InterlinearBlocks
            tokens={PLACEHOLDER_TOKENS}
            selectedStrongs={selectedStrongs}
            onSelect={setSelectedStrongs}
          />

          {definition && (
            <>
              <div className="mt-8">
                <DefinitionPanel definition={definition} />
              </div>

              <div className="mt-8">
                <CorpusPanel definition={definition} />
              </div>
            </>
          )}

          {!definition && (
            <div className="mt-8 border-t border-border pt-6 text-center">
              <p className="text-muted-foreground text-sm">Select a word to view its definition</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
