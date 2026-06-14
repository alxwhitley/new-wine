"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import Link from "next/link";
import Image from "next/image";
import {
  Search, ArrowLeft, Loader2, Menu, ChevronDown,
  Trash2, Pencil, SlidersHorizontal,
} from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import LoginModal from "@/components/auth/LoginModal";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  searchDocumentsFts, browseDocuments, getArticle, fetchBooks, deleteDocument,
  fetchDocMeta, fetchRecentDocs, fetchSourceCounts, fetchRecentNotes,
} from "@/lib/api";
import type {
  DocumentSearchResult, ArticleResponse, Book,
  DiscoverDoc, SourceCounts, PastorsNote,
} from "@/lib/api";

// ── Constants ─────────────────────────────────────────────────────────────────

/**
 * Hand-edited featured document IDs. Replace with real UUIDs from the corpus.
 * Leave empty to hide the Featured section entirely.
 */
const FEATURED_IDS: string[] = [];

const SEARCH_SUGGESTIONS = [
  "Hearing God's Voice",
  "Identity in Christ",
  "Renewing the Mind",
];

const AUTHOR_IMAGES: Record<string, string> = {
  "Ern Baxter": "/images/authors/ern-baxter.webp",
  "Jack Deere": "/images/authors/jack-deere.jpeg",
  "John Bevere": "/images/authors/john-bevere.webp",
  "Michael Brown": "/images/authors/michael-brown.jpeg",
  "Oswald J. Smith": "/images/authors/oswald-smith.jpeg",
};

const CLASSIC_AUTHORS = new Set(["Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson", "Don Basham", "Oswald J. Smith"]);

const AUTHOR_DATA = [
  { name: "Derek Prince", years: "1915–2003", specialty: "Deliverance, spiritual warfare, and foundational Spirit-filled living." },
  { name: "Bob Mumford", years: "b. 1930", specialty: "Kingdom of God theology and the Father heart of God." },
  { name: "Ern Baxter", years: "1914–1993", specialty: "Kingdom proclamation, worship, and Spirit-empowered preaching." },
  { name: "Charles Simpson", years: "1937–2024", specialty: "Covenant community, pastoral care, and charismatic church life." },
  { name: "Don Basham", years: "1926–1989", specialty: "Holy Spirit baptism, deliverance ministry, and spiritual authority." },
  { name: "John Bevere", years: "b. 1959", specialty: "The fear of the Lord, spiritual authority, and uncompromising discipleship." },
  { name: "Michael Brown", years: "b. 1955", specialty: "Revival, Jewish roots of Christianity, and cultural apologetics." },
  { name: "Jack Deere", years: "b. 1948", specialty: "Continuation of spiritual gifts, prophecy, and hearing God's voice." },
  { name: "Oswald J. Smith", years: "1889–1986", specialty: "Evangelism, world missions, and the Spirit-empowered church." },
];

const BOOK_COVERS: Record<string, string> = {
  "Blessing or Curse: You Can Choose": "/images/books/blessing-or-curse.jpg",
  "They Shall Expel Demons": "/images/books/they-shall-expel-demons.jpg",
  "Shaping History Through Prayer and Fasting": "/images/books/shaping-history-prayer-fasting.jpg",
  "Holy Spirit in You": "/images/books/holy-spirit-in-you.jpg",
  "The King and You": "/images/books/the-king-and-you.jpg",
  "A Handbook on Holy Spirit Baptism": "/images/books/handbook-holy-spirit-baptism.jpg",
  "True and False Prophets": "/images/books/true-and-false-prophets.jpg",
  "The Bait of Satan": "/images/books/bait-of-satan.jpg",
  "Driven by Eternity": "/images/books/driven-by-eternity.jpg",
  "Our Hands Are Stained with Blood": "/images/books/our-hands-are-stained.jpg",
  "Answering Jewish Objections to Jesus": "/images/books/answering-jewish-objections.jpg",
  "Whatever Happened to the Power of God?": "/images/books/whatever-happened-power-of-god.jpg",
  "Authentic Fire": "/images/books/authentic-fire.jpg",
  "Revolution in the Church": "/images/books/revolution-in-the-church.jpg",
  "Why I Am Still Surprised by the Power of the Spirit": "/images/books/still-surprised-by-spirit.jpg",
};

