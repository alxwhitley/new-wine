#!/usr/bin/env python3
"""Generate and operate the retroactive closeness-check review queues.

The recorded calibration JSONL is authoritative. Generation reads source
chunks through a read-only Postgres connection solely to add review context.
Decisions are written only to a local JSON ledger; this script contains no
corpus mutation path and never changes proposition or chunk content.
"""

import argparse
import difflib
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = ROOT / "closeness_review" / "calibrated_corpus_recheck_2026-07-29.jsonl"
DEFAULT_OUTPUT = ROOT / "closeness_review" / "retroactive_triage"
EXPECTED_TOTAL = 213
EXPECTED_OVERLAP_ONLY = 137
EXPECTED_LONG_RUN = 74
EXPECTED_HOLDS = 2
FAST_DECISIONS = ("clear", "send to real-attention pile")
REAL_DECISIONS = (
    "keep as-is",
    "needs shortening or rewording",
    "pull from library",
)
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import closeness_check as cc  # noqa: E402


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_recorded_results(path: Path) -> List[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON on {0}:{1}: {2}".format(path, line_number, exc))
    ids = [record["proposition_id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Recorded calibration contains duplicate proposition IDs.")
    return records


def partition_flagged(records: Iterable[dict]) -> Tuple[List[dict], List[dict]]:
    overlap = [
        record for record in records
        if record.get("verdict") == "QUOTE_CANDIDATE"
        and record.get("signal") == "OVERLAP_FLOOR"
    ]
    long_run = [
        record for record in records
        if record.get("verdict") == "QUOTE_CANDIDATE"
        and record.get("signal") in ("12_WORD_RUN", "BOTH")
    ]
    holds = [
        record for record in records
        if record.get("verdict") == "HOLD_TOO_LITTLE"
    ]
    flagged_count = len(overlap) + len(long_run) + len(holds)
    observed = (len(overlap), len(long_run), len(holds), flagged_count)
    expected = (
        EXPECTED_OVERLAP_ONLY,
        EXPECTED_LONG_RUN,
        EXPECTED_HOLDS,
        EXPECTED_TOTAL,
    )
    if observed != expected:
        raise ValueError(
            "Recorded count mismatch: overlap-only={0}, long-run={1}, holds={2}, "
            "total={3}; expected {4}/{5}/{6}/{7}. Review before generating.".format(
                *(observed + expected)
            )
        )

    sort_key = lambda item: (
        item.get("teacher") or "",
        item.get("document") or "",
        int(item.get("proposition_index") or 0),
        item["proposition_id"],
    )
    # Holds are non-long-run cases. The fast queue can clear or escalate them.
    fast = sorted(overlap + holds, key=sort_key)
    real = sorted(long_run, key=sort_key)
    return fast, real


def balanced_batches(items: Sequence[dict], minimum: int = 15, maximum: int = 20) -> List[list]:
    if not items:
        return []
    batch_count = int(math.ceil(len(items) / float(maximum)))
    if len(items) < minimum:
        return [list(items)]
    while batch_count > 1 and len(items) // batch_count < minimum:
        batch_count -= 1
    base, remainder = divmod(len(items), batch_count)
    sizes = [base + (1 if index < remainder else 0) for index in range(batch_count)]
    if any(size < minimum or size > maximum for size in sizes):
        raise ValueError("Cannot divide {0} items into {1}-{2} item batches.".format(
            len(items), minimum, maximum
        ))
    batches = []
    offset = 0
    for size in sizes:
        batches.append(list(items[offset:offset + size]))
        offset += size
    return batches


def _token_spans(text: str) -> List[Tuple[str, int, int]]:
    return [(match.group(0).lower(), match.start(), match.end()) for match in WORD_RE.finditer(text)]


def raw_longest_run(passage: str, source: str) -> Tuple[str, ...]:
    passage_tokens = [token for token, _start, _end in _token_spans(passage)]
    source_tokens = [token for token, _start, _end in _token_spans(source)]
    match = difflib.SequenceMatcher(
        None, passage_tokens, source_tokens, autojunk=False
    ).find_longest_match(0, len(passage_tokens), 0, len(source_tokens))
    return tuple(passage_tokens[match.a:match.a + match.size])


def _find_run_span(text: str, run_tokens: Sequence[str]) -> Optional[Tuple[int, int]]:
    if not run_tokens:
        return None
    spans = _token_spans(text)
    words = [token for token, _start, _end in spans]
    target = [token.lower() for token in run_tokens]
    width = len(target)
    for index in range(len(words) - width + 1):
        if words[index:index + width] == target:
            return spans[index][1], spans[index + width - 1][2]
    return None


def highlight_token_run(text: str, run_tokens: Sequence[str]) -> str:
    span = _find_run_span(text, run_tokens)
    if span is None:
        raise ValueError("Could not locate recorded near-verbatim run in text.")
    start, end = span
    return text[:start] + "**" + text[start:end] + "**" + text[end:]


def context_excerpt(source: str, run_tokens: Sequence[str], radius: int = 420) -> str:
    source = re.sub(r"\s+", " ", source).strip()
    span = _find_run_span(source, run_tokens)
    if span is None:
        raise ValueError("Could not locate review anchor in source material.")
    run_start, run_end = span
    start = max(0, run_start - radius)
    end = min(len(source), run_end + radius)
    if start:
        boundary = source.find(" ", start)
        start = boundary + 1 if boundary >= 0 else start
    if end < len(source):
        boundary = source.rfind(" ", 0, end)
        end = boundary if boundary >= 0 else end
    excerpt = source[start:run_start] + "**" + source[run_start:run_end] + "**" + source[run_end:end]
    return ("…" if start else "") + excerpt + ("…" if end < len(source) else "")


def db_params() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise SystemExit("SUPABASE_DB_URL not set in backend/app/.env")
    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def fetch_source_texts(document_ids: Sequence[str]) -> Dict[str, str]:
    import psycopg2

    conn = psycopg2.connect(**db_params())
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT document_id, chunk_index, content
                FROM chunks
                WHERE document_id = ANY(%s::uuid[])
                ORDER BY document_id, chunk_index
                """,
                (list(document_ids),),
            )
            rows = cursor.fetchall()
    finally:
        conn.close()
    by_document: Dict[str, List[str]] = {}
    for document_id, _chunk_index, content in rows:
        by_document.setdefault(str(document_id), []).append(content or "")
    texts = {
        document_id: "\n\n".join(parts)
        for document_id, parts in by_document.items()
    }
    missing = sorted(set(document_ids) - set(texts))
    if missing:
        raise ValueError("No source chunks found for document IDs: {0}".format(", ".join(missing)))
    return texts


def initialize_ledger(path: Path, records: Sequence[dict]) -> dict:
    if path.exists():
        ledger = json.loads(path.read_text(encoding="utf-8"))
        if ledger.get("schema_version") != 1 or not isinstance(ledger.get("items"), dict):
            raise ValueError("Unsupported or malformed decision ledger: {0}".format(path))
    else:
        ledger = {
            "schema_version": 1,
            "purpose": "Local decisions only; no corpus actions are performed.",
            "items": {},
        }
    for record in records:
        proposition_id = record["proposition_id"]
        item = ledger["items"].setdefault(
            proposition_id,
            {
                "queue": record["queue"],
                "decision": None,
                "reviewed_at": None,
                "reviewer_note": "",
            },
        )
        if item.get("queue") != record["queue"]:
            raise ValueError("Queue changed for existing decision item {0}.".format(proposition_id))
    active_ids = {record["proposition_id"] for record in records}
    stale = sorted(set(ledger["items"]) - active_ids)
    if stale:
        raise ValueError("Decision ledger contains IDs absent from this calibration: {0}".format(
            ", ".join(stale)
        ))
    _write_json(path, ledger)
    return ledger


def validate_decision(queue: str, decision: str) -> str:
    allowed = FAST_DECISIONS if queue == "fast" else REAL_DECISIONS
    if decision not in allowed:
        raise ValueError(
            "Invalid {0} decision {1!r}; choose exactly one of: {2}".format(
                queue, decision, " / ".join(allowed)
            )
        )
    return decision


def _card_header(number: int, record: dict) -> List[str]:
    return [
        "## Item {0:03d}".format(number),
        "",
        "- Teacher: {0}".format(record["teacher"]),
        "- Source material: {0}".format(record["document"]),
        "- Proposition ID: `{0}`".format(record["proposition_id"]),
        "- Proposition index: {0}".format(record["proposition_index"]),
        "",
    ]


def _fast_card(number: int, record: dict, source: str) -> str:
    anchor = raw_longest_run(record["content"], source)
    if not anchor:
        anchor = tuple(_token_spans(record["content"])[0][0:1])
    context = context_excerpt(source, anchor)
    lines = _card_header(number, record)
    lines.extend([
        "**Flagged passage**",
        "",
        "> " + record["content"],
        "",
        "**Source context**",
        "",
        "> " + context,
        "",
        "**Decision — choose one:** [ ] clear  [ ] send to real-attention pile",
        "",
        "- Timestamp: `________________________`",
        "- Reviewer note: `____________________________________________________________`",
        "",
    ])
    return "\n".join(lines)


def compute_real_highlight_run(passage: str, source: str) -> Tuple[str, ...]:
    """Computes the near-verbatim highlight run for a real-attention card from
    RAW (unmasked) text via raw_longest_run — the same run-finding function
    _fast_card already uses, reused rather than reimplemented.

    This is deliberately SEPARATE from classify()'s own masked run
    (cc.longest_common_run), which generate()'s loop uses ONLY for the
    classifier-integrity check and must never feed into
    highlight_token_run/context_excerpt: masking (e.g. _mask_theology's plain
    word-regex substitution matching "Bible" inside "Bible's" — \\b matches
    between a word char and an apostrophe — and leaving a dangling "'s" that
    tokenize()'s [a-z0-9]+(?:'[a-z]+)? word regex then retokenizes as a
    standalone one-letter "s" token) can produce a run that is a real match
    in MASKED-token space but does not exist as a literal contiguous sequence
    in the real, unmasked text — highlight_token_run would then raise
    ValueError on a perfectly valid, correctly-classified item. See
    test_closeness_triage.py for the reproduced bug case (the masked run
    fails to locate; this raw run succeeds).

    Raises ValueError if no run is found at all (raw_longest_run returned an
    empty tuple), so callers can catch this alongside
    highlight_token_run's/context_excerpt's own ValueError and treat both as
    one rendering-failure case.
    """
    raw_run = raw_longest_run(passage, source)
    if not raw_run:
        raise ValueError("No raw verbatim run found between passage and source.")
    return raw_run


def _real_card(number: int, record: dict, source: str, raw_run: Sequence[str]) -> str:
    """Renders a real-attention card. `raw_run` must be a RAW (unmasked)
    token run from compute_real_highlight_run/raw_longest_run — never
    classify()'s masked run_tokens (see compute_real_highlight_run's
    docstring for why)."""
    passage = highlight_token_run(record["content"], raw_run)
    context = context_excerpt(source, raw_run, radius=650)
    lines = _card_header(number, record)
    lines.extend([
        "- Recorded signal: {0}; longest near-verbatim run: {1} words".format(
            record["signal"], record["longest_run_words"]
        ),
        "",
        "**Flagged passage — near-verbatim stretch highlighted**",
        "",
        "> " + passage,
        "",
        "**Source passage in context — same stretch highlighted**",
        "",
        "> " + context,
        "",
        "**Decision — choose one only:**",
        "",
        "- [ ] keep as-is",
        "- [ ] needs shortening or rewording",
        "- [ ] pull from library",
        "",
        "- Timestamp: `________________________`",
        "- Reviewer note: `____________________________________________________________`",
        "",
        "_Decision recording only. This queue never edits or removes library content._",
        "",
    ])
    return "\n".join(lines)


def _real_card_highlight_failed(number: int, record: dict, reason: str) -> str:
    """Fallback card for an item whose near-verbatim run (classified
    correctly and recorded in the JSONL) could not be located as a literal
    highlighted span in the raw text — see compute_real_highlight_run's
    docstring. Built through the same _card_header helper as _real_card so it
    still carries the `- Proposition ID:` line other tooling
    (_resolve_card_id, show_real) depends on. States the failure honestly;
    never fabricates or approximates a highlight, and never wraps unanchored
    text in `**...**` as if a real run were found."""
    lines = _card_header(number, record)
    lines.extend([
        "- Recorded signal: {0}; longest near-verbatim run: {1} words".format(
            record["signal"], record["longest_run_words"]
        ),
        "",
        "**Highlight rendering failed — the near-verbatim run could not be "
        "located as a literal contiguous span in the source text.**",
        "",
        "No highlighted excerpt is shown for this item. Reason: {0}".format(reason),
        "",
        "The item's recorded verdict itself was still validated against a "
        "fresh reconstruction before this rendering step ran; only the "
        "highlight rendering failed, not the underlying classification.",
        "",
        "**Flagged passage — full text, no highlight available**",
        "",
        "> " + record["content"],
        "",
        "**Decision — choose one only:**",
        "",
        "- [ ] keep as-is",
        "- [ ] needs shortening or rewording",
        "- [ ] pull from library",
        "",
        "- Timestamp: `________________________`",
        "- Reviewer note: `____________________________________________________________`",
        "",
        "_Decision recording only. This queue never edits or removes library content._",
        "",
    ])
    return "\n".join(lines)


def generate(results_path: Path, output_dir: Path) -> dict:
    records = load_recorded_results(results_path)
    fast, real = partition_flagged(records)
    source_texts = fetch_source_texts(sorted({
        record["document_id"] for record in fast + real
    }))

    params = db_params()
    name_pattern = cc.build_name_pattern(cc.build_name_set(params))
    verse_lookup = cc.build_verse_lookup(params)
    vocab_matcher = cc.build_vocab_matcher()

    fast_records = [dict(record, queue="fast") for record in fast]
    real_records = [dict(record, queue="real_attention") for record in real]
    ledger_path = output_dir / "decisions.json"
    initialize_ledger(ledger_path, fast_records + real_records)

    batches = balanced_batches(fast_records)
    fast_dir = output_dir / "fast_pile"
    fast_index = [
        "# Fast-pile batches",
        "",
        "139 recorded non-long-run items: 137 containment-only candidates plus 2 too-little holds.",
        "Use `python3 scripts/closeness_triage.py show-fast N` to page a batch in chat.",
        "",
    ]
    item_number = 0
    for batch_number, batch in enumerate(batches, 1):
        parts = [
            "# Fast pile — batch {0:02d} of {1:02d}".format(batch_number, len(batches)),
            "",
            "{0} items. Decisions are recorded in `../decisions.json`; these checkboxes are review prompts.".format(
                len(batch)
            ),
            "",
        ]
        for record in batch:
            item_number += 1
            parts.append(_fast_card(
                item_number, record, source_texts[record["document_id"]]
            ))
        filename = "batch_{0:02d}.md".format(batch_number)
        _write_text(fast_dir / filename, "\n".join(parts))
        fast_index.append(
            "- Batch {0:02d}: {1} items (`{2}`)".format(batch_number, len(batch), filename)
        )
    _write_text(fast_dir / "index.md", "\n".join(fast_index) + "\n")

    real_dir = output_dir / "real_attention"
    real_index = [
        "# Real-attention queue",
        "",
        "74 recorded long-run items, one card per file. This queue records decisions only.",
        "Use `python3 scripts/closeness_triage.py show-real` for the next undecided card.",
        "",
    ]
    highlight_failures: List[dict] = []
    for number, record in enumerate(real_records, 1):
        source = source_texts[record["document_id"]]
        # Classifier-integrity check -- reproduces the recorded JSONL's own
        # verdict via the SAME masked-token path classify() used. Unwrapped,
        # outside any try/except: a mismatch here means the recorded results
        # can no longer be reproduced and generation must stop, not silently
        # continue on stale/inconsistent calibration data. Never feed this
        # masked run into rendering -- see compute_real_highlight_run below.
        run_length, run_tokens = cc.longest_common_run(
            record["content"], source, name_pattern, verse_lookup, vocab_matcher
        )
        if run_length != int(record["longest_run_words"]):
            raise ValueError(
                "Recorded run mismatch for {0}: JSON={1}, reconstructed={2}. "
                "Review calibration inputs before generating.".format(
                    record["proposition_id"], record["longest_run_words"], run_length
                )
            )
        filename = "item_{0:03d}.md".format(number)
        # Rendering path is separate from the integrity check above and uses
        # RAW (unmasked) text, not the just-validated masked run_tokens --
        # see compute_real_highlight_run's docstring for why the masked run
        # can be un-renderable even for a correctly-classified item.
        try:
            raw_run = compute_real_highlight_run(record["content"], source)
            card_text = _real_card(number, record, source, raw_run)
        except ValueError as exc:
            highlight_failures.append({
                "proposition_id": record["proposition_id"],
                "item_number": number,
                "reason": str(exc),
            })
            print(
                "HIGHLIGHT_FAILURE item {0:03d} ({1}): {2}".format(
                    number, record["proposition_id"], exc
                )
            )
            card_text = _real_card_highlight_failed(number, record, str(exc))
        _write_text(real_dir / filename, card_text)
        real_index.append(
            "- Item {0:03d}: {1} — {2} (`{3}`)".format(
                number, record["teacher"], record["document"], filename
            )
        )
    _write_text(real_dir / "index.md", "\n".join(real_index) + "\n")

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recorded_results": str(results_path.relative_to(ROOT)),
        "recorded_corpus_items": len(records),
        "flagged_total": len(fast_records) + len(real_records),
        "fast_pile": {
            "count": len(fast_records),
            "containment_only": EXPECTED_OVERLAP_ONLY,
            "too_little_holds": EXPECTED_HOLDS,
            "batch_count": len(batches),
            "batch_sizes": [len(batch) for batch in batches],
        },
        "real_attention": {
            "count": len(real_records),
            "signals": {
                "12_WORD_RUN": sum(1 for item in real if item["signal"] == "12_WORD_RUN"),
                "BOTH": sum(1 for item in real if item["signal"] == "BOTH"),
            },
        },
        "highlight_failures": highlight_failures,
        "corpus_access": "SELECT-only chunks/name aliases/WEB verses; no corpus writes",
        "decision_effect": "local record only; no auto-fixing or corpus action",
    }
    _write_json(output_dir / "manifest.json", manifest)
    return manifest


def _load_ledger(output_dir: Path) -> dict:
    path = output_dir / "decisions.json"
    if not path.exists():
        raise SystemExit("Decision ledger not found. Run the generate command first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_card_id(output_dir: Path, queue: str, selector: str) -> str:
    ledger = _load_ledger(output_dir)
    if selector in ledger["items"]:
        proposition_id = selector
    else:
        try:
            number = int(selector)
        except ValueError:
            raise ValueError("Selector must be an item number or proposition ID.")
        pattern = "item_{0:03d}.md".format(number)
        card_path = output_dir / ("real_attention" if queue == "real_attention" else "fast_pile") / pattern
        if queue == "fast":
            raise ValueError("Fast decisions use proposition IDs shown on batch cards.")
        if not card_path.exists():
            raise ValueError("No real-attention item {0}.".format(number))
        match = re.search(r"Proposition ID: `([^`]+)`", card_path.read_text(encoding="utf-8"))
        if not match:
            raise ValueError("Card is missing its proposition ID.")
        proposition_id = match.group(1)
    item = ledger["items"].get(proposition_id)
    if item is None or item["queue"] != queue:
        raise ValueError("Item {0} is not in the {1} queue.".format(proposition_id, queue))
    return proposition_id


def record_decision(output_dir: Path, queue: str, selector: str, decision: str, note: str) -> dict:
    decision = validate_decision(queue, decision)
    proposition_id = _resolve_card_id(output_dir, queue, selector)
    path = output_dir / "decisions.json"
    ledger = _load_ledger(output_dir)
    item = ledger["items"][proposition_id]
    item["decision"] = decision
    item["reviewed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    item["reviewer_note"] = note
    _write_json(path, ledger)
    return dict(item, proposition_id=proposition_id)


def show_real(output_dir: Path, selector: Optional[str]) -> str:
    if selector is None:
        ledger = _load_ledger(output_dir)
        undecided = {
            proposition_id for proposition_id, item in ledger["items"].items()
            if item["queue"] == "real_attention" and item["decision"] is None
        }
        for path in sorted((output_dir / "real_attention").glob("item_*.md")):
            text = path.read_text(encoding="utf-8")
            match = re.search(r"Proposition ID: `([^`]+)`", text)
            if match and match.group(1) in undecided:
                return text
        return "All real-attention items have decisions.\n"
    path = output_dir / "real_attention" / "item_{0:03d}.md".format(int(selector))
    return path.read_text(encoding="utf-8")


def progress(output_dir: Path) -> dict:
    ledger = _load_ledger(output_dir)
    result = {}
    for queue in ("fast", "real_attention"):
        items = [item for item in ledger["items"].values() if item["queue"] == queue]
        decided = sum(item["decision"] is not None for item in items)
        result[queue] = {
            "total": len(items),
            "decided": decided,
            "remaining": len(items) - decided,
        }
    return result


def main() -> None:
    load_dotenv(ROOT / "backend" / "app" / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)

    fast_parser = subparsers.add_parser("show-fast")
    fast_parser.add_argument("batch", type=int)

    real_parser = subparsers.add_parser("show-real")
    real_parser.add_argument("item", nargs="?")

    decide_fast = subparsers.add_parser("decide-fast")
    decide_fast.add_argument("proposition_id")
    decide_fast.add_argument("decision", choices=FAST_DECISIONS)
    decide_fast.add_argument("--note", default="")

    decide_real = subparsers.add_parser("decide-real")
    decide_real.add_argument("item")
    decide_real.add_argument("decision", choices=REAL_DECISIONS)
    decide_real.add_argument("--note", default="")

    subparsers.add_parser("progress")
    args = parser.parse_args()

    if args.command == "generate":
        print(json.dumps(generate(args.results, args.output), indent=2))
    elif args.command == "show-fast":
        path = args.output / "fast_pile" / "batch_{0:02d}.md".format(args.batch)
        print(path.read_text(encoding="utf-8"))
    elif args.command == "show-real":
        print(show_real(args.output, args.item))
    elif args.command == "decide-fast":
        print(json.dumps(record_decision(
            args.output, "fast", args.proposition_id, args.decision, args.note
        ), indent=2))
    elif args.command == "decide-real":
        print(json.dumps(record_decision(
            args.output, "real_attention", args.item, args.decision, args.note
        ), indent=2))
    elif args.command == "progress":
        print(json.dumps(progress(args.output), indent=2))


if __name__ == "__main__":
    main()
