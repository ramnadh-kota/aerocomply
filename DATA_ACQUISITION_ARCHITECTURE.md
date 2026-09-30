# Kota Aerospace — Data Acquisition Architecture (as implemented)

> Supersedes the earlier specification-style version of this file, which described components that
> do not exist in the code (Redis de-duplication, asynchronous worker queues, TimescaleDB, a
> `/webhooks/dji` route, an async `BaseDataConnector`, a flat event model). Every statement below
> is backed by code and by a test named in the last column. Things that are **not** built are listed
> in §9 and are not claimed anywhere else.

## 1. The path

```text
 DataSource (tenant-bound, ACTIVE)              POST /api/v1/data-sources/{id}/ingest   (raw body, ≤ 25 MB)
        │                                        POST /api/v1/telemetry/ingest           (already-normalised batch)
        ▼                                        POST /api/v1/telemetry/dji/webhook      (HMAC-signed, tenant by header)
 connector  ── MAVLink v1/v2 | MQTT | CSV | JSON | canonical webhook JSON
        ▼
 NormalizedTelemetryEvent          (app/schemas/telemetry.py)
        ▼
 acquisition_service.ingest        (app/services/acquisition_service.py)  ← per-event SAVEPOINT, health evidence, metrics
        ▼
 telemetry_service.process_normalized_event      ← THE persistence path (one implementation)
   1. idempotency        unique (org, source_system, source_event_id)
   2. quality gate       naive / future(>5 min) / pre-2000 timestamp → REJECTED
   3. asset resolution   explicit mapping → asset id → UNIQUE exact serial/registration; ambiguous or unknown → QUARANTINED
   4. flight             one Flight per streaming session (flight_number + start), advisory-locked per asset
   5. battery            updates an EXISTING battery only; never invents cycle counts
   6. sensors/readings   get-or-create sensor (race-safe), reading rows
   7. exceedances        HUMS detection (failures logged, isolated by SAVEPOINT)
   8. event log + audit  telemetry_event_logs row, audit event
        ▼
 hums_sensor_readings · flights · telemetry_event_logs · hums_exceedances → findings → M7 → LISA
```

## 2. Canonical event (actual fields)

`NormalizedTelemetryEvent`: `source_system`, `source_event_id`, `source_asset_id`, `event_type`,
`event_timestamp`, optional `flight` (flight_number, duration_minutes, cycles, origin, destination,
flown_at, notes), optional `battery` (serial_number, cycle_count, voltage_v, temperature_c,
health_percent, …), `readings[]` (sensor_code, sensor_type, measurement_type, **value (finite only)**,
unit, component_id, data_quality), `raw_metadata`.
Reading `data_quality` ∈ VALID, SUSPECT, MISSING, OUT_OF_RANGE, STALE, DUPLICATE, INVALID.
Processing status ∈ RECEIVED, VALIDATED, PROCESSED, DUPLICATE, REJECTED, QUARANTINED, FAILED.

## 3. Data sources

Model `data_sources` (migrations 0062, 0063): `connector_type` ∈ MAVLINK, MQTT, DJI_FLIGHTHUB, CSV_BATCH,
JSON_BATCH, OEM_API, GENERIC_WEBHOOK; status DRAFT → ACTIVE ⇄ PAUSED → DECOMMISSIONED; `connection_config`
(no credentials — keys such as password/token/api_key are refused; use `secret_reference`);
health evidence columns (last seen/success/failure, duplicate/quarantine/loss counters, latency).
Only ACTIVE sources accept data (409 `data_source_not_active`). The whole `/data-sources` surface
requires an active `flight_telemetry` entitlement in addition to RBAC.

