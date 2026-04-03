"use client";

import { useEffect, useRef } from "react";
import { Message as MessageType } from "@/hooks/useChat";
import Message from "./Message";

interface MessageListProps {
  messages: MessageType[];
  loading: boolean;
}

export default function MessageList({ messages, loading }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div
      ref={scrollRef}
      style={{
        flex: 1,
        overflowY: "auto",
        padding: "24px 32px 40px",
        minHeight: 0,
      }}
    >
      <div
        style={{
          maxWidth: "620px",
          margin: "0 auto",
          display: "flex",
          flexDirection: "column",
          gap: "28px",
        }}
      >
        {messages.map((message, i) => (
          <div key={i}>
            <Message message={message} />
          </div>
        ))}
        {loading && (
          <div style={{ animation: "fade-in 0.2s ease-out" }}>
            <div
              style={{
                fontSize: "18px",
                color: "#c1c1b8",
                display: "flex",
                gap: "2px",
              }}
            >
              <span style={{ animation: "pulse-dot 1.4s infinite ease-in-out", animationDelay: "0s" }}>.</span>
              <span style={{ animation: "pulse-dot 1.4s infinite ease-in-out", animationDelay: "0.2s" }}>.</span>
              <span style={{ animation: "pulse-dot 1.4s infinite ease-in-out", animationDelay: "0.4s" }}>.</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
