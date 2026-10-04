"""Persistent, crash-resilient store-and-forward queue backed by SQLite.

Provides bounded entry and byte capacity management, protects in-flight records from
eviction, supports quarantined records for poison isolation, and delivers detailed queue
telemetry metrics without data loss under nominal operations.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("kota_gateway.queue")


@dataclass
class QueuedItem:
    id: int
    data: bytes
    created_at: float
    attempts: int
    status: str
    error_reason: str | None = None


class PersistentQueue:
    """Thread-safe persistent FIFO queue storing raw MAVLink telemetry bytes."""

    def __init__(
        self,
        db_path: str = "./gateway_queue.db",
        max_entries: int = 50000,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.db_path = db_path
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

        # In-memory metric counters for dropped and evicted records
        self._dropped_count = 0
        self._evicted_count = 0

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        parent = Path(self.db_path).parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS telemetry_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data BLOB NOT NULL,
                        data_len INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'PENDING',
                        error_reason TEXT
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_status_id ON telemetry_queue(status, id);"
                )
                # Crash recovery: Reset any records left in 'IN_FLIGHT' status back to 'PENDING'
                cursor = conn.execute(
                    "UPDATE telemetry_queue SET status = 'PENDING' WHERE status = 'IN_FLIGHT';"
                )
                recovered = cursor.rowcount
                if recovered > 0:
                    logger.info(f"Crash recovery: restored {recovered} in-flight record(s) back to PENDING status.")
                conn.commit()
            finally:
                conn.close()

    def enqueue(self, raw_bytes: bytes) -> bool:
        """Enqueue raw telemetry chunk.

        Enforces entry count and byte capacity repeatedly until limits are satisfied.
        Protects records currently marked 'IN_FLIGHT'.
        Returns False if the record cannot fit and capacity cannot be recovered.
        """
        if not raw_bytes:
            return False

        chunk_len = len(raw_bytes)

        # 1. Reject individual records larger than the entire queue's byte capacity
        if chunk_len > self.max_bytes:
            self._dropped_count += 1
            logger.warning(
                f"DROPPED incoming telemetry record: record size ({chunk_len} bytes) "
                f"exceeds total queue capacity limit ({self.max_bytes} bytes)."
            )
            return False

        now = time.time()

        with self._lock:
            conn = self._get_connection()
            try:
                # 2. Capacity Check & Repeated Eviction
                while True:
                    stat_row = conn.execute(
                        """
                        SELECT
                            count(*),
                            coalesce(sum(data_len), 0)
                        FROM telemetry_queue;
                        """
                    ).fetchone()
                    total_count = stat_row[0] if stat_row else 0
                    total_bytes = stat_row[1] if stat_row else 0

                    exceeds_count = (total_count + 1) > self.max_entries
                    exceeds_bytes = (total_bytes + chunk_len) > self.max_bytes

                    if not exceeds_count and not exceeds_bytes:
                        # Capacity satisfied
                        break

                    # Must evict oldest records.
                    # CRITICAL: We NEVER evict 'IN_FLIGHT' records as they are currently being processed!
                    # We evict oldest 'PENDING' or 'QUARANTINED' records.
                    evict_candidates = conn.execute(
                        """
                        SELECT id, data_len FROM telemetry_queue
                        WHERE status IN ('PENDING', 'QUARANTINED')
                        ORDER BY id ASC
                        LIMIT 50;
                        """
                    ).fetchall()

                    if not evict_candidates:
                        # Cannot recover capacity because all remaining records are IN_FLIGHT!
                        self._dropped_count += 1
                        logger.warning(
                            f"DROPPED incoming telemetry record ({chunk_len} bytes): "
                            f"Queue capacity limits reached (count={total_count}/{self.max_entries}, "
                            f"bytes={total_bytes}/{self.max_bytes}) and all records are currently IN_FLIGHT."
                        )
                        return False

                    # Evict up to the candidates fetched
                    evict_ids = [c[0] for c in evict_candidates]
                    evicted_bytes = sum(c[1] for c in evict_candidates)
                    placeholders = ",".join("?" for _ in evict_ids)
                    conn.execute(
                        f"DELETE FROM telemetry_queue WHERE id IN ({placeholders});",
                        evict_ids,
                    )
                    self._evicted_count += len(evict_ids)
                    logger.warning(
                        f"EVICTED {len(evict_ids)} oldest pending record(s) ({evicted_bytes} bytes) "
                        f"to enforce configured capacity limits."
                    )

                # 3. Insert new record
                conn.execute(
                    """
                    INSERT INTO telemetry_queue (data, data_len, created_at, status)
                    VALUES (?, ?, ?, 'PENDING');
                    """,
                    (raw_bytes, chunk_len, now),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def dequeue_batch(self, max_bytes: int = 65536, max_count: int = 100) -> tuple[list[int], bytes]:
        """Fetch a batch of pending items up to `max_bytes`, marking them as 'IN_FLIGHT'."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT id, data, data_len, attempts FROM telemetry_queue
                    WHERE status = 'PENDING'
                    ORDER BY id ASC
                    LIMIT ?;
                    """,
                    (max_count,),
                )
                rows = cursor.fetchall()
                if not rows:
                    return [], b""

                item_ids: list[int] = []
                chunks: list[bytes] = []
                accumulated_bytes = 0

                for r_id, r_data, r_len, _ in rows:
                    # If this is not the first item and adding it would exceed max_bytes, stop accumulating
                    if accumulated_bytes > 0 and (accumulated_bytes + r_len) > max_bytes:
                        break
                    item_ids.append(r_id)
                    chunks.append(r_data)
                    accumulated_bytes += r_len

                if item_ids:
                    placeholders = ",".join("?" for _ in item_ids)
                    conn.execute(
                        f"""
                        UPDATE telemetry_queue
                        SET status = 'IN_FLIGHT', attempts = attempts + 1
                        WHERE id IN ({placeholders});
                        """,
                        item_ids,
                    )
                    conn.commit()

                return item_ids, b"".join(chunks)
            finally:
                conn.close()

    def acknowledge_batch(self, item_ids: list[int]) -> None:
        """Permanently delete successfully transmitted items from the persistent queue."""
        if not item_ids:
            return
        with self._lock:
            conn = self._get_connection()
            try:
                placeholders = ",".join("?" for _ in item_ids)
                conn.execute(
                    f"DELETE FROM telemetry_queue WHERE id IN ({placeholders});",
                    item_ids,
                )
                conn.commit()
            finally:
                conn.close()

    def retry_batch(self, item_ids: list[int]) -> None:
        """Mark items back as 'PENDING' so they can be re-transmitted."""
        if not item_ids:
            return
        with self._lock:
            conn = self._get_connection()
            try:
                placeholders = ",".join("?" for _ in item_ids)
                conn.execute(
                    f"UPDATE telemetry_queue SET status = 'PENDING' WHERE id IN ({placeholders});",
                    item_ids,
                )
                conn.commit()
            finally:
                conn.close()

    def quarantine_items(self, item_ids: list[int], reason: str = "") -> None:
        """Quarantine permanently rejected or poisoned items so they do not block the queue."""
        if not item_ids:
            return
        with self._lock:
            conn = self._get_connection()
            try:
                placeholders = ",".join("?" for _ in item_ids)
                conn.execute(
                    f"""
                    UPDATE telemetry_queue
                    SET status = 'QUARANTINED', error_reason = ?
                    WHERE id IN ({placeholders});
                    """,
                    [reason] + item_ids,
                )
                conn.commit()
                logger.warning(
                    f"QUARANTINED {len(item_ids)} item(s) (IDs: {item_ids}). Reason: {reason}"
                )
            finally:
                conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Return comprehensive queue metrics including pending, in-flight, quarantined, and dropped items."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT
                        count(*),
                        coalesce(sum(data_len), 0),
                        coalesce(sum(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END), 0),
                        coalesce(sum(CASE WHEN status = 'PENDING' THEN data_len ELSE 0 END), 0),
                        coalesce(sum(CASE WHEN status = 'IN_FLIGHT' THEN 1 ELSE 0 END), 0),
                        coalesce(sum(CASE WHEN status = 'IN_FLIGHT' THEN data_len ELSE 0 END), 0),
                        coalesce(sum(CASE WHEN status = 'QUARANTINED' THEN 1 ELSE 0 END), 0),
                        coalesce(sum(CASE WHEN status = 'QUARANTINED' THEN data_len ELSE 0 END), 0)
                    FROM telemetry_queue;
                    """
                )
                row = cursor.fetchone()
                return {
                    "total_items": row[0] if row else 0,
                    "total_bytes": row[1] if row else 0,
                    "pending_items": row[2] if row else 0,
                    "pending_bytes": row[3] if row else 0,
                    "in_flight_items": row[4] if row else 0,
                    "in_flight_bytes": row[5] if row else 0,
                    "quarantined_items": row[6] if row else 0,
                    "quarantined_bytes": row[7] if row else 0,
                    "dropped_items": self._dropped_count,
                    "evicted_items": self._evicted_count,
                }
            finally:
                conn.close()
