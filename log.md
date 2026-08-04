# Session Log

## 2026-08-04 — Project 1 async production-readiness closeout

Completed the engineering and controlled-test portion of the final Project 1
readiness slice.

- Hardened `POST /async-chat/submit` to enforce the database
  `serving_enabled` switch before metering or enqueueing.
- Added immediate frontend fallback to `/chat` when a browser has a stale
  async-mode cache after rollback.
- Measured the Anthropic account limits at 10,000 RPM, 10,000,000 input tokens
  per minute, and 2,000,000 output tokens per minute.
- Configured the shared async dials with 20% headroom: 8,000 RPM, 8,000,000
  ITPM, and 1,600,000 OTPM.
- Set the live rolling-24-hour spend ceiling to $10.
- Verified the Supabase transaction-pooler route on port 6543.
- Measured 20/20 simultaneous generations through the transaction pooler. Five
  20-slot replicas provision the 100-slot target without an architecture change.
- Ran five real questions plus one queued end-to-end answer through retrieval,
  generation, and the existing verification path with zero harness failures.
- Verified worker recovery, single-flight sharing, reconnectable results,
  spend pauses, and provider-rate pauses with zero-cost fake generations.
- Cleaned all marked test rows after the run.
- Final live state: `serving_enabled=false`, `paused=false`, $10 rolling ceiling,
  configured rate dials intact, and zero marked test rows.

Implementation and durable-record updates are in local commit `6dca017`
(`fix: harden async traffic rollback before cutover`). The commit is not pushed:
`main` auto-deploys, but Railway CLI is unauthenticated in this environment, so a
production worker service could not be created or configured safely.

Remaining cutover work:

1. Authenticate Railway.
2. Create the worker service with conservative 20-slot concurrency and the
   transaction-pooler database URL.
3. Enable `ASYNC_ANSWER_ENABLED` while keeping `serving_enabled=false` and run
   dark health checks.
4. Run the controlled public traffic window, measure it, and switch serving off
   immediately afterward.
5. Make async serving normal only after the controlled window passes.

Unrelated commentary UI, proposition/numeral-detector, and position-paper work
was intentionally left untouched.
