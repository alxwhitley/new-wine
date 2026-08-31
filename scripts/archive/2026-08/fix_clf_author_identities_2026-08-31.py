"""Clean up CLF author identities (Alex's ruling, 2026-08-30: keep names, fix data).

Two changes, both keyed on exact document id so nothing else can be caught:

  A. Four author corrections -- a parser artifact and three title-prefixed
     duplicates of an identity that already exists in bare form. These stay
     `citable`; the point is that "Pastor Paul Kidd" and "Paul Kidd" are one
     person and must not each draw their own share of producer.py's
     per-author 3-chunk cap.

  B. Three genuinely two-speaker documents -> `silent_context`.
     `reference_verifier.build_retrieval_grounding()` builds `author_keys` via
     `normalize_alias_key(author)` on the WHOLE string and matches exactly --
     there is no comma splitting anywhere on that path. So a document authored
     "Paul Kidd, Shabaka Williams" permits only that literal joined string:
     a correct "Paul Kidd" attribution normalizes to `paul kidd`, misses, and
     can drive a regenerate-then-refuse. Silencing them makes crediting one
     speaker's words to the other structurally impossible (ranked failure
     mode #2) at the cost of attribution on 3 documents.

Dry-run by default; --apply required. Reconciles after writing.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/Users/alexwhitley/rhemata/backend")))
from app.services.async_answers.db import connect  # noqa: E402

# (document_id, expected_current_author, new_author)
AUTHOR_FIXES = [
    ("235e3009-f22a-4a41-b06a-f37c0edab4b4", "Sunday", "Moses Ng'etich"),
    ("0b3d5910-e4d5-46d3-8f3f-2616537cfeb6", "Pastor Paul Kidd", "Paul Kidd"),
    ("568e68f7-73b1-43ce-962f-fabc5805048f", "Bishop JB Masinde", "JB Masinde"),
    ("260b9c97-ab77-45e7-b0b1-58913897d25c", "Pastor Peter Kamau", "Peter Kamau"),
]

# (document_id, expected_current_author)
SILENCE = [
    ("9acaca0e-b6fc-4ed4-9687-cd5fa603a4e5", "Paul Kidd, Alex Whitley"),
    ("5629a0c8-e0df-4be0-aa45-f6044a0faa23", "Paul Kidd, Shabaka Williams"),
    ("714e598c-6898-419b-afa4-c4bf2e403ebb", "Paul Kidd, Shabaka Williams"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    con = connect()
    con.autocommit = False
    cur = con.cursor()

    # Guard: every target must exist, belong to CLF, and still hold the author
    # this script was written against. A drifted row aborts the whole batch.
    ids = [d for d, *_ in AUTHOR_FIXES] + [d for d, _ in SILENCE]
    cur.execute("""SELECT d.id::text, d.author, d.citation_mode, s.name
                   FROM documents d JOIN sources s ON s.id = d.source_id
                   WHERE d.id::text = ANY(%s)""", (ids,))
    live = {r[0]: r[1:] for r in cur.fetchall()}

    problems = []
    for did, expected, _new in AUTHOR_FIXES:
        got = live.get(did)
        if not got:
            problems.append(f"{did}: not found")
        elif got[0] != expected:
            problems.append(f"{did}: author is {got[0]!r}, expected {expected!r}")
        elif got[2] != "CLF Church":
            problems.append(f"{did}: source is {got[2]!r}, not CLF Church")
    for did, expected in SILENCE:
        got = live.get(did)
        if not got:
            problems.append(f"{did}: not found")
        elif got[0] != expected:
            problems.append(f"{did}: author is {got[0]!r}, expected {expected!r}")
        elif got[2] != "CLF Church":
            problems.append(f"{did}: source is {got[2]!r}, not CLF Church")
    if problems:
        con.rollback()
        sys.exit("ABORT — live data drifted:\n  " + "\n  ".join(problems))

    print("A. author corrections (stay citable)")
    for did, old, new in AUTHOR_FIXES:
        print(f"   {did}  {old!r} -> {new!r}")
    print("\nB. two-speaker docs -> silent_context")
    for did, old in SILENCE:
        print(f"   {did}  {old!r}  citable -> silent_context")

    if not args.apply:
        con.rollback()
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return

    for did, _old, new in AUTHOR_FIXES:
        cur.execute("UPDATE documents SET author=%s WHERE id::text=%s", (new, did))
        assert cur.rowcount == 1, f"{did}: {cur.rowcount} rows"
    for did, _old in SILENCE:
        cur.execute(
            "UPDATE documents SET citation_mode='silent_context' WHERE id::text=%s",
            (did,))
        assert cur.rowcount == 1, f"{did}: {cur.rowcount} rows"
    con.commit()
    print("\ncommitted 7 updates")

    # Reconcile from a fresh read, not from rowcounts.
    cur.execute("""SELECT d.id::text, d.author, d.citation_mode
                   FROM documents d WHERE d.id::text = ANY(%s)""", (ids,))
    after = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    ok = True
    for did, _old, new in AUTHOR_FIXES:
        got = after[did]
        good = got[0] == new and got[1] == "citable"
        ok &= good
        print(f"   {'OK ' if good else 'BAD'} {did} author={got[0]!r} mode={got[1]}")
    for did, _old in SILENCE:
        got = after[did]
        good = got[1] == "silent_context"
        ok &= good
        print(f"   {'OK ' if good else 'BAD'} {did} mode={got[1]}")
    print("\nreconciliation:", "PASS" if ok else "FAIL")
    con.close()


if __name__ == "__main__":
    main()
