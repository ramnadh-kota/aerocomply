# KOTA Aerospace — Edge Telemetry & Hardware Specification

## 1. Overview & Canonical Envelope (M14.12)

The KOTA Edge Telemetry Envelope provides a standardized, hardware-agnostic ingestion contract for field IoT gateways, airborne OBD loggers, and OEM telemetry hubs.

### JSON Envelope Format

```json
{
  "device_id": "KOTA-EDGE-SN-1082",
  "gateway_id": "KOTA-EDGE-SN-1082",
  "firmware_version": "2.4.1",
  "source_asset_id": "DR-HZ01",
  "sequence_number": 1042,
  "envelope_timestamp": "2026-09-28T10:45:00Z",
  "measurements": [
    {
      "sensor_code": "MOT_1_VIB",
      "sensor_type": "VIBRATION",
      "timestamp": "2026-09-28T10:45:00Z",
      "unit": "g",
      "raw_values": {
        "rms_g": 0.22,
        "peak_g": 0.58,
        "crest_factor": 2.63
      },
      "quality": "VALID"
    },
    {
      "sensor_code": "MOT_1_TEMP",
      "sensor_type": "TEMPERATURE",
      "timestamp": "2026-09-28T10:45:00Z",
      "unit": "degC",
      "raw_values": {
        "temp_c": 54.2
      },
      "quality": "VALID"
    }
  ],
  "signature": "hmac_sha256_sig_here"
}
```

---

## 2. Ingestion & Data Flow

```text
Physical Sensor / CAN Bus
           │
           ▼
    Edge Gateway
 (Local SQLite Buffer)
           │
           ▼ (HTTPS / MQTT POST /api/v1/edge/ingest)
    KOTA Edge Router
           │
           ▼
 telemetry_service.process_normalized_event
           │
  ┌────────┼────────┐
  ▼        ▼        ▼
Flight    Battery  HUMSSensorReading
Log       State    (RMS / FFT Features)
                    │
                    ▼
               M7 Intelligence
                    │
                    ▼
                 LISA AI
```
