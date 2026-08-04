"""Reconnect-resilient psycopg2 access for the async answer path.

The live serving path talks to Supabase over PostgREST (supabase-py). The queue
needs row-locking semantics (SELECT ... FOR UPDATE SKIP LOCKED) that PostgREST
cannot express, so workers use direct Postgres via psycopg2 -- the same
`SUPABASE_DB_URL` the ingest/backfill scripts already use.

A long model stall can outlast the pooler's idle timeout and drop the
connection mid-work (observed 2026-08-02, CLAUDE.md landmine). `run()` reopens
on psycopg2 OperationalError/InterfaceError and retries once, mirroring
scripts/run_full_backfill.py's resilience.

Python 3.9 (Invariant 1): Optional[...] typing only.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

T = TypeVar("T")

# Keep the DSN parse in one place so every worker connection is identical.
_DSN_KWARGS: Optional[dict] = None
_DSN_LOCK = threading.Lock()


def _dsn_kwargs() -> dict:
    global _DSN_KWARGS
    if _DSN_KWARGS is None:
        with _DSN_LOCK:
            if _DSN_KWARGS is None:
                db_url = os.environ.get("SUPABASE_DB_URL")
                if not db_url:
                    raise RuntimeError(
                        "SUPABASE_DB_URL is not set (backend/app/.env) -- the async "
                        "answer worker needs direct Postgres access."
                    )
                p = urlparse(db_url)
                _DSN_KWARGS = {
                    "host": p.hostname,
                    "port": p.port or 5432,
                    "user": unquote(p.username or ""),
                    "password": unquote(p.password or ""),
                    "dbname": p.path.lstrip("/"),
                    # Survive idle pooler drops during long generations.
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 5,
                }
    return _DSN_KWARGS


def connect():
    """Open a new autocommit-off psycopg2 connection."""
    conn = psycopg2.connect(**_dsn_kwargs())
    conn.autocommit = False
    return conn


class Db:
    """A single worker-owned connection with reconnect-on-drop.

    Not thread-safe: give each concurrent worker slot its own Db (psycopg2
    connections must not be shared across threads).
    """

    def __init__(self):
        self._conn = None  # type: Optional[Any]

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = connect()
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def _reconnect(self) -> None:
        try:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
        except Exception:
            pass
        self._conn = connect()

    def run(self, fn: Callable[[Any], T]) -> T:
        """Run `fn(conn)` in a transaction, committing on success.

        On a connection-level failure (OperationalError/InterfaceError) the
        connection is reopened and `fn` retried exactly once. Any other
        exception rolls back and propagates -- callers decide the job's fate.
        """
        for attempt in (1, 2):
            conn = self.conn
            try:
                result = fn(conn)
                conn.commit()
                return result
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                self._reconnect()
                if attempt == 2:
                    raise
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    self._reconnect()
                raise
        # Unreachable: the loop either returns or raises.
        raise RuntimeError("Db.run exhausted retries without returning")


def dict_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
