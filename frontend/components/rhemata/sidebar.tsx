"use client";

import { Plus, MessageSquare, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/hooks/useConversations";

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoggedIn: boolean;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onSignInClick: () => void;
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function Sidebar({
  conversations,
  activeConversationId,
  isLoggedIn,
  onNewChat,
  onSelectConversation,
  onSignInClick,
}: SidebarProps) {
  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-64 flex-col bg-sidebar border-r border-sidebar-border px-4 pt-6">
      {/* Wordmark */}
      <div className="pb-4">
        <h1 className="font-serif text-2xl font-semibold text-foreground tracking-tight">
          Rhemata
        </h1>
      </div>

      {/* New Chat Button */}
      <div className="mb-4">
        <Button
          onClick={onNewChat}
          className="w-full justify-start gap-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
        >
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>

      {/* Conversation History */}
      <div className="flex-1 overflow-y-auto -mx-2 px-2">
        {isLoggedIn ? (
          <div className="space-y-2">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                onClick={() => onSelectConversation(conversation.id)}
                className={cn(
                  "w-full rounded-lg px-3 py-2 text-left transition-colors",
                  "hover:bg-sidebar-accent",
                  activeConversationId === conversation.id
                    ? "bg-sidebar-accent"
                    : "bg-transparent"
                )}
              >
                <div className="flex items-start gap-1">
                  <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-foreground">
                      {conversation.title}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {relativeTime(conversation.updated_at)}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="px-3 py-6 text-center">
            <p className="text-xs text-muted-foreground mb-4">
              Sign in to save conversations
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={onSignInClick}
              className="gap-2"
            >
              <LogIn className="h-3.5 w-3.5" />
              Sign in
            </Button>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="mt-auto pb-4 px-4">
        <p className="text-xs text-muted-foreground text-center">
          Theological Research Assistant
        </p>
      </div>
    </aside>
  );
}
