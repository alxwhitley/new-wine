"use client";

import { useState } from "react";
import { ArrowLeft, Menu } from "lucide-react";
import Link from "next/link";
import Image from "next/image";
import { useAuth } from "@/hooks/useAuth";
import { useConversations } from "@/hooks/useConversations";
import { Sidebar } from "@/components/newwine/sidebar";
import LoginModal from "@/components/auth/LoginModal";
import { useAuthGate } from "@/hooks/useAuthGate";
import { cn } from "@/lib/utils";

const AUTHOR_IMAGES: Record<string, string> = {
  "Ern Baxter": "/images/authors/ern-baxter.webp",
  "Jack Deere": "/images/authors/jack-deere.jpeg",
  "Michael Brown": "/images/authors/michael-brown.jpeg",
  "Oswald J. Smith": "/images/authors/oswald-smith.jpeg",
};

const CLASSIC_AUTHORS = new Set(["Derek Prince", "Bob Mumford", "Ern Baxter", "Charles Simpson", "Don Basham", "Oswald J. Smith"]);

function getInitials(name: string) {
  return name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

const AUTHORS = [
  { name: "Derek Prince", years: "1915–2003", bio: "Cambridge-educated philosopher turned Bible teacher, Prince founded Derek Prince Ministries after a wartime conversion and became one of the most widely translated charismatic teachers of the 20th century, known especially for his work on deliverance, healing, and the Holy Spirit." },
  { name: "Bob Mumford", years: "b. 1930", bio: "Bible teacher and co-founder of New Wine Magazine, Mumford is known for his Kingdom of God teaching and his role in the charismatic renewal, still living and ministering through Lifechangers." },
  { name: "Ern Baxter", years: "1914–1993", bio: "Canadian Pentecostal preacher regarded as one of the greatest orators of the 20th century, Baxter served as Bible teacher for William Branham's crusades and delivered his landmark \"Thy Kingdom Come\" message to 5,000 leaders in Kansas City." },
  { name: "Charles Simpson", years: "1937–2024", bio: "Baptist-turned-charismatic pastor from Mobile, Alabama who co-founded New Wine Magazine in 1969 and became a key leader in the charismatic renewal, known for his pastoral teaching on covenant community and spiritual authority." },
  { name: "Don Basham", years: "1926–1989", bio: "Bible teacher and author who pioneered deliverance ministry in the charismatic movement, Basham served as editor of New Wine Magazine from 1975–1981 and was known for his accessible writing on the Holy Spirit and spiritual warfare." },
  { name: "Michael Brown", years: "b. 1955", bio: "Scholar, apologist, and radio host with a PhD from NYU, Brown is a leading charismatic voice on the Jewish roots of Christianity, revival, and cultural apologetics, and has authored over 40 books." },
  { name: "Jack Deere", years: "b. 1948", bio: "Former Dallas Seminary professor of Old Testament who became a charismatic theologian after encountering the gifts through John Wimber; best known for Surprised by the Power of the Spirit, a landmark defense of continuationism." },
  { name: "Oswald J. Smith", years: "1889–1986", bio: "Canadian pastor, hymn writer, and missions statesman who founded The People's Church in Toronto; preached 12,000 sermons in 80 countries and was described by Billy Graham as \"the greatest missionary statesman of our time.\"" },
];

export default function AuthorsPage() {
  const { user, accessToken, signIn, signUp } = useAuth();
  // In-app surface: anyone already here has an account, so it opens on sign in.
  const { authOpen, authMode, authReason, openAuth, closeAuth } = useAuthGate("signin");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { conversations, deleteConversation } = useConversations(user?.id);
  const [failedImages, setFailedImages] = useState<Set<string>>(new Set());

  return (
    <div className="flex h-dvh-safe overflow-hidden bg-sidebar">
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
        onSignInClick={() => openAuth("signin")}
      />

      <main className="md:ml-64 flex flex-1 min-w-0 min-h-0 p-2 pb-24 md:pb-2">
        <div className="flex flex-col flex-1 min-h-0 bg-background rounded-xl border border-border overflow-hidden">
          <div className="flex h-14 shrink-0 items-center px-4 md:px-6 z-30 border-b border-border">
            <button aria-label="Open sidebar" onClick={() => setSidebarOpen(true)} className="md:hidden min-h-[44px] min-w-[44px] flex items-center justify-center rounded text-muted-foreground hover:text-foreground">
              <Menu className="h-5 w-5" />
            </button>
            <h1 className="md:hidden flex-1 text-center font-sans text-lg font-semibold text-foreground">New Wine</h1>
            <div className="md:hidden min-w-[44px]" />
          </div>

          <div className="flex-1 overflow-y-auto">
            <div className="mx-auto max-w-5xl px-4 md:px-6 pt-8 pb-16">
              <Link
                href="/library"
                className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-8 min-h-[44px]"
              >
                <ArrowLeft className="h-4 w-4" />
                Back to Library
              </Link>

              <h2 className="font-sans text-2xl md:text-3xl font-semibold text-foreground mb-8 text-balance">
                Authors
              </h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
                {AUTHORS.map((author) => {
                  const imgSrc = AUTHOR_IMAGES[author.name];
                  const isClassic = CLASSIC_AUTHORS.has(author.name);
                  return (
                    <div
                      key={author.name}
                      className="flex flex-row bg-card border border-border rounded-xl p-5 gap-3.5 transition-colors hover:bg-accent"
                    >
                      {imgSrc && !failedImages.has(author.name) ? (
                        <Image
                          src={imgSrc}
                          alt={author.name}
                          width={64}
                          height={64}
                          className={cn("rounded-full object-cover shrink-0 w-16 h-16 ring-1 ring-white/8", isClassic && "grayscale")}
                          onError={() => setFailedImages((prev) => new Set(prev).add(author.name))}
                        />
                      ) : (
                        <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center shrink-0 ring-1 ring-white/8">
                          <span className="text-lg font-semibold text-muted-foreground">{getInitials(author.name)}</span>
                        </div>
                      )}
                      <div className="flex flex-col min-w-0">
                        <h4 className="font-sans text-[17px] font-semibold text-foreground leading-snug">{author.name}</h4>
                        <p className="text-[11px] text-muted-foreground mt-1">{author.years}</p>
                        <div className="border-t border-border my-3" />
                        <p className="line-clamp-4 text-[13px] text-muted-foreground leading-relaxed">{author.bio}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </main>

      {authOpen && (
        <LoginModal onClose={closeAuth} onSignIn={signIn} onSignUp={signUp} reason={authReason} initialMode={authMode} />
      )}
    </div>
  );
}
