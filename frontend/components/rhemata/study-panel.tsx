"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Dialog as PanelPrimitive } from "radix-ui";
import { Pin, PinOff, X, GraduationCap } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-mobile";
import { supabase } from "@/lib/supabase";
import {
  type StudyReference,
  verseId,
  referenceLabel,
  referenceKey,
} from "@/lib/study-reference";
import { AccordionRow } from "@/components/rhemata/accordion-row";
import { CommentaryAccordionRow } from "@/components/rhemata/commentary-accordion-row";
import { PastorsNotesSection } from "@/components/rhemata/pastors-notes";

// ── Verse text fetch ─────────────────────────────────────────────────────────
// Reuses the same `verses` table + verse_id shape already proven in
// app/study/page.tsx (read for convention, not imported — that file is
// spec-mandated read-only this session). This is the one piece of real,
// uncontroversial data (public-domain WEB text) the shell fetches for real;
// everything gated on unbuilt backend work (SP1 pointers, SP3 lexicon) stays
// an honest empty state below.

interface VerseText {
  text: string;
  translation: string;
}

function useVerseText(ref: StudyReference | null): {
  data: VerseText | null;
  loading: boolean;
  error: boolean;
} {
  const [data, setData] = useState<VerseText | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // Nothing to fetch for a non-verse (or absent) reference — short-circuited
  // below, before the effect, so there's no synchronous setState-in-effect
  // reset to perform for that case at all.
  const targetKey = ref && ref.type === "verse" ? verseId(ref) : null;

  useEffect(() => {
    if (!targetKey) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    setData(null);
    supabase
      .from("verses")
      .select("text, translation")
      .eq("verse_id", targetKey)
      .single()
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error || !data) {
          setError(true);
        } else {
          setData({ text: data.text ?? "", translation: data.translation ?? "WEB" });
        }
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [targetKey]);

  if (!targetKey) return { data: null, loading: false, error: false };
  return { data, loading, error };
}

// ── Teachers-on-verse fetch (SP2 Phase 4) ────────────────────────────────────
// Replaces a previously hardcoded, unconditional "none of your teachers"
// claim with a real, teacher-only query against /study/commentary
// (source_kind_filter=sermon_transcript) — classical commentary authors
// never surface here, which is the exact positioning failure this phase
// exists to prevent. Panel-local fetch hook, not shared with the standalone
// Study page, per the plan's design note.

interface TeacherOnVerseResult {
  document_id: string;
  title: string;
  author: string;
  excerpt: string;
}

