"use client";

import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatFocus } from "@/contexts/chat-focus-context";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  /** Parent owns horizontal spacing, as in the empty-state prompt cluster. */
  embedded?: boolean;
}

export function ChatInput({
  onSend,
  disabled,
  embedded = false,
}: ChatInputProps) {
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
    <div className={cn(
      "shrink-0 bg-background",
      embedded ? undefined : "px-4 pb-2 md:px-12 md:pb-6",
    )}>
      <form
        onSubmit={handleSubmit}
        className={cn("mx-auto", embedded ? "max-w-none" : "max-w-2xl")}
      >
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-popover px-4 py-1.5 md:py-2 transition-[box-shadow,border-color] focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
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
            className="min-h-11 min-w-0 max-h-[200px] flex-1 resize-none bg-transparent py-2.5 text-sm leading-normal text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
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
