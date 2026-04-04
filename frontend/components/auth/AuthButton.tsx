"use client";

import { useState } from "react";
import { User } from "@supabase/supabase-js";
import { LogOut } from "lucide-react";

interface AuthButtonProps {
  user: User | null;
  onSignInClick: () => void;
  onSignOut: () => void;
}

export default function AuthButton({ user, onSignInClick, onSignOut }: AuthButtonProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  if (!user) {
    return (
      <button
        onClick={onSignInClick}
        style={{
          position: "fixed",
          top: "16px",
          right: "20px",
          zIndex: 50,
          padding: "6px 14px",
          borderRadius: "7px",
          fontSize: "13px",
          fontWeight: 500,
          fontFamily: "var(--font-inter), Inter, sans-serif",
          color: "var(--muted-foreground)",
          background: "transparent",
          border: "1px solid var(--border)",
          cursor: "pointer",
          transition: "border-color 150ms, color 150ms",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--gold)";
          e.currentTarget.style.color = "var(--foreground)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "var(--border)";
          e.currentTarget.style.color = "var(--muted-foreground)";
        }}
      >
        Sign in
      </button>
    );
  }

  return (
    <div style={{ position: "fixed", top: "16px", right: "20px", zIndex: 50 }}>
      <button
        onClick={() => setMenuOpen(!menuOpen)}
        style={{
          padding: "6px 14px",
          borderRadius: "7px",
          fontSize: "13px",
          fontFamily: "var(--font-inter), Inter, sans-serif",
          color: "var(--muted-foreground)",
          background: "transparent",
          border: "1px solid var(--border)",
          cursor: "pointer",
          transition: "border-color 150ms, color 150ms",
          maxWidth: "200px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "var(--gold)";
          e.currentTarget.style.color = "var(--foreground)";
        }}
        onMouseLeave={(e) => {
          if (!menuOpen) {
            e.currentTarget.style.borderColor = "var(--border)";
            e.currentTarget.style.color = "var(--muted-foreground)";
          }
        }}
      >
        {user.email}
      </button>

      {menuOpen && (
        <>
          <div
            onClick={() => setMenuOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 49 }}
          />
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              right: 0,
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "4px",
              zIndex: 51,
              minWidth: "140px",
            }}
          >
            <button
              onClick={() => {
                setMenuOpen(false);
                onSignOut();
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                width: "100%",
                padding: "8px 12px",
                borderRadius: "6px",
                fontSize: "13px",
                fontFamily: "var(--font-inter), Inter, sans-serif",
                color: "var(--muted-foreground)",
                cursor: "pointer",
                transition: "background 150ms, color 150ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "var(--background)";
                e.currentTarget.style.color = "var(--foreground)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "var(--muted-foreground)";
              }}
            >
              <LogOut size={14} strokeWidth={1.8} />
              Sign out
            </button>
          </div>
        </>
      )}
    </div>
  );
}
