"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type React from "react";
import {
  Loader2,
  ChevronDown,
  ChevronUp,
  Lock,
  ThumbsUp,
  Users,
  Inbox,
  Database,
  Copy,
  Check,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useUserRole } from "@/hooks/useUserRole";
import { supabase } from "@/lib/supabase";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import CorpusCardComponent from "@/components/admin/corpus-card";
import CardModal from "@/components/admin/card-modal";
import { CARDS, GROUPS, FUTURE_TARGETS } from "@/components/admin/corpus-data";
import type { CorpusCard } from "@/components/admin/corpus-types";
import { CorpusDocumentsPanel, CopyButton } from "@/components/admin/CorpusDocumentsPanel";
import type { CorpusLicenseSource } from "@/components/admin/CorpusDocumentsPanel";

const API = process.env.NEXT_PUBLIC_API_URL;

const SENTINEL_SOURCE_ID = "267a09ac-76f3-43fb-901f-3015aef88e22";

// ── Types ──────────────────────────────────────────────────────────────────

interface LicenseSource {
  id: string;
  name: string;
  license_status: string;
  visibility: string;
  doc_count: number | null;
}

interface FeedbackEntry {
  id: string;
  question: string;
  rating: string;
  comment: string | null;
  created_at: string;
  user_id: string | null;
  anon_id: string | null;
  source_type: string | null;
  source_document_id: string | null;
}

type FeedbackTab = "chat_answer" | "commentary" | "word_study";

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

interface PendingNote {
  id: string;
  verse_id: string;
  content: string;
  topic_tags: string[];
  created_at: string;
  user_id: string;
  display_name: string | null;
  email: string;
}

interface CountData {
  [cardId: string]: { count: number; lastIngested: string | null };
}

interface GlobalStats {
  totalDocuments: number;
  totalChunks: number;
  totalVerses: number;
  totalInterlinearWords: number;
}

interface FilterCondition {
  col: string;
  val: string;
}

// ── Constants ──────────────────────────────────────────────────────────────

const FEEDBACK_TABS: { key: FeedbackTab; label: string }[] = [
  { key: "chat_answer", label: "Chat Answers" },
  { key: "commentary", label: "Commentary" },
  { key: "word_study", label: "Word Studies" },
];

type TopTab = "corpus" | "feedback" | "contributors" | "notes-queue";
type CorpusSubView = "documents" | "sources" | "pipelines";

type NavTab = {
  key: TopTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const NAV_TABS: NavTab[] = [
  { key: "corpus",       label: "Corpus",       icon: Database },
  { key: "feedback",     label: "Feedback",     icon: ThumbsUp },
  { key: "contributors", label: "Contributors", icon: Users    },
  { key: "notes-queue",  label: "Notes Queue",  icon: Inbox    },
];

// Pipeline command reference (Pipelines sub-view)
const PIPELINE_CMD_GROUPS = [
  {
    group: "YouTube",
    note: null as string | null,
    cmds: [
      { label: "Triage (2h)",  cmd: "python scripts/run_queue_triage.py --time-limit 120" },
      { label: "Triage (6h)",  cmd: "python scripts/run_queue_triage.py --time-limit 360" },
      { label: "Ingest (2h)",  cmd: "python scripts/run_queue_ingest.py --time-limit 120"  },
      { label: "Ingest (6h)",  cmd: "python scripts/run_queue_ingest.py --time-limit 360"  },
      { label: "Triage (dry)", cmd: "python scripts/run_queue_triage.py --dry-run"         },
      { label: "Ingest (dry)", cmd: "python scripts/run_queue_ingest.py --dry-run"          },
    ],
  },
  {
    group: "Magazine",
    note: "↓ manual: review extracted issues and move approved ones into sources/magazine/03_approved/ before Step 2",
    cmds: [
      { label: "Step 1 — Extract",      cmd: "python scripts/extract_magazine.py"                       },
      { label: "Step 1 — Extract (2h)", cmd: "python scripts/extract_magazine.py --time-limit 120"     },
      { label: "Step 1 — Extract (6h)", cmd: "python scripts/extract_magazine.py --time-limit 360"     },
      { label: "Step 2 — Ingest",       cmd: "python scripts/ingest_magazine.py"                       },
    ],
  },
  {
    group: "Documents",
    note: null as string | null,
    cmds: [
      { label: "Ingest",      cmd: "python scripts/ingest.py"            },
      { label: "Ingest (dry)", cmd: "python scripts/ingest.py --dry-run" },
    ],
  },
];

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatVerseId(verseId: string): string {
  const parts = verseId.split(".");
  if (parts.length !== 3) return verseId;
  return `${parts[0]} ${parts[1]}:${parts[2]}`;
}

function parseFilter(filter: string): { and: FilterCondition[]; or: FilterCondition[] } {
  const and: FilterCondition[] = [];
  const or: FilterCondition[] = [];
  const cleaned = filter.replace(/[()]/g, "");
  const andParts = cleaned.split(/\s+AND\s+/i);
  for (const part of andParts) {
    const orParts = part.split(/\s+OR\s+/i);
    if (orParts.length > 1) {
      for (const orPart of orParts) {
        const match = orPart.trim().match(/^(\w+)\s+ILIKE\s+'([^']+)'$/i);
        if (match) or.push({ col: match[1], val: match[2] });
      }
    } else {
      const match = part.trim().match(/^(\w+)\s+ILIKE\s+'([^']+)'$/i);
      if (match) and.push({ col: match[1], val: match[2] });
    }
  }
  return { and, or };
}

