"use client";

import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { MobileTabBar } from "@/components/rhemata/mobile-tab-bar";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      forcedTheme="dark"
      disableTransitionOnChange
    >
      <TooltipProvider>
        {children}
        <MobileTabBar />
      </TooltipProvider>
    </ThemeProvider>
  );
}
