import Link from "next/link";
import { cn } from "@/lib/utils";

const LINKS = [
  { label: "Home", href: "/home" },
  { label: "Sources", href: "/sources" },
  { label: "Beliefs", href: "/beliefs" },
] as const;

export function FooterNav({ className }: { className?: string }) {
  return (
    <nav className={cn("flex items-center gap-1.5 text-xs text-muted-foreground/70", className)}>
      {LINKS.map((link, i) => (
        <span key={link.href} className="flex items-center gap-1.5">
          {i > 0 && <span aria-hidden="true">|</span>}
          <Link href={link.href} className="hover:text-muted-foreground transition-colors no-underline">
            {link.label}
          </Link>
        </span>
      ))}
    </nav>
  );
}
