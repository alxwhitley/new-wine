"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Menu } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import { ChatMessage } from "@/components/rhemata/chat-message";
import { ChatInput } from "@/components/rhemata/chat-input";
import { SourcePanel } from "@/components/rhemata/source-panel";
import { LoadingIndicator } from "@/components/rhemata/loading-indicator";
import { UsageRing } from "@/components/rhemata/usage-ring";
import { WeeklyLimitCard } from "@/components/rhemata/weekly-limit-card";
import LoginModal from "@/components/auth/LoginModal";
import BetaGate from "@/components/auth/BetaGate";
import type { Citation } from "@/lib/api";
import type { WeeklyLimitDetail } from "@/hooks/useChat";

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
      />

      {/* Floating panel wrapper — small inset gap on all sides */}
      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
        {/* The floating panel */}
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">

          {/* Top bar */}
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30 border-b border-border">
            <button
              aria-label="Open sidebar"
              onClick={() => setSidebarOpen(true)}
              className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex-1 md:hidden" />
            {/* Mobile usage ring — right side, only for authenticated users */}
            {user && weeklyUsage && (
              <div
                className="md:hidden"
                role="img"
                aria-label={`${weeklyUsage.used} of ${weeklyUsage.limit} queries used this week`}
              >
                <UsageRing used={weeklyUsage.used} limit={weeklyUsage.limit} />
              </div>
            )}
          </div>

          {isEmpty ? (
            /* Empty state — centred, full remaining height */
            <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-6 overflow-y-auto min-h-0">
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
                <div className="pointer-events-none sticky top-0 z-10 h-8 bg-gradient-to-b from-background to-transparent" />
                <div className="mx-auto max-w-3xl px-4 md:px-6 pt-2 pb-8">
                  {messages.map((message, i) => {
                    const question = message.role === "assistant" && i > 0 && messages[i - 1].role === "user"
                      ? messages[i - 1].content
                      : undefined;
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
