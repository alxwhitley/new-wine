"use client";

import { useEffect, useRef, useState } from "react";
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
import { InterlinearBlocks } from "@/components/rhemata/interlinear-blocks";
import { useInterlinear } from "@/hooks/useInterlinear";
import { WordDefinitionCard, type WordDefinition } from "@/components/rhemata/word-definition-card";
import { useLexiconDefinition } from "@/hooks/useLexiconDefinition";
import { TeacherCard } from "@/components/rhemata/teacher-card";

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

// ── Word study view (SP2 Phase 8) ───────────────────────────────────────────
// The panel's one back-button surface — reached only by tapping a word in the
// Interlinear row. Lexicon-only (WordDefinitionCard), unlike the standalone
// page's InlineWordPanel: no Precept Austin excerpt, no "From the Library"
// corpus section, by design.

function WordStudyView({ definition, onBack }: { definition: WordDefinition | null; onBack: () => void }) {
  // SP2 Phase 9 (Fix 3, entry): this view fully replaces the row view's DOM
  // subtree on mount, so the tapped token's focus is gone by the time this
  // renders — land focus on Back, the one actionable element at the top of
  // this back-stack surface, rather than leaving it on the generic container.
  const backRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    backRef.current?.focus();
  }, []);

  return (
    <div>
      <button
        ref={backRef}
        onClick={onBack}
        className="text-sm cursor-pointer hover:underline text-muted-foreground hover:text-foreground transition-colors"
      >
        &larr; Back
      </button>
      <div className="mt-4">
        <WordDefinitionCard definition={definition} />
      </div>
      <p className="text-xs text-muted-foreground mt-6">
        Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)
      </p>
    </div>
  );
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
  interlinearOpen,
  onInterlinearOpenChange,
  teacherQuestion,
}: {
  reference: StudyReference;
  isPinned: boolean;
  pinDisabled: boolean;
  onTogglePin: () => Promise<PinToggleResult>;
  accessToken?: string | null;
  role?: string | null;
  userId?: string | null;
  interlinearOpen: boolean;
  onInterlinearOpenChange: (open: boolean) => void;
  teacherQuestion?: string;
}) {
  const { data: verse, loading, error } = useVerseText(reference);
  const [showCapMessage, setShowCapMessage] = useState(false);
  const [selectedStrongs, setSelectedStrongs] = useState<string | null>(null);
  // SP2 Phase 9 (Fix 3, exit): remembers which token to return focus to when
  // leaving the word-study view via Back — read once, after the row view has
  // re-rendered, then cleared. Falls back to the row view's own scrollable
  // container if that exact token isn't found (e.g. tokens still loading).
  const pendingRefocusStrongsRef = useRef<string | null>(null);
  const rowViewContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedStrongs !== null || !pendingRefocusStrongsRef.current) return;
    const strongs = pendingRefocusStrongsRef.current;
    pendingRefocusStrongsRef.current = null;
    const target = document.querySelector<HTMLElement>(`[data-strongs-token="${strongs}"]`);
    (target ?? rowViewContainerRef.current)?.focus();
  }, [selectedStrongs]);

  function handleBackFromWordStudy() {
    pendingRefocusStrongsRef.current = selectedStrongs;
    setSelectedStrongs(null);
  }

  async function handlePinClick() {
    const result = await onTogglePin();
    if (result === "cap_reached") {
      setShowCapMessage(true);
      setTimeout(() => setShowCapMessage(false), 2500);
    }
  }
  const isVerseRef = reference.type === "verse";
  const verseIdStr = reference.type === "verse" ? verseId(reference) : null;
  const { results: teacherResults, loading: teachersLoading } = useTeachersOnVerse(
    reference.type === "verse" ? verse?.text ?? null : null,
    verseIdStr,
    accessToken
  );

  const { tokens, loading: tokensLoading, isNT } = useInterlinear(verseIdStr);

  // A stale word selection from a previously-viewed verse would be actively
  // wrong (matches nothing, or the wrong thing, in the new verse's tokens) —
  // reset it whenever the reference changes. The Interlinear row's own
  // open/closed state is left alone; that's a UI preference, not tied to
  // verse identity.
  useEffect(() => {
    setSelectedStrongs(null);
  }, [verseIdStr]);

  // A teacher card never has an Interlinear row — collapse the width
  // reservation if it was left open from a previously-viewed verse, so
  // switching verse -> teacher doesn't leave the panel stuck at 50vw.
  useEffect(() => {
    if (reference.type !== "verse" && interlinearOpen) {
      onInterlinearOpenChange(false);
    }
  }, [reference.type, interlinearOpen, onInterlinearOpenChange]);

  const lexiconEntry = useLexiconDefinition(selectedStrongs, accessToken ?? null);
  const selectedToken = selectedStrongs ? tokens.find((t) => t.strongs === selectedStrongs) ?? null : null;
  const wordDefinition: WordDefinition | null = selectedToken
    ? {
        strongs: selectedToken.strongs,
        word: selectedToken.greek,
        transliteration: selectedToken.transliteration,
        gloss: selectedToken.english,
        lexiconDefinition: lexiconEntry?.lexiconDefinition ?? "",
        meaning: lexiconEntry?.meaning ?? "",
      }
    : selectedStrongs && lexiconEntry
    ? {
        strongs: selectedStrongs,
        word: selectedStrongs,
        transliteration: "",
        gloss: lexiconEntry.gloss,
        lexiconDefinition: lexiconEntry.lexiconDefinition,
        meaning: lexiconEntry.meaning,
      }
    : null;

  if (selectedStrongs) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-4 shrink-0">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Verse</p>
            <PanelPrimitive.Title className="mt-0.5 truncate text-xl font-medium tracking-wide text-foreground">
              {referenceLabel(reference)}
            </PanelPrimitive.Title>
          </div>
          <PanelPrimitive.Close asChild>
            <button className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
              <X className="h-4 w-4" />
              <span className="sr-only">Close</span>
            </button>
          </PanelPrimitive.Close>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <WordStudyView definition={wordDefinition} onBack={handleBackFromWordStudy} />
        </div>
      </div>
    );
  }

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
              aria-label={isPinned ? "Unpin" : pinDisabled ? "Pin limit reached (8)" : "Pin"}
              className="flex h-8 w-8 items-center justify-center rounded-full border border-border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              {isPinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
            </button>
            {showCapMessage && (
              <div
                role="alert"
                className="absolute right-0 top-full z-10 mt-2 whitespace-nowrap rounded-md border border-border bg-popover px-3 py-1.5 text-xs text-foreground shadow-md"
              >
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
      <div ref={rowViewContainerRef} tabIndex={-1} className="flex-1 overflow-y-auto px-4 py-4">
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
          <TeacherCard
            sourceId={reference.source_id}
            question={teacherQuestion ?? ""}
            accessToken={accessToken}
          />
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
            <AccordionRow label="Interlinear" open={interlinearOpen} onOpenChange={onInterlinearOpenChange}>
              <InterlinearBlocks
                tokens={tokens}
                selectedStrongs={selectedStrongs}
                onSelect={setSelectedStrongs}
                loading={tokensLoading}
                isNT={isNT}
              />
            </AccordionRow>
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
  onInterlinearOpenChange?: (open: boolean) => void;
  teacherQuestion?: string;
}

export function StudyPanel({ isOpen, onClose, reference, pins, onTogglePin, accessToken, role, userId, onInterlinearOpenChange, teacherQuestion }: StudyPanelProps) {
  const isMobile = useIsMobile();
  // SP2 Phase 8 (Task 30): lifted here, not just PanelBody, since the panel's
  // own width class (below) needs it too — width follows need, automatically,
  // no user-managed "wide mode". Left open across a verse switch deliberately
  // (a UI preference, not tied to verse identity — see PanelBody's comment on
  // why selectedStrongs, unlike this, DOES reset per verse).
  const [interlinearOpen, setInterlinearOpen] = useState(false);

  // SP2 Phase 9 (Fix 2): this panel has no Dialog.Trigger — it's opened from
  // several different places (verse-underline clicks, the dev button, the
  // keyboard shortcut), so Radix has nothing reliable to restore focus to on
  // close by default, and it was landing on <body>. Capture whatever had
  // focus right before opening; restore it on close via onCloseAutoFocus
  // (Radix's own sanctioned override point — doesn't touch the focus-trap
  // itself, which is a separate mechanism). Falls back to the chat input if
  // the original element is no longer in the DOM.
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      previouslyFocusedRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
  }, [isOpen]);

  function handleCloseAutoFocus(event: Event) {
    event.preventDefault();
    const el = previouslyFocusedRef.current;
    if (el && document.contains(el)) {
      el.focus();
      return;
    }
    document.querySelector<HTMLTextAreaElement>("textarea")?.focus();
  }

  function handleInterlinearOpenChange(open: boolean) {
    setInterlinearOpen(open);
    onInterlinearOpenChange?.(open);
  }

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
          onCloseAutoFocus={handleCloseAutoFocus}
          className={cn(
            "fixed z-50 flex flex-col bg-background shadow-lg outline-none",
            "transition ease-in-out motion-reduce:transition-none motion-reduce:animate-none",
            "data-[state=closed]:animate-out data-[state=closed]:duration-300",
            "data-[state=open]:animate-in data-[state=open]:duration-300",
            isMobile
              ? "inset-0 data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom"
              : cn(
                  "inset-y-0 right-0 border-l border-border data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
                  interlinearOpen ? "w-[50vw] min-w-[480px] max-w-[720px]" : "w-[33vw] min-w-[380px] max-w-[480px]"
                )
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
            interlinearOpen={interlinearOpen}
            onInterlinearOpenChange={handleInterlinearOpenChange}
            teacherQuestion={teacherQuestion}
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
