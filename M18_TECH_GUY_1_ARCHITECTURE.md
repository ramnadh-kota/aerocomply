# KOTA AEROSPACE — M18 TECH GUY 1 ARCHITECTURE SPECIFICATION
## UAV Data Acquisition, MAVLink Connectivity & Secure Cloud Uplink

### 1. Executive Overview & System Boundary
The Kota Aerospace UAV Data Acquisition Layer provides a hardware-independent, vendor-neutral software bridge connecting existing UAV flight controllers (ArduPilot / PX4 / Micro-Air Vehicles) to Kota Cloud.

```
+-------------------------------------------------------------------------+
|                              EDGE DOMAIN                                |
|                                                                         |
|  +--------------------+        +--------------------+                   |
|  | Existing UAV / FC  |  UDP / | Kota Edge Gateway  |                   |
|  | ArduPilot / PX4    |------->| MAVLink Connector  |                   |
|  | (SysID 1..255)     | Serial | Frame Parser & SI  |                   |
|  +--------------------+        +--------------------+                   |
|                                          |                              |
|                                          v                              |
|                                +--------------------+                   |
|                                | Local FIFO Buffer  | (Store-and-Fwd)   |
|                                | Dynamic Deque/Disk | Offline Queue     |
|                                +--------------------+                   |
|                                          |                              |
|                                          | Cellular / Wi-Fi / Satcom    |
+------------------------------------------|------------------------------+
                                           | HTTPS / TLS 1.3 (Bearer JWT)
                                           v
+-------------------------------------------------------------------------+
|                              CLOUD DOMAIN                               |
|                                                                         |
|  +-------------------------------------------------------------------+  |
|  | KOTA CLOUD INGESTION (POST /api/v1/telemetry/ingest)              |  |
|  | - Tenant Authentication & RBAC (DRONE_WRITE / ORG_ADMIN)          |  |
|  | - NormalizedTelemetryEvent Validation & SHA-256 Idempotency       |  |
|  | - External Asset Mapping Resolution                              |  |
|  +-------------------------------------------------------------------+  |
|                                  |                                      |
|                                  v                                      |
|  +-------------------------------------------------------------------+  |
|  | TECH GUY 2 DETERMINISTIC INTELLIGENCE PIPELINE                    |  |
|  |   HUMS Sensor Ingestion -> Feature Extraction (Time/Freq)         |  |
|  |   -> Baselines -> Exceedances -> Findings & Evidence Linkage     |  |
|  |   -> Diagnostics -> Prognostics/RUL -> M7 Signals -> LISA AI      |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

---

### 2. Core Architectural Components

#### 2.1 Connector Base Abstraction (`TelemetryConnector`)
- Abstract base class defining universal lifecycle: `connect(uri)`, `disconnect()`, `decode_message()`, `dispatch_event()`, `get_stats()`.
- Protocol-agnostic telemetry decoupling, enabling future connectors (e.g. MQTT, WebSocket, Direct REST, CoAP, DDS) without architectural redesign.

#### 2.2 MAVLink v1 / v2 Connector (`MAVLinkConnector`)
- Ingests raw binary frame streams (STX `0xFE` for v1, `0xFD` for v2) and parses standard frame headers.
- Decodes critical MAVLink message types:
  - `HEARTBEAT` (0): Flight mode, armed status, autopilot type, system status.
  - `SYS_STATUS` (1): Bus voltage (mV -> V), load, battery current (cA -> A), remaining capacity (%).
  - `GPS_RAW_INT` (24) & `GLOBAL_POSITION_INT` (33): Coordinates (degE7 -> deg), altitude (mm -> m), groundspeed (cm/s -> m/s), heading (cdeg -> deg).
  - `ATTITUDE` (30): Roll, pitch, yaw (rad -> deg).
  - `VFR_HUD` (74): Airspeed, groundspeed, throttle, altimeter, climb rate.
  - `BATTERY_STATUS` (147): Cell voltages (mV -> V), battery temperature (cdegC -> °C), current draw.
  - `VIBRATION` (241): Tri-axial vibration ($m/s^2$ / $mm/s$) and RMS composite calculation.
  - `ESC_STATUS` (291): Motor RPM, ESC temperature, ESC current/voltage.
- Maintains per-vehicle state (`MAVLinkVehicleState`) isolated by `system_id` (1..255).
- Automatically converts units to standard SI canonical representations and constructs `NormalizedTelemetryEvent`.

#### 2.3 Edge Telemetry Gateway (`KotaTelemetryGateway`)
- Autonomous daemon running on onboard companion computer (Jetson, RPi, CM4) or cellular ground router.
- Local FIFO buffering (`collections.deque` with configurable capacity, e.g. 5,000 events).
- Zero data loss during network disconnections (tunnels, remote flights, cellular dead zones).
- Reconnect and store-and-forward batch replay with exponential backoff retry.
- Periodic health heartbeat dispatches (`EdgeDeviceHeartbeatRequest`) reporting queue depth, uptime, sensor status, and event counters.

---

### 3. Canonical Contract Preservation (Tech Guy 2 Boundary)
The acquisition layer strictly emits the canonical `NormalizedTelemetryEvent` into `POST /api/v1/telemetry/ingest`:
- **Source Identification:** `source_system="KOTA_MAVLINK_GATEWAY"`, `source_event_id`, `source_asset_id`.
- **Flight Context:** `TelemetryFlightPayload` (flight number, duration, flown_at, autopilot notes).
- **Battery Context:** `TelemetryBatteryPayload` (serial number, cycle count, voltage, temperature, health %).
- **Readings Array:** `list[TelemetryReadingItem]` (sensor_code, sensor_type, measurement_type, value, unit, data_quality).
- **Raw Metadata:** Autopilot type, MAVLink sysid, flight modes, satellite fix status.

---

### 4. Security & Multi-Tenant Isolation
1. **Edge Identity:** Every gateway carries a unique hardware UUID (`gateway_id`) provisioned in Kota Platform.
2. **Tenant Scoping:** Gateway uplinks with scoped JWT Bearer tokens issued to the operating organization.
3. **Asset Resolution:** Telemetry asset IDs map deterministically via `ExternalAssetMapping` table within the caller's tenant. Cross-tenant spoofing is strictly prevented at the API gate.
4. **Idempotency & Replay Protection:** Ingestion pipeline calculates SHA-256 payload digests and enforces unique `(organization_id, source_system, source_event_id)` constraints. Replayed store-and-forward packets are safely deduplicated.
