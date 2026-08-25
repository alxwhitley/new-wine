"""In-memory, write-free timing trace for the B6 answer benchmark."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional


class LatencyTrace:
    """Collect monotonic stage durations without logging answer or source text."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._stages: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {}

    @contextmanager
    def span(self, name: str) -> Iterator[Dict[str, Any]]:
        started_at = self._clock()
        stage: Dict[str, Any] = {"name": name, "_started_at": started_at}
        try:
            yield stage
        except Exception:
            stage["outcome"] = "error"
            raise
        finally:
            stage["duration_ms"] = round((self._clock() - started_at) * 1000, 3)
            stage.pop("_started_at", None)
            self._stages.append(stage)

    def mark(self, stage: Dict[str, Any], key: str) -> None:
        """Record an offset from the enclosing span's start exactly once."""
        if key not in stage:
            stage[key] = round((self._clock() - stage["_started_at"]) * 1000, 3)

    def annotate(self, **metadata: Any) -> None:
        self._metadata.update(metadata)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"schema_version": 1, "stages": list(self._stages)}
        if self._metadata:
            payload["metadata"] = dict(self._metadata)
        return payload
