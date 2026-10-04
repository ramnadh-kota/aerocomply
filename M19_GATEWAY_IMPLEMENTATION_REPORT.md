# KOTA AEROSPACE — M19: REMOTE EDGE TELEMETRY GATEWAY IMPLEMENTATION REPORT

**Document ID:** KOTA-REP-M19-GW-001  
**Milestone:** M19 — Remote Edge Telemetry Gateway Implementation & Backend Contract Reliability  
**Date:** 2026-10-03  
**Status:** Completed & Validated  
**Branch:** `staging/m17-drone-ops-review`  

---

## 1. Executive Summary

This report documents the architectural implementation and hardening of the **Kota Remote Edge Telemetry Gateway Daemon** (`kota_gateway`). The edge gateway acts as an autonomous store-and-forward companion proxy deployed on companion computers (Raspberry Pi, NVIDIA Jetson, or ground control PCs) to ingest MAVLink telemetry from flight controllers (ArduPilot/PX4) and reliably stream it to the Kota Cloud API over HTTPS.

Following the M19 read-only technical review, critical reliability, acknowledgment, heartbeat, and security gaps were resolved in M19.1. The gateway is fully aligned with the backend FastAPI ingestion pipeline, guarantees frame boundary safety, protects in-flight telemetry during queue capacity enforcement, isolates corrupted frames via quarantine, and maintains continuous diagnostic heartbeats independent of upload retry backoffs.

---

## 2. Gateway Architecture & Subsystems

```
+-----------------------------------------------------------------------------------+
|                        KOTA REMOTE EDGE TELEMETRY GATEWAY                         |
|                                                                                   |
|  [ MAVLink Ingress ]                                                              |
|   - UDP:0.0.0.0:14550  ---(Frame-Aware Parser)--->  [ Persistent Queue ]          |
|   - TCP:127.0.0.1:5760                               - SQLite WAL Backend         |
|   - Serial (Gated)                                   - Entry & Byte Enforcement   |
|                                                      - In-Flight Protection       |
|                                                      - Poison Batch Quarantine    |
|                                                              |                    |
|                                                              v                    |
|  [ Dedicated Heartbeat Thread ]                   [ Dynamic Batch Uploader ]      |
|   - Independent 15s Timer                          - HTTPS / TLS 1.2+ Enforced    |
|   - Canonical Health Payload                       - Single/Multi-Item Mode       |
|   - Non-blocking execution                         - TelemetryAckHandler          |
|                                                              |                    |
+--------------------------------------------------------------|--------------------+
                                                               | (mTLS/HTTPS)
                                                               v
                                             [ Kota Cloud Backend (FastAPI) ]
                                              POST /api/v1/device/heartbeat
                                              POST /api/v1/device/telemetry/mavlink
                                                               |
                                                               v
                                                  [ PostgreSQL Persistence ]
```

### Key Components

1. **`gateway/config.py`**:
   - Manages validated configuration loaded from environment variables, CLI parameters, and secure credential files.
   - Enforces HTTPS by default; rejects unencrypted HTTP unless explicit development flag `allow_insecure_http` is set.
   - Enforces minimum TLS version (TLS 1.2+).
   - Redacts credentials in string representations.

2. **`gateway/health.py`**:
   - Assembles canonical heartbeat payloads matching `EdgeDeviceHeartbeatRequest`.
   - Provides top-level `timestamp` (ISO-8601 UTC), `device_id`, flat `queue_depth`, `connectivity_state`, and detailed observability metrics.

3. **`gateway/local_queue.py`**:
   - High-throughput SQLite store-and-forward queue with WAL mode and normal synchronous operations.
   - Strict capacity management: loops repeatedly until entry count and byte capacity are within limits.
   - In-flight protection: never evicts `IN_FLIGHT` items; evicts only oldest `PENDING` or `QUARANTINED` items.
   - Reject oversized individual records exceeding total capacity.
   - Crash recovery: resets all `IN_FLIGHT` rows back to `PENDING` on daemon startup.
   - Explicit quarantine storage and reason tracking for forensic auditing.

4. **`gateway/mavlink_receiver.py`**:
   - Frame-boundary safe parser (`extract_mavlink_frames`).
   - Reassembles fragmented frames across partial TCP reads.
   - Extracts multiple MAVLink frames bundled within a single UDP datagram.
   - Discards garbage bytes prior to MAVLink STX sync byte (`0xFE` or `0xFD`).
   - Gated serial transport requiring native hardware validation.

5. **`gateway/ack_handler.py`**:
   - Evaluates HTTP response codes and backend ingestion reports.
   - Directs queue actions: `ACKNOWLEDGE`, `SPLIT`, `QUARANTINE`, `PAUSE`, `RETRY`.
   - Protects logs against secret leakage via regex token masking (`mask_secret`).

6. **`gateway/uploader.py`**:
   - Cloud HTTP client utilizing hardened `ssl.SSLContext` (TLS 1.2/1.3).
   - Handles network errors and HTTP error codes with masked diagnostic reporting.

7. **`gateway/kota_gateway.py`**:
   - Orchestrates ingestion, persistence, transmission, and heartbeats.
   - Spawns independent heartbeat daemon thread to prevent backoff starvation.
   - Dynamically toggles single-item and multi-item transmission for poison batch isolation.

---

## 3. Subsystem Verification Matrix

| Subsystem | Unit Tests | Contract Tests | Integration Tests | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Heartbeat Contract** | `TestGatewayHealth` | `test_gateway_health_payload_matches_schema_and_backend_contract` | `test_heartbeat_and_connectivity` | **VERIFIED** |
| **Safe Acknowledgment** | `TestTelemetryAckHandler` | N/A | `test_duplicate_retry_handling`, `test_partial_acknowledgment_batch_splitting` | **VERIFIED** |
| **Poison-Batch Quarantine** | `TestPersistentQueue::test_quarantine_items_isolated_from_batching` | N/A | `test_invalid_corrupted_frame_quarantine` | **VERIFIED** |
| **Queue Capacity Limits** | `TestPersistentQueue::test_entry_capacity_enforcement`, `test_byte_capacity_enforcement` | N/A | `test_network_outage_buffering_and_recovery` | **VERIFIED** |
| **Frame Boundary Safety** | `TestMAVLinkFraming::test_split_tcp_stream_reassembly`, `test_udp_multi_frame_datagram` | N/A | End-to-end multi-frame transmission | **VERIFIED** |
| **Transport Security** | `TestTransportAndCredentialSecurity` | N/A | Full suite over secure endpoints | **VERIFIED** |

---

## 4. Operational Recommendations

1. **Edge Deployment**:
   - Run gateway as a systemd service (`kota-gateway.service`) with `Restart=always` and `RestartSec=5`.
   - Store credentials in `/etc/aerocomply/device.token` readable only by `root` / `kota` (`chmod 600`).
2. **Network Bandwidth**:
   - In low-bandwidth cellular environments, set `KOTA_BATCH_SIZE_BYTES=32768` and `KOTA_BATCH_TIMEOUT_SECONDS=1.0` to maximize packet efficiency.
3. **Queue Sizing**:
   - A 100 MB queue accommodates ~20-30 hours of continuous 10 Hz MAVLink flight telemetry during cellular blackouts.
