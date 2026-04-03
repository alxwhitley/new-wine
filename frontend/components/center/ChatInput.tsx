"use client";

import { useState, useRef, useEffect } from "react";
import { ArrowUp } from "lucide-react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
  onFocusChange?: (focused: boolean) => void;
}

export default function ChatInput({ onSend, disabled, onFocusChange }: ChatInputProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "22px";
      el.style.height = Math.min(el.scrollHeight, 120) + "px";
    }
  }, [value]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (value.trim() && !disabled) {
      onSend(value.trim());
      setValue("");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ width: "100%" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          maxWidth: "620px",
          margin: "0 auto",
          background: "#262624",
          border: focused ? "1px solid rgba(230, 230, 230, 1)" : "1px solid rgba(230, 230, 230, 0.35)",
          borderRadius: "9999px",
          padding: "10px 14px",
          transition: "border-color 150ms",
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => { setFocused(true); onFocusChange?.(true); }}
          onBlur={() => { setFocused(false); onFocusChange?.(false); }}
          placeholder="Enter your prompt..."
          disabled={disabled}
          rows={1}
          style={{
            flex: 1,
            background: "transparent",
            fontSize: "14px",
            fontFamily: "var(--font-inter), Inter, sans-serif",
            color: "#e6e6e6",
            resize: "none",
            lineHeight: "1.5",
            minHeight: "22px",
            maxHeight: "120px",
          }}
        />
        <button
          type="submit"
          disabled={disabled || !value.trim()}
          style={{
            flexShrink: 0,
            width: "30px",
            height: "30px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: "7px",
            background: value.trim() ? "#b49238" : "#3c3c38",
            color: value.trim() ? "#1b1b19" : "#c1c1b8",
            cursor: disabled || !value.trim() ? "default" : "pointer",
            opacity: disabled ? 0.4 : 1,
            transition: "background 150ms, color 150ms",
          }}
          onMouseEnter={(e) => {
            if (value.trim() && !disabled) {
              e.currentTarget.style.background = "#c9a843";
            }
          }}
          onMouseLeave={(e) => {
            if (value.trim() && !disabled) {
              e.currentTarget.style.background = "#b49238";
            }
          }}
        >
          <ArrowUp size={14} strokeWidth={2.5} />
        </button>
      </div>
    </form>
  );
}
