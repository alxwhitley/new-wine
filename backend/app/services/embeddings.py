import logging
import math
import os
from typing import List

from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None

EMBED_BATCH_SIZE = 100


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Shared home for the one cosine-similarity implementation embedding
    consumers should use (position_papers.py's pillar matching, quotes.py's
    quote-topic matching, and any future one) -- consolidated here 2026-08-06
    rather than left as position_papers.py's own private `_cosine`, the same
    "one shared implementation, not independently-maintained copies" move
    already made for DOMINANCE_THRESHOLD/determine_scope (see dominance.py)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def embed_text(text: str) -> List[float]:
    try:
        response = _get_client().embeddings.create(
            input=text,
            model="text-embedding-3-small",
            dimensions=1536,
        )
        return response.data[0].embedding
    except Exception:
        logger.exception("OpenAI embedding call failed")
        raise


def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed multiple texts in as few OpenAI calls as possible, sub-batched at
    EMBED_BATCH_SIZE. Returns embeddings in the same order as the input
    texts."""
    if not texts:
        return []
    client = _get_client()
    embeddings: List[List[float]] = []
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i:i + EMBED_BATCH_SIZE]
            response = client.embeddings.create(
                input=batch,
                model="text-embedding-3-small",
                dimensions=1536,
            )
            embeddings.extend(item.embedding for item in response.data)
        return embeddings
    except Exception:
        logger.exception("OpenAI batch embedding call failed")
        raise
