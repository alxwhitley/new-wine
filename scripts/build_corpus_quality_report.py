#!/usr/bin/env python3
"""
build_corpus_quality_report.py — renders the Markdown report from the JSON
produced by score_corpus_quality.py. Pure data processing, no DB access.

CLI:
    python3 scripts/build_corpus_quality_report.py --date 2026-07-24
"""

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from score_corpus_quality import describe_best, describe_middle, describe_worst, distribution, RANDOM_SEED  # noqa: E402

SOURCE_TYPE_LABEL = {
    "sermon": "Sermon transcript",
    "commentary": "Commentary",
    "book": "Book",
    "magazine_article": "Magazine article",
    "paper": "Paper",
    "position_paper": "Position paper",
    "background": "Background / lexicon",
    "other": "Other",
    "manual": "Manual",
}

METRICS = [
    ("attribution_score", "Attribution risk"),
    ("packaging_score", "Signal density (packaging)"),
    ("integrity_score", "Text integrity problems"),
    ("composite", "Composite (0-100 percentile avg)"),
]


def dist_table_row(label, dist):
    if dist is None:
        return f"| {label} | - | - | - | - | - | - | - | - |"
    return (
        f"| {label} | {dist['n']} | {dist['min']} | {dist['p10']} | {dist['p25']} | "
        f"{dist['median']} | {dist['p75']} | {dist['p90']} | {dist['max']} |"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-24")
    args = parser.parse_args()

    json_path = ROOT / "docs" / "audits" / f"corpus_quality_scores_{args.date}.json"
    data = json.load(open(json_path))
    docs = data["documents"]
    by_id = {d["id"]: d for d in docs}

    lines = []
    A = lines.append

    A(f"# Corpus Quality Measurement — Phase 1 Report ({args.date})")
    A("")
    A("Read-only measurement. No deletions, no visibility changes, no writes to any table.")
    A("")
    A("## Scope")
    A("")
    A(f"- In-scope documents scored: **{data['scored_count']}**")
    A("- Excluded: the Precept Austin source (`698e0596-a9c6-4890-958d-9199f1b8f762`), per standing source-level exclusion.")
    A("- All other documents in the corpus are in scope, including 4 STEPBible lexicon/background documents — see caveat below.")
    A("")

    A("## Methodology — signal sets actually used")
    A("")
    A("No LLM calls this phase. All three dimensions are computed from countable, deterministic signals only.")
    A("")
    A("**1. Attribution risk** (higher = more likely the single-teacher attribution is wrong or incomplete)")
    A("- Title contains a guest/second-speaker indicator (`w/`, `ft.`/`feat.`, \"interview\", \"panel\", \"Q&A\", \"conversation with\", \"guest\", \"talks with\", `& Firstname Lastname`) → +3")
    A("- Title contains \"with Firstname Lastname\" (weaker pattern, only scored if the above didn't already fire) → +2")
    A("- Opening ~300 words contain guest-introduction language (\"our guest\", \"please welcome\", \"joining me/us\", \"my guest today\", \"welcome to the show/podcast\", \"today's guest\", \"special guest\") → +2 per distinct phrase, capped at +6")
    A("- Source is classified a **multi-voice channel** rather than a single-teacher archive or book → +3. Classification is source-level and countable: ≥3 documents, ≥3 distinct non-null `author` values, and <50% of the source's documents have `author == source_name` → multi-voice channel. ≥80% match rate, or `source_type == 'book'` → single-teacher archive. Otherwise ambiguous (no bonus).")
    A("")
    A("**2. Signal density** (packaging_score; higher = more packaging relative to teaching)")
    A("- Platform/CTA/greeting language density per 1000 words (\"subscribe\", \"link in the description\", \"hit the bell\", \"welcome back\", \"let's pray\", \"before we get started\", \"follow us on\", \"sign up\", \"donate\", \"click the link\", \"smash that\", URLs, etc. — 27-phrase list)")
    A("- + 40 × sentence-repetition rate (exact-duplicate sentences ≥4 words, as a fraction of all sentences ≥4 words)")
    A("- − scripture-reference density per 1000 words (from `documents.bible_references`, already extracted corpus-wide; capped at 15 so very citation-dense documents don't runaway-dominate the credit)")
    A("")
    A("**3. Text integrity** (integrity_score; higher = more integrity problems)")
    A("- Document does not end on terminal punctuation → +25")
    A("- Non-word/non-standard-punctuation character ratio × 400")
    A("- Missing chunk-index gaps × 6 per gap (0 found corpus-wide — see caveat)")
    A("- Near-empty-chunk ratio (chunks <40 chars) × 30")
    A("- Repeated-non-digit-character-run rate (runs of 5+, per 10,000 chars, floored at a 2,000-char denominator) × 3 — digits are excluded because some sources (STEPBible verse-code citations) legitimately contain long digit runs that are not scan/OCR garbage; this was caught as a false-positive class during verification and fixed before this report was built (see caveats).")
    A("")
    A("**Near-duplicates** (reported separately, not folded into the three scores): 5-word-shingle MinHash (48 hash functions, deterministic seed), compared pairwise **within the same source only** — cross-source comparison was out of scope for this pass. Similarity ≥0.5 reported as a candidate; ≥0.85 as likely-duplicate.")
    A("")
    A("**Composite score** (used only to rank the worst/middle/best lists): each dimension's raw score is converted to a 0–100 percentile rank across the 1,641 in-scope documents, then the three percentile ranks are averaged unweighted. This is a methodology choice, not specified by the original brief — a document that is extremely bad on one axis and fine on the other two will rank as moderately bad overall, not catastrophically bad. The per-dimension distributions below are the way to see axis-specific worst cases.")
    A("")

    A("## Caveats found during verification — read before trusting the numbers")
    A("")
    A("- **A real scoring bug was caught and fixed before this report was generated.** The first version of the repeated-character-run signal matched digit runs, which fired systematically on HistoricalChristianFaith's internal verse-reference codes (e.g. `revelation 5000001`) — a citation format, not scan garbage. It also used a raw count instead of a length-normalized rate, which let the corpus's handful of 1–2 million-word documents dominate the \"worst integrity\" list purely by being long. Both fixed (digits excluded from the pattern; rate-per-10k-chars with a length floor) before any of the numbers below were generated. Flagged here per this project's standing practice of reporting bugs found and fixed in-session rather than smoothing over them.")
    A("- **The 4 STEPBible lexicon/background documents (`source_type='background'`) are structurally different from teaching content** and several signals don't cleanly apply to them: they are one-entry-per-chunk reference databases (10,258 chunks / 420,949 words for the Hebrew lexicon alone), so \"ends without terminal punctuation\" fires trivially (a dictionary entry doesn't end in a period) and scripture-reference density is meaningless (a lexicon entry isn't a scripture citation). Their integrity/packaging scores should not be read the same way as a sermon's.")
    A("- **HistoricalChristianFaith Commentaries Database documents vary in length by five orders of magnitude** — from a single ~150-character cross-reference stub (`Anselm of Laon`) to a 2.66-million-word collected-works dump (`Thomas Aquinas`, 7,657 chunks). \"One document\" is not a consistent unit of content for this source. Scores for this source's documents should be read per-document, not assumed comparable to a sermon transcript.")
    A("- **A genuine, actionable ingestion-pipeline finding, not just a low score:** 29 of the 33 documents carrying `source_name = 'New Wine Magazine'` (this is the entire `magazine_article` population) end their stored text with a leaked JSON/markdown code-fence artifact — literally `\"\\n}\\n\\`\\`\\`` or `\"\\n}` — from the Gemini/Groq extraction pipeline (`extract_magazine.py`). The article text itself reads fine; only the last few characters of the last chunk carry the artifact. This is a well-scoped, mechanically fixable defect (strip the trailing pattern and re-ingest, or patch the approved `.md` source files), not a content-quality problem. It is a large part of why New Wine Magazine articles cluster at the top of the worst-overall list below — worth fixing on its own before re-running any future pass, since it will otherwise keep re-flagging clean content.")
    A("- **A second, separate, corpus-wide ingestion-pipeline finding, verified directly against the DB (not just the JSON snippet — the JSON's stored 120-char tail undercounted this by more than half):** at least 19 public-domain books end their stored text with a leaked CCEL website artifact — either an ebook-store promo footer (\"Visit the Kindle store or see http://www.ccel.org/...\") or a bare \"Index of Scripture References\" page-number dump, sometimes just a trailing bare page number with no other text. This is NOT limited to the 13 documents whose `source_id` resolves to the \"Christian Classics Ethereal Library\" source row — it also hits books correctly attributed to their real individual author (Andrew Murray ×4, E.M. Bounds ×4, Charles G. Finney ×2, John Wesley ×1, Brother Lawrence ×1, R.A. Torrey ×1, An Unknown Christian ×1), because all of them were scraped through the same CCEL pipeline (`scripts/scrape_ccel.py` / `download_ccel.py`) regardless of which source they ultimately resolved to. Confirmed affected titles: *The School of Obedience*, *Prayer and Praying Men*, *Purpose in Prayer*, *Absolute Surrender*, *The Weapon of Prayer*, *The Two Covenants*, *The Deeper Christian Life*, *The Reality of Prayer*, *How To Pray*, *The True Vine*, *The Journal of John Wesley*, *Lectures to Professing Christians*, *The Kneeling Christian*, *Power From On High*, *With Christ in the School of Prayer*, *The Practice of the Presence of God*, *The Essentials of Prayer*, *Sermons on Several Occasions*, *The Necessity of Prayer*. At least one more (E.M. Bounds' *Power Through Prayer*) shows the same bare-trailing-page-number pattern and is very likely the same root cause, not separately confirmed. Same fix shape as the New Wine finding: strip the trailing pattern, re-ingest.")
    A("- **The multi-voice-channel classification (attribution-risk signal #4) conflates two different risks and should not be read as \"this source has the Savchuk/Bevere co-host problem.\"** It fires whenever a source has ≥3 distinct non-null `author` values and a low author/source-name match rate — true both for a channel with real, uncredited co-speakers (the risk this signal is meant to catch) AND for a library/anthology source that correctly attributes each document to its own real author but groups them under one umbrella source row (Christian Classics Ethereal Library, HistoricalChristianFaith Commentaries Database, New Wine Magazine's un-resolved articles). For the latter group the underlying `author` field is very likely already correct — grouping under one source is a cataloging fact, not an attribution error. This signal cannot currently tell the two cases apart from countable signals alone; 18 of the 40 documents in the worst-overall list below are flagged **only** via this bonus, and most of those are anthology/library documents, not genuine guest-speaker risk. Treat this as the weakest of the four attribution-risk signals and verify manually before acting on it for any given source.")
    A("- **One single-chunk document (`CLF Church` — \"Prophetic Equipping via Zoom\", 102 words) contains no teaching content at all** — its stored text is a Zoom meeting link and passcode, nothing else. This is the single most severe finding in the corpus by a different kind of severity than a score number conveys: it isn't a badly-scored teaching document, it's not a teaching document.")
    A("- **Near-duplicate detection is scoped to within-source pairs only.** A document near-duplicate across two different sources (e.g. the same sermon re-uploaded under a slightly different channel/source) would not be caught by this pass.")
    A("- **Zero chunk-index gaps found corpus-wide.** Migration 061's `UNIQUE(document_id, chunk_index)` constraint (closed 2026-07-13 per PLAN.md) appears to hold; this signal currently contributes nothing to any score but is kept for future-proofing.")
    A("")

    # ── Grouped by material type ────────────────────────────────────────
    A("## Grouped results — by material type (`source_type`)")
    A("")
    A("User's suggested categories map onto this corpus's actual `source_type` values as: transcript → `sermon`; book → `book`; article → `paper`/`position_paper`; magazine → `magazine_article`. `commentary` and `background` (lexicon) are large enough in this corpus (493 and 4 docs) to warrant their own rows rather than folding into \"other\".")
    A("")
    by_type = defaultdict(list)
    for d in docs:
        by_type[d["source_type"]].append(d)
    for metric_key, metric_label in METRICS:
        A(f"### {metric_label}")
        A("")
        A("| Material type | n | min | p10 | p25 | median | p75 | p90 | max |")
        A("|---|---|---|---|---|---|---|---|---|")
        for st in sorted(by_type, key=lambda k: -len(by_type[k])):
            label = SOURCE_TYPE_LABEL.get(st, st)
            dist = distribution([d[metric_key] for d in by_type[st]])
            A(dist_table_row(label, dist))
        A("")

    # ── Grouped by source ────────────────────────────────────────────────
    A("## Grouped results — by source")
    A("")
    by_source = defaultdict(list)
    for d in docs:
        by_source[d["source_name"] or "(unassigned)"].append(d)
    large_sources = {k: v for k, v in by_source.items() if len(v) >= 3}
    small_sources = {k: v for k, v in by_source.items() if len(v) < 3}
    A(f"{len(large_sources)} sources have ≥3 in-scope documents (shown as distributions below); "
      f"{len(small_sources)} sources have 1-2 documents (listed individually after, since a distribution over 1-2 points isn't meaningful).")
    A("")
    for metric_key, metric_label in METRICS:
        A(f"### {metric_label}")
        A("")
        A("| Source | n | min | p10 | p25 | median | p75 | p90 | max |")
        A("|---|---|---|---|---|---|---|---|---|")
        for src in sorted(large_sources, key=lambda k: -len(large_sources[k])):
            dist = distribution([d[metric_key] for d in large_sources[src]])
            A(dist_table_row(src, dist))
        A("")

    A("### Small sources (1-2 documents) — raw composite scores, not a distribution")
    A("")
    A("| Source | Document | Composite |")
    A("|---|---|---|")
    for src in sorted(small_sources):
        for d in small_sources[src]:
            A(f"| {src} | {d['title'][:60]} | {d['composite']:.1f} |")
    A("")

    # ── Duplicates ───────────────────────────────────────────────────────
    A("## Suspected duplicates (separate list)")
    A("")
    A("Within-source MinHash candidates, similarity ≥0.5. These are a separate, easier decision from the quality scores above.")
    A("")
    A("| Similarity | Source | Title A | Title B |")
    A("|---|---|---|---|")
    for p in data["duplicate_pairs"]:
        tag = "likely duplicate" if p["similarity"] >= 0.85 else "candidate"
        A(f"| {p['similarity']:.3f} ({tag}) | {p['source']} | {p['title_a'][:55]} | {p['title_b'][:55]} |")
    A("")

    # ── Worst / middle / best ───────────────────────────────────────────
    ranked = sorted(docs, key=lambda d: -d["composite"])
    worst_40 = ranked[:40]

    mid_band = [d for d in docs if 40 <= d["composite"] <= 60]
    rng = random.Random(RANDOM_SEED)
    middle_15 = rng.sample(mid_band, min(15, len(mid_band)))

    best_15 = sorted(docs, key=lambda d: d["composite"])[:15]

    def doc_line(d, describe_fn):
        m = d  # json record already has all metric fields flattened
        desc = describe_fn(d, m)
        return f"- **{d['composite']:.1f}** — *{d['title'][:70]}* ({d['source_name']}, {SOURCE_TYPE_LABEL.get(d['source_type'], d['source_type'])}) — {desc}"

    CCEL_PIPELINE_TITLES = {
        "The School of Obedience", "Prayer and Praying Men", "Purpose in Prayer", "Absolute Surrender",
        "The Weapon of Prayer", "The Two Covenants", "The Deeper Christian Life", "The Reality of Prayer",
        "How To Pray", "The True Vine: Meditations for a Month on John 15:1-16", "The Journal of John Wesley",
        "Lectures to Professing Christians", "The Kneeling Christian", "Power From On High",
        "With Christ in the School of Prayer", "The Practice of the Presence of God", "The Essentials of Prayer",
        "Sermons on Several Occasions", "The Necessity of Prayer",
    }
    n_ccel = sum(1 for d in worst_40 if d["title"] in CCEL_PIPELINE_TITLES)
    n_newwine = sum(1 for d in worst_40 if d["source_name"] == "New Wine Magazine")
    n_multivoice_only = sum(
        1 for d in worst_40
        if d["title"] not in CCEL_PIPELINE_TITLES
        and d["source_name"] != "New Wine Magazine"
        and d.get("multi_voice_bonus", 0) > 0
    )
    n_other = len(worst_40) - n_ccel - n_newwine - n_multivoice_only

    A("## 40 worst-scoring documents overall")
    A("")
    A(f"**Before reading this list: {n_ccel + n_newwine} of these 40 ({n_ccel} CCEL-pipeline, {n_newwine} New-Wine-pipeline) are explained by the two known ingestion-pipeline bugs above, and {n_multivoice_only} more are flagged only via the multi-voice-channel classification caveat above (mostly anthology/library sources, not confirmed guest-speaker risk).** Only **{n_other}** of the 40 are not explained by either caveat — those are the ones most worth reading closely.")
    A("")
    for d in worst_40:
        A(doc_line(d, describe_worst))
    A("")

    A(f"## Random sample of 15 from the middle (composite 40-60 band, n={len(mid_band)}, seed={RANDOM_SEED})")
    A("")
    for d in sorted(middle_15, key=lambda d: -d["composite"]):
        A(doc_line(d, describe_middle))
    A("")

    A("## 15 best-scoring documents overall")
    A("")
    for d in best_15:
        A(doc_line(d, describe_best))
    A("")

    out_path = ROOT / "docs" / "audits" / f"corpus_quality_report_{args.date}.md"
    out_path.write_text("\n".join(lines))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
