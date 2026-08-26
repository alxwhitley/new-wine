# Rhemata — Live Status

Point-in-time state only. Overwritten each session, not appended to. Never
durable truth — the durable records are the code, git history, PLAN.md
(current Blockers), docs/roadmap.md (later classified work),
docs/plan-archive.md (history), and CLAUDE.md (invariants). Corpus, row, and
table counts are NOT recorded here except as a dated, sourced snapshot from a
specific live query — treat any count seen elsewhere as unverified.

Last verified: 2026-08-25 (B6 answer-latency benchmark and guarded deployment;
New Wine Issue 02-1973 paid no-write review completed and quarantined).

**Session close:** `.claude/skills/session-close/SKILL.md`. Target ≤150 lines
for this file.

---

## Current state

`PLAN.md` now has **1 active blocker**: B6-F1, the named-teacher/stored-position
route collision. The B6 work measured the full answer path, built a read-only
benchmark and observational trace, corrected broken Groq query expansion, and
rejected the tested teacher-specific candidate as a suite-wide latency solution.
The quote rail remains off.

**Shipped and live (`fc87041`):**

1. Query expansion now uses the already-established
   `openai/gpt-oss-120b`; the former hardcoded Groq model returned 404 and
   silently reduced retrieval depth. Paid preflights repeatedly returned three
   variants plus keyword routing after the correction.
2. The answer producer accepts an optional in-memory latency trace that records
   routing, retrieval, generation, first text, validation, references, quotes,
   tokens, and total time without recording source text or changing untraced
   results.
3. The teacher-specific source boundary and 12-chunk cap are present only behind
   `experimental_teacher_routing=False`. The production worker has no caller
   enabling it; the rejected candidate is dormant. Prompt safeguards, generation
   model, attribution/reference checks, and quote-off policy are unchanged.
4. The safe-default benchmark requires an explicit paid flag, quote-off runtime,
   pinned model/prompt/policy, local-only output, expansion preflight, and cost
   ceiling. It creates no answer jobs, messages, conversations, metering rows, or
   other database writes.

**Measured result:** 48/48 paid read-only generations completed with no errors
or skips, no database writes, no quotes, and $2.744223 combined spend. Baseline
answered 22/24 and reproduced the two known named-teacher refusals; the candidate
answered 24/24 and both named-teacher repetitions delivered exactly 12 Derek
Prince citations with no attribution retry. The candidate improved suite median
latency only 2.81% (20% required), won 8/12 cases (10 required), and did not
regress p90. It is rejected as the B6 latency direction because it structurally
changes only the named-teacher case; movements elsewhere are provider variance.

**Production deployment:** Railway API `bec3c06c-7dbb-4979-9983-8c8eccab8560`
and answer worker `1894b766-9c84-4540-86e7-3f33ec2a650a` reached SUCCESS from
`fc87041`; Vercel `dpl_BAUDGAbPghiyC2JUi9LUb2of17bE` reached Ready and is
aliased to `rhemata.app`. No migration or production database write ran.

**Verification:** independent answer-integrity review returned ACCEPT; targeted
answer-latency, shared-intent, stored-position, and single-teacher-lock suites
passed; changed Python compiled under Python 3.12; frontend tests passed 26/26;
the 17-route production build passed with the existing environment; staged
secret scan and diff checks passed. The three existing transitive frontend high
advisories remain the already-classified Next.js-tree follow-up; no dependency
changed.

**Session measures:** original outcome completed (measured and bounded; tested
candidate rejected honestly); unplanned investigations 0; findings promoted to
Blocker 1 (B6-F1); active critical-path item count 1. Alex-approved scope:
read-only provider spend up to $5, commit, push, and production deployment.

**New Wine A2 no-write review (`b18c6ca` and related commits):** Issue 02-1973
reached a valid `quarantined` terminal state. Gemini `gemini-3.7-flash` initial
OCR plus `gemini-3.6-flash` review passed all 32 pages; page 15 used the single
allowed repair. Groq `openai/gpt-oss-120b` produced 17 lineage-bound article
candidates whose exact text and source pages were derived locally from verified
spans. Fresh whole-issue review found the omitted `THE APOSTLE—GOD'S MASTER
BUILDER` article and two missing Health and Healing continuations, so proposition
extraction correctly did not run. Reconciliation: 32 pages, 17 articles,
0 propositions, 0 database writes. Conservative cumulative spend was
$1.08638205 under Alex's $1.25 ceiling.

The validated New Wine artifacts remain local-only and intentionally untracked
under `docs/audits/2026-08/new_wine_issue_02_1973_review_2026-08-25_retry_13/`
because the Git remote is public. All artifact envelopes and lineage revalidated;
the magazine suite passes 166 tests.

---

## Findings surfaced, not yet acted on

- **Scheduled** (`docs/roadmap.md`, new "Dependency and hardening follow-up"
  section): starlette+fastapi coupled bump — do the read-only exploitability
  triage of its 7 advisories first, the same pass that reduced 3 alarming
  Next.js CVEs to zero live attack surface; pdfplumber+pdfminer coupled bump;
  CSP on the frontend; the deferred Next.js major bump.
- **Scheduled** (`docs/roadmap.md`): quote accuracy and relevance repair before
  any attended re-enable; the live rail remains off.
- **Blocker** (`PLAN.md`, B6-F1): named-teacher requests can collide with
  stored-topic evidence and cleanly refuse. The source-faithful correction is
  live-proven but remains dormant pending targeted blind human quality review.
- **Scheduled** (`docs/roadmap.md`, B6): a future suite-wide latency candidate
  must address the generation bottleneck; the teacher-specific route was
  rejected after only 2.81% median improvement.
- **Triggered** (`docs/roadmap.md`): JWKS unknown-`kid` rate limit — PyJWT
  2.13.0 already fixed the amplifying half (cache-wipe on failed fetch); the
  residual is un-amplified and belongs at the edge, not in `auth.py`.
- Public `/docs` + `/openapi.json` on the API list every route including
  admin ones. Routes stay auth-gated, so this is a map, not an open door.
  Left as-is deliberately — Alex may use it; not yet formally classified.
- Staging source name still reads `"Vlad Savchuk (web staging)"` on
  citations — attended one-row `sources.name` UPDATE whenever Alex wants it.
- Carried, not re-checked this session: Bonnke URL suspect (expired cert, no
  CfaN corroboration); no retention/TTL logic for user data;
  `rhemata_readonly_analysis` has no grant on PII tables; full cascading
  account deletion still unbuilt (migration 090 removed only the DB-level
  blocker — `POST /account/delete-request` is still a stub).
- **Scheduled A2:** correct the omitted New Wine article and two continuations,
  then rerun the local no-write article/proposition gates. The current
  quarantine is the desired safety result, not authorization for ingestion.
- The two New Wine `missing_substantive_spans` point at page markers immediately
  before the omitted continuations; the failed article records independently
  identify the missing content. Improve precision during the scheduled correction.

---

## Next single item

Run a targeted blind human quality review of the saved named-teacher integrity
correction, then make one explicit accept/reject implementation decision for
B6-F1. Do not conflate that correctness fix with a future suite-wide latency
candidate. The separately authorized crawler track remains available through
its own workflow. New Wine A2 remains scheduled behind the active critical-path
blocker. Active blocker count **1**.
