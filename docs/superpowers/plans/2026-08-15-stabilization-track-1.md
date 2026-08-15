# Stabilization Track 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish current deployment, serving, quote-verification, stored-position, attribution, and F5-bypass truth before any further corrective build.

**Architecture:** This track is a read-only evidence pass over Git, Railway, Vercel, the production HTTP surfaces, and Supabase through the `rhemata_readonly_analysis` role. It produces one durable audit; it does not modify application behavior or production data. Any demonstrated defect becomes a separately reviewed Track 2 packet.

**Tech Stack:** Git, Railway CLI 5.13.3, Vercel CLI 58.5.1, curl, Python 3.12, PostgreSQL/psql, existing Rhemata regression scripts.

**Spec:** `docs/superpowers/specs/2026-08-15-stabilization-and-beta-readiness-design.md`

## Global Constraints

- Preserve every `CLAUDE.md` invariant and `PLAN.md` standing rule.
- Use `backend/app/.env.readonly-analysis` for direct SQL and assert `current_user = 'rhemata_readonly_analysis'` before evidence queries.
- Execute no `INSERT`, `UPDATE`, `DELETE`, `ALTER`, migration, deploy, or other production mutation in this track.
- Do not generate a fresh paid answer merely to diagnose the existing deliverance result; inspect the retained completed job first.
- Treat theological interpretation and teacher-position judgment as human-owned; this track diagnoses data flow and rendering only.
- Keep `Temporary-assets/` untouched.
- Store conclusions in a docs-only audit commit, separate from every later build commit.

---

### Task 1: Verify repository and deployed revisions

**Files:**
- Create after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: local `main`, `origin/main`, Railway project services `rhemata` and `answer-worker`, Vercel project `rhemata`.
- Produces: exact local/origin/deployed revision and status evidence for Checkpoint A.

- [ ] **Step 1: Confirm local and remote Git state**

Run:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git log --oneline --decorate -5
```

Expected: only `Temporary-assets/` is unrelated/untracked; the plan commit may be ahead of `origin/main` until the docs close is pushed.

- [ ] **Step 2: Read Railway deployment metadata for both services**

Run:

```bash
railway status --json
railway deployment list --service rhemata --environment production --limit 5 --json
railway deployment list --service answer-worker --environment production --limit 5 --json
```

Expected: both services identify a latest deployment, status, creation time, and source revision. No `deployment up`, `redeploy`, `restart`, or `service` mutation command is permitted.

- [ ] **Step 3: Read Vercel production deployment metadata**

Run:

```bash
vercel list rhemata --environment production --status READY --limit 5 --json --cwd frontend
```

Expected: the latest READY deployment exposes its URL, creation time, and Git revision metadata.

- [ ] **Step 4: Compare deployed revisions with the two shipped fixes**

Run:

```bash
git merge-base --is-ancestor 21ff62f HEAD
git merge-base --is-ancestor bc37749 HEAD
git show -s --format='%H %cI %s' 21ff62f bc37749
```

Expected: both commands exit zero and deployment timestamps/revisions are new enough to contain both fixes. If a provider does not expose a source SHA, record that limitation and use its build timestamp/log rather than claiming revision identity.

---

### Task 2: Verify the shipped serving guards

**Files:**
- Modify after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: production-deployed revision evidence, real servable/unservable document fixtures, existing mutation-tested regression scripts.
- Produces: local real-DB guard evidence plus production availability evidence without weakening authentication.

- [ ] **Step 1: Run the four-surface real-DB regression**

Run:

```bash
python3.12 scripts/test_four_surfaces_license_gate.py
```

Expected: all document, article, book-excerpt, background-topic, and position-paper checks pass, including refusal of the real sentinel-backed unservable document.

- [ ] **Step 2: Run the teacher-card regression**

Run:

```bash
python3.12 scripts/test_teacher_card_bio_redaction.py
```

Expected: bio redaction, fabricated other-teacher attribution refusal, candidate-pool decoupling, and bibliography-cap checks all pass.

- [ ] **Step 3: Verify public production availability**

Run:

```bash
curl -fsS https://rhemata-production.up.railway.app/
curl -I https://rhemata.vercel.app/
```

Expected: backend returns `{"message":"Rhemata API"}` and the production frontend returns an HTTP success or redirect to its canonical production URL.

- [ ] **Step 4: Exercise authenticated production surfaces through the existing signed-in browser session**

Verify one servable document opens, the sentinel-backed unservable document returns the product's not-found behavior, a Derek Prince teacher card renders, and no fabricated other-teacher attribution appears. Do not bypass authentication or expose session credentials.

Expected: public behavior agrees with the real-DB regression and deployed revision evidence. If no authenticated session exists, record the production-auth smoke as blocked rather than substituting a service-role call and calling it production HTTP evidence.

---

### Task 3: Quantify Derek Prince quote rejection reasons

**Files:**
- Modify after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: `quote_verification_log`, Derek Prince source ID `17be391b-d025-4178-8543-3e84da675c5d`, `quotes`, `quote_source_revisions`, `chunks`, and `documents`.
- Produces: Decision 23 evidence grouped by rule, reason, document, and time window.

- [ ] **Step 1: Establish the read-only connection and log bounds**

Run from one foreground shell after sourcing `backend/app/.env.readonly-analysis` and confirming `READONLY_ANALYSIS_DB_URL` is non-empty:

```sql
SELECT current_user;
SELECT min(created_at), max(created_at), count(*)
FROM quote_verification_log
WHERE teacher_source_id = '17be391b-d025-4178-8543-3e84da675c5d';
```

Expected: `current_user` is exactly `rhemata_readonly_analysis`; the log query returns a bounded timestamp range and row count.

- [ ] **Step 2: Produce the rejection distribution**

Run:

```sql
SELECT decision, rule, coalesce(reason, '(none)') AS reason, count(*) AS decisions,
       count(DISTINCT document_id) AS documents
