# KOTA AEROSPACE — M18.5 TELEMETRY CONTRACT MATRIX
## Canonical Telemetry Contract Validation & Downstream Mapping

### 1. Master Telemetry Field Contract Matrix

| Field | Produced By | Required? | Validated? | Persisted? | HUMS Used? | M7 Used? | LISA Used? | Downstream Purpose |
|---|---|---|---|---|---|---|---|---|
| `source_system` | Tech Guy 1 | **YES** | **YES** (Pydantic max 64) | **YES** (`telemetry_event_logs`) | Indirectly | Yes | Yes | Identifies origin gateway / protocol adapter |
| `source_event_id` | Tech Guy 1 | **YES** | **YES** (Pydantic max 128) | **YES** (`telemetry_event_logs`) | Indirectly | Yes | Yes | Idempotency key component & deduplication |
| `source_asset_id` | Tech Guy 1 | **YES** | **YES** (Pydantic max 128) | **YES** (`telemetry_event_logs`) | **YES** | **YES** | **YES** | External asset resolution to KOTA Asset UUID |
| `event_type` | Tech Guy 1 | **YES** | **YES** (Pydantic max 64) | **YES** (`telemetry_event_logs`) | Yes | Yes | Yes | Telemetry classification (e.g. REALTIME_TELEMETRY) |
| `event_timestamp` | Tech Guy 1 | **YES** | **YES** (ISO 8601 UTC) | **YES** (`telemetry_event_logs`) | **YES** | **YES** | **YES** | Time-series ordering & feature windowing |
| `flight.flight_number` | Tech Guy 1 | No | Yes (Pydantic string) | **YES** (`flights`) | Yes | Yes | Yes | Flight session identification |
| `flight.duration_minutes` | Tech Guy 1 | If flight present | Yes (gt=0) | **YES** (`flights`) | Yes | **YES** | **YES** | Asset utilization hours accumulation |
| `flight.cycles` | Tech Guy 1 | If flight present | Yes (ge=1) | **YES** (`flights`) | Yes | **YES** | **YES** | Asset cycle count accumulation |
| `flight.origin` | Tech Guy 1 | No | Yes (string) | **YES** (`flights`) | No | No | Yes | Operational context |
| `flight.destination` | Tech Guy 1 | No | Yes (string) | **YES** (`flights`) | No | No | Yes | Operational context |
| `flight.flown_at` | Tech Guy 1 | No | Yes (datetime) | **YES** (`flights`) | **YES** | **YES** | **YES** | Authoritative flight departure timestamp |
| `flight.notes` | Tech Guy 1 | No | Yes (string) | **YES** (`flights`) | No | No | Yes | Autopilot mode, armed state, mission details |
| `battery.serial_number` | Tech Guy 1 | If battery present | Yes (max 128) | **YES** (`batteries`) | **YES** | **YES** | **YES** | Battery entity resolution |
| `battery.cycle_count` | Tech Guy 1 | No | Yes (ge=0) | **YES** (`batteries`) | **YES** | **YES** | **YES** | Battery life tracking |
| `battery.voltage_v` | Tech Guy 1 | No | Yes (float) | **YES** (`batteries`) | **YES** | **YES** | **YES** | Electrical state of health |
| `battery.temperature_c` | Tech Guy 1 | No | Yes (float) | **YES** (`batteries`) | **YES** | **YES** | **YES** | Battery thermal management |
| `battery.health_percent` | Tech Guy 1 | No | Yes (0..100) | **YES** (`batteries`) | **YES** | **YES** | **YES** | State of Health (SOH) monitoring |
| `readings[].sensor_code` | Tech Guy 1 | **YES** | Yes (max 64) | **YES** (`hums_sensors`, `readings`) | **YES** | **YES** | **YES** | HUMS sensor identity & channel mapping |
| `readings[].sensor_type` | Tech Guy 1 | No (default TELEMETRY)| Yes (max 64) | **YES** (`hums_sensors`) | **YES** | **YES** | **YES** | Transducer category (VIBRATION, ACCELEROMETER) |
| `readings[].measurement_type`| Tech Guy 1 | **YES** | Yes (max 64) | **YES** (`hums_sensors`, `readings`) | **YES** | **YES** | **YES** | Physical dimension (vibration, temperature, rpm) |
| `readings[].value` | Tech Guy 1 | **YES** | Yes (float) | **YES** (`hums_sensor_readings`) | **YES** | **YES** | **YES** | Numerical measurement value |
| `readings[].unit` | Tech Guy 1 | **YES** | Yes (max 32) | **YES** (`hums_sensor_readings`) | **YES** | **YES** | **YES** | Canonical engineering unit (mm/s, celsius, V, A) |
| `readings[].component_id` | Tech Guy 1 | No | Yes (UUID) | **YES** (`hums_sensor_readings`) | **YES** | **YES** | **YES** | Component digital thread linkage |
| `readings[].data_quality` | Tech Guy 1 | No (default VALID) | Yes (max 32) | **YES** (`hums_sensor_readings`) | **YES** | **YES** | **YES** | Analytics filter (VALID, DEGRADED, INVALID) |
| `raw_metadata` | Tech Guy 1 | No | Yes (dict) | **YES** (`telemetry_event_logs`) | No | No | Yes | Full provenance, GPS coords, autopilot metadata |

---

### 2. Engineering Unit Standards

| Measurement Domain | MAVLink Native Format | NormalizedTelemetryEvent Unit | HUMS Target Unit | Validation Formula / Conversion |
|---|---|---|---|---|
| **Vibration (RMS/Peak)** | Raw tri-axial m/s² (0.001g) | `mm/s` or `m/s^2` | `mm/s` | $\text{RMS} = \sqrt{(v_x^2 + v_y^2 + v_z^2)/3}$ |
| **Temperature** | Centi-degrees Celsius ($0.01^\circ\text{C}$) | `celsius` | `celsius` | $T(^\circ\text{C}) = \text{raw} / 100.0$ |
| **Battery Voltage** | Millivolts (mV) | `V` | `V` | $V(\text{Volts}) = \text{raw} / 1000.0$ |
| **Battery Current** | Centi-amperes (cA) | `A` | `A` | $I(\text{Amperes}) = \text{raw} / 100.0$ |
| **Motor Velocity** | Revolutions per minute | `rpm` | `rpm` | Exact value passthrough |
| **Pressure** | Hectopascals / Millibars | `hPa` | `hPa` | Exact value passthrough |
| **GPS Position** | $10^{-7}\text{ degrees}$ | `deg` (in metadata) | `deg` (in metadata) | $\text{deg} = \text{raw} / 10^7$ |
| **GPS Altitude** | Millimeters (mm) | `m` (in metadata) | `m` (in metadata) | $\text{Alt}(\text{meters}) = \text{raw} / 1000.0$ |
