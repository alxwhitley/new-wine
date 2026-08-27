# Discovery Review Browser Extension Design

**Date:** 2026-08-27

**Status:** Approved by Alex in chat on 2026-08-27

**Owner:** Rhemata ingestion candidate review

## Outcome

Alex can review each eligible Discovery candidate directly on its website. A
fixed bar at the bottom of the page offers **Approve** and **Do Not Approve**.
After a successful decision, the same browser tab advances to the next
candidate. The workflow ends with a visible caught-up state.

The extension is a local review interface only. It updates the tracked
Discovery and Approved Sites TSV files through the existing local review
server. It never writes to the production database, runs ingestion, promotes a
source, or changes source visibility.

## Existing Contracts Preserved

- `docs/ingestion/master_ingestion_queue_discovery.tsv` remains the Discovery
  source of truth.
- `docs/ingestion/master_ingestion_queue_approved_sites.tsv` remains the only
  approved-site input to `site_ingest_crawler.py`.
- `scripts/ingestion_sheet_io.py` remains the only TSV encoding and write
  implementation.
- Approval continues to mark the Discovery row verified and append a deduped,
  `approved=TRUE` Approved Sites row.
- Rejection continues to mark the Discovery row rejected.
- Existing mtime-based stale-file refusal remains authoritative. A concurrent
  edit produces an error; it is never overwritten.
- The current local controller remains available as a fallback when the
  extension is absent or disabled.
- Existing user changes in either TSV are preserved. This feature does not
  rewrite, normalize, or clean historical decisions.

## Selected Approach

Build a small unpacked Chrome Manifest V3 extension under
`tools/discovery-review-extension/`.

The extension uses:

- a static content script on top-level `http` and `https` pages;
- a Manifest V3 service worker for fixed localhost API calls;
- `chrome.storage.session` to retain the active review tab across service
  worker suspension and cross-origin navigation;
- a Shadow DOM toolbar so host-page CSS and JavaScript do not accidentally
  restyle or control the review interface.

Chrome content scripts run in an isolated JavaScript world and can change the
host page DOM. Cross-origin requests to the local review server are made by the
extension service worker, not by the content script, and require only the
declared localhost host permission.

Official references:

- <https://developer.chrome.com/docs/extensions/reference/manifest/content-scripts>
- <https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts>
- <https://developer.chrome.com/docs/extensions/develop/concepts/network-requests>
- <https://developer.chrome.com/docs/extensions/mv3/manifest>

## Components

### Local review server

Extend `scripts/review_discovery_candidates.py` with an extension-facing JSON
contract:

- `GET /api/review/current`
  - Returns `{done: true, candidate: null}` when nothing remains.
  - Otherwise returns the current candidate's name, link, and remaining count.
- `POST /api/review/start`
  - Returns the same current-candidate payload.
  - Performs no write.
- `POST /api/review/decision`
  - Accepts only `action=approve` or `action=reject`.
  - Re-reads the current eligible candidate from the TSV at decision time.
  - Does not accept a caller-supplied candidate name or URL.
  - Applies the existing approval or rejection function to that current row.
  - Returns the freshly re-read next candidate or the terminal state.

The extension endpoints reuse `next_candidate()`, `approve_candidate()`, and
`reject_candidate()` rather than duplicating sheet logic. Existing HTML routes
remain for the fallback controller.

### Extension manifest

`manifest.json` uses Manifest V3 and declares:

- content-script matches for `http://*/*` and `https://*/*`;
- `host_permissions` only for `http://127.0.0.1:8765/*`;
- the `storage` permission for session-scoped active-tab state;
- a service worker;
- one content script and one stylesheet.

The extension requests broad page injection because candidate domains are not
known in advance. It does not request cookies, browsing history, web-request
interception, downloads, or production Rhemata host access.

### Service worker

The service worker owns all localhost communication and review-session state.
It accepts a fixed message enum only:

- `START_REVIEW`
- `GET_REVIEW_STATE`
- `DECIDE_APPROVE`
- `DECIDE_REJECT`

Handlers call fixed paths on `http://127.0.0.1:8765`. Messages cannot supply an
arbitrary fetch URL. This prevents the extension from becoming a general
cross-origin request proxy.

On start, the worker records the initiating tab ID in
`chrome.storage.session`. Only messages from that tab may retrieve review state
or submit decisions. A new start replaces the prior active tab deliberately.

### Content script and toolbar

On the local controller page, the content script detects the review-controller
marker and starts extension mode. The current tab then navigates to the first
candidate returned by the server.

On ordinary pages, the content script asks the worker whether its tab is the
active review tab. Non-review tabs receive an inactive response and no visible
DOM is added.

