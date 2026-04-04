"""
Recursive character text splitter.

Splits text by trying separators in priority order: \n\n, \n, ". ", " ", "".
Each chunk targets ~1000 characters with 200 characters of overlap (~20%).
"""

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def token_len(text: str) -> int:
    """Approximate token count (kept for backward compat with ingest.py)."""
    return len(text) // 4


def _split_text(text: str, separators: list[str]) -> list[str]:
    """Recursively split text using the first separator that produces splits."""
    if len(text) <= CHUNK_SIZE:
        return [text] if text.strip() else []

    sep = separators[0]
    remaining_seps = separators[1:] if len(separators) > 1 else [""]

    if sep == "":
        # Hard split at CHUNK_SIZE
        chunks = []
        for i in range(0, len(text), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk = text[i:i + CHUNK_SIZE]
            if chunk.strip():
                chunks.append(chunk)
            if i + CHUNK_SIZE >= len(text):
                break
        return chunks

    parts = text.split(sep)

    chunks = []
    current = ""

    for part in parts:
        # What the chunk would look like if we add this part
        candidate = current + sep + part if current else part

        if len(candidate) <= CHUNK_SIZE:
            current = candidate
        else:
            # Flush current chunk
            if current.strip():
                chunks.append(current)
            # If this single part is too big, recurse with finer separators
            if len(part) > CHUNK_SIZE:
                sub_chunks = _split_text(part, remaining_seps)
                chunks.extend(sub_chunks)
                current = ""
            else:
                current = part

    if current.strip():
        chunks.append(current)

    return chunks


def _add_overlap(chunks: list[str]) -> list[str]:
    """Add overlap by prepending the tail of the previous chunk."""
    if len(chunks) <= 1:
        return chunks

    result = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        overlap = prev[-CHUNK_OVERLAP:] if len(prev) > CHUNK_OVERLAP else prev
        # Find a clean break point in the overlap (nearest space)
        space_idx = overlap.find(" ")
        if space_idx > 0:
            overlap = overlap[space_idx + 1:]
        merged = overlap + chunks[i]
        result.append(merged)

    return result


def chunk_pages(pages: list[str]) -> list[tuple[str, int]]:
    """
    Recursive character text splitter with overlap.
    Returns list of (chunk_text, page_number) tuples. Page numbers are 1-indexed.
    """
    all_chunks: list[tuple[str, int]] = []

    for page_num, page_text in enumerate(pages, start=1):
        page_text = page_text.strip()
        if not page_text:
            continue
        raw_chunks = _split_text(page_text, SEPARATORS)
        overlapped = _add_overlap(raw_chunks)
        for chunk in overlapped:
            if chunk.strip():
                all_chunks.append((chunk.strip(), page_num))

    return all_chunks


def chunk_text(text: str) -> list[tuple[str, int]]:
    """Convenience wrapper: chunk a single text string (treated as one page)."""
    return chunk_pages([text])
