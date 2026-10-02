# KOTA AEROSPACE — DRONE OPERATIONS API CONTRACTS SPECIFICATION

**Document Version:** 1.0.0  
**Status:** APPROVED & IMPLEMENTED  
**Base Path:** `/api/v1`  
**Authentication:** HTTP Bearer Token (`Authorization: Bearer <jwt>`)  
**Tenant Enforcement:** Implicit through `CurrentUser.organization_id` extracted from validated JWT claims.

---

## 1. Drones & Fleet Inventory API

### `GET /api/v1/drones`
- **Description:** Retrieve all drone assets belonging to the authenticated user's organization.
- **Permission:** `aircraft:read` or `drone:read`
- **Query Parameters:**
  - `page` (optional, integer, default 1)
  - `page_size` (optional, integer, default 50)
  - `status` (optional, string: `ACTIVE`, `MAINTENANCE`, `GROUNDED`, `INACTIVE`)
- **Response Shape (200 OK):**
```json
{
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "organization_id": "8fa85f64-5717-4562-b3fc-2c963f66afa6",
      "asset_type": "DRONE",
      "model": "SkyRanger R70",
      "serial_number": "SR-70-9841",
      "registration": "DR-SKY-01",
      "status": "ACTIVE",
      "created_at": "2026-09-15T10:00:00Z",
      "updated_at": "2026-10-02T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50
}
```

### `GET /api/v1/drones/{id}`
- **Description:** Retrieve single drone asset by UUID.
- **Response Shape (200 OK):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "organization_id": "8fa85f64-5717-4562-b3fc-2c963f66afa6",
  "asset_type": "DRONE",
  "model": "SkyRanger R70",
  "serial_number": "SR-70-9841",
  "registration": "DR-SKY-01",
  "status": "ACTIVE",
  "battery_type": "LiPo 6S",
  "firmware_version": "v3.4.1-rc2",
  "operating_limits": {
    "max_altitude_m": 120,
    "max_speed_mps": 18.0,
    "max_wind_mps": 12.0
  }
}
```

---

## 2. Mission Operations API

### `GET /api/v1/missions`
- **Description:** List planned, authorized, or executed drone missions.
- **Response Shape (200 OK):**
```json
[
  {
    "id": "11111111-2222-3333-4444-555555555555",
    "organization_id": "8fa85f64-5717-4562-b3fc-2c963f66afa6",
    "asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "purpose": "Perimeter Surveillance Sector 4",
    "operating_area": "Sector-4 North Grid",
    "status": "AUTHORIZED",
    "planned_start": "2026-10-02T14:00:00Z",
    "planned_end": "2026-10-02T15:30:00Z",
    "pilot_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "authorized_at": "2026-10-02T13:45:00Z",
    "notes": "Pre-flight geofence verified"
  }
]
```

### `POST /api/v1/missions/{id}/authorize`
- **Description:** Formally authorize a planned mission for flight readiness.
- **Permission:** `drone:authorize`
- **Response Shape (200 OK):**
```json
{
  "id": "11111111-2222-3333-4444-555555555555",
  "status": "AUTHORIZED",
  "authorized_at": "2026-10-02T13:45:00Z",
  "authorized_by": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
}
```

---

## 3. Telemetry & Live State API

### `GET /api/v1/live/fleet`
- **Description:** Retrieve current real-time state for all active drones with GPS fix quality.
- **Response Shape (200 OK):**
```json
[
  {
    "asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "latitude": 37.7749,
    "longitude": -122.4194,
    "altitude_m": 45.2,
    "heading_deg": 184.0,
    "ground_speed_mps": 6.8,
    "battery_soc_pct": 78.5,
    "gps_fix_type": "3D_FIX",
    "satellites_visible": 14,
    "hdop": 0.9,
    "freshness_status": "LIVE",
    "last_telemetry_at": "2026-10-02T16:50:22Z",
    "is_simulated": false
  }
]
```

---

## 4. LISA Grounded Intelligence Tools Specification

### Tool: `get_alert_details`
- **Handler:** `_handle_get_alert_details`
- **Required Permission:** `Permission.AIRCRAFT_READ`
- **Required Feature:** `aircraft_fleet_management,drone_fleet_management`
- **Input Parameters:**
  - `alert_id` (string, required): Proactive signal UUID or signal key (e.g. `aog-xyz`, `shortage-123`).
- **Response Shape:**
```json
{
  "id": "99999999-8888-7777-6666-555555555555",
  "signal_key": "drone-battery-cell-imbalance-01",
  "headline": "Elevated Cell 4 Voltage Imbalance on DR-SKY-01",
  "severity": "WARNING",
  "contributing_factors": ["Cell 4 delta > 85mV during peak motor discharge"],
  "evidence_refs": ["telemetry-session-20261002-01"],
  "recommended_actions": ["Perform battery conditioning cycle before next flight release"]
}
```

### Tool: `get_mission_details`
- **Handler:** `_handle_get_mission_details`
- **Required Permission:** `Permission.DRONE_READ`
- **Required Feature:** `drone_fleet_management`
- **Input Parameters:**
  - `mission_id` (string, UUID, required): Mission UUID.
- **Response Shape:**
```json
{
  "id": "11111111-2222-3333-4444-555555555555",
  "asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "asset_registration": "DR-SKY-01",
  "status": "AUTHORIZED",
  "purpose": "Perimeter Surveillance Sector 4",
  "operating_area": "Sector-4 North Grid",
  "planned_start": "2026-10-02T14:00:00Z",
  "planned_end": "2026-10-02T15:30:00Z",
  "pilot_user_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  "pilot_name": "Capt. Sarah Connor",
  "authorized_at": "2026-10-02T13:45:00Z",
  "notes": "Pre-flight geofence verified",
  "execution_state": "PLANNED_OR_AUTHORIZED (flight not automatically executed without verified telemetry)"
}
```
