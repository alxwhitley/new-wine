"""
Token-based text chunker for Rhemata.

Splits text into chunks of ~chunk_target tokens with overlap.
Breaking priority: headings → paragraph breaks → sentence boundaries → hard split.
Uses tiktoken with cl100k_base encoding.
"""

import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def token_len(text: str) -> int:
    """Return the exact token count for a string."""
    return len(_enc.encode(text))


def chunk_text(text: str, chunk_target: int = 550, overlap: int = 80) -> list[str]:
    """Split text into chunks of approximately `chunk_target` tokens with `overlap`."""
    tokens = _enc.encode(text)
    if len(tokens) <= chunk_target:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_target, len(tokens))
        chunk_str = _enc.decode(tokens[start:end])

        # Try to break at a clean boundary (only if not at end of text)
        if end < len(tokens):
            # Priority 1: heading boundary (\n# or \n## )
            last_heading = max(
                chunk_str.rfind("\n# "),
                chunk_str.rfind("\n## "),
            )
            if last_heading > len(chunk_str) * 0.3:
                chunk_str = chunk_str[:last_heading]
                end = start + len(_enc.encode(chunk_str))
            else:
                # Priority 2: paragraph break
                last_para = chunk_str.rfind("\n\n")
                if last_para > len(chunk_str) * 0.5:
                    chunk_str = chunk_str[:last_para]
                    end = start + len(_enc.encode(chunk_str))
                else:
                    # Priority 3: sentence boundary
                    last_period = chunk_str.rfind(". ")
                    if last_period > len(chunk_str) * 0.5:
                        chunk_str = chunk_str[:last_period + 1]
                        end = start + len(_enc.encode(chunk_str))

        if chunk_str.strip():
            chunks.append(chunk_str.strip())

        if end >= len(tokens):
            break

        advance = max(end - start - overlap, 1)
        start = start + advance

    return chunks