function useTeachersOnVerse(
  verseText: string | null,
  verseIdStr: string | null,
  accessToken: string | null | undefined
): { results: TeacherOnVerseResult[]; loading: boolean } {
  const [results, setResults] = useState<TeacherOnVerseResult[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!verseText) {
      setResults([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const params = new URLSearchParams({
      verse_text: verseText,
      offset: "0",
      source_kind_filter: "sermon_transcript",
    });
    if (verseIdStr) params.set("verse_id", verseIdStr);
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/commentary?${params}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error("teachers-on-verse fetch failed");
        return res.json();
      })
      .then((data) => {
        if (cancelled) return;
        setResults(data.results ?? []);
      })
      .catch(() => {
        if (!cancelled) setResults([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [verseText, verseIdStr, accessToken]);

  return { results, loading };
}

// ── Panel body (shared between desktop side panel and mobile sheet) ────────

type PinToggleResult = "pinned" | "unpinned" | "cap_reached" | "guest_prompt";

function PanelBody({
  reference,
  isPinned,
  pinDisabled,
  onTogglePin,
  accessToken,
  role,
  userId,
}: {
  reference: StudyReference;
  isPinned: boolean;
  pinDisabled: boolean;
  onTogglePin: () => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
}) {
  const { data: verse, loading, error } = useVerseText(reference);
  const [showCapMessage, setShowCapMessage] = useState(false);

  async function handlePinClick() {
    const result = await onTogglePin();
    if (result === "cap_reached") {
      setShowCapMessage(true);
      setTimeout(() => setShowCapMessage(false), 2500);
    }
  }
  const isVerseRef = reference.type === "verse";
  const { results: teacherResults, loading: teachersLoading } = useTeachersOnVerse(
    reference.type === "verse" ? verse?.text ?? null : null,
    reference.type === "verse" ? verseId(reference) : null,
    accessToken
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-4 shrink-0">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {reference.type === "verse" ? "Verse" : "Teacher"}
          </p>
          <PanelPrimitive.Title className="mt-0.5 truncate text-xl font-medium tracking-wide text-foreground">
            {referenceLabel(reference)}
          </PanelPrimitive.Title>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <div className="relative">
            <button
              onClick={handlePinClick}
              title={isPinned ? "Unpin" : pinDisabled ? "Pin limit reached (8)" : "Pin"}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              {isPinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
            </button>
            {showCapMessage && (
              <div className="absolute right-0 top-full z-10 mt-2 whitespace-nowrap rounded-md border border-border bg-popover px-3 py-1.5 text-xs text-foreground shadow-md">
                Pin limit reached (8) — unpin something first
              </div>
            )}
          </div>
          <PanelPrimitive.Close asChild>
            <button className="flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </PanelPrimitive.Close>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {reference.type === "verse" ? (
          <>
            {loading && (
              <div className="space-y-2 animate-pulse">
                <div className="h-4 w-full rounded bg-border" />
                <div className="h-4 w-5/6 rounded bg-border" />
                <div className="h-4 w-2/3 rounded bg-border" />
              </div>
            )}
            {!loading && verse && (
              <>
                <p className="font-serif text-lg leading-relaxed text-foreground">
                  {verse.text}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">{verse.translation}</p>
              </>
            )}
            {!loading && !verse && error && (
              <p className="text-sm text-muted-foreground">
                Verse text isn&apos;t available yet for this reference.
              </p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Teacher cards (bio, works in the corpus, position on this topic) are a later
            piece of this build — not wired up yet.
          </p>
        )}

        {isVerseRef && (
          <div className="mt-6">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-2">
              Your teachers on this verse
            </p>
            {teachersLoading && (
              <div className="space-y-2 animate-pulse">
                <div className="h-4 w-full rounded bg-border" />
                <div className="h-4 w-4/5 rounded bg-border" />
              </div>
            )}
            {!teachersLoading && teacherResults.length > 0 && (
              <div className="space-y-3">
                {teacherResults.map((r) => (
                  <div key={r.document_id}>
                    <p className="text-sm font-medium text-foreground">{r.author}</p>
                    <p className="text-sm text-muted-foreground leading-relaxed">{r.excerpt}</p>
                  </div>
                ))}
              </div>
            )}
            {!teachersLoading && teacherResults.length === 0 && (
              <p className="text-sm text-muted-foreground leading-relaxed">
                None of your teachers address this verse directly yet. Content is added
                daily.
              </p>
            )}
          </div>
        )}

        {reference.type === "verse" && (
          <div className="mt-6">
            <AccordionRow label="Commentaries">
              <CommentaryAccordionRow
                verseText={verse?.text ?? null}
                verseIdStr={verseId(reference)}
                accessToken={accessToken}
              />
            </AccordionRow>
            <AccordionRow label="Pastors' Notes">
              <PastorsNotesSection
                verseId={verseId(reference)}
                accessToken={accessToken ?? null}
                role={role ?? null}
                userId={userId ?? null}
              />
            </AccordionRow>
          </div>
        )}

        <div className="mt-6 border-t border-border pt-4">
          <Link
            href="/study"
            className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline transition-colors"
          >
            <GraduationCap className="h-3.5 w-3.5" />
            Open in Study
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Main panel ───────────────────────────────────────────────────────────────

interface StudyPanelProps {
  isOpen: boolean;
  onClose: () => void;
  reference: StudyReference | null;
  pins: StudyReference[];
  onTogglePin: (ref: StudyReference) => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
}

export function StudyPanel({ isOpen, onClose, reference, pins, onTogglePin, accessToken, role, userId }: StudyPanelProps) {
  const isMobile = useIsMobile();

  if (!reference) return null;

  const isPinned = pins.some((p) => referenceKey(p) === referenceKey(reference));
  const pinDisabled = !isPinned && pins.length >= 8;

  return (
    <PanelPrimitive.Root open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <PanelPrimitive.Portal>
        {/* Desktop: transparent click-catcher — chat stays fully visible, per
            spec ("chat keeps two-thirds and stays where it is"). Mobile: a
            real dark scrim, since the sheet is a full takeover there and chat
            is not visible underneath (spec, mobile section). */}
        <PanelPrimitive.Overlay
          className={cn(
            "fixed inset-0 z-50",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
            "motion-reduce:animate-none",
            isMobile ? "bg-black/50" : "bg-transparent"
          )}
        />
        <PanelPrimitive.Content
          className={cn(
            "fixed z-50 flex flex-col bg-background shadow-lg outline-none",
            "transition ease-in-out motion-reduce:transition-none motion-reduce:animate-none",
            "data-[state=closed]:animate-out data-[state=closed]:duration-300",
            "data-[state=open]:animate-in data-[state=open]:duration-300",
            isMobile
              ? "inset-0 data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom"
              : "inset-y-0 right-0 w-[33vw] min-w-[380px] max-w-[480px] border-l border-border data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right"
          )}
        >
          {/* Mobile grab handle — visual affordance only; drag-to-dismiss is
              a follow-up (no drag dependency in this project yet). Tap closes. */}
          {isMobile && (
            <PanelPrimitive.Close asChild>
              <button className="flex shrink-0 items-center justify-center py-3" aria-label="Close">
                <span className="h-1 w-10 rounded-full bg-border" />
              </button>
            </PanelPrimitive.Close>
          )}
          <PanelPrimitive.Description className="sr-only">
            Study panel for {referenceLabel(reference)}
          </PanelPrimitive.Description>
          <PanelBody
            reference={reference}
            isPinned={isPinned}
            pinDisabled={pinDisabled}
            onTogglePin={() => onTogglePin(reference)}
            accessToken={accessToken}
            role={role}
            userId={userId}
          />
        </PanelPrimitive.Content>
      </PanelPrimitive.Portal>
    </PanelPrimitive.Root>
  );
}

// Edge-tab re-entry removed (SP2 Phase 5) — replaced by the top-bar pin
// dropdown (components/rhemata/pin-dropdown.tsx), which is reachable
// regardless of panel state and lets you pick a specific pin rather than
// only reopening "the last one."
