import { useState, useEffect, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import { Message } from "./useChat";

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export function useConversations(userId: string | undefined) {
  const [conversations, setConversations] = useState<Conversation[]>([]);

  const fetchConversations = useCallback(async () => {
    if (!userId) {
      setConversations([]);
      return;
    }

    const { data } = await supabase
      .from("conversations")
      .select("id, title, updated_at")
      .eq("user_id", userId)
      .order("updated_at", { ascending: false })
      .limit(50);

    if (data) setConversations(data);
  }, [userId]);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const addOrUpdate = useCallback(
    (id: string, title: string) => {
      setConversations((prev) => {
        const without = prev.filter((c) => c.id !== id);
        return [{ id, title, updated_at: new Date().toISOString() }, ...without];
      });
    },
    [],
  );

  // Returns whether the conversation was actually deleted. Callers must
  // not treat this as fire-and-forget: clearing a visible chat thread on
  // the assumption a delete succeeded, when it silently failed, makes the
  // conversation appear to vanish with no explanation (it's still there,
  // in Supabase and in the sidebar list) -- see app/page.tsx's
  // handleDeleteConversation, which only clears the open thread when this
  // returns true.
  const deleteConversation = useCallback(async (id: string): Promise<boolean> => {
    if (!userId) return false;
    try {
      // Verify the conversation belongs to this user before touching messages.
      // The messages table has no user_id column, so we gate the message delete
      // on confirmed conversation ownership rather than filtering messages directly.
      const { data: owned, error: ownErr } = await supabase
        .from("conversations")
        .select("id")
        .eq("id", id)
        .eq("user_id", userId)
        .maybeSingle();
      if (ownErr) {
        console.error("Failed to verify conversation ownership:", ownErr);
        return false;
      }
      if (!owned) {
        console.error("Refusing to delete conversation not owned by user:", id);
        return false;
      }

      const { error: msgErr } = await supabase.from("messages").delete().eq("conversation_id", id);
      if (msgErr) {
        console.error("Failed to delete messages:", msgErr);
        return false;
      }

      const { error: convErr } = await supabase.from("conversations").delete().eq("id", id).eq("user_id", userId);
      if (convErr) {
        console.error("Failed to delete conversation:", convErr);
        return false;
      }

      setConversations((prev) => prev.filter((c) => c.id !== id));
      return true;
    } catch (err) {
      console.error("Unexpected error deleting conversation:", err);
      return false;
    }
  }, [userId]);

  const loadMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    const { data } = await supabase
      .from("messages")
      .select("id, role, content, citations, verified_references")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });

    if (!data) return [];
    return data.map((m) => ({
      role: m.role as "user" | "assistant",
      content: m.content,
      messageId: m.id,
      citations: m.citations ?? undefined,
      verifiedReferences: m.verified_references ?? undefined,
    }));
  }, []);

  return { conversations, fetchConversations, addOrUpdate, deleteConversation, loadMessages };
}
