# Kota Aerospace — MAVLink Architecture (as implemented)

> Replaces the earlier specification (serial listener, TimescaleDB, Redis router) that described components which do
> not exist. Every statement below is backed by code and a test. **EXTERNAL VALIDATION REQUIRED** for anything that
> depends on a physical radio, autopilot or vehicle: see `MAVLINK_HARDWARE_VALIDATION_PLAN.md` and the measurement tool
> `backend/scripts/mavlink_bench_harness.py`.

## 1. Entry paths

| Path | Component | Notes |
|---|---|---|
| HTTP push | `POST /api/v1/data-sources/{id}/ingest` (raw bytes; `?mode=async` queues) | tenant user token; 25 MB cap |
| UDP listener | `python -m app.listeners` → `listeners/udp_mavlink.py` | datagram ≤ 2 048 B; `listen.udp_port`, `bind`, `allowed_cidrs` |
| TCP listener (server mode) | `listeners/tcp_mavlink.py` | `listen.tcp_port`; ≤ 64 peers, 60 s idle timeout |
| Edge gateway daemon | `app/services/edge/gateway_service.py` | companion computer / gateway host that uplinks over HTTPS |
| Serial radio | **not built** | bridge to UDP/TCP with mavlink-router or the gateway host |

Listeners buffer bytes in a bounded sink and enqueue `acquisition.ingest` jobs; a worker (`python -m app.worker`) runs
them through `MAVLinkConnector` and the shared acquisition pipeline. A listener **refuses to start** unless
`allowed_cidrs` is set and/or signing is configured (`secret_reference` resolving to a key, `require_signing` not
false): UDP/TCP have no sender authentication.

## 2. Frame handling (`app/services/edge/mavlink_connector.py`)

- v1 (`0xFE`) and v2 (`0xFD`) framing, partial frames buffered across reads, resync on corruption.
- X.25 checksum with **CRC_EXTRA** for the supported messages (HEARTBEAT, SYS_STATUS, ATTITUDE, GLOBAL_POSITION_INT,
  VIBRATION, …); unsupported message ids are consumed and counted, never trusted.
- Per-`(sysid, compid)` sequence tracking: duplicates and late frames dropped, gaps counted as **packet loss**;
  sysid 0/255 (GCS) and non-autopilot components never update vehicle state. Multi-vehicle streams are routed by
  `system_id_map` (sysid → asset).
- **Signing (MAVLink 2)**: signature = first 48 bits of SHA-256(key + header + payload + CRC + link id + timestamp).
  Verified before sequence tracking, so a forged frame cannot poison loss accounting. A valid signature must carry a
  timestamp strictly greater than the last accepted one for that `(sysid, compid, link)` (replay protection). With a key
  configured, unsigned and v1 frames are refused; `require_signing: true` without a resolvable key rejects everything
  (fail closed). Key = 64 hex characters or a passphrase (SHA-256 of it), resolved from the platform secrets layer
  (`KOTA_SECRET_…` environment variables), never stored on the data source. Counters: `crc_errors`, `duplicates`,
  `late`, `lost`, `unsigned_rejected`, `bad_signature`, `replayed_signature`.
- Event time is **arrival time** (MAVLink `time_boot_ms` is boot-relative), strictly increasing per vehicle.
- No invented measurements: a bare heartbeat produces no battery or vibration values.

## 3. Verification status

| Claim | Evidence |
|---|---|
| Parser, CRC, sequence, loss, components, multi-vehicle | `test_m20_mavlink_integrity`, `test_acquisition_pipeline` (frames built with the connector's own checksum; table cross-checked against the official dialect during development) |
| Signing (valid / wrong key / tampered / replay / unsigned / forged-then-genuine) | `test_mavlink_signing`, `test_mavlink_signing_api` — the signer in the tests is written from the spec, **not** cross-checked against pymavlink or an autopilot |
| UDP / TCP listeners, allow-list, caps, back-pressure, supervisor | `test_listeners` with real loopback sockets; `backend/scripts/e2e_listener_smoke.py` with separate listener and worker processes (30 frames → 30 events, health HEALTHY) |
| Radio link, real autopilot, signing interop, sustained rates | **NOT VALIDATED** — 12 bench tests in `MAVLINK_HARDWARE_VALIDATION_PLAN.md` |

## 4. Not implemented

Serial listener; MAVLink parameter/command protocol (read-only telemetry only); microservice sub-protocols (FTP, mission);
GPS-epoch time from SYSTEM_TIME; parsing of message types beyond the supported set.
