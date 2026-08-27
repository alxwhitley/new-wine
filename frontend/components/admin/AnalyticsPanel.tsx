"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const API = process.env.NEXT_PUBLIC_API_URL;

interface Summary {
  monitored_searches: number;
  no_material_count: number;
  missing_content_rate: number;
  topics_with_open_gaps: number;
  unclassified_rate: number;
  finalization_pending: number;
  finalization_classified: number;
  window_days: number;
}

interface TopicBar {
  topic: string;
  total: number;
  no_material: number;
  failure_rate: number;
}

interface Gap {
  id: string;
  redacted_question: string | null;
  status: "open" | "resolved";
  retest_outcome: string | null;
  created_at: string;
  resolved_at: string | null;
  text_purge_at: string | null;
}

interface AnalyticsPanelProps {
  accessToken: string | null;
}

function fmtPercent(n: number): string {
  return `${Math.round(n * 100)}%`;
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function AnalyticsPanel({ accessToken }: AnalyticsPanelProps) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [topics, setTopics] = useState<TopicBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState("");

  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [gapsLoading, setGapsLoading] = useState(false);
  const [gapActionIds, setGapActionIds] = useState<Set<string>>(new Set());

  const fetchSummary = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(`${API}/admin/analytics/summary`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setSummary(data.summary ?? null);
      setTopics(data.topics ?? []);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const fetchGaps = useCallback(
    async (topic: string) => {
      if (!accessToken) return;
      setGapsLoading(true);
      try {
        const res = await fetch(
          `${API}/admin/analytics/topics/${encodeURIComponent(topic)}/gaps`,
          { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        if (!res.ok) throw new Error();
        const data = await res.json();
        setGaps(data.gaps ?? []);
      } catch {
        setGaps([]);
      } finally {
        setGapsLoading(false);
      }
    },
    [accessToken]
  );

  function handleSelectTopic(topic: string) {
    setSelectedTopic(topic);
    fetchGaps(topic);
  }

  async function handleRetest(gapId: string) {
    if (!accessToken) return;
    setGapActionIds((prev) => new Set(prev).add(gapId));
    try {
      const res = await fetch(`${API}/admin/analytics/gaps/${gapId}/retests`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok && selectedTopic) fetchGaps(selectedTopic);
    } finally {
      setGapActionIds((prev) => {
        const s = new Set(prev);
        s.delete(gapId);
        return s;
      });
    }
  }

  async function handleResolve(gapId: string) {
    if (!accessToken) return;
    setGapActionIds((prev) => new Set(prev).add(gapId));
    try {
      const res = await fetch(`${API}/admin/analytics/gaps/${gapId}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (res.ok && selectedTopic) fetchGaps(selectedTopic);
    } finally {
      setGapActionIds((prev) => {
        const s = new Set(prev);
        s.delete(gapId);
        return s;
      });
    }
  }

  const filteredTopics = topics.filter((t) =>
    t.topic.toLowerCase().includes(filter.toLowerCase())
  );
  const maxTotal = Math.max(1, ...topics.map((t) => t.total));

  if (selectedTopic) {
    return (
      <div role="tabpanel">
        <button
          onClick={() => setSelectedTopic(null)}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4 cursor-pointer"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to topics
        </button>
        <h2 className="text-xl font-semibold text-foreground font-sans mb-6">{selectedTopic}</h2>

        {gapsLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : gaps.length === 0 ? (
          <p className="text-sm text-muted-foreground">No content gaps recorded for this topic.</p>
        ) : (
          <div className="space-y-3">
            {gaps.map((gap) => (
              <Card key={gap.id}>
                <CardContent className="pt-6">
                  <p className="text-sm text-foreground mb-2">
                    {gap.redacted_question ?? (
                      <span className="italic text-muted-foreground">Wording purged (30-day retention)</span>
                    )}
                  </p>
                  <div className="flex items-center gap-2 flex-wrap mb-3">
                    <Badge variant="outline" className={gap.status === "resolved" ? "bg-primary/15 text-primary border-primary/35" : ""}>
                      {gap.status === "resolved" ? "Resolved" : "Open"}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{fmtDate(gap.created_at)}</span>
                    {gap.retest_outcome && (
                      <span className="text-xs text-muted-foreground">
                        Last retest: {gap.retest_outcome}
                      </span>
                    )}
                  </div>
                  {gap.status === "open" && (
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRetest(gap.id)}
                        disabled={gapActionIds.has(gap.id) || !gap.redacted_question}
                      >
                        {gapActionIds.has(gap.id) ? <Loader2 className="h-3 w-3 animate-spin" /> : "Retest"}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleResolve(gap.id)}
                        disabled={
                          gapActionIds.has(gap.id) ||
                          !gap.retest_outcome ||
                          gap.retest_outcome === "no_material"
                        }
                      >
                        Resolve
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div role="tabpanel">
      <h2 className="text-xl font-semibold text-foreground font-sans mb-6">Analytics</h2>

      {error && (
        <div className="mb-6 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <p className="text-sm font-medium text-destructive">
            Couldn&apos;t load analytics — check backend connection or auth.
          </p>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : summary ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-primary">{summary.monitored_searches}</p>
              <p className="text-xs text-muted-foreground mt-1">Monitored searches</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-foreground">{summary.no_material_count}</p>
              <p className="text-xs text-muted-foreground mt-1">No-material results</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-foreground">{fmtPercent(summary.missing_content_rate)}</p>
              <p className="text-xs text-muted-foreground mt-1">Missing-content rate</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-foreground">{summary.topics_with_open_gaps}</p>
              <p className="text-xs text-muted-foreground mt-1">Topics with open gaps</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-foreground">{fmtPercent(summary.unclassified_rate)}</p>
              <p className="text-xs text-muted-foreground mt-1">Unclassified rate</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-2xl font-bold text-foreground">
                {summary.finalization_classified}/{summary.finalization_classified + summary.finalization_pending}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Classification coverage</p>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <CardTitle className="text-base font-semibold text-foreground">Topics by demand</CardTitle>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter topics…"
              className="h-8 rounded-md border border-border bg-background px-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
            />
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : filteredTopics.length === 0 ? (
            <p className="text-sm text-muted-foreground">No searches recorded in this window yet.</p>
          ) : (
            <>
              {/* Visual ranked bar chart -- no_material segment labeled with
                  text, never conveyed by color alone (WCAG AA). */}
              <div className="space-y-2 mb-6" role="img" aria-label="Topics ranked by search demand and missing-content count">
                {filteredTopics.map((t) => {
                  const totalWidth = Math.max(4, (t.total / maxTotal) * 100);
                  const noMaterialWidth = t.total > 0 ? (t.no_material / t.total) * totalWidth : 0;
                  return (
                    <button
                      key={t.topic}
                      onClick={() => handleSelectTopic(t.topic)}
                      className="w-full text-left group cursor-pointer"
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs text-foreground truncate">{t.topic}</span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {t.total} searches · {t.no_material} no material
                        </span>
                      </div>
                      <div className="h-3 rounded-full bg-muted overflow-hidden relative">
                        <div
                          className="h-full bg-primary/40 group-hover:bg-primary/55 transition-colors"
                          style={{ width: `${totalWidth}%` }}
                        />
                        {t.no_material > 0 && (
                          <div
                            className="h-full bg-destructive absolute top-0 left-0"
                            style={{ width: `${noMaterialWidth}%` }}
                          />
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Accessible table equivalent of the bar chart above. */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">
                    Topics ranked by no-material count, then failure percentage
                  </caption>
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th scope="col" className="py-2 pr-4 font-medium text-muted-foreground">Topic</th>
                      <th scope="col" className="py-2 pr-4 font-medium text-muted-foreground text-right">Searches</th>
                      <th scope="col" className="py-2 pr-4 font-medium text-muted-foreground text-right">No material</th>
                      <th scope="col" className="py-2 font-medium text-muted-foreground text-right">Failure rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTopics.map((t) => (
                      <tr key={t.topic} className="border-b border-border/50">
                        <td className="py-2 pr-4">
                          <button
                            onClick={() => handleSelectTopic(t.topic)}
                            className="text-foreground hover:text-primary hover:underline cursor-pointer text-left"
                          >
                            {t.topic}
                          </button>
                        </td>
                        <td className="py-2 pr-4 text-right text-foreground">{t.total}</td>
                        <td className="py-2 pr-4 text-right text-foreground">{t.no_material}</td>
                        <td className="py-2 text-right text-foreground">{fmtPercent(t.failure_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
