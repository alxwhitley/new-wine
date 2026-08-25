# New Wine AI Review Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable, issue-level AI review gate that proves New Wine OCR and article completeness and stores only evidence-grounded, pre-approved propositions.

**Architecture:** Add focused modules beside the legacy magazine scripts for schemas/artifacts, OCR review, article review, and proposition review. Keep `extract_magazine.py` as the compatibility entry point and `shared_ingest.ingest_document()` as the only document-writing chokepoint; pass a validated approved proposition set through its existing atomic transaction.

**Tech Stack:** Python 3, PyMuPDF, Google GenAI, Google Document AI, Groq structured outputs, pytest/unittest mocks, existing Rhemata chunking/embedding/proposition modules.

**Spec:** `docs/superpowers/specs/2026-08-25-new-wine-ai-review-design.md`

## Global Constraints

- No production database write, paid benchmark, backlog OCR run, file move, rename, archive, or deletion is authorized by implementing this plan.
- Every paid model run and every production database write requires a separately named, attended approval.
- Initial OCR selection is blocked until a blind benchmark passes severe failures and good controls and Alex accepts the winner.
- Every page is reviewed; a failed page gets exactly one targeted repair; a second failure quarantines the entire issue.
- Every article is checked against the complete verified issue transcript.
- Every stored proposition must exactly match the approved artifact and have a valid supporting evidence span.
- `scripts/shared_ingest.py` remains the only magazine document-writing path.
- Existing callers that do not provide approved propositions retain byte-identical behavior.
- OCR/mixed-author magazine material remains quote-ineligible.
- Runtime review stages do not automatically promote or move issue files.

---

### Task 1: Blind OCR benchmark harness

**Files:**
- Create: `scripts/magazine_review/__init__.py`
- Create: `scripts/magazine_review/benchmark.py`
- Create: `scripts/benchmark_magazine_ocr.py`
- Create: `scripts/test_magazine_ocr_benchmark.py`

**Interfaces:**
- Consumes: a JSON fixture manifest containing PDF path, PDF SHA-256, page number, fixture class (`severe_failure` or `good_control`), and human scoring fields.
- Produces: `BenchmarkCandidate`, `BenchmarkPageResult`, `BenchmarkReport`, `run_benchmark(manifest_path, providers, output_path)`, and a blind report whose candidates are labeled A/B/C rather than by provider.

- [ ] **Step 1: Write failing tests for immutable fixture identity and blind labels**

```python
def test_fixture_hash_mismatch_stops_before_provider_call(tmp_path):
    provider = FakeProvider()
    with pytest.raises(BenchmarkInputError, match="pdf_sha256"):
        run_benchmark(bad_manifest, [provider], tmp_path / "report.json")
    assert provider.calls == []

def test_blind_report_hides_provider_names(tmp_path):
    report = run_benchmark(valid_manifest, fake_providers, tmp_path / "report.json")
    encoded = json.dumps(report.blind_view())
    assert "gemini" not in encoded.lower()
    assert "document ai" not in encoded.lower()
    assert set(report.blind_view()["candidates"]) == {"A", "B", "C"}
```

- [ ] **Step 2: Run the benchmark unit tests and confirm the new imports fail**

Run: `pytest -q scripts/test_magazine_ocr_benchmark.py`

Expected: FAIL because `magazine_review.benchmark` does not exist.

- [ ] **Step 3: Implement fixture validation, provider injection, cost capture, and blind serialization**

```python
@dataclass(frozen=True)
class BenchmarkCandidate:
    provider: str
    model: str

def run_benchmark(manifest_path: Path, providers: Sequence[OCRProvider], output_path: Path) -> BenchmarkReport:
    fixtures = load_and_verify_fixtures(manifest_path)
    results = [provider.transcribe(fixture) for fixture in fixtures for provider in providers]
    report = BenchmarkReport.from_results(fixtures, results)
    output_path.write_text(report.to_json(), encoding="utf-8")
    return report
```

The three adapters are configured for `gemini-2.5-flash`, `gemini-3.6-flash`,
and a caller-supplied Enterprise Document OCR processor ID. The CLI requires
`--manifest` and `--output`; it has no directory-wide mode.

- [ ] **Step 4: Test reconciliation and the no-call dry run**

