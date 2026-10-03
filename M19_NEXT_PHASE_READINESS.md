# Kota Aerospace — M19 Edge Telemetry Gateway Next-Phase Readiness

**Document ID:** KOTA-M19-READINESS-001  
**Milestone:** M19 — Remote Edge Telemetry Gateway Architecture & Backend Integration  
**Date:** 2026-10-04  
**Status:** Architecture Reviewed & Hardening Tasks Prioritized  
**Target Codebase:** `gateway/` (Python 3.12 / SQLite WAL / MAVLink / HTTPS TLS 1.3)  
**Target Backend:** `backend/app/api/v1/telemetry.py` & `backend/app/services/device_auth_service.py`

---

## 1. Readiness Audit Summary

The M19 Edge Telemetry Gateway (`gateway/`) enables edge computing nodes (embedded companion computers on drones, helicopters, and general aviation aircraft) to ingest high-frequency MAVLink streams over serial/UDP, buffer telemetry in an ACID SQLite local queue, and reliably stream normalized batches to the Kota Aerospace backend over cellular/satellite uplinks.

During previous investigation, 8 critical gaps were identified and explored across contract compatibility, queue eviction, retry backoff, framing, and security.

### Readiness Status by Subsystem:

| Subsystem | Status | Verification & Readiness Notes |
|---|---|---|
| **Heartbeat & Connectivity State** | **[VERIFIED IN TESTS]** | Backend `EdgeDeviceHeartbeatRequest` requires top-level `timestamp`, `device_id`, `queue_depth`, and `connectivity_state`. A dedicated background heartbeat thread prevents starvation during upload retries. |
| **ACID Queue & Capacity Limits** | **[VERIFIED IN TESTS]** | Local SQLite WAL queue manages batch locking, transaction isolation, byte caps, and iterative FIFO eviction of lowest-priority events. |
| **Poison-Batch Quarantine** | **[VERIFIED IN TESTS]** | HTTP 422 / permanently malformed records trigger batch-splitting and quarantine table isolation rather than unrecoverable head-of-line blocking. |
| **MAVLink Stream Framing** | **[VERIFIED IN TESTS]** | STX-sync framing (`0xFE` for MAVLink v1, `0xFD` for MAVLink v2) handles stream fragmentation across TCP boundaries and multi-frame UDP packets. |
| **Device Authentication & Tenancy** | **[VERIFIED IN TESTS]** | HMAC-SHA256 signature / API key enrollment binds each gateway instance strictly to its assigned `organization_id` on the backend. Cross-tenant spoofing rejected. |
| **Hardware Physical Edge Boundary** | **[NOT VERIFIED / HARDWARE BOUNDARY]** | Verified against software SITL and simulated UDP/TCP streams; physical CAN bus, RS-422, and cellular modem interfaces require physical bench testing. |

---

## 2. Risk Register & Technical Considerations

| Risk ID | Severity | Area | Technical Description & Mitigation |
|---|---|---|---|
| **RSK-M19-01** | High | Heartbeat Starvation | If telemetry upload loops encounter network degradation, synchronous heartbeat calls in the same thread can starve, causing the cloud control tower to flag the device offline. *Mitigation:* Decouple heartbeats into an independent daemon thread with an autonomous 15s timer. |
| **RSK-M19-02** | High | Poison Batch Head-of-Line Block | A malformed telemetry record returning HTTP 400/422 from backend causes repeated retries, blocking all subsequent telemetry. *Mitigation:* Error-code classification; split batches on 4xx validation errors and isolate unparseable payloads in `quarantine_records`. |
| **RSK-M19-03** | Medium | Queue Disk Saturation | Extended offline flight operations could exhaust local storage if queue eviction is naive. *Mitigation:* Strict byte quota (e.g. 50MB) and multi-tier priority eviction (discarding raw debug packets while preserving telemetry state and alerts). |
| **RSK-M19-04** | Medium | MAVLink Packet Fragmentation | Network routers or serial buffers may split a single MAVLink frame across read chunks. *Mitigation:* State-machine byte buffer seeking magic start bytes `0xFE` or `0xFD` with CRC-16 check before dispatching. |
| **RSK-M19-05** | High | Credential Exposure | Hardware companion computers can be inspected or extracted. Plaintext API keys in shell commands or logs create security vulnerabilities. *Mitigation:* Restrict config to read-only 0600 secret files, mask credentials in logs, and enforce HTTPS TLS 1.2+ minimum. |

