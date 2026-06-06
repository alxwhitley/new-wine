const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

// Types
export interface Citation {
  chunk_id: string;
  document_title: string;
  author: string;
  content: string;
  url?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  conversation_id: string | null;
}

export interface SearchDocument {
  id: string;
  title: string;
  author: string;
  source_name: string;
  source_type: string;
  year: number;
  issue: string | null;
  topic_tags: string[];
}

export interface SearchChunk {
  id: string;
  document_id: string;
  content: string;
  chunk_index: number;
}

export interface SearchResponse {
  documents: SearchDocument[];
  chunks: SearchChunk[];
}

export interface Document {
  id: string;
  title: string;
  author: string;
  source_name: string;
  source_type: string;
  year: number;
  issue: string | null;
  topic_tags: string[];
}

export interface Chunk {
  id: string;
  chunk_index: number;
  content: string;
}

export interface DocumentResponse {
  document: Document;
  chunks: Chunk[];
}

// API calls
export interface ChatMessagePayload {
  role: "user" | "assistant";
  content: string;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (meta: { citations: Citation[]; conversation_id: string | null; message_id?: string | null; topics_established?: Record<string, number> }) => void;
  onError: (error: string) => void;
}

export async function streamChatMessage(
  question: string,
  callbacks: StreamCallbacks,
  options?: {
    token?: string | null;
    conversationId?: string | null;
    messages?: ChatMessagePayload[];
    anonId?: string | null;
    topicsEstablished?: Record<string, number>;
  },
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options?.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  const body: Record<string, unknown> = { question };
  if (options?.conversationId) {
    body.conversation_id = options.conversationId;
  }
  if (options?.messages && options.messages.length > 0) {
    body.messages = options.messages;
  }
  if (options?.anonId) {
    body.anon_id = options.anonId;
  }
  if (options?.topicsEstablished && Object.keys(options.topicsEstablished).length > 0) {
    body.topics_established = options.topicsEstablished;
  }

  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    if (res.status === 429) {
      const data = await res.json().catch(() => ({}));
      if (data.detail === "guest_limit_reached") {
        throw new Error("guest_limit_reached");
      }
      if (data.detail === "daily_limit_reached") {
        throw new Error("daily_limit_reached");
      }
    }
    throw new Error("Chat request failed");
  }
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // Keep the last incomplete line in the buffer
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const payload = trimmed.slice(6);

      if (payload === "[DONE]") return;

      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) {
          callbacks.onError(parsed.error);
          return;
        }
        if (parsed.token !== undefined) {
          callbacks.onToken(parsed.token);
        }
        if (parsed.citations !== undefined) {
          callbacks.onMeta(parsed);
        }
      } catch {
        // Not JSON — skip
      }
    }
  }
}

export async function searchDocuments(query: string): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error("Search request failed");
  return res.json();
}

export async function getDocument(id: string): Promise<DocumentResponse> {
  const res = await fetch(`${API_URL}/document/${id}`);
  if (!res.ok) throw new Error("Document fetch failed");
  return res.json();
}

// Document-level search (search_documents RPC)
export interface DocumentSearchResult {
  id: string;
  title: string;
  author: string;
  issue: string | null;
  year: number | null;
  topic_tags: string[];
  source_kind: string | null;
  source_name: string | null;
  description: string | null;
  highlighted_snippet: string | null;
  rank: number;
}

export interface DocumentSearchResponse {
  results: DocumentSearchResult[];
  count: number;
}

export async function searchDocumentsFts(params: {
  q?: string;
  author?: string;
  source_kind?: string;
  include_copyrighted?: boolean;
  era?: string;
}): Promise<DocumentSearchResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.author) sp.set("author", params.author);
  if (params.source_kind) sp.set("source_kind", params.source_kind);
  if (params.include_copyrighted !== undefined) sp.set("include_copyrighted", String(params.include_copyrighted));
  if (params.era) sp.set("era", params.era);
  const res = await fetch(`${API_URL}/search/documents?${sp.toString()}`);
  if (!res.ok) throw new Error("Document search failed");
  return res.json();
}

// Browse all documents (no search query)
export async function browseDocuments(params?: {
  source_kind?: string;
  include_copyrighted?: boolean;
  era?: string;
  author?: string;
}): Promise<DocumentSearchResponse> {
  const sp = new URLSearchParams();
  if (params?.source_kind) sp.set("source_kind", params.source_kind);
  if (params?.include_copyrighted !== undefined) sp.set("include_copyrighted", String(params.include_copyrighted));
  if (params?.era) sp.set("era", params.era);
  if (params?.author) sp.set("author", params.author);
  const res = await fetch(`${API_URL}/search/documents/browse?${sp.toString()}`);
  if (!res.ok) throw new Error("Browse request failed");
  return res.json();
}

// Full article reader
export interface ArticleResponse {
  id: string;
  title: string;
  author: string;
  issue: string | null;
  year: number | null;
  source_name: string | null;
  url: string | null;
  source_kind: string | null;
  content: string;
}

export async function getArticle(id: string, version?: string): Promise<ArticleResponse> {
  const sp = new URLSearchParams();
  if (version) sp.set("version", version);
  const qs = sp.toString();
  const res = await fetch(`${API_URL}/document/${id}/article${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error("Article fetch failed");
  return res.json();
}

// Admin
export async function deleteDocument(id: string, token: string): Promise<void> {
  const res = await fetch(`${API_URL}/admin/document/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Delete failed");
}

export interface AdminDocumentEdit {
  title: string;
  author: string;
  source_kind: string | null;
  url: string | null;
  content: string;
}

export async function getDocumentForEdit(id: string, token: string): Promise<AdminDocumentEdit> {
  const res = await fetch(`${API_URL}/admin/document/${id}/edit`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load document for editing");
  return res.json();
}

export async function updateDocument(id: string, body: { title: string; author: string; content: string }, token: string): Promise<{ success: boolean; chunk_count: number }> {
  const res = await fetch(`${API_URL}/admin/document/${id}/edit`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Save failed");
  return res.json();
}

// Books
export interface Book {
  id: string;
  title: string;
  author: string;
  description: string | null;
  topic_tags: string[];
  created_at: string;
  document_id: string | null;
}

export interface BooksResponse {
  results: Book[];
  count: number;
}

export async function fetchBooks(params?: {
  q?: string;
  era?: string;
  author?: string;
}): Promise<BooksResponse> {
  const sp = new URLSearchParams();
  if (params?.q) sp.set("q", params.q);
  if (params?.era) sp.set("era", params.era);
  if (params?.author) sp.set("author", params.author);
  const res = await fetch(`${API_URL}/library/books?${sp.toString()}`);
  if (!res.ok) throw new Error("Books fetch failed");
  return res.json();
}

// Book excerpt reader
export interface BookExcerptChunk {
  id: string;
  chunk_index: number;
  content: string;
}

export interface BookExcerptResponse {
  document: { id: string; title: string; author: string; era: string | null };
  chunks: BookExcerptChunk[];
}

export async function getBookExcerpts(docId: string): Promise<BookExcerptResponse> {
  const res = await fetch(`${API_URL}/library/book/${docId}`);
  if (!res.ok) throw new Error("Book fetch failed");
  return res.json();
}
