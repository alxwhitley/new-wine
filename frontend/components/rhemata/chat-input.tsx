"use client";

import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatFocus } from "@/contexts/chat-focus-context";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { setInputFocused } = useChatFocus();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput("");
      if (textareaRef.current) textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="shrink-0 bg-background px-4 md:px-12 pb-2 md:pb-6">
      <form onSubmit={handleSubmit} className="mx-auto max-w-2xl">
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-popover px-4 py-1.5 focus-within:ring-1 focus-within:ring-ring md:py-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            placeholder="Enter your prompt..."
            aria-label="Ask a question about Scripture or theology"
            disabled={disabled}
            rows={1}
            className="min-w-0 flex-1 resize-none bg-transparent py-0 text-sm leading-normal text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50 min-h-6 max-h-[200px]"
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement;
              target.style.height = "auto";
              target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
            }}
          />
          <Button
            type="submit"
            disabled={!input.trim() || disabled}
            size="icon"
            className="min-h-[44px] min-w-[44px] shrink-0 rounded-2xl bg-primary text-background hover:bg-primary/90 disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
            <span className="sr-only">Send message</span>
          </Button>
        </div>
      </form>
    </div>
  );
}
