import { useState, useCallback } from "react";
import { streamChatMessage, Citation } from "@/lib/api";

export interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
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
) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);

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
                setConversationId(meta.conversation_id);
              }
              if (meta.citations?.length) {
                setMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === "assistant") {
                    updated[updated.length - 1] = { ...last, citations: meta.citations };
                  }
                  return updated;
                });
              }
            },
            onError: (errMsg) => {
              setError(errMsg);
            },
          },
          {
            token: accessToken,
            conversationId,
            messages: history.map((m) => ({ role: m.role, content: m.content })),
            anonId: getAnonId(),
          },
        );

        return newConversationId;
      } catch (err) {
        if (err instanceof Error && err.message === "guest_limit_reached") {
          // Remove the placeholder messages we just added
          setMessages((prev) => prev.slice(0, -2));
          onGuestLimitReached?.();
          return null;
        }
        setError("Something went wrong. Please try again.");
        return null;
      } finally {
        setLoading(false);
      }
    },
    [accessToken, conversationId, onGuestLimitReached],
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setConversationId(null);
  }, []);

  const loadConversation = useCallback((id: string, msgs: Message[]) => {
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
