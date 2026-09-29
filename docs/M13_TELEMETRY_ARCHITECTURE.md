# KOTA Aerospace / AeroComply — M13 Telemetry Architecture

## Telemetry Ingestion Contract & DJI FlightHub 2 Adapter

### 1. Executive Summary & Objective

The M13 Telemetry Ingestion subsystem provides an authenticated, tenant-isolated, idempotent, and auditable pipeline to ingest operational and sensor telemetry from external sources (such as DJI FlightHub 2, onboard HUMS units, and third-party ground control stations) into KOTA Aerospace / AeroComply.

Telemetry ingestion is designed under the **Domain Service Invariant**: telemetry feeds directly into existing domain services (`flight_service.record_flight`, battery state services, `HUMSSensor` / `HUMSSensorReading` models) rather than creating a parallel source of truth or mutating database state ad-hoc.

---

### 2. Architecture & Pipeline

```text
External Source (e.g. DJI FlightHub 2 Webhook / HUMS Gateway)
                              ↓
              Authenticated Ingestion Endpoint
      (HMAC-SHA256 Signature Verification / JWT RBAC)
                              ↓
                  Raw Event Validation
      (JSON Schema validation, timestamp sanity checks)
                              ↓
                   Deterministic Idempotency
      (Tenant + Source System + Source Event ID uniqueness)
                              ↓
              Replay / Ordering / Freshness Check
                              ↓
                Tenant-Scoped Asset Resolution
       (ExternalAssetMapping table: org_id + source + ext_id)
                              ↓
                Unmatched Asset Quarantine
         (Quarantine record if external ID not mapped)
                              ↓
                     Domain Services
      ├── flight_service.record_flight (utilization / cycles)
      ├── battery_service (voltage, cycle count, health %)
      └── hums_service (HUMSSensor & HUMSSensorReading)
                              ↓
           Authoritative PostgreSQL Operational State
```

---

### 3. Core Architectural Invariants

1. **PostgreSQL as Sole Authoritative Truth**: Telemetry is an ingestion channel, not a secondary source of truth.
2. **Tenant Isolation**: Every mapping, event log, sensor reading, and flight record is strictly scoped by `organization_id`. Cross-tenant lookup and global searches are prohibited.
3. **Domain-Service Invariant**: State modifications must invoke domain services (`flight_service.record_flight`) to ensure flight hours, landing cycles, maintenance schedules, and readiness scores are correctly calculated.
4. **Idempotency & Double-Counting Protection**: Duplicate deliveries (e.g. webhook retries) are detected via deterministic compound key `(organization_id, source_system, source_event_id)` and rejected before domain writes occur. Flights recorded manually or via telemetry match on operation/source identifiers to prevent double utilization counting.
5. **Historical Baseline Protection**: Ingestion respects the M5 historical migration baseline and does not re-import pre-baseline flights or corrupt baseline totals.

---

### 4. Component Details

#### 4.1. Database Models (`app/models/telemetry.py`)
- **`ExternalAssetMapping`**: Maps `(organization_id, source_system, external_asset_id)` to internal `asset_id` (Aircraft / Drone). Enforces unique constraint across tenant + source + external ID.
- **`TelemetryEventLog`**: Stores telemetry ingestion events with status (`RECEIVED`, `VALIDATING`, `VALIDATED`, `PROCESSED`, `DUPLICATE`, `UNMATCHED`, `QUARANTINED`, `REJECTED`, `FAILED`), raw payload hash (`SHA256`), and processing metadata.
- **`TelemetryProcessingStatus`**: Enum for tracking lifecycle states.

#### 4.2. Schema & Normalization Contract (`app/schemas/telemetry.py`)
- **`NormalizedTelemetryEvent`**: Canonical schema including:
  - `source_system`: `DJI_FLIGHTHUB`, `HUMS_DEVICE`, `OTHER_TELEMETRY`, etc.
  - `source_event_id`: Unique external event ID.
  - `source_asset_id`: Serial number or external drone ID.
  - `event_type`: e.g. `flight_record.created`, `device.osd.telemetry`.
  - `event_timestamp`: UTC timestamp of event generation.
  - `flight`: Optional `TelemetryFlightPayload` (duration, cycles, route).
  - `battery`: Optional `TelemetryBatteryPayload` (voltage, cycles, health %).
  - `readings`: List of `TelemetryReadingItem` (sensor code, value, unit).
- **`DJIFlightHubWebhookPayload`**: DJI-specific payload schema normalized via `normalize_dji_webhook_payload()`.

#### 4.3. Ingestion Service (`app/services/telemetry_service.py`)
- **`verify_webhook_signature(raw_body, signature_header, secret)`**: Constant-time HMAC-SHA256 verification against unparsed request bytes.
- **`resolve_asset(db, organization_id, source_system, external_asset_id)`**: Tenant-scoped asset resolver.
- **`process_normalized_event(db, organization_id, event, raw_payload)`**: Complete pipeline managing idempotency checks, asset resolution, domain service execution, battery updates, and HUMS reading persistence.

#### 4.4. API Endpoints (`app/api/v1/telemetry.py`)
- `POST /api/v1/telemetry/dji/webhook`: Webhook endpoint with header-based tenant resolution (`X-Organization-ID`) and HMAC signature verification (`X-DJI-Signature`).
- `POST /api/v1/telemetry/ingest`: Protected generic ingestion endpoint requiring authenticated user and `Permission.DRONE_WRITE`.
- `POST /api/v1/telemetry/mappings`: Asset mapping creation endpoint requiring `Permission.DRONE_WRITE`.
- `GET /api/v1/telemetry/mappings`: Asset mapping listing endpoint requiring `Permission.DRONE_READ`.
- `GET /api/v1/telemetry/events`: Telemetry event audit query endpoint requiring `Permission.DRONE_READ`.

---

### 5. DJI Contract Status & External Dependency

> [!WARNING]
> **EXTERNAL DEPENDENCY — NOT LIVE VERIFIED**
> Live DJI FlightHub 2 webhook integration is currently validated against synthetic OpenAPI v2 schemas and deterministic test fixtures. Live production deployment requires end-to-end verification against customer-specific FlightHub 2 organization credentials, webhook endpoints, and signing keys.

---

### 6. Audit & Observability

All telemetry events record audit logs (`audit_service.log_event`):
- `TELEMETRY_INGEST_RECEIVED`: Event received and logged.
- `TELEMETRY_INGEST_PROCESSED`: Successfully processed and domain services executed.
- `TELEMETRY_INGEST_DUPLICATE`: Duplicate event detected and safely skipped.
- `TELEMETRY_INGEST_UNMATCHED`: Unmatched external asset quarantined.
- `TELEMETRY_INGEST_REJECTED`: Validation failure.
- `TELEMETRY_INGEST_AUTH_FAILURE`: Missing or invalid signature.
