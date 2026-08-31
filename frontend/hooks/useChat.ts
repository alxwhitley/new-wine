import { useState, useCallback, useRef, useEffect } from "react";
import {
  streamAsyncChatMessage,
  streamAsyncChatResult,
  fetchWeeklyUsage,
  Citation,
  type StreamMeta,
} from "@/lib/api";
import type { VerifiedReference } from "@/lib/study-reference";
import { withoutFailedTurn } from "@/lib/chat-recovery";
import {
  GUEST_CHAT_SESSION_KEY,
  parseGuestChatSession,
  serializeGuestChatSession,
  shouldRetainPendingGuestJob,
  type PendingGuestJob,
} from "@/lib/guest-chat-session";

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
  const key = "newwine_anon_id";
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
  // Long-conversation-handoff nudge signal (docs/superpowers/specs/2026-08-26-
  // long-conversation-handoff.md). null until the first authenticated turn
  // completes; stays null for guests (server doesn't accumulate for them).
  const [conversationCostUsd, setConversationCostUsd] = useState<number | null>(null);
  const [pendingGuestJob, setPendingGuestJob] = useState<PendingGuestJob | null>(null);
  const [guestJobToResume, setGuestJobToResume] = useState<PendingGuestJob | null>(null);
  const [guestSessionHydrated, setGuestSessionHydrated] = useState(false);
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

  // Guest chats are session-scoped but reload-durable. Authenticated history
  // remains server-owned; never mirror it into browser storage.
  useEffect(() => {
    if (accessToken) {
      sessionStorage.removeItem(GUEST_CHAT_SESSION_KEY);
      setGuestSessionHydrated(true);
      return;
    }

    const restored = parseGuestChatSession(sessionStorage.getItem(GUEST_CHAT_SESSION_KEY));
    if (restored) {
      const restoredMessages = [...restored.messages];
      if (restored.pendingJob) {
        const last = restoredMessages[restoredMessages.length - 1];
        if (last?.role === "assistant") {
          restoredMessages[restoredMessages.length - 1] = { ...last, content: "" };
        }
      }
      topicsEstablishedRef.current = restored.topicsEstablished;
      setMessages(restoredMessages);
      setPendingGuestJob(restored.pendingJob);
      setGuestJobToResume(restored.pendingJob);
    }
    setGuestSessionHydrated(true);
  }, [accessToken]);

  useEffect(() => {
    if (accessToken || !guestSessionHydrated || pendingGuestJob) return;
    if (messages.length === 0 && !pendingGuestJob) {
      sessionStorage.removeItem(GUEST_CHAT_SESSION_KEY);
      return;
    }
    sessionStorage.setItem(GUEST_CHAT_SESSION_KEY, serializeGuestChatSession({
      version: 1,
      messages,
      topicsEstablished: topicsEstablishedRef.current,
      pendingJob: pendingGuestJob,
    }));
  }, [accessToken, guestSessionHydrated, messages, pendingGuestJob]);

  const appendAnswerToken = useCallback((token: string) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last?.role === "assistant") {
        updated[updated.length - 1] = { ...last, content: last.content + token };
      }
      return updated;
    });
  }, []);

  const applyAnswerMeta = useCallback((meta: StreamMeta) => {
    if (meta.conversation_id) {
      conversationIdRef.current = meta.conversation_id;
      setConversationId(meta.conversation_id);
    }
    if (meta.topics_established) {
      topicsEstablishedRef.current = meta.topics_established;
    }
    if (meta.usage) {
      setWeeklyUsage({ used: meta.usage.used, limit: meta.usage.limit });
    }
    if (meta.conversation_cost_usd !== undefined) {
      setConversationCostUsd(meta.conversation_cost_usd);
    }
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (last?.role === "assistant") {
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
  }, []);

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
      let guestJobSubmitted = false;
      let streamFailure: string | null = null;

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
            onToken: appendAnswerToken,
            onMeta: (meta) => {
              newConversationId = meta.conversation_id;
              applyAnswerMeta(meta);
            },
            onError: (errMsg) => {
              streamFailure = errMsg;
              setError(errMsg);
            },
            onJobSubmitted: (jobId) => {
              if (!accessToken) {
                guestJobSubmitted = true;
                const pendingJob = { jobId, question };
                setPendingGuestJob(pendingJob);
                sessionStorage.setItem(GUEST_CHAT_SESSION_KEY, serializeGuestChatSession({
                  version: 1,
                  messages: [...history, userMessage, { role: "assistant", content: "" }],
                  topicsEstablished: topicsEstablishedRef.current,
                  pendingJob,
                }));
              }
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

        if (streamFailure) {
          if (!guestJobSubmitted || !shouldRetainPendingGuestJob(streamFailure)) {
            setMessages((prev) => withoutFailedTurn(prev));
            setPendingGuestJob(null);
          } else {
            setError("Something went wrong. Reload to reconnect to your answer.");
          }
          return null;
        }
        setPendingGuestJob(null);
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
        // Unlike the guest/weekly-limit branches above, this path used to
        // leave the failed question + empty assistant placeholder sitting
        // permanently in `messages` -- a dead bubble that only disappeared
        // if the caller wiped the whole conversation. Stripping it here
        // lets a retry resubmit cleanly in place instead.
        if (!accessToken && guestJobSubmitted) {
          setError("Something went wrong. Reload to reconnect to your answer.");
        } else {
          setMessages((prev) => withoutFailedTurn(prev));
          setError("Something went wrong. Please try again.");
        }
        return null;
      } finally {
        setLoading(false);
      }
    },
    [accessToken, appendAnswerToken, applyAnswerMeta, onGuestLimitReached, onWeeklyLimitReached],
  );

  useEffect(() => {
    if (accessToken || !guestJobToResume) return;
    let cancelled = false;
    let failed = false;
    let terminalFailure = false;

    setLoading(true);
    setError(null);
    streamAsyncChatResult(
      guestJobToResume.jobId,
      {
        onToken: (token) => {
          if (!cancelled) appendAnswerToken(token);
        },
        onMeta: (meta) => {
          if (!cancelled) applyAnswerMeta(meta);
        },
        onError: (message) => {
          if (cancelled) return;
          failed = true;
          terminalFailure = !shouldRetainPendingGuestJob(message);
          setError(terminalFailure
            ? "That answer could not be recovered. Please send your question again."
            : message);
        },
      },
    ).catch(() => {
      if (!cancelled) {
        failed = true;
        setError("Something went wrong. Reload to reconnect to your answer.");
      }
    }).finally(() => {
      if (cancelled) return;
      setLoading(false);
      setGuestJobToResume(null);
      if (terminalFailure) {
        setMessages((prev) => withoutFailedTurn(prev));
        setPendingGuestJob(null);
      } else if (!failed) {
        setPendingGuestJob(null);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [accessToken, appendAnswerToken, applyAnswerMeta, guestJobToResume]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setPendingGuestJob(null);
    setGuestJobToResume(null);
    conversationIdRef.current = null;
    setConversationId(null);
    setConversationCostUsd(null);
    topicsEstablishedRef.current = {};
    sessionStorage.removeItem(GUEST_CHAT_SESSION_KEY);
  }, []);

  const loadConversation = useCallback((id: string, msgs: Message[]) => {
    conversationIdRef.current = id;
    setConversationId(id);
    setMessages(msgs);
    // A loaded past conversation's accumulated cost isn't known client-side
    // until its next turn completes -- reset rather than show a stale/zero
    // figure carried over from whatever conversation was open before.
    setConversationCostUsd(null);
  }, []);

  return {
    messages,
    loading,
    error,
    conversationId,
    weeklyUsage,
    conversationCostUsd,
    sendMessage,
    clearMessages,
    loadConversation,
  };
}
