"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { useChatFocus } from "@/contexts/chat-focus-context";
import { useAuth } from "@/hooks/useAuth";
import { supabase } from "@/lib/supabase";
import { useChat } from "@/hooks/useChat";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import { ChatMessage } from "@/components/rhemata/chat-message";
import { ChatInput } from "@/components/rhemata/chat-input";
import { SourcePanel } from "@/components/rhemata/source-panel";
import { StudyPanel } from "@/components/rhemata/study-panel";
import { PinDropdown } from "@/components/rhemata/pin-dropdown";
import { LoadingIndicator } from "@/components/rhemata/loading-indicator";
import { UsageRing } from "@/components/rhemata/usage-ring";
import { WeeklyLimitCard } from "@/components/rhemata/weekly-limit-card";
import LoginModal from "@/components/auth/LoginModal";
import BetaGate from "@/components/auth/BetaGate";
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
const PENDING_PIN_KEY = "rhemata_pending_pin";

const SUGGESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "Is speaking in tongues for today?",
  "How do I hear God's voice?",
];

export default function Home() {
  const { user, accessToken, signIn, signUp } = useAuth();
  const { role: userRole } = useUserRole(accessToken);
  const [showLogin, setShowLogin] = useState(false);
  const [showGate, setShowGate] = useState(false);
  const [loginInitialMode, setLoginInitialMode] = useState<"signin" | "signup">("signup");
  const [loginReason, setLoginReason] = useState<string | undefined>();

  function openAuthGate(mode: "signin" | "signup" = "signup") {
    setLoginInitialMode(mode);
    if (typeof window !== "undefined" && sessionStorage.getItem("beta_access") === "1") {
      setShowLogin(true);
    } else {
      setShowGate(true);
    }
  }
  const [weeklyLimitDetail, setWeeklyLimitDetail] = useState<WeeklyLimitDetail | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
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
    sendMessage,
    clearMessages,
    loadConversation,
  } = useChat(
    accessToken,
    () => {
      setLoginReason("You've used your 6 free searches. Create a free account to keep going.");
      openAuthGate("signup");
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

  useEffect(() => {
    if (!accessToken) {
      setStudyPins([]);
      return;
    }
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
        setLoginReason("Sign up to save this verse and access it anytime.");
        // Close the panel before opening the auth gate: BetaGate/LoginModal
        // and the study panel's own Radix Dialog overlay are both fixed,
        // full-screen, and z-50 — tied. With the panel left open, its
        // overlay paints on top (later in DOM) and silently swallows every
        // click meant for the modal underneath, even though it looks
        // completely normal in a screenshot. The pending pin already lives
        // in sessionStorage above, independent of the panel's own state, so
        // closing it here doesn't affect whether the pin lands after signup.
        setStudyPanelOpen(false);
        openAuthGate("signup");
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
    [accessToken, studyPins],
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

  // Auto-scroll — only when user is already near the bottom
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < 150) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, chatLoading]);

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
  }

  function handleRetry() {
    if (!lastQuery) return;
    handleNewChat();
    handleSend(lastQuery);
  }

  async function handleSelectConversation(id: string) {
    setIsSourcePanelOpen(false);
    setSelectedCitation(null);
    const msgs = await loadMessages(id);
    loadConversation(id, msgs);
  }

  async function handleDeleteConversation(id: string) {
    await deleteConversation(id);
    if (conversationId === id) {
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
  const { inputFocused } = useChatFocus();

  const [greeting, setGreeting] = useState("What would you like to learn about?");
  useEffect(() => {
    const h = new Date().getHours();
    if (h >= 5 && h < 12) setGreeting("Good morning, what would you like to learn about?");
    else if (h >= 12 && h < 17) setGreeting("Good afternoon, what would you like to learn about?");
    else if (h >= 17 && h < 21) setGreeting("Good evening, what would you like to learn about?");
    else setGreeting("You're up late. What would you like to explore?");
  }, []);

  return (
    // Outermost shell: sidebar tone, full viewport
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
      {/* Sidebar sits directly on this canvas */}
      <Sidebar
        conversations={conversations}
        activeConversationId={conversationId}
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        weeklyUsage={weeklyUsage}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={handleNewChat}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
        onSignInClick={() => { setLoginReason(undefined); openAuthGate("signup"); }}
      />

      {/* Chat card wrapper — inset on desktop, full-bleed on mobile. The
          sidebar NEVER collapses (md:ml-64 is constant); the card's own
          outer bounds never move either, panel open or closed (geometry
          v3, replaces the old padding-right reservation) — only the split
          INSIDE the card between chat region and panel slot changes. */}
      <main
        className={cn(
          "flex flex-1 min-w-0 min-h-0 md:p-2 md:pb-2 md:ml-64",
          // Chat-only beta: no tab bar to clear, so no keyboard-focus
          // toggle needed — just the real bottom safe-area (Phase 4 makes
          // env() non-zero). Flag on: unchanged, 56px reserved for the bar.
          isFullNavEnabled() ? (inputFocused ? "pb-0" : "pb-14") : "pb-safe"
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
          <div className="relative flex flex-col flex-1 min-w-0 min-h-0">

          {/* Mobile floating menu button — replaces full-width bar on mobile.
              LOAD-BEARING once the tab bar is gated off: this is the only
              way to open the drawer on mobile. top-3 (0.75rem) shifted by
              the real inset so it lands at the same visual position as
              today instead of under the notch/status bar. */}
          <button
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
            className="md:hidden absolute top-[calc(0.75rem+env(safe-area-inset-top))] left-3 z-30 h-11 w-11 flex items-center justify-center rounded-full border border-border bg-background text-muted-foreground hover:text-foreground"
          >
            <Menu className="h-5 w-5" />
          </button>
          {/* usage ring moved to drawer (Pass B) */}

          {/* Top bar — desktop only (mobile uses floating button above).
              Pin dropdown is desktop-only in this phase — see Open Flags. */}
          <div className="hidden md:flex h-14 shrink-0 items-center justify-end px-6 z-30 border-b border-border">
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
            <div className="flex flex-1 flex-col items-center justify-center px-4 md:px-12 overflow-hidden overscroll-none min-h-0">
              <h2 suppressHydrationWarning className="font-sans text-2xl md:text-3xl font-semibold text-foreground text-center max-w-lg text-balance">
                {greeting}
              </h2>

              <div className="w-full max-w-2xl mt-8">
                <ChatInput onSend={handleSend} disabled={chatLoading} />
              </div>

              <div className="flex flex-col items-center w-full max-w-xl mt-2 gap-2 mx-auto">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleSend(s)}
                    className="w-full min-h-[44px] text-left rounded-lg bg-popover px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {s}
                  </button>
                ))}
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
              <div ref={scrollContainerRef} className="flex-1 overflow-y-auto min-h-0">
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

              {/* Fixed input area — stays at panel bottom */}
              <ChatInput onSend={handleSend} disabled={chatLoading || !!weeklyLimitDetail} />
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

      {showGate && (
        <BetaGate
          onSuccess={() => { setShowGate(false); setShowLogin(true); }}
          onClose={() => setShowGate(false)}
        />
      )}
      {showLogin && (
        <LoginModal
          onClose={() => { setShowLogin(false); setLoginReason(undefined); }}
          onSignIn={signIn}
          onSignUp={handleSignUpWithPendingPin}
          reason={loginReason}
          initialMode={loginInitialMode}
        />
      )}
    </div>
  );
}
