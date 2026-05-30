import { useState, useCallback, useRef } from "react";
import { streamChatMessage, Citation } from "@/lib/api";

export interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  messageId?: string | null;
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
  onDailyLimitReached?: () => void,
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const conversationIdRef = useRef<string | null>(null);
  const topicsEstablishedRef = useRef<Record<string, number>>({});

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
        await streamChatMessage(
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
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last && last.role === "assistant") {
                  updated[updated.length - 1] = {
                    ...last,
                    ...(meta.citations?.length ? { citations: meta.citations } : {}),
                    ...(meta.message_id ? { messageId: meta.message_id } : {}),
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
        if (err instanceof Error && err.message === "daily_limit_reached") {
          setMessages((prev) => prev.slice(0, -2));
          onDailyLimitReached?.();
          return null;
        }
        setError("Something went wrong. Please try again.");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [accessToken, onGuestLimitReached, onDailyLimitReached],
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
    sendMessage,
    clearMessages,
    loadConversation,
  };
}
