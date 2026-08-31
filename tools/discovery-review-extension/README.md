# New Wine Discovery Review Extension

## Install once

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `~/newwine/tools/discovery-review-extension/`.

## Review candidates

```bash
cd ~/newwine
python3.12 scripts/review_discovery_candidates.py
```

The first eligible website replaces the local controller tab. Use **Approve**
or **Do Not Approve** in the bottom bar; the same tab advances after each saved
decision.

## Stop

Stop the Python process with `Ctrl-C`. Disable or remove the unpacked extension
from `chrome://extensions` when the review session is finished.

## Safety boundary

The extension writes only through the loopback review server into the tracked
Discovery and Approved Sites TSV files. It never runs ingestion or writes to
the production database.

## Troubleshooting

- **Server unavailable:** return to Terminal, start the command above, then use
  **Retry** in the bottom bar.
- **Toolbar absent after reloading the extension:** reopen
  `http://127.0.0.1:8765/` to start a fresh tracked review tab.
- **File changed while reviewing:** another process edited an ingestion TSV.
  Reload the review session before deciding so the tool does not overwrite it.
- **Candidate page will not load:** reopen `http://127.0.0.1:8765/` and use the
  fallback controller for that decision.
