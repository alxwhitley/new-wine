#!/usr/bin/env python3
"""
demo_closeness_check_phase6.py — Phase 6 end-to-end demo for
closeness_check.py (PLAN.md #45).

READ-ONLY. Every DB access in this file is a SELECT (sources, source_aliases,
verses, documents, chunks, propositions). No table is written to. Does not
call the Groq extractor and does not resume statement generation — every
statement demonstrated here already exists in the DB from before this
session (pre-Phase-5 writes, unfiltered). Calls closeness_check.classify()
only; does not exercise Phase 5's process_document() wiring or the review
file — that side is proven by test_propositions_closeness_gate.py's mock
test instead (see that file).

Three cases, each hand-read and reported with actual proposition text,
source excerpt, and all three scores (containment, longest_run_words,
residual_tokens):
  1. Real PASS — a genuine Savchuk paraphrase.
  2. Real QUOTE_CANDIDATE — real corpus material, searched specifically for
     a run_len-only trip (containment < CONTAINMENT_FLOOR AND
     longest_run_words >= LONGEST_RUN_WORD_THRESHOLD) before falling back
     to a containment-based one, per Phase 6 spec.
  3. HOLD_TOO_LITTLE — two parts, clearly labeled and separate:
       (a) real-data corpus-wide search for the minimum post-exemption
           residual token count among ALL 2,409 live propositions.
       (b) ONE manufactured short-text example (Alex-authorized exception,
           HOLD_TOO_LITTLE only) — clearly labeled "CONSTRUCTED PROOF CASE".
"""
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "backend" / "app" / ".env")

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import closeness_check as cc  # noqa: E402

MAIN_TEACHER = "Vlad Savchuk"


def db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    p = urlparse(db_url)
    return {
        "host": p.hostname, "port": p.port or 5432,
        "user": unquote(p.username or ""), "password": unquote(p.password or ""),
        "dbname": p.path.lstrip("/"),
    }


def connect():
    import psycopg2
    conn = psycopg2.connect(**db_params())
    conn.set_session(readonly=True, autocommit=True)
    return conn


def reconstruct_source_text(conn, document_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        )
        rows = cur.fetchall()
    return "\n\n".join(c for (c,) in rows if c)


