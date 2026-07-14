#!/usr/bin/env python3
"""
Lexicon slice-runner — the batching/pacing layer PLAN #12's conversion
(33e92b4) deliberately left out of the writer: "the future full-batch
runner's job, not the writer's" (rhemata-status.md). Drives the already-
converted scripts/ingest_lexicon.py through shared_ingest.ingest_document()
in small, checkpointed slices instead of one call per whole file.

Deliberately does NOT modify ingest_lexicon.py or shared_ingest.py. All new
complexity (slicing, retry/backoff, failure isolation, a persistent skip
list) lives here, in the runner, per the pacing decision surfaced during
#12's own scoping. This script imports ingest_lexicon's pure helpers
(parse_file / format_chunk_content / truncate_for_embedding) and calls
shared_ingest.ingest_document() directly rather than ingest_lexicon.
ingest_file(), because the failure policy needs to permanently exclude one
bad entry from the middle of a file's entry list -- ingest_file()'s own
max_entries is a cumulative-PREFIX cap only (grow or shrink the boundary),
with no hook to cut a single entry out of the middle. Everything else
(title-keyed lookup, one-entry-one-chunk formatting, the reuse/append
mechanism itself) is reused as-is.

SLICING: entries are grown in bounded slices (--slice-size, default 75,
matching backend/app/services/embeddings.py's EMBED_BATCH_SIZE=100 so a
normal slice is at most one embedding API call). The writer's own
reuse/append mechanism (1ec5226) makes this resumable for free: re-running
picks up from whatever's actually stored (MAX(chunk_index)+1), not from
any state this runner keeps.

FAILURE POLICY: on a slice failing, retry the SAME target a few times with
a brief backoff. If it still fails, bisect the remaining span in half and
retry each half -- recursing down to a single entry if necessary. A single
entry that still fails at that point is the genuine culprit: it's logged
(Strong's code + reason) to a persistent skip list
(logs/lexicon_slice_runner_skips.json), permanently excluded from every
subsequent attempt (this run and any future resumed run), and the runner
continues past it. The whole run is never halted by one bad entry.

Usage:
    # Proof run against a throwaway test title (does not touch real production docs)
    python3 scripts/ingest_lexicon_runner.py --lexicon TBESG --limit 250 \\
        --test-title-suffix " — RUNNER PROOF (test, delete before session close)"

    # Resumability check: run the identical command again
    python3 scripts/ingest_lexicon_runner.py --lexicon TBESG --limit 250 \\
        --test-title-suffix " — RUNNER PROOF (test, delete before session close)"

    # Failure-policy check: force entry at position 40 (0-based) to fail
    python3 scripts/ingest_lexicon_runner.py --lexicon TBESG --limit 250 \\
        --test-title-suffix " — RUNNER PROOF (test, delete before session close)" \\
        --simulate-failure-at 40

    # Full real run (NOT executed this session -- separate, deliberate launch)
    python3 scripts/ingest_lexicon_runner.py
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import ingest_lexicon  # noqa: E402 -- provides parse_file/format_chunk_content/
                        # truncate_for_embedding/_find_existing_by_title/supabase/
                        # DB_PARAMS/LEXICON_DIR/FILE_CONFIGS. Untouched by this script.
import shared_ingest    # noqa: E402

# ── Config ────────────────────────────────────────────────────────────────────

RETRIES = 3
BACKOFF_SECONDS = (2, 5, 10)  # brief pause per attempt, per Alex's failure policy

LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
SKIP_LOG_PATH = LOG_DIR / "lexicon_slice_runner_skips.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "lexicon_slice_runner.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

LEXICON_MAP = {
    "TBESG": [ingest_lexicon.FILE_CONFIGS[0]],
    "TBESH": [ingest_lexicon.FILE_CONFIGS[1]],
    "TFLSJ": [ingest_lexicon.FILE_CONFIGS[2], ingest_lexicon.FILE_CONFIGS[3]],
}


# ── Persistent skip list ──────────────────────────────────────────────────────

class SkipLog:
    """Durable record of permanently-excluded entries, keyed by document
    title. Read at start so a resumed run never re-attempts an entry
    already proven bad; written immediately on every new skip so a crash
    mid-run doesn't lose the record."""

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, List[dict]] = (
            json.loads(path.read_text()) if path.exists() else {}
        )

    def get_set(self, title: str) -> Set[str]:
        return {item["strongs"] for item in self.data.get(title, [])}

    def add(self, title: str, strongs: str, reason: str) -> None:
        self.data.setdefault(title, []).append({
            "strongs": strongs,
            "reason": reason,
            "logged_at": datetime.now(timezone.utc).isoformat(),
        })
        self.path.write_text(json.dumps(self.data, indent=2))

    def remove_title(self, title: str) -> None:
        """Cleanup hook for throwaway test titles -- drop their skip
        records entirely once the test document itself is deleted."""
        if title in self.data:
            del self.data[title]
            self.path.write_text(json.dumps(self.data, indent=2))


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_effective_entries(filename: str, skip_set: Set[str]) -> List[dict]:
    """Real, freshly-parsed entries for `filename`, minus anything already
    on the permanent skip list. Cheap enough (pure in-memory parse of a few
    MB, well under a second) to recompute on demand rather than cache --
    the skip set is the only mutable state; entries are always derived
    fresh from it."""
    filepath = ingest_lexicon.LEXICON_DIR / filename
    entries = ingest_lexicon.parse_file(filepath)
    if skip_set:
        entries = [e for e in entries if e["strongs"] not in skip_set]
    return entries


