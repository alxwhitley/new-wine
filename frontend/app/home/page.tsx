"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import BetaGate from "@/components/auth/BetaGate";
import LoginModal from "@/components/auth/LoginModal";

/* ── Inline-style color tokens (mockups only — page uses Tailwind classes) ── */
const C = {
  bg: "hsl(var(--background))",
  fg: "hsl(var(--foreground))",
  cardFg: "hsl(var(--card-foreground))",
  popover: "hsl(var(--popover))",
  primary: "hsl(var(--primary))",
  primaryFg: "hsl(var(--primary-foreground))",
  mutedFg: "hsl(var(--muted-foreground))",
  accent: "hsl(var(--accent))",
  accentFg: "hsl(var(--accent-foreground))",
  border: "hsl(var(--border))",
  sidebar: "hsl(var(--sidebar))",
  gold: "hsl(var(--gold-light))",
  r: "calc(var(--radius) - 4px)",
  rMd: "calc(var(--radius) - 2px)",
  rLg: "var(--radius)",
} as const;

/* ════════════════════════════════════════════════════════
   SHARED MOCK SIDEBAR
════════════════════════════════════════════════════════ */
function MockSidebar({ activeItem }: { activeItem: "chat" | "discover" | "study" }) {
  const items = [
    { id: "chat" as const, icon: "💬", label: "Chat" },
    { id: "discover" as const, icon: "⊙", label: "Discover" },
    { id: "study" as const, icon: "📖", label: "Study" },
  ];
  return (
    <div style={{ width: 200, flexShrink: 0, background: C.sidebar, borderRight: `1px solid ${C.border}`, display: "flex", flexDirection: "column", padding: ".75rem .6rem", gap: ".25rem" }}>
      <div style={{ fontWeight: 700, fontSize: ".95rem", color: C.cardFg, padding: ".4rem .4rem .75rem" }}>Rhemata</div>
      <div style={{ background: C.primary, color: C.primaryFg, borderRadius: C.rMd, padding: ".5rem .75rem", fontSize: ".78rem", fontWeight: 600, display: "flex", alignItems: "center", gap: ".4rem", marginBottom: ".4rem" }}>
        ＋ New Chat
      </div>
      {items.map(({ id, icon, label }) => (
        <div key={id} style={{ display: "flex", alignItems: "center", gap: ".5rem", padding: ".4rem .5rem", borderRadius: C.r, fontSize: ".78rem", color: activeItem === id ? C.accentFg : C.mutedFg, background: activeItem === id ? C.accent : "transparent" }}>
          {icon} {label}
        </div>
      ))}
    </div>
  );
}

