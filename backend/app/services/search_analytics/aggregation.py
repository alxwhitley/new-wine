"""Dashboard aggregation queries: summary counts and the ranked topic
bar-chart dataset. Both scope to origin='user' only -- an admin retest is
never counted as demand.

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List


def _since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _open_gap_topics(supabase, no_material_rows: List[Dict[str, object]]) -> set:
    """Topics with at least one STILL-OPEN gap among the given no_material
    occurrence rows -- a resolved gap must not count, even though its
    occurrence remains a real historical no_material search. Requires a
    second query because gap status lives on search_gap_details, not on
    search_occurrences itself."""
    occurrence_ids = [r["id"] for r in no_material_rows if r.get("id")]
    if not occurrence_ids:
        return set()
    gap_result = (
        supabase.table("search_gap_details")
        .select("occurrence_id, status")
        .in_("occurrence_id", occurrence_ids)
        .eq("status", "open")
        .execute()
    )
    open_occurrence_ids = {g["occurrence_id"] for g in (gap_result.data or [])}
    return {
        r.get("primary_topic") for r in no_material_rows
        if r.get("id") in open_occurrence_ids and r.get("primary_topic")
    }


def get_summary(supabase, days: int = 30) -> Dict[str, object]:
    since = _since_iso(days)
    result = (
        supabase.table("search_occurrences")
        .select("id, primary_topic, outcome, classification_status")
        .eq("origin", "user")
        .gte("created_at", since)
        .execute()
    )
    rows = result.data or []
    total = len(rows)
    no_material_rows = [r for r in rows if r.get("outcome") == "no_material"]
    no_material = len(no_material_rows)
    unclassified = sum(1 for r in rows if r.get("primary_topic") == "Unclassified")
    pending = sum(1 for r in rows if r.get("classification_status") == "pending")
    open_gap_topics = _open_gap_topics(supabase, no_material_rows)
    return {
        "monitored_searches": total,
        "no_material_count": no_material,
        "missing_content_rate": (no_material / total) if total else 0.0,
        "topics_with_open_gaps": len(open_gap_topics),
        "unclassified_rate": (unclassified / total) if total else 0.0,
        "finalization_pending": pending,
        "finalization_classified": total - pending,
        "window_days": days,
    }


def get_topic_bars(supabase, days: int = 30) -> List[Dict[str, object]]:
    since = _since_iso(days)
    result = (
        supabase.table("search_occurrences")
        .select("primary_topic, outcome")
        .eq("origin", "user")
        .gte("created_at", since)
        .execute()
    )
    rows = result.data or []
    by_topic = {}  # type: Dict[str, Dict[str, int]]
    for r in rows:
        topic = r.get("primary_topic") or "Unclassified"
        bucket = by_topic.setdefault(topic, {"total": 0, "no_material": 0})
        bucket["total"] += 1
        if r.get("outcome") == "no_material":
            bucket["no_material"] += 1

    bars = []
    for topic, counts in by_topic.items():
        total = counts["total"]
        no_material = counts["no_material"]
        bars.append({
            "topic": topic,
            "total": total,
            "no_material": no_material,
            "failure_rate": (no_material / total) if total else 0.0,
        })
    # Rank by no_material count, then failure percentage (directive's rule).
    bars.sort(key=lambda b: (b["no_material"], b["failure_rate"]), reverse=True)
    return bars
