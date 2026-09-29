# DJI FlightHub 2 — Production Telemetry Activation Guide

## 1. Overview

KOTA Aerospace / AeroComply integrates with **DJI FlightHub 2** to ingest flight telemetry, battery analytics, and vibration metrics automatically into authoritative maintenance accounting, HUMS feature pipelines, and proactive intelligence.

---

## 2. Webhook Registration in FlightHub 2

1. Log in to the **DJI FlightHub 2 Developer Platform**.
2. Navigate to **Organization Settings → Developer Center → Webhook Subscriptions**.
3. Create Webhook:
   - **Callback URL**: `https://api.aerocomply.com/api/v1/telemetry/dji/webhook`
   - **Custom Headers**:
     - `X-Organization-ID`: `<YOUR_KOTA_ORGANIZATION_UUID>`
   - **Subscribed Events**:
     - `flight_record.created`
     - `device.osd.telemetry`
     - `battery.status`
     - `device.hums.vibration`
4. Copy the generated **Webhook Secret** (used for HMAC-SHA256 signature verification in header `X-DJI-Signature`).

---

## 3. External Asset Mapping in KOTA Aerospace

Map each DJI aircraft serial number to internal KOTA Asset IDs:

```http
POST /api/v1/telemetry/mappings
Authorization: Bearer <CAMO_MANAGER_JWT>
Content-Type: application/json

{
  "source_system": "DJI_FLIGHTHUB",
  "external_asset_id": "FC30-0981-HZ01",
  "asset_id": "a1b2c3d4-0000-0000-0000-000000000001",
  "device_model": "DJI FlyCart 30",
  "notes": "Horizon Medical Logistics Drone 1"
}
```

---

## 4. Ingestion Lifecycle & Idempotency

```text
DJI FlightHub 2 Webhook POST
    ↓
HMAC-SHA256 Signature Verification (`X-DJI-Signature`)
    ↓
Payload SHA-256 Hash & Deterministic Idempotency Check
    ↓
Tenant-Scoped Asset Resolution (`external_asset_mappings`)
    ↓
Flight Domain Dispatch (`flight_service.record_flight`)
    ↓
Battery State Accounting (`Battery` cycle count & health %)
    ↓
HUMS Sensor Reading Persistence (`HUMSSensorReading`)
    ↓
Telemetry Audit Log (`TelemetryEventLog`)
```

- **Idempotency**: Duplicate event deliveries with the same `(organization_id, source_system, source_event_id)` are detected, logged as `DUPLICATE`, and safely ignored without double-counting flight hours.
