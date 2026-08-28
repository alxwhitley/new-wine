import { useState } from "react";
import { searchDocuments, SearchDocument, SearchChunk } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

export function useSearch() {
  const { accessToken } = useAuth();
  const [query, setQuery] = useState("");
  const [documents, setDocuments] = useState<SearchDocument[]>([]);
  const [chunks, setChunks] = useState<SearchChunk[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  async function search(q: string) {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    setQuery(q);

    try {
      const res = await searchDocuments(q, accessToken);
      setDocuments(res.documents);
      setChunks(res.chunks);
      setHasSearched(true);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function clearSearch() {
    setQuery("");
    setDocuments([]);
    setChunks([]);
    setHasSearched(false);
  }

  return { query, documents, chunks, loading, error, hasSearched, search, clearSearch };
}