def get_stored_count(title: str) -> int:
    """Ground truth from the DB, not runner-side bookkeeping -- matches
    Alex's own "verify by direct DB recomputation, not self-report" bar."""
    doc_id = ingest_lexicon._find_existing_by_title(title)
    if doc_id is None:
        return 0
    result = (
        ingest_lexicon.supabase.table("chunks")
        .select("id", count="exact")
        .eq("document_id", doc_id)
        .execute()
    )
    return result.count or 0


def slice_ingest(
    filename: str,
    title: str,
    entries: List[dict],
    brief: bool,
    simulate_failure_strongs: Optional[str] = None,
) -> dict:
    """One call through the shared writer for a bounded prefix of entries.
    Mirrors ingest_lexicon.ingest_file()'s own logic (one-entry-one-chunk
    via a chunk_fn override, on_existing="reuse" so only the new tail is
    embedded) -- the only difference is `entries` here is the runner's
    already skip-filtered, already-sliced list, not a fresh whole-file
    parse. `on_existing` is always "reuse": the runner never deletes or
    redoes a real document -- that's a separate, deliberate operator
    choice, not something a batch runner does on its own.
    """
    if simulate_failure_strongs is not None and any(
        e["strongs"] == simulate_failure_strongs for e in entries
    ):
        raise RuntimeError(
            f"SIMULATED FAILURE (test-injected via --simulate-failure-at): "
            f"entry {simulate_failure_strongs}"
        )

    chunk_texts = [
        ingest_lexicon.truncate_for_embedding(
            ingest_lexicon.format_chunk_content(e, brief=brief)
        )
        for e in entries
    ]
    full_text = "\n\n".join(chunk_texts)

    def _chunk_fn(_body_text: str) -> List[str]:
        return chunk_texts

    existing_id = ingest_lexicon._find_existing_by_title(title)

    result = shared_ingest.ingest_document(
        db=ingest_lexicon.supabase,
        db_params=ingest_lexicon.DB_PARAMS,
        title=title,
        body_text=full_text,
        filename=filename,
        author="STEPBible / Tyndale House",
        source_name="STEPBible",
        source_type="background",
        source_kind="lexicon",
        citation_mode="silent_context",
        is_copyrighted=False,
        topic_tags=[],
        bible_references=[],
        skip_dedup=True,
        find_existing_fn=lambda: existing_id,
        on_existing="reuse",
        chunk_fn=_chunk_fn,
    )
    if result["status"] == "failed":
        raise RuntimeError(f"writer reported failed: {result.get('reason')}")
    return result


