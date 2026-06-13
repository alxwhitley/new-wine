"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import Link from "next/link";
import Image from "next/image";
import { Search, ArrowLeft, Loader2, Menu, ChevronDown, Trash2, Pencil, SlidersHorizontal } from "lucide-react";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import LoginModal from "@/components/auth/LoginModal";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { searchDocumentsFts, browseDocuments, getArticle, fetchBooks, deleteDocument } from "@/lib/api";
import type { DocumentSearchResult, ArticleResponse, Book } from "@/lib/api";

type ContentFilter = "all" | "articles" | "sermons" | "books";

const CONTENT_FILTERS: { key: ContentFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "articles", label: "Articles" },
  { key: "sermons", label: "Sermons" },
  { key: "books", label: "Books" },
];

const SEARCH_SUGGESTIONS = [
  "Hearing God’s Voice",
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

function getInitials(name: string) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

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

// Author data for the filter panel
const AUTHOR_DATA = [
  { name: "Derek Prince", years: "1915–2003", specialty: "Specialised in deliverance, spiritual warfare, and foundational Spirit-filled living." },
  { name: "Bob Mumford", years: "b. 1930", specialty: "Specialised in Kingdom of God theology and the Father heart of God." },
  { name: "Ern Baxter", years: "1914–1993", specialty: "Specialised in Kingdom proclamation, worship, and Spirit-empowered preaching." },
  { name: "Charles Simpson", years: "1937–2024", specialty: "Specialised in covenant community, pastoral care, and charismatic church life." },
  { name: "Don Basham", years: "1926–1989", specialty: "Specialised in Holy Spirit baptism, deliverance ministry, and spiritual authority." },
  { name: "John Bevere", years: "b. 1959", specialty: "Specialised in the fear of the Lord, spiritual authority, and uncompromising discipleship." },
  { name: "Michael Brown", years: "b. 1955", specialty: "Specialised in revival, Jewish roots of Christianity, and cultural apologetics." },
  { name: "Jack Deere", years: "b. 1948", specialty: "Specialised in the continuation of spiritual gifts, prophecy, and hearing God’s voice." },
  { name: "Oswald J. Smith", years: "1889–1986", specialty: "Specialised in evangelism, world missions, and the Spirit-empowered church." },
];

type UnifiedResult =
  | { type: "doc"; data: DocumentSearchResult }
  | { type: "book"; data: Book };

export default function LibraryPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const isMobile = useIsMobile();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const {
    conversations,
    deleteConversation,
    loadMessages,
  } = useConversations(user?.id);

  const [failedAuthorImages, setFailedAuthorImages] = useState<Set<string>>(new Set());

  // Search + filter state
  const [query, setQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>([]);
  const [authorPanelOpen, setAuthorPanelOpen] = useState(false);
  const authorPanelRef = useRef<HTMLDivElement>(null);
  const [eraFilter, setEraFilter] = useState("");
  const [contentFilter, setContentFilter] = useState<ContentFilter>("all");

  // Mobile filter sheet state
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const [draftAuthors, setDraftAuthors] = useState<string[]>([]);
  const [draftEra, setDraftEra] = useState("");

  // Results
  const [docResults, setDocResults] = useState<DocumentSearchResult[]>([]);
  const [bookResults, setBookResults] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Article reader
  const [article, setArticle] = useState<ArticleResponse | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);

  // Admin delete
  const isAdmin = user?.id === "1ea99425-08ec-40f2-9ed3-588b88122a82";
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Compute effective era
  const effectiveEra = eraFilter || undefined;

  // Compute comma-separated author string for API
  const authorParam = selectedAuthors.length > 0 ? selectedAuthors.join(",") : undefined;

  // Fetch data on filter change
  const fetchData = useCallback(async (q?: string) => {
    setLoading(true);
    setError(null);
    try {
      const includeArticles = contentFilter === "all" || contentFilter === "articles";
      const includeSermons = contentFilter === "all" || contentFilter === "sermons";
      const includeBooks = contentFilter === "all" || contentFilter === "books";

      const promises: Promise<void>[] = [];
      let newDocs: DocumentSearchResult[] = [];
      let newBooks: Book[] = [];

      if (includeArticles || includeSermons) {
        let sourceKind: string | undefined;
        if (includeArticles && !includeSermons) sourceKind = "magazine_article";
        else if (includeSermons && !includeArticles) sourceKind = "sermon_transcript";
        else sourceKind = undefined;

        if (q && q.trim()) {
          promises.push(
            searchDocumentsFts({
              q: q.trim(),
              source_kind: sourceKind,
              include_copyrighted: true,
              era: effectiveEra,
              author: authorParam,
            }).then((res) => { newDocs = res.results; })
          );
        } else {
          promises.push(
            browseDocuments({
              source_kind: sourceKind,
              include_copyrighted: true,
              era: effectiveEra,
              author: authorParam,
            }).then((res) => { newDocs = res.results; })
          );
        }
      }

      if (includeBooks) {
        promises.push(
          fetchBooks({
            q: q?.trim() || undefined,
            era: effectiveEra,
            author: authorParam,
          }).then((res) => { newBooks = res.results; })
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

  // Initial load + refetch on filter changes
  useEffect(() => {
    fetchData(query);
  }, [contentFilter, effectiveEra, authorParam]); // eslint-disable-line react-hooks/exhaustive-deps

  // Dismiss suggestions / author panel on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchBarRef.current && !searchBarRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
      if (authorPanelRef.current && !authorPanelRef.current.contains(e.target as Node)) {
        setAuthorPanelOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleSearch = useCallback(() => {
    setShowSuggestions(false);
    fetchData(query);
  }, [query, fetchData]);

  const handleSuggestionClick = useCallback((text: string) => {
    setQuery(text);
    setShowSuggestions(false);
    fetchData(text);
  }, [fetchData]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSearch();
      }
    },
    [handleSearch],
  );

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

  const handleBackToResults = useCallback(() => {
    setArticle(null);
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

  // Build unified results
  const unified: UnifiedResult[] = [];
  for (const doc of docResults) {
    unified.push({ type: "doc", data: doc });
  }
  for (const book of bookResults) {
    unified.push({ type: "book", data: book });
  }
  const totalCount = unified.length;

  // Split docs into articles vs sermons for grouped view
  const articles = docResults.filter((d) => d.source_kind !== "sermon_transcript");
  const sermons = docResults.filter((d) => d.source_kind === "sermon_transcript");

  const activeFilterCount = selectedAuthors.length + (eraFilter ? 1 : 0);

  // Render a doc card
  const renderDocCard = (doc: DocumentSearchResult) => {
    const isNewWine = doc.source_kind !== "sermon_transcript" && (doc.source_name || "").toLowerCase().includes("new wine");
    return (
      <button
        key={doc.id}
        onClick={() => handleCardClick(doc.id, doc.source_kind)}
        className="relative flex flex-col text-left cursor-pointer bg-card border border-border rounded-xl p-5 transition-colors hover:bg-accent"
      >
        <div className="flex items-center gap-2">
          {doc.author && (
            <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
              {doc.author}
            </p>
          )}
          {isNewWine && (
            <span className="text-xs text-muted-foreground">New Wine Magazine</span>
          )}
        </div>
        <h3 className="font-sans text-[17px] font-semibold text-foreground leading-snug mt-1.5">
          {doc.title}
        </h3>
        <div className="border-t border-border my-3" />
        {isNewWine && doc.description ? (
          <p className="line-clamp-2 text-xs text-muted-foreground italic leading-relaxed">
            {doc.description.length > 150 ? doc.description.slice(0, 150) + "…" : doc.description}
          </p>
        ) : doc.topic_tags && doc.topic_tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {doc.topic_tags.slice(0, 2).map((tag) => (
              <span
                key={tag}
                className="inline-block text-[11px] text-primary bg-primary/10 border border-primary/20 rounded-full px-2.5 py-0.5"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : null}
        {doc.year && (
          <p className="mt-auto text-[11px] text-muted-foreground pt-2.5">{doc.year}</p>
        )}
        {isAdmin && (
          confirmingDeleteId === doc.id ? (
            <span
              className="absolute bottom-3 right-3 flex gap-2"
              onClick={(e) => e.stopPropagation()}
            >
              {deleteError === doc.id && <span className="text-[11px] text-destructive">Error</span>}
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
                className="text-[11px] text-destructive cursor-pointer bg-transparent border-none p-0"
              >
                Delete
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(null); setDeleteError(null); }}
                className="text-[11px] text-muted-foreground cursor-pointer bg-transparent border-none p-0"
              >
                Cancel
              </button>
            </span>
          ) : (
            <span
              className="absolute bottom-3 right-3 flex gap-2 items-center"
              onClick={(e) => e.stopPropagation()}
            >
              <a
                href={`/admin/edit/${doc.id}`}
                onClick={(e) => { e.stopPropagation(); }}
                className="flex cursor-pointer"
              >
                <Pencil className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground transition-colors" />
              </a>
              <span
                className="flex cursor-pointer"
                onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(doc.id); }}
              >
                <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground transition-colors" />
              </span>
            </span>
          )
        )}
      </button>
    );
  };

  // Render a book card
  const renderBookCard = (book: Book) => {
    const coverSrc = BOOK_COVERS[book.title];
    return (
      <div
        key={book.id}
        className="flex flex-row bg-card border border-border rounded-xl p-5 gap-3.5 transition-colors hover:bg-accent"
      >
        {coverSrc ? (
          <Image
            src={coverSrc}
            alt={book.title}
            width={56}
            height={80}
            className="object-cover flex-shrink-0 rounded-sm shadow-lg w-14 h-20"
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              img.style.display = "none";
              img.nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <div className={cn(coverSrc ? "hidden" : "", "w-14 h-20 rounded-sm bg-muted flex-shrink-0")} />
        <div className="flex flex-col min-w-0">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            {book.author}
          </p>
          <h4 className="font-sans text-[17px] font-semibold text-foreground leading-snug mt-1.5">
            {book.title}
          </h4>
          <div className="border-t border-border my-3" />
          {book.description && (
            <p className="line-clamp-2 text-[13px] text-muted-foreground leading-relaxed">
              {book.description}
            </p>
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

  // Article reader view
  if (article) {
    return (
      <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
        <Sidebar
          conversations={conversations}
          activeConversationId={null}
          isLoggedIn={!!user}
          user={user}
          accessToken={accessToken}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewChat={() => { window.location.href = "/"; }}
          onSelectConversation={(id) => { window.location.href = `/?c=${id}`; }}
          onDeleteConversation={deleteConversation}
          onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
          onSignOut={signOut}
        />
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
                onClick={handleBackToResults}
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
              <div className="prose prose-invert max-w-none">
                <ReactMarkdown>
                  {article.content.replace(/^#\s+[^\n]*\n?/, "").replace(/^\*by\s+[^\n]*\n?/, "").trimStart()}
                </ReactMarkdown>
              </div>
            </div>
          </div>
          </div>
        </main>
        {showLogin && (
          <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />
        )}
      </div>
    );
  }

  return (
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
      <Sidebar
        conversations={conversations}
        activeConversationId={null}
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { window.location.href = "/"; }}
        onSelectConversation={(id) => { window.location.href = `/?c=${id}`; }}
        onDeleteConversation={deleteConversation}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
        onSignOut={signOut}
      />

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
          <div className="md:hidden min-w-[44px]" />
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-4 md:px-6 pt-12 pb-16">
            {/* Page heading */}
            <h2 className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center mb-6">
              Library
            </h2>

            {/* Search bar */}
            <div className="relative mb-4" ref={searchBarRef}>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onFocus={() => setShowSuggestions(true)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search articles, authors, topics..."
                  className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary transition-colors"
                />
                <button
                  onClick={handleSearch}
                  disabled={loading}
                  className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                  <Search className="h-4 w-4" />
                  <span className="hidden sm:inline">Search</span>
                </button>
              </div>

              {showSuggestions && (
                <div className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-border bg-popover p-3 z-20">
                  <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">
                    Suggested topics
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {SEARCH_SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => handleSuggestionClick(s)}
                        className="rounded-full px-3 py-1 text-xs font-medium transition-colors cursor-pointer text-primary bg-primary/10 border border-primary/25 hover:bg-primary/20"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Filter row */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
              {/* Mobile: single Filters button */}
              <button
                onClick={() => {
                  setDraftAuthors(selectedAuthors);
                  setDraftEra(eraFilter);
                  setMobileFiltersOpen(true);
                }}
                className={cn(
                  "md:hidden min-h-[44px] flex items-center gap-2 rounded-lg px-4 text-sm border transition-colors",
                  activeFilterCount > 0 ? "border-primary text-primary" : "border-border text-muted-foreground"
                )}
              >
                <SlidersHorizontal className="h-4 w-4" />
                Filters
                {activeFilterCount > 0 && (
                  <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-primary text-primary-foreground text-[10px] font-medium">
                    {activeFilterCount}
                  </span>
                )}
              </button>

              {/* Desktop: Author filter trigger + panel */}
              <div className="relative hidden md:block" ref={authorPanelRef}>
                <button
                  onClick={() => setAuthorPanelOpen(!authorPanelOpen)}
                  className="min-h-[36px] text-sm cursor-pointer flex items-center gap-1.5 border border-border bg-card text-muted-foreground rounded-lg px-3 py-2"
                >
                  {selectedAuthors.length === 0
                    ? "All Authors"
                    : selectedAuthors.length === 1
                      ? selectedAuthors[0]
                      : `${selectedAuthors.length} Authors Selected`}
                  <ChevronDown
                    className={cn("w-3.5 h-3.5 text-muted-foreground transition-transform", authorPanelOpen && "rotate-180")}
                  />
                </button>

                {authorPanelOpen && (
                  <div className="absolute left-0 top-full mt-2 z-30 flex flex-col w-80 h-[360px] bg-popover border border-border rounded-xl p-3">
                    <div className="flex-1 overflow-y-auto flex flex-col gap-2">
                      {AUTHOR_DATA.map((author) => {
                        const isSelected = selectedAuthors.includes(author.name);
                        const imgSrc = AUTHOR_IMAGES[author.name];
                        const isClassic = CLASSIC_AUTHORS.has(author.name);
                        return (
                          <button
                            key={author.name}
                            onClick={() => {
                              setSelectedAuthors((prev) =>
                                isSelected ? prev.filter((a) => a !== author.name) : [...prev, author.name]
                              );
                            }}
                            className={cn(
                              "text-left cursor-pointer transition-colors flex flex-row items-center rounded-lg px-3.5 py-2.5 gap-3 border",
                              isSelected ? "bg-muted border-primary" : "bg-card border-border hover:bg-accent"
                            )}
                          >
                            {imgSrc && !failedAuthorImages.has(author.name) ? (
                              <Image
                                src={imgSrc}
                                alt={author.name}
                                width={40}
                                height={40}
                                className={cn("rounded-full object-cover flex-shrink-0 w-10 h-10", isClassic && "grayscale")}
                                style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                                onError={() => setFailedAuthorImages((prev) => new Set(prev).add(author.name))}
                              />
                            ) : (
                              <div
                                className="w-10 h-10 rounded-full bg-muted flex items-center justify-center flex-shrink-0"
                                style={{ boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                              >
                                <span className="text-[14px] font-semibold text-muted-foreground">{getInitials(author.name)}</span>
                              </div>
                            )}
                            <div className="flex flex-col min-w-0">
                              <p className="font-sans text-sm text-foreground">{author.name}</p>
                              <p className="text-[11px] text-muted-foreground mt-0.5">{author.years}</p>
                              <p className="text-xs text-muted-foreground italic mt-1 leading-relaxed">{author.specialty}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Desktop: Era dropdown */}
              <div className="relative hidden md:flex items-center">
                <select
                  value={eraFilter}
                  onChange={(e) => setEraFilter(e.target.value)}
                  className="min-h-[36px] text-sm cursor-pointer focus:outline-none appearance-none border border-border bg-card text-muted-foreground rounded-lg px-3 py-2 pr-8"
                >
                  <option value="">All Eras</option>
                  <option value="classic">Classic</option>
                  <option value="contemporary">Contemporary</option>
                </select>
                <ChevronDown className="absolute right-2.5 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
              </div>

              {/* Explore Authors link */}
              <Link
                href="/library/authors"
                className="ml-auto min-h-[36px] rounded-lg px-3 flex items-center text-sm transition-colors border border-border text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                Explore Authors
              </Link>
            </div>

            {/* Content type pills */}
            <div className="flex gap-2 mb-6">
              {CONTENT_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setContentFilter(f.key)}
                  className={cn(
                    "rounded-md px-3 py-1 text-xs font-medium transition-colors cursor-pointer",
                    contentFilter === f.key
                      ? "bg-primary text-primary-foreground"
                      : "border border-border hover:bg-accent"
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {/* Error */}
            {error && <p className="text-sm text-red-400 mt-4 text-center">{error}</p>}

            {/* Loading */}
            {loading && (
              <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-primary animate-spin" /></div>
            )}

            {/* Results */}
            {!loading && (
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
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
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
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
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
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                            {bookResults.map((book) => renderBookCard(book))}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-muted-foreground mb-4">{totalCount} result{totalCount !== 1 ? "s" : ""}</p>
                    <div className={cn(contentFilter === "books" ? "grid grid-cols-1 sm:grid-cols-2" : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3", "gap-3.5")}>
                      {unified.map((item) =>
                        item.type === "doc"
                          ? renderDocCard(item.data)
                          : renderBookCard(item.data)
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
        </div>
      </main>

      {/* Mobile filters bottom sheet */}
      <Sheet open={mobileFiltersOpen} onOpenChange={(open) => { if (!open) setMobileFiltersOpen(false); }}>
        <SheetContent side="bottom" className="h-[85vh] overflow-y-auto rounded-t-xl p-0">
          <div className="px-4 pt-5 pb-8 flex flex-col gap-6">
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
                      onClick={() => {
                        setDraftAuthors((prev) =>
                          isSelected ? prev.filter((a) => a !== author.name) : [...prev, author.name]
                        );
                      }}
                      className={cn(
                        "flex items-center justify-between rounded-lg px-3 py-2.5 border transition-colors min-h-[44px] text-left",
                        isSelected ? "bg-muted border-primary text-foreground" : "bg-card border-border text-muted-foreground"
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
                      draftEra === era ? "bg-primary text-primary-foreground border-primary" : "bg-card border-border text-muted-foreground"
                    )}
                  >
                    {era === "" ? "All" : era === "classic" ? "Classic" : "Contemporary"}
                  </button>
                ))}
              </div>
            </div>

            {/* Apply */}
            <button
              onClick={() => {
                setSelectedAuthors(draftAuthors);
                setEraFilter(draftEra);
                setMobileFiltersOpen(false);
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
