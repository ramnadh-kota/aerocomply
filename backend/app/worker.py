"""Background job worker:  python -m app.worker [--once] [--poll 1.0] [--types acquisition.ingest]

Runs jobs from the durable queue (app/services/job_service.py). Graceful shutdown: SIGINT/SIGTERM stop the loop
after the CURRENT job finishes (the job is never abandoned mid-write). Run several workers for parallelism; jobs are
claimed with SKIP LOCKED so they never collide. A crashed worker's job is recovered by reclaim_stale."""
from __future__ import annotations

import argparse
import os
import signal
import socket
import threading
import time
from collections.abc import Callable

import structlog
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services import job_handlers, job_service  # noqa: F401  (job_handlers registers the handlers)

log = structlog.get_logger("worker")


def run_worker(
    stop: threading.Event,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    poll_interval: float = 1.0,
    job_types: list[str] | None = None,
    once: bool = False,
    worker_id: str | None = None,
) -> int:
    """Returns the number of jobs processed."""
    worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"
    processed, last_reclaim = 0, 0.0
    log.info("worker.started", worker_id=worker_id, job_types=job_types)
    while not stop.is_set():
        with session_factory() as db:
            if time.monotonic() - last_reclaim > 60:
                n = job_service.reclaim_stale(db)
                db.commit()
                last_reclaim = time.monotonic()
                if n:
                    log.warning("worker.reclaimed_stale_jobs", count=n)
            did = job_service.run_one(db, worker_id=worker_id, job_types=job_types)
        if did:
            processed += 1
            continue
        if once:
            break
        stop.wait(poll_interval)
    log.info("worker.stopped", worker_id=worker_id, processed=processed)
    return processed


def main() -> None:
    ap = argparse.ArgumentParser(description="Kota background job worker")
    ap.add_argument("--once", action="store_true", help="drain the queue then exit")
    ap.add_argument("--poll", type=float, default=1.0)
    ap.add_argument("--types", nargs="*", default=None)
    args = ap.parse_args()
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    run_worker(stop, poll_interval=args.poll, job_types=args.types, once=args.once)


if __name__ == "__main__":
    main()
