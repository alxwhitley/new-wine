"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Search, Menu, Bookmark, Flag, ChevronDown, ChevronUp, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/hooks/useAuth";
import { Sidebar } from "@/components/rhemata/sidebar";
import type { SavedWord } from "@/components/rhemata/sidebar";
import LoginModal from "@/components/auth/LoginModal";
import BetaGate from "@/components/auth/BetaGate";
import { supabase } from "@/lib/supabase";
import { getAdjacentVerseId } from "@/lib/verse-counts";
import { useUserRole } from "@/hooks/useUserRole";
import { PastorsNotesSection } from "@/components/rhemata/pastors-notes";
import { InterlinearBlocks, type WordToken } from "@/components/rhemata/interlinear-blocks";
import { useInterlinear } from "@/hooks/useInterlinear";
import type { WordDefinition } from "@/components/rhemata/word-definition-card";
import { useLexiconDefinition } from "@/hooks/useLexiconDefinition";
import { useCommentarySearch, type CommentaryResult } from "@/hooks/useCommentarySearch";
import { formatCommentaryContent } from "@/lib/format-commentary-content";

// ── Types ────────────────────────────────────────────────────────────────────

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

interface CorpusResult {
  content: string;
  title: string;
  author: string;
  source_kind: string;
  url: string | null;
  is_excerpt?: boolean;
}

// ── Book maps ────────────────────────────────────────────────────────────────

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

// ── Reusable helpers ─────────────────────────────────────────────────────────

function SkeletonCards() {
  return (
    <div className="space-y-4">
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
  heading, sourceName, author, onSubmit, onClose,
}: {
  heading: string; sourceName: string; author: string;
  onSubmit: (comment: string) => void; onClose: () => void;
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
        <p className="text-xs mt-1 mb-4 text-muted-foreground">{sourceName} &middot; {author}</p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Describe the theological concern..."
          rows={4}
          className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary resize-none"
        />
        <div className="flex justify-end gap-3 mt-4">
          <button onClick={() => onSubmit("")} className="px-4 py-2 text-sm rounded-lg cursor-pointer text-muted-foreground hover:text-foreground transition-colors">Skip</button>
          <Button onClick={() => onSubmit(comment)} size="sm">Submit</Button>
        </div>
      </div>
    </div>
  );
}

const EXCERPT_COMPONENTS: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  h1: ({ children }) => <p className="text-sm font-semibold text-foreground tracking-tight mt-4 mb-1">{children}</p>,
  h2: ({ children }) => <p className="text-sm font-semibold text-foreground tracking-tight mt-4 mb-1">{children}</p>,
  h3: ({ children }) => <p className="text-sm font-semibold text-foreground tracking-tight mt-4 mb-1">{children}</p>,
  h4: ({ children }) => <p className="text-sm font-medium text-foreground mt-3 mb-1">{children}</p>,
  p: ({ children }) => <p className="text-sm text-foreground leading-relaxed mb-3">{children}</p>,
  strong: ({ children }) => <strong className="font-medium text-foreground">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="text-sm text-foreground leading-relaxed mb-3 ml-4 list-disc space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="text-sm text-foreground leading-relaxed mb-3 ml-4 list-decimal space-y-1">{children}</ol>,
  li: ({ children }) => <li className="text-sm text-foreground">{children}</li>,
  blockquote: ({ children }) => <blockquote className="border-l-2 border-border pl-3 text-sm text-muted-foreground italic mb-3">{children}</blockquote>,
};

