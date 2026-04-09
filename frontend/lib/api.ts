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
  onMeta: (meta: { citations: Citation[]; conversation_id: string | null }) => void;
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
}): Promise<DocumentSearchResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.author) sp.set("author", params.author);
  if (params.source_kind) sp.set("source_kind", params.source_kind);
  if (params.include_copyrighted !== undefined) sp.set("include_copyrighted", String(params.include_copyrighted));
  const res = await fetch(`${API_URL}/search/documents?${sp.toString()}`);
  if (!res.ok) throw new Error("Document search failed");
  return res.json();
}

// Browse all documents (no search query)
export async function browseDocuments(params?: {
  source_kind?: string;
  include_copyrighted?: boolean;
}): Promise<DocumentSearchResponse> {
  const sp = new URLSearchParams();
  if (params?.source_kind) sp.set("source_kind", params.source_kind);
  if (params?.include_copyrighted !== undefined) sp.set("include_copyrighted", String(params.include_copyrighted));
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
  content: string;
}

export async function getArticle(id: string): Promise<ArticleResponse> {
  const res = await fetch(`${API_URL}/document/${id}/article`);
  if (!res.ok) throw new Error("Article fetch failed");
  return res.json();
}
