"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const modes = [
  { label: "Chat", href: "/" },
  { label: "Study", href: "/study" },
] as const;

export function ModeToggle() {
  const pathname = usePathname();

  return (
    <div
      className="flex rounded-full p-0.5"
      style={{ backgroundColor: "#262624" }}
    >
      {modes.map(({ label, href }) => {
        const isActive =
          href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className="rounded-full px-4 py-1 text-sm font-medium transition-colors"
            style={{
              backgroundColor: isActive ? "#b49238" : "transparent",
              color: isActive ? "#1b1b19" : "#c1c1b8",
            }}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