For the active tab, the content script creates one fixed Shadow DOM host at the
bottom of the viewport. The bar displays:

- candidate name;
- remaining count;
- **Approve**;
- **Do Not Approve**;
- a compact status/error message.

The bar never reads page content, form values, cookies, local storage, or user
input from the candidate site.

## User Flow

1. Alex loads the unpacked extension once through `chrome://extensions`.
2. Alex runs:

   ```bash
   cd ~/rhemata
   python3.12 scripts/review_discovery_candidates.py
   ```

3. The server opens the local controller as it does today.
4. The extension recognizes the controller, starts a review session in that
   tab, and navigates it to the first eligible candidate.
5. The bottom bar appears after navigation.
6. Alex reviews the site and clicks a decision.
7. The clicked controls disable immediately to prevent duplicate submissions.
8. The service worker submits the decision to the fixed localhost endpoint.
9. On success, the same tab navigates to the returned next candidate.
10. On the final decision, the bar changes to the caught-up state and no
    navigation occurs.

Only one candidate tab is used. The extension never opens the full queue or a
new tab per candidate.

## Failure Behavior

- **Server unavailable:** show “Start the Rhemata review server” and a Retry
  action. Do not navigate or write.
- **Stale TSV:** display the server's conflict message. Keep the current page
  open and controls retryable after reload.
- **Invalid or unexpected response:** show an error and keep the current page.
- **Double click:** disable both decisions before sending the first request.
- **Candidate site fails to load:** Chrome's normal error page remains visible;
  the extension cannot inject into privileged Chrome error pages. Alex can use
  the fallback controller or navigate back and retry.
- **Extension disabled mid-session:** no further injected controls appear. The
  fallback local controller remains usable.
- **Server restart:** session state in Chrome may still name the tab, but the
  worker must re-fetch the server's current candidate before showing actionable
  controls.

A failed decision never advances to the next candidate.

## Security Boundaries

- The extension is local and unpacked; it is not published to the Chrome Web
  Store.
- Broad page injection is used only to display the toolbar in the one tracked
  review tab.
- Host-page scripts cannot access the content script's isolated JavaScript
  world.
- The toolbar renders server strings with `textContent`; it does not use
  untrusted `innerHTML`.
- The service worker fetches fixed localhost endpoints only.
- Decision identity is selected by the server from the fresh queue, never
  trusted from the website or content script.
- No production credentials or secrets are stored in the extension.
- No database endpoint is reachable through the extension contract.
- The local server retains its current single-user, loopback-only trust posture.

## Testing Contract

### Python tests

- Current-candidate endpoint returns the first eligible row and remaining
  count.
- Start performs no write.
- Approve persists through the canonical TSV functions and returns the next
  candidate.
- Reject persists and returns the next candidate.
- Final decision returns the terminal state.
- Unknown action is rejected without changing either TSV.
- Caller cannot choose a different candidate by supplying a name or URL.
- Stale-file refusal returns a conflict and does not advance.

All Python tests use throwaway TSV fixtures.

### Extension unit tests

- Only the fixed message enum is accepted.
- Only the active review tab can retrieve state or decide.
- Worker fetch targets are fixed localhost paths.
- Toolbar uses text nodes for candidate data.
- Controls disable while a decision is pending and recover on error.
- Inactive tabs receive no toolbar.

### Browser verification

Run Chrome/Playwright against the real local FastAPI app with throwaway TSV
fixtures and two local fake candidate sites:

1. Start page navigates to candidate one.
2. Toolbar is visible at the bottom.
3. Approve records candidate one and navigates the same tab to candidate two.
4. Reject records candidate two.
5. The same tab shows the caught-up state.
6. No additional candidate tabs exist.
7. Real ingestion TSVs and the database remain unchanged.

## Installation Documentation

Add a short README in the extension directory covering:

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose **Load unpacked**.
4. Select `tools/discovery-review-extension/`.
5. Start the Python review server.
6. Remove or disable the extension when review work is finished.

## Non-Goals

- No automated judgment about candidate quality.
- No Skip or Undo action in this version.
- No bulk approval or rejection.
- No scraping or reading candidate page content.
- No site crawler or ingestion execution.
- No production database writes.
- No changes to Discovery eligibility rules.
- No Chrome Web Store packaging or distribution.
- No support for Firefox or Safari.
- No redesign of the ingestion spreadsheet.

## Acceptance Criteria

The feature is accepted when Alex can load the unpacked extension, start the
existing review server, review two representative websites in one browser tab,
save one approval and one rejection through the canonical TSV path, and reach
the caught-up state without returning to a controller tab. All automated tests
and the throwaway-data browser verification must pass, and the production
database must remain untouched.