FROM quote_verification_log
WHERE teacher_source_id = '17be391b-d025-4178-8543-3e84da675c5d'
GROUP BY decision, rule, coalesce(reason, '(none)')
ORDER BY decisions DESC, rule, reason;
```

Expected: every logged Prince acceptance/refusal is accounted for exactly once; sum of grouped `decisions` equals the Step 1 row count.

- [ ] **Step 3: Identify documents with refusals and no approved quote**

Run:

```sql
WITH prince_docs AS (
  SELECT d.id, d.title
  FROM documents d
  WHERE d.source_id = '17be391b-d025-4178-8543-3e84da675c5d'
    AND coalesce(d.source_type, '') <> 'book'
    AND coalesce(d.source_kind, '') <> 'commentary'
), approved_docs AS (
  SELECT DISTINCT c.document_id
  FROM quotes q
  JOIN quote_source_revisions qsr ON qsr.id = q.source_revision_id
  JOIN chunks c ON c.id = qsr.chunk_id
  WHERE q.teacher_source_id = '17be391b-d025-4178-8543-3e84da675c5d'
    AND q.status = 'approved'
)
SELECT pd.id, pd.title,
       count(v.id) FILTER (WHERE v.decision = 'refused') AS refusals,
       array_agg(DISTINCT v.rule) FILTER (WHERE v.decision = 'refused') AS refusal_rules
FROM prince_docs pd
LEFT JOIN approved_docs ad ON ad.document_id = pd.id
LEFT JOIN quote_verification_log v ON v.document_id = pd.id
 AND v.teacher_source_id = '17be391b-d025-4178-8543-3e84da675c5d'
