# KOTA AEROSPACE — M18.5 INTELLIGENCE INTEGRATION GAP ANALYSIS
## Hardening the Boundary: NormalizedTelemetryEvent → HUMS → Diagnostics → Prognostics → M7 → LISA

---

### 1. What exactly enters the system from Tech Guy 1?
Tech Guy 1 delivers a JSON batch payload via `POST /api/v1/telemetry/ingest` conforming to `TelemetryIngestRequest`:
```json
{
  "events": [
    {
      "source_system": "KOTA_MAVLINK_GATEWAY",
      "source_event_id": "mavlink-sys1-1727610000000-a1b2c3",
      "source_asset_id": "UAV-KOTA-001",
      "event_type": "REALTIME_TELEMETRY",
      "event_timestamp": "2026-09-29T18:00:00Z",
      "flight": {
        "flight_number": "FLT-SYS1-1727610000",
        "duration_minutes": 15,
        "cycles": 1,
        "origin": "BASE_STATION",
        "destination": "MISSION_AREA",
        "flown_at": "2026-09-29T17:45:00Z",
        "notes": "Autopilot: ARDUPILOT | Mode: AUTO | Armed: True"
      },
      "battery": {
        "serial_number": "BAT-SYS-1",
        "cycle_count": 12,
        "voltage_v": 24.5,
        "temperature_c": 31.2,
        "health_percent": 98
      },
      "readings": [
        {
          "sensor_code": "VIB_MAIN_SYS1",
          "sensor_type": "VIBRATION",
          "measurement_type": "vibration",
          "value": 2.15,
          "unit": "mm/s",
          "component_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
          "data_quality": "VALID"
        }
      ],
      "raw_metadata": {
        "mavlink_system_id": 1,
        "lat": 37.7749,
        "lon": -122.4194,
        "altitude_m": 120.5,
        "groundspeed_mps": 14.2
      }
    }
  ]
}
```

---

### 2. What exact fields does Tech Guy 2 consume?
Tech Guy 2 consumes:
- **Routing & Idempotency:** `source_system`, `source_event_id`, `source_asset_id`, `event_timestamp`, `event_type`.
- **Flight Operations Domain:** `flight.flight_number`, `flight.duration_minutes`, `flight.cycles`, `flight.flown_at`, `flight.origin`, `flight.destination`, `flight.notes`.
- **Battery Management Domain:** `battery.serial_number`, `battery.cycle_count`, `battery.voltage_v`, `battery.temperature_c`, `battery.health_percent`.
- **HUMS Sensor Readings:** `readings[].sensor_code`, `readings[].sensor_type`, `readings[].measurement_type`, `readings[].value`, `readings[].unit`, `readings[].component_id`, `readings[].data_quality`.
- **Observability / Traceability:** `raw_metadata` (persisted into `TelemetryEventLog.metadata_payload`).

---

### 3. Which fields are mandatory?
- `source_system` (str, max 64)
- `source_event_id` (str, max 128)
- `source_asset_id` (str, max 128)
- `event_type` (str, max 64)
- `event_timestamp` (datetime, timezone-aware)
- `readings[].sensor_code` (str, max 64)
- `readings[].measurement_type` (str, max 64)
- `readings[].value` (float)
- `readings[].unit` (str, max 32)

---

### 4. Which fields are optional?
- `flight` (`TelemetryFlightPayload` | None)
- `battery` (`TelemetryBatteryPayload` | None)
- `readings` (list, default empty)
- `readings[].sensor_type` (default "TELEMETRY")
- `readings[].component_id` (UUID | None)
- `readings[].data_quality` (default "VALID")
- `raw_metadata` (dict, default empty)

---

### 5. Which fields are currently ignored?
- In `flight`: `pilot_user_id` is parsed if present, but for autonomous MAVLink telemetry, it is typically null unless mapped to a ground operator.
- In `battery`: `cell_voltages` array is logged in metadata but individual cell entities are aggregated into battery total voltage.
- In `readings`: Custom hardware vendor strings are preserved in `TelemetryEventLog.metadata_payload` rather than mutating the structured relational schema.

---

### 6. Which telemetry types reach HUMS?
Any reading contained in `readings[]` reaches `HUMSSensorReading`:
- Tri-axial and RMS vibration (`measurement_type="vibration"`, `unit="mm/s"`)
- Motor & ESC Temperatures (`measurement_type="temperature"`, `unit="celsius"`)
- Motor RPM (`measurement_type="rpm"`, `unit="rpm"`)
- Battery / Bus Voltages (`measurement_type="voltage"`, `unit="V"`)
- Electrical Currents (`measurement_type="current"`, `unit="A"`)
- Barometric / Pitot Pressure (`measurement_type="pressure"`, `unit="hPa"`)

---

### 7. Which telemetry types do not reach HUMS?
High-frequency raw spatial navigation kinematics (GPS raw latitude/longitude micro-steps, quaternions) are preserved in `TelemetryEventLog.metadata_payload` and `Flight` records, but do not create high-frequency time-series rows in `hums_sensor_readings` to avoid database bloat.

