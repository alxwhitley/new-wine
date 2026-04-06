"use client";

import { useState, useEffect, useRef } from "react";
import { Plus, MessageSquare, LogIn, MoreHorizontal, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/hooks/useConversations";
import type { User } from "@supabase/supabase-js";

interface SidebarProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoggedIn: boolean;
  user: User | null;
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onSignInClick: () => void;
  onSignOut: () => void;
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
  user,
  isOpen,
  onClose,
  onNewChat,
  onSelectConversation,
  onDeleteConversation,
  onSignInClick,
  onSignOut,
}: SidebarProps) {
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpenId) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
        setConfirmingId(null);
      }
    }
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [menuOpenId]);

  // Lock body scroll when drawer is open on mobile
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  function handleSelectConversation(id: string) {
    onSelectConversation(id);
    onClose();
  }

  function handleNewChat() {
    onNewChat();
    onClose();
  }

  const sidebarContent = (
    <>
      {/* Wordmark + close button (mobile) */}
      <div className="flex items-center justify-between pb-4">
        <h1 className="font-serif text-2xl font-semibold text-foreground tracking-tight">
          Rhemata
        </h1>
        <button
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:text-foreground md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* New Chat Button */}
      <div className="mb-4">
        <Button
          onClick={handleNewChat}
          className="w-full min-h-[44px] justify-start gap-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90"
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
              <div key={conversation.id} className="group relative">
                <button
                  onClick={() => handleSelectConversation(conversation.id)}
                  className={cn(
                    "w-full min-h-[44px] rounded-lg px-3 py-2 text-left transition-colors",
                    "hover:bg-sidebar-accent",
                    activeConversationId === conversation.id
                      ? "bg-sidebar-accent"
                      : "bg-transparent"
                  )}
                >
                  <div className="flex items-start gap-1">
                    <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p
                        className="text-sm font-medium text-foreground"
                        style={{
                          WebkitMaskImage: "linear-gradient(to right, black 70%, transparent 100%)",
                          maskImage: "linear-gradient(to right, black 70%, transparent 100%)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                        }}
                      >
                        {conversation.title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {relativeTime(conversation.updated_at)}
                      </p>
                    </div>
                  </div>
                </button>

                {/* Three-dot menu button — visible on hover */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    console.log("[DELETE TRACE] 1. Three-dot menu opened for:", conversation.id);
                    setMenuOpenId(menuOpenId === conversation.id ? null : conversation.id);
                    setConfirmingId(null);
                  }}
                  className={cn(
                    "absolute right-2 top-2 min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted-foreground transition-colors hover:text-foreground",
                    menuOpenId === conversation.id ? "hidden" : "hidden group-hover:flex"
                  )}
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>

                {/* Dropdown menu */}
                {menuOpenId === conversation.id && (
                  <div
                    ref={menuRef}
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    className="absolute right-0 top-9 z-50 bg-card border border-border rounded-lg shadow-lg py-1 min-w-[120px]"
                  >
                    {confirmingId === conversation.id ? (
                      <div className="px-3 py-2">
                        <p className="text-xs text-muted-foreground mb-2">Delete?</p>
                        <div className="flex gap-2">
                          <button
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                              e.stopPropagation();
                              console.log("[DELETE TRACE] 3. Confirm click — calling onDeleteConversation for:", conversation.id);
                              onDeleteConversation(conversation.id);
                              setMenuOpenId(null);
                              setConfirmingId(null);
                            }}
                            className="rounded px-2 py-1 text-xs font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors"
                          >
                            Delete
                          </button>
                          <button
                            onMouseDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenuOpenId(null);
                              setConfirmingId(null);
                            }}
                            className="rounded px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          console.log("[DELETE TRACE] 2. First click — showing confirm for:", conversation.id);
                          setConfirmingId(conversation.id);
                        }}
                        className="flex w-full items-center gap-2 text-sm px-3 py-2 text-destructive hover:bg-sidebar-accent transition-colors"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Delete
                      </button>
                    )}
                  </div>
                )}
              </div>
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
              className="gap-2 min-h-[44px]"
            >
              <LogIn className="h-3.5 w-3.5" />
              Sign in
            </Button>
          </div>
        )}
      </div>

      {/* Mobile-only: profile/email above footer */}
      <div className="md:hidden border-t border-sidebar-border pt-4 pb-2 px-1">
        {user ? (
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground truncate max-w-[160px]">{user.email}</p>
            <button
              onClick={onSignOut}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors min-h-[44px] px-2"
            >
              Sign out
            </button>
          </div>
        ) : (
          <button
            onClick={onSignInClick}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors min-h-[44px]"
          >
            Sign in
          </button>
        )}
      </div>

      {/* Footer */}
      <div className="mt-auto pb-4 px-4">
        <p className="text-xs text-muted-foreground text-center">
          Theological Research Assistant
        </p>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar — always visible */}
      <aside className="hidden md:flex fixed left-0 top-0 z-40 h-screen w-64 flex-col bg-sidebar border-r border-sidebar-border px-4 pt-6">
        {sidebarContent}
      </aside>

      {/* Mobile drawer overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}

      {/* Mobile drawer */}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-screen w-64 flex-col bg-sidebar border-r border-sidebar-border px-4 pt-6 transition-transform duration-300 md:hidden",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
