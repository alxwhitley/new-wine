"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Search, Menu, Bookmark, Flag } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@/hooks/useAuth";
import { Sidebar } from "@/components/rhemata/sidebar";
import type { SavedWord } from "@/components/rhemata/sidebar";
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";
import { supabase } from "@/lib/supabase";
import { getAdjacentVerseId } from "@/lib/verse-counts";

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

interface WordSearchResult {
  id: string;
  title: string;
  author: string;
  word: string;
  transliteration: string;
  strongs_number: string;
}

// Full 66-book mapping: lowercase name/abbreviation -> 3-letter SBL code
const BOOK_MAP: Record<string, string> = {
  genesis: "GEN", gen: "GEN",
  exodus: "EXO", exo: "EXO", exod: "EXO",
  leviticus: "LEV", lev: "LEV",
  numbers: "NUM", num: "NUM",
  deuteronomy: "DEU", deut: "DEU", deu: "DEU",
  joshua: "JOS", josh: "JOS", jos: "JOS",
  judges: "JDG", judg: "JDG", jdg: "JDG",
  ruth: "RUT", rut: "RUT",
  "1 samuel": "1SA", "1samuel": "1SA", "1 sam": "1SA", "1sam": "1SA", "1sa": "1SA",
  "2 samuel": "2SA", "2samuel": "2SA", "2 sam": "2SA", "2sam": "2SA", "2sa": "2SA",
  "1 kings": "1KI", "1kings": "1KI", "1 kgs": "1KI", "1kgs": "1KI", "1ki": "1KI",
  "2 kings": "2KI", "2kings": "2KI", "2 kgs": "2KI", "2kgs": "2KI", "2ki": "2KI",
  "1 chronicles": "1CH", "1chronicles": "1CH", "1 chr": "1CH", "1chr": "1CH", "1ch": "1CH",
  "2 chronicles": "2CH", "2chronicles": "2CH", "2 chr": "2CH", "2chr": "2CH", "2ch": "2CH",
  ezra: "EZR", ezr: "EZR",
  nehemiah: "NEH", neh: "NEH",
  esther: "EST", esth: "EST", est: "EST",
  job: "JOB",
  psalms: "PSA", psalm: "PSA", psa: "PSA", ps: "PSA",
  proverbs: "PRO", prov: "PRO", pro: "PRO",
  ecclesiastes: "ECC", eccl: "ECC", ecc: "ECC",
  "song of solomon": "SNG", "song of songs": "SNG", song: "SNG", sng: "SNG", sos: "SNG",
  isaiah: "ISA", isa: "ISA",
  jeremiah: "JER", jer: "JER",
  lamentations: "LAM", lam: "LAM",
  ezekiel: "EZK", ezek: "EZK", ezk: "EZK",
  daniel: "DAN", dan: "DAN",
  hosea: "HOS", hos: "HOS",
  joel: "JOL", jol: "JOL",
  amos: "AMO", amo: "AMO",
  obadiah: "OBA", obad: "OBA", oba: "OBA",
  jonah: "JON", jon: "JON",
  micah: "MIC", mic: "MIC",
  nahum: "NAM", nah: "NAM", nam: "NAM",
  habakkuk: "HAB", hab: "HAB",
  zephaniah: "ZEP", zeph: "ZEP", zep: "ZEP",
  haggai: "HAG", hag: "HAG",
  zechariah: "ZEC", zech: "ZEC", zec: "ZEC",
  malachi: "MAL", mal: "MAL",
  matthew: "MAT", matt: "MAT", mat: "MAT",
  mark: "MRK", mrk: "MRK",
  luke: "LUK", luk: "LUK",
  john: "JHN", jhn: "JHN",
  acts: "ACT", act: "ACT",
  romans: "ROM", rom: "ROM",
  "1 corinthians": "1CO", "1corinthians": "1CO", "1 cor": "1CO", "1cor": "1CO", "1co": "1CO",
  "2 corinthians": "2CO", "2corinthians": "2CO", "2 cor": "2CO", "2cor": "2CO", "2co": "2CO",
  galatians: "GAL", gal: "GAL",
  ephesians: "EPH", eph: "EPH",
  philippians: "PHP", phil: "PHP", php: "PHP",
  colossians: "COL", col: "COL",
  "1 thessalonians": "1TH", "1thessalonians": "1TH", "1 thess": "1TH", "1thess": "1TH", "1th": "1TH",
  "2 thessalonians": "2TH", "2thessalonians": "2TH", "2 thess": "2TH", "2thess": "2TH", "2th": "2TH",
  "1 timothy": "1TI", "1timothy": "1TI", "1 tim": "1TI", "1tim": "1TI", "1ti": "1TI",
  "2 timothy": "2TI", "2timothy": "2TI", "2 tim": "2TI", "2tim": "2TI", "2ti": "2TI",
  titus: "TIT", tit: "TIT",
  philemon: "PHM", phlm: "PHM", phm: "PHM",
  hebrews: "HEB", heb: "HEB",
  james: "JAS", jas: "JAS",
  "1 peter": "1PE", "1peter": "1PE", "1 pet": "1PE", "1pet": "1PE", "1pe": "1PE",
  "2 peter": "2PE", "2peter": "2PE", "2 pet": "2PE", "2pet": "2PE", "2pe": "2PE",
  "1 john": "1JN", "1john": "1JN", "1 jn": "1JN", "1jn": "1JN",
  "2 john": "2JN", "2john": "2JN", "2 jn": "2JN", "2jn": "2JN",
  "3 john": "3JN", "3john": "3JN", "3 jn": "3JN", "3jn": "3JN",
  jude: "JUD", jud: "JUD",
  revelation: "REV", rev: "REV",
};

const ABBREV_TO_NAME: Record<string, string> = {
  GEN: "Genesis", EXO: "Exodus", LEV: "Leviticus", NUM: "Numbers",
  DEU: "Deuteronomy", JOS: "Joshua", JDG: "Judges", RUT: "Ruth",
  "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
  "1CH": "1 Chronicles", "2CH": "2 Chronicles", EZR: "Ezra", NEH: "Nehemiah",
  EST: "Esther", JOB: "Job", PSA: "Psalms", PRO: "Proverbs",
  ECC: "Ecclesiastes", SNG: "Song of Solomon", ISA: "Isaiah", JER: "Jeremiah",
  LAM: "Lamentations", EZK: "Ezekiel", DAN: "Daniel", HOS: "Hosea",
  JOL: "Joel", AMO: "Amos", OBA: "Obadiah", JON: "Jonah",
  MIC: "Micah", NAM: "Nahum", HAB: "Habakkuk", ZEP: "Zephaniah",
  HAG: "Haggai", ZEC: "Zechariah", MAL: "Malachi",
  MAT: "Matthew", MRK: "Mark", LUK: "Luke", JHN: "John",
  ACT: "Acts", ROM: "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
  GAL: "Galatians", EPH: "Ephesians", PHP: "Philippians", COL: "Colossians",
  "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy",
  "2TI": "2 Timothy", TIT: "Titus", PHM: "Philemon", HEB: "Hebrews",
  JAS: "James", "1PE": "1 Peter", "2PE": "2 Peter", "1JN": "1 John",
  "2JN": "2 John", "3JN": "3 John", JUD: "Jude", REV: "Revelation",
};