---

### 8. Which telemetry types can generate features?
Vibration telemetry (`measurement_type="vibration"`) and temperature telemetry (`measurement_type="temperature"`) generate time-domain statistical features:
- **RMS (Root Mean Square)**
- **Peak Acceleration**
- **Crest Factor**
- **Kurtosis (4th Central Moment)**
- **Mean & Standard Deviation**

---

### 9. Which telemetry types can generate findings?
Telemetry with exceedances against established statistical baselines ($> 3\sigma$ or defined absolute safety thresholds) automatically creates `Finding` records with `FindingSeverity` (CRITICAL / HIGH / MEDIUM / LOW) and attaches `Evidence` linking to the originating `TelemetryEventLog`.

---

### 10. Which telemetry types can generate diagnostics?
Vibration patterns matching registered fault signatures (e.g. `VIB-BRG-001` Bearing Degradation, `VIB-IMB-001` Rotor Imbalance) and thermal signatures (e.g. `TEMP-ESC-001` ESC Overheating) generate `HUMSDiagnosticCandidate` records.

---

### 11. Which telemetry types can generate prognostics/RUL?
Persistent trending features and diagnostic candidates feed `prognostic_service.py` and `degradation_engine.py` (exponential, polynomial, or linear degradation curves) to compute remaining flight hours until maintenance threshold.

---

### 12. Which telemetry types can trigger M7?
Active exceedances, diagnostic candidates, and maintenance threshold breaches trigger `proactive_intelligence_service.py` to emit `ProactiveSignalRecord` entries (e.g. `HUMS_VIBRATION_EXCEEDANCE`, `HUMS_DIAGNOSTIC_RISK`).

---

### 13. Which telemetry context is available to LISA?
LISA AI has full access to the persisted records via registered tools in `app/services/ai/tools.py`:
- `get_asset_telemetry_status`: Ingestion state, recent events, staleness.
- `get_asset_hums_health`: Baseline health, feature states.
- `get_asset_hums_diagnostics`: Active diagnostic hypotheses & supporting evidence.
- `get_asset_hums_prognostics`: RUL estimate, confidence, threshold trajectory.
- `get_asset_proactive_signals`: Active proactive early-warning signals.
- `get_digital_twin`: Unified 360° asset operational twin.

---

### 14. Where is telemetry dropped?
- Malformed JSON payloads missing required fields fail schema validation (HTTP 422).
- Telemetry from unauthenticated callers is rejected (HTTP 401).
- Unresolvable assets are **quarantined** in `telemetry_event_logs` with `status=QUARANTINED` rather than silently dropped.

---

### 15. Where can telemetry become silently unusable?
- If `data_quality="INVALID"` or `"STALE"`, the readings are stored in `hums_sensor_readings` but excluded from baseline calculation and feature trends to prevent corrupting analytics.
- If `sensor_code` is improperly mapped across flights, historical continuity is broken.

---

### 16. Where can asset/flight/component mapping fail?
- Asset resolution fails if `source_asset_id` has no matching `ExternalAssetMapping` and does not match `serial_number` or `registration` within the caller's tenant.
- Flight association fails if timestamp deviates from registered flights without flight context in the payload.

---

### 17. Where can timestamps fail?
- Naive datetime objects without UTC timezone info. (NormalizedTelemetryEvent enforces ISO 8601 with timezone).
- Timestamps in the far future ($> 1\text{ hour}$ ahead) are rejected.
- Delayed out-of-order packets: Handled by recorded timestamp ordering rather than receipt time.

---

### 18. Where can units fail?
If a connector emits non-standard units (e.g. raw $m/s^2$ without scaling vs $mm/s$ or $mV$ vs $V$), baseline thresholds become meaningless. Tech Guy 1's `MAVLinkConnector` explicitly normalizes to canonical SI units.

---

### 19. Where can data quality fail?
Telemetry with dropout flags, zero-variance flatlines, or sensor clipping can corrupt baseline statistics if not marked with `data_quality != "VALID"`.

---

### 20. Where can duplicate/out-of-order events cause problems?
Replayed events from store-and-forward buffers are deduplicated at ingestion by the unique key `(organization_id, source_system, source_event_id)`. Duplicates return status `DUPLICATE` and do not generate duplicate flights or exceedances.

---

### 21. Where can multi-UAV streams contaminate each other?
Contamination could occur if state is cached in shared memory without asset keying. In Kota, all state is strictly keyed by `(organization_id, asset_id)` in PostgreSQL.

---

### 22. Where can tenant isolation fail?
Tenant isolation is enforced at the API dependency layer (`CurrentUser.organization_id`). Queries never use caller-provided organization IDs.

---

### 23. What must be fixed before M19?
1. Formalize the unit contract matrix so physical UAV sensor calibrators adhere to strict SI units.
2. Verify that persistent disk-backed FIFO buffering is deployed on companion computers during physical installation.
3. Validate multi-stream concurrent ingestion performance under 10+ simultaneous aircraft.
