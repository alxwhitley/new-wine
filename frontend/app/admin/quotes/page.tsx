"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ArrowLeft } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

const API = process.env.NEXT_PUBLIC_API_URL;

type Teacher = { source_id: string; name: string };
type DocumentRow = { id: string; title: string; source_kind: string; cleared: boolean };
type Passage = { id: string; chunk_index: number; content: string; quote_ineligible_reason: string | null };
type CreatedQuote = {
  id: string;
  quote_text: string;
  topic: string;
  teacher_source_id: string;
  status: string;
  resolved?: { quote_text: string; teacher_name: string; topic: string } | null;
};

export default function QuoteReviewPage() {
  const router = useRouter();
  const { user, accessToken, loading: authLoading } = useAuth();
  const [roleChecked, setRoleChecked] = useState(false);

  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [teacherId, setTeacherId] = useState<string>("");
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [documentId, setDocumentId] = useState<string>("");
  const [passages, setPassages] = useState<Passage[]>([]);
  const [loadingPassages, setLoadingPassages] = useState(false);

  const [selection, setSelection] = useState<{ chunkId: string; text: string } | null>(null);
  const [attributedTeacherId, setAttributedTeacherId] = useState<string>("");
  const [topic, setTopic] = useState("");
  const [note, setNote] = useState("");
  const [clearanceNote, setClearanceNote] = useState("");
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "error">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [createdQuotes, setCreatedQuotes] = useState<CreatedQuote[]>([]);

  const passageRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Role gate — same admin check used by the /admin/edit page.
  useEffect(() => {
    if (authLoading || roleChecked) return;
    if (!user || !accessToken) { router.replace("/"); return; }
    fetch(`${API}/pastors-notes/me`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.json())
      .then((data) => { if (data.role === "admin") setRoleChecked(true); else router.replace("/"); })
      .catch(() => router.replace("/"));
  }, [authLoading, user, accessToken, router, roleChecked]);

  // Load confirmed teachers
  useEffect(() => {
    if (!accessToken || !roleChecked) return;
    fetch(`${API}/quotes/teachers`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.json())
      .then((data: Teacher[]) => {
        setTeachers(data);
        if (data.length && !teacherId) setTeacherId(data[0].source_id);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, roleChecked]);

  // Load documents for selected teacher
  useEffect(() => {
    if (!accessToken || !teacherId) return;
    setDocumentId("");
    setPassages([]);
    fetch(`${API}/quotes/documents?teacher_source_id=${teacherId}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => r.json())
      .then((data: DocumentRow[]) => setDocuments(data));
  }, [accessToken, teacherId]);

  // Load passages for selected document
  useEffect(() => {
    if (!accessToken || !documentId) return;
    setLoadingPassages(true);
    setSelection(null);
    fetch(`${API}/quotes/documents/${documentId}/passages`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => r.json())
      .then((data: Passage[]) => setPassages(data))
      .finally(() => setLoadingPassages(false));
  }, [accessToken, documentId]);

  useEffect(() => {
    if (teacherId) setAttributedTeacherId(teacherId);
  }, [teacherId]);

  const currentDocument = documents.find((d) => d.id === documentId);

  const handleMouseUp = useCallback((chunkId: string) => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.toString().trim()) return;
    const container = passageRefs.current[chunkId];
    if (!container) return;
    // Selection must be fully contained within this one passage block — a
    // quote must live entirely inside one retrievable unit (Step 2).
    if (!container.contains(sel.anchorNode) || !container.contains(sel.focusNode)) {
      return;
    }
    setSelection({ chunkId, text: sel.toString() });
  }, []);

  const handleClearSource = useCallback(async () => {
    if (!accessToken || !documentId || !clearanceNote.trim()) return;
    const res = await fetch(`${API}/quotes/documents/${documentId}/clear`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ note: clearanceNote }),
    });
    if (res.ok) {
      setDocuments((docs) => docs.map((d) => (d.id === documentId ? { ...d, cleared: true } : d)));
      setClearanceNote("");
    }
  }, [accessToken, documentId, clearanceNote]);

  const handleSubmit = useCallback(async () => {
    if (!accessToken || !selection || !attributedTeacherId || !topic.trim() || !note.trim()) return;
    setSubmitState("submitting");
    setSubmitError(null);
    try {
      const res = await fetch(`${API}/quotes`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({
          chunk_id: selection.chunkId,
          quote_text: selection.text,
          teacher_source_id: attributedTeacherId,
          topic,
          reviewer_note: note,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setSubmitState("error");
        setSubmitError(data.detail || "Verification failed — quote was not saved.");
        return;
      }
      // Prove Step 4 immediately: resolve the quote we just approved by ID.
      const resolveRes = await fetch(`${API}/quotes/${data.id}/resolve`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      const resolved = resolveRes.ok ? await resolveRes.json() : null;
      setCreatedQuotes((prev) => [{ ...data, resolved }, ...prev]);
      setSubmitState("idle");
      setSelection(null);
      setTopic("");
      setNote("");
    } catch (e) {
      setSubmitState("error");
      setSubmitError(String(e));
    }
  }, [accessToken, selection, attributedTeacherId, topic, note]);

  const handleRevoke = useCallback(async (quoteId: string) => {
    if (!accessToken) return;
    await fetch(`${API}/quotes/${quoteId}/revoke`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const resolveRes = await fetch(`${API}/quotes/${quoteId}/resolve`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const resolved = resolveRes.ok ? await resolveRes.json() : null; // expect null (404) after revoke
    setCreatedQuotes((prev) =>
      prev.map((q) => (q.id === quoteId ? { ...q, status: "revoked", resolved } : q))
    );
  }, [accessToken]);

  if (authLoading || !roleChecked) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-screen bg-background px-6 py-6 gap-6 max-w-5xl mx-auto">
      <button
        onClick={() => router.push("/")}
        className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors self-start"
      >
        <ArrowLeft className="h-4 w-4" />
        Home
      </button>

      <h1 className="text-2xl font-semibold text-foreground">Quote review</h1>
      <p className="text-sm text-muted-foreground -mt-4">
        Manual curation only. Nothing here is AI-suggested or AI-approved — every quote is your
        own selection, and a failed check blocks saving rather than warning.
      </p>

      {/* Teacher + document pickers */}
      <div className="flex gap-4">
        <select
          data-testid="teacher-select"
          value={teacherId}
          onChange={(e) => setTeacherId(e.target.value)}
          className="bg-card border border-border rounded-lg px-3 py-2 text-foreground"
        >
          {teachers.map((t) => (
            <option key={t.source_id} value={t.source_id}>{t.name}</option>
          ))}
        </select>
        <select
          data-testid="document-select"
          value={documentId}
          onChange={(e) => setDocumentId(e.target.value)}
          className="bg-card border border-border rounded-lg px-3 py-2 text-foreground flex-1"
        >
          <option value="">Select a document…</option>
          {documents.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title} {d.cleared ? "— cleared" : "— not cleared"}
            </option>
          ))}
        </select>
      </div>

      {currentDocument && !currentDocument.cleared && (
        <div className="border border-border rounded-lg p-4 bg-card flex flex-col gap-2">
          <p className="text-sm text-foreground">
            This document has not been cleared for quoting yet. Say why it's safe to source quotes
            from before selecting any text.
          </p>
          <textarea
            data-testid="clearance-note"
            value={clearanceNote}
            onChange={(e) => setClearanceNote(e.target.value)}
            placeholder="Why this source is clear to use…"
            className="bg-background border border-border rounded-lg p-2 text-sm text-foreground"
            rows={2}
          />
          <button
            data-testid="clear-source-button"
            onClick={handleClearSource}
            disabled={!clearanceNote.trim()}
            className="self-start bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm disabled:opacity-50"
          >
            Clear this source
          </button>
        </div>
      )}

      {loadingPassages && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}

      {/* Passages */}
      {currentDocument?.cleared && (
        <div className="flex flex-col gap-3">
          {passages.map((p) => {
            const ineligible = !!p.quote_ineligible_reason;
            return (
              <div
                key={p.id}
                data-testid="passage"
                data-chunk-index={p.chunk_index}
                data-eligible={!ineligible}
                ref={(el) => { passageRefs.current[p.id] = el; }}
                onMouseUp={() => !ineligible && handleMouseUp(p.id)}
                className={`whitespace-pre-wrap text-sm leading-relaxed p-3 rounded-lg border ${
                  ineligible
                    ? "bg-muted/40 border-border text-muted-foreground opacity-60 select-none"
                    : "bg-card border-border text-foreground cursor-text"
                }`}
              >
                {ineligible && (
                  <p className="text-xs font-medium mb-1 text-destructive">
                    Excluded — {p.quote_ineligible_reason} (never sourced)
                  </p>
                )}
                {p.content}
              </div>
            );
          })}
        </div>
      )}

      {/* Selection form */}
      {selection && (
        <div className="border border-border rounded-lg p-4 bg-card flex flex-col gap-3">
          <div>
            <p className="text-xs text-muted-foreground mb-1">Selected quote</p>
            <p className="text-sm text-foreground italic">&ldquo;{selection.text}&rdquo;</p>
          </div>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-xs text-muted-foreground">Attributed teacher</label>
              <select
                value={attributedTeacherId}
                onChange={(e) => setAttributedTeacherId(e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground"
              >
                {teachers.map((t) => (
                  <option key={t.source_id} value={t.source_id}>{t.name}</option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="text-xs text-muted-foreground">Point / topic it supports</label>
              <input
                data-testid="topic-input"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground"
                placeholder="e.g. surrender, prayer, holiness…"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Why it's clear to use</label>
            <textarea
              data-testid="reviewer-note-input"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground"
            />
          </div>
          <button
            data-testid="approve-button"
            onClick={handleSubmit}
            disabled={submitState === "submitting" || !topic.trim() || !note.trim()}
            className="self-start bg-primary text-primary-foreground rounded-lg px-4 py-2 text-sm disabled:opacity-50"
          >
            {submitState === "submitting" ? "Verifying…" : "Approve quote"}
          </button>
          {submitState === "error" && (
            <p className="text-sm text-destructive">Blocked, not saved: {submitError}</p>
          )}
        </div>
      )}

      {/* Created quotes this session */}
      {createdQuotes.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-foreground">Approved this session</h2>
          {createdQuotes.map((q) => (
            <div key={q.id} data-testid="created-quote" data-quote-id={q.id} data-status={q.status} className="border border-border rounded-lg p-3 bg-card text-sm">
              <p className="text-foreground italic">&ldquo;{q.quote_text}&rdquo;</p>
              <p className="text-xs text-muted-foreground mt-1">
                Topic: {q.topic} — status: {q.status}
              </p>
              <p data-testid="resolved-result" className="text-xs mt-1">
                Resolved by ID: {q.resolved ? (
                  <span className="text-foreground">
                    &ldquo;{q.resolved.quote_text.slice(0, 60)}…&rdquo; — {q.resolved.teacher_name}
                  </span>
                ) : (
                  <span className="text-muted-foreground">nothing (not approved / revoked)</span>
                )}
              </p>
              {q.status === "approved" && (
                <button
                  data-testid="revoke-button"
                  onClick={() => handleRevoke(q.id)}
                  className="text-xs text-destructive underline mt-1"
                >
                  Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