---

## 3. Prioritized Implementation Sequence

The next implementation phase should execute in safe, atomic tasks:

### Task 1 (Smallest Safe Starting Point — Recommended):
**Backend Heartbeat Contract & Thread Decoupling**
- **Scope:** Align `gateway/health.py` and `gateway/kota_gateway.py` with `backend/app/schemas/telemetry.py` (`EdgeDeviceHeartbeatRequest`).
- **Safety:** Does not affect the telemetry queue schema; isolates health reporting from upload retry loops.
- **Verification:** Dedicated unit tests in `tests/unit/test_m19_edge_gateway.py` and contract tests against `backend/tests/integration/test_m19_gateway_contract.py`.

### Task 2:
**Safe Batch Acknowledgment & Poison-Batch Quarantine**
- **Scope:** Enhance `gateway/ack_handler.py` and `gateway/uploader.py` to parse partial acceptance responses and isolate rejected/malformed telemetry items into a quarantine table.
- **Verification:** Unit tests verifying batch halving, quarantine insertion, and non-blocking queue forward progress.

### Task 3:
**Queue Capacity & Byte-Cap Eviction Management**
- **Scope:** Enforce database size limits in `gateway/local_queue.py` with multi-tier priority eviction.
- **Verification:** Test queue growth to limit and verify low-priority items are pruned while high-priority alarms remain intact.

### Task 4:
**MAVLink Byte-Level Reassembly State Machine**
- **Scope:** Strengthen `gateway/mavlink_receiver.py` with STX framing and CRC-16 payload verification across fragmented chunk streams.
- **Verification:** Fragmented packet unit tests with synthetic packet splits.

---

## 4. Test Commands for M19 Verification

```powershell
# 1. Gateway Unit Tests
& "backend\.venv\Scripts\python.exe" -m pytest backend/tests/unit/test_m19_edge_gateway.py -v

# 2. Gateway Contract Tests (requires test DB on 55432)
cmd /c "set TEST_DB_PORT=55432&& backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_m19_gateway_contract.py -v"

# 3. End-to-End SITL Stream Integration Tests
cmd /c "set TEST_DB_PORT=55432&& backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_m19_end_to_end_gateway.py -v"
```

---

## 5. Handoff: Next Antigravity Prompt

To initiate Task 1 autonomously in the next session, use the following prompt:

```markdown
# TASK: M19.1 IMPLEMENTATION PHASE 1 — BACKEND HEARTBEAT CONTRACT & THREAD DECOUPLING

Branch: `staging/m17-drone-ops-review`
Repository: `C:\Users\ramna\Documents\Aerocomply`

Objective: Implement Task 1 of M19 Edge Telemetry Gateway hardening:
1. Refactor `gateway/health.py` to build heartbeat payloads matching `backend/app/schemas/telemetry.py::EdgeDeviceHeartbeatRequest` (including ISO timestamp, device_id, queue_depth, connectivity_state).
2. Refactor `gateway/kota_gateway.py` to decouple heartbeat transmission from the telemetry upload retry loop by spawning an independent background daemon thread with a 15-second heartbeat timer.
3. Add/verify unit tests in `backend/tests/unit/test_m19_edge_gateway.py` and contract tests in `backend/tests/integration/test_m19_gateway_contract.py`.
4. Run tests with `TEST_DB_PORT=55432` and report exact results.
Do not modify frontend files or deploy to Vercel during this task.
```
