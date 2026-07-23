"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog as PanelPrimitive } from "radix-ui";
import { Pin, PinOff, X } from "lucide-react";
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
  const verseIdStr = reference.type === "verse" ? verseId(reference) : null;
  const { tokens, loading: tokensLoading, isNT } = useInterlinear(verseIdStr);

  // A stale word selection from a previously-viewed verse would be actively
  // wrong (matches nothing, or the wrong thing, in the new verse's tokens) —
  // reset it whenever the reference changes.
  useEffect(() => {
    setSelectedStrongs(null);
  }, [verseIdStr]);

  // Swap-in-place (Phase 2): a second underline click while the panel is
  // already open updates `reference` in place — this component re-renders,
  // it never unmounts (see handlePointerDownOutside below, which suppresses
  // Radix's dismiss for exactly this case). Reset to the default verse view
  // on every genuine target change (scroll returns to top) so a swap always
  // lands where a fresh open would. targetKey is a content-identity string,
  // not object identity: re-clicking the exact same target is correctly a
  // no-op, not a reset. Commentaries/Pastors' Notes reset to closed for
  // free via the keyed `key={targetKey}` wrapper below, which remounts
  // their (uncontrolled) internal state — Interlinear's open state is
  // lifted above that boundary, so it needs this explicit reset.
  //
  // Default open-state (decided): Interlinear starts OPEN, Commentaries and
  // Pastors' Notes start closed — on a fresh open AND on every swap. This
  // supersedes the old "Interlinear collapses" behavior from the floating-
  // overlay build, which itself had superseded an even older "leave
  // Interlinear open across a verse switch" decision. This effect also
  // fires on PanelBody's initial mount (every fresh open), not just on
  // targetKey changes, since useEffect always runs once after mount.
  const targetKey = referenceKey(reference);
  useEffect(() => {
    onInterlinearOpenChange(true);
    rowViewContainerRef.current?.scrollTo({ top: 0 });
  }, [targetKey, onInterlinearOpenChange]);

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
        {/* Keyed on the target's identity so a swap remounts this subtree —
            a smooth fade rather than a jarring cut, and content-local state
            here would reset for free too (none currently lives here; the
            outer effect above handles Interlinear/scroll explicitly since
            those are owned above this boundary). */}
        <div key={targetKey} className="animate-in fade-in-0 duration-200 motion-reduce:animate-none">
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

          {reference.type === "verse" && (
            <div className="mt-6 space-y-3">
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
  teacherQuestion?: string;
}

export function StudyPanel({ isOpen, onClose, reference, pins, onTogglePin, accessToken, role, userId, teacherQuestion }: StudyPanelProps) {
  const isMobile = useIsMobile();
  // Lifted here, not just PanelBody, so PanelBody's swap-reset effect can
  // force it back open on a target change even if the user had manually
  // closed it (Phase 2). No longer drives panel width (Phase 3: width is
  // fixed regardless of section state) — purely accordion open/closed now.
  // Defaults open (Phase 2 decision) so there's no closed-then-open flash
  // on the very first panel open of a session, before PanelBody's swap
  // effect below can catch up — that effect re-asserts `true` on every
  // open/swap after this.
  const [interlinearOpen, setInterlinearOpen] = useState(true);

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

  // Elements that open/manipulate the panel from outside its own Content
  // (verse/teacher underlines, the pin-dropdown trigger) are marked
  // data-study-trigger — interacting with them must never register as an
  // "outside" dismiss, even though DOM-wise they live outside Content.
  function isStudyTrigger(target: EventTarget | null): boolean {
    return target instanceof HTMLElement && !!target.closest("[data-study-trigger]");
  }

  // Phase 2 (floating overlay): a click on a DIFFERENT verse/teacher
  // underline while the panel is already open must swap content in place,
  // not close-then-reopen — the underline lives outside Content, so Radix's
  // default outside-pointerdown dismiss would otherwise fire first (racing
  // the click's own handler, which updates `reference`). Suppressing the
  // dismiss for marked triggers only lets that update land untouched;
  // everything else outside the panel still closes it normally. No-op on
  // mobile: the modal sheet covers the chat area, so no underline is
  // reachable while it's open.
  function handlePointerDownOutside(event: CustomEvent<{ originalEvent: PointerEvent }>) {
    if (isStudyTrigger(event.detail.originalEvent.target)) {
      event.preventDefault();
    }
  }

  // Bug fix (found live, 2026-07-22): opening the panel from the pin
  // dropdown (PinDropdown -> onSelectPin -> handleVerseClick) opened the
  // panel and then immediately closed it again. Root cause: selecting a
  // DropdownMenuItem closes that Radix DropdownMenu, which by default
  // restores focus to ITS trigger (the pin button in the top bar) — an
  // element outside this Content. Radix Dialog's default onFocusOutside
  // treats focus landing outside Content as a dismiss signal, same as
  // onPointerDownOutside above, and nothing here overrode it. Same fix,
  // same marker: suppress it for data-study-trigger elements. The pin
  // button itself carries the marker (pin-dropdown.tsx), not the dropdown
  // items — the item that was clicked is already gone from the DOM by the
  // time focus moves; it's the trigger regaining focus that matters here.
  function handleFocusOutside(event: CustomEvent<{ originalEvent: FocusEvent }>) {
    if (isStudyTrigger(event.detail.originalEvent.target)) {
      event.preventDefault();
    }
  }

  if (!reference) return null;

  const isPinned = pins.some((p) => referenceKey(p) === referenceKey(reference));
  const pinDisabled = !isPinned && pins.length >= 8;

  return (
    <PanelPrimitive.Root open={isOpen} modal={isMobile} onOpenChange={(open) => { if (!open) onClose(); }}>
      <PanelPrimitive.Portal>
        {/* Mobile only: real dark scrim, full-screen takeover, chat hidden
            underneath (spec, mobile section — untouched by Phase 2). Desktop
            floats over the chat with no scrim/overlay at all: the chat stays
            fully visible AND interactive, and the rounded corners + shadow
            on Content below are the only depth cues. Root's modal={isMobile}
            (false on desktop) plus handlePointerDownOutside above are what
            make that safe — no blocking layer is needed for outside-click-
            to-close to keep working. */}
        {isMobile && (
          <PanelPrimitive.Overlay
            className={cn(
              "fixed inset-0 z-50 bg-black/50",
              "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
              "motion-reduce:animate-none"
            )}
          />
        )}
        <PanelPrimitive.Content
          onCloseAutoFocus={handleCloseAutoFocus}
          onPointerDownOutside={handlePointerDownOutside}
          onFocusOutside={handleFocusOutside}
          className={cn(
            "fixed z-50 flex flex-col bg-background shadow-lg outline-none",
            "transition ease-in-out motion-reduce:transition-none motion-reduce:animate-none",
            "data-[state=closed]:animate-out data-[state=closed]:duration-300",
            "data-[state=open]:animate-in data-[state=open]:duration-300",
            isMobile
              // LOAD-BEARING: the close control below is the only way out
              // of this full-screen takeover. pt safe-area keeps it below
              // the notch/status bar instead of shifting inset-0's whole
              // box — mobile only, desktop's floating card never touches
              // the top edge.
              ? "inset-0 pt-[env(safe-area-inset-top)] data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom"
              : cn(
                  // Floating card beside the chat (revised live, 2026-07-22):
                  // small gap on all sides (inset-y-2/right-2), never
                  // touches a screen edge. Background matches the chat
                  // card's own bg-background (not the sidebar) — the panel
                  // reads as a sibling of the chat card, not a nav surface.
                  // Same 300ms timing as page.tsx's padding-right shift on
                  // `main`, so the panel's slide and the chat's narrowing
                  // read as one coordinated motion.
                  "inset-y-2 right-2 rounded-xl border border-border",
                  "data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
                  // Phase 3: fixed width, permanently — the old 50vw
                  // Interlinear-open expansion is gone. This is the
                  // pre-Interlinear-click closed-state width from before
                  // Phase 3 (Phase 0 measurement), now the panel's only
                  // width regardless of which sections are open.
                  "w-[33vw] min-w-[380px] max-w-[480px]"
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
            onInterlinearOpenChange={setInterlinearOpen}
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
