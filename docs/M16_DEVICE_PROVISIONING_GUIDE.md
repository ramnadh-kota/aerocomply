# M16 Edge Device Provisioning Guide

## 1. Zero-Code Device Provisioning Workflow

To onboard a physical edge gateway for an airline or drone customer without application code changes:

```text
1. Generate Device Identifier (e.g. KOTA-EDGE-HZA-01)
                    │
                    ▼
2. Bind to Customer Tenant (organization_id) & Operational Asset (asset_id)
                    │
                    ▼
3. Define Attached Sensor Inventory (Vibration, Temperature, Pressure, Electrical)
                    │
                    ▼
4. Dispatch Provisioning API Request (POST /api/v1/edge/devices/provision)
                    │
                    ▼
5. Cloud Issues Factory Token & Configuration v1
                    │
                    ▼
6. Edge Daemon Boots, Ingests Token, and Dispatches Initial Heartbeat
```

---

## 2. API Provisioning Example

```http
POST /api/v1/edge/devices/provision
Authorization: Bearer <ORGANIZATION_ADMIN_TOKEN>
Content-Type: application/json

{
  "device_id": "KOTA-EDGE-VT-HZA-01",
  "device_type": "EDGE_GATEWAY",
  "asset_id": "8e01814d-3351-464a-939e-26a12b489a24",
  "firmware_version": "2.6.0-m16",
  "sensors": [
    {
      "sensor_code": "MOT_1_VIB",
      "sensor_type": "VIBRATION",
      "model": "ADXL345",
      "serial_number": "SN-VIB-8821",
      "channel": "SPI0",
      "unit": "g"
    },
    {
      "sensor_code": "ENG_1_TEMP",
      "sensor_type": "TEMPERATURE",
      "model": "PT100-RTD",
      "serial_number": "SN-TMP-9912",
      "channel": "I2C1_0x48",
      "unit": "degC"
    }
  ],
  "initial_config": {
    "sampling_hz": 1000,
    "telemetry_interval_sec": 5,
    "heartbeat_interval_sec": 30,
    "buffer_capacity": 500
  }
}
```

---

## 3. Deterministic Lifecycle States
- **`PROVISIONING`:** Identity established in database.
- **`CONFIGURED`:** Sensors and initial configuration version applied.
- **`CONNECTED`:** First heartbeat received and validated.
- **`ACTIVE`:** Normal operational state streaming valid telemetry.
- **`DEGRADED`:** Partial sensor dropout or cellular fallback active.
- **`OFFLINE`:** Heartbeat overdue (> 15 min); local buffering engaged.
- **`REVOKED`:** Decommissioned / compromised; telemetry permanently refused.
