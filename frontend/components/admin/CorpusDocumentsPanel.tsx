"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Search,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Eye,
  Trash2,
  Copy,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";

const API = process.env.NEXT_PUBLIC_API_URL;
const PAGE_SIZE = 50;

// ── Types ─────────────────────────────────────────────────────────────────────

interface CorpusDoc {
  id: string;
  title: string | null;
  original_title: string | null;
  author: string | null;
  source_kind: string | null;
  source_name: string | null;
  license_status: string | null;
  visibility: string | null;
  url: string | null;
  created_at: string | null;
}

interface ArticleView {
  title: string;
  author: string | null;
  content: string;
  url: string | null;
}

export interface CorpusLicenseSource {
  id: string;
  name: string;
}

interface CorpusDocumentsPanelProps {
  accessToken: string | null;
  licenseSources: CorpusLicenseSource[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function licenseClass(status: string | null) {
  if (status === "public_domain" || status === "owned")
    return "text-primary border-primary/40 bg-primary/10";
  if (status === "unlicensed")
    return "text-destructive border-destructive/40 bg-destructive/10";
  return "text-muted-foreground border-border bg-muted/40";
}

function licenseShort(status: string | null) {
  if (status === "public_domain") return "PD";
  if (status === "owned") return "owned";
  if (status === "licensed") return "lic.";
  if (status === "unlicensed") return "unlic.";
  return status ?? "—";
}

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ── DocRow ────────────────────────────────────────────────────────────────────

function DocRow({
  doc,
  onView,
  onRemove,
}: {
  doc: CorpusDoc;
  onView: () => void;
  onRemove: () => void;
}) {
  const titleDiffers =
    doc.original_title &&
    doc.title !== doc.original_title;

  return (
    <div className="group grid grid-cols-[1fr_6.5rem_5rem_3.5rem_5.5rem_4.5rem] gap-x-3 px-4 py-3 items-start hover:bg-accent/40 transition-colors">
      {/* Title / URL / original title */}
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground truncate leading-snug">
          {doc.title ?? "—"}
        </p>
        {doc.url && (
          <a
            href={doc.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-0.5 text-xs text-primary/80 hover:text-primary truncate max-w-full"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="truncate">{doc.url}</span>
            <ExternalLink className="h-2.5 w-2.5 shrink-0" />
          </a>
        )}
        {titleDiffers && (
          <p className="text-xs text-muted-foreground italic truncate">
            YT: {doc.original_title}
          </p>
        )}
        {doc.author && (
          <p className="text-xs text-muted-foreground truncate">{doc.author}</p>
        )}
      </div>

      {/* Type badge */}
      <div className="pt-0.5">
        <span className="inline-block text-[10px] rounded-full border border-border bg-muted/40 px-2 py-0.5 truncate max-w-full leading-tight">
          {doc.source_kind ?? "—"}
        </span>
      </div>

      {/* Source */}
      <p className="text-xs text-muted-foreground truncate pt-0.5">
        {doc.source_name ?? "—"}
      </p>

      {/* License */}
      <div className="pt-0.5">
        {doc.license_status && (
          <span
            className={cn(
              "text-[10px] rounded-full border px-2 py-0.5 leading-tight inline-block",
              licenseClass(doc.license_status)
            )}
          >
            {licenseShort(doc.license_status)}
          </span>
        )}
      </div>

      {/* Ingested date */}
      <p className="text-xs text-muted-foreground pt-0.5">{fmtDate(doc.created_at)}</p>

      {/* Hover actions */}
      <div className="flex items-center justify-end gap-1 pt-0.5">
        <button
          className="h-6 w-6 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-accent text-muted-foreground hover:text-foreground"
          onClick={onView}
          title="View article"
        >
          <Eye className="h-3.5 w-3.5" />
        </button>
        <button
          className="h-6 w-6 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
          onClick={onRemove}
          title="Remove document"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

// ── CopyButton ────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}
      className="shrink-0 h-5 w-5 flex items-center justify-center rounded text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
      title="Copy"
    >
      {copied ? <Check className="h-3 w-3 text-primary" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

// ── CorpusDocumentsPanel ──────────────────────────────────────────────────────

export function CorpusDocumentsPanel({
  accessToken,
  licenseSources,
}: CorpusDocumentsPanelProps) {
  const [docs, setDocs] = useState<CorpusDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [kindCounts, setKindCounts] = useState<Record<string, number>>({});
  const [totalAll, setTotalAll] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Filters
  const [filterKind, setFilterKind] = useState("");
  const [filterSourceId, setFilterSourceId] = useState("");
  const [filterLicense, setFilterLicense] = useState("");
  const [filterVisibility, setFilterVisibility] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");

  // Pagination
  const [page, setPage] = useState(0);

  // View sheet
  const [viewDocId, setViewDocId] = useState<string | null>(null);
  const [viewArticle, setViewArticle] = useState<ArticleView | null>(null);
  const [viewLoading, setViewLoading] = useState(false);

  // Remove dialog
  const [removeTarget, setRemoveTarget] = useState<CorpusDoc | null>(null);
  const [removeLoading, setRemoveLoading] = useState(false);
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());

  // ── Fetch ────────────────────────────────────────────────────────────────────

  const fetchDocs = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(false);
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      });
      if (filterKind) params.set("source_kind", filterKind);
      if (filterSourceId) params.set("source_id", filterSourceId);
      if (filterLicense) params.set("license_status", filterLicense);
      if (filterVisibility) params.set("visibility", filterVisibility);
      if (search) params.set("search", search);

      const res = await fetch(`${API}/admin/corpus/documents?${params}`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setDocs(data.rows ?? []);
      setTotal(data.total ?? 0);
      setKindCounts(data.kind_counts ?? {});
      setTotalAll(data.total_all ?? 0);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [accessToken, page, filterKind, filterSourceId, filterLicense, filterVisibility, search]);

  useEffect(() => { fetchDocs(); }, [fetchDocs]);

  // Reset page on filter change
  useEffect(() => { setPage(0); }, [filterKind, filterSourceId, filterLicense, filterVisibility, search]);

  // Debounce search input → search
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput), 400);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Load article for View sheet
  useEffect(() => {
    if (!viewDocId || !accessToken) return;
    setViewLoading(true);
    setViewArticle(null);
    fetch(`${API}/document/${viewDocId}/article`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) =>
        setViewArticle({
          title: data.title ?? "",
          author: data.author ?? null,
          content: data.content ?? "",
          url: data.url ?? null,
        })
      )
      .catch(() =>
        setViewArticle({
          title: "Error",
          author: null,
          content: "Failed to load article content.",
          url: null,
        })
      )
      .finally(() => setViewLoading(false));
  }, [viewDocId, accessToken]);

