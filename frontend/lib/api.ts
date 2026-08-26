import type { VerifiedReference } from "@/lib/study-reference";
import { revealCharsPerSecond } from "@/lib/chat-reveal";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

// Types
export interface Citation {
  chunk_id: string;
  document_title: string;
  author: string;
  content: string;
  url?: string | null;
}

export interface ResolvedQuote {
  id: string;
  quote_text: string;
  topic: string;
  /** Passage-level taxonomy tags when present (quality pipeline). */
  topic_ids?: string[] | null;
  teacher_name: string | null;
  /** Source work / document title when resolvable. */
  work_title?: string | null;
  /** Optional one-sentence companion (not quoted typography). */
  restated_point?: string | null;
  approved_at: string;
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

export interface StreamMeta {
  citations: Citation[];
  conversation_id: string | null;
  message_id?: string | null;
  topics_established?: Record<string, number>;
  usage?: { used: number; limit: number; week_start: string };
  verified_references?: VerifiedReference[];
  quote_ids?: string[];
  // Long-conversation-handoff nudge signal (docs/superpowers/specs/2026-08-26-
  // long-conversation-handoff.md). null for guests -- server-side accumulation
  // needs a persisted conversation row, which guests don't have (v1 scope).
  conversation_cost_usd?: number | null;
  conversation_turn_count?: number | null;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onMeta: (meta: StreamMeta) => void;
  onError: (error: string) => void;
  onJobSubmitted?: (jobId: string) => void;
}

// DEAD CODE as of 2026-08-07 (mirror-unification job complete): the backend
// endpoint this fetches (/chat, chat.py) is deleted, and useChat.ts no longer
// calls this function at all (batch 3 removed the fallback that used to
// route here). Left in place rather than deleted in the same pass as the
// backend deletion -- zero callers, safe to remove whenever frontend
// cleanup touches this file next.
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

// ── Async answer path ─────────────────────────────────────────────────────────
// This is now the ONE answer path the frontend calls -- no routing, no fallback.
// getChatMode()/_chatModeCache (a mode-check used to decide between this path and
// the legacy streamChatMessage) were removed 2026-08-07 (mirror-unification batch
// 3, Part 2 -- Alex's explicit decision: no fallback of any kind). They were pure
// routing plumbing with no purpose once there's only one path to route to, and
// keeping a mode pre-check would have added a redundant network round-trip that
// still couldn't eliminate the need for streamAsyncChatMessage to handle its own
// failures below (a race between the pre-check and the real submit is always
// possible). A failure to reach or use this path now surfaces as a real, visible
// error via callbacks.onError -- never a silent handoff to a different path.
//

/** Shown when the answer service can't be reached or is deliberately paused
 *  (async_answer_config.serving_enabled = false -- see async_chat.py's module
 *  docstring). Plain, honest, non-marketing tone, matching the backend's
 *  _NO_ANSWER_FALLBACK string. Two candidates were drafted 2026-08-07;
 *  Alex confirmed this one. */
const _SERVICE_UNAVAILABLE_MESSAGE =
  "I wasn't able to reach Rhemata's answer service just now. Please try again in a moment.";

/** Client-side reading-pace reveal (~250 chars/sec), matching the server's old
 *  PLAYBACK_CHARS_PER_SEC. Fires only after the fully-checked answer has arrived. */
async function clientPaceReveal(answer: string, onToken: (t: string) => void): Promise<void> {
  if (!answer) return;
  const charsPerSecond = revealCharsPerSecond(answer.length);
  const parts = answer.match(/\S+\s*/g) ?? [answer];
  for (const part of parts) {
    onToken(part);
    await new Promise((r) => setTimeout(r, (part.length / charsPerSecond) * 1000));
  }
}

interface AsyncResultOptions {
  token?: string | null;
  conversationId?: string | null;
  usage?: { used: number; limit: number; week_start: string };
}

export async function streamAsyncChatResult(
  jobId: string,
  callbacks: StreamCallbacks,
  options?: AsyncResultOptions,
): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options?.token) headers["Authorization"] = `Bearer ${options.token}`;

  const cidQuery = options?.conversationId
    ? `?conversation_id=${encodeURIComponent(options.conversationId)}`
    : "";
  let res: Response;
  try {
    res = await fetch(`${API_URL}/async-chat/result/${jobId}${cidQuery}`, { headers });
  } catch {
    callbacks.onError(_SERVICE_UNAVAILABLE_MESSAGE);
    return;
  }
  if (!res.ok) {
    callbacks.onError(`result_${res.status}`);
    return;
  }
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let revealPromise: Promise<void> | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data: ")) continue;
      const payload = trimmed.slice(6);
      if (payload === "[DONE]") {
        await revealPromise;
        return;
      }
      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) {
          callbacks.onError(parsed.error);
          return;
        }
        if (parsed.answer !== undefined && !revealPromise) {
          revealPromise = clientPaceReveal(parsed.answer, callbacks.onToken);
        }
        if (parsed.citations !== undefined) {
          callbacks.onMeta({
            citations: parsed.citations ?? [],
            conversation_id: parsed.conversation_id ?? null,
            message_id: parsed.message_id ?? null,
            verified_references: parsed.verified_references ?? undefined,
            topics_established: parsed.topics_established ?? undefined,
            usage: options?.usage,
            quote_ids: parsed.quote_ids ?? [],
            conversation_cost_usd: parsed.conversation_cost_usd ?? null,
            conversation_turn_count: parsed.conversation_turn_count ?? null,
          });
        }
      } catch {
        // Not JSON — skip
      }
    }
  }
  await revealPromise;
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
  let submitRes: Response;
  try {
    submitRes = await fetch(`${API_URL}/async-chat/submit`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        question,
        messages: options?.messages ?? [],
        topics_established: options?.topicsEstablished ?? {},
        anon_id: options?.anonId ?? null,
      }),
    });
  } catch {
    // Network error reaching the backend at all -- no fallback path exists
    // (2026-08-07, mirror-unification batch 3, Part 2). Surface a real,
    // visible error instead of throwing a generic Error the caller has no
    // specific copy for.
    callbacks.onError(_SERVICE_UNAVAILABLE_MESSAGE);
    return;
  }
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
        // The emergency-pause switch (async_answer_config.serving_enabled) is
        // off -- a deliberate kill-switch, not a rollback mechanism (see
        // async_chat.py's module docstring, corrected 2026-08-07). There is
        // no other path to hand this off to: surface a real, visible error.
        callbacks.onError(_SERVICE_UNAVAILABLE_MESSAGE);
        return;
      }
      throw new Error("queue_full");
    }
    throw new Error("Chat request failed");
  }
  const submitData = await submitRes.json();
  const jobId: string | undefined = submitData?.job_id;
  if (!jobId) throw new Error("Chat request failed");
  const submitUsage = submitData?.usage as { used: number; limit: number; week_start: string } | undefined;
  callbacks.onJobSubmitted?.(jobId);

  // 2. Stream the result. Reconnect = re-issue this GET for the same job_id.
  //    The conversation_id (if we have one) tells the server which conversation
  //    to persist the answer under.
  return streamAsyncChatResult(jobId, callbacks, {
    token: options?.token,
    conversationId: options?.conversationId,
    usage: submitUsage,
  });
}

export async function resolveQuotes(quoteIds: string[]): Promise<ResolvedQuote[]> {
  const res = await fetch(`${API_URL}/answer-quotes/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quote_ids: quoteIds }),
  });
  if (!res.ok) throw new Error("Quote resolve failed");
  const data = await res.json();
  return data.quotes ?? [];
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