Configuration keys understood by the orchestrator: `system_id_map` (MAVLink sysid → asset id or
external id), `topic_filter`, `source_system`, `expected_interval_seconds` (enables staleness health),
`asset_binding: "SINGLE_ASSET"` + `default_asset_id` (explicit opt-in; the asset must belong to the
source's own tenant).

## 4. Connectors

| Connector | Input | Identity / ordering / integrity | Tests |
|---|---|---|---|
| MAVLink | raw v1/v2 bytes | CRC-16/X.25 + CRC_EXTRA verified (8 message types, seeds cross-checked against the official dialect); per-(sysid, compid) sequence: duplicates and late frames dropped, gaps counted as loss; GCS (sysid 0/255) and non-autopilot components ignored; signed v2 frames framed correctly (signature not verified); **no invented measurements** | `test_m20_mavlink_integrity`, `test_acquisition_pipeline` |
| MQTT | one message payload (+ topic) | device timestamp honoured; content-derived event id (at-least-once redelivery is a duplicate); payload asset id outranks topic segment, conflict recorded in metadata | `test_acquisition_pipeline` |
| CSV / JSON | file body (≤ 10 000 rows) | content-derived event id (re-upload idempotent, no cross-file collisions); ordered column priority; unparseable timestamp = row error (never "now"); empty/non-finite records rejected | `test_acquisition_pipeline`, `test_phase_b_data_acquisition` |
| DJI FlightHub | signed webhook | HMAC mandatory; endpoint disabled (503) until `DJI_WEBHOOK_SECRET` is set; target tenant must hold `flight_telemetry` | `test_m13_telemetry_ingestion`, `test_m20_route_gating` |

## 5. Guarantees (each test-backed)

- **Tenant binding**: the organization comes from the DataSource row loaded with the caller's organization; another tenant's source is 404.
- **No guessing**: unknown or ambiguous identifiers are quarantined, never attached; soft-deleted assets never receive data.
- **Replay after fix**: a quarantined event re-sent after its mapping is corrected is processed (its log row is updated).
- **Atomicity**: one event is one unit; a failing event rolls back only itself (SAVEPOINT).
- **Concurrency**: duplicate-event race → exactly one PROCESSED; parallel first events of one flight/sensor → one Flight, one sensor (`test_concurrency`).
- **Hostile input**: recursion bombs, binary junk, `Infinity`, oversized values never yield a 5xx and never store data (`test_customer_journeys_commercial`).
- **Health is evidence**: derived from recorded counters/timestamps, never assumed; "NO_DATA_YET" is reported as such.

## 6. Read side (Phase C)

`GET /telemetry/assets/{id}/status | latest | history | flights`, `GET /telemetry/events` (real total, filters).
`latest` reports each sensor's own reading time and age — a stalled feed shows growing age, not a fresh value.

## 7. Health states

HEALTHY / DEGRADED / FAILED / INACTIVE from: lifecycle status, consecutive failures (≥2 degraded, ≥5 failed),
staleness against `expected_interval_seconds` (>3× degraded, >10× failed), packet loss ≥ 20 % (min 10), and
quarantine ≥ 50 % (min 5).

## 8. Time

MAVLink `time_boot_ms` is boot-relative, so MAVLink events are stamped with **arrival time**, made strictly
increasing per vehicle. Buffered/late frames therefore carry their delivery time. Batch/MQTT use the source's own timestamp when present
(`raw_metadata.timestamp_source` = SOURCE | RECEIVED).

## 9. NOT implemented (roadmap, not claims)

| Item | State |
|---|---|
| MQTT broker subscription, MAVLink UDP/TCP/serial listener | **No process exists** that opens a socket. Connectors decode bytes handed to them; an external gateway/worker must deliver to `/ingest`. EXTERNAL / NOT IMPLEMENTED |
| Asynchronous queue / workers / dead-letter | none — ingestion is synchronous in the request; bounded by 25 MB / 10 000 rows |
| Rate limiting and quota (`max_telemetry_rate_hz`) | none on ingest (only body/row limits and entitlement) |
| Redis/window de-duplication | not used; idempotency is the database unique constraint + connector sequence state (per worker process) |
| OEM_API / ERP / cloud-storage pull connectors | type exists in the enum; **no pull implementation** |
| Per-source machine credentials | ingest uses a tenant user/API token (JWT); no source-scoped key |
| Flight-phase detection (takeoff/cruise/landing) | not implemented; a flight is only what the source supplies (MAVLink: one session flight per vehicle) |
| MAVLink signature verification, GPS-epoch time (SYSTEM_TIME) | not implemented |
| TimescaleDB / hypertables | not used; plain PostgreSQL tables |
