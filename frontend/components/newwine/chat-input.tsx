"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatFocus } from "@/contexts/chat-focus-context";
import { composerMaxHeight } from "@/lib/composer-viewport";
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

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const viewportHeight = window.visualViewport?.height ?? window.innerHeight;
    const maxHeight = composerMaxHeight(viewportHeight);
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, []);

  useEffect(() => {
    const viewport = window.visualViewport;
    let animationFrame = 0;
    const scheduleResize = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(resizeTextarea);
    };

    scheduleResize();
    viewport?.addEventListener("resize", scheduleResize);
    viewport?.addEventListener("scroll", scheduleResize);
    window.addEventListener("resize", scheduleResize);
    window.addEventListener("orientationchange", scheduleResize);
    return () => {
      cancelAnimationFrame(animationFrame);
      viewport?.removeEventListener("resize", scheduleResize);
      viewport?.removeEventListener("scroll", scheduleResize);
      window.removeEventListener("resize", scheduleResize);
      window.removeEventListener("orientationchange", scheduleResize);
    };
  }, [resizeTextarea]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput("");
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.overflowY = "hidden";
      }
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
        <div className="flex items-end gap-2 rounded-2xl border border-border bg-popover px-4 py-1.5 md:py-2">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              setInputFocused(true);
              resizeTextarea();
              requestAnimationFrame(() => {
                textareaRef.current?.scrollIntoView({ block: "nearest" });
              });
            }}
            onBlur={() => setInputFocused(false)}
            placeholder="Enter your prompt..."
            aria-label="Ask a question about Scripture or theology"
            disabled={disabled}
            rows={1}
            className="min-h-11 min-w-0 max-h-[min(12rem,32dvh)] flex-1 resize-none overflow-y-hidden bg-transparent py-2.5 text-sm leading-normal text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-50"
            onInput={resizeTextarea}
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
