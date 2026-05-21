"use client";

import { useState, useCallback } from "react";
import { Search } from "lucide-react";
import { ModeToggle } from "@/components/rhemata/mode-toggle";

interface WordToken {
  greek: string;
  transliteration: string;
  english: string;
  strongs: string;
  morph: string;
}

interface VerseData {
  verse_id: string;
  book: string;
  chapter: number;
  verse: number;
  text: string;
  translation: string;
}

// Hardcoded fallback data for when API is unavailable
const FALLBACK_VERSES: Record<string, VerseData> = {
  "john 1:1": {
    verse_id: "JHN.1.1",
    book: "John",
    chapter: 1,
    verse: 1,
    text: "In the beginning was the Word, and the Word was with God, and the Word was God.",
    translation: "WEB",
  },
  "john 3:16": {
    verse_id: "JHN.3.16",
    book: "John",
    chapter: 3,
    verse: 16,
    text: "For God so loved the world, that he gave his one and only Son, that whoever believes in him should not perish, but have eternal life.",
    translation: "WEB",
  },
};

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

interface HistoryEntry {
  strongs: string;
  greek: string;
  transliteration: string;
}

function WordHistorySidebar({
  history,
  selectedStrongs,
  onSelect,
}: {
  history: HistoryEntry[];
  selectedStrongs: string | null;
  onSelect: (strongs: string) => void;
}) {
  return (
    <aside
      className="hidden md:flex w-64 shrink-0 flex-col h-full"
      style={{ background: "#1b1b19", borderRight: "0.5px solid #3c3c38" }}
    >
      <div className="px-4 pt-6 pb-4">
        <p
          className="text-xs font-medium uppercase tracking-wide"
          style={{ color: "#888780" }}
        >
          Word History
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {history.length === 0 ? (
          <p className="px-2 text-sm italic text-muted-foreground">
            Words you select will appear here
          </p>
        ) : (
          <div className="space-y-0.5">
            {history.map((entry) => {
              const isActive = selectedStrongs === entry.strongs;
              return (
                <button
                  key={entry.strongs}
                  onClick={() => onSelect(entry.strongs)}
                  className="w-full text-left rounded px-3 py-2 transition-colors"
                  style={{
                    backgroundColor: isActive ? "#262624" : "transparent",
                    borderLeft: isActive ? "2px solid #b49238" : "2px solid transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "#262624";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  <p className="text-sm" style={{ color: "#e6e6e6" }}>
                    {entry.greek}
                  </p>
                  <p className="text-xs" style={{ color: "#888780" }}>
                    {entry.transliteration} &middot; {entry.strongs}
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}

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
  onSubmit,
  loading,
}: {
  verseRef: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={verseRef}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSubmit();
        }}
        placeholder="Enter verse reference (e.g. John 1:1)"
        className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
      />
      <button
        onClick={onSubmit}
        disabled={loading}
        className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium hover:bg-gold-hover transition-colors disabled:opacity-50"
      >
        {loading ? (
          <span className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          <Search className="h-4 w-4" />
        )}
      </button>
    </div>
  );
}

function VerseDisplay({ verse, error }: { verse: VerseData | null; error: string | null }) {
  if (error) {
    return <p className="text-sm text-red-500 mt-4">{error}</p>;
  }
  if (!verse) return null;
  return (
    <div className="mt-4 rounded-lg border border-border bg-card p-4">
      <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "#c1c1b8" }}>
        {verse.book} {verse.chapter}:{verse.verse} ({verse.translation})
      </p>
      <p className="text-sm text-foreground leading-relaxed">{verse.text}</p>
    </div>
  );
}

export default function StudyPage() {
  const [verseRef, setVerseRef] = useState("John 1:1");
  const [selectedStrongs, setSelectedStrongs] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [verseData, setVerseData] = useState<VerseData | null>(null);
  const [verseLoading, setVerseLoading] = useState(false);
  const [verseError, setVerseError] = useState<string | null>(null);

  const lookupVerse = useCallback(async () => {
    const ref = verseRef.trim();
    if (!ref) return;
    setVerseLoading(true);
    setVerseError(null);
    setVerseData(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/study/verse?ref=${encodeURIComponent(ref)}`
      );
      if (res.status === 404) {
        // Try fallback
        const fallback = FALLBACK_VERSES[ref.toLowerCase()];
        if (fallback) {
          setVerseData(fallback);
        } else {
          setVerseError("Verse not found");
        }
        return;
      }
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      const data: VerseData = await res.json();
      setVerseData(data);
    } catch {
      // Fall back to hardcoded data
      const fallback = FALLBACK_VERSES[ref.toLowerCase()];
      if (fallback) {
        setVerseData(fallback);
      } else {
        setVerseError("Verse not found");
      }
    } finally {
      setVerseLoading(false);
    }
  }, [verseRef]);

  const definition = selectedStrongs
    ? PLACEHOLDER_DEFINITIONS[selectedStrongs] ?? null
    : null;

  const handleSelectWord = useCallback(
    (strongs: string | null) => {
      if (strongs === null) {
        setSelectedStrongs(null);
        return;
      }
      setSelectedStrongs(strongs);
      // Find the token info for this strongs number
      const token = PLACEHOLDER_TOKENS.find((t) => t.strongs === strongs);
      if (!token) return;
      setHistory((prev) => {
        const filtered = prev.filter((e) => e.strongs !== strongs);
        return [
          { strongs: token.strongs, greek: token.greek, transliteration: token.transliteration },
          ...filtered,
        ];
      });
    },
    [],
  );

  const handleHistorySelect = useCallback(
    (strongs: string) => {
      setSelectedStrongs(strongs);
    },
    [],
  );

  return (
    <div className="flex h-dvh-safe flex-col bg-background">
      {/* Top Bar */}
      <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6">
        <div className="flex-1" />
        <ModeToggle />
        <div className="flex-1" />
      </div>

      {/* Desktop: three-column layout */}
      <div className="hidden md:flex flex-1 min-h-0">
        {/* Word History Sidebar */}
        <WordHistorySidebar
          history={history}
          selectedStrongs={selectedStrongs}
          onSelect={handleHistorySelect}
        />

        {/* Middle Column: Search + Interlinear + Definition (380px fixed) */}
        <div
          className="w-[380px] shrink-0 flex flex-col overflow-y-auto"
          style={{ borderRight: "0.5px solid #3c3c38" }}
        >
          <div className="px-4 pt-6 pb-16">
            <VerseSearch verseRef={verseRef} onChange={setVerseRef} onSubmit={lookupVerse} loading={verseLoading} />

            <VerseDisplay verse={verseData} error={verseError} />

            <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-4" style={{ color: "#c1c1b8" }}>
              {verseRef}
            </p>

            <InterlinearBlocks
              tokens={PLACEHOLDER_TOKENS}
              selectedStrongs={selectedStrongs}
              onSelect={handleSelectWord}
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
          <VerseSearch verseRef={verseRef} onChange={setVerseRef} onSubmit={lookupVerse} loading={verseLoading} />

          <VerseDisplay verse={verseData} error={verseError} />

          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-4" style={{ color: "#c1c1b8" }}>
            {verseRef}
          </p>

          <InterlinearBlocks
            tokens={PLACEHOLDER_TOKENS}
            selectedStrongs={selectedStrongs}
            onSelect={handleSelectWord}
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
