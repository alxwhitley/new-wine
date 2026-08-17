export interface FailedTurnMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * After a failed generic-error turn, the message list ends with the
 * user's question followed by an empty assistant placeholder that never
 * received real content (see hooks/useChat.ts's sendMessage). Returns the
 * list with that trailing pair removed so a retry can resubmit cleanly --
 * no leftover empty bubble, no duplicate question -- without discarding
 * everything earlier in the conversation. Only strips when the trailing
 * assistant message is genuinely empty -- a completed answer (any real
 * content, even one token) is never a "failed turn" and must never be
 * discarded.
 */
export function withoutFailedTurn<T extends FailedTurnMessage>(messages: T[]): T[] {
  const n = messages.length;
  if (
    n >= 2 &&
    messages[n - 1].role === "assistant" &&
    messages[n - 1].content === "" &&
    messages[n - 2].role === "user"
  ) {
    return messages.slice(0, n - 2);
  }
  return messages;
}
