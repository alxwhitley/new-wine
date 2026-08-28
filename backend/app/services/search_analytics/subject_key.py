"""Irreversible, versioned HMAC-derived subject keys for search analytics.

A subject key stands in for an account in search_occurrences /
search_gap_details -- never the account id itself. Derivation is one-way
(HMAC, not encryption): given a subject key, the account id cannot be
recovered even with the secret, only forward-verified (recompute and
compare). Never log a subject key alongside anything identifying; never
return one from any API.

Rotation: to rotate, set ANALYTICS_HMAC_SECRET_V{n+1} and bump
CURRENT_SUBJECT_KEY_VERSION. Old rows keep whatever subject_key they were
written with (immutable) -- deletion for an old version stays possible as
long as its secret env var is still configured (see consent.py's
withdraw(), which recomputes against every retired version on record).

Python 3.9 (Invariant 1).
"""
from __future__ import annotations

import hashlib
import hmac
import os

CURRENT_SUBJECT_KEY_VERSION = 1


class MissingHmacSecretError(Exception):
    """Raised when the HMAC secret for a requested version isn't configured.
    Never derive a subject key from a missing/empty secret -- fail loudly
    instead of silently using a weak or predictable key."""


def _secret_bytes(version: int) -> bytes:
    env_name = "ANALYTICS_HMAC_SECRET_V%d" % version
    secret = os.environ.get(env_name)
    if not secret:
        raise MissingHmacSecretError(
            "%s is not set -- cannot derive a subject key for version %d" % (env_name, version)
        )
    return secret.encode("utf-8")


def derive_subject_key(user_id: str, version: int) -> str:
    """HMAC-SHA256(secret_v, user_id), hex-encoded. Deterministic per
    (user_id, version); irreversible; never the user_id itself."""
    secret = _secret_bytes(version)
    return hmac.new(secret, user_id.encode("utf-8"), hashlib.sha256).hexdigest()
