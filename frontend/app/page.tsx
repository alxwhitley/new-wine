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
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";
import type { Citation } from "@/lib/api";

const SUGGESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "Is speaking in tongues for today?",
  "How do I hear God's voice?",
];

export default function Home() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
  const [dailyLimitMessage, setDailyLimitMessage] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const {
    messages,
    loading: chatLoading,
    error: chatError,
    conversationId,
    sendMessage,
    clearMessages,
    loadConversation,
  } = useChat(
    accessToken,
    () => {
      setLoginReason("You've used your 6 free searches. Create a free account to keep going.");
      setShowLogin(true);
    },
    () => {
      setDailyLimitMessage("You've reached your daily usage limit. Your quota resets at midnight UTC.");
    },
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

  // Auto-scroll
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  const handleSend = useCallback(
    async (question: string) => {
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
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
        onSignOut={signOut}
      />

      {/* Floating panel wrapper — small inset gap on all sides */}
      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2">
        {/* The floating panel */}
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl overflow-hidden">

          {/* Top bar — no border needed; panel edge provides separation */}
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30">
            <button
              onClick={() => setSidebarOpen(true)}
              className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex-1" />
            <div className="hidden md:flex">
              <AuthButton
                user={user}
                onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
                onSignOut={signOut}
              />
            </div>
          </div>

          {isEmpty ? (
            /* Empty state — centred, full remaining height */
            <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-6 overflow-y-auto min-h-0">
              <h2 className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center max-w-lg">
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
                    className="w-full min-h-[44px] text-left rounded-lg border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-accent transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>

              {chatError && (
                <p className="text-sm text-red-400 mt-4">{chatError}</p>
              )}
              {dailyLimitMessage && (
                <p className="text-sm text-amber-300 mt-4">{dailyLimitMessage}</p>
              )}
            </div>
          ) : (
            /* Chat thread */
            <>
              {/* Scrollable message list — panel corners never clipped */}
              <div className="flex-1 overflow-y-auto min-h-0">
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

                  {chatError && (
                    <p className="text-sm text-red-400 mt-2">{chatError}</p>
                  )}

                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Fixed input area — stays at panel bottom */}
              {dailyLimitMessage && (
                <div className="mx-4 mb-2 rounded-lg bg-amber-900/50 border border-amber-700 px-4 py-3 text-sm text-amber-200">
                  {dailyLimitMessage}
                </div>
              )}
              <ChatInput onSend={handleSend} disabled={chatLoading || !!dailyLimitMessage} streaming={chatLoading} />
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
      {showLogin && (
        <LoginModal
          onClose={() => { setShowLogin(false); setLoginReason(undefined); }}
          onSignIn={signIn}
          onSignUp={signUp}
          reason={loginReason}
        />
      )}
    </div>
  );
}
