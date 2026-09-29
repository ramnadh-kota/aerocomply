# M17 Tech Guy 1 → Tech Guy 2 Interface Handoff Contract

**Document Version:** 1.0  
**From:** Tech Guy 2 (Intelligence-Side Engineering, Kota Aerospace)  
**To:** Tech Guy 1 (Telemetry Acquisition & Edge Engineering, Kota Aerospace)  
**Date:** September 2026  

---

## 1. Boundary & Separation of Responsibilities

Tech Guy 1 owns:
- Physical UAVs, flight controllers (PX4, ArduPilot), onboard sensors, and ESC telemetry.
- Radio systems, ELRS, telemetry transceivers, and ground control station (Mission Planner / QGroundControl).
- MAVLink stream decoding, parsing, and normalization.
- Edge gateways and transport to the cloud.

Tech Guy 2 owns:
- Ingestion and consumption of Normalized Canonical Telemetry.
- Feature extraction, baseline comparison, and anomaly detection.
- Finding creation and evidence linkage.
- Diagnostics and fault signature matching.
- Prognostics and Remaining Useful Life (RUL) estimation.
- M7 Proactive Intelligence early warning signals.
- LISA AI grounded reasoning and Control Center dashboards.

---

## 2. Ingress API Endpoint

Tech Guy 1 will publish canonical telemetry batches via HTTPS:

- **Method:** `POST`
- **Path:** `/api/v1/telemetry/ingest`
- **Headers:**
  - `Authorization: Bearer <tenant_jwt_or_api_token>`
  - `Content-Type: application/json`

---

## 3. Payload Schema Contract

The request payload is a `TelemetryIngestRequest`:

```json
{
  "events": [
    {
      "source_system": "KOTA_GATEWAY",
      "source_event_id": "evt-20260929-104500-001",
      "source_asset_id": "UAV-ALPHA-01",
      "event_type": "REALTIME_TELEMETRY",
      "event_timestamp": "2026-09-29T10:45:00Z",
      "flight": {
        "flight_number": "FLT-101",
        "duration_minutes": 25,
        "cycles": 1,
        "origin": "PAD-NORTH",
        "destination": "PAD-SOUTH",
        "flown_at": "2026-09-29T10:20:00Z"
      },
      "battery": {
        "serial_number": "BAT-6S-9921",
        "cycle_count": 48,
        "voltage_v": 22.8,
        "internal_resistance_mohm": 12.4,
        "temperature_c": 34.5,
        "health_percent": 98
      },
      "readings": [
        {
          "sensor_code": "VIB_MOTOR_1",
          "sensor_type": "VIBRATION",
          "measurement_type": "vibration",
          "value": 3.42,
          "unit": "mm/s",
          "data_quality": "VALID"
        },
        {
          "sensor_code": "TEMP_ESC_1",
          "sensor_type": "TEMPERATURE",
          "measurement_type": "temperature",
          "value": 48.6,
          "unit": "celsius",
          "data_quality": "VALID"
        }
      ],
      "raw_metadata": {
        "gateway_fw": "v2.4.1",
        "rssi_dbm": -68
      }
    }
  ]
}
```

---

## 4. Invariant Rules for Tech Guy 1

1. **Deterministic Event IDs:** `source_event_id` must be globally unique per event. Retried messages MUST keep the same `source_event_id` so the intelligence pipeline can safely deduplicate.
2. **Canonical Units:**
   - Vibration: `mm/s` or `g`
   - Temperature: `celsius`
   - Voltage: `volts` (or `V`)
   - Current: `amperes` (or `A`)
   - Rotational speed: `rpm`
   - Pressure: `bar` or `psi`
3. **Data Quality Flags:**
   - `VALID`: Healthy, verified sensor reading.
   - `SUSPECT`: Questionable CRC or intermittent drop.
   - `OUT_OF_RANGE`: Exceeds physical sensor bounds.
   - `STALE`: Cached reading from disconnected sub-bus.
   - `INVALID`: Unreadable or malformed packet.
4. **No Direct MAVLink Leakage:** Downstream intelligence components will NEVER process raw MAVLink packet structs. All field mapping must be normalized prior to handoff.

---