  // ── Handlers ─────────────────────────────────────────────────────────────────

  async function handleRemove() {
    if (!removeTarget || !accessToken) return;
    setRemoveLoading(true);
    try {
      const res = await fetch(`${API}/admin/document/${removeTarget.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok) {
        setRemovedIds((prev) => new Set(prev).add(removeTarget.id));
        setRemoveTarget(null);
        fetchDocs();
      }
    } finally {
      setRemoveLoading(false);
    }
  }

  function clearFilters() {
    setFilterKind("");
    setFilterSourceId("");
    setFilterLicense("");
    setFilterVisibility("");
    setSearch("");
    setSearchInput("");
  }

  const hasFilters = filterKind || filterSourceId || filterLicense || filterVisibility || search;
  const totalPages = Math.ceil(total / PAGE_SIZE);
  const visibleDocs = docs.filter((d) => !removedIds.has(d.id));

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Stats row */}
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 mb-4 px-3 py-2.5 rounded-lg bg-card border border-border text-xs">
        <span className="font-semibold text-foreground">
          {totalAll.toLocaleString()} total
        </span>
        {Object.entries(kindCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([kind, count]) => (
            <span key={kind} className="text-muted-foreground">
              <span className="font-medium text-foreground">{count.toLocaleString()}</span>{" "}
              {kind}
            </span>
          ))}
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap gap-2 mb-4">
        <select
          value={filterKind}
          onChange={(e) => setFilterKind(e.target.value)}
          className="h-8 rounded border border-input bg-background px-2 text-xs text-foreground"
        >
          <option value="">All types</option>
          {Object.keys(kindCounts)
            .sort()
            .map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
        </select>

        <select
          value={filterSourceId}
          onChange={(e) => setFilterSourceId(e.target.value)}
          className="h-8 rounded border border-input bg-background px-2 text-xs text-foreground max-w-[180px]"
        >
          <option value="">All sources</option>
          {licenseSources.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>

        <select
          value={filterLicense}
          onChange={(e) => setFilterLicense(e.target.value)}
          className="h-8 rounded border border-input bg-background px-2 text-xs text-foreground"
        >
          <option value="">Any license</option>
          <option value="public_domain">public_domain</option>
          <option value="owned">owned</option>
          <option value="licensed">licensed</option>
          <option value="unlicensed">unlicensed</option>
        </select>

        <select
          value={filterVisibility}
          onChange={(e) => setFilterVisibility(e.target.value)}
          className="h-8 rounded border border-input bg-background px-2 text-xs text-foreground"
        >
          <option value="">Any visibility</option>
          <option value="shown">shown</option>
          <option value="hidden">hidden</option>
        </select>

        <div className="relative flex-1 min-w-[160px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search title / author…"
            className="h-8 w-full rounded border border-input bg-background pl-7 pr-2 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {hasFilters && (
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={clearFilters}>
            Clear
          </Button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 mb-4">
          <p className="text-sm text-destructive">
            Failed to load documents. Check backend connection.
          </p>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : visibleDocs.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-6 text-center">
          <p className="text-sm text-muted-foreground">No documents found.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          {/* Column headers */}
          <div className="grid grid-cols-[1fr_6.5rem_5rem_3.5rem_5.5rem_4.5rem] gap-x-3 px-4 py-2 border-b border-border bg-muted/40">
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Title / URL
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Type
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Source
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Lic.
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Ingested
            </span>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground text-right">
              Actions
            </span>
          </div>

          <div className="divide-y divide-border">
            {visibleDocs.map((doc) => (
              <DocRow
                key={doc.id}
                doc={doc}
                onView={() => setViewDocId(doc.id)}
                onRemove={() => setRemoveTarget(doc)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-xs text-muted-foreground">
          <span>{total.toLocaleString()} results</span>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-7"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <span>
              Page {page + 1} of {totalPages}
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* View Sheet */}
      <Sheet
        open={!!viewDocId}
        onOpenChange={(open) => {
          if (!open) {
            setViewDocId(null);
            setViewArticle(null);
          }
        }}
      >
        <SheetContent side="right" className="w-full sm:max-w-2xl flex flex-col">
          <SheetHeader>
            <SheetTitle className="truncate pr-8">
              {viewArticle?.title ?? "Loading…"}
            </SheetTitle>
            {viewArticle?.author && (
              <SheetDescription>{viewArticle.author}</SheetDescription>
            )}
          </SheetHeader>

          <div className="flex-1 overflow-y-auto px-1 pb-4">
            {viewLoading ? (
              <div className="space-y-3 pt-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : (
              <>
                {viewArticle?.url && (
                  <a
                    href={viewArticle.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-primary hover:underline mb-4 mt-1 block break-all"
                  >
                    {viewArticle.url}
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                )}
                <div className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
                  {viewArticle?.content}
                </div>
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>

      {/* Remove AlertDialog */}
      <AlertDialog
        open={!!removeTarget}
        onOpenChange={(open) => {
          if (!open) setRemoveTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Remove &ldquo;{removeTarget?.title ?? "this document"}&rdquo;?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {removeTarget?.url
                ? "This deletes the document, all chunks and propositions, and prevents re-ingest of this video URL. "
                : "This deletes the document and all chunks and propositions. "}
              This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={removeLoading}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRemove}
              disabled={removeLoading}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {removeLoading ? "Removing…" : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export { CopyButton };