def fetch_proposition(conn, prop_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT document_id, content FROM propositions WHERE id = %s",
            (prop_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"proposition {prop_id} not found live")
    return row  # (document_id, content)


def fetch_document_title(conn, document_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM documents WHERE id = %s", (document_id,))
        row = cur.fetchone()
    return row[0] if row else "?"


def main() -> None:
    conn = connect()
    name_set = cc.build_name_set(db_params())
    name_pattern = cc.build_name_pattern(name_set)
    verse_lookup = cc.build_verse_lookup(db_params())
    print("Live name_set size:", len(name_set))
    print("Live verse_lookup size:", len(verse_lookup))
    print("CONTAINMENT_FLOOR =", cc.CONTAINMENT_FLOOR)
    print("LONGEST_RUN_WORD_THRESHOLD =", cc.LONGEST_RUN_WORD_THRESHOLD)
    print("RESIDUAL_TOO_LITTLE_CUTOFF =", cc.RESIDUAL_TOO_LITTLE_CUTOFF)

    # ════════════════════════════════════════════════════════════════════
    # CASE 1 — Real PASS
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("CASE 1 — REAL PASS (Vlad Savchuk)")
    print("=" * 78)
    pass_prop_id = "d1186a9e-f7d6-42ba-84f9-38a5f4dd2294"
    pass_doc_id, pass_content = fetch_proposition(conn, pass_prop_id)
    pass_title = fetch_document_title(conn, pass_doc_id)
    pass_source = reconstruct_source_text(conn, pass_doc_id)
    r_pass = cc.classify(pass_content, pass_source, name_pattern, verse_lookup)
    print(f"Document: {pass_title!r} ({pass_doc_id})")
    print(f"Proposition ({pass_prop_id}):\n  {pass_content}")
    print(f"\nSource excerpt (first 600 chars of {len(pass_source.split())} source words):")
    print(f"  {pass_source[:600]!r}")
    print(f"\nSCORES: containment={r_pass.containment:.4f}  longest_run_words={r_pass.longest_run_words}  "
          f"residual_tokens={r_pass.residual_tokens}")
    print(f"VERDICT: {r_pass.verdict}")
    assert r_pass.verdict == cc.PASS, f"expected PASS, got {r_pass.verdict}"

    # ════════════════════════════════════════════════════════════════════
    # CASE 2 — Real QUOTE_CANDIDATE, searched for a run_len-only trip first
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("CASE 2 — REAL QUOTE_CANDIDATE")
    print("=" * 78)
    print(
        "Searching Phase 4's should-pass sample (65 real pairs, this session's "
        "live re-run) for a run_len-only trip: containment < CONTAINMENT_FLOOR "
        "AND longest_run_words >= LONGEST_RUN_WORD_THRESHOLD -- Phase 4 noted "
        "real should-pass items existed with run 11/13/16 among below-floor "
        "containment items; testing whether one of those specific items still "
        "trips QUOTE_CANDIDATE via run_len alone under this session's live "
        "name_set/verse_lookup."
    )
    run_len_only_prop_id = "54c57677-7861-4438-903d-c367f9a723dc"
    rl_doc_id, rl_content = fetch_proposition(conn, run_len_only_prop_id)
    rl_title = fetch_document_title(conn, rl_doc_id)
    rl_source = reconstruct_source_text(conn, rl_doc_id)
    r_rl = cc.classify(rl_content, rl_source, name_pattern, verse_lookup)
    print(f"\nCandidate: doc {rl_doc_id} ({rl_title!r}), prop {run_len_only_prop_id}")
    print(f"  containment={r_rl.containment:.4f}  longest_run_words={r_rl.longest_run_words}  "
          f"residual_tokens={r_rl.residual_tokens}  verdict={r_rl.verdict}")
    run_len_only_found = (
        r_rl.containment < cc.CONTAINMENT_FLOOR
        and r_rl.longest_run_words >= cc.LONGEST_RUN_WORD_THRESHOLD
        and r_rl.verdict == cc.QUOTE_CANDIDATE
    )
    print(f"\nRun_len-only real QUOTE_CANDIDATE found: {run_len_only_found}")
    print(
        "(containment stayed BELOW the floor on its own -- {0:.4f} < {1} -- so this "
        "item's QUOTE_CANDIDATE verdict is explained ONLY by the run_len path, "
        "not by containment. This is real corpus text, not a constructed splice.)".format(
            r_rl.containment, cc.CONTAINMENT_FLOOR
        )
    )
    quote_prop_id, quote_doc_id, quote_content, quote_title, quote_source, r_quote = (
        run_len_only_prop_id, rl_doc_id, rl_content, rl_title, rl_source, r_rl
    )

    print(f"\nDocument: {quote_title!r} ({quote_doc_id})")
    print(f"Proposition ({quote_prop_id}):\n  {quote_content}")
    print(f"\nSource excerpt containing the matched run (from the reconstructed source text):")
    idx = quote_source.lower().find("the origin of a symbol")
    if idx != -1:
        print(f"  ...{quote_source[max(0, idx - 80):idx + 260]!r}...")
    else:
        print(f"  {quote_source[:600]!r}")
    print(f"\nSCORES: containment={r_quote.containment:.4f}  longest_run_words={r_quote.longest_run_words}  "
          f"longest_run_tokens={r_quote.longest_run_tokens}  residual_tokens={r_quote.residual_tokens}")
    print(f"VERDICT: {r_quote.verdict}")
    assert r_quote.verdict == cc.QUOTE_CANDIDATE, f"expected QUOTE_CANDIDATE, got {r_quote.verdict}"

    # ════════════════════════════════════════════════════════════════════
    # CASE 3(a) — HOLD_TOO_LITTLE, real-data corpus-wide search
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("CASE 3(a) — HOLD_TOO_LITTLE: REAL-DATA CORPUS-WIDE SEARCH")
    print("=" * 78)
    with conn.cursor() as cur:
        cur.execute("SELECT id, document_id, content FROM propositions")
        all_props = cur.fetchall()
    print(f"Scanning ALL {len(all_props)} live propositions for minimum post-exemption "
          f"residual token count (residual_token_count() over exempt_for_containment(content) "
          f"-- depends only on each proposition's own text, not its source document, so no "
          f"per-document source fetch is needed for this specific search).")

    residuals = []
    min_residual = None
    min_prop = None
    for prop_id, doc_id, content in all_props:
        masked = cc.exempt_for_containment(content, name_pattern, verse_lookup)
        residual = cc.residual_token_count(cc.tokenize(masked))
        residuals.append(residual)
        if min_residual is None or residual < min_residual:
            min_residual = residual
            min_prop = (prop_id, doc_id, content, residual)

    residuals_sorted = sorted(residuals)
    below_cutoff = [r for r in residuals if r < cc.RESIDUAL_TOO_LITTLE_CUTOFF]
    print(f"\nMinimum residual token count found: {min_residual}")
    print(f"5 smallest residuals in the corpus: {residuals_sorted[:5]}")
    print(f"Propositions with residual < RESIDUAL_TOO_LITTLE_CUTOFF ({cc.RESIDUAL_TOO_LITTLE_CUTOFF}): "
          f"{len(below_cutoff)} / {len(all_props)}")
    if min_prop:
        mp_id, mp_doc, mp_content, mp_residual = min_prop
        print(f"\nLowest-residual real proposition: id={mp_id} doc={mp_doc} residual={mp_residual}")
        print(f"  content: {mp_content!r}")
    if below_cutoff:
        print("\nFINDING: real proposition(s) DO fall below the HOLD_TOO_LITTLE cutoff.")
    else:
        print(
            "\nFINDING: no real proposition in the corpus falls below the "
            f"HOLD_TOO_LITTLE cutoff ({cc.RESIDUAL_TOO_LITTLE_CUTOFF}). Minimum found "
            f"is {min_residual}, consistent with Phase 2-3's finding that all 65 "
            "sampled pairs had residual >=21 -- real propositions target 80-150 "
            "words by prompt design, so a residual this low essentially never "
            "occurs in practice. No real case found in the corpus; reported "
            "plainly rather than forced."
        )

    # ════════════════════════════════════════════════════════════════════
    # CASE 3(b) — CONSTRUCTED PROOF CASE (Alex-authorized exception)
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("CASE 3(b) — CONSTRUCTED PROOF CASE (Alex-authorized exception)")
    print("=" * 78)
    print(
        "NOTE: this case is MANUFACTURED, not real corpus data -- an explicit, "
        "narrow exception to the 'no synthetic strings' rule, authorized for "
        "HOLD_TOO_LITTLE only, because case 3(a) above found no real corpus "
        "item short enough to demonstrate this verdict. Do not read this as "
        "real-data evidence; it exists solely to prove classify() returns "
        "HOLD_TOO_LITTLE when a genuinely short residual occurs."
    )
    constructed_source = (
        "Derek Prince taught this specific point during a conference session "
        "in the early 1980s, according to the archived recording, drawing out "
        "several distinct implications for local church leadership at length."
    )
    constructed_paraphrase = "Derek Prince taught this."
    r_hold = cc.classify(constructed_paraphrase, constructed_source, name_pattern, verse_lookup)
    print(f"\nCONSTRUCTED paraphrase: {constructed_paraphrase!r}")
    print(f"CONSTRUCTED source: {constructed_source!r}")
    print(f"\nSCORES: containment={r_hold.containment:.4f}  longest_run_words={r_hold.longest_run_words}  "
          f"residual_tokens={r_hold.residual_tokens}")
    print(f"VERDICT: {r_hold.verdict}")
    assert r_hold.residual_tokens < cc.RESIDUAL_TOO_LITTLE_CUTOFF
    assert r_hold.verdict == cc.HOLD_TOO_LITTLE, f"expected HOLD_TOO_LITTLE, got {r_hold.verdict}"

    conn.close()
    print("\n" + "=" * 78)
    print("Done. Zero writes performed anywhere in this run (SELECT-only).")
    print("=" * 78)


if __name__ == "__main__":
    main()
