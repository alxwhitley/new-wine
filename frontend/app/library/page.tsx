"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { Search, ArrowLeft, Loader2, Menu } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";
import { searchDocumentsFts, browseDocuments, getArticle } from "@/lib/api";
import type { DocumentSearchResult, ArticleResponse } from "@/lib/api";

type Tab = "articles" | "authors" | "sermons" | "books";

const TABS: { key: Tab; label: string }[] = [
  { key: "articles", label: "Articles" },
  { key: "authors", label: "Authors" },
  { key: "sermons", label: "Sermons" },
  { key: "books", label: "Books" },
];

const SEARCH_SUGGESTIONS = [
  "Hearing God's Voice",
  "Identity in Christ",
  "Renewing the Mind",
];


const AUTHORS = [
  { name: "Derek Prince", years: "1915\u20132003", bio: "Cambridge-educated philosopher turned Bible teacher, Prince founded Derek Prince Ministries after a wartime conversion and became one of the most widely translated charismatic teachers of the 20th century, known especially for his work on deliverance, healing, and the Holy Spirit." },
  { name: "Bob Mumford", years: "b. 1930", bio: "Bible teacher and co-founder of New Wine Magazine, Mumford is known for his Kingdom of God teaching and his role in the charismatic renewal, still living and ministering through Lifechangers." },
  { name: "Ern Baxter", years: "1914\u20131993", bio: "Canadian Pentecostal preacher regarded as one of the greatest orators of the 20th century, Baxter served as Bible teacher for William Branham\u2019s crusades and delivered his landmark \u201cThy Kingdom Come\u201d message to 5,000 leaders in Kansas City." },
  { name: "Charles Simpson", years: "1937\u20132024", bio: "Baptist-turned-charismatic pastor from Mobile, Alabama who co-founded New Wine Magazine in 1969 and became a key leader in the charismatic renewal, known for his pastoral teaching on covenant community and spiritual authority." },
  { name: "Don Basham", years: "1926\u20131989", bio: "Bible teacher and author who pioneered deliverance ministry in the charismatic movement, Basham served as editor of New Wine Magazine from 1975\u20131981 and was known for his accessible writing on the Holy Spirit and spiritual warfare." },
  { name: "John Bevere", years: "b. 1959", bio: "Co-founder of Messenger International and bestselling author of The Bait of Satan and The Awe of God, Bevere is known globally for his bold teachings on the fear of the Lord, spiritual authority, and uncompromising discipleship." },
  { name: "Michael Brown", years: "b. 1955", bio: "Scholar, apologist, and radio host with a PhD from NYU, Brown is a leading charismatic voice on the Jewish roots of Christianity, revival, and cultural apologetics, and has authored over 40 books." },
  { name: "Jack Deere", years: "b. 1948", bio: "Former Dallas Seminary professor of Old Testament who became a charismatic theologian after encountering the gifts through John Wimber; best known for Surprised by the Power of the Spirit, a landmark defense of continuationism." },
  { name: "Oswald J. Smith", years: "1889\u20131986", bio: "Canadian pastor, hymn writer, and missions statesman who founded The People\u2019s Church in Toronto; preached 12,000 sermons in 80 countries and was described by Billy Graham as \u201cthe greatest missionary statesman of our time.\u201d" },
];

function sourceKindForTab(tab: Tab): string | null {
  if (tab === "articles") return "magazine_article";
  if (tab === "sermons") return "sermon_transcript";
  return null;
}