Run: `pytest -q scripts/test_magazine_ocr_benchmark.py`

Expected: PASS, including `candidate_count * fixture_count == result_count`,
usage/cost fields for every result, and `--dry-run` making zero provider calls.

- [ ] **Step 5: Commit the benchmark harness**

```bash
git add scripts/magazine_review/__init__.py scripts/magazine_review/benchmark.py scripts/benchmark_magazine_ocr.py scripts/test_magazine_ocr_benchmark.py
git commit -m "feat(magazine): add blind OCR benchmark harness"
```

**Attended checkpoint:** Before any real benchmark call, name the exact pages,
verify their hashes, calculate the maximum provider cost, and obtain Alex's
explicit approval. Record Alex's accepted winner in a reviewed benchmark
report; do not infer a winner from aggregate cost or model reputation.

### Task 2: Review schemas, validation, and resumable artifacts

**Files:**
- Create: `scripts/magazine_review/schemas.py`
- Create: `scripts/magazine_review/artifacts.py`
- Create: `scripts/test_magazine_review_artifacts.py`

**Interfaces:**
- Consumes: PDF/page/article/proposition evidence and stage configuration.
- Produces: `OCRManifest`, `ArticleManifest`, `PropositionReview`, `IssueDecision`, `StageIdentity`, `load_valid_artifact(path, expected_identity)`, and `write_artifact(path, value)`.

- [ ] **Step 1: Write failing schema tests for all fail-closed invariants**

```python
@pytest.mark.parametrize("mutation", [
    "missing_page", "second_repair", "bad_article_span", "bad_evidence_offset",
    "noncontiguous_proposition_index", "unsupported_proposition",
])
def test_invalid_evidence_cannot_approve(valid_issue_artifacts, mutation):
    damaged = mutate(valid_issue_artifacts, mutation)
    with pytest.raises(ArtifactValidationError):
        IssueDecision.approve(damaged)
```

- [ ] **Step 2: Run tests and verify schema imports fail**

Run: `pytest -q scripts/test_magazine_review_artifacts.py`

Expected: FAIL because the schema module is absent.

- [ ] **Step 3: Implement frozen dataclasses and explicit `validate()` methods**

```python
@dataclass(frozen=True)
class PropositionEvidence:
    proposition_index: int
    content: str
    evidence_text: str
    evidence_start: int
    evidence_end: int
    supported: bool
    missing_qualification: bool
    overstatement: bool
    attribution_ok: bool

    def validate(self, article_text: str) -> None:
        if article_text[self.evidence_start:self.evidence_end] != self.evidence_text:
            raise ArtifactValidationError("evidence_offset_mismatch")
        if not self.supported or self.missing_qualification or self.overstatement or not self.attribution_ok:
            raise ArtifactValidationError("proposition_not_supported")
```

`StageIdentity` hashes canonical JSON containing schema version, complete input
hashes, model ID, prompt fingerprint, and renderer settings. A stale or
malformed artifact raises `ArtifactValidationError`; it never returns a truthy
partial result.

- [ ] **Step 4: Implement direct writes and exact reload verification**

`write_artifact()` writes canonical UTF-8 JSON, flushes and `fsync()`s it, then
reopens the same path and verifies its SHA-256. It does not rename, replace,
move, or delete any path.

- [ ] **Step 5: Run artifact tests**

Run: `pytest -q scripts/test_magazine_review_artifacts.py`

Expected: PASS for round trips, stale identities, page-count reconciliation,
one-repair ceiling, evidence offsets, contiguous indices, and fail-closed issue
approval.

- [ ] **Step 6: Commit schemas and artifact handling**

```bash
git add scripts/magazine_review/schemas.py scripts/magazine_review/artifacts.py scripts/test_magazine_review_artifacts.py
git commit -m "feat(magazine): add fail-closed review artifacts"
```

### Task 3: Page OCR review and single repair

**Files:**
- Create: `scripts/magazine_review/ocr.py`
- Create: `scripts/test_magazine_ocr_review.py`
- Modify: `scripts/extract_magazine.py`

