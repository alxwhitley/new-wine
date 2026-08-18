#!/usr/bin/env python3
"""One-at-a-time durable worker for cleared source-ingest queue rows."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / "backend" / "app" / ".env")

from app.db.supabase import get_supabase  # noqa: E402
from app.services.async_answers.db import Db  # noqa: E402
from source_ingest_queue import jobs  # noqa: E402
from source_ingest_queue.processor import (  # noqa: E402
    AttentionRequired,
    RetryableIngestError,
    execute_ingest,
    prepare_ingest,
)


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("source_ingest_worker")


def _uuid_argument(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a UUID") from exc


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Durable source-ingest worker")
    parser.add_argument("--once", action="store_true", help="drain ready work and exit")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-idle", type=float, default=None)
    parser.add_argument("--dry-run-row", default=None, metavar="UUID")
    parser.add_argument("--row-id", type=_uuid_argument, default=None, metavar="UUID")
    args = parser.parse_args(argv)
    if args.row_id is not None and not args.once:
        parser.error("--row-id requires --once")
    if args.row_id is not None and args.dry_run_row is not None:
        parser.error("--row-id cannot be combined with --dry-run-row")
    return args


def _db_params_from_env() -> dict:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is not set")
    parsed = urlparse(db_url)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise RuntimeError("SUPABASE_DB_URL is invalid")
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }


def _redacted_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = "[%s]" % hostname
    if parsed.port is not None:
        default_port = 443 if parsed.scheme == "https" else 80
        if parsed.port != default_port:
            hostname = "%s:%d" % (hostname, parsed.port)
    return urlunsplit((parsed.scheme, hostname, parsed.path or "/", "", ""))


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        db_factory,
        jobs_api,
        row_id: str,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float,
    ):
        self._db_factory = db_factory
        self._jobs = jobs_api
        self._row_id = row_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="source-ingest-heartbeat",
            daemon=True,
        )

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        db = self._db_factory()
        try:
            while not self._stop.wait(self._interval_seconds):
                try:
                    renewed = self._jobs.heartbeat(
                        db,
                        self._row_id,
                        self._worker_id,
                        self._lease_seconds,
                    )
                except Exception:
                    logger.error(
                        "[%s] row %s heartbeat failed",
                        self._worker_id,
                        self._row_id,
                    )
                    self._lost.set()
                    return
                if not renewed:
                    self._lost.set()
                    return
        finally:
            db.close()


class Worker:
    def __init__(
        self,
        *,
        db_factory=Db,
        supabase_factory=get_supabase,
        prepare_fn=prepare_ingest,
        execute_fn=execute_ingest,
        jobs_api=jobs,
        db_params_factory=_db_params_from_env,
        heartbeat_factory=_LeaseHeartbeat,
        poll_interval: float = 2.0,
        once: bool = False,
        max_idle: Optional[float] = None,
        worker_id: Optional[str] = None,
        lease_seconds: int = 300,
        only_row_id: Optional[str] = None,
    ):
        self._db_factory = db_factory
        self._supabase_factory = supabase_factory
        self._prepare = prepare_fn
        self._execute = execute_fn
        self._jobs = jobs_api
        self._db_params_factory = db_params_factory
        self._heartbeat_factory = heartbeat_factory
        self.poll_interval = max(0.0, poll_interval)
        self.once = once
        self.max_idle = max_idle
        self.worker_id = worker_id or "%s-%d" % (socket.gethostname(), os.getpid())
        self.lease_seconds = lease_seconds
        self.only_row_id = only_row_id
        self._heartbeat_interval = max(1.0, min(30.0, lease_seconds / 3.0))
        self._db = None
        self._supabase = None
        self._db_params = None
        self._stop = threading.Event()

    def _job_db(self):
        if self._db is None:
            self._db = self._db_factory()
        return self._db

    def _supabase_client(self):
        if self._supabase is None:
            self._supabase = self._supabase_factory()
        return self._supabase

    def _direct_db_params(self):
        if self._db_params is None:
            self._db_params = self._db_params_factory()
        return self._db_params

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def tick(self, *, only_row_id: Optional[str] = None) -> bool:
        db = self._job_db()
        target_row_id = self.only_row_id if only_row_id is None else only_row_id
        row = self._jobs.claim_next(
            db,
            self.worker_id,
            self.lease_seconds,
            only_row_id=target_row_id,
        )
        if not row:
            return False

        row_id = str(row["id"])
        heartbeat = self._heartbeat_factory(
            db_factory=self._db_factory,
            jobs_api=self._jobs,
            row_id=row_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            interval_seconds=self._heartbeat_interval,
        )
        heartbeat.start()
        terminal = None
        prepared = None
        result = None
        try:
            if not self._jobs.set_stage(
                db, row_id, self.worker_id, "fetching"
            ):
                return True
            prepared = self._prepare(
                row,
                db=self._supabase_client(),
                db_params=self._direct_db_params(),
                dry_run=False,
            )
            if heartbeat.lost:
                return True
            if not self._jobs.set_stage(db, row_id, self.worker_id, "writing"):
                return True
            result = self._execute(
                prepared,
                db=self._supabase_client(),
                db_params=self._direct_db_params(),
            )
        except AttentionRequired as exc:
            terminal = ("attention", exc.code, exc.detail, False)
        except RetryableIngestError as exc:
            terminal = ("retry", exc.code, exc.detail, exc.attempted)
        except Exception:
            terminal = (
                "retry",
                "internal_error",
                "source processing failed",
                False,
            )
        finally:
            heartbeat.stop()

        if heartbeat.lost:
            logger.warning("[%s] row %s lease lost", self.worker_id, row_id)
            return True
        if terminal is not None:
            kind, code, detail, attempted = terminal
            if kind == "attention":
                self._jobs.needs_attention(
                    db, row_id, self.worker_id, code, detail
                )
            else:
                self._jobs.fail_or_requeue(
                    db,
                    row_id,
                    self.worker_id,
                    code,
                    detail,
                    attempted=attempted,
                )
            return True

        if not self._jobs.set_stage(db, row_id, self.worker_id, "finalizing"):
            return True
        self._jobs.complete(
            db,
            row_id,
            self.worker_id,
            result,
            final_url=prepared.final_url,
            content_sha256=prepared.content_sha256,
            fetched_bytes=prepared.fetched_bytes,
        )
        return True

    def dry_run_row(self, row_id: str) -> dict:
        row = self._jobs.get_row(self._job_db(), row_id, read_only=True)
        if row is None:
            raise ValueError("source-ingest row was not found")
        prepared = self._prepare(
            row,
            db=self._supabase_client(),
            db_params=self._direct_db_params(),
            dry_run=True,
        )
        return {
            "row_id": row_id,
            "source_id": prepared.source_id,
            "final_url": _redacted_url(prepared.final_url),
            "content_sha256": prepared.content_sha256,
            "fetched_bytes": prepared.fetched_bytes,
            "page_count": prepared.page_count,
            "chunk_count": prepared.chunk_count,
            "duplicate": prepared.duplicate,
        }

    def run(self) -> None:
        idle_since = None
        try:
            while not self._stop.is_set():
                try:
                    did_work = self.tick(only_row_id=self.only_row_id)
                except Exception:
                    logger.error("[%s] worker tick failed", self.worker_id)
                    self._stop.wait(min(5.0, max(0.1, self.poll_interval * 5)))
                    continue
                if did_work:
                    idle_since = None
                    continue
                now = time.time()
                if idle_since is None:
                    idle_since = now
                if self.once:
                    break
                if self.max_idle is not None and now - idle_since >= self.max_idle:
                    break
                self._stop.wait(self.poll_interval)
        finally:
            self.close()


def main() -> None:
    args = _parse_args()

    worker = Worker(
        poll_interval=args.poll_interval,
        once=args.once,
        max_idle=args.max_idle,
        only_row_id=args.row_id,
    )

    def _handle(sig, frame):
        logger.info("signal %s received; stopping", sig)
        worker.stop()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    try:
        if args.dry_run_row:
            print(json.dumps(worker.dry_run_row(args.dry_run_row), sort_keys=True))
        else:
            worker.run()
    finally:
        worker.close()


if __name__ == "__main__":
    main()
