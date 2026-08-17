"""Reusable, deterministic quote-candidate GENERATION for any teacher/
source -- not just Derek Prince's own corpus-tuned
extract_quote_candidates_derek_prince.py.

This module proposes candidate spans; it makes no approval decision and
never touches a database. app.services.quote_verifier.verify_quote_candidate
remains the sole authority on whether a candidate is actually quotable --
see extract_quote_candidates_article.py for the tool that composes this
generation layer with that unmodified verifier.

Scope, deliberately narrow (see this module's own top-level docstring in
the article extraction tool for the exact remaining product decision this
does NOT invent an answer to): every check here is a STRUCTURAL safety
filter (length bounds, boundary safety, avoiding a fragment that opens on
a weak connective, avoiding a block dominated by someone else's quoted
words, avoiding verse-per-line poetic formatting) -- never a "how quotable
does this sound" quality score. extract_quote_candidates_derek_prince.py's
own _score_candidate() ranks candidates by corpus-specific, hand-calibrated
weights (theological vocabulary hits, preferred length bands, oral-speech
markers like "applause"/"turn to your Bible") tuned against Derek Prince's
own spoken-sermon corpus on 2026-08-13 -- reusing those exact weights for
arbitrary written article prose from an unknown author would be inventing
a calibration decision this module deliberately leaves to a human with
real content to look at, not a structural safety property. This module
gives every structurally eligible candidate to the caller in document
order; ranking/scoring, if a caller wants one, is the caller's own
decision to make on top of this.
"""
from __future__ import annotations

import re
from typing import List, Tuple

CandidateSpan = Tuple[int, int, str]

_SENT_RE = re.compile(r"[^.!?]*[.!?]+[\"'’”»]?")

_WEAK_START_WORDS = {
    "and", "but", "or", "so", "then", "there", "here", "now", "well", "oh",
    "ah", "yes", "no", "okay", "all", "why", "what", "where", "when", "who",
    "how", "if", "because", "for", "yet", "nor", "nevertheless", "however",
    "moreover", "furthermore", "therefore", "thus", "consequently",
    "meanwhile", "instead", "otherwise", "anyhow", "anyway",
}

# A long double-quote-delimited span is, structurally, someone else's
# words being quoted, not the credited author's own sentence -- the same
# signal quote_subchunk_exclusion.py's long_quotation detector and the
# Prince script's own _RE_LONG_DOUBLE_QUOTE use, kept at the same 80-char
# threshold for consistency across this codebase's quote tooling.
_RE_LONG_QUOTE = re.compile(r"[“\"][^”\"]{80,}?[”\"]", re.DOTALL)


def split_sentences(text: str) -> List[CandidateSpan]:
    """Return (start, end, sentence_text) spans, each an exact substring
    of text, split on terminal punctuation with an optional trailing
    closing quote/guillemet kept attached to its own sentence."""
    out: List[CandidateSpan] = []
    for m in _SENT_RE.finditer(text):
        raw = m.group()
        leading_ws = len(raw) - len(raw.lstrip())
        start = m.start() + leading_ws
        end = m.end()
        sentence = text[start:end]
        if sentence:
            out.append((start, end, sentence))
    return out


def _is_structurally_eligible(text: str, *, min_len: int, max_len: int) -> bool:
    length = len(text)
    if length < min_len or length > max_len:
        return False

    stripped = text.strip()
    if not stripped:
        return False
    first_char = stripped[0]
    if not first_char.isalpha() or first_char.islower():
        return False

    first_word = stripped.split()[0].lower().strip(".,;:!?\"'")
    if first_word in _WEAK_START_WORDS:
        return False

    if "\n\n" in text:
        return False

    digits = sum(ch.isdigit() for ch in text)
    if digits > length * 0.12:
        return False

    quoted_chars = sum(len(m.group()) for m in _RE_LONG_QUOTE.finditer(text))
    if length and (quoted_chars / length) > 0.40:
        return False

    return True


def generate_candidate_spans(
    chunk_content: str,
    *,
    min_len: int = 120,
    max_len: int = 500,
    max_sentence_window: int = 3,
) -> List[CandidateSpan]:
    """Return every structurally eligible (start, end, text) candidate
    span from one chunk's content, as a 1-to-max_sentence_window-sentence
    window, in document order. A candidate flush against either edge of
    the chunk is skipped here (verify_quote_candidate's boundary-proximity
    check would refuse it anyway; skipping early saves a verifier call,
    matching extract_quote_candidates_derek_prince.py's own convention)."""
    sentences = split_sentences(chunk_content)
    if not sentences:
        return []

    candidates: List[CandidateSpan] = []
    n = len(sentences)
    for i in range(n):
        for j in range(i, min(i + max_sentence_window, n)):
            start = sentences[i][0]
            end = sentences[j][1]
            if start == 0 or end == len(chunk_content):
                continue
            text = chunk_content[start:end]
            if _is_structurally_eligible(text, min_len=min_len, max_len=max_len):
                candidates.append((start, end, text))
    return candidates
