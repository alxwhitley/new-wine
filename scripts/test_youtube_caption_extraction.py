#!/usr/bin/env python3.12
"""
test_youtube_caption_extraction.py — regression tests for the json3 caption
path in youtube_ingest.py (built 2026-08-29).

Why this exists: the previous path asked yt-dlp for `--convert-subs srt`,
which flattens YouTube's rolling-window cue format into literally triplicated
text. A Groq "cleaning" model was then relied on to undo that — and instead
discarded ~62% of real sermon content, silently, across 49 live documents.
Nothing in the pipeline noticed, because nothing compared what was stored
against what the source actually contained.

These tests lock in the two properties whose absence caused that:
  1. json3 extraction is complete and duplication-free.
  2. A caption track that stops early is REJECTED, not stored short.

Tier A is deterministic and offline (no network, no cost).
Tier B makes real yt-dlp fetches — network only: no LLM calls, no database
access, no cost.

Usage:
    python3.12 scripts/test_youtube_caption_extraction.py           # Tier A + B
    python3.12 scripts/test_youtube_caption_extraction.py --offline # Tier A only
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_ingest as yi  # noqa: E402

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print("  OK: {}".format(label))
    else:
        print("  FAIL: {}{}".format(label, "  -- " + detail if detail else ""))
        FAILURES.append(label)


def immediate_repeats(text, span=5):
    """Count positions where a `span`-word window repeats immediately after
    itself — the signature of SRT rolling-window triplication."""
    w = text.split()
    return sum(1 for i in range(len(w) - 2 * span)
               if w[i:i + span] == w[i + span:i + 2 * span])


def write_json3(path, events):
    Path(path).write_text(json.dumps({"wireMagic": "pb3", "events": events}),
                          encoding="utf-8")


def body(n_words, start_ms, dur_ms=2000):
    """A text-bearing event carrying n_words distinct words."""
    words = ["w{}x{}".format(start_ms, i) for i in range(n_words)]
    return {"tStartMs": start_ms, "dDurationMs": dur_ms,
            "segs": [{"utf8": " ".join(words)}]}


def sep(start_ms):
    """The aAppend newline separator YouTube emits between rolling cues."""
    return {"tStartMs": start_ms, "dDurationMs": 10, "aAppend": 1,
            "segs": [{"utf8": "\n"}]}


print("=" * 74)
print("Tier A — deterministic, offline")
print("=" * 74)

# ── A1: aAppend '\n' events must be INCLUDED, or words glue together ─────────
print("\n-- A1: aAppend separators preserve word boundaries --")
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "a.json3"
    write_json3(p, [
        {"tStartMs": 0, "dDurationMs": 9000, "id": 1},  # window event, no segs
        {"tStartMs": 0, "dDurationMs": 2000,
         "segs": [{"utf8": "All"}, {"utf8": " right."}, {"utf8": " Hello"},
                  {"utf8": " everybody."}]},
        sep(2000),
        {"tStartMs": 2010, "dDurationMs": 2000,
         "segs": [{"utf8": "Well,"}, {"utf8": " I'm"}, {"utf8": " excited."}]},
    ])
    text, last_end, max_gap = yi._parse_json3(p)
    check("all 7 words recovered, none glued", len(text.split()) == 7,
          "got {} words: {!r}".format(len(text.split()), text))
    check("no 'everybody.Well,' glue artifact", "everybody.Well" not in text, text)
    # MUTATION NOTE: dropping aAppend events yields "everybody.Well," -> 6 words.

# ── A2: non-speech markers stripped ─────────────────────────────────────────
print("\n-- A2: bracketed non-speech markers removed --")
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "b.json3"
    write_json3(p, [
        {"tStartMs": 0, "dDurationMs": 2000,
         "segs": [{"utf8": "Praise"}, {"utf8": " him."}, {"utf8": " [music]"},
                  {"utf8": " [applause]"}, {"utf8": " Amen."}]},
    ])
    text, _, _ = yi._parse_json3(p)
    check("markers gone", "[music]" not in text and "[applause]" not in text, text)
    check("real speech kept", "Praise him." in text and "Amen." in text, text)

# ── A3: coverage + gap arithmetic ───────────────────────────────────────────
print("\n-- A3: coverage and gap math --")
with tempfile.TemporaryDirectory() as td:
    p = Path(td) / "c.json3"
    write_json3(p, [body(5, 0, 2000), sep(2000), body(5, 60_000, 3000)])
    text, last_end, max_gap = yi._parse_json3(p)
    check("last_end is end of final event", last_end == 63_000, str(last_end))
    check("largest gap measured (~58s)", 57_000 <= max_gap <= 59_000, str(max_gap))

# ── A4/A5: the truncation guardrail itself ──────────────────────────────────
print("\n-- A4/A5: truncated caption track is rejected, complete one accepted --")


class FakeRun:
    """Stands in for the yt-dlp subprocess call: reports a 1000s video and
    writes nothing (the test pre-writes the json3 itself)."""

    def __init__(self, duration_s=1000):
        self.stdout = "{}\n".format(duration_s)
        self.stderr = ""
        self.returncode = 0


def run_with_fixture(events, duration_s=1000):
    real_run = yi.subprocess.run
    yi.subprocess.run = lambda *a, **k: FakeRun(duration_s)
    try:
        td = tempfile.mkdtemp()
        write_json3(Path(td) / "vid.en.json3", events)
        return yi.try_auto_captions("/fake/yt-dlp", "https://x", td)
    finally:
        yi.subprocess.run = real_run


# 150 words spread across the FULL 1000s video -> should be accepted
full = []
for i in range(30):
    full.append(body(5, i * 33_000, 2000))
    full.append(sep(i * 33_000 + 2000))
accepted = run_with_fixture(full, duration_s=1000)
check("complete track accepted", accepted is not None and len(accepted.split()) >= 100,
      "returned {}".format(None if accepted is None else len(accepted.split())))

# Same 150 words, but the track stops at ~150s of a 1000s video (15%)
truncated = []
for i in range(30):
    truncated.append(body(5, i * 5_000, 2000))
    truncated.append(sep(i * 5_000 + 2000))
rejected = run_with_fixture(truncated, duration_s=1000)
check("truncated track REJECTED (falls back to Whisper)", rejected is None,
      "returned {} words instead of None".format(
          None if rejected is None else len(rejected.split())))
# MUTATION NOTE: this is the check whose absence let 38%-length transcripts
# reach production. Raise _MIN_CAPTION_COVERAGE above 0 and delete the
# coverage branch in try_auto_captions() and this assertion fails.

# ── A6: too-short transcripts still rejected ────────────────────────────────
print("\n-- A6: sub-100-word transcript rejected --")
short = run_with_fixture([body(20, 0, 2000), sep(2000)], duration_s=10)
check("short transcript rejected", short is None,
      "returned {}".format(None if short is None else len(short.split())))

if "--offline" in sys.argv:
    print("\n" + "=" * 74)
    print("Tier A complete ({} failure(s)). Tier B skipped (--offline).".format(
        len(FAILURES)))
    sys.exit(1 if FAILURES else 0)

print("\n" + "=" * 74)
print("Tier B — live yt-dlp fetches (network only: no LLM, no DB, no cost)")
print("=" * 74)

LIVE = [
    # (video_id, label, min_words, max_words)
    ("ESWQX5AblJ0", "CLF / Alex Whitley, 46.9 min", 8_400, 10_400),
    ("KEBB2SXWqcU", "Vlad Savchuk, 16.1 min", 2_300, 3_200),
]

ytdlp = yi.find_ytdlp()
if not ytdlp:
    print("  SKIP: yt-dlp not found")
else:
    for vid, label, lo, hi in LIVE:
        print("\n-- {} [{}] --".format(label, vid))
        with tempfile.TemporaryDirectory() as td:
            text = yi.try_auto_captions(
                ytdlp, "https://www.youtube.com/watch?v={}".format(vid), td)
        if text is None:
            check("captions returned", False, "got None")
            continue
        n = len(text.split())
        reps = immediate_repeats(text)
        print("     {:,} words, {} immediate 5-word repeats".format(n, reps))
        check("word count in expected range ({:,}-{:,})".format(lo, hi),
              lo <= n <= hi, "got {:,}".format(n))
        check("no rolling-window duplication", reps <= 5, "got {} repeats".format(reps))
        # MUTATION NOTE: restoring --convert-subs srt makes word count ~3x the
        # upper bound and repeats jump into the hundreds.

print("\n" + "=" * 74)
if FAILURES:
    print("{} FAILURE(S): {}".format(len(FAILURES), FAILURES))
    sys.exit(1)
print("All assertions passed (Tier A + Tier B).")
print("=" * 74)
