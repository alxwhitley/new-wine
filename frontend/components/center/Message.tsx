"use client";

import ReactMarkdown from "react-markdown";
import { Message as MessageType } from "@/hooks/useChat";

interface MessageProps {
  message: MessageType;
}

export default function Message({ message }: MessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
        animation: "fade-in 0.25s ease-out",
      }}
    >
      <div
        style={{
          maxWidth: "85%",
          fontSize: "14px",
          lineHeight: "1.8",
          fontFamily: "var(--font-inter), Inter, sans-serif",
          color: "#e6e6e6",
          ...(isUser
            ? {
                whiteSpace: "pre-wrap",
                background: "#262624",
                border: "1px solid #3c3c38",
                borderRadius: "18px",
                padding: "10px 16px",
              }
            : {}),
        }}
      >
        {isUser ? (
          message.content
        ) : (
          <ReactMarkdown
            components={{
              h2: ({ children }) => (
                <h2
                  style={{
                    fontFamily: "var(--font-lora), Lora, serif",
                    fontSize: "1.1rem",
                    fontWeight: 600,
                    color: "#e6e6e6",
                    margin: "20px 0 8px",
                  }}
                >
                  {children}
                </h2>
              ),
              h3: ({ children }) => (
                <h3
                  style={{
                    fontFamily: "var(--font-lora), Lora, serif",
                    fontSize: "16px",
                    fontWeight: 600,
                    color: "#e6e6e6",
                    margin: "16px 0 6px",
                  }}
                >
                  {children}
                </h3>
              ),
              p: ({ children }) => (
                <p style={{ margin: "0 0 12px" }}>{children}</p>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>
    </div>
  );
}
