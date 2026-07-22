# Phone-Triggered Ingestion — Parked Design Concept
Status: design-approved in concept, NOT scheduled. Resume when ready.

## Goal
Alex wants to trigger a corpus ingestion/extraction script from his phone (app, web app, or inside Rhemata) instead of typing bash commands at his Mac. Ideal: works while the computer is closed. Fallback: works while the computer is awake and prepared.

## Guiding constraint
Must extend Alex's supervision discipline, not bypass it. NOT a free-form "run anything" remote control. Design is: pre-approved jobs only, one at a time, full logs, fail-closed if anything looks off. The phone triggers a vetted run; it never composes an arbitrary one.

## Core architecture: job queue, not remote control
Phone posts a job; a runner picks it up. Phone never reaches into the Mac.
- A "jobs" table in the existing database.
- A hidden admin-role-gated page inside Rhemata lists pre-approved runs; tapping one inserts a job row (status: requested).
- A runner executes it, streams its log into the table, marks done/failed.
- Phone page shows live status. No open inbound ports, no new accounts, every run recorded.

## Two runner scenarios
- COMPUTER AWAKE (low-risk, ~1 session on top of current setup): a small local agent on the Mac polls the jobs table every minute and runs queued jobs. Mac polls OUTWARD, so nothing needs inbound access — works from any network. Scripts run unchanged. Alex preps the machine, triggers + monitors from phone.
- COMPUTER CLOSED (the real goal; a migration, not a feature): runner lives in the cloud (Railway, where backend already runs). Cloud worker pulls needed source files from Google Drive, runs the ingest, writes to DB. Feasible BECAUSE the corpus is now backed up to Drive — but this promotes the Drive backup from "safety net" to "operational source" (must be reliably current). Each script needs adapting off Mac-specific paths/quirks and re-verifying before unattended cloud runs. Per-script migration, demo-before-scale.

## Recommended phasing
Build job queue + Rhemata admin trigger page + Mac-awake poller FIRST (small, safe; the queue/page/logging layer is permanent regardless of runner). Then migrate scripts to the cloud runner one at a time, most-repetitive first (New Wine batches = likely first). The phone button never changes; only the worker behind it moves. Ends at "computer closed" without an unproven leap.

## Rejected approaches
- Remote-desktop / SSH-to-Mac apps: reduces to typing terminal commands on a phone; opens the machine to the internet. Opposite of the goal.
- Apple Shortcuts automations: brittle, no real logs, fails silently — violates the no-silent-failure rule.
- Always-listening inbound service on the Mac: unnecessary security surface; outward polling achieves the same safely.

## Security flag to carry forward
This hands a production DB-write trigger to whoever holds an admin session on a phone. Pre-approved-jobs-only contains most of the risk (button runs only vetted scripts), but "my phone can write to production" is a new posture; losing the phone becomes a bigger event. Decide deliberately.

## Open decisions (unanswered — resume here)
1. Confirm the constrained version (pre-approved jobs only, one-at-a-time, full logs, fail-closed) vs a free-form button.
2. Phase 1 (job queue + Rhemata admin page + Mac-awake poller) first, cloud runner later per-script — or jump straight to cloud runner?
3. If Phase 1: which script is the first pre-approved job? (New Wine batch is the suggested pick.)