const VERSE_BOOK_NAMES: Record<string, string> = {
  GEN: "Genesis", EXO: "Exodus", LEV: "Leviticus", NUM: "Numbers", DEU: "Deuteronomy",
  JOS: "Joshua", JDG: "Judges", RUT: "Ruth", "1SA": "1 Samuel", "2SA": "2 Samuel",
  "1KI": "1 Kings", "2KI": "2 Kings", "1CH": "1 Chronicles", "2CH": "2 Chronicles",
  EZR: "Ezra", NEH: "Nehemiah", EST: "Esther", JOB: "Job", PSA: "Psalms",
  PRO: "Proverbs", ECC: "Ecclesiastes", SNG: "Song of Solomon", ISA: "Isaiah",
  JER: "Jeremiah", LAM: "Lamentations", EZK: "Ezekiel", DAN: "Daniel",
  HOS: "Hosea", JOL: "Joel", AMO: "Amos", OBA: "Obadiah", JON: "Jonah",
  MIC: "Micah", NAM: "Nahum", HAB: "Habakkuk", ZEP: "Zephaniah", HAG: "Haggai",
  ZEC: "Zechariah", MAL: "Malachi", MAT: "Matthew", MRK: "Mark", LUK: "Luke",
  JHN: "John", ACT: "Acts", ROM: "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
  GAL: "Galatians", EPH: "Ephesians", PHP: "Philippians", COL: "Colossians",
  "1TH": "1 Thessalonians", "2TH": "2 Thessalonians", "1TI": "1 Timothy", "2TI": "2 Timothy",
  TIT: "Titus", PHM: "Philemon", HEB: "Hebrews", JAS: "James", "1PE": "1 Peter",
  "2PE": "2 Peter", "1JN": "1 John", "2JN": "2 John", "3JN": "3 John", JUD: "Jude",
  REV: "Revelation",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function getInitials(name: string) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

function formatVerseRef(verseId: string): string {
  const parts = verseId.split(".");
  if (parts.length !== 3) return verseId;
  const book = VERSE_BOOK_NAMES[parts[0]] || parts[0];
  return `${book} ${parts[1]}:${parts[2]}`;
}

function sourceKindLabel(kind: string | null): string {
  switch (kind) {
    case "magazine_article": return "Article";
    case "sermon_transcript": return "Sermon";
    case "paper": return "Paper";
    case "book": return "Book";
    case "background": return "Study";
    case "commentary": return "Commentary";
    default: return kind || "Document";
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function DiscoverDocCard({
  doc, onClick, isHero = false,
}: {
  doc: DiscoverDoc;
  onClick: () => void;
  isHero?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex flex-col text-left w-full rounded-lg border border-border bg-card hover:bg-accent transition-colors",
        isHero ? "p-5 min-h-[180px]" : "p-4"
      )}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          {sourceKindLabel(doc.source_kind)}
        </span>
      </div>
      {doc.author && (
        <p className="text-xs text-muted-foreground">{doc.author}</p>
      )}
      <h3 className={cn(
        "font-sans font-semibold text-foreground leading-snug mt-1",
        isHero ? "text-base md:text-lg" : "text-sm"
      )}>
        {doc.title}
      </h3>
      {doc.content_summary && (
        <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 leading-relaxed">
          {doc.content_summary}
        </p>
      )}
      {doc.topic_tags && doc.topic_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {doc.topic_tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="inline-block text-[10px] bg-secondary text-secondary-foreground rounded-md px-1.5 py-0.5"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
      {doc.year && (
        <p className="text-[11px] text-muted-foreground mt-auto pt-2">{doc.year}</p>
      )}
    </button>
  );
}

function PastorsNoteCard({ note }: { note: PastorsNote }) {
  const snippet = note.content.length > 160
    ? note.content.slice(0, 160).replace(/\s\S*$/, "") + "…"
    : note.content;

  return (
    <a
      href={`/study?verse=${encodeURIComponent(note.verse_id)}`}
      className="flex flex-col rounded-lg border border-border bg-card hover:bg-accent transition-colors p-4"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="rounded-full bg-secondary text-secondary-foreground text-[11px] font-medium px-2 py-0.5">
          {formatVerseRef(note.verse_id)}
        </span>
        {note.display_name && (
          <span className="text-[11px] text-muted-foreground truncate">{note.display_name}</span>
        )}
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed">{snippet}</p>
    </a>
  );
}

function SectionHeader({
  label, href, linkLabel,
}: {
  label: string;
  href?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground">
        {label}
      </span>
      {href && linkLabel && (
        <Link
          href={href}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          {linkLabel}
        </Link>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

type ContentFilter = "all" | "articles" | "sermons" | "books";

type UnifiedResult =
  | { type: "doc"; data: DocumentSearchResult }
  | { type: "book"; data: Book };

export default function LibraryPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const isMobile = useIsMobile();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { conversations, deleteConversation } = useConversations(user?.id);

  // ── Discover data ──────────────────────────────────────────────────────────
  const [featuredDocs, setFeaturedDocs] = useState<DiscoverDoc[]>([]);
  const [recentDocs, setRecentDocs] = useState<DiscoverDoc[]>([]);
  const [magazineDocs, setMagazineDocs] = useState<DocumentSearchResult[]>([]);
  const [recentNotes, setRecentNotes] = useState<PastorsNote[]>([]);
  const [sourceCounts, setSourceCounts] = useState<SourceCounts | null>(null);
  const [discoverLoading, setDiscoverLoading] = useState(true);

  // ── Search/browse mode ─────────────────────────────────────────────────────
  const [discoverMode, setDiscoverMode] = useState(true);
  const [query, setQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>([]);
  const [eraFilter, setEraFilter] = useState("");
  const [contentFilter, setContentFilter] = useState<ContentFilter>("all");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [draftAuthors, setDraftAuthors] = useState<string[]>([]);
  const [draftEra, setDraftEra] = useState("");

  const [docResults, setDocResults] = useState<DocumentSearchResult[]>([]);
  const [bookResults, setBookResults] = useState<Book[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [failedAuthorImages, setFailedAuthorImages] = useState<Set<string>>(new Set());

  // ── Article reader ─────────────────────────────────────────────────────────
  const [article, setArticle] = useState<ArticleResponse | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);

  // ── Admin ──────────────────────────────────────────────────────────────────
  const isAdmin = user?.id === "1ea99425-08ec-40f2-9ed3-588b88122a82";
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const activeFilterCount = selectedAuthors.length + (eraFilter ? 1 : 0);
  const authorParam = selectedAuthors.length > 0 ? selectedAuthors.join(",") : undefined;
  const effectiveEra = eraFilter || undefined;

  // ── Load Discover sections on mount ───────────────────────────────────────
  useEffect(() => {
    async function loadDiscover() {
      setDiscoverLoading(true);
      await Promise.allSettled([
        FEATURED_IDS.length > 0
          ? fetchDocMeta(FEATURED_IDS).then((r) => setFeaturedDocs(r.results)).catch(() => {})
          : Promise.resolve(),
        fetchRecentDocs(6).then((r) => setRecentDocs(r.results)).catch(() => {}),
        browseDocuments({ source_kind: "magazine_article" })
          .then((r) => setMagazineDocs(r.results.slice(0, 6)))
          .catch(() => {}),
        fetchRecentNotes(4).then(setRecentNotes).catch(() => {}),
        fetchSourceCounts().then(setSourceCounts).catch(() => {}),
      ]);
      setDiscoverLoading(false);
    }
    loadDiscover();
  }, []);

  // ── Click outside to dismiss suggestions ──────────────────────────────────
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchBarRef.current && !searchBarRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // ── Search/browse fetch ────────────────────────────────────────────────────
  const fetchResults = useCallback(async (q?: string, filter: ContentFilter = contentFilter) => {
    setLoading(true);
    setError(null);
    setDiscoverMode(false);
    try {
      const includeArticles = filter === "all" || filter === "articles";
      const includeSermons = filter === "all" || filter === "sermons";
      const includeBooks = filter === "all" || filter === "books";

      let newDocs: DocumentSearchResult[] = [];
      let newBooks: Book[] = [];

      const promises: Promise<void>[] = [];

      if (includeArticles || includeSermons) {
        let sourceKind: string | undefined;
        if (includeArticles && !includeSermons) sourceKind = "magazine_article";
        else if (includeSermons && !includeArticles) sourceKind = "sermon_transcript";
        else sourceKind = undefined;

        if (q && q.trim()) {
          promises.push(
            searchDocumentsFts({ q: q.trim(), source_kind: sourceKind, include_copyrighted: true, era: effectiveEra, author: authorParam })
              .then((r) => { newDocs = r.results; })
          );
        } else {
          promises.push(
            browseDocuments({ source_kind: sourceKind, include_copyrighted: true, era: effectiveEra, author: authorParam })
              .then((r) => { newDocs = r.results; })
          );
        }
      }
      if (includeBooks) {
        promises.push(
          fetchBooks({ q: q?.trim() || undefined, era: effectiveEra, author: authorParam })
            .then((r) => { newBooks = r.results; })
        );
      }

      await Promise.all(promises);
      setDocResults(newDocs);
      setBookResults(newBooks);
    } catch {
      setError("Failed to load results.");
    } finally {
      setLoading(false);
    }
  }, [contentFilter, effectiveEra, authorParam]);

  const handleSearch = useCallback(() => {
    setShowSuggestions(false);
    fetchResults(query);
  }, [query, fetchResults]);

  const handleSuggestionClick = useCallback((text: string) => {
    setQuery(text);
    setShowSuggestions(false);
    fetchResults(text);
  }, [fetchResults]);

  const handleBrowseTile = useCallback((filter: ContentFilter) => {
    setContentFilter(filter);
    setQuery("");
    fetchResults(undefined, filter);
  }, [fetchResults]);

  const handleBackToDiscover = useCallback(() => {
    setDiscoverMode(true);
    setQuery("");
    setContentFilter("all");
    setSelectedAuthors([]);
    setEraFilter("");
    setDocResults([]);
    setBookResults([]);
    setError(null);
  }, []);

  const handleCardClick = useCallback(async (id: string, sourceKind?: string | null) => {
    setArticleLoading(true);
    setError(null);
    try {
      const version = sourceKind === "sermon_transcript" ? "rewritten" : "original";
      const data = await getArticle(id, version);
      setArticle(data);
    } catch {
      setError("Failed to load article.");
    } finally {
      setArticleLoading(false);
    }
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    if (!accessToken) return;
    setDeleteError(null);
    try {
      await deleteDocument(id, accessToken);
      setDocResults((prev) => prev.filter((d) => d.id !== id));
      setConfirmingDeleteId(null);
    } catch {
      setDeleteError(id);
    }
  }, [accessToken]);

  // ── Unified results ────────────────────────────────────────────────────────
  const articles = docResults.filter((d) => d.source_kind !== "sermon_transcript");
  const sermons = docResults.filter((d) => d.source_kind === "sermon_transcript");
  const totalCount = docResults.length + bookResults.length;

  // ── Card renderers (search mode) ───────────────────────────────────────────
  const renderDocCard = (doc: DocumentSearchResult) => {
    const isNewWine = doc.source_kind !== "sermon_transcript" && (doc.source_name || "").toLowerCase().includes("new wine");
    return (
      <button
        key={doc.id}
        onClick={() => handleCardClick(doc.id, doc.source_kind)}
        className="relative flex flex-col text-left cursor-pointer bg-card border border-border rounded-lg p-4 transition-colors hover:bg-accent"
      >
        <div className="flex items-center gap-2">
          {doc.author && (
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">{doc.author}</p>
          )}
          {isNewWine && (
            <span className="text-xs text-muted-foreground">New Wine</span>
          )}
        </div>
        <h3 className="font-sans text-[15px] font-semibold text-foreground leading-snug mt-1.5">{doc.title}</h3>
        <div className="border-t border-border my-3" />
        {isNewWine && doc.description ? (
          <p className="line-clamp-2 text-xs text-muted-foreground italic leading-relaxed">
            {doc.description.length > 150 ? doc.description.slice(0, 150) + "…" : doc.description}
          </p>
        ) : doc.topic_tags && doc.topic_tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {doc.topic_tags.slice(0, 2).map((tag) => (
              <span key={tag} className="inline-block text-[10px] bg-secondary text-secondary-foreground rounded-md px-1.5 py-0.5">
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        {doc.year && <p className="mt-auto text-[11px] text-muted-foreground pt-2.5">{doc.year}</p>}
        {isAdmin && (
          confirmingDeleteId === doc.id ? (
            <span className="absolute bottom-3 right-3 flex gap-2" onClick={(e) => e.stopPropagation()}>
              {deleteError === doc.id && <span className="text-[11px] text-destructive">Error</span>}
              <button onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }} className="text-[11px] text-destructive cursor-pointer">Delete</button>
              <button onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(null); setDeleteError(null); }} className="text-[11px] text-muted-foreground cursor-pointer">Cancel</button>
            </span>
          ) : (
            <span className="absolute bottom-3 right-3 flex gap-2 items-center" onClick={(e) => e.stopPropagation()}>
              <a href={`/admin/edit/${doc.id}`} onClick={(e) => e.stopPropagation()} className="flex cursor-pointer">
                <Pencil className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground transition-colors" />
              </a>
              <span className="flex cursor-pointer" onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(doc.id); }}>
                <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground transition-colors" />
              </span>
            </span>
          )
        )}
      </button>
    );
  };

  const renderBookCard = (book: Book) => {
    const coverSrc = BOOK_COVERS[book.title];
    return (
      <div key={book.id} className="flex flex-row bg-card border border-border rounded-lg p-4 gap-3.5 transition-colors hover:bg-accent">
        {coverSrc ? (
          <Image
            src={coverSrc}
            alt={book.title}
            width={56}
            height={80}
            className="object-cover flex-shrink-0 rounded-sm shadow-sm w-14 h-20"
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              img.style.display = "none";
              img.nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <div className={cn(coverSrc ? "hidden" : "", "w-14 h-20 rounded-sm bg-muted flex-shrink-0")} />
        <div className="flex flex-col min-w-0">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">{book.author}</p>
          <h4 className="font-sans text-[15px] font-semibold text-foreground leading-snug mt-1.5">{book.title}</h4>
          <div className="border-t border-border my-3" />
          {book.description && (
            <p className="line-clamp-2 text-[13px] text-muted-foreground leading-relaxed">{book.description}</p>
          )}
          {book.document_id && (
            <a
              href={`/library/book/${book.document_id}`}
              onClick={(e) => e.stopPropagation()}
              className="min-h-[44px] flex items-center justify-center text-xs text-center border border-border text-muted-foreground rounded-md px-2.5 mt-3 transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              Read Excerpts
            </a>
          )}
        </div>
      </div>
    );
  };

  // ── Shared chrome (sidebar + modal wrappers) ───────────────────────────────
  const sidebarProps = {
    conversations,
    activeConversationId: null,
    isLoggedIn: !!user,
    user,
    accessToken,
    isOpen: sidebarOpen,
    onClose: () => setSidebarOpen(false),
    onNewChat: () => { window.location.href = "/"; },
    onSelectConversation: (id: string) => { window.location.href = `/?c=${id}`; },
    onDeleteConversation: deleteConversation,
    onSignInClick: () => { setLoginReason(undefined); setShowLogin(true); },
    onSignOut: signOut,
  };

  // ── Article reader view ────────────────────────────────────────────────────
  if (article) {
    return (
      <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
        <Sidebar {...sidebarProps} />
        <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
          <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
            <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
              <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
                <Menu className="h-5 w-5" />
              </button>
              <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
              <div className="md:hidden min-w-[44px]" />
            </div>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-2xl px-4 md:px-6 pt-8 pb-16">
                <button
                  onClick={() => setArticle(null)}
                  className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-8 min-h-[44px]"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back to results
                </button>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h1 className="font-sans text-2xl font-semibold text-foreground leading-tight">{article.title}</h1>
                    {article.author && <p className="text-sm text-muted-foreground mt-2">{article.author}</p>}
                  </div>
                  {article.source_kind === "sermon_transcript" && article.url && (
                    <a
                      href={article.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 rounded px-3 py-1 text-sm border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
                    >
                      Visit Original Source
                    </a>
                  )}
                </div>
                {article.issue && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {(() => {
                      const months = ["January","February","March","April","May","June","July","August","September","October","November","December"];
                      const [mm, yyyy] = article.issue.split("-");
                      const monthIdx = parseInt(mm, 10) - 1;
                      return months[monthIdx] && yyyy ? `${months[monthIdx]} ${yyyy}` : article.issue;
                    })()}
                  </p>
                )}
                <div className="border-t border-border my-6" />
                {article.source_kind === "sermon_transcript" && (
                  <p className="text-sm italic text-muted-foreground mb-6">
                    These are structured notes drawn from the sermon, not a word-for-word transcript.
                  </p>
                )}
                <div className="prose prose-sm prose-invert max-w-none">
                  <ReactMarkdown>
                    {article.content.replace(/^#\s+[^\n]*\n?/, "").replace(/^\*by\s+[^\n]*\n?/, "").trimStart()}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          </div>
        </main>
        {showLogin && <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />}
      </div>
    );
  }

  // ── Main layout ────────────────────────────────────────────────────────────
  return (
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
      <Sidebar {...sidebarProps} />

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">

          {/* Top bar (mobile only) */}
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30 border-b border-border">
            <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
            <div className="md:hidden min-w-[44px]" />
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-5xl px-4 md:px-6 pt-10 pb-16">

              {/* Page title */}
              <h2 className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center mb-6">
                Discover
              </h2>

              {/* Search bar + filter icon */}
              <div className="relative mb-6" ref={searchBarRef}>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <input
                      type="text"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      onFocus={() => setShowSuggestions(true)}
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleSearch(); } }}
                      placeholder="Search articles, authors, topics…"
                      className="w-full min-h-[44px] rounded-lg border border-border bg-card pl-9 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
                    />
                  </div>
                  <button
                    onClick={() => {
                      setDraftAuthors(selectedAuthors);
                      setDraftEra(eraFilter);
                      setFiltersOpen(true);
                    }}
                    className={cn(
                      "min-h-[44px] min-w-[44px] rounded-lg border flex items-center justify-center gap-1.5 px-3 text-sm transition-colors",
                      activeFilterCount > 0
                        ? "border-primary text-primary"
                        : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
                    )}
                  >
                    <SlidersHorizontal className="h-4 w-4" />
                    {activeFilterCount > 0 && (
                      <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-primary text-primary-foreground text-[10px] font-medium">
                        {activeFilterCount}
                      </span>
                    )}
                  </button>
                  <button
                    onClick={handleSearch}
                    disabled={loading}
                    className="min-h-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center gap-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                  >
                    <span className="hidden sm:inline">Search</span>
                    <Search className="h-4 w-4 sm:hidden" />
                  </button>
                </div>

                {showSuggestions && (
                  <div className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-border bg-popover p-3 z-20">
                    <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">Suggested topics</p>
                    <div className="flex flex-wrap gap-1.5">
                      {SEARCH_SUGGESTIONS.map((s) => (
                        <button
                          key={s}
                          onClick={() => handleSuggestionClick(s)}
                          className="rounded-full px-3 py-1 text-xs font-medium cursor-pointer text-primary bg-primary/10 border border-primary/25 hover:bg-primary/20 transition-colors"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* ── SEARCH/BROWSE MODE ──────────────────────────────────────── */}
              {!discoverMode && (
                <div>
                  {/* Back + content type pills */}
                  <div className="flex items-center gap-3 mb-4 flex-wrap">
                    <button
                      onClick={handleBackToDiscover}
                      className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors min-h-[36px]"
                    >
                      <ArrowLeft className="h-4 w-4" />
                      Discover
                    </button>
                    <div className="flex gap-2">
                      {(["all", "articles", "sermons", "books"] as ContentFilter[]).map((f) => (
                        <button
                          key={f}
                          onClick={() => { setContentFilter(f); fetchResults(query, f); }}
                          className={cn(
                            "rounded-md px-3 py-1 text-xs font-medium transition-colors cursor-pointer capitalize",
                            contentFilter === f
                              ? "bg-primary text-primary-foreground"
                              : "border border-border hover:bg-accent"
                          )}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  </div>

                  {error && <p className="text-sm text-destructive mt-4 text-center">{error}</p>}

                  {loading || articleLoading ? (
                    <div className="flex justify-center mt-12">
                      <Loader2 className="h-6 w-6 text-primary animate-spin" />
                    </div>
                  ) : (
                    <div className="mt-2">
                      {totalCount === 0 ? (
                        <p className="text-center text-muted-foreground mt-12">No results found</p>
                      ) : contentFilter === "all" ? (
                        <>
                          <p className="text-xs text-muted-foreground mb-4">{totalCount} result{totalCount !== 1 ? "s" : ""}</p>
                          <div className="flex flex-col gap-8">
                            {sermons.length > 0 && (
                              <div>
                                <div className="flex items-center gap-2.5 mb-3">
                                  <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground whitespace-nowrap">Sermons</span>
                                  <div className="flex-1 h-px bg-border" />
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                  {sermons.map((doc) => renderDocCard(doc))}
                                </div>
                              </div>
                            )}
                            {articles.length > 0 && (
                              <div>
                                <div className="flex items-center gap-2.5 mb-3">
                                  <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground whitespace-nowrap">Articles</span>
                                  <div className="flex-1 h-px bg-border" />
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                  {articles.map((doc) => renderDocCard(doc))}
                                </div>
                              </div>
                            )}
                            {bookResults.length > 0 && (
                              <div>
                                <div className="flex items-center gap-2.5 mb-3">
                                  <span className="text-[11px] font-medium uppercase tracking-widest text-muted-foreground whitespace-nowrap">Books</span>
                                  <div className="flex-1 h-px bg-border" />
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                  {bookResults.map((book) => renderBookCard(book))}
                                </div>
                              </div>
                            )}
                          </div>
                        </>
                      ) : (
                        <>
                          <p className="text-xs text-muted-foreground mb-4">{totalCount} result{totalCount !== 1 ? "s" : ""}</p>
                          <div className={cn(contentFilter === "books" ? "grid grid-cols-1 sm:grid-cols-2" : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3", "gap-3")}>
                            {contentFilter === "books"
                              ? bookResults.map((b) => renderBookCard(b))
                              : docResults.map((d) => renderDocCard(d))}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* ── DISCOVER MODE ───────────────────────────────────────────── */}
              {discoverMode && (
                <div className="flex flex-col gap-12">

                  {/* 1. Featured */}
                  {FEATURED_IDS.length > 0 && featuredDocs.length > 0 && (
                    <section>
                      <SectionHeader label="Featured" />
                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                        <div className="lg:col-span-2">
                          <DiscoverDocCard
                            doc={featuredDocs[0]}
                            isHero
                            onClick={() => handleCardClick(featuredDocs[0].id, featuredDocs[0].source_kind)}
                          />
                        </div>
                        {featuredDocs.slice(1, 3).length > 0 && (
                          <div className="flex flex-col gap-3">
                            {featuredDocs.slice(1, 3).map((doc) => (
                              <DiscoverDocCard
                                key={doc.id}
                                doc={doc}
                                onClick={() => handleCardClick(doc.id, doc.source_kind)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    </section>
                  )}

                  {/* 2. Browse by type */}
                  <section>
                    <SectionHeader label="Browse" />
                    <div className="grid grid-cols-3 gap-3">
                      {[
                        { filter: "articles" as ContentFilter, label: "Articles", count: sourceCounts?.magazine_article },
                        { filter: "sermons" as ContentFilter, label: "Sermons", count: sourceCounts?.sermon_transcript },
                        { filter: "books" as ContentFilter, label: "Books", count: sourceCounts?.books },
                      ].map(({ filter, label, count }) => (
                        <button
                          key={filter}
                          onClick={() => handleBrowseTile(filter)}
                          className="flex flex-col rounded-lg border border-border bg-card hover:bg-accent transition-colors p-4 text-left"
                        >
                          {count !== undefined && count !== null ? (
                            <span className="text-2xl font-semibold text-foreground tabular-nums">
                              {count.toLocaleString()}
                            </span>
                          ) : (
                            <span className="text-2xl font-semibold text-foreground">—</span>
                          )}
                          <span className="text-xs text-muted-foreground mt-1">{label}</span>
                        </button>
                      ))}
                    </div>
                  </section>

                  {/* 3. Featured authors */}
                  <section>
                    <SectionHeader label="Authors" href="/library/authors" linkLabel="See all →" />
                    <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-none">
                      {AUTHOR_DATA.map((author) => {
                        const imgSrc = AUTHOR_IMAGES[author.name];
                        const isClassic = CLASSIC_AUTHORS.has(author.name);
                        return (
                          <Link
                            key={author.name}
                            href="/library/authors"
                            className="flex flex-col items-center gap-1.5 flex-shrink-0 group"
                          >
                            {imgSrc && !failedAuthorImages.has(author.name) ? (
                              <Image
                                src={imgSrc}
                                alt={author.name}
                                width={48}
                                height={48}
                                className={cn(
                                  "rounded-full object-cover w-12 h-12 ring-1 ring-white/[0.08] group-hover:ring-primary/50 transition-all",
                                  isClassic && "grayscale"
                                )}
                                onError={() => setFailedAuthorImages((prev) => new Set(prev).add(author.name))}
                              />
                            ) : (
                              <div className="w-12 h-12 rounded-full bg-muted ring-1 ring-white/[0.08] flex items-center justify-center group-hover:ring-primary/50 transition-all">
                                <span className="text-sm font-semibold text-muted-foreground">{getInitials(author.name)}</span>
                              </div>
                            )}
                            <span className="text-[11px] text-muted-foreground text-center max-w-[64px] leading-tight group-hover:text-foreground transition-colors">
                              {author.name.split(" ").pop()}
                            </span>
                          </Link>
                        );
                      })}
                    </div>
                  </section>

                  {/* 4. Recently added */}
                  {(recentDocs.length > 0 || discoverLoading) && (
                    <section>
                      <SectionHeader label="Recently Added" />
                      {discoverLoading ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                          {[1, 2, 3].map((i) => (
                            <div key={i} className="rounded-lg border border-border bg-card p-4 h-28 animate-pulse" />
                          ))}
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                          {recentDocs.map((doc) => (
                            <DiscoverDocCard
                              key={doc.id}
                              doc={doc}
                              onClick={() => handleCardClick(doc.id, doc.source_kind)}
                            />
                          ))}
                        </div>
                      )}
                    </section>
                  )}

                  {/* 5. From the New Wine archive */}
                  {(magazineDocs.length > 0 || discoverLoading) && (
                    <section>
                      <SectionHeader
                        label="From the New Wine Archive"
                        href="/library?browse=magazine"
                      />
                      <p className="text-xs text-muted-foreground mb-4 -mt-2">
                        New Wine Magazine · Charismatic renewal teaching, 1970s–80s
                      </p>
                      {discoverLoading ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                          {[1, 2, 3].map((i) => (
                            <div key={i} className="rounded-lg border border-border bg-card p-4 h-28 animate-pulse" />
                          ))}
                        </div>
                      ) : (
                        <>
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                            {magazineDocs.map((doc) => (
                              <button
                                key={doc.id}
                                onClick={() => handleCardClick(doc.id, doc.source_kind)}
                                className="flex flex-col text-left rounded-lg border border-border bg-card hover:bg-accent transition-colors p-4"
                              >
                                {doc.author && (
                                  <p className="text-xs text-muted-foreground">{doc.author}</p>
                                )}
                                <h3 className="text-sm font-semibold text-foreground leading-snug mt-1">{doc.title}</h3>
                                {doc.description && (
                                  <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2 leading-relaxed italic">{doc.description}</p>
                                )}
                                {doc.topic_tags && doc.topic_tags.length > 0 && (
                                  <div className="flex flex-wrap gap-1.5 mt-2">
                                    {doc.topic_tags.slice(0, 2).map((tag) => (
                                      <span key={tag} className="text-[10px] bg-secondary text-secondary-foreground rounded-md px-1.5 py-0.5">
                                        {tag}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {doc.year && <p className="text-[11px] text-muted-foreground mt-auto pt-2">{doc.year}</p>}
                              </button>
                            ))}
                          </div>
                          <button
                            onClick={() => handleBrowseTile("articles")}
                            className="mt-4 text-sm text-primary underline-offset-4 hover:underline"
                          >
                            Browse all articles →
                          </button>
                        </>
                      )}
                    </section>
                  )}

                  {/* 6. Recent pastors' notes */}
                  {(recentNotes.length > 0 || discoverLoading) && (
                    <section>
                      <SectionHeader label="Pastors' Notes" />
                      {discoverLoading ? (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {[1, 2].map((i) => (
                            <div key={i} className="rounded-lg border border-border bg-card p-4 h-24 animate-pulse" />
                          ))}
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          {recentNotes.map((note) => (
                            <PastorsNoteCard key={note.id} note={note} />
                          ))}
                        </div>
                      )}
                    </section>
                  )}

                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Unified filter sheet (desktop + mobile) */}
      <Sheet open={filtersOpen} onOpenChange={(open) => { if (!open) setFiltersOpen(false); }}>
        <SheetContent
          side={isMobile ? "bottom" : "right"}
          className={isMobile
            ? "h-[85vh] overflow-y-auto rounded-t-xl p-0 bg-popover"
            : "w-80 max-w-80 p-0 bg-popover"}
          showCloseButton={true}
        >
          <div className="px-5 pt-5 pb-8 flex flex-col gap-6">
            <h2 className="font-sans text-lg font-semibold text-foreground">Filters</h2>

            {/* Authors */}
            <div>
              <h3 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-3">Authors</h3>
              <div className="flex flex-col gap-2">
                {AUTHOR_DATA.map((author) => {
                  const isSelected = draftAuthors.includes(author.name);
                  return (
                    <button
                      key={author.name}
                      onClick={() => setDraftAuthors((prev) => isSelected ? prev.filter((a) => a !== author.name) : [...prev, author.name])}
                      className={cn(
                        "flex items-center justify-between rounded-lg px-3 py-2.5 border transition-colors min-h-[44px] text-left",
                        isSelected ? "bg-muted border-primary text-foreground" : "bg-card border-border text-muted-foreground hover:bg-accent"
                      )}
                    >
                      <span className="text-sm">{author.name}</span>
                      <span className="text-[11px] text-muted-foreground">{author.years}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Era */}
            <div>
              <h3 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-3">Era</h3>
              <div className="flex gap-2">
                {(["", "classic", "contemporary"] as const).map((era) => (
                  <button
                    key={era}
                    onClick={() => setDraftEra(era)}
                    className={cn(
                      "flex-1 min-h-[44px] rounded-lg px-3 py-2 text-sm border transition-colors",
                      draftEra === era ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border text-muted-foreground hover:bg-accent"
                    )}
                  >
                    {era === "" ? "All" : era === "classic" ? "Classic" : "Contemporary"}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={() => {
                setSelectedAuthors(draftAuthors);
                setEraFilter(draftEra);
                setFiltersOpen(false);
                if (!discoverMode) {
                  fetchResults(query);
                }
              }}
              className="w-full min-h-[44px] rounded-lg bg-primary text-primary-foreground text-sm font-medium transition-colors hover:bg-primary/90"
            >
              Apply Filters
            </button>
          </div>
        </SheetContent>
      </Sheet>

      {showLogin && (
        <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />
      )}
    </div>
  );
}
