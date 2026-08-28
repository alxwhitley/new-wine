"use client";

import { useState, useEffect } from "react";
import { Pencil, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";

const API = process.env.NEXT_PUBLIC_API_URL;

interface PastorCard {
  id: string;
  verse_id: string;
  user_id: string;
  display_name: string | null;
  content: string;
  topic_tags: string[];
  created_at: string;
  updated_at: string;
  status: string;
}

function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  const wks = Math.floor(days / 7);
  if (wks < 5) return `${wks}w ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface Props {
  verseId: string | null;
  accessToken: string | null;
  role: string | null;
  userId: string | null;
}

export function PastorsNotesSection({ verseId, accessToken, role, userId }: Props) {
  const canAdd = role === "contributor" || role === "admin";
  const isAdmin = role === "admin";

  const [cards, setCards] = useState<PastorCard[]>([]);
  const [cardsLoading, setCardsLoading] = useState(false);
  const [cardsError, setCardsError] = useState(false);

  // Add note form
  const [addOpen, setAddOpen] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Inline edit
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete confirm
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  // Fetch cards on verse change
  useEffect(() => {
    if (!verseId) {
      setCards([]);
      setCardsError(false);
      return;
    }
    setCardsLoading(true);
    setCardsError(false);
    setAddOpen(false);
    setNewContent("");
    setAddError(null);
    setEditingId(null);
    setConfirmDeleteId(null);

    const headers: HeadersInit = accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
    fetch(`${API}/pastors-notes/cards?verse_id=${encodeURIComponent(verseId)}`, { headers })
      .then((r) => {
        if (!r.ok) throw new Error("pastors-notes fetch failed");
        return r.json();
      })
      .then((data) => setCards(Array.isArray(data) ? data : []))
      .catch(() => {
        setCards([]);
        setCardsError(true);
      })
      .finally(() => setCardsLoading(false));
  }, [verseId, accessToken]);

  async function handleAddNote() {
    if (!accessToken || !verseId) return;
    const trimmed = newContent.trim();
    if (trimmed.length < 50) {
      setAddError("Notes must be at least 50 characters.");
      return;
    }
    setAddLoading(true);
    setAddError(null);
    try {
      const res = await fetch(`${API}/pastors-notes/cards`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ verse_id: verseId, content: trimmed }),
      });
      if (res.ok) {
        const card = await res.json();
        setCards((prev) => [card, ...prev]);
        setNewContent("");
        setAddOpen(false);
      } else {
        const data = await res.json().catch(() => ({}));
        setAddError(data.detail ?? "Failed to publish note.");
      }
    } catch {
      setAddError("Something went wrong.");
    } finally {
      setAddLoading(false);
    }
  }

  function startEdit(card: PastorCard) {
    setEditingId(card.id);
    setEditContent(card.content);
    setEditError(null);
    setConfirmDeleteId(null);
  }

  async function handleSaveEdit() {
    if (!accessToken || !editingId) return;
    setEditLoading(true);
    setEditError(null);
    try {
      const res = await fetch(`${API}/pastors-notes/cards/${editingId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ content: editContent.trim() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setCards((prev) =>
          prev.map((c) => (c.id === editingId ? { ...c, ...updated } : c))
        );
        setEditingId(null);
      } else {
        const data = await res.json().catch(() => ({}));
        setEditError(data.detail ?? "Failed to save changes.");
      }
    } catch {
      setEditError("Something went wrong.");
    } finally {
      setEditLoading(false);
    }
  }

  async function handleDelete(cardId: string) {
    if (!accessToken) return;
    setDeleteLoading(true);
    try {
      const res = await fetch(`${API}/pastors-notes/cards/${cardId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        setCards((prev) => prev.filter((c) => c.id !== cardId));
        setConfirmDeleteId(null);
      }
    } finally {
      setDeleteLoading(false);
    }
  }

  return (
    <section id="section-pastors" className="pt-10">
      <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground mb-4">
        Pastors&apos; Notes
      </h2>

      {/* Add note button + inline form */}
      {canAdd && verseId && (
        <div className="mb-4">
          {!addOpen ? (
            <button
              onClick={() => { setAddOpen(true); setAddError(null); }}
              className="text-sm text-primary hover:underline underline-offset-4"
            >
              + Add note
            </button>
          ) : (
            <div className="rounded-lg border border-border bg-card p-4 space-y-3">
              <Textarea
                placeholder="Share an insight on this verse..."
                value={newContent}
                onChange={(e) => { setNewContent(e.target.value); setAddError(null); }}
                rows={4}
                maxLength={2000}
                className="resize-none"
              />
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  {newContent.length} / 2000
                </span>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => { setAddOpen(false); setNewContent(""); setAddError(null); }}
                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    Cancel
                  </button>
                  <Button
                    size="sm"
                    onClick={handleAddNote}
                    disabled={addLoading}
                  >
                    {addLoading ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      "Publish note"
                    )}
                  </Button>
                </div>
              </div>
              {addError && (
                <p className="text-xs text-destructive">{addError}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Card list */}
      {cardsLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-24 w-full rounded-lg" />
        </div>
      ) : cardsError ? (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-sm text-destructive">
            Couldn&apos;t load notes — try again.
          </p>
        </div>
      ) : cards.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-sm text-muted-foreground">
            Notes from pastors and ministry leaders will appear here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {cards.map((card) => {
            const isOwn = card.user_id === userId;
            const canEdit = (role === "contributor" && isOwn) || isAdmin;
            const isEditing = editingId === card.id;
            const isConfirmDelete = confirmDeleteId === card.id;

            return (
              <div
                key={card.id}
                className="rounded-lg border border-border bg-card p-4"
              >
                {isEditing ? (
                  <div className="space-y-3">
                    <Textarea
                      value={editContent}
                      onChange={(e) => { setEditContent(e.target.value); setEditError(null); }}
                      rows={4}
                      maxLength={2000}
                      className="resize-none"
                    />
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm"
                        onClick={handleSaveEdit}
                        disabled={editLoading}
                      >
                        {editLoading ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          "Save"
                        )}
                      </Button>
                      <button
                        onClick={() => { setEditingId(null); setEditError(null); }}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                    {editError && (
                      <p className="text-xs text-destructive">{editError}</p>
                    )}
                  </div>
                ) : (
                  <>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="text-sm font-medium text-foreground">
                          {card.display_name ?? "Anonymous"}
                        </p>
                        {card.status === "pending" && (
                          <span className="mt-1 inline-block text-[11px] rounded border border-border px-1.5 py-0.5 text-muted-foreground">
                            Pending review
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {canEdit && !isConfirmDelete && (
                          <button
                            onClick={() => startEdit(card)}
                            className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
                            aria-label="Edit note"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                        )}
                        {isAdmin && !isConfirmDelete && (
                          <button
                            onClick={() => {
                              setConfirmDeleteId(card.id);
                              setEditingId(null);
                            }}
                            className="rounded p-1 text-muted-foreground hover:text-destructive transition-colors"
                            aria-label="Delete note"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-sm text-foreground leading-relaxed">
                      {card.content}
                    </p>
                    <p className="text-xs text-muted-foreground mt-2">
                      {relativeTime(card.updated_at)}
                    </p>

                    {isConfirmDelete && (
                      <div className="mt-3 rounded-lg border border-border bg-background p-3">
                        <p className="text-sm text-foreground mb-2">
                          Remove this note?
                        </p>
                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => handleDelete(card.id)}
                            disabled={deleteLoading}
                          >
                            {deleteLoading ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              "Confirm"
                            )}
                          </Button>
                          <button
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
