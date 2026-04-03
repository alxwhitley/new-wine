"use client";

import { useState, useCallback } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import Sidebar from "@/components/sidebar/Sidebar";
import CenterPanel from "@/components/center/CenterPanel";
import AuthButton from "@/components/auth/AuthButton";
import LoginModal from "@/components/auth/LoginModal";

export default function Home() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
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
    loadMessages,
  } = useConversations(user?.id);

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
  }

  async function handleSelectConversation(id: string) {
    const msgs = await loadMessages(id);
    loadConversation(id, msgs);
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        isLoggedIn={!!user}
        conversations={conversations}
        activeConversationId={conversationId}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
      />
      <CenterPanel
        messages={messages}
        chatLoading={chatLoading}
        chatError={chatError}
        onSendMessage={handleSend}
      />
      <AuthButton
        user={user}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
        onSignOut={signOut}
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
