# Kota Aerospace — M19.2 Edge Gateway Packaging & Provisioning Report

**Document ID:** KOTA-REP-M19-2-PKG-001  
**Milestone:** M19.2 — Remote Edge Telemetry Gateway Packaging, CLI & Secure Provisioning  
**Date:** 2026-10-04  
**Status:** **COMPLETED & VALIDATED (100% PASS RATE)**  
**Branch:** `feature/m19-edge-telemetry-gateway` (branched from `staging/m17-drone-ops-review` at `8e446f0`)  
**Target Environment:** Python >=3.10 / Linux Companion Computers (systemd) / ArduPilot & PX4 Ingress  

---

## 1. Executive Summary

Milestone M19.2 operationalizes the Kota Aerospace Remote Edge Telemetry Gateway (`kota-gateway`) from a standalone prototype into an installable, production-ready Python package with hardened Linux systemd service management and an authorized machine credential provisioning workflow.

All objectives have been implemented and verified:
1. **Packaging & CLI:** Created [gateway/pyproject.toml](file:///c:/Users/ramna/Documents/Aerocomply/gateway/pyproject.toml) exposing the `kota-gateway` console entrypoint. Supports both standard (`pip install ./gateway`) and editable development (`pip install -e ./gateway`) modes.
2. **Configuration Architecture:** Added `--config` JSON loading via `GatewayConfig.from_json()`, `--validate-only` preflight checks, `--version`, and deterministic exit codes (`0`: success/valid, `1`: config error, `2`: fatal runtime failure).
3. **Hardened Systemd Service:** Created [gateway/systemd/kota-gateway.service](file:///c:/Users/ramna/Documents/Aerocomply/gateway/systemd/kota-gateway.service) with network-online ordering, automatic failure recovery, process sandboxing (`ProtectSystem=strict`, `NoNewPrivileges=true`, `PrivateTmp=true`), and pre-start validation (`ExecStartPre`).
4. **Authorized Device Provisioning CLI:** Implemented [backend/scripts/provision_edge_device.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/scripts/provision_edge_device.py) consuming the existing backend endpoint (`POST /api/v1/edge/devices/provision`) requiring operator authorization (`ORG_MANAGE`). Writes atomic `0600` JSON configs, masks tokens in logs (`kdev.<uuid>.***`), and prevents accidental overwrite without `--force`.
5. **Comprehensive Automated Verification:** Added 13 new unit tests. All 61 M19 tests (48 unit + 4 contract + 9 integration) passed with a 100% pass rate.

---

## 2. Changes Made & Architecture Alignment

### A. Python Packaging (`gateway/pyproject.toml` & `gateway/README.md`)
- Defines package metadata (`name = "kota-gateway"`, `version = "1.0.0"`).
- Maps package discovery to `./gateway` directory.
- Declares console script: `kota-gateway = "gateway.kota_gateway:main"`.
- Minimal runtime dependencies: relies only on standard library and `urllib3>=1.26.0`.

### B. Gateway Configuration Loading (`gateway/config.py` & `gateway/kota_gateway.py`)
- Added `GatewayConfig.from_json(json_path, env=None)` and `update_from_dict()` for unified JSON configuration parsing.
- Added `--config` / `-c` CLI argument.
- Added `--validate-only` argument enabling automated pre-flight configuration testing prior to launching socket listeners.
- Added `--version` flag (`kota-gateway 1.0.0`).
- Deterministic exit codes:
  - `0`: Success (clean exit or `--validate-only` pass).
  - `1`: Configuration error (missing required device key, insecure HTTP rejected, invalid port).
  - `2`: Fatal daemon runtime exception.

### C. Systemd Unit Hardening (`gateway/systemd/kota-gateway.service`)
- Lifecycle: `Restart=on-failure`, `RestartSec=5s`, `TimeoutStopSec=15s`, `KillMode=mixed`, `KillSignal=SIGTERM`.
- Dependencies: `After=network-online.target`, `Wants=network-online.target`.
- Pre-start verification: `ExecStartPre=/usr/local/bin/kota-gateway --config /etc/kota/gateway.json --validate-only`.
- Isolation: `ProtectSystem=strict`, `ProtectHome=read-only`, `PrivateTmp=true`, `ProtectKernelTunables=true`, `ProtectKernelModules=true`, `ProtectControlGroups=true`, `RestrictRealtime=true`, `MemoryDenyWriteExecute=true`, `LockPersonality=true`.
- Filesystem bounds: `ReadOnlyPaths=/etc/kota`, `ReadWritePaths=/var/lib/kota /var/log/kota`.

### D. Edge Device Provisioning Tooling (`backend/scripts/provision_edge_device.py`)
- Consumes backend `POST /api/v1/edge/devices/provision` requiring operator JWT bearer token.
- Alternatively supports direct database session (`DATABASE_URL` + `--org-id`) for internal operational bootstrapping.
- Writes atomically via temporary file and atomic replace (`os.replace`).
- Enforces strict `0600` permissions (owner read/write only) on POSIX filesystems.
- Overwrite protection: aborts if destination file exists unless `--force` / `-f` is provided.
- Secret redaction: machine credentials (`kdev.<uuid>.<secret>`) are masked in logs and console output as `kdev.<uuid>.***`.
- Optional connectivity verification (`--verify`): executes an authenticated test heartbeat handshake before finalizing.

---

## 3. Test Verification Matrix

All tests were executed in the `feature/m19-edge-telemetry-gateway` branch:

| Test Suite | Command | Tests Run | Result | Duration |
|---|---|---|---|---|
| **Gateway Core Unit Tests** | `pytest tests/unit/test_m19_edge_gateway.py` | 35 | **35 PASSED** | 0.62s |
| **Gateway Packaging & CLI** | `pytest tests/unit/test_m19_gateway_cli.py` | 7 | **7 PASSED** | 0.12s |
| **Edge Device Provisioning** | `pytest tests/unit/test_m19_provisioning.py` | 6 | **6 PASSED** | 0.15s |
| **Gateway Contract Tests** | `pytest tests/integration/test_m19_gateway_contract.py` | 4 | **4 PASSED** | 1.78s |
| **End-to-End Gateway Tests** | `pytest tests/integration/test_m19_end_to_end_gateway.py` | 9 | **9 PASSED** | 94.09s |
| **Ruff Code Style / Linting** | `ruff check backend/scripts/ backend/tests/unit/test_m19*` | 3 files | **0 ERRORS** | 0.10s |
| **Total** | | **61** | **61 PASSED (100%)** | |

---

## 4. Hardware Validation Boundary

- **Software SITL Status:** **[VERIFIED IN CURRENT CODE & TESTED]** — Verified against software MAVLink streams, fragmented TCP sockets, multi-frame UDP packets, mock backends, and live PostgreSQL databases.
- **Physical Hardware Status:** **[NOT VERIFIED / HARDWARE BOUNDARY]** — Companion computer hardware (Raspberry Pi CM4, NVIDIA Jetson Orin Nano) with physical serial links (RS-422, Pixhawk TELEM1/TELEM2) and cellular modems require physical bench testing scheduled for Milestone M20.
