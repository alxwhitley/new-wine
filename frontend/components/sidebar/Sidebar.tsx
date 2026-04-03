"use client";

import Logo from "./Logo";
import { Conversation } from "@/hooks/useConversations";
import { Plus } from "lucide-react";

interface SidebarProps {
  isLoggedIn: boolean;
  conversations: Conversation[];
  activeConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (id: string) => void;
  onSignInClick: () => void;
}

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

export default function Sidebar({
  isLoggedIn,
  conversations,
  activeConversationId,
  onNewChat,
  onSelectConversation,
  onSignInClick,
}: SidebarProps) {
  return (
    <aside
      style={{
        display: "flex",
        flexDirection: "column",
        width: "200px",
        flexShrink: 0,
        height: "100vh",
        background: "#1b1b19",
        borderRight: "1px solid #2a2a28",
        padding: "20px 16px",
      }}
    >
      <Logo />

      <button
        onClick={onNewChat}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          width: "100%",
          padding: "8px 10px",
          borderRadius: "7px",
          fontSize: "13px",
          fontWeight: 500,
          fontFamily: "var(--font-inter), Inter, sans-serif",
          color: "#e6e6e6",
          background: "#262624",
          border: "1px solid #3c3c38",
          cursor: "pointer",
          transition: "border-color 150ms",
          marginBottom: "16px",
        }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = "#b49238"; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = "#3c3c38"; }}
      >
        <Plus size={14} strokeWidth={2} />
        New chat
      </button>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "1px",
        }}
      >
        {isLoggedIn ? (
          conversations.length > 0 ? (
            conversations.map((c) => {
              const isActive = c.id === activeConversationId;
              return (
                <button
                  key={c.id}
                  onClick={() => onSelectConversation(c.id)}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "2px",
                    width: "100%",
                    padding: "8px 10px",
                    borderRadius: "7px",
                    textAlign: "left",
                    fontSize: "13px",
                    fontFamily: "var(--font-inter), Inter, sans-serif",
                    color: isActive ? "#e6e6e6" : "#c1c1b8",
                    background: isActive ? "#262624" : "transparent",
                    cursor: "pointer",
                    transition: "background 150ms, color 150ms",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = "#262624";
                      e.currentTarget.style.color = "#e6e6e6";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.background = "transparent";
                      e.currentTarget.style.color = "#c1c1b8";
                    }
                  }}
                >
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {c.title}
                  </span>
                  <span style={{ fontSize: "11px", color: "#888" }}>
                    {relativeTime(c.updated_at)}
                  </span>
                </button>
              );
            })
          ) : (
            <p
              style={{
                fontSize: "12px",
                color: "#888",
                fontFamily: "var(--font-inter), Inter, sans-serif",
                padding: "8px 10px",
                margin: 0,
              }}
            >
              No conversations yet
            </p>
          )
        ) : (
          <button
            onClick={onSignInClick}
            style={{
              fontSize: "12px",
              color: "#888",
              fontFamily: "var(--font-inter), Inter, sans-serif",
              padding: "8px 10px",
              textAlign: "left",
              cursor: "pointer",
              transition: "color 150ms",
            }}
            onMouseEnter={(e) => { e.currentTarget.style.color = "#b49238"; }}
            onMouseLeave={(e) => { e.currentTarget.style.color = "#888"; }}
          >
            Sign in to save your conversations
          </button>
        )}
      </div>
    </aside>
  );
}
