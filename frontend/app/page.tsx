"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatFocus } from "@/contexts/chat-focus-context";
import { useAuth } from "@/hooks/useAuth";
import { supabase } from "@/lib/supabase";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/newwine/sidebar";
import { ChatMessage } from "@/components/newwine/chat-message";
import { ChatInput } from "@/components/newwine/chat-input";
import { SourcePanel } from "@/components/newwine/source-panel";
import { StudyPanel } from "@/components/newwine/study-panel";
import { PinDropdown } from "@/components/newwine/pin-dropdown";
import { LoadingIndicator } from "@/components/newwine/loading-indicator";
import { WeeklyLimitCard } from "@/components/newwine/weekly-limit-card";
import {
  ConversationLengthNudge,
  CONVERSATION_LENGTH_NUDGE_THRESHOLD_USD,
} from "@/components/newwine/conversation-length-nudge";
import LoginModal from "@/components/auth/LoginModal";
import { useAuthGate } from "@/hooks/useAuthGate";
import { ConsentGate } from "@/components/newwine/consent-gate";
import type { Citation } from "@/lib/api";
import type { WeeklyLimitDetail } from "@/hooks/useChat";
import { referenceKey, referenceFromVerseId, verseId as verseIdOf, type StudyReference, type CuratedTeacher } from "@/lib/study-reference";
import { isStudyPanelEnabled } from "@/lib/study-panel-flag";
import { isFullNavEnabled } from "@/lib/chat-only-beta-flag";
import { useUserRole } from "@/hooks/useUserRole";

// SP2 Phase 5: a guest's pin attempt is stored here (verse identity only,
// not the whole StudyReference) while they complete signup, then landed
// automatically — see handleToggleStudyPin's guest branch and
// handleSignUpWithPendingPin below.
const PENDING_PIN_KEY = "newwine_pending_pin";

const SUGGESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "Is speaking in tongues for today?",
  "How do I hear God's voice?",
];