**Interfaces:**
- Consumes: PDF path, accepted benchmark configuration, `OCRProvider`, `PageReviewer`, and an issue artifact directory.
- Produces: `review_issue_ocr(pdf_path, config, artifact_dir) -> OCRManifest` and `VerifiedIssueTranscript`.

- [ ] **Step 1: Write failing tests for every-page review and the repair ceiling**

```python
def test_reviews_ad_page_and_repairs_only_failed_page(two_page_pdf):
    reviewer = FakeReviewer([PASS, FAIL, PASS])
    repair = FakeOCRProvider(text="repaired page two")
    manifest = review_issue_ocr(two_page_pdf, config(repair=repair), artifact_dir)
    assert reviewer.page_numbers == [1, 2, 2]
    assert repair.page_numbers == [2]
    assert manifest.pages[1].repair_attempts == 1

def test_second_failure_quarantines_entire_issue(two_page_pdf):
    manifest = review_issue_ocr(two_page_pdf, config(reviewer=always_fail), artifact_dir)
    assert manifest.status == "quarantined"
    assert manifest.quarantine_reasons == ["page:1:ocr_incomplete_after_repair"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest -q scripts/test_magazine_ocr_review.py`

Expected: FAIL because `review_issue_ocr` is not implemented.

- [ ] **Step 3: Implement deterministic rendering and initial OCR adapters**

Render every page at fixed DPI/colorspace, hash the image bytes, and require
ordered pages `1..pdf.page_count`. Initial OCR provider selection must come
from the accepted benchmark configuration, not a silent default.

- [ ] **Step 4: Implement Gemini 3.6 Flash completeness review with structured output**

```python
class PageReview(TypedDict):
    complete: bool
    missing_regions: list[str]
    reading_order_errors: list[str]
    duplicated_text: list[str]
    reason: str
```

The prompt tells the reviewer that advertisements and non-article material are
still content and that `complete=true` is forbidden if any visible text region
is absent or reordered materially.

- [ ] **Step 5: Enforce exactly one targeted repair and build the verified transcript**

Only a failed page enters repair. The repaired text is reviewed once; failure
sets the issue to `quarantined` and stops article/proposition stages. Concatenate
accepted pages with stable page delimiters and record each page's transcript
offsets.

- [ ] **Step 6: Keep the legacy entry point compatible**

Change `extract_magazine.py` to delegate its page stage to
`review_issue_ocr()` only when `--review-pipeline --artifact-dir PATH` is
supplied. The existing command behavior remains unchanged until later rollout;
replace the retired Groq constant in the new path with
`openai/gpt-oss-120b`.

- [ ] **Step 7: Run OCR tests**

Run: `pytest -q scripts/test_magazine_ocr_review.py scripts/test_magazine_review_artifacts.py`

Expected: PASS with exact call counts, complete page coverage, deterministic
transcript offsets, usage/cost reconciliation, and no provider calls when a
matching manifest resumes.

- [ ] **Step 8: Commit OCR review**

```bash
git add scripts/magazine_review/ocr.py scripts/test_magazine_ocr_review.py scripts/extract_magazine.py
git commit -m "feat(magazine): review every OCR page with one repair"
```

### Task 4: Issue-wide article segmentation and completeness review

**Files:**
- Create: `scripts/magazine_review/articles.py`
- Create: `scripts/test_magazine_article_review.py`

**Interfaces:**
- Consumes: `VerifiedIssueTranscript`, issue metadata, and an injected structured-output model client.
- Produces: `segment_articles(transcript, client) -> ArticleManifest` and `review_articles_against_issue(transcript, manifest, client) -> ArticleManifest`.

- [ ] **Step 1: Write failing boundary and issue-wide-context tests**

```python
def test_mid_thought_ending_quarantines_issue(verified_issue, client):
    client.queue(segmentation_with_truncated_article, review_flags_mid_thought)
    manifest = review_articles_against_issue(verified_issue, segment_articles(verified_issue, client), client)
    assert manifest.status == "quarantined"
    assert "ending_mid_thought" in manifest.articles[0].reasons

def test_reviewer_receives_complete_issue_and_all_articles(verified_issue, client):
    review_articles_against_issue(verified_issue, two_article_manifest, client)
    assert client.last_request["issue_transcript"] == verified_issue.text
    assert len(client.last_request["articles"]) == 2
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest -q scripts/test_magazine_article_review.py`

