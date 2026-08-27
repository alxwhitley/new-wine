#!/usr/bin/env python3
"""review_discovery_candidates.py -- minimal one-candidate-at-a-time local
review tool for the Discovery data in
docs/ingestion/master_ingestion_queue_discovery.tsv.

Alex's explicit requirement (2026-08-25): find links to blogs/material,
review them, approve them for ingestion -- nothing else. So this page shows
exactly two things per candidate: their name, and a link to their site.
The controller opens one candidate site in a child tab and keeps the local
Approve / Do Not Approve controls in the original tab. After a successful
decision it closes the reviewed child, opens the next candidate, and updates
the controller without a page reload. It never opens the whole backlog at
once. Two decisions, no forms:
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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

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


def decide_and_advance(action: str, name: str, link: str) -> dict:
    """Persist one controller decision, then return the fresh next item."""
    if action == "approve":
        approve_candidate(name, link)
    elif action == "reject":
        reject_candidate(name)
    else:
        raise ValueError(f"Unknown review action: {action!r}")

    found = next_candidate()
    if found is None:
        return {"done": True, "candidate": None}
    row, next_link, remaining = found
    return {
        "done": False,
        "candidate": {
            "name": row["name"],
            "link": next_link,
            "remaining": remaining,
        },
    }


def current_review_payload() -> dict:
    found = next_candidate()
    if found is None:
        return {"done": True, "candidate": None}
    row, link, remaining = found
    return {
        "done": False,
        "candidate": {
            "name": row["name"],
            "link": link,
            "remaining": remaining,
        },
    }


def decide_current_and_advance(action: str) -> dict:
    found = next_candidate()
    if found is None:
        return {"done": True, "candidate": None}
    row, link, _remaining = found
    if action == "approve":
        approve_candidate(row["name"], link)
    elif action == "reject":
        reject_candidate(row["name"])
    else:
        raise ValueError(f"Unknown review action: {action!r}")
    return current_review_payload()


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
  button:disabled { cursor: wait; opacity: 0.55; }
  .open { background: #292524; color: white; margin-top: 1.5rem; }
  .open:hover { background: #44403c; }
  .yes { background: #16a34a; color: white; }
  .yes:hover { background: #15803d; }
  .no { background: #e7e5e4; color: #1c1917; }
  .no:hover { background: #d6d3d1; }
  .status { color: #57534e; min-height: 1.5rem; margin-top: 1rem; }
  .status.error { color: #b91c1c; }
</style>
"""


def _page(body: str) -> str:
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Review candidates</title>{_STYLE}</head><body><div class='wrap'>{body}</div></body></html>"


def _render_candidate(row: dict, link: str, remaining: int) -> str:
    name = row["name"]
    return _page(
        f"""
        <section id="review-controller" data-name="{_esc(name)}" data-link="{_esc(link)}">
        <p class="count"><span id="remaining">{remaining}</span> left to review</p>
        <h1 id="candidate-name">{_esc(name)}</h1>
        <p><a id="candidate-link" class="link" href="{_esc(link)}" target="_blank" rel="noopener">{_esc(link)}</a></p>
        <button id="open-site" class="open" type="button">Start Review</button>
        <p id="review-status" class="status">Open the site to begin.</p>
        <div class="actions">
          <button id="approve" class="yes" type="button" disabled>Approve</button>
          <button id="reject" class="no" type="button" disabled>Do Not Approve</button>
        </div>
        </section>
        <script>
        (() => {{
          const controller = document.getElementById("review-controller");
          const openButton = document.getElementById("open-site");
          const approveButton = document.getElementById("approve");
          const rejectButton = document.getElementById("reject");
          const status = document.getElementById("review-status");
          let siteWindow = null;

          const current = () => ({{
            name: controller.dataset.name,
            link: controller.dataset.link,
          }});

          const setBusy = (busy) => {{
            openButton.disabled = busy;
            approveButton.disabled = busy;
            rejectButton.disabled = busy;
          }};

          const setStatus = (message, isError = false) => {{
            status.textContent = message;
            status.classList.toggle("error", isError);
          }};

          const openBlankChild = (windowName) => {{
            const child = window.open("about:blank", windowName);
            if (child) child.opener = null;
            return child;
          }};

          const navigateChild = (child, url) => {{
            child.location.replace(url);
            child.focus();
          }};

          const openCurrentSite = () => {{
            const child = openBlankChild("rhemata-review-site");
            if (!child) {{
              setStatus("The website tab was blocked. Allow popups for 127.0.0.1, then try again.", true);
              return;
            }}
            siteWindow = child;
            navigateChild(siteWindow, current().link);
            openButton.textContent = "Reopen Site";
            approveButton.disabled = false;
            rejectButton.disabled = false;
            setStatus("Review the website, then choose a decision here.");
          }};

          const renderNext = (candidate) => {{
            controller.dataset.name = candidate.name;
            controller.dataset.link = candidate.link;
            document.getElementById("candidate-name").textContent = candidate.name;
            const link = document.getElementById("candidate-link");
            link.href = candidate.link;
            link.textContent = candidate.link;
            document.getElementById("remaining").textContent = candidate.remaining;
            openButton.textContent = "Reopen Site";
          }};

          const renderDone = () => {{
            controller.innerHTML = `<h1>You're all caught up.</h1><p class="count">Nothing left to review right now.</p>`;
          }};

          const decide = async (action) => {{
            // Reserve the successor tab during this click. Waiting until the
            // network response returns would let popup blockers reject it.
            const nextWindow = openBlankChild("rhemata-review-next");
            if (!nextWindow) {{
              setStatus("The next website tab was blocked. Allow popups before saving this decision.", true);
              return;
            }}

            const reviewed = current();
            setBusy(true);
            setStatus("Saving decision…");
            try {{
              const body = new URLSearchParams({{
                action,
                name: reviewed.name,
                link: reviewed.link,
              }});
              const response = await fetch("/decision", {{
                method: "POST",
                headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
                body,
              }});
              const result = await response.json();
              if (!response.ok) throw new Error(result.error || "The decision could not be saved.");

              if (siteWindow && !siteWindow.closed) siteWindow.close();
              if (result.done) {{
                nextWindow.close();
                siteWindow = null;
                renderDone();
                return;
              }}

              renderNext(result.candidate);
              nextWindow.name = "rhemata-review-site";
              siteWindow = nextWindow;
              navigateChild(siteWindow, result.candidate.link);
              setBusy(false);
              setStatus("Decision saved. Review the next website.");
            }} catch (error) {{
              nextWindow.close();
              setBusy(false);
              setStatus(error.message || "The decision could not be saved.", true);
            }}
          }};

          openButton.addEventListener("click", openCurrentSite);
          approveButton.addEventListener("click", () => decide("approve"));
          rejectButton.addEventListener("click", () => decide("reject"));
        }})();
        </script>
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


@app.post("/decision", response_class=JSONResponse)
def decision(
    action: str = Form(...), name: str = Form(...), link: str = Form("")
) -> JSONResponse:
    try:
        result = decide_and_advance(action, name, link)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(result)


@app.get("/api/review/current", response_class=JSONResponse)
def api_review_current() -> JSONResponse:
    return JSONResponse(current_review_payload())


@app.post("/api/review/start", response_class=JSONResponse)
def api_review_start() -> JSONResponse:
    return JSONResponse(current_review_payload())


@app.post("/api/review/decision", response_class=JSONResponse)
def api_review_decision(action: str = Form(...)) -> JSONResponse:
    try:
        result = decide_current_and_advance(action)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except RuntimeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(result)


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
