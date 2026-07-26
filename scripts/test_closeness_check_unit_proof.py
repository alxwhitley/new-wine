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

Run: python3 scripts/test_closeness_check_unit_proof.py
"""
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

    print("\nAll assertions passed.")


if __name__ == "__main__":
    main()
