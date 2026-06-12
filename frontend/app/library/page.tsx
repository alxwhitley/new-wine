"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import Link from "next/link";
import Image from "next/image";
import { Search, ArrowLeft, Loader2, Menu, ChevronDown, Trash2, Pencil } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";
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
  "Hearing God\u2019s Voice",
  "Identity in Christ",
  "Renewing the Mind",
];

const AUTHOR_IMAGES: Record<string, string> = {
  "Derek Prince": "/images/authors/derek-prince.jpg",
  "Bob Mumford": "/images/authors/bob-mumford.jpg",
  "Ern Baxter": "/images/authors/ern-baxter.jpg",
  "Charles Simpson": "/images/authors/charles-simpson.jpg",
  "Don Basham": "/images/authors/don-basham.jpg",
  "Oswald J. Smith": "/images/authors/oswald-smith.jpg",
  "John Bevere": "/images/authors/john-bevere.jpg",
  "Michael Brown": "/images/authors/michael-brown.jpg",
  "Jack Deere": "/images/authors/jack-deere.jpg",
};

const CLASSIC_AUTHORS = new Set(["Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson", "Don Basham", "Oswald J. Smith"]);

function getInitials(name: string) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

const BOOK_COVERS: Record<string, string> = {
  "Blessing or Curse: You Can Choose": "/images/books/blessing-or-curse.jpg",
  "They Shall Expel Demons": "/images/books/they-shall-expel-demons.jpg",
  "Shaping History Through Prayer and Fasting": "/images/books/shaping-history-prayer-fasting.jpg",
  "Spiritual Warfare": "/images/books/spiritual-warfare.jpg",
  "Foundational Truths for Christian Living": "/images/books/foundational-truths.jpg",
  "God's Medicine Bottle": "/images/books/gods-medicine-bottle.jpg",
  "Holy Spirit in You": "/images/books/holy-spirit-in-you.jpg",
  "Agape Road": "/images/books/agape-road.jpg",
  "Take Another Look at Guidance": "/images/books/take-another-look-at-guidance.jpg",
  "The Purpose of Temptation": "/images/books/purpose-of-temptation.jpg",
  "The King and You": "/images/books/the-king-and-you.jpg",
  "Fifteen Steps Out": "/images/books/fifteen-steps-out.jpg",
  "Thy Kingdom Come": "/images/books/thy-kingdom-come.jpg",
  "The Challenge to Care": "/images/books/the-challenge-to-care.jpg",
  "Courageous Living": "/images/books/courageous-living.jpg",
  "Straight Answers to 21 Honest Questions About Prayer": "/images/books/straight-answers-prayer.jpg",
  "Face Up with a Miracle": "/images/books/face-up-with-a-miracle.jpg",
  "Deliver Us from Evil": "/images/books/deliver-us-from-evil.jpg",
  "A Handbook on Holy Spirit Baptism": "/images/books/handbook-holy-spirit-baptism.jpg",
  "True and False Prophets": "/images/books/true-and-false-prophets.jpg",
  "The Bait of Satan": "/images/books/bait-of-satan.jpg",
  "Under Cover": "/images/books/under-cover.jpg",
  "Driven by Eternity": "/images/books/driven-by-eternity.jpg",
  "Good or God?": "/images/books/good-or-god.jpg",
  "The Awe of God": "/images/books/awe-of-god.jpg",
  "Killing Kryptonite": "/images/books/killing-kryptonite.jpg",
  "Our Hands Are Stained with Blood": "/images/books/our-hands-are-stained.jpg",
  "Answering Jewish Objections to Jesus": "/images/books/answering-jewish-objections.jpg",
  "Whatever Happened to the Power of God?": "/images/books/whatever-happened-power-of-god.jpg",
  "Authentic Fire": "/images/books/authentic-fire.jpg",
  "Hyper-Grace": "/images/books/hyper-grace.jpg",
  "Revolution in the Church": "/images/books/revolution-in-the-church.jpg",
  "Surprised by the Power of the Spirit": "/images/books/surprised-by-power-of-spirit.jpg",
  "Surprised by the Voice of God": "/images/books/surprised-by-voice-of-god.jpg",
  "Even in Our Darkness": "/images/books/even-in-our-darkness.jpg",
  "Why I Am Still Surprised by the Power of the Spirit": "/images/books/still-surprised-by-spirit.jpg",
  "The Passion for Souls": "/images/books/passion-for-souls.jpg",
  "The Man God Uses": "/images/books/the-man-god-uses.jpg",
  "The Enduement of Power": "/images/books/enduement-of-power.jpg",
  "The Revival We Need": "/images/books/the-revival-we-need.jpg",
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
  { name: "Jack Deere", years: "b. 1948", specialty: "Specialised in the continuation of spiritual gifts, prophecy, and hearing God\u2019s voice." },
  { name: "Oswald J. Smith", years: "1889–1986", specialty: "Specialised in evangelism, world missions, and the Spirit-empowered church." },
];

