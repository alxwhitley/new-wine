"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { getDocumentForEdit, updateDocument } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL;

type SaveState = "idle" | "saving" | "success" | "error";

export default function AdminEditPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user, accessToken, loading: authLoading } = useAuth();
  const [roleChecked, setRoleChecked] = useState(false);

  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");

  const origTitle = useRef("");
  const origAuthor = useRef("");
  const origContent = useRef("");

  const isDirty =
    title !== origTitle.current ||
    author !== origAuthor.current ||
    content !== origContent.current;

  // Role gate
  useEffect(() => {
    if (authLoading || roleChecked) return;
    if (!user || !accessToken) { router.replace("/"); return; }
    fetch(`${API}/pastors-notes/me`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.json())
      .then((data) => { if (data.role === "admin") setRoleChecked(true); else router.replace("/"); })
      .catch(() => router.replace("/"));
  }, [authLoading, user, accessToken, router, roleChecked]);

  // Load document
  useEffect(() => {
    if (!accessToken || !id || !roleChecked) return;
    setLoading(true);
    getDocumentForEdit(id, accessToken)
      .then((doc) => {
        setTitle(doc.title || "");
        setAuthor(doc.author || "");
        setContent(doc.content || "");
        origTitle.current = doc.title || "";
        origAuthor.current = doc.author || "";
        origContent.current = doc.content || "";
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [accessToken, id, roleChecked]);

  // Warn on unsaved changes
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (isDirty) e.preventDefault();
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty]);

  const handleSave = useCallback(async () => {
    if (!accessToken || !id) return;
    setSaveState("saving");
    try {
      await updateDocument(id, { title, author, content }, accessToken);
      origTitle.current = title;
      origAuthor.current = author;
      origContent.current = content;
      setSaveState("success");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("error");
    }
  }, [accessToken, id, title, author, content]);

  if (authLoading || !roleChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isSaving = saveState === "saving";

  return (
    <div className="flex h-screen bg-background">
      {/* Left pane — editor */}
      <div className="flex flex-col w-1/2 h-full border-r border-border">
        <div className="flex flex-col flex-1 overflow-hidden px-5 pt-5 pb-4 gap-3">
          {/* Back link */}
          <button
            onClick={() => router.push("/library")}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors min-h-[44px] self-start"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Library
          </button>

          {/* Title */}
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={isSaving}
            placeholder="Title"
            className="font-sans text-2xl font-semibold w-full bg-card border border-border rounded-lg px-3.5 py-2.5 text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors disabled:opacity-60"
          />

          {/* Author */}
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            disabled={isSaving}
            placeholder="Author"
            className="text-base w-full bg-card border border-border rounded-lg px-3.5 py-2.5 text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors disabled:opacity-60"
          />

          {/* Content textarea */}
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={isSaving}
            className="flex-1 w-full bg-background border border-border rounded-lg p-4 text-muted-foreground font-mono text-sm leading-[1.7] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors resize-none disabled:opacity-60"
          />

          {/* Save row */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex-1 bg-primary text-primary-foreground font-medium rounded-lg py-3 text-base transition-colors hover:opacity-90 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {saveState === "idle" && "Save & Re-index"}
              {saveState === "saving" && "Saving…"}
              {saveState === "success" && "Saved ✓"}
              {saveState === "error" && "Save failed — try again"}
            </button>
            {isDirty && !isSaving && (
              <span className="text-xs text-muted-foreground whitespace-nowrap">Unsaved changes</span>
            )}
          </div>
          {isSaving && (
            <p className="text-xs text-muted-foreground">Re-indexing chunks, this may take a few seconds…</p>
          )}
        </div>
      </div>

      {/* Right pane — preview */}
      <div className="flex flex-col w-1/2 h-full overflow-y-auto px-6 pt-5 pb-16">
        <p className="text-xs text-muted-foreground mb-4">Preview</p>
        <h1 className="font-sans text-2xl font-semibold leading-tight text-foreground text-balance">
          {title || "Untitled"}
        </h1>
        {author && <p className="text-sm text-muted-foreground mt-2">{author}</p>}
        <div className="border-t border-border my-6" />
        <div className="prose prose-invert">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
