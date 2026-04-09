"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import { Search, ArrowLeft, Loader2, Menu } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";
import { searchDocumentsFts, getArticle } from "@/lib/api";
import type { DocumentSearchResult, ArticleResponse } from "@/lib/api";

export default function SearchPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const {
    conversations,
    deleteConversation,
    loadMessages,
  } = useConversations(user?.id);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DocumentSearchResult[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Article reader state
  const [article, setArticle] = useState<ArticleResponse | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    setArticle(null);
    try {
      const trimmed = query.trim();
      const res = await searchDocumentsFts({
        q: trimmed,
        source_kind: "magazine_article",
        include_copyrighted: true,
      });
      setResults(res.results);
      setCount(res.count);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  }, [query]);

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
        handleSearch();
      }
    },
    [handleSearch],
  );

  const pageContent = article ? (
    // Article reader view
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-4 md:px-6 pt-8 pb-16">
        <button
          onClick={handleBackToResults}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-gold transition-colors mb-8 min-h-[44px]"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to results
        </button>

        <h1 className="font-serif text-2xl font-semibold text-foreground leading-tight">
          {article.title}
        </h1>

        <p className="text-sm text-muted-foreground mt-2">
          {[article.author, article.issue, article.year].filter(Boolean).join(" \u00b7 ")}
        </p>

        <div className="border-t border-border my-6" />

        <div className="prose prose-invert max-w-none">
          <ReactMarkdown>
            {article.content
              .replace(/^#\s+[^\n]*\n?/, "")
              .replace(/^\*by\s+[^\n]*\n?/, "")
              .trimStart()}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  ) : (
    // Search view
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-2xl px-4 md:px-6 pt-12 pb-16">
        {/* Search heading */}
        <h2 className="font-serif text-2xl md:text-3xl font-semibold text-foreground text-center mb-8">
          Search the Library
        </h2>

        {/* Search bar */}
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search articles, authors, topics..."
            className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-gold-hover transition-colors disabled:opacity-50"
          >
            <Search className="h-4 w-4" />
            <span className="hidden sm:inline">Search</span>
          </button>
        </div>

        {/* Error */}
        {error && (
          <p className="text-sm text-red-400 mt-4 text-center">{error}</p>
        )}

        {/* Loading */}
        {searching && (
          <div className="flex justify-center mt-12">
            <Loader2 className="h-6 w-6 text-gold animate-spin" />
          </div>
        )}

        {/* Article loading overlay */}
        {articleLoading && (
          <div className="flex justify-center mt-12">
            <Loader2 className="h-6 w-6 text-gold animate-spin" />
          </div>
        )}

        {/* Results */}
        {!searching && !articleLoading && count !== null && (
          <div className="mt-8 space-y-3">
            {results.length === 0 ? (
              <p className="text-center text-muted-foreground mt-12">
                No results found
              </p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-4">
                  {count} result{count !== 1 ? "s" : ""}
                </p>
                {results.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => handleCardClick(doc.id)}
                    className="group w-full text-left rounded-lg border border-border bg-card p-4 transition-colors hover:border-gold/40"
                    style={{ borderLeftWidth: "3px" }}
                  >
                    <h3 className="font-serif text-foreground group-hover:text-citation transition-colors leading-snug">
                      {doc.title}
                    </h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      {[doc.author, doc.issue, doc.year].filter(Boolean).join(" \u00b7 ")}
                    </p>
                    {doc.highlighted_snippet && (
                      <p
                        className="text-sm text-muted-foreground mt-2 line-clamp-2"
                        dangerouslySetInnerHTML={{ __html: doc.highlighted_snippet }}
                      />
                    )}
                  </button>
                ))}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
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

      {/* Main Content Area */}
      <main className="md:ml-64 flex flex-1 flex-col min-w-0 h-screen">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
          {/* Mobile: hamburger */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Mobile: centered wordmark */}
          <h1 className="md:hidden flex-1 text-center font-serif text-lg font-semibold text-foreground">
            Rhemata
          </h1>

          {/* Mobile: spacer to balance hamburger */}
          <div className="md:hidden min-w-[44px]" />

          {/* Desktop: auth button */}
          <div className="hidden md:flex ml-auto">
            <AuthButton
              user={user}
              onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
              onSignOut={signOut}
            />
          </div>
        </div>

        {pageContent}
      </main>

      {showLogin && (
        <LoginModal
          onClose={() => { setShowLogin(false); setLoginReason(undefined); }}
          onSignIn={signIn}
          onSignUp={signUp}
          reason={loginReason}
        />
      )}
    </div>
  );
}