/* ════════════════════════════════════════════════════════
   CHAT MOCKUP
════════════════════════════════════════════════════════ */
function ChatMockup() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);

  const runAnimation = useCallback(() => {
    const body = bodyRef.current;
    if (!body) return;

    const blocks: Array<{ type: "head" | "text"; text: string }> = [
      { type: "head", text: "The Biblical Pattern" },
      { type: "text", text: "Hearing God’s voice begins with intimacy, not technique. You recognize His voice by knowing Him deeply — the same way you recognize your spouse’s voice on the phone. Relationship is the foundation." },
      { type: "head", text: "Practical Steps Forward" },
      { type: "text", text: "Jack Deere offers a clear starting point: believe that God speaks to His children, then ask Him to start. God typically speaks through impressions — thoughts that come “out of nowhere,” not manufactured by your own reasoning." },
      { type: "head", text: "The Posture That Hears" },
      { type: "text", text: "Hebrews 3:7–8 warns, “Today, if you hear His voice, do not harden your hearts.” Quietness matters too — life is noisy, and God’s voice is often a gentle whisper." },
    ];

    let delay = 0;
    const wordDelay = 55;

    blocks.forEach((block) => {
      if (block.type === "head") {
        const el = document.createElement("div");
        el.style.cssText = `font-size:.82rem;font-weight:700;color:${C.gold};margin:.75rem 0 .3rem;opacity:0;transition:opacity .3s`;
        el.textContent = block.text;
        body.appendChild(el);
        setTimeout(() => { el.style.opacity = "1"; }, delay);
        delay += 350;
      } else {
        const words = block.text.split(" ");
        const para = document.createElement("div");
        para.style.cssText = `font-size:.78rem;color:${C.fg};line-height:1.75;margin-bottom:.5rem`;
        body.appendChild(para);
        words.forEach((word, i) => {
          const span = document.createElement("span");
          span.textContent = (i === 0 ? "" : " ") + word;
          span.style.cssText = "opacity:0;transition:opacity .08s";
          para.appendChild(span);
          setTimeout(() => { span.style.opacity = "1"; }, delay + i * wordDelay);
        });
        delay += words.length * wordDelay + 200;
      }
    });

    setTimeout(() => {
      const thumbs = document.createElement("div");
      thumbs.style.cssText = `display:flex;gap:.5rem;margin-top:.75rem;opacity:0;transition:opacity .3s`;
      thumbs.innerHTML = `<button style="background:none;border:1px solid ${C.border};border-radius:${C.r};padding:.25rem .5rem;font-size:.75rem;color:${C.mutedFg};cursor:default">👍</button><button style="background:none;border:1px solid ${C.border};border-radius:${C.r};padding:.25rem .5rem;font-size:.75rem;color:${C.mutedFg};cursor:default">👎</button>`;
      body.appendChild(thumbs);
      setTimeout(() => { thumbs.style.opacity = "1"; }, 80);
    }, delay + 300);
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasAnimated.current) {
            hasAnimated.current = true;
            el.style.opacity = "1";
            el.style.transform = "translateY(0)";
            setTimeout(runAnimation, 400);
          }
        });
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [runAnimation]);

  return (
    <div ref={wrapRef} style={{ opacity: 0, transform: "translateY(28px)", transition: "opacity .65s ease, transform .65s ease", borderRadius: C.rLg, overflow: "hidden", background: C.sidebar, border: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", height: 480, fontSize: 13 }}>
        <MockSidebar activeItem="chat" />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: C.bg }}>
          <div style={{ flex: 1, overflow: "hidden", padding: "1.5rem 1.75rem", display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div style={{ alignSelf: "flex-end", fontSize: ".78rem", color: C.mutedFg }}>How do I hear God&rsquo;s voice?</div>
            <div ref={bodyRef} />
          </div>
          <div style={{ borderTop: `1px solid ${C.border}`, padding: ".75rem 1rem", display: "flex", alignItems: "center", gap: ".5rem" }}>
            <span style={{ fontSize: ".62rem", color: C.mutedFg, opacity: .5, marginRight: ".25rem" }}>1/50</span>
            <div style={{ flex: 1, background: C.popover, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: ".5rem .75rem", fontSize: ".78rem", color: C.mutedFg }}>Enter your prompt…</div>
            <div style={{ background: C.primary, borderRadius: C.r, width: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4z"/></svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
   STUDY MOCKUP
════════════════════════════════════════════════════════ */
const INTERLINEAR = [
  { gk: "Ἐν", en: "In", sn: "G1722" },
  { gk: "ἀρχῇ", en: "beginning", sn: "G746" },
  { gk: "ἦν", en: "was", sn: "G1510" },
  { gk: "ὁ", en: "the", sn: "G3588" },
  { gk: "λόγος", en: "Word", sn: "G3056" },
  { gk: "καὶ", en: "and", sn: "G2532" },
  { gk: "ὁ", en: "the", sn: "G3588" },
  { gk: "λόγος", en: "Word", sn: "G3056" },
  { gk: "ἦν", en: "was", sn: "G1510" },
  { gk: "πρὸς", en: "with", sn: "G4314" },
  { gk: "τὸν", en: "the", sn: "G3588" },
];

function StudyMockup() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);
  const [activeWord, setActiveWord] = useState(4);
  const [showDef, setShowDef] = useState(false);
  const [showCommentary, setShowCommentary] = useState(false);

  const runAnimation = useCallback(() => {
    const scanOrder = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 4];
    let t = 0;
    scanOrder.forEach((idx, i) => {
      setTimeout(() => setActiveWord(idx), t);
      t += i < scanOrder.length - 1 ? 320 : 0;
    });
    setTimeout(() => setShowDef(true), t + 200);
    setTimeout(() => setShowCommentary(true), t + 700);
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasAnimated.current) {
            hasAnimated.current = true;
            el.style.opacity = "1";
            el.style.transform = "translateY(0)";
            setTimeout(runAnimation, 400);
          }
        });
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [runAnimation]);

  return (
    <div ref={wrapRef} style={{ opacity: 0, transform: "translateY(28px)", transition: "opacity .65s ease, transform .65s ease", borderRadius: C.rLg, overflow: "hidden", background: C.sidebar, border: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", height: 520, fontSize: 13 }}>
        <MockSidebar activeItem="study" />
        <div style={{ flex: 1, overflow: "hidden", background: C.bg, display: "flex", flexDirection: "column" }}>
          {/* Search row */}
          <div style={{ display: "flex", alignItems: "center", gap: ".5rem", padding: ".75rem 1.25rem", borderBottom: `1px solid ${C.border}` }}>
            <input readOnly value="John 1:1" style={{ flex: 1, background: C.popover, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: ".45rem .75rem", fontSize: ".78rem", color: C.cardFg, fontFamily: "inherit" }} />
            <div style={{ background: C.primary, borderRadius: C.rMd, width: 28, height: 28, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </div>
            <button style={{ background: "none", border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: ".3rem .6rem", fontSize: ".72rem", color: C.mutedFg, cursor: "default", fontFamily: "inherit" }}>View Chapter</button>
          </div>
          {/* Tabs */}
          <div style={{ display: "flex", padding: ".5rem 1.25rem 0", borderBottom: `1px solid ${C.border}` }}>
            {["Words", "Commentary", "Pastors’ Notes"].map((tab, i) => (
              <div key={tab} style={{ padding: ".4rem .75rem", fontSize: ".78rem", cursor: "default", color: i === 0 ? C.cardFg : C.mutedFg, borderBottom: i === 0 ? `2px solid ${C.cardFg}` : "2px solid transparent", marginBottom: -1 }}>{tab}</div>
            ))}
          </div>
          {/* Content */}
          <div style={{ flex: 1, overflow: "hidden", padding: "1rem 1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Verse panel */}
            <div style={{ border: `1px solid ${C.border}`, borderRadius: C.rLg, overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: ".4rem .75rem", borderBottom: `1px solid ${C.border}`, fontSize: ".65rem", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase", color: C.mutedFg }}>
                <span>←</span><span>JOHN 1:1 (WEB)</span><span>→</span>
              </div>
              <div style={{ padding: ".6rem .75rem", fontSize: ".82rem", color: C.cardFg, lineHeight: 1.6, borderBottom: `1px solid ${C.border}` }}>
                In the beginning was the Word, and the Word was with God, and the Word was God.
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: ".3rem", padding: ".65rem .75rem" }}>
                {INTERLINEAR.map((w, idx) => (
                  <div key={idx} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1, border: `1px solid ${activeWord === idx ? C.primary : C.border}`, borderRadius: C.r, padding: ".3rem .45rem", cursor: "default", background: activeWord === idx ? "hsl(var(--primary) / 0.1)" : "transparent", transition: "background .15s, border-color .15s", minWidth: 44 }}>
                    <span style={{ fontSize: ".8rem", color: C.gold, fontFamily: "ui-serif, Georgia, serif" }}>{w.gk}</span>
                    <span style={{ fontSize: ".62rem", color: C.cardFg, fontWeight: 500 }}>{w.en}</span>
                    <span style={{ fontSize: ".52rem", color: C.mutedFg, fontFamily: "ui-monospace, monospace" }}>{w.sn}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* Definition panel */}
            <div style={{ border: "1px solid hsl(var(--primary) / 0.4)", borderRadius: C.rLg, padding: ".65rem .85rem", background: "hsl(var(--primary) / 0.06)", display: "flex", flexDirection: "column", gap: ".3rem", opacity: showDef ? 1 : 0, transform: showDef ? "translateY(0)" : "translateY(6px)", transition: "opacity .3s ease, transform .3s ease" }}>
              <div style={{ fontSize: ".72rem", fontWeight: 700, color: C.gold }}>λόγος · Word, G3056</div>
              <div style={{ fontSize: ".62rem", color: C.mutedFg, fontFamily: "ui-monospace, monospace" }}>Strong&rsquo;s G3056 · logos · lógos</div>
              <div style={{ fontSize: ".71rem", color: C.fg, lineHeight: 1.6 }}>A word, utterance, or account; in John&rsquo;s prologue, the eternal personal expression of God — the divine Reason through whom all things were made.</div>
            </div>
            {/* Commentary */}
            <div>
              <div style={{ fontSize: ".62rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: C.mutedFg, opacity: .7, marginBottom: ".4rem" }}>COMMENTARY</div>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: C.rLg, padding: ".65rem .85rem", display: "flex", flexDirection: "column", gap: ".2rem", opacity: showCommentary ? 1 : 0, transform: showCommentary ? "translateY(0)" : "translateY(6px)", transition: "opacity .4s ease, transform .4s ease" }}>
                <div style={{ fontSize: ".75rem", fontWeight: 600, color: C.gold }}>Adam Clarke</div>
                <div style={{ fontSize: ".65rem", color: C.mutedFg }}>Adam Clarke&rsquo;s Commentary — John</div>
                <div style={{ fontSize: ".72rem", color: C.fg, lineHeight: 1.6, marginTop: ".15rem" }}>In the beginning — That is, before any thing was formed — ere God began the great work of creation. This is the meaning of the word in Gen 1:1, to which John plainly alludes…</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
   DISCOVER MOCKUP
════════════════════════════════════════════════════════ */
function DiscoverMockup() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const featuredRef = useRef<HTMLDivElement>(null);
  const card1Ref = useRef<HTMLDivElement>(null);
  const card2Ref = useRef<HTMLDivElement>(null);
  const pillsRef = useRef<HTMLDivElement>(null);
  const hasAnimated = useRef(false);

  const runAnimation = useCallback(() => {
    const featured = featuredRef.current;
    if (featured) {
      featured.style.transition = "background .3s, border-color .3s";
      featured.style.background = "hsl(var(--primary) / 0.07)";
      featured.style.borderColor = "hsl(var(--primary) / 0.3)";
      setTimeout(() => { featured.style.background = ""; featured.style.borderColor = ""; }, 700);
    }

    const flash = (el: HTMLDivElement | null, delay: number) => {
      setTimeout(() => {
        if (!el) return;
        el.style.transition = "background .2s, border-color .2s";
        el.style.background = "hsl(var(--primary) / 0.08)";
        el.style.borderColor = "hsl(var(--primary) / 0.3)";
        setTimeout(() => { el.style.background = ""; el.style.borderColor = ""; }, 600);
      }, delay);
    };
    flash(card1Ref.current, 1000);
    flash(card2Ref.current, 1500);

    const pills = pillsRef.current;
    if (pills) {
      Array.from(pills.children).forEach((pill, i) => {
        setTimeout(() => {
          const el = pill as HTMLElement;
          el.style.transition = "border-color .2s, color .2s";
          el.style.borderColor = "hsl(var(--gold-light) / 0.6)";
          el.style.color = C.gold;
          setTimeout(() => { el.style.borderColor = ""; el.style.color = ""; }, 400);
        }, 2200 + i * 180);
      });
    }
  }, []);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting && !hasAnimated.current) {
            hasAnimated.current = true;
            el.style.opacity = "1";
            el.style.transform = "translateY(0)";
            setTimeout(runAnimation, 400);
          }
        });
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [runAnimation]);

  const cardBase: React.CSSProperties = { border: `1px solid ${C.border}`, borderRadius: C.rLg, padding: ".65rem .8rem", display: "flex", flexDirection: "column", gap: ".3rem" };

  return (
    <div ref={wrapRef} style={{ opacity: 0, transform: "translateY(28px)", transition: "opacity .65s ease, transform .65s ease", borderRadius: C.rLg, overflow: "hidden", background: C.sidebar, border: `1px solid ${C.border}` }}>
      <div style={{ display: "flex", height: 520, fontSize: 13 }}>
        <MockSidebar activeItem="discover" />
        <div style={{ flex: 1, overflow: "hidden", background: C.bg, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, overflow: "hidden", padding: "1rem 1.5rem", display: "flex", flexDirection: "column", gap: ".85rem" }}>
            {/* Heading */}
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "1.15rem", fontWeight: 600, color: C.cardFg }}>Discover</div>
              <div style={{ fontSize: ".72rem", color: C.mutedFg }}>Sermons, articles, and books from the charismatic tradition</div>
            </div>
            {/* Search */}
            <div style={{ display: "flex", gap: ".5rem" }}>
              <div style={{ flex: 1, background: C.popover, border: `1px solid ${C.border}`, borderRadius: C.rMd, padding: ".4rem .7rem", fontSize: ".75rem", color: C.mutedFg }}>🔍 Search articles, authors, topics…</div>
              <div style={{ background: C.primary, color: C.primaryFg, borderRadius: C.rMd, padding: ".4rem .8rem", fontSize: ".75rem", fontWeight: 600 }}>Search</div>
            </div>
            {/* Featured */}
            <div ref={featuredRef} style={{ border: `1px solid ${C.border}`, borderRadius: C.rLg, padding: ".8rem 1rem", display: "grid", gridTemplateColumns: "1fr 80px", gap: ".75rem", alignItems: "start" }}>
              <div>
                <div style={{ fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: C.gold, marginBottom: ".2rem" }}>
                  ARTICLE · <span style={{ color: C.mutedFg, fontWeight: 400 }}>Ern Baxter</span>
                </div>
                <div style={{ fontSize: ".9rem", fontWeight: 600, color: C.cardFg, marginBottom: ".25rem", lineHeight: 1.3 }}>What Makes God Angry?</div>
                <div style={{ fontSize: ".7rem", color: C.mutedFg, lineHeight: 1.55 }}>New Wine · January 1978 — God&rsquo;s anger originates in perfect holiness and justice…</div>
                <div style={{ fontSize: ".65rem", color: C.mutedFg, opacity: .6, marginTop: ".3rem" }}>1978</div>
              </div>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: C.rMd, aspectRatio: "3/2", background: C.accent, display: "flex", alignItems: "center", justifyContent: "center", fontSize: "1.25rem", opacity: .3 }}>◆</div>
            </div>
            {/* Sermon cards */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".6rem" }}>
              <div ref={card1Ref} style={cardBase}>
                <div style={{ fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: C.gold }}>
                  SERMON · <span style={{ fontWeight: 400, color: C.mutedFg }}>John Bevere</span>
                </div>
                <div style={{ fontSize: ".78rem", fontWeight: 600, color: C.cardFg, lineHeight: 1.3 }}>Proof That God Still Speaks Today</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: ".3rem", marginTop: ".1rem" }}>
                  {["Discerning God’s Voice", "Hearing God’s Voice"].map((tag) => (
                    <span key={tag} style={{ fontSize: ".58rem", background: C.popover, border: `1px solid ${C.border}`, borderRadius: C.r, padding: ".15rem .45rem", color: C.mutedFg }}>{tag}</span>
                  ))}
                </div>
              </div>
              <div ref={card2Ref} style={cardBase}>
                <div style={{ fontSize: ".6rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: C.gold }}>
                  SERMON · <span style={{ fontWeight: 400, color: C.mutedFg }}>Derek Prince</span>
                </div>
                <div style={{ fontSize: ".78rem", fontWeight: 600, color: C.cardFg, lineHeight: 1.3 }}>Motivation for Living To Do God&rsquo;s Will</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: ".3rem", marginTop: ".1rem" }}>
                  {["God’s Will and Guidance", "Purpose and Calling"].map((tag) => (
                    <span key={tag} style={{ fontSize: ".58rem", background: C.popover, border: `1px solid ${C.border}`, borderRadius: C.r, padding: ".15rem .45rem", color: C.mutedFg }}>{tag}</span>
                  ))}
                </div>
              </div>
            </div>
            {/* Stats strip */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", border: `1px solid ${C.border}`, borderRadius: C.rLg, overflow: "hidden" }}>
              {[["33", "Articles"], ["755", "Sermons"], ["50", "Books"]].map(([n, l], i) => (
                <div key={l} style={{ padding: ".55rem .85rem", display: "flex", alignItems: "center", justifyContent: "space-between", borderRight: i < 2 ? `1px solid ${C.border}` : "none" }}>
                  <div>
                    <div style={{ fontSize: "1.2rem", fontWeight: 700, color: C.cardFg }}>{n}</div>
                    <div style={{ fontSize: ".65rem", color: C.mutedFg }}>{l}</div>
                  </div>
                  <span style={{ fontSize: ".75rem", color: C.mutedFg, opacity: .4 }}>→</span>
                </div>
              ))}
            </div>
            {/* Author pills */}
            <div>
              <div style={{ fontSize: ".62rem", fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: C.mutedFg, opacity: .7, marginBottom: ".4rem" }}>Browse by author</div>
              <div ref={pillsRef} style={{ display: "flex", gap: ".4rem", flexWrap: "wrap" }}>
                {[["DP", "Derek Prince"], ["BM", "Bob Mumford"], ["EB", "Ern Baxter"], ["CS", "Charles Simpson"], ["DB", "Don Basham"]].map(([init, name]) => (
                  <div key={name} style={{ display: "flex", alignItems: "center", gap: ".3rem", border: `1px solid ${C.border}`, borderRadius: "100px", padding: ".2rem .55rem .2rem .3rem", fontSize: ".65rem", color: C.mutedFg, cursor: "default" }}>
                    <div style={{ width: 18, height: 18, borderRadius: "50%", background: "hsl(var(--primary) / 0.2)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: ".5rem", fontWeight: 700, color: C.gold, flexShrink: 0 }}>{init}</div>
                    {name}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
   MARQUEE
════════════════════════════════════════════════════════ */
const ROW1 = [
  "What is the baptism of the Holy Spirit?",
  "How do I receive the gift of tongues?",
  "Is speaking in tongues for every believer?",
  "What’s the difference between the gift of tongues and a prayer language?",
  "How do I grow in the prophetic?",
  "What does it mean to be anointed?",
  "How do I know if a prophetic word is from God?",
  "What is the laying on of hands?",
];
const ROW2 = [
  "What is the fivefold ministry?",
  "What’s the role of the apostle and prophet today?",
  "How do I stir up the gift within me?",
  "What does it mean to be filled with the Spirit?",
  "How do I activate the gifts of the Spirit?",
  "What is the difference between the anointing and the fruit of the Spirit?",
  "How do I interpret tongues?",
  "What does Scripture say about prophecy in the church?",
];

function Pill({ text }: { text: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: ".4rem", background: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: "100px", padding: ".4rem .9rem", fontSize: ".78rem", color: "hsl(var(--muted-foreground))", whiteSpace: "nowrap" }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: "hsl(var(--gold-light))", flexShrink: 0, display: "inline-block" }} />
      {text}
    </span>
  );
}

function Marquee() {
  return (
    <div style={{ padding: "2.5rem 0", overflow: "hidden", position: "relative" }}>
      <div style={{ pointerEvents: "none", position: "absolute", top: 0, bottom: 0, left: 0, width: 100, background: "linear-gradient(to right, hsl(var(--background)), transparent)", zIndex: 2 }} />
      <div style={{ pointerEvents: "none", position: "absolute", top: 0, bottom: 0, right: 0, width: 100, background: "linear-gradient(to left, hsl(var(--background)), transparent)", zIndex: 2 }} />
      <div className="marquee-track" style={{ display: "flex", gap: ".625rem", width: "max-content", animation: "marquee-left 88s linear infinite", marginBottom: ".625rem" }}>
        {[...ROW1, ...ROW1].map((t, i) => <Pill key={i} text={t} />)}
      </div>
      <div className="marquee-track" style={{ display: "flex", gap: ".625rem", width: "max-content", animation: "marquee-right 72s linear infinite" }}>
        {[...ROW2, ...ROW2].map((t, i) => <Pill key={i} text={t} />)}
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════
   SECTION LABEL
════════════════════════════════════════════════════════ */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[.7rem] font-bold tracking-[.14em] uppercase text-gold-light mb-4">{children}</p>
  );
}

/* ════════════════════════════════════════════════════════
   EXPLORE CARDS DATA
════════════════════════════════════════════════════════ */
const EXPLORE_CARDS = [
  { icon: "🔡", title: "Greek & Hebrew Interlinear", body: "138,000+ word entries spanning the entire Greek NT and Hebrew OT. Tap any word for Strong’s definition, transliteration, and lexical data." },
  { icon: "✡️", title: "Jewish Perspective", body: "For every verse: Jewish historical context, Messianic perspective, and cultural setting — generated with numbered citations like a research paper." },
  { icon: "📌", title: "Pastors’ Notes", body: "Vetted pastors and ministry leaders annotate Bible verses with insights and pastoral wisdom. Three-tier role system: user, contributor, admin." },
  { icon: "📖", title: "Deep Word Studies", body: "1,700+ Greek and Hebrew word studies from Precept Austin, cross-referenced to the interlinear. Every Strong’s number links to its full article." },
  { icon: "🏛️", title: "Patristic Commentary", body: "186 documents from the Church Fathers — Chrysostom, Matthew Henry, Adam Clarke, JFB — giving historical grounding to charismatic study." },
  { icon: "🎙️", title: "Charismatic Corpus", body: "Sermon transcripts from trusted charismatic voices alongside New Wine Magazine’s archive — curated for theological reliability, not just volume." },
];

/* ════════════════════════════════════════════════════════
   PAGE
════════════════════════════════════════════════════════ */
export default function HomePage() {
  const { signIn, signUp } = useAuth();
  const [showGate, setShowGate] = useState(false);
  const [showLogin, setShowLogin] = useState(false);

  function openAuthGate() {
    if (typeof window !== "undefined" && sessionStorage.getItem("beta_access") === "1") {
      setShowLogin(true);
    } else {
      setShowGate(true);
    }
  }

  return (
    <>
    <div className="bg-background text-foreground min-h-screen font-sans antialiased overflow-x-hidden">

      {/* ── NAV ── */}
      <nav className="fixed top-0 inset-x-0 z-50 h-14 flex items-center justify-between px-6 md:px-8 border-b border-border" style={{ background: "hsl(var(--background) / 0.9)", backdropFilter: "blur(14px)" }}>
        <Link href="/" className="text-[1.1rem] font-semibold text-card-foreground no-underline hover:opacity-80 transition-opacity">
          Rhemata
        </Link>
        <ul className="hidden md:flex items-center gap-7 list-none m-0 p-0">
          {([["About", "#"], ["Features", "#"], ["Discover", "/library"], ["Study", "/study"]] as [string, string][]).map(([label, href]) => (
            <li key={label}>
              <Link href={href} className="text-sm font-medium text-muted-foreground hover:text-card-foreground transition-colors no-underline">
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={openAuthGate}>Become a test user</Button>
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="pt-[130px] pb-16 px-6 text-center max-w-[860px] mx-auto">
        <div className="inline-flex items-center gap-1.5 border border-border rounded-full px-3.5 py-1 text-[.72rem] font-semibold tracking-[.12em] uppercase text-muted-foreground mb-6">
          <span className="w-[5px] h-[5px] rounded-full bg-primary shrink-0" />
          Now in beta
        </div>
        <h1 className="font-serif text-[clamp(2.4rem,5.5vw,4.2rem)] font-semibold leading-[1.12] tracking-[-0.025em] mb-5 text-card-foreground text-balance">
          Faithful answers from sources you can trust.
        </h1>
        <p className="text-lg text-muted-foreground max-w-[580px] mx-auto mb-8 leading-[1.75]">
          Rhemata is an AI-assisted Bible study tool trained on trusted resources rooted in the charismatic tradition — now in early beta, and looking for testers.
        </p>
        <div className="flex items-center justify-center gap-3 flex-wrap">
          <Button size="lg" onClick={openAuthGate}>Become a test user</Button>
          <Button variant="outline" size="lg" asChild>
            <Link href="/">Try it free — no account needed</Link>
          </Button>
        </div>
      </section>

      {/* ── MARQUEE ── */}
      <Marquee />

      {/* ── WHY IT MATTERS ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1000px] mx-auto">
          <p className="text-[.7rem] font-bold tracking-[.14em] uppercase text-center mb-4" style={{ color: "hsl(var(--gold-light))" }}>
            Why It Matters
          </p>
          <h2 className="font-serif text-[clamp(1.7rem,3.5vw,2.6rem)] font-semibold leading-[1.2] text-card-foreground text-balance text-center max-w-[20ch] mx-auto mb-12">
            When you ask general AI about God, who&rsquo;s actually answering?
          </h2>

          {/* Two-column contrast */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-10">
            {/* Left — General AI */}
            <div className="border border-border rounded-lg p-7 bg-background">
              <div className="flex items-center gap-[.45rem] text-[.65rem] font-bold tracking-[.1em] uppercase text-muted-foreground mb-4">
                <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: "hsl(var(--muted-foreground) / 0.5)" }} />
                General AI models
              </div>
              <h3 className="font-serif text-[1.15rem] font-semibold text-card-foreground leading-[1.3] mb-[1.1rem]">
                Everything at once. No one in particular.
              </h3>
              <ul className="flex flex-col gap-[.85rem] list-none m-0 p-0">
                {[
                  "Averages every tradition, blog, and contradicting opinion into one flattened answer.",
                  "No source is trusted over another.",
                  "Applies its own content filters to theology — softening or avoiding positions it’s trained to treat as sensitive.",
                  "No name stands behind the answer.",
                ].map((text) => (
                  <li key={text} className="relative pl-[1.4rem] text-[.92rem] text-muted-foreground leading-[1.55]">
                    <span className="absolute left-0 top-[.05rem] text-[.85rem]" style={{ color: "hsl(var(--muted-foreground) / 0.5)" }}>✕</span>
                    {text}
                  </li>
                ))}
              </ul>
            </div>

            {/* Right — Rhemata */}
            <div className="rounded-lg p-7 bg-accent" style={{ border: "1px solid hsl(var(--gold-light) / 0.3)" }}>
              <div className="flex items-center gap-[.45rem] text-[.65rem] font-bold tracking-[.1em] uppercase mb-4" style={{ color: "hsl(var(--gold-light))" }}>
                <span className="w-[7px] h-[7px] rounded-full shrink-0" style={{ background: "hsl(var(--gold-light))" }} />
                Rhemata
              </div>
              <h3 className="font-serif text-[1.15rem] font-semibold text-card-foreground leading-[1.3] mb-[1.1rem]">
                A known, trusted lineage.
              </h3>
              <ul className="flex flex-col gap-[.85rem] list-none m-0 p-0">
                {[
                  "Drawn only from vetted sources within the charismatic tradition.",
                  "No hidden filters — your convictions aren’t treated as something to soften.",
                  "Every answer points back to the voices behind it.",
                  "You always know whose shoulders an answer stands on.",
                ].map((text) => (
                  <li key={text} className="relative pl-[1.4rem] text-[.92rem] text-foreground leading-[1.55]">
                    <span className="absolute left-0 top-[.05rem] text-[.85rem]" style={{ color: "hsl(var(--gold-light))" }}>✓</span>
                    {text}
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Pull-quote */}
          <blockquote className="font-serif italic text-[clamp(1.3rem,2.6vw,1.7rem)] leading-[1.4] text-card-foreground text-center max-w-[24ch] mx-auto pt-8 pb-2 border-none m-0">
            &ldquo;You wouldn&rsquo;t take spiritual counsel from{" "}
            <span style={{ color: "hsl(var(--gold-light))" }}>a stranger with no name.</span>&rdquo;
          </blockquote>
          <p className="text-base text-muted-foreground text-center max-w-[52ch] mx-auto mt-4 leading-[1.7]">
            In matters of faith, <em>who</em> is speaking matters. Rhemata is built on voices you&rsquo;d actually choose.
          </p>
        </div>
      </section>

      {/* ── FEATURE: CHAT ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center">
          <div>
            <SectionLabel>Ask Anything</SectionLabel>
            <h2 className="font-serif text-[clamp(1.7rem,3vw,2.4rem)] font-semibold leading-[1.2] mb-5 text-card-foreground text-balance">
              Trained on trusted voices. Not everything at once.
            </h2>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              Ask any question in plain language and get a clear, faithful answer — drawn only from 2,600+ vetted sources within the charismatic tradition.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              That includes historic voices like <strong className="text-card-foreground font-semibold">Derek Prince</strong> and <strong className="text-card-foreground font-semibold">Bob Mumford</strong>, alongside trusted modern-day teachers like <strong className="text-card-foreground font-semibold">John Bevere</strong>, <strong className="text-card-foreground font-semibold">Michael Koulianos</strong>, and <strong className="text-card-foreground font-semibold">Dr. Michael Brown</strong>.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75]">
              Every answer points back to the voices behind it — and where a source is available in full, you can open and read it yourself.
            </p>
          </div>
          <ChatMockup />
        </div>
      </section>

      {/* ── FEATURE: DISCOVER ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center">
          <div className="order-2 md:order-1">
            <DiscoverMockup />
          </div>
          <div className="order-1 md:order-2">
            <SectionLabel>Discover</SectionLabel>
            <h2 className="font-serif text-[clamp(1.7rem,3vw,2.4rem)] font-semibold leading-[1.2] mb-5 text-card-foreground text-balance">
              See what taught the AI. Find new voices you&rsquo;ll love.
            </h2>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              Discover is the window into the library behind every answer. See the voices and sources the AI draws from — and read the ones available in full.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              It&rsquo;s also where you stumble onto voices you&rsquo;ve never heard. Overlooked teachers, out-of-print books, and forgotten articles surfaced fresh — the next great book lost to history, waiting to be found again.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-5">
              New content is added every day.
            </p>
            <Link href="/library" className="inline-flex items-center gap-1 text-sm font-semibold no-underline hover:opacity-80 transition-opacity" style={{ color: "hsl(var(--gold-light))" }}>
              Explore Discover →
            </Link>
          </div>
        </div>
      </section>

      {/* ── FEATURE: STUDY ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-2 gap-10 md:gap-16 items-center">
          <div>
            <SectionLabel>Study</SectionLabel>
            <h2 className="font-serif text-[clamp(1.7rem,3vw,2.4rem)] font-semibold leading-[1.2] mb-5 text-card-foreground text-balance">
              AI should send you deeper — not do the thinking for you.
            </h2>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              There&rsquo;s something irreplaceable about wrestling with Scripture yourself. Study exists to protect that. It&rsquo;s the companion to the chat — built so you grow in the Word, not grow dependent on a tool.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-3.5">
              Open any verse for the full Greek and Hebrew interlinear, tap any word for its Strong&rsquo;s number and definition, and read commentary spanning the whole history of the church.
            </p>
            <p className="text-muted-foreground text-[1.0625rem] leading-[1.75] mb-5">
              And it&rsquo;s alive with community. <strong className="text-card-foreground font-semibold">Trusted contributors — pastors and leaders in local communities all across the world — add devotional notes to the passages they&rsquo;re personally reading right now.</strong> Real insight from real shepherds, attached to the verse in front of you.
            </p>
            <Link href="/study" className="inline-flex items-center gap-1 text-sm font-semibold no-underline hover:opacity-80 transition-opacity" style={{ color: "hsl(var(--gold-light))" }}>
              Explore Study →
            </Link>
          </div>
          <StudyMockup />
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1100px] mx-auto text-center">
          <SectionLabel>The Library Behind It</SectionLabel>
          <h2 className="font-serif text-[clamp(1.85rem,3.5vw,2.8rem)] font-semibold leading-[1.2] mb-5 text-card-foreground text-balance">
            Depth you can trust, growing every day.
          </h2>
          <p className="text-muted-foreground text-[1.05rem] max-w-[580px] mx-auto mb-12 leading-[1.75]">
            Built from a curated library of sermon transcripts, word studies, books, commentaries, and modern day pastor&rsquo;s notes — sourced from trusted voices within the charismatic and Spirit-filled tradition.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { num: "2,600+", label: "Source Documents" },
              { num: "1,700+", label: "Word Studies" },
              { num: "186", label: "Commentaries" },
              { num: "Added", label: "Daily" },
            ].map(({ num, label }) => (
              <div key={label} className="bg-card border border-border rounded-lg p-6">
                <div className="font-serif text-[2.1rem] font-semibold leading-none mb-1.5" style={{ color: "hsl(var(--gold-light))" }}>{num}</div>
                <div className="text-[.8rem] text-muted-foreground font-medium">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── EXPLORE MORE ── */}
      <section className="py-20 px-6 border-t border-border">
        <div className="max-w-[1100px] mx-auto">
          <div className="mb-11">
            <h2 className="font-serif text-[clamp(1.7rem,3vw,2.4rem)] font-semibold text-card-foreground">
              Explore more in Rhemata
            </h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {EXPLORE_CARDS.map(({ icon, title, body }) => (
              <div key={title} className="bg-card border border-border rounded-lg p-6 hover:border-input transition-colors">
                <div className="w-[38px] h-[38px] rounded-[9px] flex items-center justify-center text-base mb-3.5" style={{ background: "hsl(var(--primary) / 0.1)", border: "1px solid hsl(var(--gold-light) / 0.2)" }}>
                  {icon}
                </div>
                <h3 className="font-serif text-base font-semibold mb-2 text-card-foreground">{title}</h3>
                <p className="text-[.85rem] text-muted-foreground leading-[1.65]">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="py-28 px-6 text-center border-t border-border">
        <h2 className="font-serif text-[clamp(1.85rem,3.5vw,2.8rem)] font-semibold leading-[1.2] max-w-[560px] mx-auto mb-3 text-card-foreground text-balance">
          Help us build it. Become a test user.
        </h2>
        <p className="text-muted-foreground text-base mb-8">Rhemata is in active beta. Jump in free, explore everything, and help shape where it goes — no card required.</p>
        <Button size="lg" onClick={openAuthGate}>Become a test user</Button>
      </section>

      {/* ── FOOTER ── */}
      <footer className="bg-sidebar border-t border-border pt-12 pb-8 px-6">
        <div className="max-w-[1100px] mx-auto grid grid-cols-1 md:grid-cols-[1fr_auto] gap-12 items-start mb-8">
          <div>
            <div className="font-serif text-[.95rem] font-semibold text-card-foreground mb-2.5">Rhemata</div>
            <p className="text-[.8125rem] text-muted-foreground max-w-[260px] leading-[1.6]">
              Spirit-led Bible study for the charismatic tradition. Scholarly but accessible. Conviction, not performance.
            </p>
          </div>
          <div className="flex gap-14">
            <div>
              <h4 className="text-[.68rem] font-bold uppercase tracking-[.12em] mb-3.5" style={{ color: "hsl(var(--muted-foreground) / 0.7)" }}>Product</h4>
              <ul className="space-y-2 list-none m-0 p-0">
                {(["Chat", "Study", "Discover", "Pastors’ Notes"] as string[]).map((label) => (
                  <li key={label}>
                    <Link href="/" className="text-[.85rem] text-muted-foreground hover:text-card-foreground transition-colors no-underline">{label}</Link>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-[.68rem] font-bold uppercase tracking-[.12em] mb-3.5" style={{ color: "hsl(var(--muted-foreground) / 0.7)" }}>Company</h4>
              <ul className="space-y-2 list-none m-0 p-0">
                {(["About", "Contact", "Privacy Policy", "Terms of Service"] as string[]).map((label) => (
                  <li key={label}>
                    <Link href="/" className="text-[.85rem] text-muted-foreground hover:text-card-foreground transition-colors no-underline">{label}</Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
        <div className="max-w-[1100px] mx-auto pt-6 border-t border-border flex flex-col md:flex-row justify-between items-center gap-3">
          <p className="text-[.78rem]" style={{ color: "hsl(var(--muted-foreground) / 0.7)" }}>© 2026 Rhemata. All rights reserved.</p>
          <p className="font-serif italic text-[.78rem]" style={{ color: "hsl(var(--muted-foreground) / 0.7)" }}>ῥήματά ἐστιν πνεῦμα καὶ ζωή εἰσιν — John 6:63</p>
        </div>
      </footer>

    </div>

    {showGate && (
      <BetaGate
        onSuccess={() => { setShowGate(false); setShowLogin(true); }}
        onClose={() => setShowGate(false)}
      />
    )}
    {showLogin && (
      <LoginModal
        onClose={() => setShowLogin(false)}
        onSignIn={signIn}
        onSignUp={signUp}
        initialMode="signup"
      />
    )}
    </>
  );
}