def advance_with_retry(
    filename: str,
    title: str,
    skip_set: Set[str],
    skip_log: SkipLog,
    brief: bool,
    target_count: int,
    simulate_failure_strongs: Optional[str] = None,
    collected_skips: Optional[List[str]] = None,
) -> dict:
    """Try to grow `title`'s stored chunk count up to target_count (a
    position within the CURRENT skip-filtered entries list). Retries the
    same target a few times with backoff (handles the realistic failure
    mode: a transient network/rate-limit blip on the embedding call, which
    fails the whole in-flight batch regardless of content). If it still
    fails, bisects the remaining span and recurses -- down to a single
    entry if necessary, which is then permanently skipped, logged, and the
    caller's loop continues past it.

    `collected_skips` is a list threaded through the whole recursion tree
    (not just the return value) so a skip discovered in an early bisected
    branch is still visible to the top-level caller -- only the LAST
    recursive call's return value ever propagates up normally, which would
    silently drop a skip that happened in an earlier branch.
    """
    if collected_skips is None:
        collected_skips = []
    entries = get_effective_entries(filename, skip_set)
    last_exc: Optional[Exception] = None

    for attempt in range(1, RETRIES + 1):
        try:
            return slice_ingest(
                filename, title, entries[:target_count], brief,
                simulate_failure_strongs=simulate_failure_strongs,
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any
            # failure here (network, rate limit, the simulated test
            # failure, a genuine writer error) is handled identically by
            # the retry-then-bisect policy.
            last_exc = exc
            logger.warning(
                "  [%s] attempt %d/%d failed advancing to %d: %s",
                title, attempt, RETRIES, target_count, exc,
            )
            if attempt < RETRIES:
                time.sleep(BACKOFF_SECONDS[attempt - 1])

    current = get_stored_count(title)
    span = target_count - current
    if span <= 0:
        return {"status": "no_progress_needed"}
    if span == 1:
        bad_entry = entries[current]
        reason = f"{type(last_exc).__name__}: {last_exc}"
        logger.error(
            "  [%s] SKIPPING entry %s (%r) after %d failed attempts — %s",
            title, bad_entry["strongs"], bad_entry.get("gloss", "")[:60], RETRIES, reason,
        )
        skip_log.add(title, bad_entry["strongs"], reason)
        skip_set.add(bad_entry["strongs"])
        collected_skips.append(bad_entry["strongs"])
        return {"status": "entry_skipped", "strongs": bad_entry["strongs"], "reason": reason}

    mid = current + span // 2
    advance_with_retry(
        filename, title, skip_set, skip_log, brief, mid,
        simulate_failure_strongs, collected_skips,
    )
    return advance_with_retry(
        filename, title, skip_set, skip_log, brief, target_count,
        simulate_failure_strongs, collected_skips,
    )


def run_file(
    filename: str,
    title: str,
    brief: bool,
    slice_size: int,
    skip_log: SkipLog,
    limit: Optional[int] = None,
    simulate_failure_at: Optional[int] = None,
) -> dict:
    """Walk one file from its current stored count up to `limit` (or the
    full file), in slice_size-entry checkpoints. Every slice is a single
    call through the writer, so every slice IS a checkpoint -- there is no
    separate checkpoint bookkeeping to get wrong."""
    skip_set = skip_log.get_set(title)

    simulate_strongs = None
    if simulate_failure_at is not None:
        probe = get_effective_entries(filename, skip_set)
        if simulate_failure_at < len(probe):
            simulate_strongs = probe[simulate_failure_at]["strongs"]
            logger.info(
                "  [%s] TEST: will force entry %s (position %d) to fail",
                title, simulate_strongs, simulate_failure_at,
            )

    entries_all = get_effective_entries(filename, skip_set)
    total = len(entries_all) if limit is None else min(limit, len(entries_all))
    current = get_stored_count(title)
    logger.info(
        "[%s] stored=%d of target_total=%d (file has %d entries available%s)",
        title, current, total, len(entries_all),
        f", capped at --limit {limit}" if limit is not None else "",
    )

    entries_skipped: List[str] = []
    while current < total:
        target = min(current + slice_size, total)
        logger.info("[%s] advancing %d -> %d (+%d)", title, current, target, target - current)
        # entries_skipped is threaded through the whole (possibly bisected)
        # recursion tree for this slice -- see advance_with_retry's own
        # docstring for why the return value alone isn't enough.
        advance_with_retry(
            filename, title, skip_set, skip_log, brief, target, simulate_strongs, entries_skipped
        )
        current = get_stored_count(title)
        # Recompute total against the (possibly now-smaller) skip-filtered
        # entries list -- a skip shortens the file by one, which can move
        # the finish line.
        entries_all = get_effective_entries(filename, skip_set)
        total = len(entries_all) if limit is None else min(limit, len(entries_all))
        logger.info("[%s] slice done — stored now %d/%d", title, current, total)

    return {"title": title, "stored": current, "target_total": total, "skipped": entries_skipped}


# ── Main ──────────────────────────────────────────────────────────────────────

def print_summary(results: List[dict], skip_log: SkipLog) -> None:
    print(f"\n{'='*72}")
    print("LEXICON SLICE-RUNNER SUMMARY")
    print(f"{'='*72}")
    W = 46
    print(f"  {'TITLE':<{W}} STORED   TARGET   SKIPPED")
    print(f"  {'-'*(W+30)}")
    for r in results:
        print(f"  {r['title'][:W]:<{W}} {r['stored']:<8} {r['target_total']:<8} {len(r['skipped'])}")
    total_skipped = sum(len(r["skipped"]) for r in results)
    if total_skipped:
        print(f"\n  Skipped entries this run ({total_skipped}) — see {SKIP_LOG_PATH.name} for full history:")
        for r in results:
            for strongs in r["skipped"]:
                reason = next(
                    (i["reason"] for i in reversed(skip_log.data.get(r["title"], []))
                     if i["strongs"] == strongs),
                    "?",
                )
                print(f"    {r['title']}: {strongs} — {reason}")
    print(f"{'='*72}\n")


def main():
    parser = argparse.ArgumentParser(description="Lexicon slice-runner (PLAN #12 batch-scale companion)")
    parser.add_argument("--lexicon", type=str, default=None,
                        help="Run a single lexicon: TBESG, TBESH, or TFLSJ (default: all four files)")
    parser.add_argument("--slice-size", type=int, default=75,
                        help="Entries per checkpointed slice (default 75; Alex's confirmed range is 50-100)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap total entries processed per file (for bounded proof runs)")
    parser.add_argument("--test-title-suffix", type=str, default=None,
                        help="Append this suffix to every file's title, writing to a throwaway "
                             "test document instead of the real production one. Use for any proof "
                             "run -- never omit this against a real title unless deliberately "
                             "launching the real batch.")
    parser.add_argument("--simulate-failure-at", type=int, default=None,
                        help="TEST ONLY: force the entry at this 0-based position (within the "
                             "skip-filtered entries list) to fail, to exercise the failure policy.")
    args = parser.parse_args()

    configs = LEXICON_MAP[args.lexicon.upper()] if args.lexicon else ingest_lexicon.FILE_CONFIGS
    if args.lexicon and args.lexicon.upper() not in LEXICON_MAP:
        print(f"Unknown lexicon: {args.lexicon}. Choose from: {', '.join(LEXICON_MAP.keys())}")
        sys.exit(1)

    skip_log = SkipLog(SKIP_LOG_PATH)

    logger.info("Lexicon slice-runner starting — %d file(s), slice_size=%d, limit=%s, test_suffix=%r",
                len(configs), args.slice_size, args.limit, args.test_title_suffix)

    results = []
    for filename, title in configs:
        brief = "TBESG" in title
        effective_title = title + (args.test_title_suffix or "")
        result = run_file(
            filename, effective_title, brief, args.slice_size, skip_log,
            limit=args.limit, simulate_failure_at=args.simulate_failure_at,
        )
        results.append(result)

    print_summary(results, skip_log)


if __name__ == "__main__":
    main()