type UnifiedResult =
  | { type: "doc"; data: DocumentSearchResult }
  | { type: "book"; data: Book };

export default function LibraryPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
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
        // Determine source_kind filter
        let sourceKind: string | undefined;
        if (includeArticles && !includeSermons) sourceKind = "magazine_article";
        else if (includeSermons && !includeArticles) sourceKind = "sermon_transcript";
        else sourceKind = undefined; // both — no filter

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

  // Render a doc card
  const renderDocCard = (doc: DocumentSearchResult) => {
    const isNewWine = doc.source_kind !== "sermon_transcript" && (doc.source_name || "").toLowerCase().includes("new wine");
    return (
    <button
      key={doc.id}
      onClick={() => handleCardClick(doc.id, doc.source_kind)}
      className="flex flex-col text-left cursor-pointer"
      style={{ position: "relative", backgroundColor: "#262624", border: "1px solid #3c3c38", borderRadius: "14px", padding: "20px", transition: "background 0.2s ease" }}
      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "#2e2d2b"; }}
      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "#262624"; }}
    >
      <div className="flex items-center gap-2">
        {doc.author && (
          <p style={{ fontSize: "11px", fontWeight: 500, color: "#888880", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {doc.author}
          </p>
        )}
        {isNewWine && (
          <span className="text-xs text-muted-foreground">New Wine Magazine</span>
        )}
      </div>
      <h3 className="font-sans" style={{ fontSize: "17px", fontWeight: 600, color: "#e6e6e0", lineHeight: 1.45, marginTop: "6px" }}>
        {doc.title}
      </h3>
      <div style={{ borderTop: "1px solid #3c3c38", margin: "12px 0" }} />
      {isNewWine && doc.description ? (
        <p className="line-clamp-2" style={{ fontSize: "12px", color: "#c1c1b8", fontStyle: "italic", lineHeight: 1.5 }}>
          {doc.description.length > 150 ? doc.description.slice(0, 150) + "\u2026" : doc.description}
        </p>
      ) : doc.topic_tags && doc.topic_tags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {doc.topic_tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="inline-block"
              style={{ fontSize: "11px", color: "#d4b96a", backgroundColor: "rgba(212, 185, 106, 0.08)", border: "1px solid rgba(212, 185, 106, 0.2)", borderRadius: "20px", padding: "3px 10px" }}
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      {doc.year && (
        <p className="mt-auto" style={{ fontSize: "11px", color: "#555550", paddingTop: "10px" }}>{doc.year}</p>
      )}
      {isAdmin && (
        confirmingDeleteId === doc.id ? (
          <span
            style={{ position: "absolute", bottom: "12px", right: "12px", display: "flex", gap: "8px" }}
            onClick={(e) => e.stopPropagation()}
          >
            {deleteError === doc.id && <span style={{ fontSize: "11px", color: "#e24b4a" }}>Error</span>}
            <button
              onClick={(e) => { e.stopPropagation(); handleDelete(doc.id); }}
              style={{ fontSize: "11px", color: "#e24b4a", cursor: "pointer", background: "none", border: "none", padding: 0 }}
            >
              Delete
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(null); setDeleteError(null); }}
              style={{ fontSize: "11px", color: "#888880", cursor: "pointer", background: "none", border: "none", padding: 0 }}
            >
              Cancel
            </button>
          </span>
        ) : (
          <span
            style={{ position: "absolute", bottom: "12px", right: "12px", display: "flex", gap: "8px", alignItems: "center" }}
            onClick={(e) => e.stopPropagation()}
          >
            <a
              href={`/admin/edit/${doc.id}`}
              onClick={(e) => { e.stopPropagation(); }}
              style={{ cursor: "pointer", display: "flex" }}
            >
              <Pencil
                style={{ width: "14px", height: "14px", color: "#555550", transition: "color 0.15s ease" }}
                onMouseEnter={(e) => { (e.currentTarget as SVGElement).style.color = "#c1c1b8"; }}
                onMouseLeave={(e) => { (e.currentTarget as SVGElement).style.color = "#555550"; }}
              />
            </a>
            <span
              style={{ cursor: "pointer", display: "flex" }}
              onClick={(e) => { e.stopPropagation(); setConfirmingDeleteId(doc.id); }}
            >
              <Trash2
                style={{ width: "14px", height: "14px", color: "#555550", transition: "color 0.15s ease" }}
                onMouseEnter={(e) => { (e.currentTarget as SVGElement).style.color = "#c1c1b8"; }}
                onMouseLeave={(e) => { (e.currentTarget as SVGElement).style.color = "#555550"; }}
              />
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
        className="flex flex-row"
        style={{ backgroundColor: "#262624", border: "1px solid #3c3c38", borderRadius: "14px", padding: "20px", gap: "14px", transition: "background 0.2s ease" }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "#2e2d2b"; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "#262624"; }}
      >
        {coverSrc ? (
          <Image
            src={coverSrc}
            alt={book.title}
            width={56}
            height={80}
            className="object-cover flex-shrink-0"
            style={{ width: "56px", height: "80px", borderRadius: "4px", boxShadow: "0 2px 8px rgba(0,0,0,0.4)" }}
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              img.style.display = "none";
              img.nextElementSibling?.classList.remove("hidden");
            }}
          />
        ) : null}
        <div
          className={coverSrc ? "hidden" : ""}
          style={{ width: "56px", height: "80px", borderRadius: "4px", backgroundColor: "#2a2926", flexShrink: 0 }}
        />
        <div className="flex flex-col min-w-0">
          <p style={{ fontSize: "11px", fontWeight: 500, color: "#888880", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {book.author}
          </p>
          <h4 className="font-sans" style={{ fontSize: "17px", fontWeight: 600, color: "#e6e6e0", lineHeight: 1.45, marginTop: "6px" }}>
            {book.title}
          </h4>
          <div style={{ borderTop: "1px solid #3c3c38", margin: "12px 0" }} />
          {book.description && (
            <p className="line-clamp-2" style={{ fontSize: "13px", color: "#c1c1b8", lineHeight: 1.6 }}>
              {book.description}
            </p>
          )}
          {book.document_id && (
            <a
              href={`/library/book/${book.document_id}`}
              onClick={(e) => e.stopPropagation()}
              className="text-xs text-center transition-colors"
              style={{ border: "1px solid #3c3c38", color: "#c1c1b8", borderRadius: "6px", padding: "6px 10px", marginTop: "12px", display: "block", width: "100%" }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255,255,255,0.15)"; e.currentTarget.style.color = "#e6e6e0"; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; e.currentTarget.style.color = "#c1c1b8"; }}
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
        <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2">
          <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
            <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
            <div className="md:hidden min-w-[44px]" />
            <div className="hidden md:flex ml-auto">
              <AuthButton user={user} onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }} onSignOut={signOut} />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-2xl px-4 md:px-6 pt-8 pb-16">
              <button
                onClick={handleBackToResults}
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-gold transition-colors mb-8 min-h-[44px]"
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
                    className="shrink-0 rounded px-3 py-1 text-sm transition-colors"
                    style={{ border: "1px solid #3c3c38", color: "#c1c1b8" }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.2)"; e.currentTarget.style.color = "#e6e6e6"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; e.currentTarget.style.color = "#c1c1b8"; }}
                  >
                    Visit Original Source
                  </a>
                )}
              </div>
              {article.issue && (
                <p className="text-xs mt-1" style={{ color: "#c1c1b8" }}>
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
                <p className="text-sm italic mb-6" style={{ color: "#c1c1b8" }}>
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

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
          <div className="md:hidden min-w-[44px]" />
          <div className="hidden md:flex ml-auto">
            <AuthButton user={user} onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }} onSignOut={signOut} />
          </div>
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
                  className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
                />
                <button
                  onClick={handleSearch}
                  disabled={loading}
                  className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-gold-hover transition-colors disabled:opacity-50"
                >
                  <Search className="h-4 w-4" />
                  <span className="hidden sm:inline">Search</span>
                </button>
              </div>

              {showSuggestions && (
                <div
                  className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-border p-3 z-20"
                  style={{ backgroundColor: "#2a2a27" }}
                >
                  <p className="text-[11px] uppercase tracking-wider mb-2" style={{ color: "#888780", fontFamily: "Inter, sans-serif" }}>
                    Suggested topics
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {SEARCH_SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        onClick={() => handleSuggestionClick(s)}
                        className="rounded-full px-3 py-1 text-xs font-medium transition-colors cursor-pointer"
                        style={{
                          color: "#d4b96a",
                          backgroundColor: "rgba(212, 185, 106, 0.12)",
                          border: "1px solid rgba(212, 185, 106, 0.25)",
                        }}
                        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(212, 185, 106, 0.22)"; }}
                        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "rgba(212, 185, 106, 0.12)"; }}
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
              {/* Author filter trigger + panel */}
              <div className="relative" ref={authorPanelRef}>
                <button
                  onClick={() => setAuthorPanelOpen(!authorPanelOpen)}
                  className="min-h-[36px] text-sm cursor-pointer flex items-center"
                  style={{ border: "1px solid #3c3c38", backgroundColor: "#262624", color: "#c1c1b8", borderRadius: "8px", padding: "8px 12px", gap: "6px" }}
                >
                  {selectedAuthors.length === 0
                    ? "All Authors"
                    : selectedAuthors.length === 1
                      ? selectedAuthors[0]
                      : `${selectedAuthors.length} Authors Selected`}
                  <ChevronDown
                    style={{ width: "14px", height: "14px", color: "#888880", transition: "transform 0.2s ease", transform: authorPanelOpen ? "rotate(180deg)" : "rotate(0deg)" }}
                  />
                </button>

                {authorPanelOpen && (
                  <div
                    className="absolute left-0 top-full mt-2 z-30 flex flex-col"
                    style={{ width: "320px", height: "360px", backgroundColor: "#1f1e1d", border: "1px solid #3c3c38", borderRadius: "12px", padding: "12px" }}
                  >
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
                            className="text-left cursor-pointer transition-colors flex flex-row items-center"
                            style={{
                              backgroundColor: isSelected ? "#2a2926" : "#262624",
                              border: isSelected ? "1px solid #b49238" : "1px solid #3c3c38",
                              borderRadius: "8px",
                              padding: "10px 14px",
                              gap: "12px",
                            }}
                            onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "#2e2d2b"; }}
                            onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = "#262624"; }}
                          >
                            {imgSrc && !failedAuthorImages.has(author.name) ? (
                              <Image
                                src={imgSrc}
                                alt={author.name}
                                width={40}
                                height={40}
                                className="rounded-full object-cover flex-shrink-0"
                                style={{ width: "40px", height: "40px", boxShadow: "0 0 0 1px rgba(255,255,255,0.08)", filter: isClassic ? "grayscale(100%)" : "none" }}
                                onError={() => setFailedAuthorImages((prev) => new Set(prev).add(author.name))}
                              />
                            ) : (
                              <div
                                style={{ width: "40px", height: "40px", borderRadius: "50%", backgroundColor: "#2a2926", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                              >
                                <span style={{ fontSize: "14px", fontWeight: 600, color: "#888880" }}>{getInitials(author.name)}</span>
                              </div>
                            )}
                            <div className="flex flex-col min-w-0">
                              <p className="font-sans" style={{ fontSize: "14px", color: "#e6e6e0" }}>{author.name}</p>
                              <p style={{ fontSize: "11px", color: "#888880", marginTop: "2px" }}>{author.years}</p>
                              <p style={{ fontSize: "12px", color: "#c1c1b8", fontStyle: "italic", marginTop: "4px", lineHeight: 1.5 }}>{author.specialty}</p>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Era dropdown */}
              <div className="relative flex items-center">
                <select
                  value={eraFilter}
                  onChange={(e) => setEraFilter(e.target.value)}
                  className="min-h-[36px] text-sm cursor-pointer focus:outline-none appearance-none"
                  style={{ border: "1px solid #3c3c38", backgroundColor: "#262624", color: "#c1c1b8", borderRadius: "8px", padding: "8px 30px 8px 12px" }}
                >
                  <option value="">All Eras</option>
                  <option value="classic">Classic</option>
                  <option value="contemporary">Contemporary</option>
                </select>
                <ChevronDown
                  style={{ position: "absolute", right: "10px", width: "14px", height: "14px", color: "#888880", pointerEvents: "none" }}
                />
              </div>

              {/* Explore Authors link */}
              <Link
                href="/library/authors"
                className="ml-auto min-h-[36px] rounded-lg px-3 flex items-center text-sm transition-colors"
                style={{ border: "1px solid #3c3c38", color: "#c1c1b8" }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.2)"; e.currentTarget.style.color = "#e6e6e0"; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; e.currentTarget.style.color = "#c1c1b8"; }}
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
              <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>
            )}

            {/* Results */}
            {!loading && (
              <div className="mt-2">
                {totalCount === 0 ? (
                  <p className="text-center text-muted-foreground mt-12">No results found</p>
                ) : contentFilter === "all" ? (
                  <>
                    <p className="text-xs text-muted-foreground mb-4">{totalCount} result{totalCount !== 1 ? "s" : ""}</p>
                    <div className="flex flex-col" style={{ gap: "32px" }}>
                      {sermons.length > 0 && (
                        <div>
                          <div className="flex items-center" style={{ gap: "10px", marginBottom: "12px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", color: "#666660", whiteSpace: "nowrap" }}>Sermons</span>
                            <div style={{ flex: 1, height: "1px", backgroundColor: "#2a2926" }} />
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" style={{ gap: "14px" }}>
                            {sermons.map((doc) => renderDocCard(doc))}
                          </div>
                        </div>
                      )}
                      {articles.length > 0 && (
                        <div>
                          <div className="flex items-center" style={{ gap: "10px", marginBottom: "12px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", color: "#666660", whiteSpace: "nowrap" }}>Articles</span>
                            <div style={{ flex: 1, height: "1px", backgroundColor: "#2a2926" }} />
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" style={{ gap: "14px" }}>
                            {articles.map((doc) => renderDocCard(doc))}
                          </div>
                        </div>
                      )}
                      {bookResults.length > 0 && (
                        <div>
                          <div className="flex items-center" style={{ gap: "10px", marginBottom: "12px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", color: "#666660", whiteSpace: "nowrap" }}>Books</span>
                            <div style={{ flex: 1, height: "1px", backgroundColor: "#2a2926" }} />
                          </div>
                          <div className="grid grid-cols-1 sm:grid-cols-2" style={{ gap: "14px" }}>
                            {bookResults.map((book) => renderBookCard(book))}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-xs text-muted-foreground mb-4">{totalCount} result{totalCount !== 1 ? "s" : ""}</p>
                    <div className={contentFilter === "books" ? "grid grid-cols-1 sm:grid-cols-2" : "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"} style={{ gap: "14px" }}>
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

      {showLogin && (
        <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />
      )}
    </div>
  );
}