export default function Home() {
  const { inputFocused } = useChatFocus();
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const { role: userRole } = useUserRole(accessToken);
  // In-app surface: anyone already here has an account, so the bare entry
  // point opens on sign in. Contextual prompts below ask for signup explicitly.
  const { authOpen, authMode, authReason, openAuth, closeAuth } = useAuthGate("signin");
  const [weeklyLimitDetail, setWeeklyLimitDetail] = useState<WeeklyLimitDetail | null>(null);
  // Long-conversation-handoff nudge (docs/superpowers/specs/2026-08-26-long-
  // conversation-handoff.md): dismissed for the rest of THIS conversation
  // once "Not now" is clicked; reset whenever a new/different conversation
  // starts (handleNewChat / handleSelectConversation below).
  const [lengthNudgeDismissed, setLengthNudgeDismissed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
    requestAnimationFrame(() => menuButtonRef.current?.focus());
  }, []);
  // Geometry v3: StudyPanel's desktop Portal renders into this node instead
  // of document.body — real DOM nesting inside the chat card. useState (not
  // useRef) so the ref callback's assignment triggers a re-render, since
  // StudyPanel needs the actual element, not a ref object, to pass to Portal.
  const [desktopPanelContainer, setDesktopPanelContainer] = useState<HTMLDivElement | null>(null);
  const [lastQuery, setLastQuery] = useState<string | null>(null);
  const {
    messages,
    loading: chatLoading,
    error: chatError,
    conversationId,
    weeklyUsage,
    conversationCostUsd,
    sendMessage,
    clearMessages,
    loadConversation,
  } = useChat(
    accessToken,
    () => {
      openAuth("signup", "You've used your 6 free searches. Create a free account to keep going.");
    },
    (detail) => setWeeklyLimitDetail(detail),
  );
  const {
    conversations,
    addOrUpdate,
    deleteConversation,
    loadMessages,
  } = useConversations(user?.id);

  // Source panel state
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [selectedCitationIndex, setSelectedCitationIndex] = useState<number | null>(null);
  const [isSourcePanelOpen, setIsSourcePanelOpen] = useState(false);

  // Inline Study Panel state (SP2 shell — docs/inline-study-panel-spec.md)
  const [studyPanelOpen, setStudyPanelOpen] = useState(false);
  const [studyReference, setStudyReference] = useState<StudyReference | null>(null);
  // SP2 Phase 5: global, account-level pins — fetched from and persisted to
  // /study/pins, not in-memory. `id` is the server row id (needed for
  // DELETE); `reference` is reconstructed client-side from the server's
  // compact verse_id via referenceFromVerseId.
  const [studyPins, setStudyPins] = useState<
    Array<{ id: string; reference: Extract<StudyReference, { type: "verse" }> }>
  >([]);
  // SP4: the curated teacher list (GET /study/teachers) — public, no auth,
  // since guest users see teacher underlines too, same as verse underlines.
  const [curatedTeachers, setCuratedTeachers] = useState<CuratedTeacher[]>([]);
  // The current turn's user question, captured at teacher-underline-click
  // time (see handleVerseClick below) — the panel's live position synthesis
  // is scoped to "the user's current question," per the SP4 design doc.
  const [teacherCardQuestion, setTeacherCardQuestion] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/teachers`)
      .then((res) => (res.ok ? res.json() : { teachers: [] }))
      .then((data) => {
        if (cancelled) return;
        setCuratedTeachers(data.teachers ?? []);
      })
      .catch(() => {
        if (!cancelled) setCuratedTeachers([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Reset synchronously during render when accessToken becomes falsy
  // (React's documented "adjusting state when a prop changes" pattern)
  // instead of as the effect's own first statements.
  const [resolvedPinsToken, setResolvedPinsToken] = useState(accessToken);
  if (accessToken !== resolvedPinsToken) {
    setResolvedPinsToken(accessToken);
    if (!accessToken) setStudyPins([]);
  }

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/pins`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((res) => (res.ok ? res.json() : { pins: [] }))
      .then((data) => {
        if (cancelled) return;
        const pins = ((data.pins ?? []) as Array<{ id: string; verse_id: string }>)
          .map((p) => {
            const reference = referenceFromVerseId(p.verse_id);
            return reference ? { id: p.id, reference } : null;
          })
          .filter((p): p is { id: string; reference: Extract<StudyReference, { type: "verse" }> } => p !== null);
        setStudyPins(pins);
      })
      .catch(() => {
        if (!cancelled) setStudyPins([]);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  const handleVerseClick = useCallback((reference: StudyReference, question?: string) => {
    if (!isStudyPanelEnabled()) return; // defense in depth — kill switch off
    setStudyReference(reference);
    setTeacherCardQuestion(question ?? "");
    setStudyPanelOpen(true);
  }, []);

  const handleCloseStudyPanel = useCallback(() => {
    setStudyPanelOpen(false);
  }, []);

  // Returns a result the pin button can react to (Task 17 wires the visible
  // cap message off "cap_reached"; the guest sign-up flow off "guest_prompt").
  const handleToggleStudyPin = useCallback(
    async (reference: StudyReference): Promise<"pinned" | "unpinned" | "cap_reached" | "guest_prompt"> => {
      if (reference.type !== "verse") return "unpinned"; // pins are verse-only in SP2

      if (!accessToken) {
        sessionStorage.setItem(PENDING_PIN_KEY, verseIdOf(reference));
        // Close the panel before opening the auth gate: the auth card
        // and the study panel's own Radix Dialog overlay are both fixed,
        // full-screen, and z-50 — tied. With the panel left open, its
        // overlay paints on top (later in DOM) and silently swallows every
        // click meant for the modal underneath, even though it looks
        // completely normal in a screenshot. The pending pin already lives
        // in sessionStorage above, independent of the panel's own state, so
        // closing it here doesn't affect whether the pin lands after signup.
        setStudyPanelOpen(false);
        openAuth("signup", "Sign up to save this verse and access it anytime.");
        return "guest_prompt";
      }

      const key = referenceKey(reference);
      const existing = studyPins.find((p) => referenceKey(p.reference) === key);

      if (existing) {
        await fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/pins/${existing.id}`, {
          method: "DELETE",
          headers: { Authorization: `Bearer ${accessToken}` },
        }).catch(() => {});
        setStudyPins((prev) => prev.filter((p) => p.id !== existing.id));
        return "unpinned";
      }

      if (studyPins.length >= 8) {
        return "cap_reached";
      }

      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/pins`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ verse_id: verseIdOf(reference) }),
      }).catch(() => null);

      if (!res) return "cap_reached";
      if (res.status === 409) return "cap_reached"; // server-enforced, races with another device
      if (!res.ok) return "cap_reached";

      const row = await res.json();
      setStudyPins((prev) => [...prev, { id: row.id, reference }]);
      return "pinned";
    },
    [accessToken, studyPins, openAuth],
  );

  // Wraps useAuth's signUp (LoginModal itself is untouched — it's load-bearing
  // and already owns the whole success/close flow internally) so a guest pin
  // attempt lands automatically once signup succeeds, with no manual re-pin.
  // Reads the fresh session directly from the Supabase client rather than
  // this closure's `accessToken`, which won't have flushed from
  // onAuthStateChange yet at the point signUp's own promise resolves.
  const handleSignUpWithPendingPin = useCallback(
    async (email: string, password: string) => {
      const result = await signUp(email, password);
      if (result.hasSession) {
        const pendingVerseId = sessionStorage.getItem(PENDING_PIN_KEY);
        if (pendingVerseId) {
          sessionStorage.removeItem(PENDING_PIN_KEY);
          const { data } = await supabase.auth.getSession();
          const freshToken = data.session?.access_token;
          if (freshToken) {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/study/pins`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${freshToken}`,
              },
              body: JSON.stringify({ verse_id: pendingVerseId }),
            }).catch(() => null);
            // Fail quietly on any error (e.g. cap already reached from another
            // device) — never block the signup flow itself over a pin.
            if (res && res.ok) {
              const reference = referenceFromVerseId(pendingVerseId);
              if (reference) {
                const row = await res.json();
                setStudyPins((prev) => [...prev, { id: row.id, reference }]);
              }
            }
          }
        }
      }
      return result;
    },
    [signUp],
  );

  // Sending a new question deliberately reveals the new turn once. Streaming
  // tokens never own scroll position after that; the reader does.
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const appViewportRef = useRef<HTMLDivElement>(null);
  const chatRegionRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLDivElement>(null);
  const scrollOnNextTurnRef = useRef(false);
  useEffect(() => {
    if (!scrollOnNextTurnRef.current || messages.length === 0) return;
    scrollOnNextTurnRef.current = false;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  // iOS Safari keeps the layout viewport behind its software keyboard. Size
  // and position the app against the visible viewport instead, including
  // toolbar motion and rotation changes that do not always update 100dvh.
  useEffect(() => {
    const viewport = window.visualViewport;
    let animationFrame = 0;
    const scheduleViewportSync = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        const shell = appViewportRef.current;
        if (!shell) return;
        shell.style.height = `${Math.round(viewport?.height ?? window.innerHeight)}px`;
        // Clamped at 0: a rubber-band fires visualViewport 'scroll' with a
        // negative offsetTop, and writing it back made the shell ride the
        // bounce instead of staying put. The listener itself is load-bearing
        // for iOS toolbar motion, so only the negative excursion is dropped.
        shell.style.top = `${Math.max(0, Math.round(viewport?.offsetTop ?? 0))}px`;
        shell.style.bottom = "auto";
      });
    };

    scheduleViewportSync();
    viewport?.addEventListener("resize", scheduleViewportSync);
    viewport?.addEventListener("scroll", scheduleViewportSync);
    window.addEventListener("resize", scheduleViewportSync);
    window.addEventListener("orientationchange", scheduleViewportSync);
    return () => {
      cancelAnimationFrame(animationFrame);
      viewport?.removeEventListener("resize", scheduleViewportSync);
      viewport?.removeEventListener("scroll", scheduleViewportSync);
      window.removeEventListener("resize", scheduleViewportSync);
      window.removeEventListener("orientationchange", scheduleViewportSync);
    };
  }, []);

  // When a keyboard changes the visible height, keep the newest turn above
  // the composer. This only runs while composing, so reading/streaming still
  // leaves scroll ownership with the reader.
  useEffect(() => {
    if (!inputFocused || messages.length === 0) return;
    const viewport = window.visualViewport;
    let animationFrame = 0;
    const keepLatestVisible = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        // Explicit scroll-to-end rather than scrollIntoView({ block: "nearest" }).
        // "nearest" aligns to the SCROLLPORT's bottom edge, which the floating
        // composer now overlays -- it would park the newest turn underneath it.
        // The scroller's own bottom-padding reservation (--composer-h, below)
        // means scrolling fully
        // to the end lands the last turn exactly against the composer's top.
        const scroller = scrollContainerRef.current;
        if (scroller) scroller.scrollTop = scroller.scrollHeight;
      });
    };

    keepLatestVisible();
    viewport?.addEventListener("resize", keepLatestVisible);
    viewport?.addEventListener("scroll", keepLatestVisible);
    window.addEventListener("orientationchange", keepLatestVisible);
    return () => {
      cancelAnimationFrame(animationFrame);
      viewport?.removeEventListener("resize", keepLatestVisible);
      viewport?.removeEventListener("scroll", keepLatestVisible);
      window.removeEventListener("orientationchange", keepLatestVisible);
    };
  }, [inputFocused, messages.length]);

  // The composer floats over the thread, so the scroller has to reserve the
  // composer's REAL height as bottom padding -- composerMaxHeight() lets the
  // textarea grow, so a fixed reservation clips the last line of an answer.
  // Published as --composer-h on the chat region; the scroller's padding and
  // .composer-fade's height both read it.
  const hasMessages = messages.length > 0;
  useEffect(() => {
    const composer = composerRef.current;
    const region = chatRegionRef.current;
    if (!composer || !region) return;
    const sync = () => {
      region.style.setProperty(
        "--composer-h",
        `${Math.round(composer.getBoundingClientRect().height)}px`,
      );
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(composer);
    return () => observer.disconnect();
  }, [hasMessages]);

  // / shortcut focuses the chat textarea
  useEffect(() => {
    function onSlash(e: globalThis.KeyboardEvent) {
      if (
        e.key === "/" &&
        !e.metaKey && !e.ctrlKey && !e.altKey &&
        !(document.activeElement instanceof HTMLInputElement) &&
        !(document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        document.querySelector<HTMLTextAreaElement>("textarea")?.focus();
      }
    }
    document.addEventListener("keydown", onSlash);
    return () => document.removeEventListener("keydown", onSlash);
  }, []);

  const handleSend = useCallback(
    async (question: string) => {
      setLastQuery(question);
      scrollOnNextTurnRef.current = true;
      const newConvId = await sendMessage(question);
      if (newConvId && user) {
        const title = question.split(/\s+/).slice(0, 6).join(" ");
        addOrUpdate(newConvId, title);
      }
    },
    [sendMessage, user, addOrUpdate],
  );

  function handleNewChat() {
    clearMessages();
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    setLengthNudgeDismissed(false);
  }

  function handleRetry() {
    if (!lastQuery) return;
    // Deliberately NOT handleNewChat(): retry resubmits the failed
    // question in the same conversation (useChat's own error handling
    // already strips the failed turn's empty placeholder -- see
    // lib/chat-recovery.ts) rather than discarding everything the user
    // asked before the failure.
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    handleSend(lastQuery);
  }

  async function handleSelectConversation(id: string) {
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    setLengthNudgeDismissed(false);
    const msgs = await loadMessages(id);
    loadConversation(id, msgs);
  }

  async function handleDeleteConversation(id: string) {
    const deleted = await deleteConversation(id);
    // Only clear the visible thread on confirmed success -- a silent
    // failure (network blip, RLS rejection) must never make an open
    // conversation appear to vanish while it's still there in Supabase
    // and the sidebar list.
    if (deleted && conversationId === id) {
      clearMessages();
    }
  }

  // useCallback (not a plain function): ChatMessage's ReactMarkdown
  // `components` map depends on this reference staying stable across
  // unrelated re-renders — see chat-message.tsx's own comment on why an
  // unstable dependency there causes react-markdown to remount message
  // content, including mid-click on a verse/teacher reference button.
  const handleCitationClick = useCallback((citation: Citation, index: number) => {
    setSelectedCitation(citation);
    setSelectedCitationIndex(index);
    setIsSourcePanelOpen(true);
  }, []);

  function handleCloseSourcePanel() {
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    setSelectedCitationIndex(null);
  }

  const isEmpty = messages.length === 0;
  // Computed once via useState's lazy initializer, guaranteed to run
  // exactly once for this component instance's lifetime -- not in an
  // effect (react-hooks/set-state-in-effect) and not a bare call during
  // render (new Date() is impure, react-hooks/purity), matching the same
  // pattern already used for sidebar.tsx's skeleton-width randomization.
  const [greeting] = useState(() => {
    const h = new Date().getHours();
    if (h >= 5 && h < 12) return "Good morning, what would you like to learn about?";
    if (h >= 12 && h < 17) return "Good afternoon, what would you like to learn about?";
    if (h >= 17 && h < 21) return "Good evening, what would you like to learn about?";
    return "You're up late. What would you like to explore?";
  });

  return (
    // Outermost shell: sidebar tone, full viewport
    <div ref={appViewportRef} className="fixed inset-0 flex h-dvh-safe overflow-hidden overscroll-none bg-sidebar">
      {/* Sidebar sits directly on this canvas */}
      <Sidebar
        conversations={conversations}
        activeConversationId={conversationId}
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        weeklyUsage={weeklyUsage}
        isOpen={sidebarOpen}
        onOpen={() => setSidebarOpen(true)}
        onClose={closeSidebar}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onSignInClick={() => openAuth("signin")}
      />

      {/* Chat card wrapper — inset when the fixed sidebar is present. The
          sidebar stays fixed from landscape-tablet upward (lg:ml-64); the card's own
          outer bounds never move either, panel open or closed (geometry
          v3, replaces the old padding-right reservation) — only the split
          INSIDE the card between chat region and panel slot changes. */}
      <main
        className={cn(
          "flex flex-1 min-w-0 min-h-0 md:p-2 md:pb-2 lg:ml-64",
          // Chat-only beta: pb-safe has MOVED onto the floating composer
          // below, so the card now reaches the physical bottom edge and
          // answers can fade through the safe area instead of stopping short
          // of it. Flag on: unchanged, 56px reserved for the tab bar.
          isFullNavEnabled() ? (inputFocused ? "pb-0" : "pb-14") : undefined
        )}
      >
        {/* The chat card — bordered on desktop, full-bleed on mobile. Row on
            desktop (chat region | panel slot side by side, sharing this
            box's own rounded corners/border/overflow-hidden — the panel
            gets no rounding/border/shadow of its own); column on mobile,
            where the panel slot below never renders (hidden md:block) so
            this is a single unchanged flex-column, byte-for-byte as before. */}
        <div className="relative flex flex-col md:flex-row flex-1 min-h-0 bg-background md:rounded-xl md:border md:border-border overflow-hidden">
          {/* Chat region — was the card's own direct content; now its own
              flex-column so it can sit beside the panel slot on desktop. */}
          <div ref={chatRegionRef} className="relative flex flex-col flex-1 min-w-0 min-h-0">

          {/* Mobile floating menu button — replaces full-width bar on mobile.
              LOAD-BEARING once the tab bar is gated off: this is the only
              way to open the drawer on mobile. top-3 (0.75rem) shifted by
              the real inset so it lands at the same visual position as
              today instead of under the notch/status bar. */}
          <button
            ref={menuButtonRef}
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
            className="md:hidden absolute top-[calc(0.75rem+env(safe-area-inset-top))] left-3 z-30 h-11 w-11 flex items-center justify-center rounded-full border border-border bg-background text-muted-foreground transition-colors hover:text-foreground active:bg-accent active:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>
          {/* usage ring moved to drawer (Pass B) */}

          {/* The shared tablet app bar is fixed above this structural spacer. */}
          <div className="hidden h-14 shrink-0 md:block lg:hidden" aria-hidden="true" />

          {/* Top bar — desktop only (mobile uses floating button above).
              Pin dropdown is desktop-only in this phase — see Open Flags. */}
          <div className="hidden lg:flex h-14 shrink-0 items-center justify-end px-6 z-30 border-b border-border">
            {isStudyPanelEnabled() && (
              <PinDropdown
                pins={studyPins.map((p) => p.reference)}
                isSignedIn={!!user}
                onSelectPin={handleVerseClick}
              />
            )}
          </div>

          {isEmpty ? (
            /* Empty state — centred, full remaining height */
            <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-12 md:max-lg:pb-12 overflow-hidden overscroll-none min-h-0">
              <h2 suppressHydrationWarning className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center max-w-lg text-balance">
                {greeting}
              </h2>

              <div className="mt-8 w-full max-w-xl md:max-w-2xl lg:max-w-xl xl:max-w-2xl">
                <ChatInput onSend={handleSend} disabled={chatLoading} embedded />

                <div className="mt-2 flex w-full flex-col items-center gap-2 md:max-lg:gap-3">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSend(s)}
                      className="w-full min-h-[44px] text-left rounded-lg bg-popover px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground active:bg-accent active:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {chatError && (
                <div className="flex items-center gap-3 mt-4">
                  <p role="alert" aria-live="polite" className="text-sm text-destructive">{chatError}</p>
                  {lastQuery && (
                    <button onClick={handleRetry} className="shrink-0 text-sm text-primary hover:underline transition-colors">
                      Try again
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            /* Chat thread */
            <>
              {/* Scrollable message list — panel corners never clipped */}
              <div
                ref={scrollContainerRef}
                className="flex-1 overflow-y-auto overscroll-contain min-h-0 pb-[calc(var(--composer-h,5rem)+1rem)]"
              >
                {/* Scroll fade: messages dissolve into background as they pass the top */}
                <div className="pointer-events-none sticky top-0 z-10 h-14 md:h-8 bg-gradient-to-b from-background to-transparent" />
                <div className="mx-auto max-w-2xl px-4 md:px-12 pt-4 md:pt-2 pb-8">
                  {messages.map((message, i) => {
                    const question = message.role === "assistant" && i > 0 && messages[i - 1].role === "user"
                      ? messages[i - 1].content
                      : undefined;
                    const isStreaming = chatLoading && message.role === "assistant" && i === messages.length - 1;
                    return (
                      <ChatMessage
                        key={i}
                        role={message.role}
                        content={message.content}
                        citations={message.citations}
                        messageId={message.messageId}
                        question={question}
                        accessToken={accessToken}
                        onCitationClick={handleCitationClick}
                        onVerseClick={handleVerseClick}
                        isStreaming={isStreaming}
                        verifiedReferences={message.verifiedReferences}
                        curatedTeachers={curatedTeachers}
                        quoteIds={message.quoteIds}
                      />
                    );
                  })}

                  {chatLoading && messages.length > 0 && messages[messages.length - 1].content === "" && (
                    <LoadingIndicator />
                  )}

                  {/* Weekly limit hard-stop — renders where the blocked answer would appear */}
                  {weeklyLimitDetail && (
                    <div className="mt-4">
                      <WeeklyLimitCard
                        limit={weeklyLimitDetail.limit}
                        resets={weeklyLimitDetail.resets}
                        onNewChat={handleNewChat}
                      />
                    </div>
                  )}

                  {/* Long-conversation-handoff nudge — soft, dismissible, never
                      blocks sending. Suppressed under the hard weekly-limit stop
                      above (nothing to nudge toward once already hard-blocked)
                      and while a turn is still streaming in. */}
                  {!weeklyLimitDetail &&
                    !chatLoading &&
                    !lengthNudgeDismissed &&
                    conversationCostUsd !== null &&
                    conversationCostUsd >= CONVERSATION_LENGTH_NUDGE_THRESHOLD_USD && (
                      <div className="mt-4">
                        <ConversationLengthNudge
                          onNewChat={handleNewChat}
                          onDismiss={() => setLengthNudgeDismissed(true)}
                        />
                      </div>
                    )}

                  {chatError && (
                    <div className="flex items-center gap-3 mt-2">
                      <p role="alert" aria-live="polite" className="text-sm text-destructive">{chatError}</p>
                      {lastQuery && (
                        <button onClick={handleRetry} className="shrink-0 text-sm text-primary hover:underline transition-colors">
                          Try again
                        </button>
                      )}
                    </div>
                  )}

                  <div ref={bottomRef} />
                </div>
              </div>

              {/* Bottom fade — sits between the thread and the composer so
                  answers dissolve into the background as they pass beneath it,
                  rather than terminating at a hard edge. Opaque gradient, not a
                  mask on the scroller; see .composer-fade in globals.css. */}
              <div
                aria-hidden="true"
                className="composer-fade pointer-events-none absolute inset-x-0 bottom-0 z-10"
              />

              {/* Floating composer — overlays the thread instead of sitting
                  below it. Measured by the ResizeObserver above, which is what
                  drives both the fade's height and the scroller's clearance. */}
              <div
                ref={composerRef}
                className={cn(
                  "absolute inset-x-0 bottom-0 z-20",
                  // The card only reaches the physical bottom edge in the
                  // chat-only beta; with full nav on, main's pb-14 already
                  // lifts it clear of the tab bar.
                  isFullNavEnabled() ? undefined : "pb-safe",
                )}
              >
                <ChatInput onSend={handleSend} disabled={chatLoading || !!weeklyLimitDetail} />
              </div>
            </>
          )}
          </div>

          {/* Study panel slot — desktop only. Owns the width (clamp formula,
              100% resolves against this row's own inner width per the
              validated mockup), the single border-left separator, and the
              300ms width transition; StudyPanel's Content (portaled in via
              desktopPanelContainer below) just fills whatever width this
              currently is with `w-full h-full`, so it tracks the transition
              for free with no animation of its own to keep in sync. Closed
              state drops the border too — a 0-width box with a border-left
              still renders a stray 1px sliver otherwise. */}
          <div
            ref={setDesktopPanelContainer}
            className={cn(
              "hidden md:block shrink-0 min-w-0 min-h-0 overflow-hidden transition-[width] duration-300 ease-in-out",
              studyPanelOpen ? "w-[clamp(340px,calc(100%-720px),440px)] border-l border-border" : "w-0"
            )}
          />
        </div>
      </main>

      {/* Right source panel — outside the floating panel so Sheet renders above it */}
      <SourcePanel
        citation={selectedCitation}
        citationIndex={selectedCitationIndex}
        isOpen={isSourcePanelOpen}
        onClose={handleCloseSourcePanel}
      />

      {/* Inline Study Panel (SP2 shell) — declared here (outside the chat
          card) same as SourcePanel above, but geometry v3's desktop branch
          actually renders inside the card via desktopPanelContainer's
          Portal redirect (see study-panel.tsx); this is a Radix Portal
          component, so where it's declared in JSX never determined where
          it painted anyway. Mobile still portals to document.body, as
          always. */}
      <StudyPanel
        isOpen={studyPanelOpen}
        onClose={handleCloseStudyPanel}
        reference={studyReference}
        pins={studyPins.map((p) => p.reference)}
        onTogglePin={handleToggleStudyPin}
        accessToken={accessToken}
        role={userRole}
        userId={user?.id ?? null}
        teacherQuestion={teacherCardQuestion}
        desktopContainer={desktopPanelContainer}
      />

      {authOpen && (
        <LoginModal
          onClose={closeAuth}
          onSignIn={signIn}
          onSignUp={handleSignUpWithPendingPin}
          reason={authReason}
          initialMode={authMode}
        />
      )}
      <ConsentGate accessToken={accessToken} hasUser={!!user} onDecline={signOut} />
    </div>
  );
}