WHERE ad.document_id IS NULL
GROUP BY pd.id, pd.title
ORDER BY pd.title;
```

Expected: the current zero-approved-quote set is enumerated by ID and title, not copied from the stale 20-document figure.

- [ ] **Step 4: Reconcile Decision 23 evidence**

Record whether the rejection classes support keeping, changing, or separately investigating majority-Scripture and unbalanced-quotation guards. Do not close Decision 23 without a conclusion Alex can evaluate.

---

### Task 4: Reproduce and classify the stored-position test drift

**Files:**
- Read: `scripts/test_stored_position_evidence.py`
- Read: `backend/app/services/stored_position_evidence.py`
- Modify after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: six V1 topic keys, current source visibility, live stored-position evidence.
- Produces: a discriminating statement of which assertions are stale versus which invariants remain valid.

- [ ] **Step 1: Run the existing test unchanged**

Run:

```bash
python3.12 scripts/test_stored_position_evidence.py
```

Expected: the pre-flip `EXPECTED_NONE_TODAY` and `HIDDEN_AUTHOR_NAMES` assumptions fail for now-shown Savchuk/Ravenhill evidence; structural shape and commentary-exclusion checks should remain meaningful.

- [ ] **Step 2: Query current contributor visibility through the read-only role**

Run:

```sql
SELECT s.name, s.license_status, s.visibility
FROM sources s
WHERE s.name IN ('Derek Prince', 'Vlad Savchuk', 'Leonard Ravenhill', 'Doug Kreighbaum')
ORDER BY s.name;
```

Expected: current visibility explains the changed evidence results directly.

- [ ] **Step 3: Classify the required Track 2 correction**

Record which assertions should become invariant-based instead of date-stamped live snapshots. Preserve checks for required chunk shape, servability, and commentary/word-study exclusion; remove only assumptions invalidated by the authorized visibility flip.

---

### Task 5: Diagnose missing teacher names in the deliverance answer

**Files:**
- Read: `backend/app/services/async_answers/producer.py`
- Read: `backend/app/services/answer_toolbox.py`
- Read: frontend citation rendering components located by `rg -n "citations|verified_references" frontend`
- Modify after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: latest completed deliverance `answer_jobs` row, its citations, verified references, retrieved chunk IDs, and the associated documents/sources.
- Produces: one cause classification—missing in evidence, omitted by generation, or dropped during rendering—with exact supporting fields.

- [ ] **Step 1: Select recent completed deliverance jobs**

Run through the read-only role:

```sql
SELECT id, question, outcome, answer, citations, verified_references,
       retrieved_chunk_ids, retrieved_point_ids, model, finished_at
FROM answer_jobs
WHERE status = 'done'
  AND lower(question) LIKE '%deliverance%'
ORDER BY finished_at DESC
LIMIT 10;
```

Expected: identify the exact job whose six citations showed no teacher name, or record that retention no longer contains it.

- [ ] **Step 2: Resolve retrieved evidence identity**

Resolve the retrieved UUIDs for all ten recent jobs in one query, preserving
`job_id` so the exact observed answer remains distinguishable:

```sql
WITH recent_jobs AS (
  SELECT id, retrieved_chunk_ids
  FROM answer_jobs
  WHERE status = 'done'
    AND lower(question) LIKE '%deliverance%'
  ORDER BY finished_at DESC
  LIMIT 10
), retrieved AS (
  SELECT rj.id AS job_id,
         jsonb_array_elements_text(coalesce(rj.retrieved_chunk_ids, '[]'::jsonb))::uuid AS chunk_id
  FROM recent_jobs rj
)
SELECT r.job_id, c.id AS chunk_id, c.document_id, d.title, d.author,
       d.citation_mode, d.source_id, s.name AS source_name,
       s.license_status, s.visibility
