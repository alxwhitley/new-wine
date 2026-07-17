"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Menu, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatFocus } from "@/contexts/chat-focus-context";
import { useAuth } from "@/hooks/useAuth";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import { ChatMessage } from "@/components/rhemata/chat-message";
import { ChatInput } from "@/components/rhemata/chat-input";
import { SourcePanel } from "@/components/rhemata/source-panel";
import { StudyPanel, StudyPanelEdgeTab } from "@/components/rhemata/study-panel";
import { LoadingIndicator } from "@/components/rhemata/loading-indicator";
import { UsageRing } from "@/components/rhemata/usage-ring";
import { WeeklyLimitCard } from "@/components/rhemata/weekly-limit-card";
import LoginModal from "@/components/auth/LoginModal";
import BetaGate from "@/components/auth/BetaGate";
import type { Citation } from "@/lib/api";
import type { WeeklyLimitDetail } from "@/hooks/useChat";
import { referenceKey, type StudyReference } from "@/lib/study-reference";
import { isStudyPanelEnabled } from "@/lib/study-panel-flag";

// Dev-only demo reference for the always-available trigger below — lets the
// panel be opened regardless of chat content. Real triggers come from
// tapping a detected verse reference inside an actual answer.
const DEV_DEMO_REFERENCE: StudyReference = {
  type: "verse",
  raw: "Romans 8:28",
  book: "Romans",
  code: "ROM",
  chapter: 8,
  verseStart: 28,
  verseEnd: null,
};

const SUGGESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "Is speaking in tongues for today?",
  "How do I hear God's voice?",
];

