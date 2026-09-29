# M18 Tech Guy 1 — Data Acquisition & MAVLink Connectivity Gap Analysis
## Kota Aerospace — UAV Telemetry Acquisition Layer

**Document Version:** 1.0  
**Role:** Tech Guy 1 (Data Acquisition, MAVLink Connectivity & Edge Gateway)  
**Date:** September 2026  
**Status:** Approved  

---

## 1. Executive Summary

Tech Guy 2 has completed and validated the intelligence-side pipeline (`NormalizedTelemetryEvent` -> HUMS -> Features/Baselines -> Exceedance/Finding/Evidence -> Diagnostics -> Prognostics/RUL -> M7 Signals -> Grounded LISA AI).

Tech Guy 1 is responsible for the **real-world front door**:
```
EXISTING UAV (ArduPilot / PX4)
             ↓
     MAVLink Telemetry
             ↓
   KOTA CONNECTOR / GATEWAY
             ↓
     CUSTOMER INTERNET
             ↓
    POST /api/v1/telemetry/ingest
             ↓
   NormalizedTelemetryEvent (Frozen Contract)
             ↓
   EXISTING M17/M18 INTELLIGENCE STACK
```

---

## 2. Existing Repository Capabilities (Audit)

| Domain Area | Existing Component | Status | Reuse / Extension Plan |
|---|---|---|---|
| **Canonical Telemetry Contract** | `NormalizedTelemetryEvent` ([app/schemas/telemetry.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/schemas/telemetry.py)) | **COMPLETE** | **REUSE AS-IS.** Frozen boundary with Tech Guy 2. |
| **Telemetry Ingestion Endpoint** | `POST /api/v1/telemetry/ingest` ([app/api/v1/telemetry.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/api/v1/telemetry.py)) | **COMPLETE** | **REUSE AS-IS.** Ingests batches with RBAC (`Permission.DRONE_WRITE`). |
| **External Asset Mapping** | `ExternalAssetMapping` ([app/models/telemetry.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/models/telemetry.py)) | **COMPLETE** | **REUSE AS-IS.** Maps MAVLink SysID/Serial to Kota Asset UUID. |
| **Idempotency & Event Logging** | `TelemetryEventLog` ([app/models/telemetry.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/models/telemetry.py)) | **COMPLETE** | **REUSE AS-IS.** Guarantees deduplication via `(org_id, source_system, source_event_id)`. |
| **Physical Edge Engine** | `PhysicalEdgeAcquisitionEngine` ([app/services/edge/acquisition_engine.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/edge/acquisition_engine.py)) | **PARTIAL** | Bench sensor ring buffer; lacks MAVLink protocol adapter. |
| **Edge Hardware Management** | `EdgeDevice`, `edge_hardware_service.py` ([app/services/edge_hardware_service.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/edge_hardware_service.py)) | **COMPLETE** | **REUSE.** Device registration, lifecycle statuses, and heartbeats. |
| **MAVLink Connector** | None | **MISSING** | **BUILD.** `TelemetryConnector` base and `MAVLinkConnector` implementation. |
| **MAVLink Message Decoder** | None | **MISSING** | **BUILD.** Decodes HEARTBEAT, ATTITUDE, GLOBAL_POSITION_INT, GPS_RAW_INT, BATTERY_STATUS, SYS_STATUS, VFR_HUD, SCALED_IMU/VIBRATION, ESC_STATUS. |
| **Edge Store-and-Forward Daemon** | None | **MISSING** | **BUILD.** `KotaTelemetryGateway` daemon with SQLite/disk store-and-forward, auto-reconnect, and multi-UAV tracking. |

---

## 3. Genuinely Missing Components to Build

1. **`TelemetryConnector` Abstract Base Class:**
   - Universal interface for all drone telemetry protocols (MAVLink, PX4 uORB, DJI SDK, MQTT, REST).
2. **`MAVLinkConnector` Implementation:**
   - Serial/UDP/TCP/stream MAVLink reader.
   - Decodes MAVLink v1/v2 binary frames and packet payloads.
   - Normalizes raw integer units (degE7, mm, mV, cA, cdegC) to SI/canonical engineering units (degrees, meters, m/s, Volts, Amperes, Celsius, mm/s).
   - Generates compliant `NormalizedTelemetryEvent` instances.
3. **`KotaTelemetryGateway` Service:**
   - Multi-UAV session router (tracking MAVLink `system_id` to asset mappings).
   - Persistent store-and-forward buffer (SQLite / file ring buffer) for offline resilience.
   - Uplink worker with exponential backoff retry and replay synchronization.
   - Heartbeat dispatcher reporting gateway and UAV connectivity metrics to Kota Cloud.
4. **Hardware & Deployment Independence:**
   - Zero dependency on Mission Planner in production.
   - Zero dependency on permanently attached laptops.
   - Runs seamlessly on onboard companion computers (Raspberry Pi, NVIDIA Jetson), edge micro-gateways, or cellular telemetry modems.

---

## 4. Architectural Invariants

- **No Drone Hardware Engineering:** Software-first acquisition consuming existing UAV telemetry streams.
- **No Duplicate Telemetry Ingestion Endpoint:** Gateway pushes strictly to `POST /api/v1/telemetry/ingest`.
- **No Duplicate Canonical Model:** Normalizes directly into `NormalizedTelemetryEvent`.
- **Tenant & Asset Isolation:** Gateway authenticates with tenant API token; external asset mappings strictly resolve within caller's tenant.
- **Store-and-Forward Resilience:** Network interruptions buffer data locally and replay with original timestamps upon reconnection without data loss or duplicate spam.