Expected: FAIL because the article review module is absent.

- [ ] **Step 3: Implement GPT-OSS structured segmentation**

Use `openai/gpt-oss-120b` with low reasoning and strict JSON. Require title,
author, ordered source pages, transcript spans, and exact text. Reject unknown
pages, overlapping identities, out-of-bounds spans, and text that does not
round-trip.

- [ ] **Step 4: Implement fresh-context semantic review**

Use a separate request at medium reasoning. For each article require boolean
and reasons for genuine beginning, coherent ending, transition integrity,
omission, duplication, adjacent bleed, and attribution. Any non-passing field
quarantines the issue.

- [ ] **Step 5: Run tests**

Run: `pytest -q scripts/test_magazine_article_review.py scripts/test_magazine_review_artifacts.py`

Expected: PASS, including split-across-many-pages, article continuation,
advertisement interruption, missing final paragraph, duplicated page, and
adjacent-byline fixtures.

- [ ] **Step 6: Commit article review**

```bash
git add scripts/magazine_review/articles.py scripts/test_magazine_article_review.py
git commit -m "feat(magazine): add issue-wide article completeness review"
```

### Task 5: Proposition preview and exact evidence review

**Files:**
- Create: `scripts/magazine_review/proposition_review.py`
- Create: `scripts/test_magazine_proposition_review.py`

**Interfaces:**
- Consumes: a passing `ArticleManifest` and existing `propositions.extract_propositions_with_evidence()`.
- Produces: `review_issue_propositions(article_manifest, reviewer) -> PropositionReview` and `approved_propositions_for(article_id) -> list[dict]`.

- [ ] **Step 1: Write failing tests for zero propositions and evidence fidelity**

```python
def test_substantive_article_with_zero_propositions_quarantines(article_manifest):
    result = review_issue_propositions(article_manifest, extractor=lambda **_: [], reviewer=unused)
    assert result.status == "quarantined"
    assert result.reasons == ["article:a1:zero_propositions"]

def test_evidence_must_round_trip(article_manifest):
    result = review_issue_propositions(article_manifest, extractor=one_prop, reviewer=bad_offset_review)
    assert result.status == "quarantined"
    assert "evidence_offset_mismatch" in result.reasons
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest -q scripts/test_magazine_proposition_review.py`

Expected: FAIL because proposition review is absent.

- [ ] **Step 3: Integrate the current v3.1 extraction evidence path**

Call `extract_propositions_with_evidence(article.text, doc_id=article.id,
speaker=article.author, prompt_version="v3.1")`. Persist exact output, model,
usage, cost, and reference-grounding totals. Do not modify proposition text in
the review layer.

- [ ] **Step 4: Implement deterministic checks before semantic calls**

Reject empty content, duplicate/noncontiguous indices, malformed extraction,
empty articles, and any returned evidence span that does not exactly slice the
article. These failures make no second semantic-review call.

- [ ] **Step 5: Implement structured semantic support review**

For each proposition, require exact evidence text and offsets plus `supported`,
`missing_qualification`, `overstatement`, and `attribution_ok`. The request uses
a fresh context containing only the verified article and its proposition set.
Any failed proposition quarantines the entire issue.

- [ ] **Step 6: Run tests**

Run: `pytest -q scripts/test_magazine_proposition_review.py scripts/test_magazine_review_artifacts.py`

Expected: PASS for faithful paraphrase, unsupported inference, overstatement,
lost qualification, attribution mismatch, invalid offsets, and zero-output
fixtures.

- [ ] **Step 7: Commit proposition review**

```bash
git add scripts/magazine_review/proposition_review.py scripts/test_magazine_proposition_review.py
git commit -m "feat(magazine): ground reviewed propositions in exact evidence"
```

### Task 6: Review orchestrator and fail-closed issue decision

**Files:**
- Create: `scripts/review_magazine_issue.py`
- Create: `scripts/test_review_magazine_issue.py`

