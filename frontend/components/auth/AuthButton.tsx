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
        className="rounded-lg border border-border px-3 py-1.5 text-[13px] font-medium text-muted-foreground transition-colors hover:border-gold hover:text-foreground"
      >
        Sign in
      </button>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setMenuOpen(!menuOpen)}
        className="max-w-[200px] truncate rounded-lg border border-border px-3 py-1.5 text-[13px] text-muted-foreground transition-colors hover:border-gold hover:text-foreground"
      >
        {user.email}
      </button>

      {menuOpen && (
        <>
          <div
            onClick={() => setMenuOpen(false)}
            className="fixed inset-0 z-49"
          />
          <div className="absolute right-0 top-[calc(100%+6px)] z-50 min-w-[140px] rounded-lg border border-border bg-card p-1">
            <button
              onClick={() => {
                setMenuOpen(false);
                onSignOut();
              }}
              className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
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
