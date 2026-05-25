"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { supabase } from "@/lib/supabase";
import { CARDS, GROUPS } from "./data";
import type { CorpusCard } from "./types";
import CorpusCardComponent from "./CorpusCard";
import CardModal from "./CardModal";

const COLORS = {
  bg: "#1f1e1d",
  surface: "#262624",
  border: "#3c3c38",
  text: "#e6e6e6",
  textSecondary: "#c1c1b8",
  gold: "#b49238",
  citationGold: "#d4b96a",
};

interface CountData {
  [cardId: string]: {
    count: number;
    lastIngested: string | null;
  };
}

interface GlobalStats {
  totalDocuments: number;
  totalChunks: number;
  totalVerses: number;
  totalInterlinearWords: number;
}

export default function CorpusAdminPage() {
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
  const pulseTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map()
  );

  const fetchAllCounts = useCallback(async () => {
    const newCounts: CountData = {};

    // Fetch document-based cards: group by source_kind with counts and max created_at
    const { data: docGroups } = await supabase
      .from("documents")
      .select("source_kind, created_at");

    // Build per-source_kind aggregates
    const kindAgg: Record<string, { count: number; maxDate: string | null }> =
      {};
    if (docGroups) {
      for (const row of docGroups) {
        const sk = row.source_kind as string;
        if (!kindAgg[sk]) kindAgg[sk] = { count: 0, maxDate: null };
        kindAgg[sk].count++;
        if (
          row.created_at &&
          (!kindAgg[sk].maxDate || row.created_at > kindAgg[sk].maxDate!)
        ) {
          kindAgg[sk].maxDate = row.created_at as string;
        }
      }
    }

    // For cards with extraFilter, we need individual queries
    // For cards without extraFilter, use the aggregated data
    const filterPromises: Promise<void>[] = [];

    for (const card of CARDS) {
      if (card.isMaintenance) continue;

      if (card.specialTable) {
        // Special table queries
        filterPromises.push(
          (async () => {
            let query = supabase
              .from(card.specialTable!)
              .select("*", { count: "exact", head: true });
            if (card.specialWhere) {
              const [col, op] = card.specialWhere.split("=");
              const [operator, value] = op.split(".");
              if (operator === "eq") {
                query = query.eq(col, value);
              }
            }
            const { count } = await query;
            newCounts[card.id] = {
              count: count ?? 0,
              lastIngested: null,
            };
          })()
        );
      } else if (card.extraFilter) {
        // Cards with extra filters need individual queries
        filterPromises.push(
          (async () => {
            // Use RPC or direct query with textSearch isn't available,
            // so we fetch matching docs and count client-side
            let query = supabase
              .from("documents")
              .select("created_at", { count: "exact" });
            if (card.sourceKind) {
              query = query.eq("source_kind", card.sourceKind);
            }
            // Apply extra filters
            const parsed = parseFilter(card.extraFilter!);
            for (const cond of parsed.and) {
              query = query.ilike(cond.col, cond.val);
            }
            if (parsed.or.length > 0) {
              query = query.or(
                parsed.or.map((c) => `${c.col}.ilike.${c.val}`).join(",")
              );
            }
            const { data, count } = await query;
            let maxDate: string | null = null;
            if (data) {
              for (const row of data) {
                if (
                  row.created_at &&
                  (!maxDate || row.created_at > maxDate)
                ) {
                  maxDate = row.created_at as string;
                }
              }
            }
            newCounts[card.id] = {
              count: count ?? data?.length ?? 0,
              lastIngested: maxDate,
            };
          })()
        );
      } else if (card.sourceKind) {
        // Simple source_kind match — use pre-aggregated data
        const agg = kindAgg[card.sourceKind];
        newCounts[card.id] = {
          count: agg?.count ?? 0,
          lastIngested: agg?.maxDate ?? null,
        };
      }
    }

    await Promise.all(filterPromises);
    setCounts(newCounts);

    // Global stats
    const [chunksRes, versesRes, interlinearRes] = await Promise.all([
      supabase.from("chunks").select("*", { count: "exact", head: true }),
      supabase.from("verses").select("*", { count: "exact", head: true }),
      supabase
        .from("interlinear_words")
        .select("*", { count: "exact", head: true }),
    ]);

    setGlobalStats({
      totalDocuments: docGroups?.length ?? 0,
      totalChunks: chunksRes.count ?? 0,
      totalVerses: versesRes.count ?? 0,
      totalInterlinearWords: interlinearRes.count ?? 0,
    });

    setLastUpdated(new Date());
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchAllCounts();
  }, [fetchAllCounts]);

  // Supabase Realtime subscription
  useEffect(() => {
    const channel = supabase
      .channel("corpus-admin-realtime")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "documents" },
        (payload) => {
          const sourceKind = payload.new.source_kind as string;

          // Find which card(s) this insert belongs to and pulse them
          for (const card of CARDS) {
            if (card.sourceKind === sourceKind) {
              triggerPulse(card.id);
            }
          }

          // Refetch all counts
          fetchAllCounts();
        }
      )
      .subscribe((status) => {
        setRealtimeConnected(status === "SUBSCRIBED");
      });

    return () => {
      supabase.removeChannel(channel);
    };
  }, [fetchAllCounts]);

  const triggerPulse = (cardId: string) => {
    setPulsingCards((prev) => new Set(prev).add(cardId));

    // Clear existing timer for this card
    const existing = pulseTimers.current.get(cardId);
    if (existing) clearTimeout(existing);

    const timer = setTimeout(() => {
      setPulsingCards((prev) => {
        const next = new Set(prev);
        next.delete(cardId);
        return next;
      });
      pulseTimers.current.delete(cardId);
    }, 5000);

    pulseTimers.current.set(cardId, timer);
  };

  return (
    <div
      className="min-h-screen font-sans"
      style={{ backgroundColor: COLORS.bg, color: COLORS.text }}
    >
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-2">
          <h1 className="text-3xl font-serif font-semibold" style={{ color: COLORS.text }}>
            Corpus Admin
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <p className="text-sm" style={{ color: COLORS.textSecondary }}>
              Live ingestion dashboard &mdash; Supabase Realtime connected
            </p>
            <span
              className={`inline-block h-2 w-2 rounded-full ${realtimeConnected ? "animate-pulse" : ""}`}
              style={{
                backgroundColor: realtimeConnected ? "#22c55e" : "#6b7280",
              }}
            />
          </div>
          {lastUpdated && (
            <p className="text-xs mt-1" style={{ color: COLORS.textSecondary }}>
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>

        {/* Global Stats Bar */}
        <div
          className="flex flex-wrap gap-3 mb-8 mt-4 p-3 rounded-lg"
          style={{
            backgroundColor: COLORS.surface,
            border: `1px solid ${COLORS.border}`,
          }}
        >
          <StatPill label="Total Documents" value={globalStats.totalDocuments} />
          <StatPill label="Total Chunks" value={globalStats.totalChunks} />
          <StatPill label="Total Verses" value={globalStats.totalVerses} />
          <StatPill
            label="Total Interlinear Words"
            value={globalStats.totalInterlinearWords}
          />
        </div>

        {/* Card Groups */}
        {GROUPS.map((group) => {
          const groupCards = CARDS.filter((c) => c.group === group);
          if (groupCards.length === 0) return null;
          const isMaintenance = group === "Maintenance";

          return (
            <div key={group} className="mb-8">
              <h2
                className={`font-serif font-medium mb-3 ${isMaintenance ? "text-sm uppercase tracking-wider" : "text-lg"}`}
                style={{
                  color: isMaintenance ? COLORS.textSecondary : COLORS.text,
                }}
              >
                {group}
              </h2>
              <div
                className={`grid gap-3 ${
                  isMaintenance
                    ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
                    : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
                }`}
              >
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
      </div>

      {/* Modal */}
      {selectedCard && (
        <CardModal
          card={selectedCard}
          count={counts[selectedCard.id]?.count ?? null}
          onClose={() => setSelectedCard(null)}
        />
      )}
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline gap-1.5 px-3 py-1">
      <span
        className="text-lg font-bold"
        style={{ color: "#d4b96a" }}
      >
        {value.toLocaleString()}
      </span>
      <span className="text-xs" style={{ color: "#c1c1b8" }}>
        {label}
      </span>
    </div>
  );
}

interface FilterCondition {
  col: string;
  val: string;
}

/**
 * Parse SQL-like ILIKE filter strings into AND + OR groups.
 * Handles patterns like:
 *   "url ILIKE '%youtube%' AND (author ILIKE '%bevere%' OR source_name ILIKE '%bevere%')"
 *   "author ILIKE '%derek prince%' OR source_name ILIKE '%derek prince%'"
 */
function parseFilter(filter: string): {
  and: FilterCondition[];
  or: FilterCondition[];
} {
  const and: FilterCondition[] = [];
  const or: FilterCondition[] = [];

  // Strip outer parens for grouped OR conditions
  const cleaned = filter.replace(/[()]/g, "");

  // Split on AND first
  const andParts = cleaned.split(/\s+AND\s+/i);

  for (const part of andParts) {
    // Check if this part contains OR
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