function extractTeaser(content: string): string {
  const plain = content
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("#"))
    .join(" ")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/_(.+?)_/g, "$1")
    .replace(/`(.+?)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
  const sentences = plain.match(/[^.!?]+[.!?]+/g) ?? [];
  return sentences.slice(0, 2).join(" ").trim();
}

interface ScriptureVerse { reference: string; text: string; }

function WordStudyPanel({
  doc, definition, isSaved, onToggleSave, isLoggedIn,
}: {
  doc: WordSearchResult; definition: WordDefinition | null;
  isSaved: boolean; onToggleSave: () => void; isLoggedIn: boolean;
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
        .then((data) => { setVerses(data.verses ?? []); fetchedRef.current = doc.strongs_number; })
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
        <Bookmark className={cn("h-4 w-4", isSaved ? "text-primary fill-primary" : "text-muted-foreground fill-none")} />
      </button>
      <p className="font-sans text-3xl text-foreground pr-10">{definition?.word || doc.word || doc.transliteration}</p>
      <p className="text-sm text-muted-foreground mt-1">{doc.transliteration} &middot; {doc.strongs_number}</p>
      {definition && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">Definition</p>
          <p className="text-sm text-foreground leading-relaxed">{definition.gloss}</p>
          <p className="text-xs font-medium uppercase tracking-wide mt-6 mb-2 text-muted-foreground">Usage</p>
          <p className="text-sm text-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}
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
            {versesLoading && <p className="text-xs text-muted-foreground py-2">Loading...</p>}
            {!versesLoading && verses && verses.length === 0 && (
              <p className="text-xs text-muted-foreground py-2">No scripture references found for this word.</p>
            )}
            {!versesLoading && verses && verses.length > 0 && (
              <div className="space-y-3">
                {verses.map((v) => (
                  <div key={v.reference}>
                    <p className="text-xs font-medium uppercase tracking-wide text-primary">{v.reference}</p>
                    <p className="text-sm text-foreground leading-relaxed mt-0.5">{v.text}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground mt-6">
        Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)
      </p>
    </div>
  );
}

// ── VerseSearch ───────────────────────────────────────────────────────────────

function VerseSearch({
  verseRef, onChange, onSubmit, loading,
  wordSearchResults, wordSearchOpen, onWordStudySelect,
}: {
  verseRef: string; onChange: (v: string) => void; onSubmit: () => void; loading: boolean;
  wordSearchResults: WordSearchResult[]; wordSearchOpen: boolean;
  onWordStudySelect: (result: WordSearchResult) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const bookMatches = matchBooks(verseRef);
  const showBookDropdown = bookMatches.length > 0 && !/\d/.test(verseRef.trim());
  const showWordDropdown = !showBookDropdown && wordSearchOpen && wordSearchResults.length > 0;

  return (
    <div className="relative flex-1" ref={containerRef}>
      <div className="flex gap-2">
        <input
          ref={inputRef}
          type="text"
          value={verseRef}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") onSubmit(); }}
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
              onClick={() => { onChange(name + " "); inputRef.current?.focus(); }}
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
              {r.strongs_number && <span className="text-primary"> &middot; {r.strongs_number}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AnchorNav ─────────────────────────────────────────────────────────────────

const ANCHORS = [
  { id: "section-words", label: "Words" },
  { id: "section-commentary", label: "Commentary" },
  { id: "section-pastors", label: "Pastors' Notes" },
] as const;

function AnchorNav({
  activeSection, scrollContainer,
}: {
  activeSection: string;
  scrollContainer: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <nav className="sticky top-0 z-20 bg-background flex gap-6 overflow-x-auto pt-4 pb-3">
      {ANCHORS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => {
            const el = document.getElementById(id);
            const container = scrollContainer.current;
            if (el && container) {
              const top = el.offsetTop - 48;
              container.scrollTo({ top, behavior: "smooth" });
            }
          }}
          className={cn(
            "text-sm whitespace-nowrap shrink-0 transition-colors",
            activeSection === id
              ? "font-medium text-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}

// ── InlineWordPanel ───────────────────────────────────────────────────────────

function InlineWordPanel({
  definition, excerptContent, excerptLoading,
  corpusResults, corpusLoading, isSaved, onToggleSave, onClose, isLoggedIn,
}: {
  definition: WordDefinition | null;
  excerptContent: string | null; excerptLoading: boolean;
  corpusResults: CorpusResult[]; corpusLoading: boolean;
  isSaved: boolean; onToggleSave: () => void;
  onClose: () => void; isLoggedIn: boolean;
}) {
  const [wordStudyOpen, setWordStudyOpen] = useState(false);
  const isMobile = useIsMobile();
  return (
    <div className="mt-4 rounded-md border border-border bg-card p-4 relative">
      {/* Header row */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0 pr-8">
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
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onToggleSave}
            title={isLoggedIn ? (isSaved ? "Remove from saved" : "Save word") : "Sign in to save words"}
            className="h-8 w-8 rounded-full flex items-center justify-center transition-colors hover:bg-accent border border-border"
          >
            <Bookmark className={cn("h-4 w-4", isSaved ? "text-primary fill-primary" : "text-muted-foreground fill-none")} />
          </button>
          <button
            onClick={onClose}
            className="h-8 w-8 rounded-full flex items-center justify-center transition-colors hover:bg-accent border border-border"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      </div>

      {definition?.lexiconDefinition && (
        <>
          <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground mb-1.5">Definition</p>
          <p className="text-base font-medium text-foreground leading-relaxed">{definition.lexiconDefinition}</p>
        </>
      )}
      {definition?.meaning && (
        <>
          <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground pt-5 mb-1.5">Usage</p>
          <p className="text-sm text-muted-foreground leading-relaxed">{definition.meaning}</p>
        </>
      )}

      {/* Precept Austin excerpt */}
      {excerptLoading ? (
        <>
          <Separator className="my-4" />
          <Skeleton className="h-3 w-1/3 mb-3" />
          <Skeleton className="h-3 w-full mb-2" />
          <Skeleton className="h-3 w-5/6" />
        </>
      ) : excerptContent ? (
        <>
          <Separator className="my-4" />
          <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground mb-3">Word Study</p>
          <p className="text-sm text-foreground leading-relaxed mb-2">{extractTeaser(excerptContent)}</p>
          <button
            onClick={() => setWordStudyOpen(true)}
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            Full word study →
          </button>
          <Sheet open={wordStudyOpen} onOpenChange={setWordStudyOpen}>
            <SheetContent
              side={isMobile ? "bottom" : "right"}
              className={isMobile
                ? "h-[85vh] overflow-y-auto rounded-t-xl p-0 bg-popover"
                : "w-[480px] sm:max-w-[480px] p-0 bg-popover"}
              showCloseButton={true}
            >
              <div className="flex flex-col h-full">
                <div className="border-b border-border px-6 py-4 pr-12 shrink-0">
                  <SheetTitle className="font-sans text-2xl font-normal text-foreground">
                    {definition?.word}
                  </SheetTitle>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    {definition?.transliteration}
                    {definition?.transliteration && " · "}
                    <span className="font-mono">{definition?.strongs}</span>
                  </p>
                </div>
                <div className="overflow-y-auto flex-1 px-6 py-6">
                  <div className="prose prose-invert">
                    <ReactMarkdown>{excerptContent}</ReactMarkdown>
                  </div>
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </>
      ) : null}

      {/* From the Library */}
      <Separator className="my-4" />
      <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground mb-3">From the Library</p>
      {corpusLoading ? (
        <SkeletonCards />
      ) : corpusResults.length === 0 ? (
        <p className="text-sm text-muted-foreground">No library entries for this word yet.</p>
      ) : corpusResults.some((r) => r.is_excerpt) ? (
        <div className="text-sm text-foreground">
          <ReactMarkdown components={EXCERPT_COMPONENTS}>
            {corpusResults.filter((r) => r.is_excerpt).map((r) => r.content).join("\n\n")}
          </ReactMarkdown>
        </div>
      ) : (
        <div className="space-y-3">
          {corpusResults.map((r, i) => (
            <div key={i} className="rounded-lg border border-border bg-background p-3">
              <p className="text-sm text-foreground leading-relaxed">&ldquo;{r.content}&rdquo;</p>
              <div className="mt-2">
                <p className="text-xs font-medium text-foreground">{r.author}</p>
                <p className="text-xs text-muted-foreground">{r.title}</p>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-6">
        Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)
      </p>
    </div>
  );
}

// ── CommentarySection ─────────────────────────────────────────────────────────

function CommentarySection({
  commentaryResults, commentaryLoading, commentaryLoadingMore,
  commentaryHasMore, onLoadMoreCommentary, verseRef, accessToken,
}: {
  commentaryResults: CommentaryResult[]; commentaryLoading: boolean;
  commentaryLoadingMore: boolean; commentaryHasMore: boolean;
  onLoadMoreCommentary: () => void; verseRef: string; accessToken: string | null;
}) {
  const [activeCommentary, setActiveCommentary] = useState<CommentaryResult | null>(null);
  const [flaggedIds, setFlaggedIds] = useState<Set<string>>(new Set());
  const [flagModal, setFlagModal] = useState<{
    documentId: string; heading: string; sourceName: string; author: string;
  } | null>(null);

  const submitFlag = useCallback(async (comment: string) => {
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
          source_type: "commentary",
          source_document_id: flagModal.documentId,
        }),
      });
    } catch { /* silently fail */ }
    setFlaggedIds((prev) => new Set(prev).add(flagModal.documentId));
    setFlagModal(null);
  }, [flagModal, verseRef, accessToken]);

  // Strip [Source | Ref] prefix from excerpt snippets
  function stripPrefix(excerpt: string) {
    return excerpt.replace(/^\[.*?\]\s*/, "");
  }

  return (
    <section id="section-commentary" className="pt-10">
      <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-4">Commentary</h2>

      {activeCommentary ? (
        <div>
          <div className="flex items-center justify-between mb-4">
            <button
              onClick={() => setActiveCommentary(null)}
              className="text-sm cursor-pointer hover:underline text-muted-foreground hover:text-foreground transition-colors"
            >
              &larr; Back
            </button>
            {!flaggedIds.has(activeCommentary.document_id) && (
              <button
                onClick={() => setFlagModal({
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
          <div className="max-w-2xl font-serif">
            {formatCommentaryContent(activeCommentary.content)}
          </div>
        </div>
      ) : commentaryLoading ? (
        <SkeletonCards />
      ) : commentaryResults.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-sm text-muted-foreground">No commentary found for this verse.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {commentaryResults.map((r, i) => (
            <div
              key={i}
              className="rounded-lg border border-border bg-card p-4 cursor-pointer hover:bg-accent transition-colors relative group"
              onClick={() => setActiveCommentary(r)}
            >
              {!flaggedIds.has(r.document_id) && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setFlagModal({ documentId: r.document_id, heading: "Flag Commentary", sourceName: r.title, author: r.author });
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
              <p className="text-sm text-foreground leading-relaxed">{stripPrefix(r.excerpt)}</p>
            </div>
          ))}
          {commentaryHasMore ? (
            <div className="flex justify-center pt-2">
              <Button variant="outline" size="sm" onClick={onLoadMoreCommentary} disabled={commentaryLoadingMore}>
                {commentaryLoadingMore ? "Loading..." : "Load more"}
              </Button>
            </div>
          ) : commentaryResults.length > 3 ? (
            <p className="text-center text-sm pt-2 text-muted-foreground">That&apos;s all the results</p>
          ) : null}
        </div>
      )}

      {flagModal && (
        <FlagModal
          heading={flagModal.heading}
          sourceName={flagModal.sourceName}
          author={flagModal.author}
          onSubmit={submitFlag}
          onClose={() => setFlagModal(null)}
        />
      )}
    </section>
  );
}

// ── StudyPage ─────────────────────────────────────────────────────────────────

export default function StudyPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const { role: userRole } = useUserRole(accessToken);
  const [showLogin, setShowLogin] = useState(false);
  const [showGate, setShowGate] = useState(false);
  const [loginInitialMode, setLoginInitialMode] = useState<"signin" | "signup">("signup");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  function openAuthGate(mode: "signin" | "signup" = "signup") {
    setLoginInitialMode(mode);
    if (typeof window !== "undefined" && sessionStorage.getItem("beta_access") === "1") {
      setShowLogin(true);
    } else {
      setShowGate(true);
    }
  }

  const [verseRef, setVerseRef] = useState("John 1:1");
  const [selectedStrongs, setSelectedStrongs] = useState<string | null>(null);
  const [verseData, setVerseData] = useState<VerseData | null>(null);
  const [verseLoading, setVerseLoading] = useState(false);
  const [verseError, setVerseError] = useState<string | null>(null);

  const { tokens, loading: tokensLoading, isNT } = useInterlinear(verseData?.verse_id ?? null);

  const [chapterOpen, setChapterOpen] = useState(false);
  const [chapterVerses, setChapterVerses] = useState<VerseData[]>([]);
  const [chapterLoading, setChapterLoading] = useState(false);

  const [excerptContent, setExcerptContent] = useState<string | null>(null);
  const [excerptLoading, setExcerptLoading] = useState(false);

  const [wordSearchResults, setWordSearchResults] = useState<WordSearchResult[]>([]);
  const [wordSearchOpen, setWordSearchOpen] = useState(false);

  const [wordStudyMode, setWordStudyMode] = useState(false);
  const [wordStudyDoc, setWordStudyDoc] = useState<WordSearchResult | null>(null);
  const [wordStudyContent, setWordStudyContent] = useState<string | null>(null);
  const [wordStudyLoading, setWordStudyLoading] = useState(false);

  const [savedWords, setSavedWords] = useState<SavedWord[]>([]);
  const savedStrongsSet = new Set(savedWords.map((w) => w.strongs_number));

  const [corpusResults, setCorpusResults] = useState<CorpusResult[]>([]);
  const [corpusLoading, setCorpusLoading] = useState(false);

  // Anchor nav active section tracking
  const [activeSection, setActiveSection] = useState("section-words");
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const mobileScrollContainerRef = useRef<HTMLDivElement>(null);
  const [mobileWordSheetOpen, setMobileWordSheetOpen] = useState(false);
  const [mobileChapterOpen, setMobileChapterOpen] = useState(false);

  // ── Saved words ────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!user) { setSavedWords([]); return; }
    supabase
      .from("saved_words").select("*").eq("user_id", user.id)
      .order("created_at", { ascending: false })
      .then(({ data }) => { if (data) setSavedWords(data); });
  }, [user]);

  const toggleSaveWord = useCallback(async (token: WordToken) => {
    if (!user) { setShowLogin(true); return; }
    const isSaved = savedStrongsSet.has(token.strongs);
    if (isSaved) {
      await supabase.from("saved_words").delete().eq("user_id", user.id).eq("strongs_number", token.strongs);
      setSavedWords((prev) => prev.filter((w) => w.strongs_number !== token.strongs));
    } else {
      const { data } = await supabase.from("saved_words").insert({
        user_id: user.id, strongs_number: token.strongs, greek_word: token.greek,
        transliteration: token.transliteration, english_gloss: token.english,
      }).select().single();
      if (data) setSavedWords((prev) => [data, ...prev]);
    }
  }, [user, savedStrongsSet]);

  // ── Verse fetching ─────────────────────────────────────────────────────────

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
      const { data, error } = await supabase.from("verses").select("*").eq("verse_id", verseId).single();
      if (error || !data) {
        const fallback = FALLBACK_VERSES[verseId];
        if (fallback) { setVerseData(fallback); } else { setVerseError("Verse not found"); }
        return;
      }
      setVerseData({
        verse_id: data.verse_id, book: ABBREV_TO_NAME[abbrev] ?? abbrev,
        chapter, verse, text: data.text ?? "", translation: data.translation ?? "WEB",
      });
    } catch {
      const fallback = FALLBACK_VERSES[verseId];
      if (fallback) { setVerseData(fallback); } else { setVerseError("Verse not found"); }
    } finally {
      setVerseLoading(false);
    }
  }, []);

  const lookupVerse = useCallback(async () => {
    const ref = verseRef.trim();
    if (!ref) return;
    setWordStudyMode(false);
    setWordStudyDoc(null);
    setWordStudyContent(null);
    setWordSearchOpen(false);
    setChapterOpen(false);
    setSelectedStrongs(null);
    const parsed = parseRef(ref);
    if (!parsed) { setVerseError("Verse not found"); setVerseData(null); return; }
    await fetchVerseById(`${parsed.abbrev}.${parsed.chapter}.${parsed.verse}`);
  }, [verseRef, fetchVerseById]);

  useEffect(() => {
    const parsed = parseRef(verseRef);
    if (parsed) fetchVerseById(`${parsed.abbrev}.${parsed.chapter}.${parsed.verse}`);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Word selection is page-level, shared by excerpt/corpus/lexicon fetches
  // too — reset it whenever the verse changes, same as before extraction
  // (this used to live inside the interlinear fetch effect; useInterlinear
  // now owns the tokens/loading/isNT fetch itself, keyed on the same verseId).
  useEffect(() => {
    setSelectedStrongs(null);
  }, [verseData?.verse_id]);

  // ── Chapter verses ─────────────────────────────────────────────────────────

  useEffect(() => {
    if ((!chapterOpen && !mobileChapterOpen) || !verseData) { setChapterVerses([]); return; }
    const { verse_id } = verseData;
    const parts = verse_id.split(".");
    const book = parts[0];
    const chapter = parseInt(parts[1], 10);
    setChapterLoading(true);
    const prefix = `${book}.${chapter}.`;
    supabase.from("verses").select("*").like("verse_id", `${prefix}%`).order("verse_id")
      .then(({ data }) => {
        if (data) {
          setChapterVerses(data.map((v: { verse_id: string; text: string; translation?: string }) => {
            const vParts = v.verse_id.split(".");
            return {
              verse_id: v.verse_id, book: ABBREV_TO_NAME[book] ?? book,
              chapter: parseInt(vParts[1], 10), verse: parseInt(vParts[2], 10),
              text: v.text ?? "", translation: v.translation ?? "WEB",
            };
          }));
        }
        setChapterLoading(false);
      });
  }, [chapterOpen, mobileChapterOpen, verseData]);

  // ── Excerpt fetch — fires when word selected ───────────────────────────────

  useEffect(() => {
    if (!selectedStrongs) { setExcerptContent(null); return; }
    setExcerptLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/excerpt?strongs=${encodeURIComponent(selectedStrongs)}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => res.ok ? res.json() : null)
      .then((data) => setExcerptContent(data?.content ?? null))
      .catch(() => setExcerptContent(null))
      .finally(() => setExcerptLoading(false));
  }, [selectedStrongs, accessToken]);

  // ── Corpus results (word selected) ────────────────────────────────────────

  useEffect(() => {
    if (!selectedStrongs) { setCorpusResults([]); return; }
    const token = tokens.find((t) => t.strongs === selectedStrongs);
    if (!token) { setCorpusResults([]); return; }
    const params = new URLSearchParams();
    if (verseRef.trim()) params.set("verse", verseRef.trim());
    params.set("transliteration", token.transliteration);
    params.set("strongs", token.strongs);
    params.set("source_kind", "word_study");
    setCorpusLoading(true);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/corpus?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => { if (!res.ok) throw new Error("corpus fetch failed"); return res.json(); })
      .then((data) => setCorpusResults(data.results ?? []))
      .catch(() => setCorpusResults([]))
      .finally(() => setCorpusLoading(false));
  }, [selectedStrongs, verseRef, tokens, accessToken]);

  // ── Lexicon fetch ──────────────────────────────────────────────────────────

  const selectedLexiconEntry = useLexiconDefinition(selectedStrongs, accessToken);
  const wordStudyLexiconEntry = useLexiconDefinition(wordStudyDoc?.strongs_number ?? null, accessToken);

  // ── Commentary fetch ───────────────────────────────────────────────────────

  const {
    results: commentaryResults,
    loading: commentaryLoading,
    loadingMore: commentaryLoadingMore,
    hasMore: commentaryHasMore,
    loadMore: loadMoreCommentary,
  } = useCommentarySearch(verseData?.text ?? null, verseData?.verse_id ?? null, accessToken);

  // ── Word search (debounced) ────────────────────────────────────────────────

  useEffect(() => {
    const trimmed = verseRef.trim();
    const isPlainWord = trimmed.length >= 2 && !/\d/.test(trimmed);
    const hasBookMatch = matchBooks(verseRef).length > 0;
    if (!isPlainWord || hasBookMatch || wordStudyMode) {
      setWordSearchResults([]); setWordSearchOpen(false); return;
    }
    const timer = setTimeout(() => {
      fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/wordsearch?q=${encodeURIComponent(trimmed)}`)
        .then((res) => { if (!res.ok) throw new Error("wordsearch failed"); return res.json(); })
        .then((data) => { setWordSearchResults(data.results ?? []); setWordSearchOpen((data.results ?? []).length > 0); })
        .catch(() => { setWordSearchResults([]); setWordSearchOpen(false); });
    }, 300);
    return () => clearTimeout(timer);
  }, [verseRef, wordStudyMode]);

  // ── Stepper navigation ─────────────────────────────────────────────────────

  const currentVerseId = verseData?.verse_id ?? null;
  const prevVerseId = currentVerseId ? getAdjacentVerseId(currentVerseId, "prev") : null;
  const nextVerseId = currentVerseId ? getAdjacentVerseId(currentVerseId, "next") : null;

  const stepVerse = useCallback(async (direction: "prev" | "next") => {
    if (!currentVerseId) return;
    const targetId = getAdjacentVerseId(currentVerseId, direction);
    if (!targetId) return;
    const parts = targetId.split(".");
    setVerseRef(`${ABBREV_TO_NAME[parts[0]] ?? parts[0]} ${parts[1]}:${parts[2]}`);
    await fetchVerseById(targetId);
  }, [currentVerseId, fetchVerseById]);

  useEffect(() => {
    if (!currentVerseId) return;
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") { e.preventDefault(); stepVerse("prev"); }
      else if (e.key === "ArrowRight") { e.preventDefault(); stepVerse("next"); }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [currentVerseId, stepVerse]);

  // ── Word study mode from search dropdown ──────────────────────────────────

  const handleWordStudySelect = useCallback((result: WordSearchResult) => {
    setWordStudyMode(true);
    setWordStudyDoc(result);
    setWordSearchOpen(false);
    setVerseData(null);
    setVerseError(null);
    setSelectedStrongs(null);
    // commentaryResults clears itself — useCommentarySearch reacts to
    // verseData becoming null the same way the old inline effect did.
    setCorpusResults([]);
    setVerseRef(result.word || result.transliteration);
    setWordStudyLoading(true);
    setWordStudyContent(null);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/wordstudy/${result.id}`)
      .then((res) => { if (!res.ok) throw new Error("wordstudy fetch failed"); return res.json(); })
      .then((data) => setWordStudyContent(data.content ?? null))
      .catch(() => setWordStudyContent(null))
      .finally(() => setWordStudyLoading(false));
  }, []);

  // ── Definition object ──────────────────────────────────────────────────────

  const selectedToken = selectedStrongs ? tokens.find((t) => t.strongs === selectedStrongs) ?? null : null;

  const definition: WordDefinition | null = selectedToken
    ? { strongs: selectedToken.strongs, word: selectedToken.greek, transliteration: selectedToken.transliteration, gloss: selectedToken.english, lexiconDefinition: selectedLexiconEntry?.lexiconDefinition ?? "", meaning: selectedLexiconEntry?.meaning ?? "" }
    : selectedStrongs && selectedLexiconEntry
    ? { strongs: selectedStrongs, word: selectedStrongs, transliteration: "", gloss: selectedLexiconEntry.gloss, lexiconDefinition: selectedLexiconEntry.lexiconDefinition, meaning: selectedLexiconEntry.meaning }
    : null;

  const wordStudyDefinition: WordDefinition | null = wordStudyDoc
    ? {
        strongs: wordStudyDoc.strongs_number,
        word: wordStudyDoc.word || wordStudyDoc.transliteration,
        transliteration: wordStudyDoc.transliteration,
        gloss: wordStudyLexiconEntry?.gloss ?? "",
        lexiconDefinition: "",
        meaning: wordStudyLexiconEntry?.meaning ?? "",
      }
    : null;

  // ── Save handlers ──────────────────────────────────────────────────────────

  const handleToggleSaveSelected = useCallback(() => {
    if (!selectedStrongs) return;
    const token = tokens.find((t) => t.strongs === selectedStrongs);
    if (token) toggleSaveWord(token);
  }, [selectedStrongs, tokens, toggleSaveWord]);

  const handleToggleSaveWordStudy = useCallback(() => {
    if (!wordStudyDoc) return;
    toggleSaveWord({ greek: wordStudyDoc.word || wordStudyDoc.transliteration, transliteration: wordStudyDoc.transliteration, english: wordStudyDoc.word, strongs: wordStudyDoc.strongs_number, morph: "" });
  }, [wordStudyDoc, toggleSaveWord]);

  const handleSidebarSavedWordSelect = useCallback((strongs: string) => {
    setSelectedStrongs(strongs);
  }, []);

  const handleChapterVerseClick = useCallback((v: VerseData) => {
    setVerseRef(`${v.book} ${v.chapter}:${v.verse}`);
    setChapterOpen(false);
    fetchVerseById(v.verse_id);
  }, [fetchVerseById]);

  const handleMobileChapterVerseClick = useCallback((v: VerseData) => {
    setVerseRef(`${v.book} ${v.chapter}:${v.verse}`);
    setMobileChapterOpen(false);
    fetchVerseById(v.verse_id);
  }, [fetchVerseById]);

  // ── IntersectionObserver for anchor nav ───────────────────────────────────

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const ids = ANCHORS.map((a) => a.id);
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) { setActiveSection(entry.target.id); break; }
        }
      },
      { root: container, rootMargin: "-20% 0px -60% 0px", threshold: 0 }
    );
    ids.forEach((id) => { const el = document.getElementById(id); if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, [verseData?.verse_id]);

  // Mobile IntersectionObserver — scoped to mobileScrollContainerRef
  useEffect(() => {
    const container = mobileScrollContainerRef.current;
    if (!container) return;
    const ids = ANCHORS.map((a) => a.id);
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) { setActiveSection(entry.target.id); break; }
        }
      },
      { root: container, rootMargin: "-20% 0px -60% 0px", threshold: 0 }
    );
    ids.forEach((id) => {
      const el = container.querySelector(`#${id}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [verseData?.verse_id]);

  // ── Derived ────────────────────────────────────────────────────────────────

  const verseSearchProps = {
    verseRef, onChange: setVerseRef, onSubmit: lookupVerse, loading: verseLoading,
    wordSearchResults, wordSearchOpen, onWordStudySelect: handleWordStudySelect,
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
      <Sidebar
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { window.location.href = "/"; }}
        onSignInClick={() => openAuthGate("signup")}
        onSignOut={signOut}
        savedWords={savedWords}
        selectedStrongs={selectedStrongs}
        onSelectSavedWord={handleSidebarSavedWordSelect}
      />

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">

          {/* Top Bar */}
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30 border-b border-border">
            <button
              aria-label="Open sidebar"
              onClick={() => setSidebarOpen(true)}
              className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
            >
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
            <button
              onClick={() => setSidebarOpen(true)}
              aria-label="Saved words"
              title="Saved words"
              className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
            >
              <Bookmark className="h-5 w-5" />
            </button>
            <div className="hidden md:block flex-1" />
          </div>

          {/* ── Desktop: single-column scrollable ── */}
          <div
            ref={scrollContainerRef}
            className="hidden md:flex flex-col flex-1 min-h-0 overflow-y-auto"
          >
            <div className="max-w-3xl mx-auto w-full px-6 pt-6 pb-24">

              {/* 1. Search row */}
              <div className="flex items-center gap-3">
                <VerseSearch {...verseSearchProps} />
                {verseData && (
                  <button
                    onClick={() => setChapterOpen((p) => !p)}
                    className="shrink-0 h-9 px-3 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  >
                    {chapterOpen ? "Hide Chapter" : "View Chapter"}
                  </button>
                )}
              </div>

              {/* 2. Anchor nav */}
              <AnchorNav activeSection={activeSection} scrollContainer={scrollContainerRef} />

              {/* Word study mode override */}
              {wordStudyMode && wordStudyDoc ? (
                <div className="pt-6">
                  <WordStudyPanel
                    doc={wordStudyDoc}
                    definition={wordStudyDefinition}
                    isSaved={savedStrongsSet.has(wordStudyDoc.strongs_number)}
                    onToggleSave={handleToggleSaveWordStudy}
                    isLoggedIn={!!user}
                  />
                </div>
              ) : (
                <>
                  {/* 3. Verse block */}
                  <section id="section-words" className="pt-6">
                    {verseError && <p role="alert" aria-live="polite" className="text-sm text-destructive mt-2">{verseError}</p>}
                    {verseLoading && (
                      <div className="rounded-lg border border-border bg-card p-4 animate-pulse">
                        <Skeleton className="h-4 w-1/3 mx-auto mb-4" />
                        <Skeleton className="h-4 w-full mb-2" />
                        <Skeleton className="h-4 w-5/6" />
                      </div>
                    )}

                    {!verseLoading && verseData && !chapterOpen && (
                      <div>
                        {/* Reference header + arrows — centered, borderless */}
                        <div className="flex items-center justify-center gap-3">
                          <button
                            onClick={() => stepVerse("prev")}
                            disabled={!prevVerseId}
                            className="text-sm font-medium text-muted-foreground disabled:opacity-30 hover:text-foreground transition-colors"
                          >
                            &larr;
                          </button>
                          <p className="text-xs font-medium uppercase tracking-wide text-primary">
                            {verseData.book} {verseData.chapter}:{verseData.verse} ({verseData.translation})
                          </p>
                          <button
                            onClick={() => stepVerse("next")}
                            disabled={!nextVerseId}
                            className="text-sm font-medium text-muted-foreground disabled:opacity-30 hover:text-foreground transition-colors"
                          >
                            &rarr;
                          </button>
                        </div>

                        {/* Verse text — new focal point, no card */}
                        <p className="font-sans text-xl md:text-2xl leading-relaxed text-foreground text-center mt-4">
                          {verseData.text}
                        </p>

                        {/* Interlinear row — always visible */}
                        <InterlinearBlocks
                          tokens={tokens}
                          selectedStrongs={selectedStrongs}
                          onSelect={(strongs) => setSelectedStrongs(strongs)}
                          loading={tokensLoading}
                          isNT={isNT}
                        />

                        {/* Inline word panel */}
                        {selectedStrongs && (
                          <InlineWordPanel
                            definition={definition}
                            excerptContent={excerptContent}
                            excerptLoading={excerptLoading}
                            corpusResults={corpusResults}
                            corpusLoading={corpusLoading}
                            isSaved={savedStrongsSet.has(selectedStrongs)}
                            onToggleSave={handleToggleSaveSelected}
                            onClose={() => setSelectedStrongs(null)}
                            isLoggedIn={!!user}
                          />
                        )}
                      </div>
                    )}

                    {/* Chapter view */}
                    {!verseLoading && verseData && chapterOpen && (
                      <div className="rounded-lg border border-border bg-card p-4">
                        {chapterLoading ? (
                          <div className="space-y-2">
                            {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
                          </div>
                        ) : (
                          <p className="font-sans text-base leading-relaxed text-foreground">
                            {chapterVerses.map((v) => {
                              const isActive = v.verse_id === verseData.verse_id;
                              return (
                                <span
                                  key={v.verse_id}
                                  role="button"
                                  tabIndex={0}
                                  onClick={() => handleChapterVerseClick(v)}
                                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleChapterVerseClick(v); } }}
                                  className={cn(
                                    "cursor-pointer rounded-sm transition-colors px-0.5 -mx-0.5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
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
                  </section>

                  {/* 4. Commentary */}
                  <CommentarySection
                    key={verseData?.verse_id ?? "no-verse"}
                    commentaryResults={commentaryResults}
                    commentaryLoading={commentaryLoading}
                    commentaryLoadingMore={commentaryLoadingMore}
                    commentaryHasMore={commentaryHasMore}
                    onLoadMoreCommentary={loadMoreCommentary}
                    verseRef={verseRef}
                    accessToken={accessToken}
                  />

                  {/* 5. Pastors' Notes */}
                  <PastorsNotesSection
                    verseId={currentVerseId}
                    accessToken={accessToken}
                    role={userRole}
                    userId={user?.id ?? null}
                  />
                </>
              )}
            </div>
          </div>

          {/* ── Mobile: full single-column scrollable ── */}
          <div ref={mobileScrollContainerRef} className="flex flex-1 flex-col overflow-y-auto md:hidden">

            {/* Sticky header: search + anchor nav */}
            <div className="sticky top-0 z-20 bg-background border-b border-border px-4">
              <div className="pt-4 pb-2">
                <VerseSearch {...verseSearchProps} />
              </div>
              {verseData && !wordStudyMode && (
                <nav className="flex gap-6 overflow-x-auto pb-3">
                  {ANCHORS.map(({ id, label }) => (
                    <button
                      key={id}
                      onClick={() => {
                        const container = mobileScrollContainerRef.current;
                        const el = container?.querySelector(`#${id}`);
                        if (el && container) {
                          const containerRect = container.getBoundingClientRect();
                          const elRect = el.getBoundingClientRect();
                          const targetTop = container.scrollTop + (elRect.top - containerRect.top) - 130;
                          container.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
                        }
                      }}
                      className={cn(
                        "text-sm whitespace-nowrap shrink-0 min-h-[44px] transition-colors",
                        activeSection === id ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </nav>
              )}
            </div>

            <div className="px-4 pb-24">
              {wordStudyMode && wordStudyDoc ? (
                <div className="pt-6">
                  <WordStudyPanel
                    doc={wordStudyDoc}
                    definition={wordStudyDefinition}
                    isSaved={savedStrongsSet.has(wordStudyDoc.strongs_number)}
                    onToggleSave={handleToggleSaveWordStudy}
                    isLoggedIn={!!user}
                  />
                </div>
              ) : (
                <>
                  {verseError && <p role="alert" aria-live="polite" className="text-sm mt-4 text-destructive">{verseError}</p>}
                  {verseLoading && (
                    <div className="mt-4 rounded-lg border border-border bg-card p-4 animate-pulse">
                      <Skeleton className="h-4 w-1/3 mx-auto mb-4" />
                      <Skeleton className="h-4 w-full mb-2" />
                      <Skeleton className="h-4 w-5/6" />
                    </div>
                  )}

                  {/* Words section */}
                  {!verseLoading && verseData && (
                    <section id="section-words" className="pt-4">
                      <div>
                        <div className="flex items-center justify-center gap-3">
                          <button
                            onClick={() => stepVerse("prev")}
                            disabled={!prevVerseId}
                            className="text-sm font-medium text-muted-foreground disabled:opacity-30 hover:text-foreground transition-colors min-h-[44px] px-2"
                          >
                            &larr;
                          </button>
                          <p className="text-xs font-medium uppercase tracking-wide text-primary">
                            {verseData.book} {verseData.chapter}:{verseData.verse} ({verseData.translation})
                          </p>
                          <button
                            onClick={() => stepVerse("next")}
                            disabled={!nextVerseId}
                            className="text-sm font-medium text-muted-foreground disabled:opacity-30 hover:text-foreground transition-colors min-h-[44px] px-2"
                          >
                            &rarr;
                          </button>
                        </div>
                        <p className="font-sans text-xl leading-relaxed text-foreground text-center mt-4">
                          {verseData.text}
                        </p>
                        <button
                          onClick={() => setMobileChapterOpen(true)}
                          className="mt-3 text-xs text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2"
                        >
                          View Chapter
                        </button>
                        {/* Interlinear — tapping a word opens the word bottom sheet */}
                        <InterlinearBlocks
                          tokens={tokens}
                          selectedStrongs={selectedStrongs}
                          onSelect={(strongs) => {
                            setSelectedStrongs(strongs);
                            if (strongs) setMobileWordSheetOpen(true);
                          }}
                          loading={tokensLoading}
                          isNT={isNT}
                        />
                      </div>
                    </section>
                  )}

                  {/* Commentary */}
                  <CommentarySection
                    key={(verseData?.verse_id ?? "no-verse") + "-mobile"}
                    commentaryResults={commentaryResults}
                    commentaryLoading={commentaryLoading}
                    commentaryLoadingMore={commentaryLoadingMore}
                    commentaryHasMore={commentaryHasMore}
                    onLoadMoreCommentary={loadMoreCommentary}
                    verseRef={verseRef}
                    accessToken={accessToken}
                  />

                  {/* Pastors' Notes */}
                  <PastorsNotesSection
                    verseId={currentVerseId}
                    accessToken={accessToken}
                    role={userRole}
                    userId={user?.id ?? null}
                  />
                </>
              )}
            </div>
          </div>

        </div>
      </main>

      {/* Mobile: word definition bottom sheet */}
      <Sheet
        open={mobileWordSheetOpen}
        onOpenChange={(open) => {
          if (!open) { setMobileWordSheetOpen(false); setSelectedStrongs(null); }
        }}
      >
        <SheetContent side="bottom" className="h-[85vh] overflow-y-auto p-0 rounded-t-xl md:hidden">
          <SheetTitle className="sr-only">{definition?.word ?? "Word Study"}</SheetTitle>
          {selectedStrongs && (
            <div className="p-4 pt-6">
              <InlineWordPanel
                definition={definition}
                excerptContent={excerptContent}
                excerptLoading={excerptLoading}
                corpusResults={corpusResults}
                corpusLoading={corpusLoading}
                isSaved={savedStrongsSet.has(selectedStrongs)}
                onToggleSave={handleToggleSaveSelected}
                onClose={() => { setMobileWordSheetOpen(false); setSelectedStrongs(null); }}
                isLoggedIn={!!user}
              />
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Mobile: chapter view bottom sheet */}
      <Sheet open={mobileChapterOpen} onOpenChange={setMobileChapterOpen}>
        <SheetContent side="bottom" className="h-[90vh] overflow-y-auto p-0 rounded-t-xl md:hidden">
          <SheetTitle className="sr-only">{verseData ? `${verseData.book} ${verseData.chapter}` : "Chapter View"}</SheetTitle>
          <div className="p-4 pt-6 pb-16">
            <div className="flex items-center justify-between mb-4">
              <button
                onClick={() => setMobileChapterOpen(false)}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors min-h-[44px] pr-4"
              >
                &larr; Back
              </button>
              {verseData && (
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {verseData.book} {verseData.chapter}
                </p>
              )}
              <div className="w-16" />
            </div>
            {chapterLoading ? (
              <div className="space-y-2">
                {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
              </div>
            ) : (
              <p className="font-sans text-base leading-relaxed text-foreground">
                {chapterVerses.map((v) => {
                  const isActive = v.verse_id === verseData?.verse_id;
                  return (
                    <span
                      key={v.verse_id}
                      role="button"
                      tabIndex={0}
                      onClick={() => handleMobileChapterVerseClick(v)}
                      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleMobileChapterVerseClick(v); } }}
                      className={cn(
                        "cursor-pointer rounded-sm transition-colors px-0.5 -mx-0.5 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
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
        </SheetContent>
      </Sheet>

      {showGate && <BetaGate onSuccess={() => { setShowGate(false); setShowLogin(true); }} onClose={() => setShowGate(false)} />}
      {showLogin && (
        <LoginModal onClose={() => setShowLogin(false)} onSignIn={signIn} onSignUp={signUp} initialMode={loginInitialMode} />
      )}
    </div>
  );
}
