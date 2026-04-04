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

  const deleteConversation = useCallback(async (id: string) => {
    await supabase.from("messages").delete().eq("conversation_id", id);
    await supabase.from("conversations").delete().eq("id", id);
    setConversations((prev) => prev.filter((c) => c.id !== id));
  }, []);

  const loadMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    const { data } = await supabase
      .from("messages")
      .select("role, content")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });

    if (!data) return [];
    return data.map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));
  }, []);

  return { conversations, fetchConversations, addOrUpdate, deleteConversation, loadMessages };
}
