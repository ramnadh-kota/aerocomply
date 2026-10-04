"""Unit tests for M19.1 Kota Remote Edge Gateway components.

Covers:
- Phase 2: Safe telemetry acknowledgment (full, duplicate, partial, rejected, malformed, backend errors)
- Phase 3: Error classification & poison-batch handling (auth, conflict, 413, 422, rate limits, 5xx)
- Phase 4: Queue capacity management (entry cap, byte cap, large records, in-flight protection, restart recovery)
- Phase 5: MAVLink frame boundary safety (split TCP stream, UDP multi-frame, garbage sync)
- Phase 6: Transport and credential security (HTTPS enforcement, credential file, secret masking)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Add repository root to pythonpath
repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from gateway.ack_handler import AckAction, TelemetryAckHandler, mask_secret
from gateway.config import GatewayConfig
from gateway.health import get_gateway_health_payload
from gateway.local_queue import PersistentQueue
from gateway.mavlink_receiver import extract_mavlink_frames
from gateway.retry_manager import RetryManager


# =============================================================================
# PHASE 1 & CONFIG TESTS
# =============================================================================
class TestGatewayConfig:
    def test_default_config_validation_fails_without_key(self):
        cfg = GatewayConfig(device_key="", api_url="https://api.aerocomply.com/api/v1")
        errs = cfg.validate()
        assert len(errs) > 0
        assert any("device_key is required" in e for e in errs)

    def test_valid_config_passes(self):
        cfg = GatewayConfig(
            api_url="https://api.aerocomply.com/api/v1",
            device_key="kdev.11111111-1111-1111-1111-111111111111.secretkey1234567890abcdef",
            mavlink_source="udp:127.0.0.1:14550",
        )
        assert cfg.validate() == []

    def test_from_env_loading(self):
        env = {
            "KOTA_API_URL": "https://staging.aerocomply.com/api/v1/",
            "KOTA_DEVICE_ID": "companion-alpha",
            "KOTA_DEVICE_KEY": "kdev.22222222-2222-2222-2222-222222222222.secret123",
            "KOTA_MAVLINK_SOURCE": "udp:0.0.0.0:14555",
            "KOTA_BATCH_SIZE_BYTES": "32768",
        }
        cfg = GatewayConfig.from_env(env)
        assert cfg.api_url == "https://staging.aerocomply.com/api/v1"
        assert cfg.device_id == "companion-alpha"
        assert cfg.device_key == "kdev.22222222-2222-2222-2222-222222222222.secret123"
        assert cfg.mavlink_source == "udp:0.0.0.0:14555"
        assert cfg.batch_size_bytes == 32768


# =============================================================================
# PHASE 2 & 3: SAFE ACKNOWLEDGMENT & ERROR CLASSIFICATION TESTS
# =============================================================================
class TestTelemetryAckHandler:
    def setup_method(self):
        self.handler = TelemetryAckHandler(max_retries=5)

    def test_full_acceptance(self):
        resp = {"accepted": 10, "duplicates": 0, "rejected": 0, "failed": 0, "errors": []}
        eval_res = self.handler.evaluate(200, resp, batch_size=5)
        assert eval_res.action == AckAction.ACKNOWLEDGE
        assert eval_res.accepted == 10

    def test_duplicate_only_acceptance(self):
        resp = {"accepted": 0, "duplicates": 8, "rejected": 0, "failed": 0, "errors": []}
        eval_res = self.handler.evaluate(200, resp, batch_size=4)
        assert eval_res.action == AckAction.ACKNOWLEDGE
        assert eval_res.duplicates == 8

    def test_partial_acceptance_multi_item_splits(self):
        resp = {"accepted": 3, "duplicates": 0, "rejected": 2, "failed": 0, "errors": ["CRC failure"]}
        eval_res = self.handler.evaluate(200, resp, batch_size=5)
        assert eval_res.action == AckAction.SPLIT

    def test_partial_acceptance_single_item_acknowledges(self):
        resp = {"accepted": 1, "duplicates": 0, "rejected": 1, "failed": 0, "errors": ["1 frame dropped"]}
        eval_res = self.handler.evaluate(200, resp, batch_size=1)
        assert eval_res.action == AckAction.ACKNOWLEDGE

    def test_full_rejection_multi_item_splits(self):
        resp = {"accepted": 0, "duplicates": 0, "rejected": 5, "failed": 0, "errors": ["Invalid sync"]}
        eval_res = self.handler.evaluate(200, resp, batch_size=5)
        assert eval_res.action == AckAction.SPLIT

    def test_full_rejection_single_item_quarantines(self):
        resp = {"accepted": 0, "duplicates": 0, "rejected": 1, "failed": 0, "errors": ["Checksum error"]}
        eval_res = self.handler.evaluate(200, resp, batch_size=1)
        assert eval_res.action == AckAction.QUARANTINE
        assert "Checksum error" in (eval_res.quarantine_reason or "")

    def test_malformed_response_retries(self):
        eval_res = self.handler.evaluate(200, "<html>Bad Gateway</html>", batch_size=2)
        assert eval_res.action == AckAction.RETRY
        assert eval_res.is_transient is True

    def test_http_200_with_backend_errors(self):
        resp = {"accepted": 0, "duplicates": 0, "errors": ["no valid MAVLink frames in payload"], "rejected": 1}
        # Multi item should split to isolate bad frame
        assert self.handler.evaluate(200, resp, batch_size=3).action == AckAction.SPLIT
        # Single item should quarantine
        eval_single = self.handler.evaluate(200, resp, batch_size=1)
        assert eval_single.action == AckAction.QUARANTINE
        assert "no valid MAVLink" in (eval_single.quarantine_reason or "")

    def test_auth_errors_pause_pipeline(self):
        assert self.handler.evaluate(401, "Invalid token", batch_size=2).action == AckAction.PAUSE
        assert self.handler.evaluate(403, "Forbidden device", batch_size=2).action == AckAction.PAUSE

    def test_conflict_unbound_device_pauses(self):
        assert self.handler.evaluate(409, "device_not_bound", batch_size=2).action == AckAction.PAUSE

    def test_payload_too_large_splits_or_quarantines(self):
        assert self.handler.evaluate(413, "Too large", batch_size=5).action == AckAction.SPLIT
        assert self.handler.evaluate(413, "Too large", batch_size=1).action == AckAction.QUARANTINE

    def test_unprocessable_entity_splits_or_quarantines(self):
        assert self.handler.evaluate(422, "Empty payload", batch_size=2).action == AckAction.SPLIT
        assert self.handler.evaluate(422, "Empty payload", batch_size=1).action == AckAction.QUARANTINE

    def test_rate_limiting_and_5xx_transient_retry(self):
        assert self.handler.evaluate(429, "Rate limited", batch_size=1, attempt_count=1).action == AckAction.RETRY
        assert self.handler.evaluate(503, "Unavailable", batch_size=1, attempt_count=2).action == AckAction.RETRY

    def test_max_retries_poison_quarantined(self):
        eval_res = self.handler.evaluate(500, "Internal Server Error", batch_size=1, attempt_count=5)
        assert eval_res.action == AckAction.QUARANTINE
        assert "Exceeded max retries" in eval_res.message


# =============================================================================
# PHASE 4: QUEUE CAPACITY & INTEGRITY TESTS
# =============================================================================
class TestPersistentQueue:
    def test_enqueue_dequeue_acknowledge_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            q = PersistentQueue(db_path=db_path, max_entries=100)

            assert q.enqueue(b"FRAME_1") is True
            assert q.enqueue(b"FRAME_2") is True
            assert q.enqueue(b"FRAME_3") is True

            stats = q.get_stats()
            assert stats["total_items"] == 3
            assert stats["pending_items"] == 3
            assert stats["in_flight_items"] == 0

            item_ids, batch_data = q.dequeue_batch(max_bytes=1024, max_count=2)
            assert len(item_ids) == 2
            assert batch_data == b"FRAME_1FRAME_2"

            stats = q.get_stats()
            assert stats["pending_items"] == 1
            assert stats["in_flight_items"] == 2

            q.acknowledge_batch(item_ids)
            stats = q.get_stats()
            assert stats["total_items"] == 1
            assert stats["pending_items"] == 1
            assert stats["in_flight_items"] == 0

    def test_entry_capacity_enforcement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            max_entries = 10
            q = PersistentQueue(db_path=db_path, max_entries=max_entries, max_bytes=100000)

            # Insert 25 items into queue of capacity 10
            for i in range(25):
                assert q.enqueue(f"DATA_{i:02d}".encode()) is True

            stats = q.get_stats()
            # Must strictly enforce configured limit
            assert stats["total_items"] <= max_entries
            assert stats["evicted_items"] >= 15

    def test_byte_capacity_enforcement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            max_bytes = 500
            q = PersistentQueue(db_path=db_path, max_entries=1000, max_bytes=max_bytes)

            chunk = b"A" * 100
            for _ in range(10):
                q.enqueue(chunk)

            stats = q.get_stats()
            assert stats["total_bytes"] <= max_bytes
            assert stats["evicted_items"] > 0

    def test_large_individual_record_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            q = PersistentQueue(db_path=db_path, max_entries=100, max_bytes=1024)

            # Record larger than max_bytes
            oversized = b"X" * 2048
            assert q.enqueue(oversized) is False

            stats = q.get_stats()
            assert stats["total_items"] == 0
            assert stats["dropped_items"] == 1

    def test_all_records_in_flight_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            q = PersistentQueue(db_path=db_path, max_entries=3, max_bytes=10000)

            q.enqueue(b"ITEM_1")
            q.enqueue(b"ITEM_2")
            q.enqueue(b"ITEM_3")

            # Dequeue all 3 into IN_FLIGHT
            item_ids, _ = q.dequeue_batch(max_count=3)
            assert len(item_ids) == 3

            stats = q.get_stats()
            assert stats["in_flight_items"] == 3
            assert stats["pending_items"] == 0

            # Incoming item cannot fit and cannot evict IN_FLIGHT records
            assert q.enqueue(b"ITEM_4") is False

            stats = q.get_stats()
            assert stats["in_flight_items"] == 3  # IN_FLIGHT protected!
            assert stats["dropped_items"] == 1

    def test_restart_crash_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")

            q1 = PersistentQueue(db_path=db_path)
            q1.enqueue(b"REC_1")
            q1.enqueue(b"REC_2")
            q1.enqueue(b"REC_3")

            # Mark 2 as in flight
            ids, _ = q1.dequeue_batch(max_count=2)
            assert len(ids) == 2

            # Simulate restart by instantiating new PersistentQueue on same db
            q2 = PersistentQueue(db_path=db_path)
            stats = q2.get_stats()
            assert stats["in_flight_items"] == 0
            assert stats["pending_items"] == 3  # All restored to pending

    def test_quarantine_items_isolated_from_batching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_queue.db")
            q = PersistentQueue(db_path=db_path)

            q.enqueue(b"GOOD_1")
            q.enqueue(b"BAD_POISON")
            q.enqueue(b"GOOD_2")

            # Dequeue first 2
            ids, _ = q.dequeue_batch(max_count=2)
            # Quarantine the bad item
            q.quarantine_items([ids[1]], reason="Corrupt payload")
            # Retry good item
            q.retry_batch([ids[0]])

            stats = q.get_stats()
            assert stats["quarantined_items"] == 1
            assert stats["pending_items"] == 2

            # Dequeue batch will only fetch good items, never quarantined item
            next_ids, next_data = q.dequeue_batch(max_count=10)
            assert ids[1] not in next_ids
            assert b"BAD_POISON" not in next_data


# =============================================================================
# PHASE 5: MAVLINK FRAME BOUNDARY SAFETY TESTS
# =============================================================================
class TestMAVLinkFraming:
    def _make_dummy_v1_frame(self, payload: bytes = b"HELLO") -> bytes:
        stx = bytes([0xFE])
        length = bytes([len(payload)])
        seq = bytes([1])
        sysid = bytes([1])
        compid = bytes([1])
        msgid = bytes([0])  # HEARTBEAT
        crc = b"\x12\x34"
        return stx + length + seq + sysid + compid + msgid + payload + crc

    def _make_dummy_v2_frame(self, payload: bytes = b"WORLD") -> bytes:
        stx = bytes([0xFD])
        length = bytes([len(payload)])
        incompat = bytes([0])
        compat = bytes([0])
        seq = bytes([1])
        sysid = bytes([1])
        compid = bytes([1])
        msgid = b"\x00\x00\x00"  # 3 bytes
        crc = b"\xab\xcd"
        return stx + length + incompat + compat + seq + sysid + compid + msgid + payload + crc

    def test_single_complete_frames(self):
        f1 = self._make_dummy_v1_frame()
        frames, rem = extract_mavlink_frames(bytearray(f1))
        assert len(frames) == 1
        assert frames[0] == f1
        assert len(rem) == 0

        f2 = self._make_dummy_v2_frame()
        frames, rem = extract_mavlink_frames(bytearray(f2))
        assert len(frames) == 1
        assert frames[0] == f2
        assert len(rem) == 0

    def test_split_tcp_stream_reassembly(self):
        f1 = self._make_dummy_v1_frame(b"VERY_LONG_PAYLOAD_CHUNK")
        split_point = 8

        # First TCP read: partial frame
        rx_buf = bytearray(f1[:split_point])
        frames1, rx_buf = extract_mavlink_frames(rx_buf)
        assert len(frames1) == 0
        assert len(rx_buf) == split_point

        # Second TCP read: remainder arrives
        rx_buf.extend(f1[split_point:])
        frames2, rx_buf = extract_mavlink_frames(rx_buf)
        assert len(frames2) == 1
        assert frames2[0] == f1
        assert len(rx_buf) == 0

    def test_udp_multi_frame_datagram(self):
        f1 = self._make_dummy_v1_frame(b"F1")
        f2 = self._make_dummy_v2_frame(b"F2")
        f3 = self._make_dummy_v1_frame(b"F3")

        datagram = bytearray(f1 + f2 + f3)
        frames, rem = extract_mavlink_frames(datagram)
        assert len(frames) == 3
        assert frames[0] == f1
        assert frames[1] == f2
        assert frames[2] == f3
        assert len(rem) == 0

    def test_garbage_preceding_frame_discarded(self):
        garbage = b"RANDOM_NOISE_BYTES"
        f = self._make_dummy_v1_frame(b"VALID")
        buf = bytearray(garbage + f)

        frames, rem = extract_mavlink_frames(buf)
        assert len(frames) == 1
        assert frames[0] == f
        assert len(rem) == 0


# =============================================================================
# PHASE 6: TRANSPORT & CREDENTIAL SECURITY TESTS
# =============================================================================
class TestTransportAndCredentialSecurity:
    def test_insecure_http_rejected_by_default(self):
        cfg = GatewayConfig(
            api_url="http://cloud.aerocomply.com/api/v1",
            device_key="kdev.00000000-0000-0000-0000-000000000001.secret123",
            allow_insecure_http=False,
        )
        errors = cfg.validate()
        assert any("Insecure HTTP transport rejected" in e for e in errors)

    def test_insecure_http_allowed_explicitly_for_local_testing(self):
        cfg = GatewayConfig(
            api_url="http://localhost:8001/api/v1",
            device_key="kdev.00000000-0000-0000-0000-000000000001.secret123",
            allow_insecure_http=True,
        )
        assert cfg.validate() == []

    def test_credential_file_loading_json(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write(json.dumps({
                "device_id": "companion-json-node",
                "device_key": "kdev.33333333-3333-3333-3333-333333333333.supersecretkey",
            }))
            temp_path = f.name

        try:
            cfg = GatewayConfig(
                api_url="https://api.aerocomply.com/api/v1",
                credential_file=temp_path,
            )
            errors = cfg.validate()
            assert errors == []
            assert cfg.device_id == "companion-json-node"
            assert cfg.device_key == "kdev.33333333-3333-3333-3333-333333333333.supersecretkey"
        finally:
            os.remove(temp_path)

    def test_credential_file_loading_plain(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("kdev.44444444-4444-4444-4444-444444444444.secretplain\n")
            temp_path = f.name

        try:
            cfg = GatewayConfig(
                api_url="https://api.aerocomply.com/api/v1",
                credential_file=temp_path,
            )
            errors = cfg.validate()
            assert errors == []
            assert cfg.device_key == "kdev.44444444-4444-4444-4444-444444444444.secretplain"
        finally:
            os.remove(temp_path)

    def test_secret_masking(self):
        raw = "Auth failed for kdev.12345678-1234-1234-1234-123456789abc.VERY_SECRET_KEY_123 in payload"
        masked = mask_secret(raw)
        assert "VERY_SECRET_KEY_123" not in masked
        assert "kdev.12345678-1234-1234-1234-123456789abc.***" in masked


# =============================================================================
# RETRY MANAGER TESTS
# =============================================================================
class TestRetryManager:
    def test_exponential_backoff_growth_and_reset(self):
        mgr = RetryManager(base_backoff_seconds=1.0, max_backoff_seconds=10.0, jitter_factor=0.0)
        assert mgr.consecutive_failures == 0

        t1 = mgr.record_failure()
        assert 0.9 <= t1 <= 1.1
        assert mgr.consecutive_failures == 1

        t2 = mgr.record_failure()
        assert 1.9 <= t2 <= 2.1

        t3 = mgr.record_failure()
        assert 3.9 <= t3 <= 4.1

        mgr.record_success()
        assert mgr.consecutive_failures == 0


# =============================================================================
# GATEWAY HEALTH TESTS
# =============================================================================
class TestGatewayHealth:
    def test_health_payload_generation(self):
        stats = {"total_items": 10, "total_bytes": 4096, "pending_items": 8, "in_flight_items": 2}
        payload = get_gateway_health_payload("test-device-uuid", stats, start_time=time.time() - 100)

        assert payload["device_id"] == "test-device-uuid"
        assert payload["connectivity_state"] == "ONLINE"
        assert "timestamp" in payload
        assert payload["queue_depth"] == 8
        assert payload["uptime_seconds"] >= 99
        assert "observability" in payload
        assert payload["observability"]["queue_metrics"]["pending_items"] == 8
