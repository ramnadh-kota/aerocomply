# Live Drone Operations & LISA Copilot — C1 Audit, Contracts and Milestone Tracker

Audited against the repository at branch `feature/post-freeze-productionization` (2026-10-02). Statements below were
verified in code, not taken from earlier reports. Scope is **read-only** flight operations: no remote control, no
autonomous commands.

## 1. Verified existing capabilities (REUSE — do not rebuild)

| Concern | Owner (file) | Notes |
|---|---|---|
| Asset identity | `models/asset.py`, `services/asset_service.py`, `asset_resolution.py`, `ExternalAssetMapping` | deterministic, tenant-checked resolution |
| MAVLink parsing | `services/edge/mavlink_connector.py` | v1/v2 framing, CRC_EXTRA, seq/loss/dup/late, signing + replay protection. Messages: HEARTBEAT, SYS_STATUS, GPS_RAW_INT, GLOBAL_POSITION_INT, VFR_HUD, BATTERY_STATUS (+ATTITUDE, VIBRATION) |
| Ingestion pipeline | `services/acquisition_service.py` → `telemetry_service.process_normalized_event` | per-event SAVEPOINT, idempotency (`uq_telemetry_event_org_source_eventid`), quarantine, health evidence, metrics, audit |
| Transport | `listeners/` (UDP/TCP/MQTT), `worker.py`, `background_job` queue, `webhooks.py` | bounded buffers, back-pressure, CIDR allow-list |
| Telemetry persistence | `models/telemetry.py`, `models/flight.py`, `models/hums.py` | PostgreSQL authoritative |
| Device registry | `EdgeDevice`, `edge_hardware_service.py`, `/edge/*` | provision, config versioning, command queue (non-flight commands only), revoke |
| M7 proactive | `models/proactive_signal.py`, `intelligence/proactive_intelligence_service.py`, `proactive_service.py` | canonical owner of fleet attention / HUMS signals |
| M14 cross-asset | `intelligence/cross_asset_intelligence_service.py` | |
| LISA | `services/lisa/orchestration_service.py` (+ intent/entity/context services) | extend, do not replace |
| Auth/RBAC/entitlements | `core/deps.py`, `permissions.py`, `entitlement_service.py`, feature `flight_telemetry` | |
| Observability | `core/metrics.py`, `metrics_server.py`, structlog | |
| Fleet view | `control_center_service.py` (aircraft rows) | compliance-oriented, not live state |

## 2. Verified gaps and defects

| ID | Milestone | Finding | Severity |
|---|---|---|---|
| G-C2-1 | C2 | **Device token hash was stored (`auth_token_hash`) but never verified.** Device heartbeat/ingest (`/edge/...`) authenticated via *user JWT*; no machine identity. | High — **FIXED** (see §4) |
| G-C2-2 | C2 | Caller-supplied `auth_secret` was accepted as the device secret (weak-secret risk); re-provisioning replaced credential silently, no rotation/expiry/audit. | High — **FIXED** |
| G-C2-3 | C2 | No device↔approved MAVLink data-source binding; no connectivity/freshness state with configurable timeout. | Med — **FIXED** |
| G-C2-4 | C2 | Legacy `/edge/devices/{id}/heartbeat` and `/edge/ingest` still accept user JWT (backward compatible); `/edge/ingest` ingests for unregistered devices. | Med — OPEN (deprecate after fleet migrates) |
| G-C3-1 | C3 | MISSION_CURRENT, MISSION_ITEM_REACHED, STATUSTEXT not parsed. | Med — **FIXED** |
| G-C3-2 | C3 | No canonical *versioned* drone live-state event; MAVLink event time = arrival time (boot-relative `time_boot_ms`), no GPS-epoch. | Med — **FIXED** (versioned `live_state` in event metadata; time remains arrival time, documented) |
| G-C3-3 | C3 | Connector state (`_CONNECTORS`) is process-local (documented). | Low — documented |
| G-C4-1 | C4 | **No latest-state store, no snapshot API, no SSE/WebSocket anywhere in the backend.** | High — OPEN |
| G-C4-2 | C4 | No state-freshness/offline detection independent of last value (only data-source health). | High — OPEN |
| G-C5-1 | C5 | **No geofence / restricted / caution zone model or evaluation.** | High — OPEN |
| G-C5-2 | C5 | No live-event lifecycle (ack/resolve), hysteresis or dedup for low-battery/telemetry-loss. M7 signals exist for HUMS only. | High — OPEN |
| G-C6-1 | C6 | LISA has no live-fleet/geofence/mission tools; no trajectory/battery-reserve analytics. | High — OPEN |
| G-ENV | env | Integration tests need `TEST_DB_PORT=55432` on this workstation (default 5432 is unreachable). | Note |

