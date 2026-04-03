"use client";

import { useState } from "react";
import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import { Message } from "@/hooks/useChat";

interface ChatViewProps {
  messages: Message[];
  loading: boolean;
  error: string | null;
  onSend: (message: string) => void;
}

const SUGGESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "Is speaking in tongues for today?",
  "How do I hear God's voice?",
];

export default function ChatView({
  messages,
  loading,
  error,
  onSend,
}: ChatViewProps) {
  const [focused, setFocused] = useState(false);
  const isEmpty = messages.length === 0;

  if (isEmpty) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "32px",
        }}
      >
        <h2
          style={{
            fontFamily: "var(--font-lora), Lora, serif",
            fontSize: "30px",
            fontWeight: 400,
            color: "#e6e6e6",
            marginBottom: "28px",
          }}
        >
          {(() => {
            const hour = new Date().getHours();
            const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
            return `${greeting}. What would you like to learn about?`;
          })()}
        </h2>

        <div style={{ width: "100%", maxWidth: "620px", marginBottom: "20px" }}>
          <ChatInput onSend={onSend} disabled={loading} />
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: "100%",
            maxWidth: "620px",
            gap: "6px",
          }}
        >
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => onSend(s)}
              style={{
                width: "100%",
                textAlign: "left",
                background: "#1b1b19",
                border: "1px solid #2a2a28",
                borderRadius: "9999px",
                padding: "10px 14px",
                fontSize: "13px",
                fontFamily: "var(--font-inter), Inter, sans-serif",
                color: "#c1c1b8",
                cursor: "pointer",
                transition: "border-color 150ms, color 150ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "#b49238";
                e.currentTarget.style.color = "#e6e6e6";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "#2a2a28";
                e.currentTarget.style.color = "#c1c1b8";
              }}
            >
              {s}
            </button>
          ))}
        </div>

        {error && (
          <p
            style={{
              fontSize: "13px",
              color: "#e57373",
              marginTop: "16px",
            }}
          >
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <MessageList
        messages={messages}
        loading={loading}
      />
      {error && (
        <div style={{ padding: "0 32px" }}>
          <p
            style={{
              fontSize: "13px",
              color: "#e57373",
              maxWidth: "620px",
              margin: "0 auto",
            }}
          >
            {error}
          </p>
        </div>
      )}
      <div
        style={{
          flexShrink: 0,
          borderTop: "none",
          background: "#1f1e1d",
          padding: "16px 24px",
          transition: "border-color 150ms",
        }}
      >
        <ChatInput onSend={onSend} disabled={loading} onFocusChange={setFocused} />
      </div>
    </div>
  );
}
