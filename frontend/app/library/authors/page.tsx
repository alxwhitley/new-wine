"use client";

import { useState } from "react";
import { ArrowLeft, Menu } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/rhemata/sidebar";
import LoginModal from "@/components/auth/LoginModal";

const AUTHOR_IMAGES: Record<string, string> = {
  "Ern Baxter": "/images/authors/ern-baxter.webp",
  "Jack Deere": "/images/authors/jack-deere.jpeg",
  "John Bevere": "/images/authors/john-bevere.webp",
  "Michael Brown": "/images/authors/michael-brown.jpeg",
  "Oswald J. Smith": "/images/authors/oswald-smith.jpeg",
};

const CLASSIC_AUTHORS = new Set(["Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson", "Don Basham", "Oswald J. Smith"]);

function getInitials(name: string) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

const AUTHORS = [
  { name: "Derek Prince", years: "1915\u20132003", bio: "Cambridge-educated philosopher turned Bible teacher, Prince founded Derek Prince Ministries after a wartime conversion and became one of the most widely translated charismatic teachers of the 20th century, known especially for his work on deliverance, healing, and the Holy Spirit." },
  { name: "Bob Mumford", years: "b. 1930", bio: "Bible teacher and co-founder of New Wine Magazine, Mumford is known for his Kingdom of God teaching and his role in the charismatic renewal, still living and ministering through Lifechangers." },
  { name: "Ern Baxter", years: "1914\u20131993", bio: "Canadian Pentecostal preacher regarded as one of the greatest orators of the 20th century, Baxter served as Bible teacher for William Branham\u2019s crusades and delivered his landmark \u201cThy Kingdom Come\u201d message to 5,000 leaders in Kansas City." },
  { name: "Charles Simpson", years: "1937\u20132024", bio: "Baptist-turned-charismatic pastor from Mobile, Alabama who co-founded New Wine Magazine in 1969 and became a key leader in the charismatic renewal, known for his pastoral teaching on covenant community and spiritual authority." },
  { name: "Don Basham", years: "1926\u20131989", bio: "Bible teacher and author who pioneered deliverance ministry in the charismatic movement, Basham served as editor of New Wine Magazine from 1975\u20131981 and was known for his accessible writing on the Holy Spirit and spiritual warfare." },
  { name: "John Bevere", years: "b. 1959", bio: "Co-founder of Messenger International and bestselling author of The Bait of Satan and The Awe of God, Bevere is known globally for his bold teachings on the fear of the Lord, spiritual authority, and uncompromising discipleship." },
  { name: "Michael Brown", years: "b. 1955", bio: "Scholar, apologist, and radio host with a PhD from NYU, Brown is a leading charismatic voice on the Jewish roots of Christianity, revival, and cultural apologetics, and has authored over 40 books." },
  { name: "Jack Deere", years: "b. 1948", bio: "Former Dallas Seminary professor of Old Testament who became a charismatic theologian after encountering the gifts through John Wimber; best known for Surprised by the Power of the Spirit, a landmark defense of continuationism." },
  { name: "Oswald J. Smith", years: "1889\u20131986", bio: "Canadian pastor, hymn writer, and missions statesman who founded The People\u2019s Church in Toronto; preached 12,000 sermons in 80 countries and was described by Billy Graham as \u201cthe greatest missionary statesman of our time.\u201d" },
];

export default function AuthorsPage() {
  const { user, accessToken, signIn, signUp, signOut } = useAuth();
  const [showLogin, setShowLogin] = useState(false);
  const [loginReason, setLoginReason] = useState<string | undefined>();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { conversations, deleteConversation } = useConversations(user?.id);
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set());

  return (
    <div className="flex h-screen bg-background">
      <Sidebar
        conversations={conversations}
        activeConversationId={null}
        isLoggedIn={!!user}
        user={user}
        accessToken={accessToken}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNewChat={() => { window.location.href = "/"; }}
        onSelectConversation={(id) => { window.location.href = `/?c=${id}`; }}
        onDeleteConversation={deleteConversation}
        onSignInClick={() => { setLoginReason(undefined); setShowLogin(true); }}
        onSignOut={signOut}
      />

      <main className="md:ml-64 flex flex-1 flex-col min-w-0 h-screen">
        <div className="flex h-14 shrink-0 items-center border-b border-border px-4 md:px-6 z-30">
          <button onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
            <Menu className="h-5 w-5" />
          </button>
          <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">Rhemata</h1>
          <div className="md:hidden min-w-[44px]" />
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-5xl px-4 md:px-6 pt-8 pb-16">
            <Link
              href="/library"
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-gold transition-colors mb-8 min-h-[44px]"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Library
            </Link>

            <h2 className="font-sans text-2xl md:text-3xl font-semibold text-foreground mb-8">
              Authors
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3" style={{ gap: "14px" }}>
              {AUTHORS.map((author) => {
                const imgSrc = AUTHOR_IMAGES[author.name];
                const isClassic = CLASSIC_AUTHORS.has(author.name);
                return (
                  <div
                    key={author.name}
                    className="flex flex-row"
                    style={{ backgroundColor: "#262624", border: "1px solid #3c3c38", borderRadius: "14px", padding: "20px", gap: "14px", transition: "background 0.2s ease" }}
                    onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "#2e2d2b"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "#262624"; }}
                  >
                    {imgSrc && !failedImages.has(author.name) ? (
                      <Image
                        src={imgSrc}
                        alt={author.name}
                        width={64}
                        height={64}
                        className="rounded-full object-cover flex-shrink-0"
                        style={{ width: "64px", height: "64px", boxShadow: "0 0 0 1px rgba(255,255,255,0.08)", filter: isClassic ? "grayscale(100%)" : "none" }}
                        onError={() => setFailedImages((prev) => new Set(prev).add(author.name))}
                      />
                    ) : (
                      <div
                        style={{ width: "64px", height: "64px", borderRadius: "50%", backgroundColor: "#2a2926", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, boxShadow: "0 0 0 1px rgba(255,255,255,0.08)" }}
                      >
                        <span style={{ fontSize: "18px", fontWeight: 600, color: "#888880" }}>{getInitials(author.name)}</span>
                      </div>
                    )}
                    <div className="flex flex-col min-w-0">
                      <h4 className="font-sans" style={{ fontSize: "17px", fontWeight: 600, color: "#e6e6e0", lineHeight: 1.45 }}>{author.name}</h4>
                      <p style={{ fontSize: "11px", color: "#888880", marginTop: "4px" }}>{author.years}</p>
                      <div style={{ borderTop: "1px solid #3c3c38", margin: "12px 0" }} />
                      <p className="line-clamp-4" style={{ fontSize: "13px", color: "#c1c1b8", lineHeight: 1.6 }}>{author.bio}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </main>

      {showLogin && (
        <LoginModal onClose={() => { setShowLogin(false); setLoginReason(undefined); }} onSignIn={signIn} onSignUp={signUp} reason={loginReason} />
      )}
    </div>
  );
}
