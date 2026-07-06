import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

// Shared long-form article typography for static marketing pages (/sources,
// /beliefs). Reuses the landing page's serif-heading / muted-body system
// (see app/home/page.tsx) rather than inventing a new scale, sized down for
// in-article headings instead of hero/section headlines.

export function ArticlePage({ children }: { children: ReactNode }) {
  return (
    <div className="bg-background text-foreground min-h-screen font-sans antialiased">
      <article className="max-w-2xl mx-auto px-4 pt-16 pb-24 md:pt-20 md:pb-32">
        {children}
      </article>
    </div>
  );
}

export function ArticleH1({ children }: { children: ReactNode }) {
  return (
    <h1 className="font-serif text-[clamp(1.85rem,3.5vw,2.8rem)] font-semibold leading-[1.2] text-card-foreground text-balance mb-3">
      {children}
    </h1>
  );
}

export function ArticleDek({ children }: { children: ReactNode }) {
  return (
    <p className="font-serif italic text-lg text-muted-foreground leading-[1.6] mb-8">
      {children}
    </p>
  );
}

export function ArticleDivider() {
  return <hr className="border-border mb-10" />;
}

export function ArticleH2({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-serif text-[1.4rem] font-semibold leading-[1.3] text-card-foreground mt-12 mb-4">
      {children}
    </h2>
  );
}

export function ArticleH3({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-serif text-[1.15rem] font-semibold leading-[1.3] text-card-foreground mt-8 mb-2">
      {children}
    </h3>
  );
}

export function ArticleP({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn("font-serif text-foreground leading-[1.75] mb-5", className)}>
      {children}
    </p>
  );
}

export function ArticleRefs({ children }: { children: ReactNode }) {
  return (
    <p className="font-serif italic text-sm text-muted-foreground leading-[1.6] mb-6 -mt-3">
      {children}
    </p>
  );
}

export function ArticleOl({ children }: { children: ReactNode }) {
  return (
    <ol className="list-decimal ml-6 space-y-3 font-serif text-foreground leading-[1.75] mb-5">
      {children}
    </ol>
  );
}

export function ArticleClosing({ children }: { children: ReactNode }) {
  return (
    <p className="font-serif italic text-muted-foreground leading-[1.6] mt-10">
      {children}
    </p>
  );
}
