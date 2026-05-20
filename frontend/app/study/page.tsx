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

interface WordDefinition {
  strongs: string;
  word: string;
  transliteration: string;
  gloss: string;
  meaning: string;
  occurrences: { reference: string; text: string }[];
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
    occurrences: [
      { reference: "John 1:1", text: "In the beginning was the Word" },
      { reference: "Genesis 1:1 (LXX)", text: "In the beginning God created the heaven and the earth" },
      { reference: "Colossians 1:18", text: "He is the beginning, the firstborn from the dead" },
    ],
  },
  G3056: {
    strongs: "G3056",
    word: "\u03BB\u03CC\u03B3\u03BF\u03C2",
    transliteration: "logos",
    gloss: "word, speech, reason",
    meaning:
      "From G3004; something said (including the thought); by implication a topic, also reasoning or motive. In John\u2019s prologue, Logos denotes the pre-existent divine Word, the second person of the Trinity, through whom all things were made.",
    occurrences: [
      { reference: "John 1:1", text: "In the beginning was the Word" },
      { reference: "John 1:14", text: "And the Word became flesh and dwelt among us" },
      { reference: "Revelation 19:13", text: "His name is called The Word of God" },
    ],
  },
  G2316: {
    strongs: "G2316",
    word: "\u03B8\u03B5\u03CC\u03C2",
    transliteration: "theos",
    gloss: "God, a deity",
    meaning:
      "Of uncertain affinity; a deity, especially the supreme Divinity. In the NT used of the one true God, the Father (John 17:3), and applied to Christ (John 1:1, 20:28, Romans 9:5).",
    occurrences: [
      { reference: "John 1:1", text: "and the Word was God" },
      { reference: "John 20:28", text: "Thomas said to Him, 'My Lord and my God!'" },
      { reference: "Romans 9:5", text: "Christ, who is God over all, blessed forever" },
    ],
  },
};

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

      {/* Main Content */}
      <div className="flex flex-1 min-h-0">
        {/* Left Column: Verse + Interlinear */}
        <div className="flex-1 overflow-y-auto border-r border-border">
          <div className="mx-auto max-w-2xl px-4 md:px-6 pt-8 pb-16">
            {/* Verse Lookup */}
            <div className="flex gap-2 mb-8">
              <input
                type="text"
                value={verseRef}
                onChange={(e) => setVerseRef(e.target.value)}
                placeholder="Enter verse reference (e.g. John 1:1)"
                className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
              />
              <button className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-gold-hover transition-colors">
                <Search className="h-4 w-4" />
                <span className="hidden sm:inline">Look up</span>
              </button>
            </div>

            {/* Verse Display */}
            <div className="mb-6">
              <p className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: "#c1c1b8" }}>
                {verseRef}
              </p>
              <p className="text-foreground leading-relaxed">
                In the beginning was the Word, and the Word was with God, and the Word was God.
              </p>
            </div>

            {/* Interlinear Grid */}
            <div>
              <p className="text-xs font-medium uppercase tracking-wide mb-4" style={{ color: "#c1c1b8" }}>
                Interlinear
              </p>
              <div className="flex flex-wrap gap-2">
                {PLACEHOLDER_TOKENS.map((token, i) => {
                  const isSelected = selectedStrongs === token.strongs;
                  const hasDef = token.strongs in PLACEHOLDER_DEFINITIONS;
                  return (
                    <button
                      key={i}
                      onClick={() => setSelectedStrongs(isSelected ? null : token.strongs)}
                      className="flex flex-col items-center rounded-lg border px-3 py-2 transition-colors min-w-[64px]"
                      style={{
                        borderColor: isSelected ? "#b49238" : "#3c3c38",
                        backgroundColor: isSelected ? "rgba(180, 146, 56, 0.1)" : "#262624",
                        cursor: hasDef ? "pointer" : "default",
                      }}
                    >
                      <span className="font-serif text-lg text-foreground">{token.greek}</span>
                      <span className="text-[11px] text-muted-foreground mt-0.5">{token.transliteration}</span>
                      <span className="text-xs font-medium mt-1" style={{ color: "#d4b96a" }}>
                        {token.english}
                      </span>
                      <span className="text-[10px] text-muted-foreground mt-0.5">{token.morph}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Definition Panel */}
        <div className="hidden md:flex w-96 flex-col overflow-y-auto bg-card">
          <div className="px-6 pt-8 pb-16">
            {definition ? (
              <>
                <div className="mb-6">
                  <p className="font-serif text-3xl text-foreground">{definition.word}</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {definition.transliteration} &middot; {definition.strongs}
                  </p>
                </div>

                <div className="mb-6">
                  <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "#c1c1b8" }}>
                    Gloss
                  </p>
                  <p className="text-foreground">{definition.gloss}</p>
                </div>

                <div className="mb-6">
                  <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "#c1c1b8" }}>
                    Definition
                  </p>
                  <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
                </div>

                <div>
                  <p className="text-xs font-medium uppercase tracking-wide mb-3" style={{ color: "#c1c1b8" }}>
                    Corpus Occurrences
                  </p>
                  <div className="space-y-3">
                    {definition.occurrences.map((occ, i) => (
                      <div key={i} className="rounded-lg border border-border p-3">
                        <p className="text-xs font-medium" style={{ color: "#d4b96a" }}>
                          {occ.reference}
                        </p>
                        <p className="text-sm text-foreground mt-1">{occ.text}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-center pt-32">
                <p className="text-muted-foreground text-sm">
                  Select a word to view its definition
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Mobile: Definition Bottom Sheet */}
        {definition && (
          <div className="md:hidden fixed inset-x-0 bottom-0 z-40 max-h-[60vh] overflow-y-auto rounded-t-2xl border-t border-border bg-card px-4 pt-4 pb-8 shadow-lg">
            <div className="flex justify-center mb-3">
              <div className="h-1 w-8 rounded-full" style={{ backgroundColor: "#3c3c38" }} />
            </div>
            <button
              onClick={() => setSelectedStrongs(null)}
              className="absolute top-3 right-3 text-muted-foreground hover:text-foreground text-sm min-h-[44px] min-w-[44px] flex items-center justify-center"
            >
              &times;
            </button>

            <p className="font-serif text-2xl text-foreground">{definition.word}</p>
            <p className="text-sm text-muted-foreground mt-0.5">
              {definition.transliteration} &middot; {definition.strongs}
            </p>

            <p className="text-xs font-medium uppercase tracking-wide mt-4 mb-1" style={{ color: "#c1c1b8" }}>
              Gloss
            </p>
            <p className="text-foreground text-sm">{definition.gloss}</p>

            <p className="text-xs font-medium uppercase tracking-wide mt-4 mb-1" style={{ color: "#c1c1b8" }}>
              Definition
            </p>
            <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>

            <p className="text-xs font-medium uppercase tracking-wide mt-4 mb-2" style={{ color: "#c1c1b8" }}>
              Corpus Occurrences
            </p>
            <div className="space-y-2">
              {definition.occurrences.map((occ, i) => (
                <div key={i} className="rounded-lg border border-border p-3">
                  <p className="text-xs font-medium" style={{ color: "#d4b96a" }}>{occ.reference}</p>
                  <p className="text-sm text-foreground mt-1">{occ.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
