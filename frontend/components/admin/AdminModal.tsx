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
  User as UserIcon,
  Link2,
  BarChart3,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useUserRole } from "@/hooks/useUserRole";
import { useIsMobile } from "@/hooks/use-mobile";
import { useSheetDrag } from "@/hooks/use-sheet-drag";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
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
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import CorpusCardComponent from "@/components/admin/corpus-card";
import CardModal from "@/components/admin/card-modal";
import { CARDS, GROUPS, FUTURE_TARGETS } from "@/components/admin/corpus-data";
import type { CorpusCard } from "@/components/admin/corpus-types";
import { CorpusDocumentsPanel, CopyButton } from "@/components/admin/CorpusDocumentsPanel";
import { SourceQueuePanel } from "@/components/admin/SourceQueuePanel";
import { AnalyticsPanel } from "@/components/admin/AnalyticsPanel";

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

interface DeletionRequest {
  id: string;
  user_id: string;
  email: string;
  created_at: string;
  status: "pending" | "failed";
  failure_reason: string | null;
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

// ── Constants ──────────────────────────────────────────────────────────────

const FEEDBACK_TABS: { key: FeedbackTab; label: string }[] = [
  { key: "chat_answer", label: "Chat Answers" },
  { key: "commentary", label: "Commentary" },
  { key: "word_study", label: "Word Studies" },
];

type TopTab = "profile" | "corpus" | "feedback" | "contributors" | "notes-queue" | "source-queue" | "analytics";
type CorpusSubView = "documents" | "sources" | "pipelines";

type NavTab = {
  key: TopTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

// Always visible, regardless of role.
const PROFILE_NAV_TAB: NavTab = { key: "profile", label: "Profile", icon: UserIcon };

// Admin-only — only rendered in the nav when userRole === "admin".
const NAV_TABS: NavTab[] = [
  { key: "corpus",       label: "Corpus",       icon: Database },
  { key: "feedback",     label: "Feedback",     icon: ThumbsUp },
  { key: "contributors", label: "Contributors", icon: Users    },
  { key: "notes-queue",  label: "Notes Queue",  icon: Inbox    },
  { key: "source-queue", label: "Source Queue", icon: Link2    },
  { key: "analytics",    label: "Analytics",    icon: BarChart3 },
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

function fmtResetDate(iso: string) {
  // `iso` is a date-only string (e.g. "2026-07-27") representing the UTC
  // reset day -- format in UTC explicitly, or a browser west of UTC renders
  // it a day early (new Date("2026-07-27") is midnight UTC, and
  // toLocaleDateString without a pinned timeZone renders in local time).
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function formatVerseId(verseId: string): string {
  const parts = verseId.split(".");
  if (parts.length !== 3) return verseId;
  return `${parts[0]} ${parts[1]}:${parts[2]}`;
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
  onOpenContributor: () => void;
}

export function AdminModal({ open, onOpenChange, onOpenContributor }: AdminModalProps) {
  const { user, accessToken, loading: authLoading, signOut } = useAuth();
  const { role: userRole, displayName, updateDisplayName } = useUserRole(accessToken ?? null);

  // Derived: true once auth resolves for any authenticated user — this panel
  // is no longer admin-only, it opens for everyone (Profile tab). Admin-only
  // tabs and their data fetches stay gated on roleChecked below.
  const panelReady = open && !authLoading;
  const roleChecked = panelReady && userRole === "admin";

  // ── Navigation ─────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState<TopTab>("profile");

  // ── Mobile drag-to-dismiss ─────────────────────────────────────
  // Below md this dialog presents as a bottom sheet that follows the finger.
  // Desktop keeps the ordinary centred dialog and gets no handlers at all.
  const isMobile = useIsMobile();
  const handleDismiss = useCallback(() => onOpenChange(false), [onOpenChange]);
  const sheet = useSheetDrag({ open, enabled: isMobile, onDismiss: handleDismiss });

  // The scrolling pane hands downward drags to the sheet only while it is at
  // its own top (see its touch-action below). Switching tabs resets its
  // scroll, so this has to reset with it.
  const [paneAtTop, setPaneAtTop] = useState(true);
  useEffect(() => setPaneAtTop(true), [activeTab]);
  const [corpusSubView, setCorpusSubView] = useState<CorpusSubView>("documents");

  // ── Profile ────────────────────────────────────────────────────
  const [editDisplayName, setEditDisplayName] = useState("");
  const [nameStatus, setNameStatus] = useState<"idle" | "loading" | "saved" | "error">("idle");
  const [weeklyUsage, setWeeklyUsage] = useState<{ used: number; limit: number; resets: string } | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState<"idle" | "loading" | "sent" | "error">("idle");
  const [deleteError, setDeleteError] = useState<string | null>(null);

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
  const [deletionRequests, setDeletionRequests] = useState<DeletionRequest[]>([]);
  const [deletionRequestsLoaded, setDeletionRequestsLoaded] = useState(false);
  const [deletionRequestsLoading, setDeletionRequestsLoading] = useState(true);
  const [resolveIds, setResolveIds] = useState<Set<string>>(new Set());
  const [deletionConfirmTarget, setDeletionConfirmTarget] = useState<DeletionRequest | null>(null);

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
  // Mirrors `counts` synchronously (state updates are async) so the polling
  // effect below can diff against the previous snapshot without a race.
  const countsRef = useRef<CountData>({});
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

  // documents/chunks are service-role-only as of the corpus RLS lockdown, so
  // counts run server-side under the service key instead of the anon client.
  const fetchAllCounts = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API}/admin/corpus/card-counts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          cards: CARDS.filter((c) => !c.isMaintenance).map((c) => ({
            id: c.id,
            sourceKind: c.sourceKind,
            sourceType: c.sourceType,
            extraFilter: c.extraFilter,
            notFilter: c.notFilter,
            specialTable: c.specialTable,
            specialWhere: c.specialWhere,
            countChunks: c.countChunks,
          })),
        }),
      });
      if (!res.ok) throw new Error(`card-counts ${res.status}`);
      const data: { counts: CountData } = await res.json();
      const nextCounts = data.counts ?? {};
      setCounts(nextCounts);
      countsRef.current = nextCounts;
      setLastUpdated(new Date());
    } catch (err) {
      console.warn("[admin] fetchAllCounts failed:", err);
      setAdminDataError(true);
    }
  }, [accessToken]);

  // ── Data fetches ───────────────────────────────────────────────

  // Reset the display-name field only on the open-transition edge, not on
  // every displayName change — otherwise a successful save (which updates
  // displayName via updateDisplayName) would immediately wipe its own
  // "Saved." feedback by re-running this effect.
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setEditDisplayName(displayName ?? "");
      setNameStatus("idle");
    }
    wasOpenRef.current = open;
  }, [open, displayName]);

  useEffect(() => {
    if (!panelReady || !accessToken || activeTab !== "profile") return;
    setUsageLoading(true);
    fetch(`${API}/usage`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data) => setWeeklyUsage({ used: data.used, limit: data.limit, resets: data.resets }))
      .catch(() => setWeeklyUsage(null))
      .finally(() => setUsageLoading(false));
  }, [panelReady, accessToken, activeTab]);

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
    if (!roleChecked || !accessToken || activeTab !== "contributors" || deletionRequestsLoaded) return;
    setDeletionRequestsLoaded(true);
    fetch(`${API}/account/delete-requests`, { headers: { Authorization: `Bearer ${accessToken}` } })
      .then((r) => r.json())
      .then((data) => setDeletionRequests(Array.isArray(data) ? data : []))
      .catch(() => setDeletionRequests([]))
      .finally(() => setDeletionRequestsLoading(false));
  }, [roleChecked, accessToken, activeTab, deletionRequestsLoaded]);

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

  // Polling replaces the old Supabase Realtime subscription on `documents`.
  // Realtime respects RLS for anon/authenticated roles — under the corpus
  // RLS lockdown the channel would report SUBSCRIBED but INSERT events would
  // never arrive (same silent-empty failure mode as a direct anon read).
  // Poll the same backend-aggregated counts instead, diffing against the
  // previous snapshot to drive the existing per-card pulse animation.
  useEffect(() => {
    if (!roleChecked || !accessToken || activeTab !== "corpus") return;
    setRealtimeConnected(true);
    const interval = setInterval(async () => {
      const prevCounts = countsRef.current;
      await fetchAllCounts();
      for (const card of CARDS) {
        const prevCount = prevCounts[card.id]?.count ?? 0;
        const nextCount = countsRef.current[card.id]?.count ?? 0;
        if (nextCount > prevCount) triggerPulse(card.id);
      }
    }, 30000);
    return () => {
      clearInterval(interval);
      setRealtimeConnected(false);
    };
  }, [roleChecked, accessToken, activeTab, fetchAllCounts]);

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

  async function handleSaveDisplayName() {
    if (!accessToken) return;
    const trimmed = editDisplayName.trim();
    if (!trimmed) return;
    setNameStatus("loading");
    try {
      const res = await fetch(`${API}/pastors-notes/me`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ display_name: trimmed }),
      });
      if (res.ok) {
        updateDisplayName(trimmed);
        setNameStatus("saved");
      } else {
        setNameStatus("error");
      }
    } catch {
      setNameStatus("error");
    }
  }

  function handleOpenDeleteConfirm() {
    setDeleteStatus("idle");
    setDeleteError(null);
    setDeleteConfirmOpen(true);
  }

  async function handleDeleteRequest() {
    if (!accessToken) return;
    setDeleteStatus("loading");
    setDeleteError(null);
    try {
      const res = await fetch(`${API}/account/delete-request`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.status === 400) {
        const data = await res.json();
        setDeleteError(data.detail ?? "You already have a pending deletion request.");
        setDeleteStatus("error");
      } else if (res.ok) {
        setDeleteStatus("sent");
      } else {
        setDeleteError("Something went wrong. Please try again.");
        setDeleteStatus("error");
      }
    } catch {
      setDeleteError("Something went wrong. Please try again.");
      setDeleteStatus("error");
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

  const handleResolveDeletion = useCallback(
    async (id: string) => {
      if (!accessToken) return;
      setResolveIds((prev) => new Set(prev).add(id));
      try {
        const res = await fetch(`${API}/account/delete-requests/${id}/resolve`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (res.ok) {
          setDeletionRequests((prev) => prev.filter((r) => r.id !== id));
          showToast("Account permanently deleted.");
        } else {
          // A real failure now (e.g. reconciliation found a remaining row,
          // or the Auth API call itself failed) -- refresh so the row's
          // status/failure_reason reflect what actually happened, and say
          // so instead of silently doing nothing.
          setDeletionRequestsLoaded(false);
          showToast("Deletion failed -- see the request's status for details.");
        }
      } finally {
        setResolveIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
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
        ref={sheet.rootRef}
        data-mobile-sheet=""
        data-sheet-dragging={sheet.dragging ? "true" : undefined}
        data-sheet-dismissing={sheet.dismissing ? "true" : undefined}
        style={{ "--sheet-drag-y": `${sheet.offset}px` } as React.CSSProperties}
        overlayStyle={{ opacity: sheet.overlayOpacity }}
        className="flex h-[calc(100dvh-1rem)] w-[calc(100%-1rem)] max-w-5xl flex-col gap-0 overflow-hidden p-0 sm:h-[85dvh]"
        {...sheet.dragHandlers}
      >
        <DialogTitle className="sr-only">Account</DialogTitle>

        {/* Grab affordance. The whole sheet drags, not just this bar -- it is
            here to say so, which is why it is aria-hidden and not a button. */}
        <div
          aria-hidden="true"
          className="flex shrink-0 items-center justify-center pt-2 pb-1 md:hidden"
        >
          <span className="h-1 w-10 rounded-full bg-border" />
        </div>

        {/* Loading / auth-check */}
        {!panelReady && (
          <div className="flex flex-1 items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* Two-column layout */}
        {panelReady && (
          <div className="flex flex-1 min-h-0 flex-col overflow-hidden md:flex-row">

            {/* Left nav */}
            <div className="flex w-full shrink-0 flex-col border-b border-border bg-muted px-2 pb-2 pt-3 md:w-[200px] md:border-b-0 md:border-r md:pb-4 md:pt-6">
              <p className="mb-3 hidden px-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground md:block">
                Account
              </p>
              <nav className="flex gap-1 overflow-x-auto overscroll-x-contain touch-pan-x md:touch-auto md:flex-col md:gap-0.5">
                <Button
                  variant="ghost"
                  className={cn(
                    "min-h-11 shrink-0 justify-start gap-2 text-sm font-medium md:w-full",
                    activeTab === "profile" && "bg-accent text-accent-foreground"
                  )}
                  onClick={() => setActiveTab("profile")}
                >
                  <PROFILE_NAV_TAB.icon className="h-4 w-4 shrink-0" />
                  <span>{PROFILE_NAV_TAB.label}</span>
                </Button>
                {roleChecked && NAV_TABS.map((tab) => (
                  <Button
                    key={tab.key}
                    variant="ghost"
                    className={cn(
                      "min-h-11 shrink-0 justify-start gap-2 text-sm font-medium md:w-full",
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
            <div
              className={cn(
                "flex-1 overscroll-contain overflow-y-auto p-4 sm:p-6 md:touch-auto",
                // touch-action: pan-up allows only UPWARD panning, so at the
                // top of its scroll a downward drag never starts a native
                // scroll and reaches the sheet gesture intact. Without this
                // iOS begins scrolling and cancels the pointer stream
                // mid-gesture, and the sheet just never moves.
                isMobile && paneAtTop ? "touch-pan-up" : "touch-pan-y",
              )}
              onScroll={(event) => {
                const atTop = event.currentTarget.scrollTop <= 0;
                setPaneAtTop((prev) => (prev === atTop ? prev : atTop));
              }}
            >

              {/* ── Profile ─────────────────────────────────────── */}
              {activeTab === "profile" && (
                <div role="tabpanel">
                  <div className="max-w-lg">
                    {/* Identity header */}
                    <div className="flex flex-col items-start justify-between gap-4 pb-6 sm:flex-row">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-lg font-semibold">
                          {(displayName?.[0] ?? user?.email?.[0] ?? "?").toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-lg font-semibold text-foreground truncate">
                              {displayName ?? user?.email ?? ""}
                            </p>
                            {userRole === "admin" && (
                              <Badge variant="outline" className="bg-primary/15 text-primary border-primary/35">
                                Admin
                              </Badge>
                            )}
                            {userRole === "contributor" && (
                              <Badge variant="outline" className="bg-primary/15 text-primary border-primary/35">
                                Contributor
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground truncate">{user?.email ?? ""}</p>
                        </div>
                      </div>
                      <Button variant="outline" size="sm" className="shrink-0" onClick={signOut}>
                        Sign out
                      </Button>
                    </div>

                    <div className="space-y-6">
                      <Card>
                        <CardHeader>
                          <CardTitle className="text-base font-semibold text-foreground">
                            Display name
                          </CardTitle>
                          <p className="text-sm text-muted-foreground">
                            Shown on your published pastoral notes
                          </p>
                        </CardHeader>
                        <CardContent>
                          <div className="flex flex-col gap-2 sm:flex-row">
                            <Input
                              value={editDisplayName}
                              onChange={(e) => {
                                setEditDisplayName(e.target.value);
                                setNameStatus("idle");
                              }}
                              placeholder="Your name"
                              maxLength={100}
                              className="flex-1"
                            />
                            <Button
                              onClick={handleSaveDisplayName}
                              disabled={nameStatus === "loading" || !editDisplayName.trim()}
                            >
                              {nameStatus === "loading" ? (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              ) : (
                                "Save"
                              )}
                            </Button>
                          </div>
                          {nameStatus === "saved" && (
                            <p className="text-xs text-muted-foreground mt-2">Saved.</p>
                          )}
                          {nameStatus === "error" && (
                            <p className="text-xs text-destructive mt-2">Something went wrong. Please try again.</p>
                          )}
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader>
                          <CardTitle className="text-base font-semibold text-foreground">Email</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-foreground">{user?.email ?? ""}</p>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader>
                          <div className="flex items-center justify-between">
                            <CardTitle className="text-base font-semibold text-foreground">
                              Weekly usage
                            </CardTitle>
                            {weeklyUsage && (
                              <p className="text-sm text-foreground">
                                <span className="font-medium">{weeklyUsage.used}</span> of {weeklyUsage.limit}{" "}
                                questions
                              </p>
                            )}
                          </div>
                        </CardHeader>
                        <CardContent>
                          {usageLoading ? (
                            <Skeleton className="h-4 w-full" />
                          ) : weeklyUsage ? (
                            <>
                              <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-primary"
                                  style={{
                                    width: `${Math.min(100, Math.round((weeklyUsage.used / weeklyUsage.limit) * 100))}%`,
                                  }}
                                />
                              </div>
                              <p className="text-xs text-muted-foreground mt-2">
                                Resets {fmtResetDate(weeklyUsage.resets)}
                              </p>
                            </>
                          ) : (
                            <p className="text-sm text-muted-foreground">Usage unavailable.</p>
                          )}
                        </CardContent>
                      </Card>

                      {userRole === "user" && (
                        <Card>
                          <CardHeader>
                            <CardTitle className="text-base font-semibold text-foreground">
                              Become a contributor
                            </CardTitle>
                            <p className="text-sm text-muted-foreground">
                              Contribute pastoral notes readers can see alongside a passage.
                            </p>
                          </CardHeader>
                          <CardContent>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                onOpenChange(false);
                                onOpenContributor();
                              }}
                            >
                              Apply
                            </Button>
                          </CardContent>
                        </Card>
                      )}

                      <Card className="border-destructive/30">
                        <CardHeader>
                          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row">
                            <div>
                              <CardTitle className="text-base font-semibold text-foreground">
                                Delete account
                              </CardTitle>
                              <p className="text-sm text-muted-foreground mt-1">
                                Sends a request to remove your account and data — conversations, saved words,
                                and any pastoral notes you&apos;ve contributed. We&apos;ll follow up by email
                                before anything is deleted.
                              </p>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              className="shrink-0 text-destructive hover:text-destructive"
                              onClick={handleOpenDeleteConfirm}
                            >
                              Delete account
                            </Button>
                          </div>
                        </CardHeader>
                      </Card>
                    </div>
                  </div>
                </div>
              )}

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

                    <Card>
                      <CardHeader>
                        <CardTitle className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                          Account Deletion Requests
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        {deletionRequestsLoading ? (
                          <div className="space-y-3">
                            <Skeleton className="h-16 w-full" />
                          </div>
                        ) : deletionRequests.length === 0 ? (
                          <p className="text-sm text-muted-foreground">No pending deletion requests.</p>
                        ) : (
                          <div className="space-y-3">
                            {deletionRequests.map((req) => (
                              <div
                                key={req.id}
                                className="flex items-start justify-between gap-4 rounded-lg border border-border p-4"
                              >
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium text-foreground truncate">
                                    {req.email || "—"}
                                  </p>
                                  <p className="text-xs text-muted-foreground mt-1">
                                    Requested {fmtDate(req.created_at)}
                                  </p>
                                  {req.status === "failed" && (
                                    <p className="text-xs text-destructive mt-1">
                                      Failed: {req.failure_reason || "unknown error"} — safe to retry.
                                    </p>
                                  )}
                                </div>
                                <Button
                                  variant="destructive"
                                  size="sm"
                                  onClick={() => setDeletionConfirmTarget(req)}
                                  disabled={resolveIds.has(req.id)}
                                >
                                  {resolveIds.has(req.id) ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : req.status === "failed" ? (
                                    "Retry deletion"
                                  ) : (
                                    "Delete account"
                                  )}
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

              {/* ── Source Queue ─────────────────────────────────── */}
              {activeTab === "source-queue" && (
                <SourceQueuePanel accessToken={accessToken} />
              )}

              {/* ── Analytics ────────────────────────────────────── */}
              {activeTab === "analytics" && (
                <AnalyticsPanel accessToken={accessToken} />
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

        {/* Deletion confirmation — a real, irreversible account + data
            deletion now fires from this button, not a status flip. */}
        <AlertDialog
          open={!!deletionConfirmTarget}
          onOpenChange={(isOpen) => { if (!isOpen) setDeletionConfirmTarget(null); }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                Permanently delete {deletionConfirmTarget?.email || "this account"}?
              </AlertDialogTitle>
              <AlertDialogDescription>
                This deletes the account and all of its data — conversations, saved words,
                pastoral notes, usage history, and search history. This cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <Button
                variant="destructive"
                onClick={() => {
                  if (deletionConfirmTarget) handleResolveDeletion(deletionConfirmTarget.id);
                  setDeletionConfirmTarget(null);
                }}
              >
                Permanently delete
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

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

        {/* Delete account confirm. Uses plain Buttons, not AlertDialogAction, for
            the submit button -- Radix's AlertDialogAction/Cancel close the dialog
            synchronously on click and don't wait for an async onClick to resolve,
            which would close this before the "Request sent" state ever renders. */}
        <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
          <AlertDialogContent>
            {deleteStatus === "sent" ? (
              <>
                <AlertDialogHeader>
                  <AlertDialogTitle>Request sent</AlertDialogTitle>
                  <AlertDialogDescription>
                    We&apos;ve logged your request. An admin will review it before anything is deleted.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <Button onClick={() => setDeleteConfirmOpen(false)}>Done</Button>
                </AlertDialogFooter>
              </>
            ) : (
              <>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete your account?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This sends a request to remove your account and data — conversations, saved words, and any
                    pastoral notes you&apos;ve contributed. An admin will review your request before anything
                    is deleted. This cannot be undone once it happens.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                {deleteStatus === "error" && deleteError && (
                  <p className="text-xs text-destructive mb-4">{deleteError}</p>
                )}
                <AlertDialogFooter>
                  <AlertDialogCancel disabled={deleteStatus === "loading"}>Cancel</AlertDialogCancel>
                  <Button
                    variant="destructive"
                    onClick={handleDeleteRequest}
                    disabled={deleteStatus === "loading"}
                  >
                    {deleteStatus === "loading" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      "Delete account"
                    )}
                  </Button>
                </AlertDialogFooter>
              </>
            )}
          </AlertDialogContent>
        </AlertDialog>

      </DialogContent>
    </Dialog>
  );
}
