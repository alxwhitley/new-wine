"use client";

import Link from "next/link";

import LoginModal from "@/components/auth/LoginModal";
import { useAuthGate } from "@/hooks/useAuthGate";
import { FooterNav } from "@/components/marketing/footer-nav";
import { NewWineDawnHero } from "@/components/marketing/newwine-dawn-hero";
import { ProductImagePlaceholder } from "@/components/marketing/product-image-placeholder";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";
import { isFullNavEnabled } from "@/lib/chat-only-beta-flag";

import styles from "./home.module.css";

const QUESTIONS = [
  "What is the baptism of the Holy Spirit?",
  "How do I receive the gift of tongues?",
  "How do I grow in the prophetic?",
  "What does it mean to be anointed?",
  "What is the fivefold ministry?",
  "How do I stir up the gift within me?",
  "What does Scripture say about prophecy in the church?",
];

const EXPLORE_CARDS = [
  { marker: "01", title: "Greek & Hebrew Interlinear", body: "138,000+ word entries spanning the entire Greek NT and Hebrew OT. Tap any word for Strong’s definition, transliteration, and lexical data." },
  { marker: "02", title: "Pastors’ Notes", body: "Coming: vetted pastors and ministry leaders annotating verses with bylined devotional notes. The vetting is the feature — every note from a named shepherd, none of it AI-generated." },
  { marker: "03", title: "Deep Word Studies", body: "1,700+ Greek and Hebrew word studies from Precept Austin, cross-referenced to the interlinear. Every Strong’s number links to its full article." },
  { marker: "04", title: "Patristic Commentary", body: "186 commentaries spanning the Church Fathers through Matthew Henry, Adam Clarke, and Jamieson-Fausset-Brown — historical grounding for Spirit-filled study." },
  { marker: "05", title: "Charismatic Corpus", body: "Sermon transcripts from trusted charismatic voices alongside New Wine Magazine’s archive — curated for theological reliability, not just volume." },
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className={styles.sectionLabel}>{children}</p>;
}

