"use client";

import { useState, useEffect } from "react";
import { Plus, LogIn, MoreHorizontal, X, MessageSquare, Compass, BookOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/hooks/useConversations";
import type { User } from "@supabase/supabase-js";

export interface SavedWord {
  id: string;
  strongs_number: string;
  greek_word: string;
  transliteration: string;
  english_gloss: string | null;
}

interface SidebarProps {
  isLoggedIn: boolean;
  user: User | null;
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSignInClick: () => void;
  onSignOut: () => void;
  // Chat
  conversations?: Conversation[];
  activeConversationId?: string | null;
  onSelectConversation?: (id: string) => void;
  onDeleteConversation?: (id: string) => void;
  // Study
  savedWords?: SavedWord[];
  selectedStrongs?: string | null;
  onSelectSavedWord?: (strongs: string) => void;
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
  isLoggedIn,
  user,
  isOpen,
  onClose,
  onNewChat,
  onSignInClick,
  onSignOut,
  conversations = [],
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  savedWords = [],
  selectedStrongs,
  onSelectSavedWord,
}: SidebarProps) {
  const pathname = usePathname();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const isChat = pathname === "/" || pathname.startsWith("/chat");
  const isDiscover = pathname === "/library";
  const isStudy = pathname.startsWith("/study");

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  function handleSelectConversation(id: string) {
    onSelectConversation?.(id);
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
        <h1 className="font-sans text-2xl font-semibold text-foreground tracking-tight">
          Rhemata
        </h1>
        <button
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:text-foreground md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* New Chat CTA */}
      <Button
        onClick={handleNewChat}
        className="w-full min-h-[44px] mb-4 gap-2"
      >
        <Plus className="h-4 w-4 shrink-0" />
        <span>New Chat</span>
      </Button>

      {/* Nav Items */}
      <nav className="space-y-0.5 mb-4">
        <Link
          href="/"
          onClick={onClose}
          className={cn(
            "flex w-full min-h-[40px] items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            isChat && "bg-sidebar-accent text-sidebar-accent-foreground"
          )}
        >
          <MessageSquare className="h-4 w-4" />
          Chat
        </Link>
        <Link
          href="/library"
          onClick={onClose}
          className={cn(
            "flex w-full min-h-[40px] items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            isDiscover && "bg-sidebar-accent text-sidebar-accent-foreground"
          )}
        >
          <Compass className="h-4 w-4" />
          Library
        </Link>
        <Link
          href="/study"
          onClick={onClose}
          className={cn(
            "flex w-full min-h-[40px] items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            isStudy && "bg-sidebar-accent text-sidebar-accent-foreground"
          )}
        >
          <BookOpen className="h-4 w-4" />
          Study
        </Link>
      </nav>

      {/* Conditional Content */}
      <div className="flex-1 overflow-y-auto -mx-2 px-2">
        {isChat && (
          isLoggedIn ? (
            <>
              <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Recents
              </p>
              <div className="space-y-2">
                {conversations.map((conversation) => (
                  <div key={conversation.id} className="group relative">
                    {confirmingId === conversation.id ? (
                      <div className="flex w-full min-h-[44px] items-center gap-2 rounded-lg bg-destructive/10 px-3 py-2">
                        <button
                          onClick={() => {
                            onDeleteConversation?.(conversation.id);
                            setConfirmingId(null);
                          }}
                          className="flex-1 rounded px-3 py-1 text-xs font-medium bg-destructive text-destructive-foreground hover:bg-destructive/90 transition-colors min-h-[32px]"
                        >
                          Delete
                        </button>
                        <button
                          onClick={() => setConfirmingId(null)}
                          className="flex-1 rounded px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors min-h-[32px]"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <button
                          onClick={() => handleSelectConversation(conversation.id)}
                          className={cn(
                            "w-full min-h-[44px] rounded-lg px-3 py-2 text-left transition-colors cursor-pointer hover:bg-sidebar-accent",
                            activeConversationId === conversation.id && "bg-sidebar-accent"
                          )}
                        >
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
                        </button>

                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setConfirmingId(conversation.id);
                          }}
                          className="absolute right-2 top-2 hidden min-h-[44px] min-w-[44px] items-center justify-center rounded p-1 text-muted-foreground transition-colors hover:text-foreground group-hover:flex"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </>
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
          )
        )}

        {isStudy && (
          <>
            <p className="px-3 pb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Saved Words
            </p>
            {savedWords.length === 0 ? (
              <p className="px-3 text-sm italic text-muted-foreground">
                No saved words yet
              </p>
            ) : (
              <div className="space-y-0.5">
                {savedWords.map((word) => {
                  const isActive = selectedStrongs === word.strongs_number;
                  return (
                    <button
                      key={word.id}
                      onClick={() => onSelectSavedWord?.(word.strongs_number)}
                      className={cn(
                        "w-full text-left rounded px-3 py-2 transition-colors cursor-pointer hover:bg-sidebar-accent",
                        isActive && "bg-sidebar-accent"
                      )}
                    >
                      <p className="text-sm text-foreground">
                        {(word.english_gloss ?? "").split(",")[0].trim() || word.transliteration}
                        <span className="text-muted-foreground"> &middot; {word.strongs_number}</span>
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {word.transliteration}
                      </p>
                    </button>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* Mobile-only: profile/email above footer (signed-in users only) */}
      {user && (
        <div className="md:hidden border-t border-sidebar-border pt-4 pb-2 px-1">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground truncate max-w-[160px]">{user.email}</p>
            <button
              onClick={onSignOut}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors min-h-[44px] px-2"
            >
              Sign out
            </button>
          </div>
        </div>
      )}

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
      <aside className="hidden md:flex fixed left-0 top-0 z-40 h-screen w-64 flex-col bg-sidebar px-4 pt-6">
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
          "fixed left-0 top-0 z-50 flex h-dvh-safe w-full flex-col bg-sidebar px-4 pt-6 transition-transform duration-300 md:hidden",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