FROM retrieved r
JOIN chunks c ON c.id = r.chunk_id
JOIN documents d ON d.id = c.document_id
JOIN sources s ON s.id = d.source_id
ORDER BY r.job_id, c.document_id, c.chunk_index;
```

Expected: establish whether each cited/retrieved item had an attributable `documents.author` or `sources.name` before generation.

- [ ] **Step 3: Compare pipeline stages**

Compare:

1. source/document identity from Step 2;
2. stored `citations` author/title fields;
3. names present in `answer` prose;
4. `verified_references` pointers;
5. frontend fields actually rendered for citation chips/cards.

Expected: exactly one earliest stage loses or suppresses the teacher name. Do not propose a renderer fix if the citation object was already nameless, and do not modify generation if the stored object is correct but the UI drops it.

- [ ] **Step 4: Define a discriminating Track 2 test**

Record the smallest fixture that fails at the identified stage and would pass only after a correct fix. Because this is answer-path work, require independent review and mutation proof in Track 2.

---

### Task 6: Reconcile the F5 bypass inventory

**Files:**
- Read: `PLAN.md` F5 section
- Read: `CLAUDE.md` Landmines
- Read: commits `21f5b14`, `21ff62f`, `ceb317f`, and `bc37749`
- Modify after evidence collection: `docs/audits/stabilization_track_1_2026-08-15.md`

**Interfaces:**
- Consumes: original 19-finding F5 trace evidence, six confirmed closures, four later license/visibility fixes, and current served/ingest paths.
- Produces: authoritative table of remaining items with status `closed`, `accepted`, `deferred`, or `needs-build`.

- [ ] **Step 1: Recover the original trace artifact before re-tracing**

Search the current task terminal, Git history, audit documents, and retained task output for the original file:line list. Do not infer the 17 remaining items from the summary count alone.

- [ ] **Step 2: Map known fixes onto the original list**

Run:

```bash
git show --stat --oneline 21f5b14 21ff62f ceb317f bc37749
git show --format=fuller --no-ext-diff 21ff62f -- backend/app/routers/document.py backend/app/routers/library.py backend/app/services/async_answers/producer.py backend/app/services/position_papers.py
git show --format=fuller --no-ext-diff ceb317f -- backend/app/routers/study.py
```

Expected: each claimed closure maps to a specific original finding or is explicitly labeled a distinct later finding.

- [ ] **Step 3: Reconstruct only missing evidence**

If the original file:line artifact cannot be recovered, perform a bounded read-only trace against the F5 exit-criterion control matrix: license/visibility, commentary, attribution, citation, position-paper, verification, shared-ingest chokepoint, and failure logging. Do not repeat already-proven branches merely to regenerate a count.

- [ ] **Step 4: Classify every item**

For each finding record surface, file:line, missing control, consequence, current status, evidence, owner, and revisit trigger. The F5 exit criterion remains unmet until no item is left unclassified.

---

### Task 7: Publish the Track 1 audit and create Track 2 packets

**Files:**
- Create: `docs/audits/stabilization_track_1_2026-08-15.md`
- Do not modify yet: `CLAUDE.md`, `PLAN.md`, `rhemata-status.md`

**Interfaces:**
- Consumes: Tasks 1-6 evidence.
- Produces: durable audit, explicit owner decisions, and bounded Track 2 packet list.

- [ ] **Step 1: Write the audit with exact evidence**

The audit must contain deployment revisions/statuses, smoke results, Prince grouped counts with reconciliation, stale-test failures and cause, deliverance stage comparison, and the complete F5 classification table. It must distinguish observed facts from inferences.

- [ ] **Step 2: Verify the audit**

Run:

```bash
rg -n "T[B]D|T[O]DO|unknown without checking|assumed" docs/audits/stabilization_track_1_2026-08-15.md
git diff --check
git diff -- docs/audits/stabilization_track_1_2026-08-15.md
```

Expected: no placeholders, no copied stale counts, no secrets, and no unsupported completion claim.

- [ ] **Step 3: Commit the audit separately**

Run:

```bash
git add docs/audits/stabilization_track_1_2026-08-15.md
git diff --cached --check
git commit -m "docs: record stabilization track 1 evidence"
```

- [ ] **Step 4: Open bounded Track 2 work from evidence**

Create one independently reviewable packet per demonstrated defect. Do not combine stored-position test maintenance, deliverance attribution, F5 bypasses, teacher-card copy, or harness-doc cleanup unless they share the same failure point and verification command.

## Track 1 completion checkpoint

- [ ] Every Task 1-6 conclusion has fresh evidence.
- [ ] The Prince grouped totals reconcile to the raw log count.
- [ ] The deliverance failure stage is identified rather than guessed.
- [ ] Every F5 finding is classified.
- [ ] No production state was mutated.
- [ ] Track 2 contains only demonstrated, bounded work.
