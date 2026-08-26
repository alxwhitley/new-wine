#!/usr/bin/env python3
"""review_discovery_candidates.py -- minimal one-candidate-at-a-time local
review tool for the Discovery data in
docs/ingestion/master_ingestion_queue_discovery.tsv.

Alex's explicit requirement (2026-08-25): find links to blogs/material,
review them, approve them for ingestion -- nothing else. So this page shows
exactly two things per candidate: their name, and a link to their site.
Two buttons, no forms:
  Yes -- approved for ingestion. Writes a new row to the Approved Sites file
         automatically (name, attribute_to, blog_url, approved=TRUE,
         approved_at) -- nothing to type. If that name already has an
         Approved Sites row, no duplicate is written, but this Discovery
         row is still marked reviewed.
  No  -- passed on, permanently. Never shown again.
Both actions mark the Discovery row (verification_status, reviewed_at,
review_notes) and immediately show the next unreviewed candidate. There is
no session/queue state anywhere -- every page load re-reads the Discovery
file fresh and shows the first row that still qualifies, so nothing is lost
if the tool is restarted mid-review and a Yes/No can never apply to a stale
row.

A candidate qualifies if: verification_status == "unverified", it is not
already_in_corpus, claimed_written_content_exists is not False,
auto_link_check is not "no_blog_detected" (see
check_discovery_blog_links.py -- a separate one-shot script that actually
fetches each candidate's link and checks for real post-shaped content
before you ever see it here; run it first so this tool only shows
candidates that already look like real blogs), and it has at least one
claimed URL to show (claimed_blog_or_articles_url, else claimed_main_url,
else the first of other_urls).

Local-only (127.0.0.1), single-user, no auth -- same trust posture as every
other script in scripts/. Reads and writes
docs/ingestion/master_ingestion_queue_discovery.tsv and
_approved_sites.tsv directly (see ingestion_sheet_io.py); no database
involved, and the Queue file / sync_master_ingestion_queue.py /
site_ingest_crawler.py are untouched by this tool.

2026-08-26 conversion note: this tool used to refuse to start or write
while Excel's own `~$master_ingestion_queue.xlsx` lock file existed --
plain .tsv files carry no equivalent lock marker, so that check is gone,
not silently left as dead code. In its place, every write re-checks each
target file's mtime immediately before writing and refuses (RuntimeError)
if it changed since this action's read -- protects against clobbering a
concurrent edit (another instance of this tool, check_discovery_blog_links.py,
or a hand edit in a text editor) the same way the old lock check did,
without depending on Excel specifically.

Run: python3.12 scripts/review_discovery_candidates.py [--port 8765]
Opens your browser automatically.

Python 3.12 (Invariant 1).
"""
from __future__ import annotations

import argparse
import html
import sys
import threading
import webbrowser
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingestion_sheet_io as sheet_io  # noqa: E402

DISCOVERY_TAB = "Discovery"
APPROVED_TAB = "Approved Sites"
DISCOVERY_PATH = sheet_io.TAB_FILES[DISCOVERY_TAB]
APPROVED_PATH = sheet_io.TAB_FILES[APPROVED_TAB]

app = FastAPI()


class StaleFileError(RuntimeError):
    """Raised when a target file changed on disk between being read and
    being written back -- see the module docstring's 2026-08-26 note."""


def _refuse_if_changed(path: Path, expected_mtime: float) -> None:
    if path.exists() and path.stat().st_mtime != expected_mtime:
        raise StaleFileError(
            f"'{path.name}' changed on disk while this action was in progress "
            "-- reload the page and try again so nothing gets silently overwritten."
        )


# ---------------------------------------------------------------------------
# Pure read logic -- no network, no write, safe to unit-test directly.
# ---------------------------------------------------------------------------
def _candidate_link(row: dict) -> Optional[str]:
    for key in ("claimed_blog_or_articles_url", "claimed_main_url"):
        value = row.get(key)
        if value and str(value).strip():
            return str(value).strip()
    other = row.get("other_urls")
    if other:
        first = str(other).split(";")[0].strip()
        if first:
            return first
    return None