// ── Inline display components ──────────────────────────────────────────────

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline gap-1.5 px-3 py-1">
      <span className="text-lg font-bold text-primary">{value.toLocaleString()}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}

function FutureTargetCard({
  target,
}: {
  target: { id: string; name: string; description: string; urls: string[] };
}) {
  const [copiedUrl, setCopiedUrl] = useState<string | null>(null);

  const handleCopy = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedUrl(url);
    setTimeout(() => setCopiedUrl(null), 2000);
  };

  return (
    <div className="rounded-lg p-4 bg-card/60 border border-dashed border-border">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="font-sans font-medium text-base text-foreground">{target.name}</h3>
        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">
          Not Ingested
        </span>
      </div>
      <p className="text-xs mb-3 text-muted-foreground">{target.description}</p>
      <div className="space-y-1.5">
        {target.urls.map((url) => (
          <div key={url} className="flex items-start gap-2 rounded p-2 bg-muted border border-border">
            <code className="text-xs break-all flex-1 font-mono leading-relaxed text-primary">
              {url}
            </code>
            <button
              onClick={() => handleCopy(url)}
              className={`shrink-0 px-2 py-1 rounded text-xs font-medium transition-colors ${
                copiedUrl === url ? "bg-primary/25 text-primary" : "bg-background text-foreground"
              }`}
            >
              {copiedUrl === url ? "Copied!" : "Copy"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-3">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-lg border border-border bg-card p-4 animate-pulse"
        >
          <div className="space-y-2">
            <div className="h-3.5 rounded bg-border w-48" />
            <div className="h-3 rounded bg-border w-24" />
          </div>
          <div className="h-5 w-9 rounded-full bg-border" />
        </div>
      ))}
    </div>
  );
}

// ── AdminModal ─────────────────────────────────────────────────────────────

interface AdminModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AdminModal({ open, onOpenChange }: AdminModalProps) {
  const { accessToken, loading: authLoading } = useAuth();
  const { role: userRole } = useUserRole(accessToken ?? null);

  // Derived: true only while modal is open and admin role is confirmed
  const roleChecked = open && !authLoading && userRole === "admin";

  // Close if role resolves to non-admin
  useEffect(() => {
    if (!open || authLoading || userRole === null) return;
    if (userRole !== "admin") onOpenChange(false);
  }, [open, authLoading, userRole, onOpenChange]);

  // ── Navigation ─────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TopTab>("corpus");
  const [corpusSubView, setCorpusSubView] = useState<CorpusSubView>("documents");

  // ── Per-tab load flags ─────────────────────────────────────────
  const [contributorsLoaded, setContributorsLoaded] = useState(false);
  const [corpusLoaded, setCorpusLoaded] = useState(false);

  // ── Feedback ───────────────────────────────────────────────────
  const [feedbackEntries, setFeedbackEntries] = useState<FeedbackEntry[]>([]);
  const [feedbackLoading, setFeedbackLoading] = useState(true);
  const [feedbackTab, setFeedbackTab] = useState<FeedbackTab>("chat_answer");

  // ── Contributors ───────────────────────────────────────────────
  const [requests, setRequests] = useState<PendingRequest[]>([]);
  const [contributors, setContributors] = useState<Contributor[]>([]);
  const [requestsLoading, setRequestsLoading] = useState(true);
  const [contributorsLoading, setContributorsLoading] = useState(true);
  const [actionIds, setActionIds] = useState<Set<string>>(new Set());
  const [revokeTarget, setRevokeTarget] = useState<Contributor | null>(null);
  const [revokeRemoveCards, setRevokeRemoveCards] = useState(false);
  const [revokeLoading, setRevokeLoading] = useState(false);

  // ── Notes queue ────────────────────────────────────────────────
  const [pendingNotes, setPendingNotes] = useState<PendingNote[]>([]);
  const [pendingNotesLoading, setPendingNotesLoading] = useState(true);
  const [noteActionIds, setNoteActionIds] = useState<Set<string>>(new Set());

  // ── Corpus: Sources sub-view ───────────────────────────────────
  const [licenseSources, setLicenseSources] = useState<LicenseSource[]>([]);
  const [licenseSourcesLoading, setLicenseSourcesLoading] = useState(true);
  const [safeMode, setSafeMode] = useState<"on" | "off">("off");
  const [safeModeLoading, setSafeModeLoading] = useState(true);
  const [manageSrcTarget, setManageSrcTarget] = useState<LicenseSource | null>(null);

