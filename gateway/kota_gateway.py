"""Kota Aerospace - Remote Edge Telemetry Gateway Daemon.

Main orchestrator managing the MAVLink receiver, local SQLite store-and-forward queue,
outbound HTTPS uploader, response-aware acknowledgment, poison-batch quarantine, and periodic
independent health heartbeats.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Any

from gateway.ack_handler import AckAction, TelemetryAckHandler, mask_secret
from gateway.config import GatewayConfig
from gateway.health import get_gateway_health_payload
from gateway.local_queue import PersistentQueue
from gateway.mavlink_receiver import MAVLinkReceiver
from gateway.retry_manager import RetryManager
from gateway.uploader import TelemetryUploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kota_gateway")


class KotaGatewayDaemon:
    """Orchestrates all edge gateway subsystems."""

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.queue = PersistentQueue(
            db_path=self.config.queue_db_path,
            max_entries=self.config.max_queue_entries,
            max_bytes=self.config.max_queue_bytes,
        )
        self.retry_mgr = RetryManager(
            base_backoff_seconds=self.config.base_backoff_seconds,
            max_backoff_seconds=self.config.max_backoff_seconds,
        )
        self.ack_handler = TelemetryAckHandler(max_retries=5)
        self.uploader = TelemetryUploader(self.config)
        self.receiver = MAVLinkReceiver(self.config, on_chunk_received=self._on_chunk)
        self._running = False
        self._stop_event = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._start_time = time.time()
        self._split_mode = False

        # Heartbeat telemetry state
        self.consecutive_heartbeat_failures: int = 0
        self.last_heartbeat_status: str = "INITIALIZING"
        self.last_heartbeat_at: float = 0.0
        self.last_heartbeat_error: str | None = None

        # Resolve device_id: prefer explicit config.device_id, fallback to UUID from token if not provided
        if self.config.device_id:
            self.device_id = self.config.device_id
        else:
            parts = self.config.device_key.split(".")
            self.device_id = parts[1] if len(parts) >= 2 else "unknown-device"

    def _on_chunk(self, raw_bytes: bytes) -> None:
        """Enqueue incoming MAVLink byte stream into persistent queue."""
        self.queue.enqueue(raw_bytes)

    def start(self) -> None:
        """Start the edge gateway daemon."""
        errors = self.config.validate()
        if errors:
            for err in errors:
                logger.error(f"Configuration error: {err}")
            sys.exit(1)

        masked_key = mask_secret(self.config.device_key)
        logger.info("=" * 60)
        logger.info("   KOTA AEROSPACE - REMOTE EDGE TELEMETRY GATEWAY   ")
        logger.info("=" * 60)
        logger.info(f"Target API Endpoint:  {self.config.api_url}")
        logger.info(f"Device Identifier:    {self.device_id}")
        logger.info(f"Device Token:         {masked_key}")
        logger.info(f"MAVLink Ingress:      {self.config.mavlink_source}")
        logger.info(f"Queue Storage DB:     {self.config.queue_db_path}")

        self._running = True
        self._stop_event.clear()
        self.receiver.start()

        # Start dedicated heartbeat thread independent of upload backoff sleeps
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="KotaHeartbeatThread",
        )
        self._heartbeat_thread.start()

        # Install signal handlers for clean shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._main_loop()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        logger.info(f"Received termination signal ({signum}). Initiating graceful shutdown...")
        self._running = False
        self._stop_event.set()

    def stop(self) -> None:
        """Stop all gateway threads and clean up."""
        self._running = False
        self._stop_event.set()
        self.receiver.stop()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        logger.info("Gateway daemon shut down cleanly.")

    def _heartbeat_loop(self) -> None:
        """Independent heartbeat loop that guarantees timely heartbeats even during long upload backoffs."""
        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.error(f"Unexpected error during heartbeat execution: {e}", exc_info=True)

            # Sleep for heartbeat_interval_seconds, interrupted immediately on shutdown
            if self._stop_event.wait(timeout=self.config.heartbeat_interval_seconds):
                break

    def _main_loop(self) -> None:
        """Primary store-and-forward transmission loop."""
        while self._running:
            # 1. Determine batch count limit: 1 if in split mode to test individually, else 100
            max_count = 1 if self._split_mode else 100

            # 2. Dequeue pending telemetry batch
            item_ids, batch_bytes = self.queue.dequeue_batch(
                max_bytes=self.config.batch_size_bytes, max_count=max_count
            )

            if not item_ids:
                # If queue is empty, restore normal batching mode and idle wait
                self._split_mode = False
                time.sleep(self.config.batch_timeout_seconds)
                continue

            # 3. Transmit to Cloud
            status_code, resp = self.uploader.upload_mavlink_batch(batch_bytes)

            # 4. Safe Response-Aware Evaluation
            evaluation = self.ack_handler.evaluate(
                status_code=status_code,
                response_body=resp,
                batch_size=len(item_ids),
                attempt_count=self.retry_mgr.consecutive_failures + 1,
            )

            # 5. Execute Action
            if evaluation.action == AckAction.ACKNOWLEDGE:
                self.queue.acknowledge_batch(item_ids)
                self.retry_mgr.record_success()
                self._split_mode = False
                logger.debug(
                    f"Acknowledged batch ({len(item_ids)} items, {len(batch_bytes)}B): {evaluation.message}"
                )

            elif evaluation.action == AckAction.SPLIT:
                # Return items to pending; switch to split mode (send individually) to isolate bad records
                self.queue.retry_batch(item_ids)
                self._split_mode = True
                logger.info(
                    f"Batch split triggered ({len(item_ids)} items). Switching to single-item mode: {evaluation.message}"
                )

            elif evaluation.action == AckAction.QUARANTINE:
                reason = evaluation.quarantine_reason or evaluation.message
                self.queue.quarantine_items(item_ids, reason=reason)
                # Quarantining a bad record resolves the blockage, so reset backoff
                self.retry_mgr.record_success()
                self._split_mode = False
                logger.warning(
                    f"Poison batch isolated ({len(item_ids)} items quarantined): {reason}"
                )

            elif evaluation.action == AckAction.PAUSE:
                # Auth/authorization/binding configuration issue: do not thrash, wait with max backoff
                self.queue.retry_batch(item_ids)
                pause_time = min(15.0, self.config.max_backoff_seconds)
                logger.error(
                    f"Pipeline paused ({pause_time}s) due to fatal auth/configuration error: {evaluation.message}"
                )
                time.sleep(pause_time)

            elif evaluation.action == AckAction.RETRY:
                self.queue.retry_batch(item_ids)
                sleep_sec = self.retry_mgr.record_failure()
                logger.warning(
                    f"Batch upload failed (HTTP {status_code}). Retrying in {sleep_sec:.2f}s "
                    f"(consecutive failures: {self.retry_mgr.consecutive_failures}): {evaluation.message}"
                )
                time.sleep(sleep_sec)

        self.stop()

    def _send_heartbeat(self) -> bool:
        """Transmit diagnostic heartbeat payload matching EdgeDeviceHeartbeatRequest."""
        stats = self.queue.get_stats()
        payload = get_gateway_health_payload(
            self.device_id,
            stats,
            start_time=self._start_time,
        )
        status_code, resp = self.uploader.send_heartbeat(payload)
        self.last_heartbeat_at = time.time()

        if status_code == 200:
            self.consecutive_heartbeat_failures = 0
            self.last_heartbeat_status = "ONLINE"
            self.last_heartbeat_error = None
            logger.info(
                f"Heartbeat sent (Device: {self.device_id}, Queue depth: {stats.get('pending_items', 0)}, "
                f"Bytes: {stats.get('total_bytes', 0)})"
            )
            return True
        else:
            self.consecutive_heartbeat_failures += 1
            self.last_heartbeat_status = "FAILED"
            clean_resp = mask_secret(str(resp))
            self.last_heartbeat_error = clean_resp

            # Explicit failure categorization
            if status_code == 401:
                logger.error(f"Heartbeat AUTHENTICATION failure (HTTP 401): invalid/expired device key. Response: {clean_resp}")
            elif status_code == 403:
                logger.error(
                    f"Heartbeat PERMISSION failure (HTTP 403): device '{self.device_id}' mismatch or revoked. Response: {clean_resp}"
                )
            elif status_code == 404:
                logger.error(
                    f"Heartbeat NOT FOUND failure (HTTP 404): device '{self.device_id}' not found in organization. Response: {clean_resp}"
                )
            elif status_code == 422:
                logger.error(f"Heartbeat SCHEMA VALIDATION failure (HTTP 422): invalid payload format. Response: {clean_resp}")
            else:
                logger.warning(
                    f"Heartbeat delivery failed (HTTP {status_code}, consecutive: {self.consecutive_heartbeat_failures}): {clean_resp}"
                )
            return False


__version__ = "1.0.0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kota-gateway",
        description="Kota Aerospace Remote Edge Telemetry Gateway",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to JSON configuration file (e.g. /etc/kota/gateway.json)",
    )
    parser.add_argument("--api-url", default=None, help="Kota Cloud API URL (e.g. https://api.aerocomply.com/api/v1)")
    parser.add_argument("--device-id", default=None, help="Device identifier (e.g. companion-123456)")
    parser.add_argument("--device-key", default=None, help="Device token (kdev.<uuid>.<secret>)")
    parser.add_argument("--credential-file", default=None, help="Path to secure credential file containing token")
    parser.add_argument("--mavlink-source", default=None, help="MAVLink ingress source (e.g. udp:127.0.0.1:14550)")
    parser.add_argument("--queue-db", default=None, help="Path to SQLite queue database")
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=False,
        help="Explicitly enable unencrypted HTTP for local development only",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        default=False,
        help="Validate configuration and exit immediately without starting listeners",
    )
    args = parser.parse_args(argv)

    try:
        if args.config:
            config = GatewayConfig.from_json(args.config)
        else:
            config = GatewayConfig.from_env()
    except Exception as exc:
        logger.error(f"Configuration load error: {exc}")
        return 1

    if args.api_url:
        config.api_url = args.api_url
    if args.device_id:
        config.device_id = args.device_id
    if args.device_key:
        config.device_key = args.device_key
    if args.credential_file:
        config.credential_file = args.credential_file
    if args.mavlink_source:
        config.mavlink_source = args.mavlink_source
    if args.queue_db:
        config.queue_db_path = args.queue_db
    if args.allow_insecure_http:
        config.allow_insecure_http = True

    errors = config.validate()
    if errors:
        for err in errors:
            logger.error(f"Configuration error: {err}")
        return 1

    if args.validate_only:
        logger.info("Configuration is valid.")
        return 0

    logging.getLogger().setLevel(getattr(logging, config.log_level, logging.INFO))
    try:
        daemon = KotaGatewayDaemon(config)
        daemon.start()
        return 0
    except KeyboardInterrupt:
        logger.info("Gateway daemon interrupted by user.")
        return 0
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        logger.error(f"Fatal gateway daemon runtime error: {exc}", exc_info=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