def load_discovery_rows() -> List[dict]:
    _headers, rows = sheet_io.read_tab(DISCOVERY_PATH)
    return [row for row in rows if row.get("name")]


def build_queue(rows: List[dict]) -> List[Tuple[dict, str]]:
    """The rows still worth showing Alex, in sheet order, each paired with
    the one link to display. Excludes: already decided, already in corpus,
    confirmed to have no written content, or nothing to click at all."""
    queue = []
    for row in rows:
        if str(row.get("verification_status") or "").strip().lower() != "unverified":
            continue
        if sheet_io.parse_bool_cell(row.get("already_in_corpus")) is True:
            continue
        if sheet_io.parse_bool_cell(row.get("claimed_written_content_exists")) is False:
            continue
        if str(row.get("auto_link_check") or "").strip().lower() == "no_blog_detected":
            continue
        link = _candidate_link(row)
        if not link:
            continue
        queue.append((row, link))
    return queue


def next_candidate() -> Optional[Tuple[dict, str, int]]:
    """(row, link, remaining_count) for the first still-eligible Discovery
    row, or None if there's nothing left to review."""
    queue = build_queue(load_discovery_rows())
    if not queue:
        return None
    row, link = queue[0]
    return row, link, len(queue)


# ---------------------------------------------------------------------------
# Write logic. Operates on (headers, rows) pairs from ingestion_sheet_io --
# see StaleFileError / _refuse_if_changed above for the write-time guard
# that replaced the old Excel lock-file check.
# ---------------------------------------------------------------------------
def _ensure_columns(headers: List[str], rows: List[dict], *columns: str) -> List[str]:
    """Adds any of `columns` missing from `headers` and backfills every row
    with None for it -- self-healing, matching the old worksheet-based
    behavior of appending missing columns rather than assuming they always
    exist. Idempotent."""
    headers = list(headers)
    for col in columns:
        if col not in headers:
            headers.append(col)
    for row in rows:
        for col in columns:
            row.setdefault(col, None)
    return headers


def _find_row_by_name(rows: List[dict], name: str) -> dict:
    target = name.strip().lower()
    for row in rows:
        value = row.get("name")
        if value and str(value).strip().lower() == target:
            return row
    raise RuntimeError(f"'{name}' was not found -- nothing was written. Reload the page and try again.")


