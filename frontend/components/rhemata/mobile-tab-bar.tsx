"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, BookOpen, Compass } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-mobile";

const TABS = [
  { href: "/study", label: "Study", icon: BookOpen },
  { href: "/", label: "Chat", icon: MessageSquare, primary: true },
  { href: "/library", label: "Discover", icon: Compass },
];

export function MobileTabBar() {
  const isMobile = useIsMobile();
  const pathname = usePathname();

  if (!isMobile) return null;

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex md:hidden bg-sidebar border-t border-border pb-safe">
      {TABS.map(({ href, label, icon: Icon, primary }) => {
        const isActive =
          href === "/"
            ? pathname === "/" || pathname.startsWith("/chat")
            : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex flex-1 flex-col items-center justify-center gap-1 min-h-[56px] transition-colors",
              primary || isActive ? "text-primary" : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            <span className="text-[10px] font-medium">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
