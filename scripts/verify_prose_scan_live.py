#!/usr/bin/env python3
"""Live verification of the Phase 2 RESIDUAL fix — the prose-attribution scan
(2026-08-02). Closes the last open pure-invention path: a teacher credited in
the answer PROSE but omitted from the model's <reference_mentions> block, which
the declared-block guard could not see (reviewer finding #3 on ee3cff4/9e5fe94).

This reuses the SAME faithful offline pipeline reproduction as
verify_teacher_name_guard_live.py (imported, not forked — single source of truth
for retrieval + context assembly), then applies the SHIPPED guard exactly as
chat.py's generate() does: the union of the declared-block arm
(_ungrounded_reference_teachers) and the prose-scan arm
(build_name_universe + ungrounded_prose_teachers), resolved by
regenerate-once-then-clean-refuse. So the served OUTCOME measured here is what
production would serve.

Requirements covered:
  6  — size the remaining SURNAME exposure: prose attributions counted as
       full-name vs bare-surname, grounded vs ungrounded (reported, NOT acted on).
  8  — the Phase 0 fabrications (Wiersbe, Tozer, Stedman, Wilson, Jenkins,
       Martin, Havner) are caught whether declared or credited only in prose.
  9  — the 55 legitimate attributions produce zero false denials (a legit answer
       must not end up refused / stripped of a real teacher).
  10 — multiple passes per question (fabrication is intermittent; one clean run
       proves nothing).

Zero DB writes (retrieval reads + LLM generation only). Why offline and not the
/chat HTTP endpoint: the endpoint's metering RPCs + _save_conversation are DB
writes; identical reasoning to Phase 0 §0 and the Phase 2 live harness.

Usage:
  python3 scripts/verify_prose_scan_live.py --dry-run     # offline logic self-test, no API cost
  python3 scripts/verify_prose_scan_live.py --runs 3 --fab-runs 4
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # so we can import the base harness

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / "app" / ".env")

# Reuse the base harness's faithful pipeline reproduction (retrieval + context).
import verify_teacher_name_guard_live as base
from verify_teacher_name_guard_live import retrieve, build_context, db, FAB_QUESTIONS, LEGIT_QUESTIONS

from app.routers.chat import ANSWER_SYSTEM_BLOCKS, _is_citable, _ungrounded_reference_teachers
from app.services.llm_client import get_anthropic_client
from app.services.position_papers import match_position_paper
from app.services.reference_verifier import (
    build_retrieval_grounding, build_name_universe, ungrounded_prose_teachers,
    resolve_alias_source_id, _is_retrieval_grounded,
    _extract_prose_attribution_names, _prose_name_present,
)
from app.services.source_resolver import normalize_alias_key
from app.services.biblical_figures import is_biblical_figure

# Built once — the finite corpus name universe the prose scan searches (Arm 1).
NAME_UNIVERSE = build_name_universe(db)

# Fabricated names each Phase 0 case should surface, for the req-8 assertion.
FAB_EXPECTED = {
    "D2": ["Warren Wiersbe"],
    "S2": ["Ray Stedman", "Douglas Wilson"],
    "S4": ["Vance Havner", "A.W. Tozer", "Philip Jenkins", "Ralph Martin"],
}


# ── Surname measurement scaffolding (req 6, measurement-only, never acted on) ──
# Surname universe = the last token of every corpus full name, plus any single-
# token alias (Bosworth, Muller). Only used to SIZE surname exposure.
def _build_surname_map():
    surn = {}  # surname_lower -> a representative full name (for "full-name present?" checks)
    for full in NAME_UNIVERSE:
        toks = full.split()
        last = toks[-1].strip(".'’-")
        if len(last) >= 3 and last.lower() not in {n.lower() for n in ("The", "And")}:
            surn.setdefault(last, full)
    # single-token alias displays are bare surnames by construction
    try:
        for row in (db.table("source_aliases").select("alias_display").execute().data or []):
            d = (row.get("alias_display") or "").strip()
            if d and len(d.split()) == 1 and d[:1].isupper() and len(d) >= 3:
                surn.setdefault(d, d)
    except Exception:
        pass
    return surn


SURNAME_MAP = _build_surname_map()
_SURNAME_ATTR = None  # compiled lazily once SURNAME_MAP is known


def _surname_attr_re():
    global _SURNAME_ATTR
    if _SURNAME_ATTR is None:
        alt = "|".join(sorted((re.escape(s) for s in SURNAME_MAP), key=len, reverse=True))
        # a surname in explicit attribution context (same anchors as Arm 2)
        _SURNAME_ATTR = re.compile(
            r"(?:According to|As|as)\s+(" + alt + r")\b"
            r"|\b(" + alt + r")(?:['’]s)?\s+(?:teaches|taught|writes|wrote|argues|argued|notes|noted|"
            r"reminds|reminded|says|said|observes|observed|explains|explained|describes|described|"
            r"emphasizes|emphasized|warns|warned|maintains|maintained|declares|declared|comments|"
            r"commented|suggests|suggested|holds|held|calls|called)\b"
        )
    return _SURNAME_ATTR


def _grounded(name):
    return _is_retrieval_grounded(name, resolve_alias_source_id(db, name), _GROUNDING)


# ── Measurement (req 6): classify prose attributions ──────────────────────────
def measure_attributions(answer, grounding):
    global _GROUNDING
    _GROUNDING = grounding

    # Full-name prose attributions (Arm 1 universe scan ∪ Arm 2 extraction).
    full = set()
    for n in NAME_UNIVERSE:
        if _prose_name_present(answer, n):
            full.add(n)
    for n in _extract_prose_attribution_names(answer):
        full.add(n)
    full = {n for n in full if not is_biblical_figure(n)}
    full_g = sorted(n for n in full if _grounded(n))
    full_u = sorted(n for n in full if not _grounded(n))

    # Bare-surname prose attributions (measurement-only).
    surn = set()
    for m in _surname_attr_re().finditer(answer):
        s = (m.group(1) or m.group(2) or "").strip()
        if s:
            surn.add(s)
    surn_g = sorted(s for s in surn if _grounded(s))
    surn_u = sorted(s for s in surn if not _grounded(s))
    # Surname-ONLY ungrounded = the true residual the full-name scan misses:
    # an ungrounded surname credit whose full name does NOT appear in the answer.
    surn_only_u = sorted(
        s for s in surn_u
        if not _prose_name_present(answer, SURNAME_MAP.get(s, s))
        and not any(_prose_name_present(answer, f) for f in NAME_UNIVERSE if f.split()[-1].strip(".'’-") == s)
    )
    return {
        "full_grounded": full_g, "full_ungrounded": full_u,
        "surname_grounded": surn_g, "surname_ungrounded": surn_u,
        "surname_only_ungrounded": surn_only_u,
    }


# ── Served-outcome simulation (mirrors chat.py generate() exactly) ────────────
_ATTR_CONSTRAINT_PERMITTED = None  # set per-question


def generate_answer(question, context, permitted_names=None):
    """Mirrors chat.py's _stream_answer: same model, max_tokens, system blocks,
    and (for the regeneration pass) the identical STRICT ATTRIBUTION CONSTRAINT
    that only NARROWS attribution to the retrieved/permitted names."""
    system = ANSWER_SYSTEM_BLOCKS
    if permitted_names is not None:
        names = ", ".join(permitted_names) if permitted_names else "(no teachers were retrieved -- attribute to no one)"
        constraint = (
            "STRICT ATTRIBUTION CONSTRAINT (this answer only): you may attribute a claim BY NAME "
            "ONLY to these teachers, whose material was actually retrieved for this question: "
            + names + ". Do NOT name, cite, or attribute any point to any other teacher, author, "
            "commentator, or ministry -- not even in passing. If a point cannot be attributed to a "
            "permitted name, state it without attribution. This overrides any inclination to add "
            "other voices for balance."
        )
        system = list(ANSWER_SYSTEM_BLOCKS) + [{"type": "text", "text": constraint}]
    resp = get_anthropic_client().messages.create(
        model="claude-sonnet-4-5", max_tokens=3000, system=system,
        messages=[{"role": "user", "content": "Sources:\n%s\n\nQuestion: %s" % (context, question)}],
        stream=False,
    )
    raw = resp.content[0].text
    a0, a1 = raw.find("<answer>"), raw.find("</answer>")
    answer = raw[a0 + len("<answer>"):a1].strip() if (a0 != -1 and a1 != -1) else raw.strip()
    return answer, raw


def _union_flags(answer, raw, grounding):
    declared = _ungrounded_reference_teachers(answer, raw, grounding, db)
    prose = ungrounded_prose_teachers(answer, NAME_UNIVERSE, grounding, db)
    return sorted(set(declared) | set(prose)), sorted(declared), sorted(prose)


def run_question(qid, question, run_idx, canned=None):
    routed = match_position_paper(question)
    if routed:
        print("  [%s run%d] ROUTED to position-paper pillar '%s' — names no teachers, skipped" % (qid, run_idx, routed))
        return {"qid": qid, "run": run_idx, "position_paper": True}

    if canned is not None:
        # --dry-run: exercise the guard + measurement logic offline with a fixed
        # answer, no API cost. grounding is faked to a fixed retrieved set.
        chunks, topic_parts = [], []
        grounding = canned["grounding"]
        context = canned.get("context", "")
        answer, raw = canned["answer"], canned["raw"]
        permitted = canned.get("permitted", [])
    else:
        chunks, topic_parts = retrieve(question)
        grounding = build_retrieval_grounding(chunks, db)
        context = build_context(chunks, topic_parts)
        permitted = sorted({(c.get("author") or "").strip() for c in chunks
                            if _is_citable(c) and (c.get("author") or "").strip()})
        answer, raw = generate_answer(question, context)

    flags1, declared1, prose1 = _union_flags(answer, raw, grounding)
    meas = measure_attributions(answer, grounding)

    outcome, flags2 = "served_clean", []
    served_answer = answer
    if flags1:
        if canned is not None:
            a2, r2 = canned.get("regen", (answer, raw))
        else:
            a2, r2 = generate_answer(question, context, permitted_names=permitted)
        flags2, _, _ = _union_flags(a2, r2, grounding)
        if flags2:
            outcome, served_answer = "refused", "(clean refusal served)"
        else:
            outcome, served_answer = "regenerated_clean", a2

    retrieved_authors = sorted({(c.get("author") or "?") for c in chunks})
    print("  [%s run%d] outcome=%s  flags_pass1(declared=%s prose=%s)  flags_pass2=%s"
          % (qid, run_idx, outcome, declared1, prose1, flags2))
    print("             measure: full[g=%d,u=%d] surname[g=%d,u=%d] surname_only_ungrounded=%s"
          % (len(meas["full_grounded"]), len(meas["full_ungrounded"]),
             len(meas["surname_grounded"]), len(meas["surname_ungrounded"]), meas["surname_only_ungrounded"]))

    return {
        "qid": qid, "run": run_idx, "position_paper": False,
        "outcome": outcome, "flags_pass1": flags1, "declared_pass1": declared1, "prose_pass1": prose1,
        "flags_pass2": flags2, "grounding_established": grounding.established,
        "retrieved_authors": retrieved_authors, "measure": meas,
    }


def aggregate(results):
    normal = [r for r in results if not r.get("position_paper")]
    fab = [r for r in normal if r["qid"] in FAB_EXPECTED]
    legit = [r for r in normal if r["qid"] not in FAB_EXPECTED]

    print("\n" + "=" * 92)
    print("AGGREGATE — %d normal-path answers (%d fabrication-prone runs, %d legit runs)"
          % (len(normal), len(fab), len(legit)))
    print("=" * 92)

    # req 8 — every fabrication run that actually fabricated must have been caught
    # (outcome != served_clean) AND the served text carries no false credit.
    fab_fabricated = [r for r in fab if r["flags_pass1"]]
    fab_leaked = [r for r in fab if r["outcome"] == "served_clean" and r["flags_pass1"]]  # impossible by construction
    fab_uncaught_served = [r for r in fab if r["outcome"] == "served_clean"
                           and any(any(e in " ".join(r["prose_pass1"] + r["declared_pass1"]) for e in FAB_EXPECTED[r["qid"]])
                                   for _ in [0])]
    print("\n[req 8] fabrication-prone runs that fabricated (flags fired): %d / %d" % (len(fab_fabricated), len(fab)))
    for r in fab_fabricated:
        print("    %s run%d: caught=%s outcome=%s flags=%s"
              % (r["qid"], r["run"], bool(r["flags_pass1"]), r["outcome"], r["flags_pass1"]))
    print("    served answers still carrying a false credit (MUST be 0): %d" % len(fab_leaked))

    # req 9 — legit answers must not end refused (false denial); count any that
    # even fired (would regenerate) for visibility.
    legit_refused = [r for r in legit if r["outcome"] == "refused"]
    legit_fired = [r for r in legit if r["flags_pass1"]]
    legit_full_attr = sum(len(r["measure"]["full_grounded"]) + len(r["measure"]["full_ungrounded"]) for r in legit)
    legit_full_grounded = sum(len(r["measure"]["full_grounded"]) for r in legit)
    print("\n[req 9] legit runs: %d | full-name attributions: %d (grounded %d) | fired (would regen): %d | REFUSED (false denial, MUST be 0): %d"
          % (len(legit), legit_full_attr, legit_full_grounded, len(legit_fired), len(legit_refused)))
    for r in legit_fired:
        print("    %s run%d fired: declared=%s prose=%s outcome=%s" % (r["qid"], r["run"], r["declared_pass1"], r["prose_pass1"], r["outcome"]))

    # req 6 — size full-name vs surname exposure across ALL normal answers.
    tot_full_g = sum(len(r["measure"]["full_grounded"]) for r in normal)
    tot_full_u = sum(len(r["measure"]["full_ungrounded"]) for r in normal)
    tot_surn_g = sum(len(r["measure"]["surname_grounded"]) for r in normal)
    tot_surn_u = sum(len(r["measure"]["surname_ungrounded"]) for r in normal)
    surname_only_u = [(r["qid"], r["run"], r["measure"]["surname_only_ungrounded"]) for r in normal if r["measure"]["surname_only_ungrounded"]]
    print("\n[req 6] PROSE ATTRIBUTION SIZING (across %d normal answers):" % len(normal))
    print("    FULL NAMES:    grounded=%d  ungrounded=%d" % (tot_full_g, tot_full_u))
    print("    BARE SURNAMES: grounded=%d  ungrounded=%d" % (tot_surn_g, tot_surn_u))
    print("    SURNAME-ONLY ungrounded (the residual a surname scan would NEWLY catch): %d occurrence(s)" % sum(len(x[2]) for x in surname_only_u))
    for qid, run, names in surname_only_u:
        print("        %s run%d: %s" % (qid, run, names))

    failclosed = [(r["qid"], r["run"]) for r in normal if not r.get("grounding_established", True)]
    print("\n  fail-closed events (grounding not established): %d %s" % (len(failclosed), failclosed))
    return {"legit_refused": len(legit_refused), "fab_leaked": len(fab_leaked)}


def dry_run():
    """Offline self-test of the guard + measurement + served-outcome logic with
    canned answers — no API calls, no cost. Proves the harness itself is correct
    before spending on live generation."""
    from app.services.reference_verifier import RetrievalGrounding
    PRINCE = "11111111-aaaa-bbbb-cccc-222222222222"
    # Fake a question where Derek Prince was retrieved (source + author).
    g = RetrievalGrounding(source_ids=frozenset({PRINCE}),
                           author_keys=frozenset({normalize_alias_key("Derek Prince")}),
                           established=True)
    # Patch resolve for the dry run so 'Derek Prince' maps to the retrieved source.
    import app.services.reference_verifier as rv
    orig = rv.resolve_alias_source_id
    rv.resolve_alias_source_id = lambda _db, name: PRINCE if normalize_alias_key(name) == normalize_alias_key("Derek Prince") else None

    results = []
    # A) fabrication credited ONLY in prose (undeclared) -> must be caught + not served.
    fab_answer = ("Deliverance is real. According to Warren Wiersbe, the believer is kept. "
                  "Derek Prince taught on the children's bread.")
    fab_raw = "<answer>%s</answer>\n<reference_mentions>\nTEACHER: Derek Prince\n</reference_mentions>" % fab_answer
    clean_regen = ("Deliverance is real. Derek Prince taught on the children's bread.",
                   "<answer>Deliverance is real. Derek Prince taught on the children's bread.</answer>\n"
                   "<reference_mentions>\nTEACHER: Derek Prince\n</reference_mentions>")
    results.append(run_question("D2", "dry: prose-only Wiersbe", 1, canned={
        "grounding": g, "answer": fab_answer, "raw": fab_raw, "permitted": ["Derek Prince"], "regen": clean_regen}))
    # B) legit answer, only retrieved Derek Prince credited -> served clean, no flags.
    legit_answer = "According to Derek Prince, deliverance is the children's bread. Derek Prince also warned of counterfeits."
    legit_raw = "<answer>%s</answer>\n<reference_mentions>\nTEACHER: Derek Prince\n</reference_mentions>" % legit_answer
    results.append(run_question("G4", "dry: legit Derek Prince", 1, canned={
        "grounding": g, "answer": legit_answer, "raw": legit_raw, "permitted": ["Derek Prince"]}))
    # C) theological-phrase trap -> no flags, served clean.
    trap = "As Jesus Christ taught and the Holy Spirit reminds us, the New Testament church was bold."
    trap_raw = "<answer>%s</answer>\n<reference_mentions>\n</reference_mentions>" % trap
    results.append(run_question("G1", "dry: theological traps", 1, canned={
        "grounding": g, "answer": trap, "raw": trap_raw, "permitted": ["Derek Prince"]}))

    rv.resolve_alias_source_id = orig

    ok = (results[0]["outcome"] in ("regenerated_clean", "refused") and "Warren Wiersbe" in results[0]["prose_pass1"]
          and results[1]["outcome"] == "served_clean" and not results[1]["flags_pass1"]
          and results[2]["outcome"] == "served_clean" and not results[2]["flags_pass1"])
    print("\nDRY-RUN SELF-TEST:", "PASS" if ok else "FAIL")
    if not ok:
        print("  D2:", results[0]); print("  G4:", results[1]); print("  G1:", results[2])
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3, help="runs per legit question")
    ap.add_argument("--fab-runs", type=int, default=4, help="runs per fabrication-prone question")
    ap.add_argument("--dry-run", action="store_true", help="offline logic self-test, no API cost")
    args = ap.parse_args()

    if args.dry_run:
        dry_run()
        return

    print("Prose-scan universe size: %d names" % len(NAME_UNIVERSE))
    all_results = []
    out = Path(__file__).resolve().parent / "prose_scan_live_results.json"

    def flush():
        out.write_text(json.dumps(all_results, indent=2))

    print("=" * 92 + "\nFABRICATION-PRONE (Phase 0 §1/§3) — %d runs each\n" % args.fab_runs + "=" * 92)
    for qid, q in FAB_QUESTIONS:
        for i in range(args.fab_runs):
            all_results.append(run_question(qid, q, i + 1)); flush(); sys.stdout.flush()

    print("\n" + "=" * 92 + "\nLEGITIMATE (false-positive / req-9) — %d runs each\n" % args.runs + "=" * 92)
    for qid, q in LEGIT_QUESTIONS:
        for i in range(args.runs):
            all_results.append(run_question(qid, q, i + 1)); flush(); sys.stdout.flush()

    summary = aggregate(all_results)
    flush()
    print("\nSaved -> %s" % out)
    if summary["legit_refused"] or summary["fab_leaked"]:
        print("\n*** ATTENTION: legit_refused=%d fab_leaked=%d ***" % (summary["legit_refused"], summary["fab_leaked"]))


if __name__ == "__main__":
    main()