  // ── Corpus: Pipelines sub-view ─────────────────────────────────
  const [counts, setCounts] = useState<CountData>({});
  const [globalStats, setGlobalStats] = useState<GlobalStats>({
    totalDocuments: 0,
    totalChunks: 0,
    totalVerses: 0,
    totalInterlinearWords: 0,
  });
  const [realtimeConnected, setRealtimeConnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [selectedCard, setSelectedCard] = useState<CorpusCard | null>(null);
  const [pulsingCards, setPulsingCards] = useState<Set<string>>(new Set());
  const pulseTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const [maintenanceOpen, setMaintenanceOpen] = useState(false);
  const [futureTargetsOpen, setFutureTargetsOpen] = useState(false);

  // ── Shared ─────────────────────────────────────────────────────
  const [toast, setToast] = useState<string | null>(null);
  const [adminDataError, setAdminDataError] = useState(false);

  // ── Corpus counts ──────────────────────────────────────────────

  const fetchAllCounts = useCallback(async () => {
    const newCounts: CountData = {};

    const allDocs: Array<{ source_kind: string; source_type: string; created_at: string }> = [];
    let offset = 0;
    while (true) {
      const { data } = await supabase
        .from("documents")
        .select("source_kind, source_type, created_at")
        .range(offset, offset + 999);
      if (!data || data.length === 0) break;
      allDocs.push(
        ...(data as Array<{ source_kind: string; source_type: string; created_at: string }>)
      );
      if (data.length < 1000) break;
      offset += 1000;
    }

    const kindAgg: Record<string, { count: number; maxDate: string | null }> = {};
    const typeAgg: Record<string, { count: number; maxDate: string | null }> = {};
    for (const row of allDocs) {
      const sk = row.source_kind;
      if (!kindAgg[sk]) kindAgg[sk] = { count: 0, maxDate: null };
      kindAgg[sk].count++;
      if (row.created_at && (!kindAgg[sk].maxDate || row.created_at > kindAgg[sk].maxDate!)) {
        kindAgg[sk].maxDate = row.created_at;
      }
      const st = row.source_type;
      if (!typeAgg[st]) typeAgg[st] = { count: 0, maxDate: null };
      typeAgg[st].count++;
      if (row.created_at && (!typeAgg[st].maxDate || row.created_at > typeAgg[st].maxDate!)) {
        typeAgg[st].maxDate = row.created_at;
      }
    }

    const filterPromises: Promise<void>[] = [];

    for (const card of CARDS) {
      if (card.isMaintenance) continue;

      if (card.specialTable) {
        filterPromises.push(
          (async () => {
            let query = supabase.from(card.specialTable!).select("*", { count: "exact", head: true });
            if (card.specialWhere) {
              const [col, rest] = card.specialWhere.split("=");
              const [operator, value] = rest.split(".");
              if (operator === "eq") query = query.eq(col, value);
            }
            const { count } = await query;
            newCounts[card.id] = { count: count ?? 0, lastIngested: null };
          })()
        );
      } else if (card.countChunks && card.extraFilter) {
        filterPromises.push(
          (async () => {
            let docQuery = supabase.from("documents").select("id");
            if (card.sourceKind) docQuery = docQuery.eq("source_kind", card.sourceKind);
            const parsed = parseFilter(card.extraFilter!);
            for (const cond of parsed.and) docQuery = docQuery.ilike(cond.col, cond.val);
            if (parsed.or.length > 0) {
              docQuery = docQuery.or(parsed.or.map((c) => `${c.col}.ilike.${c.val}`).join(","));
            }
            const { data: docs } = await docQuery;
            if (docs && docs.length > 0) {
              const docIds = docs.map((d) => d.id as string);
              const { count } = await supabase
                .from("chunks")
                .select("*", { count: "exact", head: true })
                .in("document_id", docIds);
              newCounts[card.id] = { count: count ?? 0, lastIngested: null };
            } else {
              newCounts[card.id] = { count: 0, lastIngested: null };
            }
          })()
        );
      } else if (card.extraFilter || card.notFilter) {
        filterPromises.push(
          (async () => {
            let query = supabase.from("documents").select("created_at", { count: "exact" });
            if (card.sourceKind) query = query.eq("source_kind", card.sourceKind);
            if (card.extraFilter) {
              const parsed = parseFilter(card.extraFilter);
              for (const cond of parsed.and) query = query.ilike(cond.col, cond.val);
              if (parsed.or.length > 0) {
                query = query.or(parsed.or.map((c) => `${c.col}.ilike.${c.val}`).join(","));
              }
            }
            if (card.notFilter) {
              for (const nc of card.notFilter) {
                query = query.not(nc.col, "ilike", nc.val);
              }
            }
            const { data, count } = await query;
            let maxDate: string | null = null;
            if (data) {
              for (const row of data) {
                if (row.created_at && (!maxDate || row.created_at > maxDate)) {
                  maxDate = row.created_at as string;
                }
              }
            }
            newCounts[card.id] = { count: count ?? data?.length ?? 0, lastIngested: maxDate };
          })()
        );
      } else if (card.sourceType) {
        const agg = typeAgg[card.sourceType];
        newCounts[card.id] = { count: agg?.count ?? 0, lastIngested: agg?.maxDate ?? null };
      } else if (card.sourceKind) {
        const agg = kindAgg[card.sourceKind];
        newCounts[card.id] = { count: agg?.count ?? 0, lastIngested: agg?.maxDate ?? null };
      }
    }

    await Promise.all(filterPromises);
    setCounts(newCounts);
    setLastUpdated(new Date());
  }, []);

  // ── Data fetches ───────────────────────────────────────────────

  useEffect(() => {
    if (!roleChecked || !accessToken) return;
    fetch(`${API}/pastors-notes/pending`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => r.json())
      .then((data) => setPendingNotes(Array.isArray(data) ? data : []))
      .catch(() => setPendingNotes([]))
      .finally(() => setPendingNotesLoading(false));
  }, [roleChecked, accessToken]);

  useEffect(() => {
    if (!roleChecked || !accessToken || activeTab !== "feedback") return;
    setFeedbackLoading(true);
    const params = new URLSearchParams({ source_type: feedbackTab });
    fetch(`${API}/feedback?${params}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => setFeedbackEntries(data.feedback ?? []))
      .catch(() => setFeedbackEntries([]))
      .finally(() => setFeedbackLoading(false));
  }, [roleChecked, accessToken, activeTab, feedbackTab]);

  useEffect(() => {
    if (!roleChecked || !accessToken || activeTab !== "contributors" || contributorsLoaded) return;
    const headers = { Authorization: `Bearer ${accessToken}` };
    setContributorsLoaded(true);
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
  }, [roleChecked, accessToken, activeTab, contributorsLoaded]);

  useEffect(() => {
    if (!roleChecked || !accessToken || activeTab !== "corpus" || corpusLoaded) return;
    const headers = { Authorization: `Bearer ${accessToken}` };
    setCorpusLoaded(true);
    fetch(`${API}/admin/license-sources`, { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => setLicenseSources(data.sources ?? []))
      .catch(() => { setLicenseSources([]); setAdminDataError(true); })
      .finally(() => setLicenseSourcesLoading(false));
    fetch(`${API}/admin/safe-mode`, { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => setSafeMode(data.value === "on" ? "on" : "off"))
      .catch(() => setAdminDataError(true))
      .finally(() => setSafeModeLoading(false));
    fetch(`${API}/admin/stats`, { headers })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) =>
        setGlobalStats({
          totalDocuments: data.documents ?? 0,
          totalChunks: data.chunks ?? 0,
          totalVerses: data.verses ?? 0,
          totalInterlinearWords: data.interlinear_words ?? 0,
        })
      )
      .catch(() => setAdminDataError(true));
    fetchAllCounts();
  }, [roleChecked, accessToken, activeTab, corpusLoaded, fetchAllCounts]);

  // Realtime — active only while modal is open
  useEffect(() => {
    if (!roleChecked) return;
    const channel = supabase
      .channel("admin-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "documents" },
        (payload) => {
          const sourceKind = payload.new.source_kind as string;
          const sourceType = payload.new.source_type as string;
          for (const card of CARDS) {
            if (card.sourceKind === sourceKind || card.sourceType === sourceType) {
              triggerPulse(card.id);
            }
          }
          fetchAllCounts();
        }
      )
      .subscribe((status) => setRealtimeConnected(status === "SUBSCRIBED"));

    return () => { supabase.removeChannel(channel); };
  }, [roleChecked, fetchAllCounts]);

  // ── Action handlers ────────────────────────────────────────────

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  function triggerPulse(cardId: string) {
    setPulsingCards((prev) => new Set(prev).add(cardId));
    const existing = pulseTimers.current.get(cardId);
    if (existing) clearTimeout(existing);
    const timer = setTimeout(() => {
      setPulsingCards((prev) => {
        const n = new Set(prev);
        n.delete(cardId);
        return n;
      });
      pulseTimers.current.delete(cardId);
    }, 5000);
    pulseTimers.current.set(cardId, timer);
  }

  const handleVisibilityToggle = useCallback(
    async (sourceId: string, currentVisibility: string) => {
      if (!accessToken) return;
      const newVis = currentVisibility === "shown" ? "hidden" : "shown";
      setLicenseSources((prev) =>
        prev.map((s) => (s.id === sourceId ? { ...s, visibility: newVis } : s))
      );
      try {
        const res = await fetch(`${API}/admin/license-sources/${sourceId}/visibility`, {
          method: "PATCH",
          headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
          body: JSON.stringify({ visibility: newVis }),
        });
        if (!res.ok) throw new Error();
      } catch {
        setLicenseSources((prev) =>
          prev.map((s) => (s.id === sourceId ? { ...s, visibility: currentVisibility } : s))
        );
        showToast("Failed to update visibility.");
      }
    },
    [accessToken]
  );

  async function handleSafeModeToggle() {
    if (!accessToken) return;
    const newVal = safeMode === "on" ? "off" : "on";
    setSafeMode(newVal);
    try {
      const res = await fetch(`${API}/admin/safe-mode`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ value: newVal }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setSafeMode(safeMode);
      showToast("Failed to update safe mode.");
    }
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
        setActionIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
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
        setActionIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
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
        setContributors((prev) => prev.filter((c) => c.user_id !== revokeTarget.user_id));
        showToast(`${revokeTarget.display_name ?? "Contributor"}'s access has been revoked.`);
        setRevokeTarget(null);
        setRevokeRemoveCards(false);
      }
    } finally {
      setRevokeLoading(false);
    }
  }

  const handleApproveNote = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setNoteActionIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/pastors-notes/cards/${id}/approve`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setPendingNotes((prev) => prev.filter((n) => n.id !== id));
          showToast("Note approved and published.");
        }
      } finally {
        setNoteActionIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
      }
    },
    [accessToken]
  );

  const handleRejectNote = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setNoteActionIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/pastors-notes/cards/${id}/reject`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setPendingNotes((prev) => prev.filter((n) => n.id !== id));
          showToast("Note rejected.");
        }
      } finally {
        setNoteActionIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
      }
    },
    [accessToken]
  );

  // ── Derived state ──────────────────────────────────────────────

  const maintenanceCards = CARDS.filter((c) => c.isMaintenance);
  const visibleGroups = (GROUPS as readonly string[]).filter((g) => g !== "Maintenance");

  // ── Render ─────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex flex-col max-w-5xl w-full h-[85vh] p-0 gap-0 overflow-hidden"
      >
        <DialogTitle className="sr-only">Admin panel</DialogTitle>

        {/* Loading / auth-check */}
        {!roleChecked && (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Two-column layout */}
        {roleChecked && (
          <div className="flex flex-1 min-h-0 overflow-hidden">

            {/* Left nav */}
            <div className="w-[200px] shrink-0 bg-muted border-r border-border flex flex-col pt-6 pb-4 px-2">
              <p className="px-2 mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Admin
              </p>
              <nav className="flex flex-col gap-0.5">
                {NAV_TABS.map((tab) => (
                  <Button
                    key={tab.key}
                    variant="ghost"
                    className={cn(
                      "w-full justify-start gap-2 text-sm font-medium",
                      activeTab === tab.key && "bg-accent text-accent-foreground"
                    )}
                    onClick={() => setActiveTab(tab.key)}
                  >
                    <tab.icon className="h-4 w-4 shrink-0" />
                    <span>{tab.label}</span>
                    {tab.key === "notes-queue" && pendingNotes.length > 0 && (
                      <span className="ml-auto inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground">
                        {pendingNotes.length}
                      </span>
                    )}
                  </Button>
                ))}
              </nav>
            </div>

            {/* Right pane */}
            <div className="flex-1 overflow-y-auto p-6">

              {/* ── Feedback ───────────────────────────────────── */}
              {activeTab === "feedback" && (
                <div role="tabpanel">
                  <h2 className="text-xl font-semibold text-foreground font-sans mb-6">Feedback</h2>

                  <div className="flex gap-6 mb-6 border-b border-border">
                    {FEEDBACK_TABS.map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setFeedbackTab(tab.key)}
                        className={`-mb-px pb-2 text-sm font-medium transition-colors cursor-pointer ${
                          feedbackTab === tab.key
                            ? "text-foreground border-b-2 border-foreground"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {feedbackLoading ? (
                    <SkeletonRows />
                  ) : feedbackEntries.length === 0 ? (
                    <div className="rounded-lg border border-border bg-card p-6 text-center">
                      <p className="text-sm text-muted-foreground">No feedback yet</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {feedbackEntries.map((f) => (
                        <div key={f.id} className="rounded-lg border border-border bg-card p-4">
                          <div className="flex items-start gap-3">
                            <span
                              className={`mt-1.5 inline-block h-2 w-2 rounded-full shrink-0 ${
                                f.rating === "thumbs_up" ? "bg-primary" : "bg-destructive"
                              }`}
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-foreground">{f.question}</p>
                              {f.comment && (
                                <p className="text-xs mt-1 text-muted-foreground">{f.comment}</p>
                              )}
                              <p className="text-xs mt-2 text-muted-foreground">
                                {new Date(f.created_at).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                  hour: "numeric",
                                  minute: "2-digit",
                                })}
                              </p>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── Contributors ────────────────────────────────── */}
              {activeTab === "contributors" && (
                <div role="tabpanel">
                  <h2 className="text-xl font-semibold text-foreground font-sans mb-6">Contributors</h2>

                  <div className="space-y-6">
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
                          <p className="text-sm text-muted-foreground">No pending applications.</p>
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
                          <p className="text-sm text-muted-foreground">No active contributors.</p>
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
                                      <span className="italic text-muted-foreground">No display name</span>
                                    )}
                                  </p>
                                  <p className="text-xs text-muted-foreground truncate">
                                    {c.email || "—"}
                                  </p>
                                  <p className="text-xs text-muted-foreground mt-0.5">
                                    {c.card_count} published note{c.card_count !== 1 ? "s" : ""} · granted{" "}
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
                  </div>
                </div>
              )}

              {/* ── Notes Queue ─────────────────────────────────── */}
              {activeTab === "notes-queue" && (
                <div role="tabpanel">
                  <h2 className="text-xl font-semibold text-foreground font-sans mb-6">
                    Notes Queue
                    {pendingNotes.length > 0 && (
                      <span className="ml-3 inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-primary px-2 text-xs font-medium text-primary-foreground">
                        {pendingNotes.length}
                      </span>
                    )}
                  </h2>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Pending Review
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {pendingNotesLoading ? (
                        <div className="space-y-3">
                          <Skeleton className="h-24 w-full" />
                          <Skeleton className="h-24 w-full" />
                        </div>
                      ) : pendingNotes.length === 0 ? (
                        <p className="text-sm text-muted-foreground">No notes pending review.</p>
                      ) : (
                        <div className="space-y-4">
                          {pendingNotes.map((note) => (
                            <div
                              key={note.id}
                              className="rounded-lg border border-border bg-card p-4 space-y-3"
                            >
                              <div className="flex items-start justify-between gap-4">
                                <div className="min-w-0">
                                  <p className="text-xs font-medium uppercase tracking-wide text-primary">
                                    {formatVerseId(note.verse_id)}
                                  </p>
                                  <p className="text-sm font-medium text-foreground mt-0.5">
                                    {note.display_name ?? (
                                      <span className="italic text-muted-foreground">No display name</span>
                                    )}
                                  </p>
                                  <p className="text-xs text-muted-foreground truncate">
                                    {note.email || "—"}
                                  </p>
                                  <p className="text-xs text-muted-foreground mt-0.5">
                                    {fmtDate(note.created_at)}
                                  </p>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                  <Button
                                    size="sm"
                                    onClick={() => handleApproveNote(note.id)}
                                    disabled={noteActionIds.has(note.id)}
                                  >
                                    {noteActionIds.has(note.id) ? (
                                      <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                      "Approve"
                                    )}
                                  </Button>
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleRejectNote(note.id)}
                                    disabled={noteActionIds.has(note.id)}
                                  >
                                    Reject
                                  </Button>
                                </div>
                              </div>
                              <p className="text-sm text-foreground leading-relaxed border-t border-border pt-3">
                                {note.content}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>
              )}

              {/* ── Corpus ──────────────────────────────────────── */}
              {activeTab === "corpus" && (
                <div role="tabpanel">
                  <div className="flex items-center justify-between mb-6">
                    <h2 className="text-xl font-semibold text-foreground font-sans">Corpus</h2>
                  </div>

                  {/* Sub-view tab bar */}
                  <div className="flex gap-5 mb-6 border-b border-border">
                    {(["documents", "sources", "pipelines"] as CorpusSubView[]).map((sv) => (
                      <button
                        key={sv}
                        onClick={() => setCorpusSubView(sv)}
                        className={`-mb-px pb-2 text-sm font-medium capitalize transition-colors cursor-pointer ${
                          corpusSubView === sv
                            ? "text-foreground border-b-2 border-foreground"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {sv}
                      </button>
                    ))}
                  </div>

                  {adminDataError && (
                    <div className="mb-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
                      <p className="text-sm font-medium text-destructive">
                        Couldn&apos;t load admin data — check backend connection or auth.
                      </p>
                    </div>
                  )}

                  {/* Documents */}
                  {corpusSubView === "documents" && (
                    <CorpusDocumentsPanel
                      accessToken={accessToken}
                      licenseSources={licenseSources.map((s) => ({ id: s.id, name: s.name }))}
                    />
                  )}

                  {/* Sources */}
                  {corpusSubView === "sources" && (
                    <div>
                      {!licenseSourcesLoading && licenseSources.length > 0 && (() => {
                        const total = licenseSources.length;
                        const exposed = licenseSources.filter(
                          (s) => s.license_status === "unlicensed" && s.visibility === "shown"
                        ).length;
                        return (
                          <div className="flex items-center gap-2 mb-4 text-xs text-muted-foreground">
                            <span>{total} source{total !== 1 ? "s" : ""}</span>
                            {exposed > 0 && (
                              <span className="inline-flex items-center rounded-full border border-destructive/50 bg-destructive/10 px-2 py-0.5 text-destructive font-medium">
                                {exposed} unlicensed + shown
                              </span>
                            )}
                          </div>
                        );
                      })()}

                      {licenseSourcesLoading ? (
                        <SkeletonRows />
                      ) : licenseSources.length === 0 ? (
                        <div className="rounded-lg border border-border bg-card p-4">
                          <p className="text-sm text-muted-foreground">No sources found. Check the backend connection.</p>
                        </div>
                      ) : (
                        <div className="rounded-lg border border-border overflow-hidden mb-8">
                          <div className="grid grid-cols-[1fr_3.5rem_9rem_4.5rem_5rem] gap-x-3 px-4 py-2 border-b border-border bg-muted/40">
                            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Source</span>
                            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground text-right">Docs</span>
                            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">License</span>
                            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground text-right">Visible</span>
                            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground text-right">Manage</span>
                          </div>
                          <div className="divide-y divide-border">
                            {licenseSources.map((src) => {
                              const isSentinel = src.id === SENTINEL_SOURCE_ID;
                              const licenseColor =
                                src.license_status === "public_domain" || src.license_status === "owned"
                                  ? "border-primary/40 bg-primary/10 text-primary"
                                  : src.license_status === "unlicensed"
                                  ? "border-destructive/40 bg-destructive/10 text-destructive"
                                  : "border-border bg-muted/40 text-muted-foreground";
                              return (
                                <div
                                  key={src.id}
                                  className={
                                    "grid grid-cols-[1fr_3.5rem_9rem_4.5rem_5rem] gap-x-3 px-4 py-3 items-center" +
                                    (isSentinel ? " opacity-50" : "")
                                  }
                                >
                                  <div className="min-w-0 flex items-center gap-1.5">
                                    {isSentinel && <Lock className="h-3 w-3 text-muted-foreground shrink-0" />}
                                    <p className="text-sm font-medium text-foreground truncate">{src.name}</p>
                                  </div>
                                  <span className="text-xs text-muted-foreground text-right tabular-nums">
                                    {src.doc_count !== null ? src.doc_count.toLocaleString() : "—"}
                                  </span>
                                  <span className={"text-xs rounded-full border px-2 py-0.5 inline-block truncate font-medium " + licenseColor}>
                                    {src.license_status}
                                  </span>
                                  <div className="flex justify-end">
                                    {isSentinel ? (
                                      <span className="text-xs text-muted-foreground">protected</span>
                                    ) : (
                                      <Switch
                                        checked={src.visibility === "shown"}
                                        onCheckedChange={() => handleVisibilityToggle(src.id, src.visibility)}
                                        className={src.visibility === "shown" ? "data-[state=checked]:bg-primary" : ""}
                                      />
                                    )}
                                  </div>
                                  <div className="flex justify-end">
                                    {!isSentinel && (
                                      <button
                                        onClick={() => setManageSrcTarget(src)}
                                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                      >
                                        Manage
                                      </button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Safe Mode */}
                      <div
                        className={
                          "flex items-center justify-between rounded-lg border p-4 " +
                          (safeMode === "on"
                            ? "bg-destructive/10 border-destructive/50"
                            : "bg-card border-border")
                        }
                      >
                        <div>
                          <p className={"text-sm font-semibold " + (safeMode === "on" ? "text-destructive" : "text-foreground")}>
                            Safe mode{safeMode === "on" ? " — ACTIVE" : ""}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            Serves only public domain + owned. Ignores visibility.
                          </p>
                        </div>
                        <Switch
                          checked={safeMode === "on"}
                          onCheckedChange={handleSafeModeToggle}
                          disabled={safeModeLoading}
                          className={safeMode === "on" ? "data-[state=checked]:bg-destructive" : ""}
                        />
                      </div>

                      {/* Manage Source Sheet */}
                      <Sheet
                        open={!!manageSrcTarget}
                        onOpenChange={(open) => { if (!open) setManageSrcTarget(null); }}
                      >
                        <SheetContent side="right" className="flex flex-col w-full sm:max-w-md">
                          <SheetHeader>
                            <SheetTitle>{manageSrcTarget?.name ?? "Source"}</SheetTitle>
                            <SheetDescription>Source details (read-only)</SheetDescription>
                          </SheetHeader>
                          <div className="flex-1 overflow-y-auto px-1 pb-4 space-y-4 pt-2">
                            {manageSrcTarget && (
                              <>
                                <div className="rounded-lg border border-border bg-card p-4 space-y-3">
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-muted-foreground">License status</span>
                                    <span className="text-xs font-medium text-foreground">{manageSrcTarget.license_status}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-muted-foreground">Visibility</span>
                                    <span className="text-xs font-medium text-foreground">{manageSrcTarget.visibility}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span className="text-xs text-muted-foreground">Documents</span>
                                    <span className="text-xs font-medium text-foreground tabular-nums">
                                      {manageSrcTarget.doc_count !== null ? manageSrcTarget.doc_count.toLocaleString() : "—"}
                                    </span>
                                  </div>
                                  <div className="flex items-start justify-between gap-2">
                                    <span className="text-xs text-muted-foreground shrink-0">Source ID</span>
                                    <div className="flex items-center gap-1 min-w-0">
                                      <span className="text-xs font-mono text-foreground break-all">{manageSrcTarget.id}</span>
                                      <CopyButton text={manageSrcTarget.id} />
                                    </div>
                                  </div>
                                </div>
                                <div className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
                                  <div>
                                    <p className="text-sm font-medium text-foreground">Visibility</p>
                                    <p className="text-xs text-muted-foreground mt-0.5">
                                      {manageSrcTarget.visibility === "shown" ? "Shown in retrieval" : "Hidden from retrieval"}
                                    </p>
                                  </div>
                                  <Switch
                                    checked={manageSrcTarget.visibility === "shown"}
                                    onCheckedChange={() => {
                                      handleVisibilityToggle(manageSrcTarget.id, manageSrcTarget.visibility);
                                      setManageSrcTarget((prev) =>
                                        prev ? { ...prev, visibility: prev.visibility === "shown" ? "hidden" : "shown" } : null
                                      );
                                    }}
                                  />
                                </div>
                              </>
                            )}
                          </div>
                        </SheetContent>
                      </Sheet>
                    </div>
                  )}

                  {/* Pipelines */}
                  {corpusSubView === "pipelines" && (
                    <div>
                      {/* Stats + Ingestion monitor */}
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                            Ingestion monitor
                          </h3>
                          <span
                            className={`inline-block h-2 w-2 rounded-full ${
                              realtimeConnected ? "animate-pulse bg-primary" : "bg-muted-foreground"
                            }`}
                          />
                        </div>
                        {lastUpdated && (
                          <p className="text-xs text-muted-foreground mb-4">
                            Last updated: {lastUpdated.toLocaleTimeString()}
                          </p>
                        )}

                        <div className="flex flex-wrap gap-3 mb-8 p-3 rounded-lg bg-card border border-border">
                          <StatPill label="Total Documents" value={globalStats.totalDocuments} />
                          <StatPill label="Total Chunks" value={globalStats.totalChunks} />
                          <StatPill label="Total Verses" value={globalStats.totalVerses} />
                          <StatPill label="Interlinear Words" value={globalStats.totalInterlinearWords} />
                        </div>

                        {visibleGroups.map((group) => {
                          const groupCards = CARDS.filter((c) => c.group === group);
                          if (groupCards.length === 0) return null;
                          return (
                            <div key={group} className="mb-8">
                              <h4 className="text-base font-medium text-foreground font-sans mb-3">{group}</h4>
                              <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
                                {groupCards.map((card) => (
                                  <CorpusCardComponent
                                    key={card.id}
                                    card={card}
                                    count={counts[card.id]?.count ?? null}
                                    lastIngested={counts[card.id]?.lastIngested ?? null}
                                    pulsing={pulsingCards.has(card.id)}
                                    onClick={() => setSelectedCard(card)}
                                  />
                                ))}
                              </div>
                            </div>
                          );
                        })}

                        {maintenanceCards.length > 0 && (
                          <div className="mb-8">
                            <button
                              onClick={() => setMaintenanceOpen((o) => !o)}
                              className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors py-2"
                            >
                              {maintenanceOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                              Maintenance
                            </button>
                            {maintenanceOpen && (
                              <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 mt-3">
                                {maintenanceCards.map((card) => (
                                  <CorpusCardComponent
                                    key={card.id}
                                    card={card}
                                    count={null}
                                    lastIngested={null}
                                    pulsing={false}
                                    onClick={() => setSelectedCard(card)}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        <div className="mb-8">
                          <button
                            onClick={() => setFutureTargetsOpen((o) => !o)}
                            className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors py-2"
                          >
                            {futureTargetsOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                            Future Corpus Targets
                          </button>
                          {futureTargetsOpen && (
                            <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 mt-3">
                              {FUTURE_TARGETS.map((target) => (
                                <FutureTargetCard key={target.id} target={target} />
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Command reference */}
                      <div className="mt-2">
                        <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground mb-4">
                          Command reference
                        </h3>
                        <div className="space-y-6">
                          {PIPELINE_CMD_GROUPS.map((grp) => (
                            <div key={grp.group}>
                              <p className="text-sm font-medium text-foreground mb-2">{grp.group}</p>
                              {grp.note && (
                                <p className="text-xs text-muted-foreground mb-2 italic">{grp.note}</p>
                              )}
                              <div className="rounded-lg border border-border overflow-hidden divide-y divide-border">
                                {grp.cmds.map((c) => (
                                  <div key={c.label} className="flex items-center gap-3 px-3 py-2.5 bg-card">
                                    <span className="text-xs text-muted-foreground w-28 shrink-0">{c.label}</span>
                                    <code className="flex-1 text-xs font-mono text-foreground truncate">{c.cmd}</code>
                                    <CopyButton text={c.cmd} />
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

            </div>
          </div>
        )}

        {/* CardModal — portaled, safe to nest */}
        {selectedCard && (
          <CardModal
            card={selectedCard}
            count={counts[selectedCard.id]?.count ?? null}
            onClose={() => setSelectedCard(null)}
          />
        )}

        {/* Toast */}
        {toast && (
          <div className="fixed bottom-4 right-4 z-50 rounded-lg border bg-popover px-4 py-3 text-sm text-popover-foreground shadow-lg">
            {toast}
          </div>
        )}

        {/* Revoke sheet — portaled via SheetPortal */}
        <Sheet
          open={!!revokeTarget}
          onOpenChange={(isOpen) => { if (!isOpen) setRevokeTarget(null); }}
        >
          <SheetContent side="right" className="flex flex-col">
            <SheetHeader>
              <SheetTitle>
                Revoke {revokeTarget?.display_name ?? "contributor"}&apos;s access?
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
                <span className="text-sm text-foreground">Also remove all their notes</span>
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

      </DialogContent>
    </Dialog>
  );
}
