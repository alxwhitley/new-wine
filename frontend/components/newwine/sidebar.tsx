"use client";

import { useState, useEffect } from "react";
import { Plus, MoreHorizontal, X, MessageSquare, Compass, BookOpen, Loader2, ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useUserRole } from "@/hooks/useUserRole";
import { UsageRing } from "@/components/newwine/usage-ring";
import { AdminModal } from "@/components/admin/AdminModal";
import { FooterNav } from "@/components/marketing/footer-nav";
import { isFullNavEnabled } from "@/lib/chat-only-beta-flag";
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
  accessToken?: string | null;
  weeklyUsage?: { used: number; limit: number } | null;
  isOpen: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onSignInClick: () => void;
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
  accessToken,
  weeklyUsage,
  isOpen,
  onClose,
  onNewChat,
  onSignInClick,
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

  // Role — shared hook with module-level cache; avoids duplicate fetches.
  // Only displayName is used here now — role-conditional UI and account
  // settings all live inside AdminModal's Profile tab.
  const { displayName } = useUserRole(isLoggedIn ? accessToken : null);

  // Contributor request sheet
  const [contributorOpen, setContributorOpen] = useState(false);
  const [requestMessage, setRequestMessage] = useState("");
  const [requestStatus, setRequestStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [requestError, setRequestError] = useState<string | null>(null);

  // Admin modal — also hosts the Profile tab for every authenticated user
  const [adminOpen, setAdminOpen] = useState(false);

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

  function handleOpenContributor() {
    setRequestMessage("");
    setRequestStatus("idle");
    setRequestError(null);
    setContributorOpen(true);
  }

  async function handleSubmitRequest() {
    if (!accessToken) return;
    setRequestStatus("loading");
    setRequestError(null);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/pastors-notes/requests`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ message: requestMessage || null }),
      });
      if (res.status === 400) {
        const data = await res.json();
        setRequestError(data.detail ?? "You already have a pending application.");
        setRequestStatus("error");
      } else if (res.ok) {
        setRequestStatus("success");
      } else {
        setRequestError("Something went wrong. Please try again.");
        setRequestStatus("error");
      }
    } catch {
      setRequestError("Something went wrong. Please try again.");
      setRequestStatus("error");
    }
  }

  const sidebarContent = (
    <>
      {/* Wordmark + close button (mobile) */}
      <div className="flex items-center justify-between pb-4">
        <h1 className="font-sans text-2xl font-semibold text-foreground tracking-tight">
          New Wine
        </h1>
        <button
          onClick={onClose}
          aria-label="Close sidebar"
          className="rounded-md p-1 text-muted-foreground hover:text-foreground md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-ring"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* New Chat CTA */}
      <Button
        variant="ghost"
        onClick={handleNewChat}
        className="w-full min-h-[44px] mb-4 gap-2 border border-border text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground dark:hover:bg-sidebar-accent"
      >
        <Plus className="h-4 w-4 shrink-0" />
        <span>New Chat</span>
      </Button>

      {/* Nav Items — desktop only; mobile uses bottom tab bar.
          Chat-only beta: whole block gated on isFullNavEnabled(), Chat
          link included — with Study/Discover hidden there's nowhere else
          to navigate to, so a single always-active Chat link is dead
          weight. Flag on restores all three exactly as before. */}
      {isFullNavEnabled() && (
        <nav className="hidden md:block space-y-0.5 mb-4">
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
            Discover
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
      )}

      {/* Conditional Content */}
      <div className="flex-1 overflow-y-auto -mx-2 px-2">
        {isChat && isLoggedIn && (
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

      {/* Footer — profile menu or sign-in. Bottom clearance is unconditional
          (both flag states): this content was clipped by the iOS home
          indicator regardless of nav state, and additionally sits under
          the tab bar when it's present. pb-4 stays the source of truth
          on desktop — the mobile-scoped classes below only take effect
          under 768px, see globals.css. */}
      <div className={cn(
        "mt-auto pt-2 pb-4",
        isFullNavEnabled() ? "pb-drawer-footer-safe-tabbar" : "pb-drawer-footer-safe"
      )}>
        {isLoggedIn ? (
          <button
            onClick={() => setAdminOpen(true)}
            className="flex w-full items-center gap-3 rounded-md px-2 py-2 hover:bg-accent transition-colors text-left"
          >
            {weeklyUsage && (
              <UsageRing used={weeklyUsage.used} limit={weeklyUsage.limit} />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {displayName ?? user?.email ?? ""}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.email ?? ""}
              </p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          </button>
        ) : (
          <Button size="sm" className="min-h-11 w-full text-background" onClick={onSignInClick}>
            Sign in
          </Button>
        )}
      </div>

      {/* Footer nav — bottom-left of the app shell */}
      <FooterNav className="pb-2" />

      {/* Contributor request sheet */}
      <Sheet open={contributorOpen} onOpenChange={setContributorOpen}>
        <SheetContent side="right" className="flex flex-col">
          <SheetHeader>
            <SheetTitle>Apply to contribute</SheetTitle>
            <SheetDescription>
              Contributors can write pastoral notes attached to Bible verses. We review each application before granting access.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 px-4">
            {requestStatus === "success" ? (
              <p className="text-sm text-muted-foreground">
                Application submitted. We&apos;ll be in touch.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <p className="text-xs text-muted-foreground">
                    Message <span className="text-muted-foreground">(optional)</span>
                  </p>
                  <Textarea
                    placeholder="Tell us a bit about yourself..."
                    value={requestMessage}
                    onChange={(e) => setRequestMessage(e.target.value)}
                    className="resize-none"
                    rows={4}
                  />
                </div>
                {requestStatus === "error" && requestError && (
                  <p className="text-xs text-destructive">{requestError}</p>
                )}
              </div>
            )}
          </div>

          {requestStatus !== "success" && (
            <SheetFooter>
              <Button
                onClick={handleSubmitRequest}
                disabled={requestStatus === "loading"}
                className="w-full"
              >
                {requestStatus === "loading" ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Submit"
                )}
              </Button>
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>

      {/* Admin modal — also hosts Profile for every authenticated user */}
      <AdminModal
        open={adminOpen}
        onOpenChange={setAdminOpen}
        onOpenContributor={handleOpenContributor}
      />
    </>
  );

  return (
    <>
      {/* Desktop sidebar — fixed, never moves. The Study Panel (Phase 1: true
          floating overlay) opens on its own z-layer above this; it must
          never collapse, translate, or resize in response to panel state. */}
      <aside
        className="hidden md:flex fixed left-0 top-0 z-40 h-screen w-64 flex-col bg-sidebar px-4 pt-6"
      >
        {sidebarContent}
      </aside>

      {/* Mobile drawer overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}

      {/* Mobile drawer — slides in from the left, matching its top-left
          trigger. pt uses the larger of
          the original 24px and the real inset (not additive) — identical
          24px on devices where the inset is smaller or zero, grows only
          on notched/Dynamic-Island devices where 24px wasn't enough. */}
      <aside
        aria-label="Mobile navigation"
        aria-hidden={!isOpen}
        inert={!isOpen}
        className={cn(
          "fixed left-0 top-0 z-50 flex h-dvh-safe w-full flex-col bg-sidebar px-4 pt-[max(1.5rem,env(safe-area-inset-top))] transition-transform duration-300 md:hidden",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {sidebarContent}
      </aside>
    </>
  );
}
