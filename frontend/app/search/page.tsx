"use client";

import { useState, useCallback } from "react";
import { Search, ArrowLeft, Loader2, Menu } from "lucide-react";
import Link from "next/link";
import { searchDocumentsFts, getArticle } from "@/lib/api";
import type { DocumentSearchResult, ArticleResponse } from "@/lib/api";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [author, setAuthor] = useState("");
  const [results, setResults] = useState<DocumentSearchResult[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Article reader state
  const [article, setArticle] = useState<ArticleResponse | null>(null);
  const [articleLoading, setArticleLoading] = useState(false);

  const handleSearch = useCallback(async () => {
    if (!query.trim() && !author.trim()) return;
    setSearching(true);
    setError(null);
    setArticle(null);
    try {
      const res = await searchDocumentsFts({
        q: query.trim() || undefined,
        author: author.trim() || undefined,
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
  }, [query, author]);

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

  // Article reader view
  if (article) {
    return (
      <div className="flex h-screen bg-background">
        <main className="flex flex-1 flex-col min-w-0 h-screen">
          {/* Top bar */}
          <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6">
            <Link
              href="/"
              className="font-serif text-lg font-semibold text-foreground tracking-tight hidden md:block"
            >
              Rhemata
            </Link>
            <div className="hidden md:flex ml-auto">
              <Link
                href="/search"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                Search
              </Link>
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

              <h1 className="font-serif text-2xl font-semibold text-foreground leading-tight">
                {article.title}
              </h1>

              <p className="text-sm text-muted-foreground mt-2">
                {[article.author, article.issue, article.year].filter(Boolean).join(" \u00b7 ")}
              </p>

              <div className="border-t border-border my-6" />

              <div className="text-foreground leading-relaxed text-base whitespace-pre-line">
                {article.content}
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Search view
  return (
    <div className="flex h-screen bg-background">
      <main className="flex flex-1 flex-col min-w-0 h-screen">
        {/* Top bar */}
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6">
          <Link
            href="/"
            className="font-serif text-lg font-semibold text-foreground tracking-tight hidden md:block"
          >
            Rhemata
          </Link>
          <h1 className="md:hidden flex-1 text-center font-serif text-lg font-semibold text-foreground">
            Rhemata
          </h1>
          <div className="hidden md:flex ml-auto">
            <Link
              href="/"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Chat
            </Link>
          </div>
        </div>

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
                placeholder="Search by keyword..."
                className="flex-1 min-h-[44px] rounded-lg border border-border bg-card px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-gold transition-colors"
              />
              <button
                onClick={handleSearch}
                disabled={searching || (!query.trim() && !author.trim())}
                className="min-h-[44px] min-w-[44px] rounded-lg bg-primary text-primary-foreground px-4 flex items-center justify-center gap-2 text-sm font-medium hover:bg-gold-hover transition-colors disabled:opacity-50"
              >
                <Search className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
              </button>
            </div>

            {/* Author filter */}
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Filter by author..."
              className="w-full min-h-[40px] mt-3 rounded-lg border border-border bg-card px-4 text-sm text-muted-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-gold transition-colors"
            />

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
                        {doc.content_summary && (
                          <p className="text-sm text-muted-foreground mt-2 line-clamp-2">
                            {doc.content_summary}
                          </p>
                        )}
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
