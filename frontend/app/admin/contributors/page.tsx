"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";

const API = process.env.NEXT_PUBLIC_API_URL;

interface PendingRequest {
  id: string;
  user_id: string;
  email: string;
  message: string | null;
  created_at: string;
}

interface Contributor {
  user_id: string;
  display_name: string | null;
  email: string;
  card_count: number;
  created_at: string;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function ContributorsPage() {
  const { user, accessToken, loading: authLoading } = useAuth();
  const router = useRouter();
  const [roleChecked, setRoleChecked] = useState(false);

  const [requests, setRequests] = useState<PendingRequest[]>([]);
  const [contributors, setContributors] = useState<Contributor[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(true);
  const [contributorsLoading, setContributorsLoading] = useState(true);

  const [toast, setToast] = useState<string | null>(null);
  const [actionIds, setActionIds] = useState<Set<string>>(new Set());

  const [revokeTarget, setRevokeTarget] = useState<Contributor | null>(null);
  const [revokeRemoveCards, setRevokeRemoveCards] = useState(false);
  const [revokeLoading, setRevokeLoading] = useState(false);

  // Role gate: check /me and redirect if not admin
  useEffect(() => {
    if (authLoading || roleChecked) return;
    if (!user || !accessToken) {
      router.replace("/");
      return;
    }
    fetch(`${API}/pastors-notes/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.role === "admin") {
          setRoleChecked(true);
        } else {
          router.replace("/");
        }
      })
      .catch(() => router.replace("/"));
  }, [authLoading, user, accessToken, router, roleChecked]);

  // Fetch data once role is confirmed
  useEffect(() => {
    if (!roleChecked || !accessToken) return;
    const headers = { Authorization: `Bearer ${accessToken}` };

    fetch(`${API}/pastors-notes/requests`, { headers })
      .then((r) => r.json())
      .then((data) => setRequests(Array.isArray(data) ? data : []))
      .catch(() => setRequests([]))
      .finally(() => setRequestsLoading(false));

    fetch(`${API}/pastors-notes/contributors`, { headers })
      .then((r) => r.json())
      .then((data) => setContributors(Array.isArray(data) ? data : []))
      .catch(() => setContributors([]))
      .finally(() => setContributorsLoading(false));
  }, [roleChecked, accessToken]);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  const handleApprove = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setActionIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/pastors-notes/requests/${id}/approve`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setRequests((prev) => prev.filter((r) => r.id !== id));
          showToast("Application approved.");
        }
      } finally {
        setActionIds((prev) => {
          const s = new Set(prev);
          s.delete(id);
          return s;
        });
      }
    },
    [accessToken]
  );

  const handleReject = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setActionIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/pastors-notes/requests/${id}/reject`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setRequests((prev) => prev.filter((r) => r.id !== id));
          showToast("Application rejected.");
        }
      } finally {
        setActionIds((prev) => {
          const s = new Set(prev);
          s.delete(id);
          return s;
        });
      }
    },
    [accessToken]
  );

  async function handleRevokeConfirm() {
    if (!revokeTarget || !accessToken) return;
    setRevokeLoading(true);
    try {
      const res = await fetch(
        `${API}/pastors-notes/contributors/${revokeTarget.user_id}/revoke`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ remove_cards: revokeRemoveCards }),
        }
      );
      if (res.ok) {
        setContributors((prev) =>
          prev.filter((c) => c.user_id !== revokeTarget.user_id)
        );
        showToast(
          `${revokeTarget.display_name ?? "Contributor"}'s access has been revoked.`
        );
        setRevokeTarget(null);
        setRevokeRemoveCards(false);
      }
    } finally {
      setRevokeLoading(false);
    }
  }

  if (authLoading || !roleChecked) {
    return (
      <div className="min-h-screen bg-sidebar flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-sidebar">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Link
          href="/admin"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Back to Admin
        </Link>

        <h1 className="mt-6 mb-8 text-2xl font-semibold text-foreground">
          Contributors
        </h1>

        <div className="space-y-6">
          {/* 1. Pending Applications */}
          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Pending Applications
              </CardTitle>
            </CardHeader>
            <CardContent>
              {requestsLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : requests.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No pending applications.
                </p>
              ) : (
                <div className="space-y-3">
                  {requests.map((req) => (
                    <div
                      key={req.id}
                      className="flex items-start justify-between gap-4 rounded-lg border border-border p-4"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {req.email || "—"}
                        </p>
                        {req.message && (
                          <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                            {req.message}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">
                          {fmtDate(req.created_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Button
                          size="sm"
                          onClick={() => handleApprove(req.id)}
                          disabled={actionIds.has(req.id)}
                        >
                          {actionIds.has(req.id) ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            "Approve"
                          )}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleReject(req.id)}
                          disabled={actionIds.has(req.id)}
                        >
                          Reject
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 2. Active Contributors */}
          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Active Contributors
              </CardTitle>
            </CardHeader>
            <CardContent>
              {contributorsLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : contributors.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No active contributors.
                </p>
              ) : (
                <div className="space-y-3">
                  {contributors.map((c) => (
                    <div
                      key={c.user_id}
                      className="flex items-center justify-between gap-4 rounded-lg border border-border p-4"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground">
                          {c.display_name ? (
                            c.display_name
                          ) : (
                            <span className="italic text-muted-foreground">
                              No display name
                            </span>
                          )}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">
                          {c.email || "—"}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {c.card_count} published note
                          {c.card_count !== 1 ? "s" : ""} · granted{" "}
                          {fmtDate(c.created_at)}
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setRevokeTarget(c);
                          setRevokeRemoveCards(false);
                        }}
                      >
                        Revoke access
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 3. Flagged Notes (stub) */}
          <Card>
            <CardHeader>
              <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Flagged Notes
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Card flagging coming soon.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-lg">
          {toast}
        </div>
      )}

      {/* Revoke confirmation sheet */}
      <Sheet
        open={!!revokeTarget}
        onOpenChange={(open) => {
          if (!open) setRevokeTarget(null);
        }}
      >
        <SheetContent side="right" className="flex flex-col">
          <SheetHeader>
            <SheetTitle>
              Revoke {revokeTarget?.display_name ?? "contributor"}&apos;s
              access?
            </SheetTitle>
            <SheetDescription>
              They will lose contributor access immediately.
            </SheetDescription>
          </SheetHeader>

          <div className="flex-1 px-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={revokeRemoveCards}
                onChange={(e) => setRevokeRemoveCards(e.target.checked)}
                className="h-4 w-4 rounded border-input accent-primary"
              />
              <span className="text-sm text-foreground">
                Also remove all their notes
              </span>
            </label>
          </div>

          <SheetFooter>
            <Button
              onClick={handleRevokeConfirm}
              disabled={revokeLoading}
              className="w-full"
            >
              {revokeLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Confirm revoke"
              )}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    </div>
  );
}