**Interfaces:**
- Consumes: one named PDF, accepted benchmark configuration, and an artifact directory.
- Produces: `review_issue(pdf_path, artifact_dir, config) -> IssueDecision` and CLI states `approved`, `quarantined`, or `pipeline_error`.

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_ocr_quarantine_prevents_downstream_calls(orchestrator):
    decision = orchestrator.run(ocr_result=quarantined_ocr)
    assert decision.state == "quarantined"
    assert orchestrator.article_calls == 0
    assert orchestrator.proposition_calls == 0

def test_technical_exception_is_not_content_quarantine(orchestrator):
    decision = orchestrator.run(ocr_exception=TimeoutError("provider timeout"))
    assert decision.state == "pipeline_error"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest -q scripts/test_review_magazine_issue.py`

Expected: FAIL because the CLI/orchestrator does not exist.

- [ ] **Step 3: Implement ordered stage execution and resume**

The CLI requires `--pdf`, `--artifact-dir`, and `--benchmark-decision`. It
validates one named issue, loads only fingerprint-matching artifacts, executes
the first missing stage, and stops immediately on quarantine or technical
error. It has no production-write option.

- [ ] **Step 4: Implement hard accounting and cost output**

`IssueDecision` reconciles PDF pages to OCR pages, article manifest entries to
reviewed articles, extracted propositions to reviewed propositions, and all
stage usage/cost totals. Print one compact summary with attempted, passed,
repaired, quarantined, and errored counts.

- [ ] **Step 5: Run orchestration tests**

Run: `pytest -q scripts/test_review_magazine_issue.py scripts/test_magazine_*.py`

Expected: PASS for clean approval, every stage's quarantine, technical errors,
stale cache invalidation, exact one-stage resume, and total reconciliation.

- [ ] **Step 6: Commit the orchestrator**

```bash
git add scripts/review_magazine_issue.py scripts/test_review_magazine_issue.py
git commit -m "feat(magazine): orchestrate resumable issue review"
```

### Task 7: Store approved propositions through the atomic ingestion path

**Files:**
- Modify: `scripts/propositions.py`
- Modify: `scripts/shared_ingest.py`
- Modify: `scripts/ingest_magazine.py`
- Create: `scripts/test_magazine_approved_proposition_ingest.py`
- Modify: `scripts/test_shared_ingest.py`
- Modify: `scripts/test_propositions.py`

**Interfaces:**
- Consumes: `approved_propositions: Optional[list[dict]]`, plus approved model, prompt version, prompt fingerprint, article hash, and issue-decision hash.
- Produces: unchanged `shared_ingest.ingest_document()` result vocabulary and exact stored proposition content.

- [ ] **Step 1: Write failing tests proving no regeneration and byte identity**

```python
def test_approved_propositions_bypass_generation_but_not_storage(monkeypatch):
    monkeypatch.setattr(propositions, "extract_propositions", forbidden_call)
    result = propositions.process_document(
        conn, doc_id, source_id, article_text, embed,
        prompt_version="v3.1", approved_propositions=approved,
    )
    assert result == "stored:2"
    assert stored_contents(conn, doc_id) == [p["content"] for p in approved]

def test_manifest_model_or_fingerprint_drift_refuses_before_db(tmp_path):
    with pytest.raises(ApprovedArtifactMismatch):
        ingest_article(reviewed_md, issue, approved_artifact=stale_artifact)
    assert db.calls == []
