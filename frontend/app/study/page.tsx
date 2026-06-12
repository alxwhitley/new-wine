"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Search, Menu, Bookmark, Flag, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  jewish_background: string;
  messianic_perspective: string;
  cultural_context: string;
  sources: string[];
}

type CorpusTab = "commentaries" | "word_study" | "jewish";

interface WordDefinition {
  strongs: string;
  word: string;
  transliteration: string;
  gloss: string;
  lexiconDefinition: string;
  meaning: string;
  corpusQuotes: CorpusQuote[];
}

// SBL book codes for Bible books with interlinear data
const NT_BOOKS = new Set([
  "MAT", "MRK", "LUK", "JHN", "ACT", "ROM", "1CO", "2CO",
  "GAL", "EPH", "PHP", "COL", "1TH", "2TH", "1TI", "2TI",
  "TIT", "PHM", "HEB", "JAS", "1PE", "2PE", "1JN", "2JN",
  "3JN", "JUD", "REV",
]);
const OT_BOOKS = new Set([
  "GEN", "EXO", "LEV", "NUM", "DEU", "JOS", "JDG", "RUT",
  "1SA", "2SA", "1KI", "2KI", "1CH", "2CH", "EZR", "NEH",
  "EST", "JOB", "PSA", "PRO", "ECC", "SNG", "ISA", "JER",
  "LAM", "EZK", "DAN", "HOS", "JOL", "AMO", "OBA", "JON",
  "MIC", "NAM", "HAB", "ZEP", "HAG", "ZEC", "MAL",
]);
const INTERLINEAR_BOOKS = new Set([...NT_BOOKS, ...OT_BOOKS]);

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
  if (loading) {
    return (
      <div className="rounded-md border border-border p-3">
        <div className="flex flex-wrap gap-3">
          {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
            <div key={i} className="flex flex-col items-center gap-1">
              <Skeleton className="h-5 w-10" />
              <Skeleton className="h-3 w-8" />
              <Skeleton className="h-2.5 w-10" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!isNT) {
    return (
      <div className="rounded-md border border-border p-3">
        <p className="text-sm text-muted-foreground">
          No interlinear data available for this verse
        </p>
      </div>
    );
  }

  if (tokens.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md border border-border">
      <div className="flex flex-wrap gap-2 p-3">
        {tokens.map((token, i) => {
          const isSelected = selectedStrongs === token.strongs;
          return (
            <button
              key={i}
              onClick={() => onSelect(isSelected ? null : token.strongs)}
              className={cn(
                "rounded-md p-1.5 text-center cursor-pointer transition-colors border",
                isSelected
                  ? "border-primary bg-primary/10"
                  : "border-transparent hover:bg-accent"
              )}
            >
              <span className="font-sans text-sm block leading-tight">{token.greek}</span>
              <span className="font-medium text-[11px] block leading-tight text-primary">
                {token.english}
              </span>
              <span className="text-[10px] block leading-tight text-muted-foreground font-mono">{token.strongs}</span>
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
        className="absolute top-6 right-0 h-8 w-8 rounded-full flex items-center justify-center transition-colors bg-card border border-border"
      >
        <Bookmark
          className={cn("h-4 w-4", isSaved ? "text-primary fill-primary" : "text-muted-foreground fill-none")}
        />
      </button>
      <p className="font-sans text-3xl text-foreground pr-10">{definition.word}</p>
      <p className="text-sm text-muted-foreground mt-1">
        {definition.transliteration} &middot; {definition.strongs} &middot; {definition.gloss}
      </p>
      {definition.lexiconDefinition && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">
            Definition
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.lexiconDefinition}</p>
        </>
      )}
      {definition.meaning && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">
            Usage
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="w-full max-w-md mx-4 rounded-lg border border-border bg-popover p-6">
        <h3 className="font-sans text-lg text-foreground">{heading}</h3>
        <p className="text-xs mt-1 mb-4 text-muted-foreground">
          {sourceName} &middot; {author}
        </p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Describe the theological concern..."
          rows={4}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary resize-none"
        />
        <div className="flex justify-end gap-3 mt-4">
          <button
            onClick={() => onSubmit("")}
            className="px-4 py-2 text-sm rounded-lg cursor-pointer text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip
          </button>
          <Button onClick={() => onSubmit(comment)} size="sm">
            Submit
          </Button>
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
  commentaryLoadingMore,
  commentaryHasMore,
  onLoadMoreCommentary,
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
  corpusTab,
  onTabChange,
  tokens,
  tokensLoading,
  onSelectWord,
  isNT,
  isSaved,
  onToggleSave,
  isLoggedIn,
  excerptContent,
  excerptLoading,
}: {
  definition: WordDefinition | null;
  selectedStrongs: string | null;
  corpusResults: CorpusResult[];
  corpusLoading: boolean;
  commentaryResults: CommentaryResult[];
  commentaryLoading: boolean;
  commentaryLoadingMore: boolean;
  commentaryHasMore: boolean;
  onLoadMoreCommentary: () => void;
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
  corpusTab: CorpusTab;
  onTabChange: (tab: CorpusTab) => void;
  tokens: WordToken[];
  tokensLoading: boolean;
  onSelectWord: (strongs: string | null) => void;
  isNT: boolean;
  isSaved: boolean;
  onToggleSave: () => void;
  isLoggedIn: boolean;
  excerptContent: string | null;
  excerptLoading: boolean;
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
  const [jpContent, setJpContent] = useState<JewishPerspectiveContent | null>(null);
  const [jpLoading, setJpLoading] = useState(false);
  const [jpError, setJpError] = useState(false);
  const [jpCacheChecked, setJpCacheChecked] = useState(false);
  const [jpCheckedRef, setJpCheckedRef] = useState<string | null>(null);
  // Reset JP state when verse changes
  useEffect(() => {
    setJpContent(null);
    setJpError(false);
    setJpCacheChecked(false);
    setJpCheckedRef(null);
  }, [verseRef]);

  const checkJpCache = useCallback(async () => {
    // If already loaded for this verse, skip
    if (jpContent && jpCheckedRef === verseRef) return;
    // If we already checked cache for this verse, don't re-check
    if (jpCacheChecked && jpCheckedRef === verseRef) return;

    setJpCacheChecked(false);
    setJpContent(null);

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
        setJpCacheChecked(true);
        return;
      }
    } catch {
      // fall through to empty state
    }

    // Not cached — mark checked so we show the generate button
    setJpCheckedRef(verseRef);
    setJpCacheChecked(true);
  }, [jpContent, jpCacheChecked, jpCheckedRef, verseRef]);

  const handleJpTabClick = useCallback(async () => {
    if (corpusTab === "jewish") return;
    onTabChange("jewish");
    await checkJpCache();
  }, [corpusTab, onTabChange, checkJpCache]);

  // Fix 2: Auto-check cache when verse changes while already on Jewish tab
  useEffect(() => {
    if (corpusTab === "jewish" && !jpContent && !jpLoading) {
      checkJpCache();
    }
  }, [corpusTab, verseRef, jpContent, jpLoading, checkJpCache]);

  const handleJpGenerate = useCallback(async () => {
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

  // Word study mode (from search dropdown): show full excerpt/article
  if (wordStudyMode && wordStudyDoc) {
    return (
      <>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              From the library
            </p>
            <p className="font-sans text-lg mt-1 mb-6 text-primary">
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
              className="h-7 w-7 rounded-full flex items-center justify-center cursor-pointer shrink-0 bg-background border border-border"
              title="Flag this content"
            >
              <Flag className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
        {wordStudyLoading ? (
          <SkeletonCards />
        ) : wordStudyContent ? (
          <TruncatedExcerpt content={wordStudyContent} />
        ) : (
          <div className="py-12 text-center">
            <p className="text-sm text-muted-foreground">
              No content available for this word study yet.
            </p>
          </div>
        )}
        {flagModalEl}
      </>
    );
  }

  // Reader view: show full commentary content
  if (hasVerse && activeCommentary) {
    return (
      <>
        <div className="flex items-center justify-between mb-4">
          <button
            onClick={onCommentaryBack}
            className="text-sm cursor-pointer hover:underline text-muted-foreground hover:text-foreground transition-colors"
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
              className="h-7 w-7 rounded-full flex items-center justify-center cursor-pointer bg-background border border-border"
              title="Flag this content"
            >
              <Flag className="h-3.5 w-3.5 text-muted-foreground" />
            </button>
          )}
        </div>
        <p className="text-xs mb-6 text-muted-foreground">
          {activeCommentary.title} &middot; {activeCommentary.author}
        </p>
        <div className="mx-auto max-w-[680px]">
          {activeCommentary.content
            .split(/\n\n+/)
            .flatMap((block) =>
              block.split(/(?<=\.)\s+(?=[A-Z])/)
            )
            .filter((p) => p.trim())
            .map((para, i) => (
              <p
                key={i}
                className="text-foreground mb-4 text-[15px] leading-[1.7]"
              >
                {para.trim()}
              </p>
            ))}
        </div>
        {flagModalEl}
      </>
    );
  }

  if (!hasVerse) {
    return (
      <>
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground text-sm">Search a verse to see commentary from the library</p>
        </div>
        {flagModalEl}
      </>
    );
  }

  const triggerClass = "flex-none h-auto rounded-none bg-transparent px-0 pb-2 mr-6 text-sm font-medium cursor-pointer transition-colors text-muted-foreground data-[state=active]:text-foreground data-[state=active]:bg-transparent data-[state=active]:shadow-none border-b-2 border-transparent data-[state=active]:border-primary -mb-px";

  return (
    <>
      <Tabs
        value={corpusTab}
        onValueChange={(val) => {
          if (val === "jewish") handleJpTabClick();
          else onTabChange(val as CorpusTab);
        }}
      >
        <TabsList className="w-full justify-start rounded-none bg-transparent p-0 border-b border-border mb-5 h-auto gap-0">
          <TabsTrigger value="commentaries" className={triggerClass}>Commentary</TabsTrigger>
          <TabsTrigger value="word_study" className={triggerClass}>Word Study</TabsTrigger>
          <TabsTrigger value="jewish" className={triggerClass}>Jewish Perspective</TabsTrigger>
        </TabsList>

        {/* Word Study tab */}
        <TabsContent value="word_study" className="mt-0">
          {(() => {
            const label = definition
              ? `${definition.word} (${definition.transliteration})`
              : selectedStrongs && corpusResults.length > 0
                ? corpusResults[0].title
                : null;
            return (
              <>
                <div className="mb-5">
                  <InterlinearBlocks
                    tokens={tokens}
                    selectedStrongs={selectedStrongs}
                    onSelect={onSelectWord}
                    loading={tokensLoading}
                    isNT={isNT}
                  />
                </div>
                {selectedStrongs && definition && (
                  <div className="mb-6">
                    <DefinitionPanel
                      definition={definition}
                      isSaved={isSaved}
                      onToggleSave={onToggleSave}
                      isLoggedIn={isLoggedIn}
                    />
                  </div>
                )}
                {selectedStrongs ? (
                  <>
                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      From the library
                    </p>
                    {label && (
                      <p className="font-sans text-lg mt-1 mb-6 text-primary">
                        {label}
                      </p>
                    )}
                    {corpusLoading ? (
                      <SkeletonCards />
                    ) : corpusResults.length === 0 ? (
                      <div className="py-12 text-center">
                        <p className="text-sm text-muted-foreground">
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
                  </>
                ) : (
                  <div className="py-8 text-center">
                    <p className="text-sm text-muted-foreground">
                      Select a word from the interlinear to see its definition and library results.
                    </p>
                  </div>
                )}
              </>
            );
          })()}
        </TabsContent>

        {/* Jewish Perspective tab */}
        <TabsContent value="jewish" className="mt-0">
          {jpLoading ? (
            <div className="py-12 flex flex-col items-center gap-3">
              <svg className="animate-spin h-6 w-6 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-sm text-muted-foreground">Generating...</p>
            </div>
          ) : jpError ? (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground">
                Unable to generate. Please try again.
              </p>
              <button
                onClick={() => { setJpError(false); }}
                className="text-sm mt-3 cursor-pointer hover:underline text-primary"
              >
                Try Again
              </button>
            </div>
          ) : jpContent ? (
            <div className="space-y-3">
              {([
                { key: "jewish_background", label: "Jewish Background" },
                { key: "messianic_perspective", label: "Messianic Perspective" },
                { key: "cultural_context", label: "Cultural Context" },
              ] as const).map((section) => (
                <div key={section.key} className="rounded-lg border border-border bg-card p-4">
                  <p className="text-[11px] font-medium uppercase tracking-wider mb-2 text-muted-foreground">
                    {section.label}
                  </p>
                  <div className="text-sm text-foreground leading-[1.7]">
                    {(jpContent[section.key] || "").split(/\n\n+/).map((para, pi, arr) => (
                      <p key={pi} className={pi < arr.length - 1 ? "mb-2.5" : ""}>
                        {para.split(/\n/).map((line, li, lineArr) => (
                          <span key={li}>
                            {line}
                            {li < lineArr.length - 1 && <br />}
                          </span>
                        ))}
                      </p>
                    ))}
                  </div>
                </div>
              ))}
              {jpContent.sources && jpContent.sources.length > 0 && (
                <div className="rounded-lg border border-border bg-card p-4">
                  <p className="text-[11px] font-medium uppercase tracking-wider mb-2 text-muted-foreground">
                    Sources
                  </p>
                  <ul className="text-sm text-foreground leading-[1.7]">
                    {jpContent.sources.map((src, i) => (
                      <li key={i} className="mb-1">{src}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : !jpCacheChecked ? (
            <div className="py-12 flex flex-col items-center gap-3">
              <svg className="animate-spin h-5 w-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <p className="text-sm text-muted-foreground">Checking cache...</p>
            </div>
          ) : (
            <div className="py-12 flex flex-col items-center gap-4">
              <p className="text-sm text-muted-foreground">
                No Jewish perspective generated for this verse yet.
              </p>
              <Button onClick={handleJpGenerate}>
                Generate Jewish Perspective
              </Button>
            </div>
          )}
        </TabsContent>

        {/* Commentaries tab (default) */}
        <TabsContent value="commentaries" className="mt-0">
          {commentaryLoading ? (
            <SkeletonCards />
          ) : commentaryResults.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-muted-foreground">
                No commentary found for this verse.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {commentaryResults.map((r, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-border bg-card p-4 cursor-pointer hover:bg-accent transition-colors relative group"
                  onClick={() => onCommentaryClick(r)}
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
                      className="absolute top-3 right-3 h-7 w-7 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer bg-background border border-border"
                      title="Flag this content"
                    >
                      <Flag className="h-3.5 w-3.5 text-muted-foreground" />
                    </button>
                  )}
                  {r.source_kind === "sermon_transcript" && (
                    <span className="text-xs rounded border border-border px-2 py-0.5 inline-block mb-1 text-muted-foreground">Sermon</span>
                  )}
                  <p className="text-sm font-medium text-primary">{r.author}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 mb-3">{r.title}</p>
                  <p className="text-sm text-foreground leading-relaxed">{r.excerpt}</p>
                </div>
              ))}
              {commentaryHasMore ? (
                <div className="flex justify-center pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onLoadMoreCommentary}
                    disabled={commentaryLoadingMore}
                  >
                    {commentaryLoadingMore ? "Loading..." : "Load more"}
                  </Button>
                </div>
              ) : commentaryResults.length > 3 ? (
                <p className="text-center text-sm pt-2 text-muted-foreground">
                  That&apos;s all the results
                </p>
              ) : null}
            </div>
          )}
        </TabsContent>
      </Tabs>
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
          className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
        />
        <button
          onClick={onSubmit}
          disabled={loading}
          className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground flex items-center justify-center text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <span className="h-4 w-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          ) : (
            <Search className="h-4 w-4" />
          )}
        </button>
      </div>
      {showBookDropdown && (
        <div className="absolute top-full left-0 right-12 mt-1 rounded-lg border border-border bg-popover shadow-lg z-50 overflow-hidden">
          {bookMatches.map((name) => (
            <button
              key={name}
              onClick={() => {
                onChange(name + " ");
                inputRef.current?.focus();
              }}
              className="w-full text-left px-4 py-3 text-sm cursor-pointer text-foreground hover:bg-accent transition-colors border-b border-border last:border-b-0"
            >
              {name}
            </button>
          ))}
        </div>
      )}
      {showWordDropdown && (
        <div className="absolute top-full left-0 right-12 mt-1 rounded-lg border border-border bg-popover shadow-lg z-50 overflow-hidden">
          {wordSearchResults.map((r) => (
            <button
              key={r.id}
              onClick={() => onWordStudySelect(r)}
              className="w-full text-left px-4 py-3 text-sm transition-colors cursor-pointer hover:bg-accent border-b border-border last:border-b-0"
            >
              <span className="text-foreground font-medium">{r.word || r.transliteration}</span>
              <span className="text-muted-foreground">
                {r.word && r.transliteration && r.word !== r.transliteration ? ` (${r.transliteration})` : ""}
              </span>
              {r.strongs_number && (
                <span className="text-primary"> &middot; {r.strongs_number}</span>
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
    return <p className="text-sm mt-4 text-destructive">{error}</p>;
  }
  if (!verse) return null;
  return (
    <div
      className="mt-4 rounded-lg border border-border bg-card"
      style={{ cursor: selectedStrongs ? "pointer" : "default" }}
      onClick={() => { if (selectedStrongs) onDeselect(); }}
    >
      <div className="flex items-center justify-center gap-3 py-2 px-4 border-b border-border">
        <button
          onClick={(e) => { e.stopPropagation(); onStepPrev(); }}
          disabled={!hasPrev}
          className="text-sm font-medium text-muted-foreground disabled:opacity-50"
        >
          &larr;
        </button>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {verse.book} {verse.chapter}:{verse.verse} ({verse.translation})
        </p>
        <button
          onClick={(e) => { e.stopPropagation(); onStepNext(); }}
          disabled={!hasNext}
          className="text-sm font-medium text-muted-foreground disabled:opacity-50"
        >
          &rarr;
        </button>
      </div>
      <div className="p-4">
        <p className="text-sm text-foreground leading-relaxed">{verse.text}</p>
      </div>
    </div>
  );
}

function TruncatedExcerpt({ content, wordLimit = 300 }: { content: string; wordLimit?: number }) {
  const [expanded, setExpanded] = useState(false);

  // Reset to collapsed when content changes (new word selected)
  useEffect(() => {
    setExpanded(false);
  }, [content]);

  const words = content.split(/\s+/);
  const needsTruncation = words.length > wordLimit;
  const displayContent = !expanded && needsTruncation
    ? words.slice(0, wordLimit).join(" ") + "..."
    : content;

  return (
    <>
      <div className="prose prose-invert prose-sm max-w-none">
        <ReactMarkdown>{displayContent}</ReactMarkdown>
      </div>
      {needsTruncation && (
        <div className="border-t border-border">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 w-full py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {expanded ? "Show Less" : "Read More"}
          </button>
        </div>
      )}
    </>
  );
}

interface ScriptureVerse {
  reference: string;
  text: string;
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
  const [versesOpen, setVersesOpen] = useState(false);
  const [verses, setVerses] = useState<ScriptureVerse[] | null>(null);
  const [versesLoading, setVersesLoading] = useState(false);
  const fetchedRef = useRef<string | null>(null);

  const handleToggleVerses = () => {
    const opening = !versesOpen;
    setVersesOpen(opening);
    if (opening && fetchedRef.current !== doc.strongs_number) {
      setVersesLoading(true);
      setVerses(null);
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/verses?strongs=${encodeURIComponent(doc.strongs_number)}`)
        .then((res) => (res.ok ? res.json() : { verses: [] }))
        .then((data) => {
          setVerses(data.verses ?? []);
          fetchedRef.current = doc.strongs_number;
        })
        .catch(() => setVerses([]))
        .finally(() => setVersesLoading(false));
    }
  };

  return (
    <div className="mt-8 relative">
      <button
        onClick={onToggleSave}
        title={isLoggedIn ? (isSaved ? "Remove from saved" : "Save word") : "Sign in to save words"}
        className="absolute top-0 right-0 h-8 w-8 rounded-full flex items-center justify-center transition-colors bg-card border border-border"
      >
        <Bookmark
          className={cn("h-4 w-4", isSaved ? "text-primary fill-primary" : "text-muted-foreground fill-none")}
        />
      </button>
      <p className="font-sans text-3xl text-foreground pr-10">
        {definition?.word || doc.word || doc.transliteration}
      </p>
      <p className="text-sm text-muted-foreground mt-1">
        {doc.transliteration} &middot; {doc.strongs_number}
      </p>

      {definition && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">
            Definition
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.gloss}</p>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">
            Usage
          </p>
          <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}

      {/* Scripture References reveal */}
      <div className="mt-6 border-t border-border">
        <button
          onClick={handleToggleVerses}
          className="flex items-center gap-1.5 w-full py-2 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
        >
          {versesOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          Scripture References
        </button>
        {versesOpen && (
          <div className="pb-2">
            {versesLoading && (
              <p className="text-xs text-muted-foreground py-2">Loading...</p>
            )}
            {!versesLoading && verses && verses.length === 0 && (
              <p className="text-xs text-muted-foreground py-2">No scripture references found for this word.</p>
            )}
            {!versesLoading && verses && verses.length > 0 && (
              <div className="space-y-3">
                {verses.map((v) => (
                  <div key={v.reference}>
                    <p className="text-xs font-medium uppercase tracking-wide text-primary">
                      {v.reference}
                    </p>
                    <p className="text-sm text-foreground leading-relaxed mt-0.5">{v.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
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

  // Tab state (lifted up so left panel can react)
  const [corpusTab, setCorpusTab] = useState<CorpusTab>("commentaries");

  // Chapter view state
  const [chapterOpen, setChapterOpen] = useState(false);
  const [chapterVerses, setChapterVerses] = useState<VerseData[]>([]);
  const [chapterLoading, setChapterLoading] = useState(false);

  // Excerpt state (Precept Austin word study excerpt for selected word)
  const [excerptContent, setExcerptContent] = useState<string | null>(null);
  const [excerptLoading, setExcerptLoading] = useState(false);

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
    setChapterOpen(false);
    setCorpusTab("commentaries");

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

  // Fetch interlinear tokens only when Word Study tab is active
  useEffect(() => {
    if (corpusTab !== "word_study") return;

    setSelectedStrongs(null);
    setTokens([]);

    const verseId = verseData?.verse_id;
    if (!verseId) return;

    const book = verseId.split(".")[0];
    if (!INTERLINEAR_BOOKS.has(book)) return;

    setTokensLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/interlinear?verse_id=${encodeURIComponent(verseId)}`)
      .then((res) => {
        if (!res.ok) throw new Error("interlinear fetch failed");
        return res.json();
      })
      .then((data: Array<{ original_word: string; transliteration: string; strongs_number: string; english_gloss: string; morphology: string; word_position: number }>) => {
        const mapped = data.map((w) => ({
          greek: w.original_word,
          transliteration: w.transliteration || "",
          english: w.english_gloss || "",
          strongs: w.strongs_number || "",
          morph: w.morphology || "",
        }));
        setTokens(mapped);
        // Auto-select first word
        if (mapped.length > 0 && mapped[0].strongs) {
          setSelectedStrongs(mapped[0].strongs);
        }
      })
      .catch(() => {
        setTokens([]);
      })
      .finally(() => {
        setTokensLoading(false);
      });
  }, [verseData?.verse_id, corpusTab]);

  // Clear interlinear when leaving Word Study tab
  useEffect(() => {
    if (corpusTab !== "word_study") {
      setTokens([]);
      setSelectedStrongs(null);
      setExcerptContent(null);
    }
  }, [corpusTab]);

  // Fetch chapter verses when chapter view is opened
  useEffect(() => {
    if (!chapterOpen || !verseData) {
      setChapterVerses([]);
      return;
    }

    const { verse_id } = verseData;
    const parts = verse_id.split(".");
    const book = parts[0];
    const chapter = parseInt(parts[1], 10);

    setChapterLoading(true);
    const prefix = `${book}.${chapter}.`;
    supabase
      .from("verses")
      .select("*")
      .like("verse_id", `${prefix}%`)
      .order("verse_id")
      .then(({ data }) => {
        if (data) {
          setChapterVerses(
            data.map((v: { verse_id: string; text: string; translation?: string }) => {
              const vParts = v.verse_id.split(".");
              return {
                verse_id: v.verse_id,
                book: ABBREV_TO_NAME[book] ?? book,
                chapter: parseInt(vParts[1], 10),
                verse: parseInt(vParts[2], 10),
                text: v.text ?? "",
                translation: v.translation ?? "WEB",
              };
            })
          );
        }
        setChapterLoading(false);
      });
  }, [chapterOpen, verseData]);

  // Fetch Precept Austin excerpt when selected word changes
  useEffect(() => {
    if (!selectedStrongs || corpusTab !== "word_study") {
      setExcerptContent(null);
      return;
    }

    setExcerptLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/excerpt?strongs=${encodeURIComponent(selectedStrongs)}`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        setExcerptContent(data?.content ?? null);
      })
      .catch(() => setExcerptContent(null))
      .finally(() => setExcerptLoading(false));
  }, [selectedStrongs, corpusTab]);

  // Debounced word search (suppressed when book autocomplete is active)
  useEffect(() => {
    const trimmed = verseRef.trim();
    const isPlainWord = trimmed.length >= 2 && !/\d/.test(trimmed);
    const hasBookMatch = matchBooks(verseRef).length > 0;

    if (!isPlainWord || hasBookMatch || wordStudyMode) {
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

  // Lexicon fetch for word study mode (triggered by word search selection)
  const [wordStudyLexicon, setWordStudyLexicon] = useState<string | null>(null);

  useEffect(() => {
    if (!wordStudyDoc) {
      setWordStudyLexicon(null);
      return;
    }
    const params = new URLSearchParams({ strongs: wordStudyDoc.strongs_number });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/lexicon?${params}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setWordStudyLexicon(data?.content ?? null))
      .catch(() => setWordStudyLexicon(null));
  }, [wordStudyDoc]);

  const wordStudyDefinition: WordDefinition | null = wordStudyDoc
    ? (() => {
        let gloss = "";
        let meaning = "";
        if (wordStudyLexicon) {
          const colonIdx = wordStudyLexicon.indexOf(":");
          const afterColon =
            colonIdx >= 0 ? wordStudyLexicon.slice(colonIdx + 1).trim() : wordStudyLexicon;
          const dotIdx = afterColon.indexOf(".");
          if (dotIdx >= 0) {
            gloss = afterColon.slice(0, dotIdx).trim();
            const rest = afterColon.slice(dotIdx + 1).trim();
            meaning = rest.length > 200 ? rest.slice(0, 200).trimEnd() + "\u2026" : rest;
          } else {
            gloss = afterColon;
          }
        }
        return {
          strongs: wordStudyDoc.strongs_number,
          word: wordStudyDoc.word || wordStudyDoc.transliteration,
          transliteration: wordStudyDoc.transliteration,
          gloss,
          lexiconDefinition: "",
          meaning,
          corpusQuotes: [],
        };
      })()
    : null;

  // Commentary results (State 1: verse loaded, no word selected)
  const [commentaryResults, setCommentaryResults] = useState<CommentaryResult[]>([]);
  const [commentaryLoading, setCommentaryLoading] = useState(false);
  const [commentaryLoadingMore, setCommentaryLoadingMore] = useState(false);
  const [commentaryOffset, setCommentaryOffset] = useState(0);
  const [commentaryHasMore, setCommentaryHasMore] = useState(false);
  const [activeCommentary, setActiveCommentary] = useState<CommentaryResult | null>(null);

  const fetchCommentary = useCallback((verseText: string, offset: number, verseId?: string) => {
    const isLoadMore = offset > 0;
    if (isLoadMore) {
      setCommentaryLoadingMore(true);
    } else {
      setCommentaryLoading(true);
    }
    const params = new URLSearchParams({ verse_text: verseText, offset: String(offset) });
    if (verseId) params.set("verse_id", verseId);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/commentary?${params}`)
      .then((res) => {
        if (!res.ok) throw new Error("commentary fetch failed");
        return res.json();
      })
      .then((data) => {
        const newResults = data.results ?? [];
        if (isLoadMore) {
          setCommentaryResults((prev) => [...prev, ...newResults]);
        } else {
          setCommentaryResults(newResults);
        }
        setCommentaryHasMore(data.has_more ?? false);
        setCommentaryOffset(offset);
      })
      .catch(() => {
        if (!isLoadMore) setCommentaryResults([]);
        setCommentaryHasMore(false);
      })
      .finally(() => {
        if (isLoadMore) {
          setCommentaryLoadingMore(false);
        } else {
          setCommentaryLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    if (!verseData?.text) {
      setCommentaryResults([]);
      setActiveCommentary(null);
      setCommentaryOffset(0);
      setCommentaryHasMore(false);
      return;
    }
    fetchCommentary(verseData.text, 0, verseData.verse_id);
  }, [verseData?.text, verseData?.verse_id, fetchCommentary]);

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

  // Lexicon definition fetch (TBESG)
  const [lexiconContent, setLexiconContent] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedStrongs) {
      setLexiconContent(null);
      return;
    }
    const params = new URLSearchParams({ strongs: selectedStrongs });
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/lexicon?${params}`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        setLexiconContent(data?.content ?? null);
      })
      .catch(() => setLexiconContent(null));
  }, [selectedStrongs]);

  // Build definition from interlinear token data + lexicon + corpus results
  const selectedToken = selectedStrongs
    ? tokens.find((t) => t.strongs === selectedStrongs) ?? null
    : null;

  // Parse lexicon content into definition + usage
  // New TBESG brief format: "Strong's G3056 (logos / λόγος): word. a word, a saying, declaration, ..."
  // After colon: "word. sub-meanings..." — gloss before dot, sub-meanings after
  let lexDef = "";
  let lexUsage = "";
  if (lexiconContent) {
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
  }

  const definition: WordDefinition | null = selectedToken
    ? {
        strongs: selectedToken.strongs,
        word: selectedToken.greek,
        transliteration: selectedToken.transliteration,
        gloss: selectedToken.english,
        lexiconDefinition: lexDef,
        meaning: lexUsage,
        corpusQuotes: [],
      }
    : null;

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

  // Handle tab change — also navigate chapter view verse to active verse
  const handleTabChange = useCallback((tab: CorpusTab) => {
    setCorpusTab(tab);
    setActiveCommentary(null);
  }, []);

  // Handle chapter verse click
  const handleChapterVerseClick = useCallback((v: VerseData) => {
    const bookName = v.book;
    setVerseRef(`${bookName} ${v.chapter}:${v.verse}`);
    fetchVerseById(v.verse_id);
  }, [fetchVerseById]);

  const corpusPanelProps = {
    definition,
    selectedStrongs,
    corpusResults,
    corpusLoading,
    commentaryResults,
    commentaryLoading,
    commentaryLoadingMore,
    commentaryHasMore,
    onLoadMoreCommentary: () => {
      if (verseData?.text) fetchCommentary(verseData.text, commentaryOffset + 3, verseData.verse_id);
    },
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
    corpusTab,
    onTabChange: handleTabChange,
    tokens,
    tokensLoading,
    onSelectWord: handleSelectWord,
    isNT: !!verseData?.verse_id && INTERLINEAR_BOOKS.has(verseData.verse_id.split(".")[0]),
    isSaved: selectedStrongs ? savedStrongsSet.has(selectedStrongs) : false,
    onToggleSave: handleToggleSaveSelected,
    isLoggedIn: !!user,
    excerptContent,
    excerptLoading,
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
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
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

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
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
          {/* Left Column: Search + Verse + View Chapter */}
          <div className="w-[380px] shrink-0 flex flex-col overflow-y-auto border-r border-border">
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
                    onDeselect={() => { setSelectedStrongs(null); setActiveCommentary(null); }}
                  />

                  {/* View Chapter button + chapter view */}
                  {verseData && (
                    <div className="mt-4">
                      <button
                        onClick={() => setChapterOpen((prev) => !prev)}
                        className="text-xs font-medium cursor-pointer transition-colors text-muted-foreground hover:text-foreground"
                      >
                        {chapterOpen ? "Hide Chapter" : "View Chapter"}
                      </button>

                      {chapterOpen && (
                        <div className="mt-3 rounded-lg border border-border bg-card p-4">
                          {chapterLoading ? (
                            <div className="space-y-2">
                              {[0, 1, 2, 3, 4].map((i) => (
                                <Skeleton key={i} className="h-4 w-full" />
                              ))}
                            </div>
                          ) : (
                            <p className="text-sm text-foreground leading-relaxed">
                              {chapterVerses.map((v) => {
                                const isActive = v.verse_id === verseData.verse_id;
                                return (
                                  <span
                                    key={v.verse_id}
                                    onClick={() => handleChapterVerseClick(v)}
                                    className={cn(
                                      "cursor-pointer rounded-sm transition-colors px-0.5 -mx-0.5",
                                      isActive ? "bg-accent" : "hover:bg-accent"
                                    )}
                                  >
                                    <sup className="text-[9px] text-muted-foreground mr-0.5">{v.verse}</sup>
                                    {v.text}{" "}
                                  </span>
                                );
                              })}
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Right Column: Tabs + Content */}
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

                {verseData && (
                  <div className="mt-8">
                    <CorpusPanel {...corpusPanelProps} />
                  </div>
                )}
              </>
            )}
          </div>
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
