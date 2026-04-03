import re

import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

CHUNK_TARGET = 600   # target chunk size in tokens
CHUNK_OVERLAP = 80   # overlap between adjacent chunks (tokens)
MIN_CHUNK_TOKENS = 100  # skip chunks shorter than this


def token_len(text: str) -> int:
    return len(enc.encode(text))


def chunk_pages(pages: list[str]) -> list[tuple[str, int]]:
    """
    Sliding-window chunker. Splits page text into sentences, then groups
    into chunks of ~CHUNK_TARGET tokens with CHUNK_OVERLAP overlap.
    Returns list of (chunk_text, page_number) tuples. Page numbers are 1-indexed.
    """
    sentence_page = []
    for page_num, page_text in enumerate(pages, start=1):
        sentences = re.split(r'(?<=[.!?])\s+', page_text.strip())
        for s in sentences:
            s = s.strip()
            if s:
                sentence_page.append((s, page_num))

    if not sentence_page:
        return []

    chunks = []
    i = 0
    while i < len(sentence_page):
        current_text = ""
        current_page = sentence_page[i][1]
        j = i
        while j < len(sentence_page) and token_len(current_text) < CHUNK_TARGET:
            if current_text:
                current_text += " "
            current_text += sentence_page[j][0]
            j += 1

        if token_len(current_text) >= MIN_CHUNK_TOKENS:
            chunks.append((current_text, current_page))

        if j >= len(sentence_page):
            break
        overlap_text = ""
        overlap_start = j
        for k in range(j - 1, i - 1, -1):
            candidate = sentence_page[k][0] + " " + overlap_text if overlap_text else sentence_page[k][0]
            if token_len(candidate) > CHUNK_OVERLAP:
                break
            overlap_text = candidate
            overlap_start = k
        i = overlap_start if overlap_start > i else j

    return chunks


def chunk_text(text: str) -> list[tuple[str, int]]:
    """Convenience wrapper: chunk a single text string (treated as one page)."""
    return chunk_pages([text])
