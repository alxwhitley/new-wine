"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL;

type SourceFormat = "web_page" | "pdf";
type SourceScope = "single" | "collection";
type AttributionMode = "declared" | "per_item";
type QueueStatus = "waiting" | "running" | "done" | "failed" | "needs_attention";

interface QueueRow {
  id: string;
  url: string;
  source_format: SourceFormat;
  source_scope: SourceScope;
  attribute_to: string | null;
  attribution_mode: AttributionMode;
  status: QueueStatus;
  flag_reason: string | null;
  cleared_to_run: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface SourceQueuePanelProps {
  accessToken: string | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function isValidUrl(raw: string): boolean {
  try {
    const u = new URL(raw.trim());
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function statusBadgeClass(status: QueueStatus): string {
  switch (status) {
    case "done":
      return "border-primary/40 bg-primary/10 text-primary";
    case "running":
      return "border-ring/40 bg-ring/10 text-foreground";
    case "failed":
      return "border-destructive/40 bg-destructive/10 text-destructive";
    case "needs_attention":
      return "border-destructive/40 bg-destructive/10 text-destructive";
    default:
      return "border-border bg-muted/40 text-muted-foreground";
  }
}

function shortUrl(url: string): string {
  try {
    const u = new URL(url);
    return u.hostname.replace(/^www\./, "") + u.pathname;
  } catch {
    return url;
  }
}

// ── Segmented two-option toggle (Button variants, no new styling) ────────────

function SegmentedToggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-2">
      {options.map((opt) => (
        <Button
          key={opt.value}
          type="button"
          variant={value === opt.value ? "default" : "outline"}
          size="sm"
          className="flex-1"
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}

// ── SourceQueuePanel ───────────────────────────────────────────────────────────

export function SourceQueuePanel({ accessToken }: SourceQueuePanelProps) {
  // ── Form state ─────────────────────────────────────────────────
  const [url, setUrl] = useState("");
  const [sourceFormat, setSourceFormat] = useState<SourceFormat>("web_page");
  const [sourceScope, setSourceScope] = useState<SourceScope>("single");
  const [creditTo, setCreditTo] = useState("");
  const [findPerItem, setFindPerItem] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);

  // ── List state ─────────────────────────────────────────────────
  const [needsAttention, setNeedsAttention] = useState<QueueRow[]>([]);
  const [queue, setQueue] = useState<QueueRow[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [actionIds, setActionIds] = useState<Set<string>>(new Set());
  const [assignDrafts, setAssignDrafts] = useState<Record<string, string>>({});

  // ── Derived validation ─────────────────────────────────────────
  const urlEmpty = url.trim().length === 0;
  const urlMalformed = !urlEmpty && !isValidUrl(url);
  const needsAttribution = !findPerItem && creditTo.trim().length === 0;
  const canSubmit = !urlEmpty && !urlMalformed && !needsAttribution && submitStatus !== "loading";

  // ── Data fetch ─────────────────────────────────────────────────
  const fetchList = useCallback(async () => {
    if (!accessToken) return;
    setListLoading(true);
    try {
      const res = await fetch(`${API}/ingest-queue`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error(`list ${res.status}`);
      const data = await res.json();
      setNeedsAttention(data.needs_attention ?? []);
      setQueue(data.queue ?? []);
      setListError(false);
    } catch (err) {
      console.warn("[source-queue] fetchList failed:", err);
      setListError(true);
    } finally {
      setListLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  // ── Domain memory prefill on URL blur ───────────────────────────
  async function handleUrlBlur() {
    if (!accessToken || urlEmpty || urlMalformed) return;
    try {
      const res = await fetch(`${API}/ingest-queue/domain-memory?url=${encodeURIComponent(url.trim())}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.found) {
        setFindPerItem(data.attribution_mode === "per_item");
        setCreditTo(data.attribute_to ?? "");
      }
    } catch {
      // Prefill is a convenience, not a requirement -- fail silently.
    }
  }

  // ── Submit ───────────────────────────────────────────────────────
  async function handleSubmit() {
    setTouched(true);
    if (!canSubmit || !accessToken) return;
    setSubmitStatus("loading");
    setSubmitError(null);
    try {
      const res = await fetch(`${API}/ingest-queue`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          url: url.trim(),
          source_format: sourceFormat,
          source_scope: sourceScope,
          attribute_to: findPerItem ? null : creditTo.trim(),
          attribution_mode: findPerItem ? "per_item" : "declared",
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `submit failed (${res.status})`);
      }
      setSubmitStatus("success");
      setUrl("");
      setSourceFormat("web_page");
      setSourceScope("single");
      setCreditTo("");
      setFindPerItem(false);
      setTouched(false);
      fetchList();
      setTimeout(() => setSubmitStatus("idle"), 2500);
    } catch (err) {
      setSubmitStatus("error");
      setSubmitError(err instanceof Error ? err.message : "Something went wrong.");
    }
  }

  // ── Row actions ────────────────────────────────────────────────
  async function handleAssign(row: QueueRow) {
    const name = (assignDrafts[row.id] ?? "").trim();
    if (!name || !accessToken) return;
    setActionIds((prev) => new Set(prev).add(row.id));
    try {
      const res = await fetch(`${API}/ingest-queue/${row.id}/assign`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ attribute_to: name }),
      });
      if (res.ok) {
        setAssignDrafts((prev) => { const n = { ...prev }; delete n[row.id]; return n; });
        fetchList();
      }
    } finally {
      setActionIds((prev) => { const s = new Set(prev); s.delete(row.id); return s; });
    }
  }

  async function handleDrop(row: QueueRow) {
    if (!accessToken) return;
    setActionIds((prev) => new Set(prev).add(row.id));
    try {
      const res = await fetch(`${API}/ingest-queue/${row.id}/drop`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({}),
      });
      if (res.ok) fetchList();
    } finally {
      setActionIds((prev) => { const s = new Set(prev); s.delete(row.id); return s; });
    }
  }

  async function handleToggleClearedToRun(row: QueueRow) {
    if (!accessToken) return;
    const next = !row.cleared_to_run;
    setQueue((prev) => prev.map((r) => (r.id === row.id ? { ...r, cleared_to_run: next } : r)));
    try {
      const res = await fetch(`${API}/ingest-queue/${row.id}/cleared-to-run`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${accessToken}` },
        body: JSON.stringify({ cleared_to_run: next }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setQueue((prev) => prev.map((r) => (r.id === row.id ? { ...r, cleared_to_run: row.cleared_to_run } : r)));
    }
  }

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div role="tabpanel">
      <h2 className="text-xl font-semibold text-foreground font-sans mb-6">Source Queue</h2>

      {/* ── Add form -- primary element, top of panel ────────────── */}
      <Card className="mb-8 border-primary/30">
        <CardHeader>
          <CardTitle className="text-base font-semibold text-foreground">Submit a source</CardTitle>
          <p className="text-sm text-muted-foreground">
            Nothing fetches on submit -- this only queues the URL for later ingestion.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Input
              autoFocus
              type="url"
              inputMode="url"
              autoCapitalize="none"
              autoCorrect="off"
              placeholder="Paste a URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={handleUrlBlur}
              className="text-base h-12"
            />
            {touched && urlEmpty && (
              <p className="text-xs text-destructive mt-1">A URL is required.</p>
            )}
            {touched && urlMalformed && (
              <p className="text-xs text-destructive mt-1">That doesn&apos;t look like a valid URL.</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
                Format
              </p>
              <SegmentedToggle
                options={[
                  { value: "web_page" as SourceFormat, label: "Web page" },
                  { value: "pdf" as SourceFormat, label: "PDF" },
                ]}
                value={sourceFormat}
                onChange={setSourceFormat}
              />
            </div>
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
                Scope
              </p>
              <SegmentedToggle
                options={[
                  { value: "single" as SourceScope, label: "Single" },
                  { value: "collection" as SourceScope, label: "Collection" },
                ]}
                value={sourceScope}
                onChange={setSourceScope}
              />
            </div>
          </div>

          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-1.5">
              Credit to
            </p>
            <div className="flex items-center gap-2 mb-2">
              <Switch
                checked={findPerItem}
                onCheckedChange={(checked) => {
                  setFindPerItem(checked);
                  if (checked) setCreditTo("");
                }}
              />
              <span className="text-sm text-foreground">Find per item</span>
            </div>
            <Input
              placeholder="Teacher name"
              value={creditTo}
              onChange={(e) => setCreditTo(e.target.value)}
              disabled={findPerItem}
              className="h-11"
            />
            {touched && needsAttribution && (
              <p className="text-xs text-destructive mt-1">
                Enter a name, or turn on &quot;Find per item&quot;.
              </p>
            )}
          </div>

          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="w-full h-11"
          >
            {submitStatus === "loading" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              "Submit"
            )}
          </Button>

          {submitStatus === "success" && (
            <p className="text-sm text-primary text-center">Queued.</p>
          )}
          {submitStatus === "error" && submitError && (
            <p className="text-sm text-destructive text-center">{submitError}</p>
          )}
        </CardContent>
      </Card>

      {listError && (
        <div className="mb-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm font-medium text-destructive">
            Couldn&apos;t load the queue -- check backend connection or auth.
          </p>
        </div>
      )}

      {/* ── Needs Attention ──────────────────────────────────────── */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Needs Attention
            {needsAttention.length > 0 && (
              <span className="ml-2 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-white">
                {needsAttention.length}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {listLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full" />
            </div>
          ) : needsAttention.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing needs attention.</p>
          ) : (
            <div className="space-y-3">
              {needsAttention.map((row) => (
                <div key={row.id} className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 space-y-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{shortUrl(row.url)}</p>
                    {row.flag_reason && (
                      <p className="text-xs text-destructive mt-1">{row.flag_reason}</p>
                    )}
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2">
                    <Input
                      placeholder="Assign a name"
                      value={assignDrafts[row.id] ?? ""}
                      onChange={(e) =>
                        setAssignDrafts((prev) => ({ ...prev, [row.id]: e.target.value }))
                      }
                      className="flex-1 h-10"
                    />
                    <div className="flex gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => handleAssign(row)}
                        disabled={actionIds.has(row.id) || !(assignDrafts[row.id] ?? "").trim()}
                      >
                        {actionIds.has(row.id) ? <Loader2 className="h-3 w-3 animate-spin" /> : "Assign"}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDrop(row)}
                        disabled={actionIds.has(row.id)}
                      >
                        Drop
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Queue ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Queue
          </CardTitle>
        </CardHeader>
        <CardContent>
          {listLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : queue.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sources queued yet.</p>
          ) : (
            <div className="space-y-3">
              {queue.map((row) => (
                <div
                  key={row.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border p-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      <p className="text-sm font-medium text-foreground truncate">{shortUrl(row.url)}</p>
                      <Badge variant="outline" className={cn("shrink-0", statusBadgeClass(row.status))}>
                        {row.status.replace("_", " ")}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      {row.source_format === "web_page" ? "Web page" : "PDF"} ·{" "}
                      {row.source_scope === "single" ? "Single" : "Collection"} ·{" "}
                      {row.attribution_mode === "per_item"
                        ? "find per item"
                        : row.attribute_to ?? "—"}{" "}
                      · {fmtDateTime(row.created_at)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs text-muted-foreground hidden sm:inline">Cleared</span>
                    <Switch
                      checked={row.cleared_to_run}
                      onCheckedChange={() => handleToggleClearedToRun(row)}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
