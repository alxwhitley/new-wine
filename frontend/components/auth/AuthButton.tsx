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
          color: "#c1c1b8",
          background: "transparent",
          border: "1px solid #3c3c38",
          cursor: "pointer",
          transition: "border-color 150ms, color 150ms",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "#b49238";
          e.currentTarget.style.color = "#e6e6e6";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = "#3c3c38";
          e.currentTarget.style.color = "#c1c1b8";
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
          color: "#c1c1b8",
          background: "transparent",
          border: "1px solid #3c3c38",
          cursor: "pointer",
          transition: "border-color 150ms, color 150ms",
          maxWidth: "200px",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = "#b49238";
          e.currentTarget.style.color = "#e6e6e6";
        }}
        onMouseLeave={(e) => {
          if (!menuOpen) {
            e.currentTarget.style.borderColor = "#3c3c38";
            e.currentTarget.style.color = "#c1c1b8";
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
              background: "#262624",
              border: "1px solid #3c3c38",
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
                color: "#c1c1b8",
                cursor: "pointer",
                transition: "background 150ms, color 150ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "#1f1e1d";
                e.currentTarget.style.color = "#e6e6e6";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
                e.currentTarget.style.color = "#c1c1b8";
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
