# Kota Aerospace — M19 Next Implementation Task Specification

**Document ID:** KOTA-TSK-M19-002  
**Date:** 2026-10-04  
**Target Milestone:** M19 — Remote Edge Telemetry Gateway Operational Packaging & Service Hardening  
**Target Architecture:** Python 3.12 / Linux Companion Computer (systemd) / ArduPilot & PX4 Ingress  
**Status:** **READY FOR IMPLEMENTATION**

---

## 1. Codebase State & Capability Audit Summary

Prior to selecting this task, an exhaustive reconciliation was performed against the current codebase:

| Subsystem | Audit Status | Evidence in Current Checkout |
|---|---|---|
| **Heartbeat Schema & Thread Decoupling** | **[VERIFIED IN CURRENT CODE & TESTED]** | `gateway/health.py` and `gateway/kota_gateway.py:97-102` implement canonical schema and independent daemon thread. Verified via 4 contract tests. |
| **Response-Aware Acknowledgment** | **[VERIFIED IN CURRENT CODE & TESTED]** | `gateway/ack_handler.py` implements `TelemetryAckHandler` with accepted/duplicate/rejected parsing. Verified via 14 unit tests. |
| **Poison-Batch Quarantine** | **[VERIFIED IN CURRENT CODE & TESTED]** | `gateway/local_queue.py:265` isolates permanently rejected records into `QUARANTINED` status. Verified via integration tests. |
| **Queue Eviction & In-Flight Protection** | **[VERIFIED IN CURRENT CODE & TESTED]** | `gateway/local_queue.py:130` enforces entry and byte quotas iteratively, shielding `IN_FLIGHT` rows. Verified via 7 queue tests. |
| **MAVLink Frame Extraction** | **[VERIFIED IN CURRENT CODE & TESTED]** | `gateway/mavlink_receiver.py:24` parses STX `0xFE`/`0xFD` frames with CRC checks. Verified via 4 framing tests. |
| **Physical Hardware Bench Testing** | **[BLOCKED BY HARDWARE OR ENVIRONMENT]** | Physical companion computers (Raspberry Pi CM4 / Jetson Orin Nano) with physical RF/cellular transceivers are scheduled for M20 field operations. |

---

## 2. Selection of the True Next Implementation Task

### Why Previous Proposal Was Rejected:
The previous report proposed re-implementing the heartbeat contract and thread decoupling. Doing so would duplicate code that already exists and passes tests in `gateway/health.py` and `gateway/kota_gateway.py`.

### The True Operational Gap:
While the gateway's core Python modules are functional and tested, the gateway is currently an unpackaged collection of standalone scripts in `gateway/`:
1. It lacks a standalone `pyproject.toml` packaging specification and console entrypoint (`kota-gateway = "gateway.kota_gateway:main"`).
2. It lacks a production-ready Linux companion computer `systemd` service unit (`kota-gateway.service`) with watchdog monitoring, process isolation, and restart backoff.
3. It lacks a secure edge device enrollment and configuration generator (`backend/scripts/provision_edge_device.py`) to bridge the backend `DeviceAuthService` with the companion computer's `/etc/kota/gateway.json` config.
4. All M19 gateway files are currently untracked in the git working tree.

---

## 3. Specification: M19 Operational Packaging & Edge Provisioning

### Subtask A: Git Isolation & Feature Branch Creation
- Create and switch to feature branch `feature/m19-edge-telemetry-gateway`.
- Stage and commit existing tested gateway files (`gateway/`, test files, and reports) so work is tracked and protected.

### Subtask B: Gateway Package Definition (`gateway/pyproject.toml`)
- Define `[project]` metadata for `kota-gateway` (version `1.0.0`, dependencies: `requests`, `urllib3`).
- Define `[project.scripts]` entrypoint: `kota-gateway = "gateway.kota_gateway:main"`.
- Support editable install (`pip install -e gateway/`).

### Subtask C: Edge Companion Computer Systemd Unit (`gateway/systemd/kota-gateway.service`)
- `Description=Kota Aerospace Edge Telemetry Gateway Daemon`
- `After=network-online.target`
- `Restart=on-failure` with `RestartSec=5s`
- `EnvironmentFile=/etc/kota/gateway.env` or `--config /etc/kota/gateway.json`
- Hardened sandbox directives (`ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`).

### Subtask D: Edge Device Provisioning CLI (`backend/scripts/provision_edge_device.py`)
- CLI utility using `DeviceAuthService` to:
  1. Enroll or look up an edge device by serial number / hardware UUID.
  2. Generate or rotate an HMAC device key.
  3. Output a secure `0600` companion computer configuration file (`gateway.json`).
  4. Perform an initial preflight heartbeat handshake against the target backend URL.

### Subtask E: Automated Test Verification
- Add unit tests verifying `kota-gateway` CLI entrypoint execution and argument parsing.
- Add test verifying `provision_edge_device.py` output structure and backend enrollment handshake.

---

## 4. Antigravity Implementation Prompt

The prompt below is ready to be executed in the next Antigravity session:

```markdown
# TASK: M19 EDGE TELEMETRY GATEWAY — PACKAGING, CLI ENTRYPOINT & EDGE PROVISIONING

Branch: `staging/m17-drone-ops-review`
Target Feature Branch: `feature/m19-edge-telemetry-gateway`
Repository: `C:\Users\ramna\Documents\Aerocomply`

Context:
The M19 edge gateway Python modules (`gateway/`) have passed 48 automated tests (35 unit + 4 contract + 9 integration). The core reliability, heartbeat contract, queue eviction, poison-batch quarantine, and MAVLink framing logic are complete.

Your task is to operationalize and package the gateway for deployment onto companion computers:

1. Branch & Commit:
   - Create feature branch `feature/m19-edge-telemetry-gateway`.
   - Stage and commit the existing verified M19 implementation files (`gateway/`, tests, and reports).

2. Gateway Package & CLI:
   - Create `gateway/pyproject.toml` with `kota-gateway` console script entrypoint pointing to `gateway.kota_gateway:main`.
   - Ensure the package installs cleanly in editable mode via pip.

3. Linux Systemd Unit:
   - Create `gateway/systemd/kota-gateway.service` with network-online dependency, restart backoff, and hardened sandboxing.

4. Edge Device Provisioning CLI:
   - Create `backend/scripts/provision_edge_device.py` that utilizes `backend/app/services/device_auth_service.py` to enroll an edge device, generate HMAC credentials, and write an encrypted or 0600 JSON config file for `/etc/kota/gateway.json`.

5. Automated Tests:
   - Add unit tests for CLI entrypoint and provisioning script.
   - Run the full M19 test suite (`test_m19_edge_gateway.py`, `test_m19_gateway_contract.py`, `test_m19_end_to_end_gateway.py`).
   - Confirm all tests pass.

Do not modify frontend files or deploy to Vercel during this task.
```
