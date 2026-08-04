import type { VerifiedReference } from "@/lib/study-reference";

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

export interface WeeklyUsage {
  used: number;
  limit: number;
  week_start: string;
  resets: string;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (meta: { citations: Citation[]; conversation_id: string | null; message_id?: string | null; topics_established?: Record<string, number>; usage?: { used: number; limit: number; week_start: string }; verified_references?: VerifiedReference[] }) => void;
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
      if (data.detail?.error === "weekly_limit_reached") {
        throw new Error("weekly_limit_reached:" + JSON.stringify(data.detail));
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

// ── Async answer path (Stage 2 cutover) ──────────────────────────────────────
// The async path is gated behind a seconds-reversible server switch. useChat calls
// getChatMode() and routes to streamAsyncChatMessage ONLY when it returns true;
// otherwise it uses the live streamChatMessage above, byte-for-byte as before.

type ChatMode = { v: boolean; ts: number };
let _chatModeCache: ChatMode | null = null;
const CHAT_MODE_TTL_MS = 30_000;

/** Returns true iff the async answer path is enabled server-side. Fails safe to
 *  false (live path) on 404 (routes not mounted) or any network error. Cached 30s. */
export async function getChatMode(): Promise<boolean> {
  const now = Date.now();
  if (_chatModeCache && now - _chatModeCache.ts < CHAT_MODE_TTL_MS) return _chatModeCache.v;
  try {
    const res = await fetch(`${API_URL}/async-chat/mode`);
    if (!res.ok) {
      _chatModeCache = { v: false, ts: now };
      return false;
    }
    const data = await res.json();
    const v = data?.async_enabled === true;
    _chatModeCache = { v, ts: now };
    return v;
  } catch {
    _chatModeCache = { v: false, ts: now };
    return false;
  }
}

/** Client-side reading-pace reveal (~250 chars/sec), matching the server's old
 *  PLAYBACK_CHARS_PER_SEC. Fires only after the fully-checked answer has arrived. */
async function clientPaceReveal(answer: string, onToken: (t: string) => void): Promise<void> {
  if (!answer) return;
  const CHARS_PER_SEC = 250;
  const parts = answer.match(/\S+\s*/g) ?? [answer];
  for (const part of parts) {
    onToken(part);
    await new Promise((r) => setTimeout(r, (part.length / CHARS_PER_SEC) * 1000));
  }
}

/** Same signature as streamChatMessage. Submits to the durable queue, then streams
 *  the (already server-verified) whole answer and reveals it at reading pace on the
 *  CLIENT. No client connection ever holds a generation worker open; reconnecting is
 *  just re-GETting the durable job. */
export async function streamAsyncChatMessage(
  question: string,
  callbacks: StreamCallbacks,
  options?: {
    token?: string | null;
    conversationId?: string | null; // threaded to /result so the answer lands in the right conversation
    messages?: ChatMessagePayload[];
    anonId?: string | null;
    topicsEstablished?: Record<string, number>;
  },
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options?.token) headers["Authorization"] = `Bearer ${options.token}`;

  // 1. Submit (returns instantly with a durable job id). Metering happens here,
  //    server-side, keyed on the caller -- so usage arrives in the submit response.
  const submitRes = await fetch(`${API_URL}/async-chat/submit`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      question,
      messages: options?.messages ?? [],
      topics_established: options?.topicsEstablished ?? {},
      anon_id: options?.anonId ?? null,
    }),
  });
  if (!submitRes.ok) {
    if (submitRes.status === 429) {
      const data = await submitRes.json().catch(() => ({}));
      if (data.detail === "guest_limit_reached") throw new Error("guest_limit_reached");
      if (data.detail?.error === "weekly_limit_reached") {
        throw new Error("weekly_limit_reached:" + JSON.stringify(data.detail));
      }
    }
    if (submitRes.status === 503) {
      const data = await submitRes.json().catch(() => ({}));
      if (data.detail === "async_serving_disabled") {
        // The DB switch may have been turned off after getChatMode() cached true.
        // Pin the cache off and retry this untouched request through the live path;
        // submit is gated before metering/enqueue, so this cannot double-charge or
        // create two generations.
        _chatModeCache = { v: false, ts: Date.now() };
        return streamChatMessage(question, callbacks, options);
      }
      throw new Error("queue_full");
    }
    throw new Error("Chat request failed");
  }
  const submitData = await submitRes.json();
  const jobId: string | undefined = submitData?.job_id;
  if (!jobId) throw new Error("Chat request failed");
  const submitUsage = submitData?.usage as { used: number; limit: number; week_start: string } | undefined;

  // 2. Stream the result. Reconnect = re-issue this GET for the same job_id.
  //    The conversation_id (if we have one) tells the server which conversation
  //    to persist the answer under.
  const cidQuery = options?.conversationId
    ? `?conversation_id=${encodeURIComponent(options.conversationId)}`
    : "";
  const res = await fetch(`${API_URL}/async-chat/result/${jobId}${cidQuery}`, { headers });
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let revealed = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue; // ignore ": keepalive" comments
      const payload = trimmed.slice(6);
      if (payload === "[DONE]") return;
      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) {
          callbacks.onError(parsed.error);
          return;
        }
        if (parsed.answer !== undefined && !revealed) {
          revealed = true;
          await clientPaceReveal(parsed.answer, callbacks.onToken);
        }
        if (parsed.citations !== undefined) {
          callbacks.onMeta({
            citations: parsed.citations ?? [],
            conversation_id: parsed.conversation_id ?? null,
            message_id: parsed.message_id ?? null,
            verified_references: parsed.verified_references ?? undefined,
            topics_established: parsed.topics_established ?? undefined,
            usage: submitUsage,
          });
        }
      } catch {
        // Not JSON — skip
      }
    }
  }
}

