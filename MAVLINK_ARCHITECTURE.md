# KOTA AEROSPACE — MAVLINK PROTOCOL & INGESTION ARCHITECTURE

## 1. Scope & Protocol Compliance
The MAVLink ingestion subsystem implements strict MAVLink v1 and v2 protocol handling for UAV fleets operating under ArduPilot, PX4, and custom MAVLink microservices.

### Key Protocol Standards
- **MAVLink v2 Packet Structure**:
  - `STX` (0xFD)
  - `LEN` (payload length: 0–255)
  - `INCOMP_FLAGS` / `COMP_FLAGS` (incompatibility/compatibility flags)
  - `SEQ` (packet sequence 0–255)
  - `SYS_ID` (1–255)
  - `COMP_ID` (1–255)
  - `MSG_ID` (24-bit message identifier)
  - `PAYLOAD` (variable length)
  - `CHECKSUM` (16-bit ITU X.25 / CRC-16-MCRF4XX with seed byte `CRC_EXTRA`)
  - `SIGNATURE` (optional 13-byte link security signature)

---

## 2. Ingestion & Vehicle Routing Architecture

```text
  [ Physical Drones / GCS Radios ]
  ├── Drone 1: SysID 1, CompID 1 (Flight Controller)
  ├── Drone 2: SysID 2, CompID 1 (Flight Controller)
  └── Drone 3: SysID 3, CompID 154 (Payload Gimbal)
               │ (RF 915MHz / 433MHz / UDP / TCP)
               ▼
   [ Gateway / Serial Listener ]
               │
               ▼
   [ MAVLink Packet Parser ]
     ├── Magic byte validation (0xFD / 0xFE)
     ├── CRC calculation with CRC_EXTRA table
     └── Truncation & Framing check
               │
               ▼
   [ Multi-Vehicle Router ]
     ├── Match (Organization_ID, SysID, CompID) -> Registered Asset UUID
     ├── Filter duplicate SEQ numbers per (SysID, CompID) stream
     └── Track connection session state & Heartbeat watchdog
               │
               ▼
   [ Message Decoders ]
     ├── #0   HEARTBEAT
     ├── #30  ATTITUDE
     ├── #33  GLOBAL_POSITION_INT
     ├── #74  VFR_HUD
     ├── #147 BATTERY_STATUS
     └── #241 VIBRATION
               │
               ▼
   [ Canonical Telemetry Event Builder ]
               │
               ▼
   [ Ingestion Dispatcher ] ──> TimescaleDB, HUMS Engine, M7 Intelligence
```

---

## 3. Supported Message Types & Field Mappings

| MAVLink Msg ID | Message Name | Target Telemetry Fields | Notes |
|---|---|---|---|
| **0** | `HEARTBEAT` | `system_status`, `flight_mode`, `base_mode`, `autopilot_type` | Maintains vehicle online state (1Hz expected). |
| **30** | `ATTITUDE` | `roll_deg`, `pitch_deg`, `yaw_deg`, `roll_rate_dps`, `pitch_rate_dps`, `yaw_rate_dps` | Converted from radians to degrees. |
| **33** | `GLOBAL_POSITION_INT` | `latitude`, `longitude`, `altitude_msl_m`, `altitude_relative_m`, `ground_speed_mps`, `heading_deg` | Scaled from 1e7 int coordinates. |
| **74** | `VFR_HUD` | `air_speed_mps`, `ground_speed_mps`, `heading_deg`, `throttle_pct`, `climb_rate_mps` | Core flight deck parameters. |
| **147** | `BATTERY_STATUS` | `battery_voltage_v`, `battery_current_a`, `battery_remaining_pct`, `battery_temperature_c` | Crucial for battery degradation tracking. |
| **241** | `VIBRATION` | `vibration_rms_g`, `accel_x_g`, `accel_y_g`, `accel_z_g`, `clipping_0`, `clipping_1`, `clipping_2` | Direct input into HUMS vibration analysis. |

---

## 4. Multi-Vehicle Routing & Tenant Isolation

1. **System ID & Component ID Mapping**:
   - Each customer organization registers drone hardware in their fleet management portal with a designated `mavlink_system_id` (or hardware serial number paired with dynamic SysID assignment).
   - Inbound packets must match an existing asset registered to the authenticated organization. Cross-tenant injection is strictly rejected at the router level.
2. **Packet Loss & Sequence Handling**:
   - The router tracks expected sequence numbers `(seq + 1) % 256`.
   - Gaps indicate packet loss: metrics are reported to `telemetry_packet_loss_rate`.
   - Packets arriving with older sequence numbers within a 10-packet window are flagged as duplicates and discarded to prevent distorted time-series metrics.
3. **Session Lifecycle & Heartbeat Watchdog**:
   - Vehicles emit `HEARTBEAT` at 1Hz.
   - If no heartbeat is received for `> 5.0 seconds`, asset state transitions to `DISCONNECTED / LOST_LINK`.
   - Flight records are automatically closed with end-of-mission summaries once landing is detected or link timeout persists past configured threshold.

---

## 5. Error Recovery & Reliability

- **Malformed Packets**: Discarded immediately without crashing the parser thread.
- **CRC Failures**: Increments `mavlink_crc_error_count` metric with source IP/port logged.
- **Burst Rate Limiting**: Token bucket rate limiter caps ingest to 50Hz per vehicle stream to protect downstream databases from unbounded serial flooding.