function parseRef(ref: string): { abbrev: string; chapter: number; verse: number } | null {
  const trimmed = ref.trim();
  const m = trimmed.match(/^(\d?\s*[A-Za-z ]+?)\s+(\d+):(\d+)$/);
  if (!m) return null;
  const bookRaw = m[1].trim().toLowerCase();
  const chapter = parseInt(m[2], 10);
  const verse = parseInt(m[3], 10);
  const bookNormalized = bookRaw.replace(/^(\d)\s*/, "$1 ").trim();
  const abbrev = BOOK_MAP[bookNormalized] ?? BOOK_MAP[bookNormalized.replace(/s$/, "")];
  if (!abbrev) return null;
  return { abbrev, chapter, verse };
}

const FALLBACK_VERSES: Record<string, VerseData> = {
  "JHN.1.1": {
    verse_id: "JHN.1.1", book: "John", chapter: 1, verse: 1,
    text: "In the beginning was the Word, and the Word was with God, and the Word was God.",
    translation: "WEB",
  },
  "JHN.3.16": {
    verse_id: "JHN.3.16", book: "John", chapter: 3, verse: 16,
    text: "For God so loved the world, that he gave his one and only Son, that whoever believes in him should not perish, but have eternal life.",
    translation: "WEB",
  },
};

interface CorpusQuote {
  text: string;
  author: string;
  source: string;
}

interface CorpusResult {
  content: string;
  title: string;
  author: string;
  source_kind: string;
  url: string | null;
  is_excerpt?: boolean;
}

interface CommentaryResult {
  document_id: string;
  title: string;
  author: string;
  source_kind: string;
  excerpt: string;
  content: string;
}

interface JewishPerspectiveContent {
  hebrew_root: string;
  targumic_usage: string;
  rabbinic_context: string;
  messianic_fulfillment: string;
  sources: string[];
}

type CorpusTab = "commentaries" | "jewish";

interface WordDefinition {
  strongs: string;
  word: string;
  transliteration: string;
  gloss: string;
  meaning: string;
  corpusQuotes: CorpusQuote[];
}

// NT book SBL codes for checking if a verse has Greek interlinear data
const NT_BOOKS = new Set([
  "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO",
  "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI",
  "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN",
  "3JN", "JUD", "REV",
]);

