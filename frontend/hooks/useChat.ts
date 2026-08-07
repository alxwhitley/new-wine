import { useState, useCallback, useRef, useEffect } from "react";
import { streamAsyncChatMessage, fetchWeeklyUsage, Citation } from "@/lib/api";
import type { VerifiedReference } from "@/lib/study-reference";

export interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
  verifiedReferences?: VerifiedReference[];
  quoteIds?: string[];
}

export interface WeeklyLimitDetail {
  used: number;
  limit: number;
  week_start: string;
  resets: string;
}

function getAnonId(): string {
  const key = "rhemata_anon_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export function useChat(
  accessToken: string | null,
  onGuestLimitReached?: () => void,
  onWeeklyLimitReached?: (detail: WeeklyLimitDetail) => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [weeklyUsage, setWeeklyUsage] = useState<{ used: number; limit: number } | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const topicsEstablishedRef = useRef<Record<string, number>>({});

  // Seed usage count on mount (and whenever token changes from null → value)
  useEffect(() => {
    if (!accessToken) return;
    fetchWeeklyUsage(accessToken)
      .then((data) => setWeeklyUsage({ used: data.used, limit: data.limit }))
      .catch(() => {
        // Silently ignore — ring stays hidden if fetch fails
      });
  }, [accessToken]);

  const sendMessage = useCallback(
    async (question: string) => {
      setLoading(true);
      setError(null);

      const userMessage: Message = { role: "user", content: question };

      // Capture current history, then append user + empty assistant in one update
      let history: Message[] = [];
      setMessages((prev) => {
        history = prev;
        return [...prev, userMessage, { role: "assistant", content: "" }];
      });

      let newConversationId: string | null = null;

      try {
        // The async answer path is the only path -- no mode check, no fallback
        // (2026-08-07, mirror-unification batch 3, Part 2, Alex's explicit
        // decision). streamAsyncChatMessage surfaces its own failures (the
        // emergency-pause switch being off, or a network error reaching the
        // backend at all) as a real error via callbacks.onError below --
        // never a silent handoff to a different implementation.
        await streamAsyncChatMessage(
          question,
          {
            onToken: (token) => {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    content: last.content + token,
                  };
                }
                return updated;
              });
            },
            onMeta: (meta) => {
              newConversationId = meta.conversation_id;
              if (meta.conversation_id) {
                conversationIdRef.current = meta.conversation_id;
                setConversationId(meta.conversation_id);
              }
              if (meta.topics_established) {
                topicsEstablishedRef.current = meta.topics_established;
              }
              // Update usage count from SSE meta — no extra /usage fetch needed
              if (meta.usage) {
                setWeeklyUsage({ used: meta.usage.used, limit: meta.usage.limit });
              }
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    ...(meta.citations?.length ? { citations: meta.citations } : {}),
                    ...(meta.message_id ? { messageId: meta.message_id } : {}),
                    ...(meta.verified_references?.length ? { verifiedReferences: meta.verified_references } : {}),
                    ...(meta.quote_ids?.length ? { quoteIds: meta.quote_ids } : {}),
                  };
                }
                return updated;
              });
            },
            onError: (errMsg) => {
              setError(errMsg);
            },
          },
          {
            token: accessToken,
            conversationId: conversationIdRef.current,
            messages: history.map((m) => ({ role: m.role, content: m.content })),
            anonId: getAnonId(),
            topicsEstablished: topicsEstablishedRef.current,
          },
        );

        return newConversationId;
      } catch (err) {
        if (err instanceof Error && err.message === "guest_limit_reached") {
          setMessages((prev) => prev.slice(0, -2));
          onGuestLimitReached?.();
          return null;
        }
        if (err instanceof Error && err.message.startsWith("weekly_limit_reached:")) {
          // Keep user message; remove the empty assistant placeholder
          setMessages((prev) => prev.slice(0, -1));
          const detail: WeeklyLimitDetail = JSON.parse(
            err.message.slice("weekly_limit_reached:".length),
          );
          onWeeklyLimitReached?.(detail);
          return null;
        }
        setError("Something went wrong. Please try again.");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [accessToken, onGuestLimitReached, onWeeklyLimitReached],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    conversationIdRef.current = null;
    setConversationId(null);
    topicsEstablishedRef.current = {};
  }, []);

  const loadConversation = useCallback((id: string, msgs: Message[]) => {
    conversationIdRef.current = id;
    setConversationId(id);
    setMessages(msgs);
  }, []);

  return {
    messages,
    loading,
    error,
    conversationId,
    weeklyUsage,
    sendMessage,
    clearMessages,
    loadConversation,
  };
}
