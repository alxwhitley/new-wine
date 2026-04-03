import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def embed_text(text: str) -> list[float]:
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