function InterlinearBlocks({
  tokens,
  selectedStrongs,
  onSelect,
  loading,
  isNT,
}: {
  tokens: WordToken[];
  selectedStrongs: string | null;
  onSelect: (strongs: string | null) => void;
  loading: boolean;
  isNT: boolean;
}) {
  const cardStyle = {
    backgroundColor: "#262624",
    border: "1px solid #3c3c38",
    borderRadius: 8,
    padding: 12,
  };

  if (loading) {
    return (
      <div style={cardStyle}>
        <div className="flex flex-wrap gap-3">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="flex flex-col items-center animate-pulse">
              <div className="h-5 w-10 rounded bg-border mb-1" />
              <div className="h-3 w-8 rounded bg-border mb-0.5" />
              <div className="h-2.5 w-10 rounded bg-border" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!isNT) {
    return (
      <div style={cardStyle}>
        <p className="text-sm" style={{ color: "#c1c1b8" }}>
          No Greek interlinear available for this verse
        </p>
      </div>
    );
  }

  if (tokens.length === 0) {
    return null;
  }

  return (
    <div style={{ ...cardStyle, padding: 0 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', padding: '12px' }}>
        {tokens.map((token, i) => {
          const isSelected = selectedStrongs === token.strongs;
          return (
            <button
              key={i}
              onClick={() => onSelect(isSelected ? null : token.strongs)}
              className="rounded transition-colors"
              style={{
                padding: '4px 6px',
                textAlign: 'center',
                cursor: 'pointer',
                border: isSelected ? "1px solid #b49238" : "1px solid transparent",
                backgroundColor: isSelected ? "rgba(180, 146, 56, 0.1)" : "transparent",
              }}
              onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "#2f2f2c"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = isSelected ? "rgba(180, 146, 56, 0.1)" : "transparent"; }}
            >
              <span className="font-serif" style={{ fontSize: '14px', display: 'block', lineHeight: '1.2' }}>{token.greek}</span>
              <span className="font-medium" style={{ fontSize: '11px', display: 'block', lineHeight: '1.2', color: "#d4b96a" }}>
                {token.english}
              </span>
              <span style={{ fontSize: '10px', display: 'block', lineHeight: '1.2', opacity: 0.6 }}>{token.strongs}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function DefinitionPanel({
  definition,
  isSaved,
  onToggleSave,
  isLoggedIn,
}: {
  definition: WordDefinition | null;
  isSaved: boolean;
  onToggleSave: () => void;
  isLoggedIn: boolean;
}) {
  if (!definition) {
    return (
      <div className="border-t border-border pt-6 text-center">
        <p className="text-muted-foreground text-sm">Select a word to view its definition</p>
      </div>
    );
  }
  return (
    <div className="border-t border-border pt-6 relative">
      <button
        onClick={onToggleSave}
        title={isLoggedIn ? (isSaved ? "Remove from saved" : "Save word") : "Sign in to save words"}
        className="absolute top-6 right-0 h-8 w-8 rounded-full flex items-center justify-center transition-colors"
        style={{
          backgroundColor: "#262624",
          border: "1px solid #3c3c38",
        }}
      >
        <Bookmark
          className="h-4 w-4"
          style={{
            color: isSaved ? "#b49238" : "#888780",
            fill: isSaved ? "#b49238" : "none",
          }}
        />
      </button>
      <p className="font-serif text-3xl text-foreground pr-10">{definition.word}</p>
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

function SkeletonCards() {
  return (
    <div className="mt-2 space-y-4">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-lg border border-border bg-card p-4 animate-pulse">
          <div className="h-3 rounded bg-border w-3/4 mb-3" />
          <div className="h-3 rounded bg-border w-full mb-2" />
          <div className="h-3 rounded bg-border w-5/6 mb-4" />
          <div className="h-2.5 rounded bg-border w-1/3 mb-1" />
          <div className="h-2.5 rounded bg-border w-1/4" />
        </div>
      ))}
    </div>
  );
}

function FlagModal({
  heading,
  sourceName,
  author,
  onSubmit,
  onClose,
}: {
  heading: string;
  sourceName: string;
  author: string;
  onSubmit: (comment: string) => void;
  onClose: () => void;
}) {
  const [comment, setComment] = useState("");
  const overlayRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: "rgba(27, 27, 25, 0.8)" }}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div
        className="w-full max-w-md mx-4 rounded-lg border p-6"
        style={{ backgroundColor: "#262624", borderColor: "#3c3c38" }}
      >
        <h3 className="font-serif text-lg text-foreground">{heading}</h3>
        <p className="text-xs mt-1 mb-4" style={{ color: "#c1c1b8" }}>
          {sourceName} &middot; {author}
        </p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Describe the theological concern..."
          rows={4}
          className="w-full rounded-lg border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold resize-none"
          style={{ backgroundColor: "#1f1e1d", borderColor: "#3c3c38" }}
        />
        <div className="flex justify-end gap-3 mt-4">
          <button
            onClick={() => onSubmit("")}
            className="px-4 py-2 text-sm rounded-lg cursor-pointer"
            style={{ color: "#c1c1b8" }}
          >
            Skip
          </button>
          <button
            onClick={() => onSubmit(comment)}
            className="px-4 py-2 text-sm font-medium rounded-lg cursor-pointer text-white"
            style={{ backgroundColor: "#b49238" }}
          >
            Submit
          </button>
        </div>
      </div>
    </div>
  );
}

function CorpusPanel({
  definition,
  selectedStrongs,
  corpusResults,
  corpusLoading,
  commentaryResults,
  commentaryLoading,
  hasVerse,
  wordStudyMode,
  wordStudyDoc,
  wordStudyContent,
  wordStudyLoading,
  activeCommentary,
  onCommentaryClick,
  onCommentaryBack,
  verseRef,
  accessToken,
}: {
  definition: WordDefinition | null;
  selectedStrongs: string | null;
  corpusResults: CorpusResult[];
  corpusLoading: boolean;
  commentaryResults: CommentaryResult[];
  commentaryLoading: boolean;
  hasVerse: boolean;
  wordStudyMode: boolean;
  wordStudyDoc: WordSearchResult | null;
  wordStudyContent: string | null;
  wordStudyLoading: boolean;
  activeCommentary: CommentaryResult | null;
  onCommentaryClick: (result: CommentaryResult) => void;
  onCommentaryBack: () => void;
  verseRef: string;
  accessToken: string | null;
}) {
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(new Set());
  const [flagModal, setFlagModal] = useState<{
    sourceType: string;
    documentId: string;
    heading: string;
    sourceName: string;
    author: string;
  } | null>(null);

  const submitFlag = useCallback(
    async (comment: string) => {
      if (!flagModal) return;
      try {
        await fetch(`${process.env.NEXT_PUBLIC_API_URL}/feedback`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({
            rating: "thumbs_down",
            question: verseRef,
            comment: comment || null,
            source_type: flagModal.sourceType,
            source_document_id: flagModal.documentId,
          }),
        });
      } catch {
        // silently fail
      }
      setFlaggedIds((prev) => new Set(prev).add(flagModal.documentId));
      setFlagModal(null);
    },
    [flagModal, verseRef, accessToken],
  );
  const flagModalEl = flagModal ? (
    <FlagModal
      heading={flagModal.heading}
      sourceName={flagModal.sourceName}
      author={flagModal.author}
      onSubmit={submitFlag}
      onClose={() => setFlagModal(null)}
    />
  ) : null;

  // Jewish Perspective state
  const [corpusTab, setCorpusTab] = useState<CorpusTab>("commentaries");
  const [jpContent, setJpContent] = useState<JewishPerspectiveContent | null>(null);
  const [jpLoading, setJpLoading] = useState(false);
  const [jpError, setJpError] = useState(false);
  const [jpDisclaimer, setJpDisclaimer] = useState(false);
  const [jpCheckedRef, setJpCheckedRef] = useState<string | null>(null);

  // Reset JP state when verse changes
  useEffect(() => {
    setJpContent(null);
    setJpError(false);
    setJpCheckedRef(null);
    setCorpusTab("commentaries");
  }, [verseRef]);

  const handleJpTabClick = useCallback(async () => {
    if (corpusTab === "jewish") return;
    setCorpusTab("jewish");

    // If already loaded for this verse, show it
    if (jpContent && jpCheckedRef === verseRef) return;

    // Check cache
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/jewish-perspective/${encodeURIComponent(verseRef)}`
      );
      if (!res.ok) throw new Error("cache check failed");
      const data = await res.json();
      if (data.cached && data.content) {
        setJpContent(data.content);
        setJpCheckedRef(verseRef);
        return;
      }
    } catch {
      // fall through to disclaimer
    }

    // Not cached — show disclaimer
    setJpDisclaimer(true);
  }, [corpusTab, jpContent, jpCheckedRef, verseRef]);

  const handleJpGenerate = useCallback(async () => {
    setJpDisclaimer(false);
    setJpLoading(true);
    setJpError(false);

    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/jewish-perspective/${encodeURIComponent(verseRef)}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
        }
      );
      if (!res.ok) throw new Error("generate failed");
      const data = await res.json();
      setJpContent(data.content);
      setJpCheckedRef(verseRef);
    } catch {
      setJpError(true);
    } finally {
      setJpLoading(false);
    }
  }, [verseRef, accessToken]);

  // Word study mode: show full excerpt/article
  if (wordStudyMode && wordStudyDoc) {
    return (
      <>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "#c1c1b8" }}>
              From the library
            </p>
            <p className="font-serif text-lg mt-1 mb-6" style={{ color: "#d4b96a" }}>
              {wordStudyDoc.word || wordStudyDoc.transliteration} ({wordStudyDoc.transliteration})
            </p>
          </div>
          {!flaggedIds.has(wordStudyDoc.id) && (
            <button
              onClick={() => setFlagModal({
                sourceType: "word_study",
                documentId: wordStudyDoc.id,
                heading: "Flag Word Study",
                sourceName: wordStudyDoc.title,
                author: wordStudyDoc.author,
              })}
              className="h-7 w-7 rounded-full flex items-center justify-center cursor-pointer shrink-0"
              style={{ backgroundColor: "#1f1e1d", border: "1px solid #3c3c38" }}
              title="Flag this content"
            >
              <Flag className="h-3.5 w-3.5" style={{ color: "#888780" }} />
            </button>
          )}
        </div>
        {wordStudyLoading ? (
          <SkeletonCards />
        ) : wordStudyContent ? (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{wordStudyContent}</ReactMarkdown>
          </div>
        ) : (
          <div className="py-12 text-center">
            <p className="text-sm" style={{ color: "#c1c1b8" }}>
              No content available for this word study yet.
            </p>
          </div>
        )}
        {flagModalEl}
      </>
    );
  }

  // State 2: word selected — show word study corpus results
  // Enters when a word is selected from the interlinear grid (selectedStrongs is set)
  if (selectedStrongs) {
    const label = definition
      ? `${definition.word} (${definition.transliteration})`
      : corpusResults.length > 0
        ? corpusResults[0].title
        : null;

    return (
      <>
        <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "#c1c1b8" }}>
          From the library
        </p>
        {label && (
          <p className="font-serif text-lg mt-1 mb-6" style={{ color: "#d4b96a" }}>
            {label}
          </p>
        )}
        {corpusLoading ? (
          <SkeletonCards />
        ) : corpusResults.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm" style={{ color: "#c1c1b8" }}>
              No library entries for this word yet — more teaching content coming soon.
            </p>
          </div>
        ) : corpusResults.some((r) => r.is_excerpt) ? (
          <div className="prose prose-invert prose-sm max-w-none">
            <ReactMarkdown>{corpusResults.filter((r) => r.is_excerpt).map((r) => r.content).join("\n\n")}</ReactMarkdown>
          </div>
        ) : (
          <div className="space-y-4">
            {corpusResults.map((r, i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-4">
                <p className="text-sm text-foreground leading-relaxed">&ldquo;{r.content}&rdquo;</p>
                <div className="mt-3">
                  <p className="text-xs font-medium text-foreground">{r.author}</p>
                  <p className="text-xs text-muted-foreground">{r.title}</p>
                </div>
              </div>
            ))}
          </div>
        )}
        {flagModalEl}
      </>
    );
  }

  // State 1: verse loaded, no word selected — show commentary
  if (hasVerse) {
    // Reader view: show full commentary content
    if (activeCommentary) {
      return (
        <>
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={onCommentaryBack}
              className="text-sm cursor-pointer hover:underline"
              style={{ color: "#c1c1b8" }}
            >
              &larr; Back
            </button>
            {!flaggedIds.has(activeCommentary.document_id) && (
              <button
                onClick={() => setFlagModal({
                  sourceType: "commentary",
                  documentId: activeCommentary.document_id,
                  heading: "Flag Commentary",
                  sourceName: activeCommentary.title,
                  author: activeCommentary.author,
                })}
                className="h-7 w-7 rounded-full flex items-center justify-center cursor-pointer"
                style={{ backgroundColor: "#1f1e1d", border: "1px solid #3c3c38" }}
                title="Flag this content"
              >
                <Flag className="h-3.5 w-3.5" style={{ color: "#888780" }} />
              </button>
            )}
          </div>
          <p className="text-xs mb-6" style={{ color: "#c1c1b8" }}>
            {activeCommentary.title} &middot; {activeCommentary.author}
          </p>
          <div className="mx-auto" style={{ maxWidth: 680 }}>
            {activeCommentary.content
              .split(/\n\n+/)
              .flatMap((block) =>
                block.split(/(?<=\.)\s+(?=[A-Z])/)
              )
              .filter((p) => p.trim())
              .map((para, i) => (
                <p
                  key={i}
                  className="text-foreground mb-4"
                  style={{ fontSize: 15, lineHeight: 1.7 }}
                >
                  {para.trim()}
                </p>
              ))}
          </div>
          {flagModalEl}
        </>
      );
    }

    const tabBar = (
      <div className="flex gap-6 mb-5" style={{ borderBottom: "1px solid #3c3c38" }}>
        <button
          onClick={() => setCorpusTab("commentaries")}
          className="pb-2 text-sm font-medium cursor-pointer transition-colors"
          style={{
            color: corpusTab === "commentaries" ? "#e6e6e6" : "#c1c1b8",
            borderBottom: corpusTab === "commentaries" ? "2px solid #b49238" : "2px solid transparent",
            marginBottom: "-1px",
          }}
        >
          Commentaries
        </button>
        <button
          onClick={handleJpTabClick}
          className="pb-2 text-sm font-medium cursor-pointer transition-colors"
          style={{
            color: corpusTab === "jewish" ? "#e6e6e6" : "#c1c1b8",
            borderBottom: corpusTab === "jewish" ? "2px solid #b49238" : "2px solid transparent",
            marginBottom: "-1px",
          }}
        >
          Jewish Perspective
        </button>
      </div>
    );

    // Jewish Perspective tab content
    if (corpusTab === "jewish") {
      return (
        <>
          {tabBar}
          {jpLoading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="rounded-lg border p-4 animate-pulse"
                  style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
                >
                  <div className="h-2.5 rounded bg-border w-1/3 mb-3" />
                  <div className="h-3 rounded bg-border w-full mb-2" />
                  <div className="h-3 rounded bg-border w-5/6 mb-2" />
                  <div className="h-3 rounded bg-border w-4/6" />
                </div>
              ))}
              <p className="text-center text-sm mt-4" style={{ color: "#c1c1b8" }}>
                Researching Messianic Jewish sources...
              </p>
            </div>
          ) : jpError ? (
            <div className="py-12 text-center">
              <p className="text-sm" style={{ color: "#c1c1b8" }}>
                Unable to generate. Please try again.
              </p>
              <button
                onClick={() => setCorpusTab("commentaries")}
                className="text-sm mt-3 cursor-pointer hover:underline"
                style={{ color: "#d4b96a" }}
              >
                View Commentaries
              </button>
            </div>
          ) : jpContent ? (
            <div className="space-y-3">
              {([
                { key: "hebrew_root", label: "Hebrew & Aramaic Root" },
                { key: "targumic_usage", label: "Targumic Usage" },
                { key: "rabbinic_context", label: "Rabbinic & Second Temple Context" },
                { key: "messianic_fulfillment", label: "Messianic Fulfillment" },
              ] as const).map((section) => (
                <div
                  key={section.key}
                  className="rounded-lg border p-4"
                  style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
                >
                  <p
                    className="font-medium uppercase tracking-wide mb-2"
                    style={{ color: "#c1c1b8", fontSize: 11, letterSpacing: "0.05em" }}
                  >
                    {section.label}
                  </p>
                  <p style={{ color: "#e6e6e6", fontSize: 14, lineHeight: 1.7 }}>
                    {jpContent[section.key]}
                  </p>
                </div>
              ))}
              {jpContent.sources && jpContent.sources.length > 0 && (
                <div
                  className="rounded-lg border p-4"
                  style={{ borderColor: "#3c3c38", backgroundColor: "#262624" }}
                >
                  <p
                    className="font-medium uppercase tracking-wide mb-2"
                    style={{ color: "#c1c1b8", fontSize: 11, letterSpacing: "0.05em" }}
                  >
                    Sources Consulted
                  </p>
                  <ul className="list-disc list-inside space-y-1">
                    {jpContent.sources.map((src, i) => (
                      <li key={i} style={{ color: "#e6e6e6", fontSize: 13, lineHeight: 1.6 }}>
                        {src}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="py-12 text-center">
              <p className="text-sm" style={{ color: "#c1c1b8" }}>
                Select the Jewish Perspective tab to generate a summary.
              </p>
            </div>
          )}
          {jpDisclaimer && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center"
              style={{ backgroundColor: "rgba(27, 27, 25, 0.8)" }}
              onClick={(e) => { if (e.target === e.currentTarget) { setJpDisclaimer(false); setCorpusTab("commentaries"); } }}
            >
              <div
                className="w-full max-w-[420px] mx-4 rounded-lg border p-6"
                style={{ backgroundColor: "#262624", borderColor: "#3c3c38" }}
              >
                <h3 className="font-serif text-lg" style={{ color: "#d4b96a" }}>
                  Jewish Perspective
                </h3>
                <p className="text-sm mt-3 leading-relaxed" style={{ color: "#c1c1b8" }}>
                  Generating this summary searches live Messianic Jewish scholarship
                  sources in real time. This feature is in early access.
                </p>
                <p className="text-sm mt-3 leading-relaxed" style={{ color: "#c1c1b8" }}>
                  Once generated, this summary is saved permanently and free for
                  everyone who studies this verse after you.
                </p>
                <div className="flex justify-end gap-3 mt-6">
                  <button
                    onClick={() => { setJpDisclaimer(false); setCorpusTab("commentaries"); }}
                    className="px-4 py-2 text-sm rounded-lg cursor-pointer"
                    style={{ color: "#c1c1b8" }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleJpGenerate}
                    className="px-4 py-2 text-sm font-medium rounded-lg cursor-pointer text-white"
                    style={{ backgroundColor: "#b49238" }}
                  >
                    Generate
                  </button>
                </div>
              </div>
            </div>
          )}
          {flagModalEl}
        </>
      );
    }

    // Commentaries tab (default)
    return (
      <>
        {tabBar}
        {commentaryLoading ? (
          <SkeletonCards />
        ) : commentaryResults.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm" style={{ color: "#c1c1b8" }}>
              No commentary found for this verse.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {commentaryResults.map((r, i) => (
              <div
                key={i}
                className="rounded-lg border border-border bg-card p-4 cursor-pointer transition-colors relative group"
                onClick={() => onCommentaryClick(r)}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#4a4a44"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = ""; }}
              >
                {!flaggedIds.has(r.document_id) && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFlagModal({
                        sourceType: "commentary",
                        documentId: r.document_id,
                        heading: "Flag Commentary",
                        sourceName: r.title,
                        author: r.author,
                      });
                    }}
                    className="absolute top-3 right-3 h-7 w-7 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    style={{ backgroundColor: "#1f1e1d", border: "1px solid #3c3c38" }}
                    title="Flag this content"
                  >
                    <Flag className="h-3.5 w-3.5" style={{ color: "#888780" }} />
                  </button>
                )}
                <p className="text-sm font-medium" style={{ color: "#d4b96a" }}>{r.author}</p>
                <p className="text-xs text-muted-foreground mt-0.5 mb-3">{r.title}</p>
                <p className="text-sm text-foreground leading-relaxed">{r.excerpt}</p>
              </div>
            ))}
          </div>
        )}
        {flagModalEl}
      </>
    );
  }

  // No verse loaded yet
  return (
    <>
      <div className="flex items-center justify-center h-full">
        <p className="text-muted-foreground text-sm">Search a verse to see commentary from the library</p>
      </div>
      {flagModalEl}
    </>
  );
}

const BOOK_NAMES = [
  "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
  "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
  "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles",
  "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
  "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah",
  "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
  "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
  "Haggai", "Zechariah", "Malachi",
  "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
  "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
  "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
  "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
  "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
  "Jude", "Revelation",
];

function matchBooks(input: string): string[] {
  const trimmed = input.trim().toLowerCase();
  if (trimmed.length === 0 || /\d/.test(trimmed.replace(/^[123]\s*/, ""))) return [];
  return BOOK_NAMES.filter((b) => b.toLowerCase().startsWith(trimmed)).slice(0, 5);
}

function VerseSearch({
  verseRef,
  onChange,
  onSubmit,
  loading,
  wordSearchResults,
  wordSearchOpen,
  onWordStudySelect,
}: {
  verseRef: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  wordSearchResults: WordSearchResult[];
  wordSearchOpen: boolean;
  onWordStudySelect: (result: WordSearchResult) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const bookMatches = matchBooks(verseRef);
  const showBookDropdown = bookMatches.length > 0 && !/\d/.test(verseRef.trim());
  const showWordDropdown = !showBookDropdown && wordSearchOpen && wordSearchResults.length > 0;

  return (
    <div className="relative" ref={containerRef}>
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={verseRef}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmit();
          }}
          placeholder="Search verse or word (e.g. John 1:1 or faith)"
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
      {showBookDropdown && (
        <div
          className="absolute top-full left-0 right-12 mt-1 rounded-lg border shadow-lg z-50 overflow-hidden"
          style={{ backgroundColor: "#262624", borderColor: "#3c3c38" }}
        >
          {bookMatches.map((name) => (
            <button
              key={name}
              onClick={() => {
                onChange(name + " ");
                inputRef.current?.focus();
              }}
              className="w-full text-left px-4 py-3 text-sm cursor-pointer"
              style={{ color: "#e6e6e6", borderBottom: "1px solid #3c3c38" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "#2f2f2c"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      {showWordDropdown && (
        <div
          className="absolute top-full left-0 right-12 mt-1 rounded-lg border border-border bg-card shadow-lg z-50 overflow-hidden"
        >
          {wordSearchResults.map((r) => (
            <button
              key={r.id}
              onClick={() => onWordStudySelect(r)}
              className="w-full text-left px-4 py-3 text-sm transition-colors cursor-pointer"
              style={{ borderBottom: "1px solid #3c3c38" }}
              onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "#2f2f2c"; }}
              onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              <span className="text-foreground font-medium">{r.word || r.transliteration}</span>
              <span className="text-muted-foreground">
                {r.word && r.transliteration && r.word !== r.transliteration ? ` (${r.transliteration})` : ""}
              </span>
              {r.strongs_number && (
                <span style={{ color: "#d4b96a" }}> &middot; {r.strongs_number}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function VerseDisplay({
  verse,
  error,
  onStepPrev,
  onStepNext,
  hasPrev,
  hasNext,
  selectedStrongs,
  onDeselect,
}: {
  verse: VerseData | null;
  error: string | null;
  onStepPrev: () => void;
  onStepNext: () => void;
  hasPrev: boolean;
  hasNext: boolean;
  selectedStrongs: string | null;
  onDeselect: () => void;
}) {
  if (error) {
    return <p className="text-sm mt-4" style={{ color: "#993c1d" }}>{error}</p>;
  }
  if (!verse) return null;
  return (
    <div
      className="mt-4 rounded-lg border border-border bg-card relative"
      style={{ minHeight: 120, cursor: selectedStrongs ? "pointer" : "default" }}
      onClick={() => { if (selectedStrongs) onDeselect(); }}
    >
      <div className="p-4 pb-10">
        <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: "#c1c1b8" }}>
          {verse.book} {verse.chapter}:{verse.verse} ({verse.translation})
        </p>
        <p className="text-sm text-foreground leading-relaxed">{verse.text}</p>
        {selectedStrongs && (
          <p style={{ fontSize: '11px', color: '#c1c1b8', marginTop: '8px' }}>Tap verse to return to commentary</p>
        )}
      </div>
      <div
        className="absolute bottom-0 left-0 right-0 flex items-center justify-center gap-3 py-1.5"
        style={{ borderTop: "1px solid #3c3c38", backgroundColor: "#262624", borderRadius: "0 0 0.5rem 0.5rem" }}
      >
        <button
          onClick={(e) => { e.stopPropagation(); onStepPrev(); }}
          disabled={!hasPrev}
          className="text-sm font-medium"
          style={{ color: "#c1c1b8", opacity: hasPrev ? 1 : 0.5 }}
        >
          &larr;
        </button>
        <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "#c1c1b8" }}>
          {verse.book} {verse.chapter}:{verse.verse}
        </p>
        <button
          onClick={(e) => { e.stopPropagation(); onStepNext(); }}
          disabled={!hasNext}
          className="text-sm font-medium"
          style={{ color: "#c1c1b8", opacity: hasNext ? 1 : 0.5 }}
        >
          &rarr;
        </button>
      </div>
    </div>
  );
}

function WordStudyPanel({
  doc,
  definition,
  isSaved,
  onToggleSave,
  isLoggedIn,
}: {
  doc: WordSearchResult;
  definition: WordDefinition | null;
  isSaved: boolean;
  onToggleSave: () => void;
  isLoggedIn: boolean;
}) {
  return (
    <div className="mt-8 relative">
      <button
        onClick={onToggleSave}
        title={isLoggedIn ? (isSaved ? "Remove from saved" : "Save word") : "Sign in to save words"}
        className="absolute top-0 right-0 h-8 w-8 rounded-full flex items-center justify-center transition-colors"
        style={{
          backgroundColor: "#262624",
          border: "1px solid #3c3c38",
        }}
      >
        <Bookmark
          className="h-4 w-4"
          style={{
            color: isSaved ? "#b49238" : "#888780",
            fill: isSaved ? "#b49238" : "none",
          }}
        />
      </button>
      <p className="font-serif text-3xl text-foreground pr-10">
        {definition?.word || doc.word || doc.transliteration}
      </p>
      <p className="text-sm text-muted-foreground mt-1">
        {doc.transliteration} &middot; {doc.strongs_number}
      </p>

      {definition && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2" style={{ color: "#c1c1b8" }}>
            Definition
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.gloss}</p>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2" style={{ color: "#c1c1b8" }}>
            Usage
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}

      <p className="text-sm mt-8" style={{ color: "#c1c1b8" }}>
        Enter a verse reference above to see this word in context
      </p>
    </div>
  );
}

export default function StudyPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [verseRef, setVerseRef] = useState("John 1:1");
  const [selectedStrongs, setSelectedStrongs] = useState<string | null>(null);
  const [verseData, setVerseData] = useState<VerseData | null>(null);
  const [verseLoading, setVerseLoading] = useState(false);
  const [verseError, setVerseError] = useState<string | null>(null);

  const [tokens, setTokens] = useState<WordToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);

  // Word search state
  const [wordSearchResults, setWordSearchResults] = useState<WordSearchResult[]>([]);
  const [wordSearchOpen, setWordSearchOpen] = useState(false);

  // Word study mode state
  const [wordStudyMode, setWordStudyMode] = useState(false);
  const [wordStudyDoc, setWordStudyDoc] = useState<WordSearchResult | null>(null);
  const [wordStudyContent, setWordStudyContent] = useState<string | null>(null);
  const [wordStudyLoading, setWordStudyLoading] = useState(false);

  // Saved words
  const [savedWords, setSavedWords] = useState<SavedWord[]>([]);
  const savedStrongsSet = new Set(savedWords.map((w) => w.strongs_number));

  // Fetch saved words on login
  useEffect(() => {
    if (!user) {
      setSavedWords([]);
      return;
    }
    supabase
      .from("saved_words")
      .select("*")
      .eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .then(({ data }) => {
        if (data) setSavedWords(data);
      });
  }, [user]);

  const toggleSaveWord = useCallback(
    async (token: WordToken) => {
      if (!user) {
        setShowLogin(true);
        return;
      }

      const isSaved = savedStrongsSet.has(token.strongs);

      if (isSaved) {
        // Unsave
        await supabase
          .from("saved_words")
          .delete()
          .eq("user_id", user.id)
          .eq("strongs_number", token.strongs);
        setSavedWords((prev) => prev.filter((w) => w.strongs_number !== token.strongs));
      } else {
        // Save
        const { data } = await supabase
          .from("saved_words")
          .insert({
            user_id: user.id,
            strongs_number: token.strongs,
            greek_word: token.greek,
            transliteration: token.transliteration,
            english_gloss: token.english,
          })
          .select()
          .single();
        if (data) {
          setSavedWords((prev) => [data, ...prev]);
        }
      }
    },
    [user, savedStrongsSet],
  );

  const fetchVerseById = useCallback(async (verseId: string) => {
    const parts = verseId.split(".");
    if (parts.length !== 3) return;
    const abbrev = parts[0];
    const chapter = parseInt(parts[1], 10);
    const verse = parseInt(parts[2], 10);

    setVerseLoading(true);
    setVerseError(null);
    setVerseData(null);

    try {
      const { data, error } = await supabase
        .from("verses")
        .select("*")
        .eq("verse_id", verseId)
        .single();

      if (error || !data) {
        const fallback = FALLBACK_VERSES[verseId];
        if (fallback) {
          setVerseData(fallback);
        } else {
          setVerseError("Verse not found");
        }
        return;
      }

      setVerseData({
        verse_id: data.verse_id,
        book: ABBREV_TO_NAME[abbrev] ?? abbrev,
        chapter,
        verse,
        text: data.text ?? "",
        translation: data.translation ?? "WEB",
      });
    } catch {
      const fallback = FALLBACK_VERSES[verseId];
      if (fallback) {
        setVerseData(fallback);
      } else {
        setVerseError("Verse not found");
      }
    } finally {
      setVerseLoading(false);
    }
  }, []);

  const lookupVerse = useCallback(async () => {
    const ref = verseRef.trim();
    if (!ref) return;

    // Reset word study mode on verse lookup
    setWordStudyMode(false);
    setWordStudyDoc(null);
    setWordStudyContent(null);
    setWordSearchOpen(false);

    const parsed = parseRef(ref);
    if (!parsed) {
      setVerseError("Verse not found");
      setVerseData(null);
      return;
    }

    const verseId = `${parsed.abbrev}.${parsed.chapter}.${parsed.verse}`;
    await fetchVerseById(verseId);
  }, [verseRef, fetchVerseById]);

  // Fetch default verse on mount
  useEffect(() => {
    const parsed = parseRef(verseRef);
    if (parsed) {
      fetchVerseById(`${parsed.abbrev}.${parsed.chapter}.${parsed.verse}`);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch interlinear tokens when verse changes
  useEffect(() => {
    setSelectedStrongs(null);
    setTokens([]);

    const verseId = verseData?.verse_id;
    if (!verseId) return;

    const book = verseId.split(".")[0];
    if (!NT_BOOKS.has(book)) return;

    setTokensLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/interlinear?verse_id=${encodeURIComponent(verseId)}`)
      .then((res) => {
        if (!res.ok) throw new Error("interlinear fetch failed");
        return res.json();
      })
      .then((data: Array<{ greek_word: string; transliteration: string; strongs_number: string; english_gloss: string; morphology: string; word_position: number }>) => {
        setTokens(
          data.map((w) => ({
            greek: w.greek_word,
            transliteration: w.transliteration || "",
            english: w.english_gloss || "",
            strongs: w.strongs_number || "",
            morph: w.morphology || "",
          }))
        );
      })
      .catch(() => {
        setTokens([]);
      })
      .finally(() => {
        setTokensLoading(false);
      });
  }, [verseData?.verse_id]);

  // Debounced word search (suppressed when book autocomplete is active)
  useEffect(() => {
    const trimmed = verseRef.trim();
    const isPlainWord = trimmed.length >= 2 && !/\d/.test(trimmed);
    const hasBookMatch = matchBooks(verseRef).length > 0;

    if (!isPlainWord || hasBookMatch) {
      setWordSearchResults([]);
      setWordSearchOpen(false);
      return;
    }

    const timer = setTimeout(() => {
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/wordsearch?q=${encodeURIComponent(trimmed)}`)
        .then((res) => {
          if (!res.ok) throw new Error("wordsearch failed");
          return res.json();
        })
        .then((data) => {
          setWordSearchResults(data.results ?? []);
          setWordSearchOpen((data.results ?? []).length > 0);
        })
        .catch(() => {
          setWordSearchResults([]);
          setWordSearchOpen(false);
        });
    }, 300);
    return () => clearTimeout(timer);
  }, [verseRef]);

  // Handle word study selection from dropdown
  const handleWordStudySelect = useCallback((result: WordSearchResult) => {
    setWordStudyMode(true);
    setWordStudyDoc(result);
    setWordSearchOpen(false);
    setVerseData(null);
    setVerseError(null);
    setSelectedStrongs(null);
    setCommentaryResults([]);
    setCorpusResults([]);
    setVerseRef(result.word || result.transliteration);

    // Fetch word study content
    setWordStudyLoading(true);
    setWordStudyContent(null);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/wordstudy/${result.id}`)
      .then((res) => {
        if (!res.ok) throw new Error("wordstudy fetch failed");
        return res.json();
      })
      .then((data) => {
        setWordStudyContent(data.content ?? null);
      })
      .catch(() => {
        setWordStudyContent(null);
      })
      .finally(() => {
        setWordStudyLoading(false);
      });
  }, []);

  // Stepper navigation
  const currentVerseId = verseData?.verse_id ?? null;
  const prevVerseId = currentVerseId ? getAdjacentVerseId(currentVerseId, "prev") : null;
  const nextVerseId = currentVerseId ? getAdjacentVerseId(currentVerseId, "next") : null;

  const stepVerse = useCallback(async (direction: "prev" | "next") => {
    if (!currentVerseId) return;
    const targetId = getAdjacentVerseId(currentVerseId, direction);
    if (!targetId) return;

    const parts = targetId.split(".");
    const bookName = ABBREV_TO_NAME[parts[0]] ?? parts[0];
    setVerseRef(`${bookName} ${parts[1]}:${parts[2]}`);
    await fetchVerseById(targetId);
  }, [currentVerseId, fetchVerseById]);

  // Keyboard navigation: ArrowLeft/ArrowRight
  useEffect(() => {
    if (!currentVerseId) return;

    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        stepVerse("prev");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        stepVerse("next");
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [currentVerseId, stepVerse]);

  // Build definition from the interlinear token data
  const selectedToken = selectedStrongs
    ? tokens.find((t) => t.strongs === selectedStrongs) ?? null
    : null;
  const definition: WordDefinition | null = selectedToken
    ? {
        strongs: selectedToken.strongs,
        word: selectedToken.greek,
        transliteration: selectedToken.transliteration,
        gloss: selectedToken.english,
        meaning: "",
        corpusQuotes: [],
      }
    : null;

  // Definition for word study mode — no placeholder data available
  const wordStudyDefinition: WordDefinition | null = null;

  // Commentary results (State 1: verse loaded, no word selected)
  const [commentaryResults, setCommentaryResults] = useState<CommentaryResult[]>([]);
  const [commentaryLoading, setCommentaryLoading] = useState(false);
  const [activeCommentary, setActiveCommentary] = useState<CommentaryResult | null>(null);

  useEffect(() => {
    if (!verseData?.text) {
      setCommentaryResults([]);
      setActiveCommentary(null);
      return;
    }

    setCommentaryLoading(true);
    const params = new URLSearchParams({ verse_text: verseData.text });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/commentary?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error("commentary fetch failed");
        return res.json();
      })
      .then((data) => {
        setCommentaryResults(data.results ?? []);
      })
      .catch(() => {
        setCommentaryResults([]);
      })
      .finally(() => {
        setCommentaryLoading(false);
      });
  }, [verseData?.text]);

  // Corpus results (State 2: word selected)
  const [corpusResults, setCorpusResults] = useState<CorpusResult[]>([]);
  const [corpusLoading, setCorpusLoading] = useState(false);

  useEffect(() => {
    if (!selectedStrongs) {
      setCorpusResults([]);
      return;
    }

    const token = tokens.find((t) => t.strongs === selectedStrongs);
    if (!token) {
      setCorpusResults([]);
      return;
    }

    const params = new URLSearchParams();
    if (verseRef.trim()) params.set("verse", verseRef.trim());
    params.set("transliteration", token.transliteration);
    params.set("strongs", token.strongs);
    params.set("source_kind", "word_study");

    setCorpusLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/corpus?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error("corpus fetch failed");
        return res.json();
      })
      .then((data) => {
        setCorpusResults(data.results ?? []);
      })
      .catch(() => {
        setCorpusResults([]);
      })
      .finally(() => {
        setCorpusLoading(false);
      });
  }, [selectedStrongs, verseRef, tokens]);

  const handleSelectWord = useCallback(
    (strongs: string | null) => {
      setSelectedStrongs(strongs);
    },
    [],
  );

  const handleToggleSaveSelected = useCallback(() => {
    if (!selectedStrongs) return;
    const token = tokens.find((t) => t.strongs === selectedStrongs);
    if (token) toggleSaveWord(token);
  }, [selectedStrongs, tokens, toggleSaveWord]);

  const handleToggleSaveWordStudy = useCallback(() => {
    if (!wordStudyDoc) return;
    const syntheticToken: WordToken = {
      greek: wordStudyDoc.word || wordStudyDoc.transliteration,
      transliteration: wordStudyDoc.transliteration,
      english: wordStudyDoc.word,
      strongs: wordStudyDoc.strongs_number,
      morph: "",
    };
    toggleSaveWord(syntheticToken);
  }, [wordStudyDoc, toggleSaveWord]);

  const handleSidebarSavedWordSelect = useCallback(
    (strongs: string) => {
      setSelectedStrongs(strongs);
    },
    [],
  );

  const corpusPanelProps = {
    definition,
    selectedStrongs,
    corpusResults,
    corpusLoading,
    commentaryResults,
    commentaryLoading,
    hasVerse: !!verseData,
    wordStudyMode,
    wordStudyDoc,
    wordStudyContent,
    wordStudyLoading,
    activeCommentary,
    onCommentaryClick: setActiveCommentary,
    onCommentaryBack: () => setActiveCommentary(null),
    verseRef,
    accessToken,
  };

  const verseSearchProps = {
    verseRef,
    onChange: setVerseRef,
    onSubmit: lookupVerse,
    loading: verseLoading,
    wordSearchResults,
    wordSearchOpen,
    onWordStudySelect: handleWordStudySelect,
  };

  return (
    <div className="flex h-dvh-safe overflow-hidden bg-background">
      <Sidebar
        isLoggedIn={!!user}
        user={user}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { window.location.href = "/"; }}
        onSignInClick={() => setShowLogin(true)}
        onSignOut={signOut}
        savedWords={savedWords}
        selectedStrongs={selectedStrongs}
        onSelectSavedWord={handleSidebarSavedWordSelect}
      />

      <main className="md:ml-64 flex flex-1 flex-col min-w-0 min-h-0">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div className="flex-1" />

          <div className="hidden md:flex">
            <AuthButton
              user={user}
              onSignInClick={() => setShowLogin(true)}
              onSignOut={signOut}
            />
          </div>
        </div>

        {/* Desktop: two-column layout */}
        <div className="hidden md:flex flex-1 min-h-0">
          {/* Left Column: Search + Interlinear + Definition */}
          <div
            className="w-[380px] shrink-0 flex flex-col overflow-y-auto"
            style={{ borderRight: "0.5px solid #3c3c38" }}
          >
            <div className="px-4 pt-6 pb-16">
              <VerseSearch {...verseSearchProps} />

              {wordStudyMode && wordStudyDoc ? (
                <WordStudyPanel
                  doc={wordStudyDoc}
                  definition={wordStudyDefinition}
                  isSaved={wordStudyDoc ? savedStrongsSet.has(wordStudyDoc.strongs_number) : false}
                  onToggleSave={handleToggleSaveWordStudy}
                  isLoggedIn={!!user}
                />
              ) : (
                <>
                  <VerseDisplay
                    verse={verseData}
                    error={verseError}
                    onStepPrev={() => stepVerse("prev")}
                    onStepNext={() => stepVerse("next")}
                    hasPrev={!!prevVerseId}
                    hasNext={!!nextVerseId}
                    selectedStrongs={selectedStrongs}
                    onDeselect={() => setSelectedStrongs(null)}
                  />

                  <div className="mt-4" style={{ minHeight: 96 }}>
                    <InterlinearBlocks
                      tokens={tokens}
                      selectedStrongs={selectedStrongs}
                      onSelect={handleSelectWord}
                      loading={tokensLoading}
                      isNT={!!verseData?.verse_id && NT_BOOKS.has(verseData.verse_id.split(".")[0])}
                    />
                  </div>

                  <div className="mt-8">
                    <DefinitionPanel
                      definition={definition}
                      isSaved={selectedStrongs ? savedStrongsSet.has(selectedStrongs) : false}
                      onToggleSave={handleToggleSaveSelected}
                      isLoggedIn={!!user}
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Right Column: Corpus Quotes */}
          <div className="flex-1 overflow-y-auto">
            <div className="px-6 pt-6 pb-16">
              <CorpusPanel {...corpusPanelProps} />
            </div>
          </div>
        </div>

        {/* Mobile: single-column stacked layout */}
        <div className="flex flex-1 flex-col overflow-y-auto md:hidden">
          <div className="px-4 pt-6 pb-16">
            <VerseSearch {...verseSearchProps} />

            {wordStudyMode && wordStudyDoc ? (
              <>
                <WordStudyPanel
                  doc={wordStudyDoc}
                  definition={wordStudyDefinition}
                  isSaved={wordStudyDoc ? savedStrongsSet.has(wordStudyDoc.strongs_number) : false}
                  onToggleSave={handleToggleSaveWordStudy}
                  isLoggedIn={!!user}
                />
                <div className="mt-8">
                  <CorpusPanel {...corpusPanelProps} />
                </div>
              </>
            ) : (
              <>
                <VerseDisplay
                  verse={verseData}
                  error={verseError}
                  onStepPrev={() => stepVerse("prev")}
                  onStepNext={() => stepVerse("next")}
                  hasPrev={!!prevVerseId}
                  hasNext={!!nextVerseId}
                  selectedStrongs={selectedStrongs}
                  onDeselect={() => setSelectedStrongs(null)}
                />

                <div className="mt-4" style={{ minHeight: 96 }}>
                  <InterlinearBlocks
                    tokens={tokens}
                    selectedStrongs={selectedStrongs}
                    onSelect={handleSelectWord}
                    loading={tokensLoading}
                    isNT={!!verseData?.verse_id && NT_BOOKS.has(verseData.verse_id.split(".")[0])}
                  />
                </div>

                <div className="mt-8">
                  <DefinitionPanel
                    definition={definition}
                    isSaved={selectedStrongs ? savedStrongsSet.has(selectedStrongs) : false}
                    onToggleSave={handleToggleSaveSelected}
                    isLoggedIn={!!user}
                  />
                </div>
                {(definition || verseData) && (
                  <div className="mt-8">
                    <CorpusPanel {...corpusPanelProps} />
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {showLogin && (
        <LoginModal
          onClose={() => setShowLogin(false)}
          onSignIn={signIn}
          onSignUp={signUp}
        />
      )}
    </div>
  );
}
