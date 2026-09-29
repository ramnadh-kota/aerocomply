# M18 Tech Guy 1 Integration Status & Readiness Report
## Kota Aerospace — Live Telemetry Gateway Boundary

**Document Version:** 1.0  
**Owner:** Tech Guy 2 (Intelligence-Side Engineering, Kota Aerospace)  
**Status:** READY FOR LIVE UAV STREAM  

---

## 1. Integration Boundary Summary

The production boundary between Tech Guy 1 (Edge/Gateway Acquisition) and Tech Guy 2 (Intelligence Processing) is frozen, hardened, and verified:

```
+-----------------------------------------------------------------------------------+
| TECH GUY 1 (Acquisition & Transport)                                              |
| - Real UAV Hardware (ArduPilot / PX4)                                             |
| - Onboard Sensors & ESC Telemetry                                                 |
| - MAVLink Acquisition, Decoding & Normalization                                   |
| - Edge Gateway / Companion Computer (Raspberry Pi / Jetson)                       |
| - Secure Transport (HTTPS / mTLS / WSS)                                           |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼ POST /api/v1/telemetry/ingest
                                         │ Body: {"events": [NormalizedTelemetryEvent, ...]}
+-----------------------------------------------------------------------------------+
| TECH GUY 2 (Intelligence & Grounded AI)                                           |
| - Ingestion, Idempotency & Asset Mapping Resolution                               |
| - HUMS Feature Extraction (RMS, Peak, Crest Factor, Kurtosis, FFT Frequency)      |
| - Statistical Baselines & Anomaly Exceedances                                     |
| - Structured Findings & Immutable Evidence Digital Thread                         |
| - Deterministic Diagnostic Fault Signature Matching                               |
| - Degradation Trajectory Fitting & RUL Prognostics                                |
| - M7 Proactive Intelligence Warning Signals                                       |
| - Grounded LISA AI Context & Kota Control Center Dashboard                        |
+-----------------------------------------------------------------------------------+
```

---

## 2. Ingress API Specification

- **Endpoint:** `POST /api/v1/telemetry/ingest`
- **Authentication:** `Authorization: Bearer <API_TOKEN_OR_JWT>`
- **Permissions Required:** `Permission.DRONE_WRITE` (or role `DRONE_GATEWAY` / `ORG_ADMIN`)
- **Content-Type:** `application/json`
- **Response Format:**
```json
{
  "total_received": 1,
  "processed_count": 1,
  "duplicate_count": 0,
  "rejected_count": 0,
  "results": [
    {
      "source_event_id": "evt-uav01-20260929-113000",
      "status": "PROCESSED",
      "asset_id": "d7f5280c-54f6-4686-903d-5050cafa4c58",
      "flight_id": "8fa1103c-22a4-4781-a9f2-6901a1c9ef00",
      "readings_count": 2,
      "message": null
    }
  ]
}
```

---

## 3. Readiness Status for Tech Guy 1

| Component | Status | Verification Detail |
|---|---|---|
| **API Endpoint** | **READY** | `POST /api/v1/telemetry/ingest` tested and operational |
| **Asset Mapping** | **READY** | Maps hardware serials (e.g. `UAV-ALPHA-001`) to Kota Asset UUIDs |
| **Deduplication** | **READY** | Re-sent packets ignored idempotently with `DUPLICATE` status |
| **Quarantine Guard** | **READY** | Unregistered hardware IDs quarantined safely without crashing |
| **Multi-UAV Concurrency** | **READY** | Handles simultaneous streams from multiple UAVs without cross-talk |
| **Staleness Monitoring** | **READY** | Automatically tracks stream freshness and emits warnings on disconnect |
| **Buffered Replay** | **READY** | Safely processes offline backlogged telemetry upon reconnection |

---

## 4. Immediate Next Step for Tech Guy 1

1. Point the Edge Gateway publisher to `POST https://<api_domain>/api/v1/telemetry/ingest`.
2. Provide the Gateway API Token with tenant authorization headers.
3. Stream canonical `NormalizedTelemetryEvent` packets during pre-flight and flight operations.
4. No further backend or intelligence modifications are required from Tech Guy 1.