def _mark_discovery_reviewed(rows: List[dict], name: str, *, status: str, note: str) -> None:
    row = _find_row_by_name(rows, name)
    row["verification_status"] = status
    row["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    row["review_notes"] = note


def _approved_sites_has_name(rows: List[dict], name: str) -> bool:
    target = name.strip().lower()
    return any(r.get("name") and str(r["name"]).strip().lower() == target for r in rows)


def _append_approved_site(rows: List[dict], headers: List[str], *, name: str, link: str) -> None:
    today = date.today().isoformat()
    new_row = {h: None for h in headers}
    new_row.update({
        "approved": "TRUE",
        "name": name,
        "attribute_to": name,
        "blog_url": link,
        "approved_at": f"{today} -- review tool approval (Discovery: {name})",
    })
    rows.append(new_row)


def approve_candidate(name: str, link: str) -> None:
    discovery_mtime = DISCOVERY_PATH.stat().st_mtime
    approved_mtime = APPROVED_PATH.stat().st_mtime
    d_headers, d_rows = sheet_io.read_tab(DISCOVERY_PATH)
    d_headers = _ensure_columns(d_headers, d_rows, "reviewed_at", "review_notes")
    a_headers, a_rows = sheet_io.read_tab(APPROVED_PATH)

    if not _approved_sites_has_name(a_rows, name):
        _append_approved_site(a_rows, a_headers, name=name, link=link)

    _mark_discovery_reviewed(d_rows, name, status="verified", note="Approved -> Approved Sites")

    # Approved Sites first: if a crash happens between these two writes, the
    # candidate simply gets asked about again next run (harmless -- dedup
    # by name means no duplicate row) rather than the approval being lost.
    _refuse_if_changed(APPROVED_PATH, approved_mtime)
    sheet_io.write_tab(APPROVED_PATH, a_headers, a_rows)
    _refuse_if_changed(DISCOVERY_PATH, discovery_mtime)
    sheet_io.write_tab(DISCOVERY_PATH, d_headers, d_rows)


def reject_candidate(name: str) -> None:
    discovery_mtime = DISCOVERY_PATH.stat().st_mtime
    d_headers, d_rows = sheet_io.read_tab(DISCOVERY_PATH)
    d_headers = _ensure_columns(d_headers, d_rows, "reviewed_at", "review_notes")
    _mark_discovery_reviewed(d_rows, name, status="rejected", note="Passed on via review tool")
    _refuse_if_changed(DISCOVERY_PATH, discovery_mtime)
    sheet_io.write_tab(DISCOVERY_PATH, d_headers, d_rows)


# ---------------------------------------------------------------------------
# HTML -- plain string templates, no templating engine dependency.
# ---------------------------------------------------------------------------
def _esc(value) -> str:
    return html.escape(str(value), quote=True)


_STYLE = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f5f4; color: #1c1917; display: flex; min-height: 100vh;
         align-items: center; justify-content: center; margin: 0; }
  .wrap { text-align: center; max-width: 640px; padding: 2rem; }
  .count { color: #78716c; font-size: 0.95rem; margin-bottom: 1.5rem; }
  h1 { font-size: 2rem; margin: 0 0 1rem; word-break: break-word; }
  a.link { font-size: 1.1rem; word-break: break-all; }
  .actions { margin-top: 2.5rem; display: flex; gap: 1rem; justify-content: center; }
  button { font-size: 1.25rem; padding: 0.9rem 2.5rem; border-radius: 0.75rem;
           border: none; cursor: pointer; font-weight: 600; }
  .yes { background: #16a34a; color: white; }
  .yes:hover { background: #15803d; }
  .no { background: #e7e5e4; color: #1c1917; }
  .no:hover { background: #d6d3d1; }
</style>
"""


def _page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Review candidates</title>{_STYLE}</head><body><div class='wrap'>{body}</div></body></html>"


def _render_candidate(row: dict, link: str, remaining: int) -> str:
    name = row["name"]
    return _page(
        f"""
        <p class="count">{remaining} left to review</p>
        <h1>{_esc(name)}</h1>
        <p><a class="link" href="{_esc(link)}" target="_blank" rel="noopener">{_esc(link)}</a></p>
        <div class="actions">
          <form method="post" action="/yes">
            <input type="hidden" name="name" value="{_esc(name)}">
            <input type="hidden" name="link" value="{_esc(link)}">
            <button class="yes" type="submit">Yes</button>
          </form>
          <form method="post" action="/no">
            <input type="hidden" name="name" value="{_esc(name)}">
            <button class="no" type="submit">No</button>
          </form>
        </div>
        """
    )


def _render_done() -> str:
    return _page("<h1>You're all caught up.</h1><p class=\"count\">Nothing left to review right now.</p>")


def _render_error(message: str) -> str:
    return _page(f"<h1>Couldn't save that</h1><p>{_esc(message)}</p><p><a href='/'>Back</a></p>")


# ---------------------------------------------------------------------------
# Routes.
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    found = next_candidate()
    if found is None:
        return HTMLResponse(_render_done())
    row, link, remaining = found
    return HTMLResponse(_render_candidate(row, link, remaining))


@app.post("/yes")
def yes(name: str = Form(...), link: str = Form(...)):
    try:
        approve_candidate(name, link)
    except RuntimeError as exc:
        return HTMLResponse(_render_error(str(exc)), status_code=409)
    return RedirectResponse("/", status_code=303)


@app.post("/no")
def no(name: str = Form(...)):
    try:
        reject_candidate(name)
    except RuntimeError as exc:
        return HTMLResponse(_render_error(str(exc)), status_code=409)
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Entrypoint.
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    url = f"http://127.0.0.1:{args.port}/"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Opening {url} ...")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