export default function Home() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [showGate, setShowGate] = useState(false);
  const [loginInitialMode, setLoginInitialMode] = useState<"signin" | "signup">("signup");
  const [loginReason, setLoginReason] = useState<string | undefined>();

  function openAuthGate(mode: "signin" | "signup" = "signup") {
    setLoginInitialMode(mode);
    if (typeof window !== "undefined" && sessionStorage.getItem("beta_access") === "1") {
      setShowLogin(true);
    } else {
      setShowGate(true);
    }
  }
  const [weeklyLimitDetail, setWeeklyLimitDetail] = useState<WeeklyLimitDetail | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [lastQuery, setLastQuery] = useState<string | null>(null);
  const {
    messages,
    loading: chatLoading,
    error: chatError,
    conversationId,
    weeklyUsage,
    sendMessage,
    clearMessages,
    loadConversation,
  } = useChat(
    accessToken,
    () => {
      setLoginReason("You've used your 6 free searches. Create a free account to keep going.");
      openAuthGate("signup");
    },
    (detail) => setWeeklyLimitDetail(detail),
  );
  const {
    conversations,
    addOrUpdate,
    deleteConversation,
    loadMessages,
  } = useConversations(user?.id);

  // Source panel state
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedCitationIndex, setSelectedCitationIndex] = useState<number | null>(null);
  const [isSourcePanelOpen, setIsSourcePanelOpen] = useState(false);

  // Inline Study Panel state (SP2 shell — docs/inline-study-panel-spec.md)
  const [studyPanelOpen, setStudyPanelOpen] = useState(false);
  const [studyReference, setStudyReference] = useState<StudyReference | null>(null);
  // In-memory only this session — persistence across reloads is deferred
  // (see rhemata-status.md). Cap of 4 per spec.
  const [studyPins, setStudyPins] = useState<StudyReference[]>([]);

  const handleVerseClick = useCallback((reference: StudyReference) => {
    if (!isStudyPanelEnabled()) return; // defense in depth — kill switch off
    setStudyReference(reference);
    setStudyPanelOpen(true);
  }, []);

  const handleCloseStudyPanel = useCallback(() => {
    setStudyPanelOpen(false);
  }, []);

  const handleToggleStudyPin = useCallback((reference: StudyReference) => {
    setStudyPins((prev) => {
      const key = referenceKey(reference);
      if (prev.some((p) => referenceKey(p) === key)) {
        return prev.filter((p) => referenceKey(p) !== key);
      }
      if (prev.length >= 4) return prev; // cap reached — silently ignore, per spec's "cap of 4"
      return [...prev, reference];
    });
  }, []);

  const handleOpenPinnedFromEdgeTab = useCallback(() => {
    setStudyPins((prev) => {
      if (prev.length > 0) setStudyReference(prev[prev.length - 1]);
      return prev;
    });
    setStudyPanelOpen(true);
  }, []);

  // Dev-only demonstration trigger — Cmd/Ctrl+Shift+S opens the panel
  // regardless of chat content, so the shell is always demonstrable.
  useEffect(() => {
    if (!isStudyPanelEnabled()) return; // kill switch off — never register the listener
    function onKeydown(e: globalThis.KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleVerseClick(DEV_DEMO_REFERENCE);
      }
    }
    document.addEventListener("keydown", onKeydown);
    return () => document.removeEventListener("keydown", onKeydown);
  }, [handleVerseClick]);

  // Auto-scroll — only when user is already near the bottom
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < 150) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, chatLoading]);

  // / shortcut focuses the chat textarea
  useEffect(() => {
    function onSlash(e: globalThis.KeyboardEvent) {
      if (
        e.key === "/" &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !(document.activeElement instanceof HTMLInputElement) &&
        !(document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        document.querySelector<HTMLTextAreaElement>("textarea")?.focus();
      }
    }
    document.addEventListener("keydown", onSlash);
    return () => document.removeEventListener("keydown", onSlash);
  }, []);

  const handleSend = useCallback(
    async (question: string) => {
      setLastQuery(question);
      const newConvId = await sendMessage(question);
      if (newConvId && user) {
        const title = question.split(/\s+/).slice(0, 6).join(" ");
        addOrUpdate(newConvId, title);
      }
    },
    [sendMessage, user, addOrUpdate],
  );

  function handleNewChat() {
    clearMessages();
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
  }

  function handleRetry() {
    if (!lastQuery) return;
    handleNewChat();
    handleSend(lastQuery);
  }

  async function handleSelectConversation(id: string) {
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    const msgs = await loadMessages(id);
    loadConversation(id, msgs);
  }

  async function handleDeleteConversation(id: string) {
    await deleteConversation(id);
    if (conversationId === id) {
      clearMessages();
    }
  }

  function handleCitationClick(citation: Citation, index: number) {
    setSelectedCitation(citation);
    setSelectedCitationIndex(index);
    setIsSourcePanelOpen(true);
  }

  function handleCloseSourcePanel() {
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    setSelectedCitationIndex(null);
  }

  const isEmpty = messages.length === 0;
  const { inputFocused } = useChatFocus();

  const [greeting, setGreeting] = useState("What would you like to learn about?");
  useEffect(() => {
    const h = new Date().getHours();
    if (h >= 5 && h < 12) setGreeting("Good morning, what would you like to learn about?");
    else if (h >= 12 && h < 17) setGreeting("Good afternoon, what would you like to learn about?");
    else if (h >= 17 && h < 21) setGreeting("Good evening, what would you like to learn about?");
    else setGreeting("You're up late. What would you like to explore?");
  }, []);

  return (
    // Outermost shell: sidebar tone, full viewport
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
      {/* Sidebar sits directly on this canvas */}
      <Sidebar
        conversations={conversations}
        activeConversationId={conversationId}
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        weeklyUsage={weeklyUsage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onSignInClick={() => { setLoginReason(undefined); openAuthGate("signup"); }}
        onSignOut={signOut}
        collapsed={studyPanelOpen}
      />

      {/* Floating panel wrapper — inset on desktop, full-bleed on mobile.
          Margin collapses in step with the sidebar (same 300ms timing) so
          the two read as one motion when the Study Panel opens. The
          right-side padding below reserves the Study Panel's own width
          (kept in sync with study-panel.tsx's w-[33vw] min-w-[380px]
          max-w-[480px]) so the chat card actually resizes to "about
          two-thirds" per spec, instead of the panel silently overlapping
          — and re-centering — content meant for the full-width card. */}
      <main
        className={cn(
          "flex flex-1 min-w-0 min-h-0 md:p-2 md:pb-2 transition-[margin-left,padding-right] duration-300 ease-in-out motion-reduce:transition-none",
          studyPanelOpen ? "md:ml-0 md:pr-[clamp(380px,33vw,480px)]" : "md:ml-64",
          inputFocused ? "pb-0" : "pb-14"
        )}
      >
        {/* The floating panel — bordered card on desktop, full-bleed on mobile */}
        <div className="relative flex flex-col flex-1 min-h-0 bg-background md:rounded-xl md:border md:border-border overflow-hidden">

          {/* Mobile floating menu button — replaces full-width bar on mobile */}
          <button
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
            className="md:hidden absolute top-3 left-3 z-30 h-11 w-11 flex items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>
          {/* usage ring moved to drawer (Pass B) */}

          {/* Top bar — desktop only (mobile uses floating button above) */}
          <div className="hidden md:flex h-14 shrink-0 items-center px-6 z-30 border-b border-border" />

          {isEmpty ? (
            /* Empty state — centred, full remaining height */
            <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-6 overflow-hidden overscroll-none min-h-0">
              <h2 suppressHydrationWarning className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center max-w-lg text-balance">
                {greeting}
              </h2>

              <div className="w-full max-w-3xl mt-8">
                <ChatInput onSend={handleSend} disabled={chatLoading} streaming={chatLoading} />
              </div>

              <div className="flex flex-col items-center w-full max-w-xl mt-2 gap-2 mx-auto">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSend(s)}
                    className="w-full min-h-[44px] text-left rounded-lg border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-accent transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {s}
                  </button>
                ))}
              </div>

              {chatError && (
                <div className="flex items-center gap-3 mt-4">
                  <p role="alert" aria-live="polite" className="text-sm text-destructive">{chatError}</p>
                  {lastQuery && (
                    <button onClick={handleRetry} className="shrink-0 text-sm text-primary hover:underline transition-colors">
                      Try again
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            /* Chat thread */
            <>
              {/* Scrollable message list — panel corners never clipped */}
              <div ref={scrollContainerRef} className="flex-1 overflow-y-auto min-h-0">
                {/* Scroll fade: messages dissolve into background as they pass the top */}
                <div className="pointer-events-none sticky top-0 z-10 h-14 md:h-8 bg-gradient-to-b from-background to-transparent" />
                <div className="mx-auto max-w-3xl px-4 md:px-6 pt-4 md:pt-2 pb-8">
                  {messages.map((message, i) => {
                    const question = message.role === "assistant" && i > 0 && messages[i - 1].role === "user"
                      ? messages[i - 1].content
                      : undefined;
                    const isStreaming = chatLoading && message.role === "assistant" && i === messages.length - 1;
                    return (
                      <ChatMessage
                        key={i}
                        role={message.role}
                        content={message.content}
                        citations={message.citations}
                        messageId={message.messageId}
                        question={question}
                        accessToken={accessToken}
                        onCitationClick={handleCitationClick}
                        onVerseClick={handleVerseClick}
                        isStreaming={isStreaming}
                        verifiedReferences={message.verifiedReferences}
                      />
                    );
                  })}

                  {chatLoading && messages.length > 0 && messages[messages.length - 1].content === "" && (
                    <LoadingIndicator />
                  )}

                  {/* Weekly limit hard-stop — renders where the blocked answer would appear */}
                  {weeklyLimitDetail && (
                    <div className="mt-4">
                      <WeeklyLimitCard
                        limit={weeklyLimitDetail.limit}
                        resets={weeklyLimitDetail.resets}
                        onNewChat={handleNewChat}
                      />
                    </div>
                  )}

                  {chatError && (
                    <div className="flex items-center gap-3 mt-2">
                      <p role="alert" aria-live="polite" className="text-sm text-destructive">{chatError}</p>
                      {lastQuery && (
                        <button onClick={handleRetry} className="shrink-0 text-sm text-primary hover:underline transition-colors">
                          Try again
                        </button>
                      )}
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Fixed input area — stays at panel bottom */}
              <ChatInput onSend={handleSend} disabled={chatLoading || !!weeklyLimitDetail} streaming={chatLoading} />
            </>
          )}
        </div>
      </main>

      {/* Right source panel — outside the floating panel so Sheet renders above it */}
      <SourcePanel
        citation={selectedCitation}
        citationIndex={selectedCitationIndex}
        isOpen={isSourcePanelOpen}
        onClose={handleCloseSourcePanel}
      />

      {/* Inline Study Panel (SP2 shell) — outside the floating panel, same
          reasoning as SourcePanel above. */}
      <StudyPanel
        isOpen={studyPanelOpen}
        onClose={handleCloseStudyPanel}
        reference={studyReference}
        pins={studyPins}
        onTogglePin={handleToggleStudyPin}
      />
      <StudyPanelEdgeTab
        pins={studyPins}
        panelOpen={studyPanelOpen}
        onOpenPins={handleOpenPinnedFromEdgeTab}
      />

      {/* Dev-only demonstration trigger — opens the Study Panel regardless of
          chat content. Cmd/Ctrl+Shift+S does the same. Gated by the
          NEXT_PUBLIC_STUDY_PANEL_ENABLED kill switch — absent from the DOM
          entirely when the flag is off, not just disabled-looking. */}
      {isStudyPanelEnabled() && (
        <button
          onClick={() => handleVerseClick(DEV_DEMO_REFERENCE)}
          title="Open Study Panel (dev) — Cmd/Ctrl+Shift+S"
          className="fixed bottom-20 right-4 z-30 flex items-center gap-1.5 rounded-full border border-border bg-popover px-3 py-1.5 text-xs text-muted-foreground shadow-sm transition-colors hover:bg-accent hover:text-foreground md:bottom-4"
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Study preview
        </button>
      )}

      {showGate && (
        <BetaGate
          onSuccess={() => { setShowGate(false); setShowLogin(true); }}
          onClose={() => setShowGate(false)}
        />
      )}
      {showLogin && (
        <LoginModal
          onClose={() => { setShowLogin(false); setLoginReason(undefined); }}
          onSignIn={signIn}
          onSignUp={signUp}
          reason={loginReason}
          initialMode={loginInitialMode}
        />
      )}
    </div>
  );
}
