"use client";

import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MobileTabBar } from "@/components/newwine/mobile-tab-bar";
import { ChatFocusProvider } from "@/contexts/chat-focus-context";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      forcedTheme="dark"
      disableTransitionOnChange
    >
      <ChatFocusProvider>
        <TooltipProvider>
          {children}
          <MobileTabBar />
        </TooltipProvider>
      </ChatFocusProvider>
    </ThemeProvider>
  );
}