External-only (cannot be validated locally): real autopilot/radio, signing interop, sustained rates, real companion
computer, production multi-worker scale.

## 3. Canonical contracts (design decisions)

**Authority.** PostgreSQL is the source of truth. Latest state (C4) = a table `drone_live_state(organization_id,
asset_id PK, seq, state_version, last_event_at, last_received_at, payload JSONB, source_system, device_id)` updated
*from* the existing acquisition pipeline after a PROCESSED event (single writer: acquisition_service) — not a second
ingest path. Freshness is computed at read time from `last_event_at`/`last_received_at`, never stored as a status.

**Live-state object (`kota.drone.live_state.v1`)**: `asset_id, device_id, seq, observed_at, received_at, freshness
{FRESH|STALE|LOST|NO_DATA, age_seconds}, position{lat,lon,alt_msl_m,alt_rel_m,fix_type,hdop,sats}, kinematics{ground_speed,
climb,heading,airspeed}, battery{voltage,current,remaining_pct}, mode{armed,custom_mode,system_status}, mission{current,
reached}, link{connectivity,device_state}, provenance{source_system,data_source_id,message_types}`. Missing values are
`null`, never defaulted.

**Streaming (`GET /api/v1/live/stream`, SSE, tenant from JWT)**: first event `snapshot` (full fleet + `cursor`), then
`state` / `alert` / `heartbeat` events each with monotonic `seq`; clients resume with `Last-Event-ID`; if the cursor is
older than the retained window the server sends `resync_required` and the client re-fetches `/live/fleet`. Events are
idempotent by `(asset_id, seq)`.

**REST**: `GET /live/fleet`, `GET /live/drones/{asset_id}`, `GET /edge/connectivity`,
`GET /edge/devices/{id}/connectivity` (done), alerts `GET /live/alerts`, `POST /live/alerts/{id}/ack|resolve`.

**AuthZ**: user routes `DRONE_READ` + `flight_telemetry`; device routes `X-Kota-Device-Key` only; admin device
actions `ORG_MANAGE`. Geofence output is *advisory information*, never legal airspace authorisation.

## 4. C2 — implemented and verified

Files: `services/device_auth_service.py` (new), `api/v1/device_gateway.py` (new), `api/v1/edge_hardware.py`,
`api/v1/router.py`, `services/edge_hardware_service.py`, `tests/integration/test_c2_device_enrollment.py`.

* Credential `kdev.<edge_device_uuid>.<secret>` (256-bit CSPRNG), SHA-256 stored, constant-time compare, uniform 401,
  tenant derived from the device row, expiry (365 d), rotation with optional ≤1 h overlap, revocation, suspended/
  deletion-pending org refused, pre-C2 devices refused until rotated.
* `POST /device/heartbeat`, `POST /device/telemetry/mavlink` (routes only into the admin-bound MAVLINK data source;
  entitlement `flight_telemetry` enforced; 1 MB cap).
* Admin: `POST /edge/devices/{id}/credential/rotate`, `PUT /edge/devices/{id}/data-source`, connectivity endpoints.
* Connectivity: ONLINE/DEGRADED/OFFLINE/REVOKED from authenticated heartbeats (timeout = `connectivity_timeout_seconds`
  or 3× heartbeat interval); telemetry freshness FRESH/STALE/LOST/NO_TELEMETRY reported separately.
* No schema migration (credential lives in `edge_devices.metadata_json`); stale-secret plaintext is never stored.

## 5. Milestone tracker

| Milestone | Status |
|---|---|
| C1 audit + contracts | DONE (this document); backlog below |
| C2 enrollment/connectivity | Implemented; tests: 5 new + 7 existing M16 pass. Exit met locally (no real hardware) |
| C3 MAVLink ingestion extensions | Implemented; `tests/unit/test_c3_mavlink_live_state.py` + full unit suite (574) pass |
| C4 live state + SSE | NOT STARTED |
| C5 geofence + alerts | NOT STARTED |
| C6 LISA live tools + analytics | NOT STARTED |

Backlog (dependency order): C3 parse MISSION_CURRENT/ITEM_REACHED/STATUSTEXT → C4 `drone_live_state` + migration 0071
+ fleet/detail APIs + SSE broker → C5 geofence tables + evaluator + alert lifecycle (publishing into M7) → C6 read-only
LISA tools over C4/C5 + analytic services + evals.