export async function searchDocuments(query: string, token?: string | null): Promise<SearchResponse> {
  const res = await fetch(`${API_URL}/search?q=${encodeURIComponent(query)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Search request failed");
  return res.json();
}

export async function getDocument(id: string, token?: string | null): Promise<DocumentResponse> {
  const res = await fetch(`${API_URL}/document/${id}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
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
}, token?: string | null): Promise<DocumentSearchResponse> {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.author) sp.set("author", params.author);
  if (params.source_kind) sp.set("source_kind", params.source_kind);
  if (params.include_copyrighted !== undefined) sp.set("include_copyrighted", String(params.include_copyrighted));
  if (params.era) sp.set("era", params.era);
  const res = await fetch(`${API_URL}/search/documents?${sp.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
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

export async function getArticle(id: string, version?: string, token?: string | null): Promise<ArticleResponse> {
  const sp = new URLSearchParams();
  if (version) sp.set("version", version);
  const qs = sp.toString();
  const res = await fetch(`${API_URL}/document/${id}/article${qs ? `?${qs}` : ""}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
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
export interface BookQuote {
  id: string;
  quote_text: string;
  quote_index: number;
}

export interface BookExcerptChunk {
  id: string;
  chunk_index: number;
  content: string;
}

export interface BookExcerptResponse {
  document: { id: string; title: string; author: string; era: string | null };
  quotes?: BookQuote[];
  chunks?: BookExcerptChunk[];
}

export async function getBookExcerpts(docId: string, token?: string | null): Promise<BookExcerptResponse> {
  const res = await fetch(`${API_URL}/library/book/${docId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Book fetch failed");
  return res.json();
}

export async function fetchWeeklyUsage(token: string): Promise<WeeklyUsage> {
  const res = await fetch(`${API_URL}/usage`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Usage fetch failed");
  return res.json();
}

// ── Discover ──────────────────────────────────────────────────────────────────

export interface DiscoverDoc {
  id: string;
  title: string;
  author: string | null;
  source_kind: string | null;
  topic_tags: string[] | null;
  year: number | null;
  era: string | null;
  content_summary: string | null;
  image_url?: string | null;
}

export interface SourceCounts {
  magazine_article: number;
  sermon_transcript: number;
  books: number;
}

export interface PastorsNote {
  id: string;
  verse_id: string;
  content: string;
  display_name: string | null;
  created_at: string;
}

export async function fetchDocMeta(ids: string[], token?: string | null): Promise<{ results: DiscoverDoc[] }> {
  if (!ids.length) return { results: [] };
  const res = await fetch(`${API_URL}/library/doc-meta?ids=${ids.join(",")}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Doc meta fetch failed");
  return res.json();
}

export async function fetchRecentDocs(limit = 6, token?: string | null): Promise<{ results: DiscoverDoc[] }> {
  const res = await fetch(`${API_URL}/library/recent?limit=${limit}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Recent docs fetch failed");
  return res.json();
}

export async function fetchSourceCounts(token?: string | null): Promise<SourceCounts> {
  const res = await fetch(`${API_URL}/library/counts`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Source counts fetch failed");
  return res.json();
}

export async function fetchRecentNotes(limit = 4): Promise<PastorsNote[]> {
  const res = await fetch(`${API_URL}/pastors-notes/recent?limit=${limit}`);
  if (!res.ok) throw new Error("Recent notes fetch failed");
  return res.json();
}
