"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { getDocumentForEdit, updateDocument } from "@/lib/api";

const ADMIN_ID = "1ea99425-08ec-40f2-9ed3-588b88122a82";

type SaveState = "idle" | "saving" | "success" | "error";

export default function AdminEditPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user, accessToken } = useAuth();

  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");

  // Track original values for dirty detection
  const origTitle = useRef("");
  const origAuthor = useRef("");
  const origContent = useRef("");

  const isDirty = title !== origTitle.current || author !== origAuthor.current || content !== origContent.current;

  // Load document
  useEffect(() => {
    if (!accessToken || !id) return;
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
  }, [accessToken, id]);

  // Warn on unsaved changes
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (isDirty) {
        e.preventDefault();
      }
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

  // Gate: not admin
  if (user && user.id !== ADMIN_ID) {
    return <div className="flex h-screen items-center justify-center bg-background"><p className="text-muted-foreground">Access denied</p></div>;
  }

  // Gate: loading auth
  if (!user) {
    return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>;
  }

  if (loading) {
    return <div className="flex h-screen items-center justify-center bg-background"><Loader2 className="h-6 w-6 text-gold animate-spin" /></div>;
  }

  const isSaving = saveState === "saving";

  return (
    <div className="flex h-screen bg-background">
      {/* Left pane — editor */}
      <div className="flex flex-col w-1/2 h-full" style={{ borderRight: "1px solid #3c3c38" }}>
        <div className="flex flex-col flex-1 overflow-hidden px-5 pt-5 pb-4 gap-3">
          {/* Back link */}
          <button
            onClick={() => router.push("/library")}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-gold transition-colors min-h-[36px] self-start"
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
            className="font-serif text-2xl font-semibold w-full focus:outline-none"
            style={{ backgroundColor: "#262624", border: "1px solid #3c3c38", borderRadius: "8px", padding: "10px 14px", color: "#e6e6e0" }}
          />

          {/* Author */}
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            disabled={isSaving}
            placeholder="Author"
            className="text-base w-full focus:outline-none"
            style={{ backgroundColor: "#262624", border: "1px solid #3c3c38", borderRadius: "8px", padding: "10px 14px", color: "#e6e6e0" }}
          />

          {/* Content textarea */}
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            disabled={isSaving}
            className="flex-1 w-full focus:outline-none resize-none"
            style={{ backgroundColor: "#1a1917", border: "1px solid #3c3c38", borderRadius: "8px", padding: "16px", color: "#c1c1b8", fontFamily: "monospace", fontSize: "14px", lineHeight: 1.7 }}
          />

          {/* Save row */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="flex-1 text-white font-medium transition-colors disabled:opacity-60"
              style={{ backgroundColor: "#b49238", borderRadius: "8px", padding: "12px", fontSize: "16px" }}
            >
              {saveState === "idle" && "Save & Re-index"}
              {saveState === "saving" && "Saving... (generating embeddings)"}
              {saveState === "success" && "Saved \u2713"}
              {saveState === "error" && "Save failed \u2014 try again"}
            </button>
            {isDirty && saveState !== "saving" && (
              <span style={{ fontSize: "12px", color: "#888880", whiteSpace: "nowrap" }}>Unsaved changes</span>
            )}
          </div>
          {isSaving && (
            <p style={{ fontSize: "12px", color: "#888880" }}>Re-indexing chunks, this may take a few seconds...</p>
          )}
        </div>
      </div>

      {/* Right pane — preview */}
      <div className="flex flex-col w-1/2 h-full overflow-y-auto px-6 pt-5 pb-16">
        <span style={{ fontSize: "11px", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.1em", color: "#666660", marginBottom: "16px" }}>
          Preview
        </span>
        <h1 className="font-serif text-2xl font-semibold leading-tight" style={{ color: "#e6e6e0" }}>
          {title || "Untitled"}
        </h1>
        {author && <p className="text-sm mt-2" style={{ color: "#888880" }}>{author}</p>}
        <div className="border-t my-6" style={{ borderColor: "#3c3c38" }} />
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