function QuestionRail() {
  return (
    <div className={styles.questionRail} aria-label="Questions New Wine can help explore">
      <div className={styles.questionTrack}>
        {[...QUESTIONS, ...QUESTIONS].map((question, index) => (
          <span key={`${question}-${index}`} className={styles.question} aria-hidden={index >= QUESTIONS.length}>
            {question}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function HomePage() {
  const { signIn, signUp } = useAuth();
  // Marketing surface: arrivals here are prospective testers, so it opens on
  // signup. The card still offers sign in for anyone who already has an account.
  const { authOpen, authMode, openAuth, closeAuth } = useAuthGate("signup");

  return (
    <>
      <div className={`${styles.marketingSurface} overflow-x-clip`}>
        <nav className={styles.nav} aria-label="Primary navigation">
          <Link href="/" className={styles.wordmark}>New Wine</Link>
          <ul className={styles.navLinks}>
            {([['About', '#'], ['Features', '#'], ...(isFullNavEnabled() ? [['Study', '/study']] : [])] as [string, string][]).map(([label, href]) => (
              <li key={label}><Link href={href}>{label}</Link></li>
            ))}
          </ul>
          <Button className={styles.navAction} size="sm" onClick={() => openAuth()}>Become a test user</Button>
        </nav>

        <NewWineDawnHero onPrimaryAction={() => openAuth()} />
        <QuestionRail />

        <section className={`${styles.section} ${styles.centeredSection}`}>
          <div className={styles.narrowContainer}>
            <SectionLabel>Why It Matters</SectionLabel>
            <h2>When you ask general AI about God, who&rsquo;s actually answering?</h2>
            <div className={styles.comparisonGrid}>
              <article className={styles.comparisonGroup}>
                <p className={styles.groupLabel}>General AI models</p>
                <h3>Everything at once. No one in particular.</h3>
                <ul>
                  <li>Averages every tradition, blog, and contradicting opinion into one flattened answer.</li>
                  <li>No source is trusted over another.</li>
                  <li>Applies its own content filters to theology — softening or avoiding positions it&rsquo;s trained to treat as sensitive.</li>
                  <li>No name stands behind the answer.</li>
                </ul>
              </article>
              <article className={styles.comparisonGroup}>
                <p className={styles.groupLabel}>New Wine</p>
                <h3>A known, trusted lineage.</h3>
                <ul>
                  <li>Drawn only from vetted sources within the charismatic tradition.</li>
                  <li>No hidden filters — your convictions aren&rsquo;t treated as something to soften.</li>
                  <li>Every answer points back to the voices behind it.</li>
                  <li>You always know whose shoulders an answer stands on.</li>
                </ul>
              </article>
            </div>
            <blockquote>&ldquo;You wouldn&rsquo;t take spiritual counsel from a stranger with no name.&rdquo;</blockquote>
            <p className={styles.centeredBody}>In matters of faith, <em>who</em> is speaking matters. New Wine is built on voices you&rsquo;d actually choose.</p>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.featureGrid}>
            <div>
              <SectionLabel>Ask Anything</SectionLabel>
              <h2>Ask about the baptism of the Holy Spirit. Get an answer — not a survey.</h2>
              <p>Ask general AI and you get &ldquo;some Christians believe&hellip; others hold&hellip;&rdquo; — every tradition averaged into one careful, beige paragraph. New Wine answers only from vetted sources across the Spirit-filled tradition, so your question gets an answer with conviction behind it.</p>
              <p>That includes historic voices like <strong>Derek Prince</strong>, <strong>Andrew Murray</strong>, and <strong>Bob Mumford</strong>, alongside teachers like <strong>Jack Deere</strong> and <strong>Dr. Michael Brown</strong>.</p>
              <p>And New Wine doesn&rsquo;t present AI-generated wording as a teacher&rsquo;s exact words.</p>
              <p>Every answer points back to the voices behind it, with the link to the full teaching right there.</p>
            </div>
            <ProductImagePlaceholder className={styles.productFrame} />
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.featureGrid}>
            <div>
              <SectionLabel>Study</SectionLabel>
              <h2>AI should send you deeper — not do the thinking for you.</h2>
              <p>There&rsquo;s something irreplaceable about wrestling with Scripture yourself. Study exists to protect that. It&rsquo;s the companion to the chat — built so you grow in the Word, not grow dependent on a tool.</p>
              <p>Open any verse for the full Greek and Hebrew interlinear, tap any word for its Strong&rsquo;s number and definition, and read commentary spanning the whole history of the church.</p>
              <p>And a human layer is coming. <strong>Vetted pastors and leaders will contribute devotional notes attached to the verse in front of you</strong> — real shepherds, present inside the study experience. Every note bylined, none of it AI-generated, and the bar for who contributes stays high.</p>
              {isFullNavEnabled() && <Link href="/study" className={styles.textLink}>Explore Study →</Link>}
            </div>
            <ProductImagePlaceholder className={styles.productFrame} />
          </div>
        </section>

        <section className={`${styles.section} ${styles.centeredSection}`}>
          <div className={styles.wideContainer}>
            <SectionLabel>The Library Behind It</SectionLabel>
            <h2>Every answer stands on named shoulders.</h2>
            <p className={styles.intro}>Built from a curated library of sermon transcripts, word studies, books, and commentaries — every one from a named, vetted voice in the charismatic and Spirit-filled tradition. If it&rsquo;s in the corpus, someone real stands behind it.</p>
            <div className={styles.statsGrid}>
              {[
                { num: "2,600+", label: "Source Documents" },
                { num: "1,700+", label: "Word Studies" },
                { num: "186", label: "Commentaries" },
                { num: "Growing", label: "Week by week" },
              ].map(({ num, label }) => (
                <div key={label} className={styles.stat}><strong>{num}</strong><span>{label}</span></div>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.section}>
          <div className={styles.wideContainer}>
            <h2>Explore more in New Wine</h2>
            <div className={styles.exploreGrid}>
              {EXPLORE_CARDS.map(({ marker, title, body }) => (
                <article key={title} className={styles.exploreGroup}>
                  <span className={styles.marker}>{marker}</span>
                  <h3>{title}</h3>
                  <p>{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={`${styles.section} ${styles.finalCta}`}>
          <h2>Help us build it. Become a test user.</h2>
          <p>New Wine is in active beta. Jump in free, explore everything, and help shape where it goes — no card required.</p>
          <div className={styles.finalActions}>
            <Button className={styles.primaryAction} size="lg" onClick={() => openAuth()}>Become a test user</Button>
            <Button className={styles.secondaryAction} variant="outline" size="lg" asChild><Link href="/sources">Explore the sources</Link></Button>
          </div>
        </section>

        <footer className={styles.footer}>
          <div className={styles.footerTop}>
            <div><div className={styles.footerBrand}>New Wine</div><p>Spirit-led Bible study for the charismatic tradition. Scholarly but accessible. Conviction, not performance.</p></div>
            <div className={styles.footerColumns}>
              <div><h4>Product</h4><ul><li><Link href="/">Chat</Link><small>Study tools built into every conversation</small></li><li><span>Pastors&rsquo; Notes</span><small>A small, growing collection</small></li><li><span>Discover · Coming soon</span></li></ul></div>
              <div><h4>Company</h4><ul>{["About", "Contact", "Privacy Policy", "Terms of Service"].map((label) => <li key={label}><Link href="/">{label}</Link></li>)}</ul></div>
            </div>
          </div>
          <div className={styles.footerBottom}><div><FooterNav /><p>© 2026 New Wine. All rights reserved.</p></div><p>οἶνον νέον εἰς ἀσκοὺς καινοὺς — Luke 5:38</p></div>
        </footer>
      </div>

      {authOpen && (
        <LoginModal onClose={closeAuth} onSignIn={signIn} onSignUp={signUp} initialMode={authMode} />
      )}
    </>
  );
}