function sourceBadge(tab: Tab, year?: number | null): string {
  if (tab === "sermons") return `Sermon${year ? ` | ${year}` : ""}`;
  return `Magazine Article${year ? ` | ${year}` : ""}`;
}

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

  const [activeTab, setActiveTab] = useState<Tab>("articles");

  // Search state
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentSearchResult[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const searchBarRef = useRef<HTMLDivElement>(null);

  // Browse state — articles
  const [articleBrowse, setArticleBrowse] = useState<DocumentSearchResult[]>([]);
  const [articleBrowseLoading, setArticleBrowseLoading] = useState(true);

  // Browse state — sermons
  const [sermonBrowse, setSermonBrowse] = useState<DocumentSearchResult[]>([]);
  const [sermonBrowseLoading, setSermonBrowseLoading] = useState(true);
  const [sermonBrowseLoaded, setSermonBrowseLoaded] = useState(false);

  // Article reader state
  const [article, setArticle] = useState<ArticleResponse | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);

  // Load articles on mount
  useEffect(() => {
    browseDocuments({ source_kind: "magazine_article", include_copyrighted: true })
      .then((res) => setArticleBrowse(res.results))
      .catch(() => {})
      .finally(() => setArticleBrowseLoading(false));
  }, []);

  // Load sermons when tab first activated
  useEffect(() => {
    if (activeTab === "sermons" && !sermonBrowseLoaded) {
      setSermonBrowseLoading(true);
      browseDocuments({ source_kind: "sermon_transcript", include_copyrighted: true })
        .then((res) => setSermonBrowse(res.results))
        .catch(() => {})
        .finally(() => {
          setSermonBrowseLoading(false);
          setSermonBrowseLoaded(true);
        });
    }
  }, [activeTab, sermonBrowseLoaded]);

  // Dismiss suggestions on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchBarRef.current && !searchBarRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Reset search state on tab change
  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab);
    setQuery("");
    setResults([]);
    setCount(null);
    setHasSearched(false);
    setError(null);
    setArticle(null);
    setShowSuggestions(false);
  }, []);

  const doSearch = useCallback(async (q: string, tab: Tab) => {
    const kind = sourceKindForTab(tab);
    if (!kind || !q.trim()) return;
    setSearching(true);
    setError(null);
    setArticle(null);
    setHasSearched(true);
    try {
      const res = await searchDocumentsFts({
        q: q.trim(),
        source_kind: kind,
        include_copyrighted: true,
      });
      setResults(res.results);
      setCount(res.count);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  }, []);

  const handleSearch = useCallback(() => {
    doSearch(query, activeTab);
  }, [query, activeTab, doSearch]);

  const handleSuggestionClick = useCallback((text: string) => {
    setQuery(text);
    setShowSuggestions(false);
    doSearch(text, activeTab);
  }, [activeTab, doSearch]);

  const handleCardClick = useCallback(async (id: string) => {
    setArticleLoading(true);
    setError(null);
    try {
      const data = await getArticle(id);
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

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        setShowSuggestions(false);
        handleSearch();
      }
    },
    [handleSearch],
  );

  // Shared card renderer
  const renderDocCard = (doc: DocumentSearchResult, tab: Tab) => (
    <button
      key={doc.id}
      onClick={() => handleCardClick(doc.id)}
      className="group flex flex-col text-left rounded-lg border border-border p-4 transition-colors hover:border-gold/40"
      style={{ backgroundColor: "#2a2a27" }}
    >
      <h3 className="font-serif text-lg text-foreground group-hover:text-citation transition-colors leading-snug">
        {doc.title}
      </h3>
      {doc.author && (
        <p className="text-xs text-muted-foreground mt-1">{doc.author}</p>
      )}
      <div className="flex flex-wrap gap-1.5 mt-2">
        <span
          className="inline-block rounded-full px-2 py-0.5 text-[11px] font-medium"
          style={{ backgroundColor: "#3c3c38", color: "#c1c1b8" }}
        >
          {sourceBadge(tab, doc.year)}
        </span>
      </div>
      {doc.highlighted_snippet && (
        <p
          className="text-sm text-muted-foreground mt-2 line-clamp-2 [&_mark]:bg-transparent [&_mark]:text-[#d4b96a] [&_mark]:font-semibold"
          dangerouslySetInnerHTML={{
            __html: doc.highlighted_snippet.replace(/<(?!\/?mark\b)[^>]*>/gi, ""),
          }}
        />
      )}
      {doc.topic_tags && doc.topic_tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {doc.topic_tags.map((tag) => (
            <span
              key={tag}
              className="inline-block rounded-full px-2 py-0.5 text-[11px] font-medium"
              style={{ backgroundColor: "rgba(212, 185, 106, 0.12)", color: "#d4b96a" }}
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </button>
  );

  // Article reader view
  if (article) {
    return (
      <div className="flex h-screen bg-background">
        <Sidebar
          conversations={conversations}
          activeConversationId={null}
          isLoggedIn={!!user}
          user={user}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewChat={() => { window.location.href = "/"; }}
          onSelectConversation={(id) => { window.location.href = `/?c=${id}`; }}
          onDeleteConversation={deleteConversation}
          onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
          onSignOut={signOut}
        />
        <main className="md:ml-64 flex flex-1 flex-col min-w-0 h-screen">
          <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
            <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="md:hidden flex-1 text-center font-serif text-lg font-semibold text-foreground">Rhemata</h1>
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
              <h1 className="font-serif text-2xl font-semibold text-foreground leading-tight">{article.title}</h1>
              {article.author && <p className="text-sm text-muted-foreground mt-2">{article.author}</p>}
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
              <div className="prose prose-invert max-w-none">
                <ReactMarkdown>
                  {article.content.replace(/^#\s+[^\n]*\n?/, "").replace(/^\*by\s+[^\n]*\n?/, "").trimStart()}
                </ReactMarkdown>
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

  // Determine browse data for current tab
  const currentBrowse = activeTab === "articles" ? articleBrowse : activeTab === "sermons" ? sermonBrowse : [];
  const currentBrowseLoading = activeTab === "articles" ? articleBrowseLoading : activeTab === "sermons" ? sermonBrowseLoading : false;
  const showSearch = activeTab !== "authors" && activeTab !== "books";

  return (
    <div className="flex h-screen bg-background">
      <Sidebar
        conversations={conversations}
        activeConversationId={null}
        isLoggedIn={!!user}
        user={user}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { window.location.href = "/"; }}
        onSelectConversation={(id) => { window.location.href = `/?c=${id}`; }}
        onDeleteConversation={deleteConversation}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
        onSignOut={signOut}
      />

      <main className="md:ml-64 flex flex-1 flex-col min-w-0 h-screen">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="md:hidden flex-1 text-center font-serif text-lg font-semibold text-foreground">Rhemata</h1>
          <div className="md:hidden min-w-[44px]" />
          <div className="hidden md:flex ml-auto">
            <AuthButton user={user} onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }} onSignOut={signOut} />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-4 md:px-6 pt-12 pb-16">
            {/* Page heading */}
            <h2 className="font-serif text-2xl md:text-3xl font-semibold text-foreground text-center mb-6">
              Library
            </h2>

            {/* Tabs */}
            <div className="flex justify-center gap-6 mb-8 border-b border-border">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => handleTabChange(tab.key)}
                  className="relative pb-3 text-sm font-medium transition-colors cursor-pointer"
                  style={{ color: activeTab === tab.key ? "#e6e6e6" : "#c1c1b8" }}
                  onMouseEnter={(e) => { if (activeTab !== tab.key) e.currentTarget.style.color = "#e6e6e6"; }}
                  onMouseLeave={(e) => { if (activeTab !== tab.key) e.currentTarget.style.color = "#c1c1b8"; }}
                >
                  {tab.label}
                  {activeTab === tab.key && (
                    <span
                      className="absolute bottom-0 left-0 right-0 h-[2px] rounded-full"
                      style={{ backgroundColor: "#b49238" }}
                    />
                  )}
                </button>
              ))}
            </div>

            {/* Search bar — hidden on Authors and Books tabs */}
            {showSearch && (
              <div className="relative mb-8" ref={searchBarRef}>
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
                    onClick={() => { setShowSuggestions(false); handleSearch(); }}
                    disabled={searching || !query.trim()}
                    className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-gold-hover transition-colors disabled:opacity-50"
                  >
                    <Search className="h-4 w-4" />
                    <span className="hidden sm:inline">Search</span>
                  </button>
                </div>

                {/* Suggestions dropdown */}
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
            )}

            {/* Error */}
            {error && <p className="text-sm text-red-400 mt-4 text-center">{error}</p>}

            {/* ── Articles tab ── */}
            {activeTab === "articles" && (
              <>
                {/* Author cards */}
                {!hasSearched && (
                  <div className="mb-8">
                    <h3
                      className="text-xs font-medium uppercase tracking-wider mb-4"
                      style={{ color: "#c1c1b8", fontFamily: "Inter, sans-serif", letterSpacing: "0.08em" }}
                    >
                      Browse by Author
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                      {AUTHORS.map((author) => (
                        <div
                          key={author.name}
                          className="rounded-lg p-5 transition-colors"
                          style={{ backgroundColor: "#262624", border: "1px solid #3c3c38" }}
                          onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.12)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; }}
                        >
                          <h4 className="font-serif text-lg font-semibold text-foreground leading-snug">{author.name}</h4>
                          <p className="text-xs mt-0.5" style={{ color: "#888780" }}>{author.years}</p>
                          <p className="text-sm mt-2 leading-relaxed" style={{ color: "#c1c1b8", fontFamily: "Inter, sans-serif" }}>{author.bio}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Search results */}
                {searching && (
                  <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>
                )}
                {!searching && hasSearched && count !== null && (
                  <div className="mt-4">
                    {results.length === 0 ? (
                      <p className="text-center text-muted-foreground mt-12">No results found</p>
                    ) : (
                      <>
                        <p className="text-xs text-muted-foreground mb-4">{count} result{count !== 1 ? "s" : ""}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {results.map((doc) => renderDocCard(doc, "articles"))}
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* Browse listing */}
                {!searching && !hasSearched && (
                  <div className="mt-4">
                    {articleBrowseLoading ? (
                      <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>
                    ) : articleBrowse.length === 0 ? (
                      <p className="text-center text-muted-foreground mt-12">No articles yet</p>
                    ) : (
                      <>
                        <p className="text-xs text-muted-foreground mb-4">{articleBrowse.length} article{articleBrowse.length !== 1 ? "s" : ""}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {articleBrowse.map((doc) => renderDocCard(doc, "articles"))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </>
            )}

            {/* ── Authors tab ── */}
            {activeTab === "authors" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {AUTHORS.map((author) => (
                  <div
                    key={author.name}
                    className="rounded-lg p-5 transition-colors"
                    style={{ backgroundColor: "#262624", border: "1px solid #3c3c38" }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.12)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; }}
                  >
                    <h4 className="font-serif text-lg font-semibold text-foreground leading-snug">{author.name}</h4>
                    <p className="text-xs mt-0.5" style={{ color: "#888780" }}>{author.years}</p>
                    <p className="text-sm mt-2 leading-relaxed" style={{ color: "#c1c1b8", fontFamily: "Inter, sans-serif" }}>{author.bio}</p>
                  </div>
                ))}
              </div>
            )}

            {/* ── Sermons tab ── */}
            {activeTab === "sermons" && (
              <>
                {searching && (
                  <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>
                )}
                {!searching && hasSearched && count !== null && (
                  <div className="mt-4">
                    {results.length === 0 ? (
                      <p className="text-center text-muted-foreground mt-12">No results found</p>
                    ) : (
                      <>
                        <p className="text-xs text-muted-foreground mb-4">{count} result{count !== 1 ? "s" : ""}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {results.map((doc) => renderDocCard(doc, "sermons"))}
                        </div>
                      </>
                    )}
                  </div>
                )}
                {!searching && !hasSearched && (
                  <div className="mt-4">
                    {sermonBrowseLoading ? (
                      <div className="flex justify-center mt-12"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>
                    ) : sermonBrowse.length === 0 ? (
                      <p className="text-center text-muted-foreground mt-12">No sermons yet</p>
                    ) : (
                      <>
                        <p className="text-xs text-muted-foreground mb-4">{sermonBrowse.length} sermon{sermonBrowse.length !== 1 ? "s" : ""}</p>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                          {sermonBrowse.map((doc) => renderDocCard(doc, "sermons"))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </>
            )}

            {/* ── Books tab ── */}
            {activeTab === "books" && (
              <div className="flex justify-center mt-16">
                <p className="text-sm" style={{ color: "#c1c1b8" }}>Books coming soon.</p>
              </div>
            )}
          </div>
        </div>
      </main>

      {showLogin && (
        <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />
      )}
    </div>
  );
}
