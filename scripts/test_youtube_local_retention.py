#!/usr/bin/env python3.12
"""
test_youtube_local_retention.py — regression tests for local transcript
retention in youtube_ingest.py (built 2026-08-30).

Why this exists: ingest_video() wrote its transcript to sources/youtube/
cleaned/, ingested from it, then unlinked it in a `finally` block. That was
deliberate -- the file was treated as scratch -- but it means a stored
document exists ONLY in Supabase. Measured 2026-08-30: 357 of 374 YouTube
documents had no local copy, across Savchuk (126), Ravenhill (117), CLF (56),
Poonen (50), Conlon (6), Deere (1) and Brown (1). The local archive had not
been written to since 2026-06-03 and nothing anywhere noticed, because
nothing ever asserted that a successful ingest leaves a file behind.

These tests lock in the properties whose absence caused that:
  1. A SUCCESSFUL ingest leaves the transcript in ingested/ and not in
     cleaned/.
  2. The retained bytes are exactly what was handed to ingest_file() -- the
     local copy is the artifact that was ingested, not a re-derivation.
  3. A FAILED ingest retains nothing, so ingested/ keeps meaning "this is in
     the corpus".
  4. Re-ingesting the same video overwrites its file rather than accumulating
     variants.
  5. A retention failure is surfaced in the returned reason, never swallowed,
     but never invalidates a database write that already succeeded.

MUTATION NOTE: restoring the old unconditional `tmp_path.unlink(missing_ok=
True)` fails tests 1, 2 and 4. Retaining on failure too fails test 3.

Fully offline -- every network and database call is stubbed. No LLM calls, no
yt-dlp, no Supabase, no cost.

Usage:
    python3.12 scripts/test_youtube_local_retention.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import youtube_ingest as yi  # noqa: E402

FAILURES = []
TRANSCRIPT = "this is the stored sermon text " * 40
FAKE_SOURCE_ID = "11111111-2222-3333-4444-555555555555"
URL = "https://www.youtube.com/watch?v=TESTvid1234"
TITLE = "A Real Sermon Title | Some Speaker"


def check(label, cond, detail=""):
    if cond:
        print("  OK: {}".format(label))
    else:
        print("  FAIL: {}{}".format(label, "  -- " + detail if detail else ""))
        FAILURES.append(label)


class Harness:
    """Redirects both transcript dirs into a tmpdir and stubs every external call."""

    def __init__(self, ingest_result=("processed", "ok"), ingest_raises=False):
        self.ingest_result = ingest_result
        self.ingest_raises = ingest_raises
        self.seen_path = None      # the path ingest_file() was handed
        self.seen_bytes = None     # its content at that moment

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.cleaned = root / "cleaned"
        self.ingested = root / "ingested"
        self.cleaned.mkdir()
        # deliberately NOT pre-created -- the code must mkdir it itself
        self._saved = {
            "CLEANED_DIR": yi.CLEANED_DIR,
            "INGESTED_DIR": yi.INGESTED_DIR,
            "ingest_file": yi.ingest_file,
            "try_auto_captions": yi.try_auto_captions,
            "_resolve_speaker_source": yi._resolve_speaker_source,
            "_get_source_display_name": yi._get_source_display_name,
        }
        yi.CLEANED_DIR = self.cleaned
        yi.INGESTED_DIR = self.ingested
        yi.try_auto_captions = lambda *a, **k: TRANSCRIPT
        yi._resolve_speaker_source = lambda *a, **k: FAKE_SOURCE_ID
        yi._get_source_display_name = lambda *a, **k: "Test Source"

        def fake_ingest_file(path, **kwargs):
            self.seen_path = Path(path)
            self.seen_bytes = Path(path).read_bytes()
            if self.ingest_raises:
                raise RuntimeError("simulated ingest explosion")
            return self.ingest_result

        yi.ingest_file = fake_ingest_file
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            setattr(yi, k, v)
        self._tmp.cleanup()
        return False

    def run(self):
        return yi.ingest_video("yt-dlp", URL, TITLE, "Test Channel", dry_run=False)

    def ingested_files(self):
        return sorted(p.name for p in self.ingested.glob("*.txt")) \
            if self.ingested.exists() else []

    def cleaned_files(self):
        return sorted(p.name for p in self.cleaned.glob("*.txt"))


print("=" * 74)
print("Local transcript retention — youtube_ingest.ingest_video()")
print("=" * 74)

# ── 1. Successful ingest retains the file ────────────────────────────────────
print("\n[1] a successful ingest leaves the transcript in ingested/")
with Harness() as h:
    status, display, reason = h.run()
    check("status is done", status == "done", "got {!r} ({})".format(status, reason))
    check("exactly one file retained in ingested/",
          len(h.ingested_files()) == 1, "got {}".format(h.ingested_files()))
    check("nothing left behind in cleaned/",
          h.cleaned_files() == [], "got {}".format(h.cleaned_files()))
    check("filename is video-id prefixed",
          h.ingested_files() and h.ingested_files()[0].startswith("TESTvid1234_"),
          "got {}".format(h.ingested_files()))
    check("ingested/ was created by the code, not the test",
          h.ingested.exists())

# ── 2. Retained bytes are exactly what was ingested ──────────────────────────
print("\n[2] the retained file is byte-identical to what ingest_file() received")
with Harness() as h:
    h.run()
    retained = h.ingested / h.ingested_files()[0]
    check("retained bytes == bytes handed to ingest_file",
          retained.read_bytes() == h.seen_bytes)
    body = retained.read_text()
    check("transcript body present verbatim", TRANSCRIPT.strip() in body)
    check("metadata header present", "URL:" in body and "SPEAKER:" in body)

# ── 3. A failed ingest retains nothing ───────────────────────────────────────
print("\n[3] a FAILED ingest retains nothing (ingested/ means 'in the corpus')")
with Harness(ingest_result=("error", "db exploded")) as h:
    status, _, reason = h.run()
    check("status is failed", status == "failed", "got {!r}".format(status))
    check("nothing retained in ingested/",
          h.ingested_files() == [], "got {}".format(h.ingested_files()))
    check("nothing left in cleaned/ either",
          h.cleaned_files() == [], "got {}".format(h.cleaned_files()))

print("\n[3b] an ingest that RAISES also retains nothing")
with Harness(ingest_raises=True) as h:
    status, _, reason = h.run()
    check("status is failed", status == "failed", "got {!r}".format(status))
    check("nothing retained", h.ingested_files() == [], "got {}".format(h.ingested_files()))
    check("exception surfaced in reason", "simulated ingest explosion" in reason)

# ── 4. Re-ingest overwrites rather than accumulating ─────────────────────────
print("\n[4] re-ingesting the same video overwrites its file")
with Harness() as h:
    h.run()
    first = h.ingested_files()
    h.run()
    check("still exactly one file after a second run",
          h.ingested_files() == first and len(first) == 1,
          "got {}".format(h.ingested_files()))

# ── 5. Retention failure is reported, not swallowed ──────────────────────────
print("\n[5] a retention failure is surfaced but does not undo a successful write")
with Harness() as h:
    # Make the move impossible: put a DIRECTORY where the file needs to land.
    h.ingested.mkdir(parents=True, exist_ok=True)
    vid = yi.extract_video_id(URL)
    blocker = h.ingested / "{}_{}.txt".format(vid, yi._slugify(TITLE))
    blocker.mkdir(parents=True, exist_ok=True)
    (blocker / "occupied").write_text("x")   # non-empty dir cannot be replaced
    status, _, reason = h.run()
    check("status still done (the DB write really happened)",
          status == "done", "got {!r}".format(status))
    check("reason reports the retention failure",
          "RETAIN FAILED" in reason, "got {!r}".format(reason))

print("\n" + "=" * 74)
if FAILURES:
    print("{} FAILURE(S): {}".format(len(FAILURES), FAILURES))
    sys.exit(1)
print("All assertions passed.")
print("=" * 74)
