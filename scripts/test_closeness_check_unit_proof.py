#!/usr/bin/env python3
"""
test_closeness_check_unit_proof.py — Phase 1 hand-checkable proof for
closeness_check.py (PLAN.md #45).

This is a UNIT-level proof of the mechanism itself using small,
hand-constructed inputs -- explicitly permitted for Phase 1. The "no
synthetic strings" rule binds only the later end-to-end demo against real
corpus material, which this file does not attempt.

Loads the live name set via closeness_check.build_name_set() (read-only
SELECT against sources/source_aliases) so the "shared teacher name" case
below is exercised against the real current name set, not a hardcoded
substitute. No writes anywhere in this file.

Cases 7-8 (PLAN.md #45 Phase 6, added 2026-07-28) prove the
common-religious-vocabulary exemption (SENTINEL_VOCAB / VocabMatcher /
build_vocab_matcher / _mask_vocab, wired through exempt_for_containment and
exempt_for_run) -- DB-free, using a small subset of the real, committed
scripts/data/common_religious_vocab.json phrase list (never a fabricated
phrase list), written to a scratch temp file for build_vocab_matcher() to
load.

Run: python3 scripts/test_closeness_check_unit_proof.py
"""
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import closeness_check as cc


def _db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "user": unquote(p.username or ""),
        "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def _print_case(label: str, paraphrase: str, source: str, name_pattern) -> cc.ClosenessResult:
    result = cc.classify(paraphrase, source, name_pattern)
    print(f"\n--- {label} ---")
    print(f"  P: {paraphrase!r}")
    print(f"  S: {source!r}")
    print(f"  containment            = {result.containment:.4f}")
    print(f"  paraphrase_trigram_ct  = {result.paraphrase_trigram_count}")
    print(f"  residual_tokens        = {result.residual_tokens}")
    print(f"  longest_run_words      = {result.longest_run_words}")
    print(f"  longest_run_tokens     = {result.longest_run_tokens}")
    print(f"  VERDICT                = {result.verdict}")
    return result


