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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const {
    messages,
    loading: chatLoading,
    error: chatError,
    conversationId,
    sendMessage,
    clearMessages,
    loadConversation,
  } = useChat(accessToken, () => {
    setLoginReason("You've used your 6 free searches. Create a free account to keep going.");
    setShowLogin(true);
  });
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
    console.log("[DELETE TRACE] 4. handleDeleteConversation called in page.tsx for:", id);
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
    else setGreeting("You\u2019re up late. What would you like to explore?");
  }, []);

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
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

      {/* Main Content Area */}
      <main className="md:ml-64 flex flex-1 flex-col min-w-0 h-screen">
        {/* Top Bar */}
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
          {/* Mobile: hamburger */}
          <button
            onClick={() => setSidebarOpen(true)}
            className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Mobile: centered wordmark */}
          <h1 className="md:hidden flex-1 text-center font-serif text-lg font-semibold text-foreground">
            Rhemata
          </h1>

          {/* Mobile: spacer to balance hamburger */}
          <div className="md:hidden min-w-[44px]" />

          {/* Desktop: auth button */}
          <div className="hidden md:flex ml-auto">
            <AuthButton
              user={user}
              onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
              onSignOut={signOut}
            />
          </div>
        </div>

        {isEmpty ? (
          /* Empty state */
          <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-6">
            <h2 className="font-serif text-2xl md:text-3xl font-semibold text-foreground text-center max-w-lg">
              {greeting}
            </h2>

            <div className="w-full max-w-3xl mt-8">
              <ChatInput onSend={handleSend} disabled={chatLoading} />
            </div>

            <div className="flex flex-col items-center w-full max-w-xl mt-2 gap-2 mx-auto">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSend(s)}
                  className="w-full min-h-[44px] text-left rounded-full border border-border bg-card px-4 py-2 text-sm text-muted-foreground hover:border-primary hover:text-foreground transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>

            {chatError && (
              <p className="text-sm text-red-400 mt-4">{chatError}</p>
            )}
          </div>
        ) : (
          /* Chat thread */
          <>
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-3xl px-4 md:px-6 pt-8 pb-8">
                {messages.map((message, i) => (
                  <ChatMessage
                    key={i}
                    role={message.role}
                    content={message.content}
                    citations={message.citations}
                    onCitationClick={handleCitationClick}
                  />
                ))}

                {chatLoading && messages.length > 0 && messages[messages.length - 1].content === "" && (
                  <LoadingIndicator />
                )}

                {chatError && (
                  <p className="text-sm text-red-400 mt-2">{chatError}</p>
                )}

                <div ref={bottomRef} />
              </div>
            </div>

            {/* Fixed Input Bar */}
            <ChatInput onSend={handleSend} disabled={chatLoading} />
          </>
        )}
      </main>

      {/* Right Source Panel */}
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