```

- [ ] **Step 2: Run focused tests and verify signature failures**

Run: `pytest -q scripts/test_propositions.py scripts/test_shared_ingest.py scripts/test_magazine_approved_proposition_ingest.py`

Expected: FAIL because `approved_propositions` is not accepted.

- [ ] **Step 3: Extend `propositions.process_document()` narrowly**

Add `approved_propositions: Optional[List[dict]] = None`. Keep source-license,
named-source, minimum-word, prompt-version, fingerprint, and model checks in
their existing order. Set:

```python
props = (
    validate_approved_propositions(approved_propositions, prompt_version)
    if approved_propositions is not None
    else extract_propositions(text, doc_id=document_id, speaker=speaker, prompt_version=prompt_version)
)
```

Then use the existing `store_propositions()` path and chunk IDs unchanged.
Validation requires current `EXTRACTION_MODEL`, current
`prompt_fingerprint(prompt_version)`, contiguous indices, nonempty content,
and the reviewed article hash.

- [ ] **Step 4: Thread the optional input through `shared_ingest.ingest_document()`**

Add the optional keyword at the end of the signature and pass it to
`process_document()`. Existing call tests must prove that omission still calls
the extractor exactly once and returns the existing result shapes.

- [ ] **Step 5: Gate magazine ingestion on `issue_decision.json`**

`ingest_magazine.py` requires `--artifact-dir` for reviewed ingestion, validates
`state == "approved"`, PDF/article/proposition hashes, current prompt/model
provenance, and all article IDs before opening a database connection. It passes
the exact approved list per article. Dry run displays counts and hashes but
makes no database or embedding calls.

- [ ] **Step 6: Disable automatic moves in the reviewed path**

The reviewed path always calls `ingest_issue(..., move_when_done=False)` and
prints that source promotion remains a separate explicit operation. Do not
alter or delete legacy directories.

- [ ] **Step 7: Run the ingestion regression suite**

Run: `pytest -q scripts/test_propositions.py scripts/test_shared_ingest.py scripts/test_magazine_approved_proposition_ingest.py`

Expected: PASS for unchanged legacy callers, exact approved output, zero
generation calls, fail-before-DB stale artifacts, transaction rollback,
provenance stamping, chunk linkage, and no automatic moves.

- [ ] **Step 8: Commit the ingestion bridge**

```bash
git add scripts/propositions.py scripts/shared_ingest.py scripts/ingest_magazine.py scripts/test_propositions.py scripts/test_shared_ingest.py scripts/test_magazine_approved_proposition_ingest.py
git commit -m "feat(magazine): ingest exact reviewed propositions"
```

### Task 8: No-write end-to-end proof and operating documentation

**Files:**
- Create: `scripts/fixtures/magazine_review/clean_issue.json`
- Create: `scripts/fixtures/magazine_review/ocr_failure_issue.json`
- Create: `scripts/test_magazine_review_end_to_end.py`
- Modify: `docs/roadmap.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: all review modules with fake providers and fixed page/article evidence.
- Produces: reproducible no-write proof and durable operating invariants.

- [ ] **Step 1: Add an end-to-end failing test with fake providers**

```python
def test_clean_issue_approves_and_dry_ingest_matches_exact_propositions(tmp_path):
    decision = run_fixture("clean_issue", tmp_path)
    assert decision.state == "approved"
    preview = preview_ingest(decision)
    assert preview.proposition_texts == fixture_expected_propositions()
    assert preview.db_calls == 0

def test_unrepaired_ocr_failure_blocks_entire_issue(tmp_path):
    decision = run_fixture("ocr_failure_issue", tmp_path)
    assert decision.state == "quarantined"
    assert decision.eligible_article_count == 0
```

- [ ] **Step 2: Run the end-to-end test and verify fixture failure**

Run: `pytest -q scripts/test_magazine_review_end_to_end.py`

Expected: FAIL until fixtures and adapters are complete.

- [ ] **Step 3: Add complete deterministic fixtures and make the tests pass**

Fixtures include visible page text, initial OCR, reviewer results, repaired OCR,
verified transcript offsets, article spans, proposition outputs, evidence
offsets, model usage, and costs. They contain no live credentials and make no
network calls.

- [ ] **Step 4: Run one coherent repository verification cycle**

Run: `pytest -q scripts/test_magazine_*.py scripts/test_review_magazine_issue.py scripts/test_shared_ingest.py scripts/test_propositions.py`

Expected: all tests PASS; no network calls, database calls, or source file
moves occur.

- [ ] **Step 5: Record the durable operating contract**

Update `CLAUDE.md` with the issue-level fail-closed review, exact-proposition,
attended-write, and no-automatic-file-move invariants. Update A2 in
`docs/roadmap.md` to say the harness is built but the trigger remains closed
until the paid blind benchmark is run and Alex accepts its winner.

- [ ] **Step 6: Commit docs separately from build commits**

```bash
git add CLAUDE.md docs/roadmap.md
git commit -m "docs: govern New Wine review rollout"
```

## Execution stop condition

Stop after Task 8 when the fake-provider suite proves the complete no-write
flow and the A2 roadmap trigger is still closed. Do not run the paid benchmark,
review a real backlog issue, write to production, or move any magazine files
without the next explicit approval.