def main() -> None:
    name_set = cc.build_name_set(_db_params())
    print(f"Live name_set size (deduped via normalize_alias_key): {len(name_set)}")
    name_pattern = cc.build_name_pattern(name_set)

    # ── Case 1: verbatim copy -> containment should be 1.0 ──────────────────
    verbatim = (
        "The prophet declared that revival always begins with brokenness "
        "before God, not with strategy or method."
    )
    r1 = _print_case("Case 1: verbatim copy (P == S)", verbatim, verbatim, name_pattern)
    assert r1.containment == 1.0, f"expected containment 1.0, got {r1.containment}"
    assert r1.verdict == cc.QUOTE_CANDIDATE, f"expected QUOTE_CANDIDATE, got {r1.verdict}"

    # ── Case 2: full reword of the same content -> containment near 0 ───────
    source_2 = (
        "The prophet declared that revival always begins with brokenness "
        "before God, not with strategy or method."
    )
    reword_2 = (
        "He taught that spiritual renewal starts when people humble "
        "themselves, not through clever planning."
    )
    r2 = _print_case("Case 2: full reword, same content", reword_2, source_2, name_pattern)
    assert r2.containment < 0.15, f"expected near-0 containment, got {r2.containment}"
    assert r2.verdict == cc.PASS, f"expected PASS, got {r2.verdict}"

    # ── Case 3: shared scripture reference must NOT drive a false match ─────
    source_3 = (
        "As it says in Romans 8:28, all things work together for good to "
        "those who love God and are called according to his purpose."
    )
    para_3 = (
        "The author references Romans 8:28 while making an entirely "
        "unrelated point about patience during long seasons of suffering."
    )
    # Unexempted baseline, to SHOW the exemption firing: run containment
    # with an empty name pattern AND with scripture masking bypassed by
    # feeding raw tokenize() output directly (no exemption pipeline at all).
    raw_p_tokens = cc.tokenize(para_3)
    raw_s_tokens = cc.tokenize(source_3)
    raw_containment, raw_tri_ct = cc.containment_score(raw_p_tokens, raw_s_tokens)
    r3 = _print_case("Case 3: shared scripture reference (exempted)", para_3, source_3, name_pattern)
    print(f"  [baseline, NO exemption at all] containment = {raw_containment:.4f}  (trigram_ct={raw_tri_ct})")
    # The exempted trigram set must not contain any trigram built from the
    # masked scripture span's own words (romans/8/28) -- confirm directly.
    p_masked = cc.exempt_for_containment(para_3, name_pattern)
    assert cc.SENTINEL_SCRIPTURE in p_masked, "expected scripture sentinel to appear in masked paraphrase"
    s_masked = cc.exempt_for_containment(source_3, name_pattern)
    assert cc.SENTINEL_SCRIPTURE in s_masked, "expected scripture sentinel to appear in masked source"
    print(f"  masked P contains sentinel: {cc.SENTINEL_SCRIPTURE in p_masked}")
    print(f"  masked S contains sentinel: {cc.SENTINEL_SCRIPTURE in s_masked}")

    # ── Case 4: shared teacher name must NOT drive a false match ────────────
    # "Derek Prince" is a live source in the corpus as of this run (see
    # printed name_set size above / report).
    source_4 = (
        "Derek Prince taught that spiritual authority flows from "
        "submission to God's order in the home and in the church."
    )
    para_4 = (
        "Derek Prince explained a completely different idea about "
        "financial stewardship, entirely unrelated to what is shown here."
    )
    raw_p4 = cc.tokenize(para_4)
    raw_s4 = cc.tokenize(source_4)
    raw_containment_4, raw_tri_ct_4 = cc.containment_score(raw_p4, raw_s4)
    r4 = _print_case("Case 4: shared teacher name (exempted)", para_4, source_4, name_pattern)
    print(f"  [baseline, NO exemption at all] containment = {raw_containment_4:.4f}  (trigram_ct={raw_tri_ct_4})")
    p4_masked = cc.exempt_for_containment(para_4, name_pattern)
    s4_masked = cc.exempt_for_containment(source_4, name_pattern)
    name_masked_p4 = cc.SENTINEL_NAME in p4_masked
    name_masked_s4 = cc.SENTINEL_NAME in s4_masked
    print(f"  masked P contains name sentinel: {name_masked_p4}")
    print(f"  masked S contains name sentinel: {name_masked_s4}")
    assert name_masked_p4 and name_masked_s4, "expected 'Derek Prince' to be masked in both P and S"

    # ── Case 5: residual below the too-little cutoff -> HOLD_TOO_LITTLE ─────
    source_5 = (
        "Derek Prince taught this specific point during a conference "
        "session in the early 1980s, according to the archived recording."
    )
    para_5 = "Derek Prince taught this."
    r5 = _print_case("Case 5: residual below too-little cutoff", para_5, source_5, name_pattern)
    print(f"  RESIDUAL_TOO_LITTLE_CUTOFF = {cc.RESIDUAL_TOO_LITTLE_CUTOFF}")
    assert r5.residual_tokens < cc.RESIDUAL_TOO_LITTLE_CUTOFF, (
        f"expected residual < cutoff, got {r5.residual_tokens}"
    )
    assert r5.verdict == cc.HOLD_TOO_LITTLE, f"expected HOLD_TOO_LITTLE, got {r5.verdict}"

    # ── Case 6: run_len-only QUOTE_CANDIDATE — the OR-wiring's own
    #    regression case (Phase 4/5, PLAN.md #45). A genuine reword (low
    #    containment on its own, well under CONTAINMENT_FLOOR) with a real
    #    ~11-word verbatim run from the source spliced onto its end,
    #    mirroring the corpus-scale R-run adversarial items validated in
    #    validate_closeness_check.py's Step 2 re-run (containment stayed
    #    0.20-0.29 there; longest_run jumped from 2-3 words pre-splice to
    #    12-13 post-splice). This is a hand-made repeatable unit case for
    #    the same shape, so the OR-wiring (containment >= FLOOR OR run_len
    #    >= THRESHOLD) stays regression-protected without needing the live
    #    corpus. Asserts the QUOTE_CANDIDATE verdict trips via the run_len
    #    path SPECIFICALLY — containment must stay BELOW CONTAINMENT_FLOOR
    #    on its own, so a verdict here can only be explained by run_len.
    source_6 = (
        "The prophet declared that revival always begins with brokenness "
        "before God, not with strategy or method. He also explained that a "
        "shepherd must guard the flock from wandering into dangerous and "
        "unfamiliar territory during the long winter night."
    )
    reword_6 = (
        "He taught that spiritual renewal starts when people humble "
        "themselves, not through clever planning, and that quiet devotion "
        "matters more than public performance."
    )
    verbatim_run_6 = "guard the flock from wandering into dangerous and unfamiliar territory during"
    spliced_6 = reword_6.rstrip(". ") + ". " + verbatim_run_6 + "."

    r6_before = _print_case("Case 6a: reword alone, BEFORE splice (control)", reword_6, source_6, name_pattern)
    assert r6_before.verdict == cc.PASS, f"expected PASS before splice, got {r6_before.verdict}"
    assert r6_before.longest_run_words < cc.LONGEST_RUN_WORD_THRESHOLD

    r6 = _print_case("Case 6b: reword + spliced verbatim run (run_len path)", spliced_6, source_6, name_pattern)
    print(f"  CONTAINMENT_FLOOR = {cc.CONTAINMENT_FLOOR}")
    print(f"  LONGEST_RUN_WORD_THRESHOLD = {cc.LONGEST_RUN_WORD_THRESHOLD}")
    assert r6.containment < cc.CONTAINMENT_FLOOR, (
        f"this case is only a valid run_len-path proof if containment stays "
        f"below the floor; got {r6.containment}"
    )
    assert r6.longest_run_words >= cc.LONGEST_RUN_WORD_THRESHOLD, (
        f"expected longest_run_words >= threshold, got {r6.longest_run_words}"
    )
    assert r6.verdict == cc.QUOTE_CANDIDATE, (
        f"expected QUOTE_CANDIDATE (via run_len, since containment alone is "
        f"below floor), got {r6.verdict}"
    )

    # ── Case 7: common-religious-vocabulary DISCRIMINATION (PLAN.md #45
    #    Phase 6) -- DB-free. Builds a SMALL matcher from a handful of the
    #    real, committed 1,210-phrase list (never a fabricated phrase), via
    #    the real loader build_vocab_matcher(), pointed at a scratch subset
    #    file. Proves TWO things at once: (a) a text containing a known
    #    stock phrase gets masked -- tokens become SENTINEL_VOCAB, and
    #    containment/residual change MEASURABLY (here, enough to flip the
    #    verdict itself, QUOTE_CANDIDATE -> PASS); (b) a text with a
    #    distinctive, non-listed phrase is left completely untouched. ───────
    real_vocab_path = PROJECT_ROOT / "scripts" / "data" / "common_religious_vocab.json"
    with open(real_vocab_path, "r", encoding="utf-8") as f:
        real_vocab_data = json.load(f)
    by_phrase = {p["phrase"]: p for p in real_vocab_data["phrases"]}

    STOCK_PHRASE = "he that hath my commandments and keepeth them he it is that loveth"
    RAVENHILL_STRESS_PHRASE = "god the father god the son and"
    assert STOCK_PHRASE in by_phrase, "expected stock phrase to be present in the real committed data file"
    assert RAVENHILL_STRESS_PHRASE in by_phrase, "expected the Ravenhill stress phrase to be present in the real committed data file"

    subset = [by_phrase[STOCK_PHRASE], by_phrase[RAVENHILL_STRESS_PHRASE]]
    scratch_dir = Path(
        "/private/tmp/claude-501/-Users-alexwhitley-rhemata/"
        "089de4dc-bced-40ff-98c1-e156d293aed9/scratchpad"
    )
    scratch_dir.mkdir(parents=True, exist_ok=True)
    tiny_vocab_path = scratch_dir / "tiny_vocab_for_unit_test.json"
    with open(tiny_vocab_path, "w", encoding="utf-8") as f:
        json.dump({"provenance": {"note": "small test subset of the real 1210-phrase list"}, "phrases": subset}, f)

    vocab_matcher = cc.build_vocab_matcher(path=tiny_vocab_path)
    assert vocab_matcher is not None
    print(f"\n--- Case 7 setup: small vocab matcher built from {len(subset)} real phrases ---")

    para_7 = (
        STOCK_PHRASE
        + ", and he also explained a completely different idea about managing household budgets wisely."
    )
    source_7 = (
        STOCK_PHRASE
        + ", according to an entirely separate teaching about caring for the poor in the local congregation."
    )
    r7_off = cc.classify(para_7, source_7, name_pattern)
    r7_on = cc.classify(para_7, source_7, name_pattern, None, vocab_matcher)
    print("--- Case 7a: stock phrase shared by P and S, vocab OFF vs ON ---")
    print(f"  vocab OFF: containment={r7_off.containment:.4f} residual={r7_off.residual_tokens} "
          f"longest_run={r7_off.longest_run_words} verdict={r7_off.verdict}")
    print(f"  vocab ON : containment={r7_on.containment:.4f} residual={r7_on.residual_tokens} "
          f"longest_run={r7_on.longest_run_words} verdict={r7_on.verdict}")
    masked_p7_on = cc.exempt_for_containment(para_7, name_pattern, None, vocab_matcher)
    print(f"  masked P (vocab ON) contains sentinel: {cc.SENTINEL_VOCAB in masked_p7_on}")
    assert cc.SENTINEL_VOCAB in masked_p7_on, "expected the stock phrase to be masked with SENTINEL_VOCAB"
    assert r7_on.containment < r7_off.containment, (
        f"expected containment to drop with vocab masking on, got OFF={r7_off.containment} ON={r7_on.containment}"
    )
    assert r7_on.residual_tokens < r7_off.residual_tokens, (
        f"expected residual_tokens to drop with vocab masking on, got OFF={r7_off.residual_tokens} ON={r7_on.residual_tokens}"
    )
    assert r7_off.verdict == cc.QUOTE_CANDIDATE, f"expected OFF verdict QUOTE_CANDIDATE, got {r7_off.verdict}"
    assert r7_on.verdict == cc.PASS, f"expected ON verdict PASS (vocab masking should discount the shared stock phrase), got {r7_on.verdict}"

    distinct_text_7 = (
        "the committee reviewed quarterly logistics reports before adjusting "
        "the shipping schedule for next month"
    )
    masked_distinct_7 = cc._mask_vocab(distinct_text_7, cc._constant_factory(cc.SENTINEL_VOCAB), vocab_matcher)
    print(f"--- Case 7b: distinctive non-listed text left untouched: {masked_distinct_7 == distinct_text_7} ---")
    assert masked_distinct_7 == distinct_text_7, "expected a text with no listed phrase to be left byte-identical by _mask_vocab"

    # ── Case 8: masking-order interaction, end-to-end (PLAN.md #45 Phase 6,
    #    B-5's named risk). _mask_theology masks single words (including
    #    "God") that are also anchor words inside vocab phrases. Proves,
    #    against the concrete Ravenhill "Secret to Revival" stress case
    #    ("god the father god the son and", 8 docs/5 teachers), that (a) the
    #    CHOSEN order (scripture, vocab, names, theology --
    #    exempt_for_containment's actual order) correctly discounts the
    #    phrase end-to-end under the FULL pipeline, and (b) the REJECTED
    #    order (theology before vocab) would have silently fragmented the
    #    phrase's anchor words into theology sentinels first, so the vocab
    #    matcher (which matches against the phrase's own LITERAL words,
    #    never a sentinel placeholder) would find nothing -- confirming the
    #    named risk is real, not hypothetical. ─────────────────────────────
    ravenhill_text = (
        "how in God's name can you be indwelt by God the Father, "
        "God the Son, and God the Holy Ghost"
    )
    print("\n--- Case 8: masking-order interaction (Ravenhill stress case) ---")
    print(f"  raw text: {ravenhill_text!r}")

    chosen_order_masked = cc.exempt_for_containment(ravenhill_text, name_pattern, None, vocab_matcher)
    print(f"  CHOSEN order (scripture->vocab->names->theology) masked: {chosen_order_masked!r}")
    assert cc.SENTINEL_VOCAB in chosen_order_masked, (
        "expected the CHOSEN masking order to discount the Ravenhill phrase end-to-end via SENTINEL_VOCAB"
    )

    # Rejected order, reconstructed directly from the same private masking
    # primitives (theology BEFORE vocab) to prove the risk is real.
    rejected_order_masked = cc._mask_theology(ravenhill_text, cc._constant_factory(cc.SENTINEL_THEOLOGY))
    rejected_order_masked = cc._mask_vocab(rejected_order_masked, cc._constant_factory(cc.SENTINEL_VOCAB), vocab_matcher)
    print(f"  REJECTED order (theology->vocab) masked:                  {rejected_order_masked!r}")
    assert cc.SENTINEL_VOCAB not in rejected_order_masked, (
        "expected the REJECTED order to fail to fire the vocab match -- theology masking must have "
        "already consumed the phrase's own 'god' anchor words, fragmenting it before vocab could match"
    )
    print("  Confirmed: CHOSEN order discounts the phrase end-to-end; REJECTED order silently fails to.")

    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
