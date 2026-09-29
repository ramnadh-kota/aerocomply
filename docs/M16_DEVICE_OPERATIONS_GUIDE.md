# M16 Edge Device Operations Guide

## 1. Overview
This runbook guides platform operators in managing physical edge gateways, monitoring device health, updating configuration versions, executing diagnostics commands, and revoking decommissioned units.

---

## 2. Routine Operational Tasks

### Checking Device Health & Heartbeats
Query device health to verify uptime, last heartbeat freshness, and resource metrics:
```http
GET /api/v1/edge/devices/{device_id}/health
Authorization: Bearer <TOKEN>
```
Response provides:
- `health_status`: `HEALTHY` (fresh heartbeat < 15 min), `STALE`, or `REVOKED`.
- `lifecycle_stage`: Current operational stage.
- `observability`: CPU %, memory %, disk space, and buffer queue depth.

---

### Updating Device Configuration
Deploy updated acquisition settings (e.g. changing sampling rate or active channels):
```http
POST /api/v1/edge/devices/{device_id}/config
Content-Type: application/json

{
  "settings": {
    "sampling_hz": 2000,
    "telemetry_interval_sec": 2,
    "buffer_capacity": 1000
  },
  "change_summary": "High-rate sampling profile for prop vibration audit",
  "apply_immediately": true
}
```

---

### Executing Safe Remote Commands
Operators can issue non-RCE operational commands via:
```http
POST /api/v1/edge/devices/{device_id}/commands
Content-Type: application/json

{
  "command_type": "REQUEST_DIAGNOSTICS",
  "parameters": {"include_sensor_raw": false}
}
```
Supported commands:
- `REQUEST_HEARTBEAT`: Forces immediate heartbeat generation.
- `REQUEST_CONFIG`: Queries active edge runtime settings.
- `APPLY_CONFIG`: Pushes latest versioned settings.
- `RESTART_ACQUISITION`: Restarts acquisition loop and reinitializes sensor drivers.
- `REQUEST_DIAGNOSTICS`: Returns internal buffer, bus error counters, and packet stats.

---

### Emergency Revocation
To immediately cut off a lost, stolen, or decommissioned hardware node:
```http
POST /api/v1/edge/devices/{device_id}/revoke
Content-Type: application/json

{
  "reason": "Hardware node decommissioned during heavy maintenance phase"
}
```
Once revoked, all subsequent telemetry bursts, heartbeats, and commands from the device are refused (`HTTP 403 Forbidden`).
