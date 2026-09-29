# M15 Physical Hardware Integration — Gap Analysis

## 1. Executive Summary
This gap analysis evaluates the existing KOTA Aerospace telemetry, edge, HUMS, and intelligence architecture to identify the precise technical extensions required for physical hardware integration (M15) while enforcing zero-rebuild and zero-duplication invariants.

---

## 2. Architectural Analysis & Capability Mapping

| Architecture Area | Existing Capability (M13/M14) | Missing Capability for M15 | Proposed Extension | Why Required | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Physical Sensor Interface** | Synthetic telemetry generator (`simulate_edge_telemetry.py`) | Modular physical sensor drivers (Vibration, Temperature, Pressure, Electrical) supporting serial/USB/I2C/SPI interfaces. | `PhysicalSensorAdapter` hierarchy with `VibrationSensorAdapter`, `TemperatureSensorAdapter`, `PressureSensorAdapter`, `ElectricalSensorAdapter`. | Required to acquire real physical signals from bench development hardware (accelerometers, RTDs, transducers). | TECH-2 / ANTIGRAVITY |
| **Physical Edge Acquisition & Buffer** | Direct API ingestion endpoint `POST /api/v1/edge-hardware/telemetry` | Edge acquisition loop, offline ring-buffer for network tolerance, auto-reconnect, and sensor disconnect detection. | `PhysicalEdgeAcquisitionEngine` / `PhysicalEdgeClient` with local queue and exponential backoff retry. | Physical edge devices must tolerate intermittent RF/network connectivity and hardware disconnects. | TECH-2 / ANTIGRAVITY |
| **Physical Boundary Data Quality** | Quality enum (`VALID`, `SUSPECT`, `OUT_OF_RANGE`, `STALE`, `INVALID`) in schemas | Physical boundary sanity validator (detects sampling jitter, sensor dropouts, out-of-range ADC clips). | `validate_physical_reading_quality()` at sensor ingestion edge. | Prevents corrupted or disconnected hardware signals from silently polluting downstream HUMS. | TECH-2 / ANTIGRAVITY |
| **Canonical Telemetry Envelope** | `DeviceTelemetryEnvelope` & `EdgeSensorMeasurement` in `app.schemas.edge_hardware` | Canonical normalization for multi-parameter physical sensors (`temp_c`, `pressure_bar`, `voltage_v`, `current_a`). | Enhance value extraction in `edge_hardware_service.py` to extract all physical measurement types seamlessly. | Ensures multi-sensor payloads flow into `HUMSSensorReading` with exact units. | TECH-2 / ANTIGRAVITY |
| **Physical-to-KOTA Traceability** | `TelemetryEventLog` with `idempotency_key` and `source_event_id` | End-to-end lineage helper linking Physical Sensor Serial -> Edge Device -> Event Log -> HUMS -> Finding -> Evidence -> M7. | `trace_telemetry_lineage()` service function in `edge_hardware_service.py`. | Guarantees forensic auditability for real-world sensor data. | TECH-2 / ANTIGRAVITY |
| **HUMS / Exceedance Processing** | `hums_service.detect_and_record_exceedances()` (H0–H5) | None (Fully functional) | REUSE as-is without modification. | Invariant: Do not rebuild or modify HUMS algorithms. | TECH-1 (Preserved) |
| **M7 Proactive Intelligence** | M7 signal generation upon HUMS exceedance / finding creation | None (Fully functional) | REUSE as-is without modification. | Invariant: Do not build parallel alert engines. | TECH-1 (Preserved) |
| **Grounded LISA** | LISA CAMO Copilot with `get_hums_health` and `get_asset_summary` tools | None (Fully functional) | REUSE as-is without modification. | Invariant: LISA reads authoritative grounded data. | TECH-1 (Preserved) |
| **Database Migrations** | Alembic HEAD `0059` with `edge_devices` table | None (Existing schema is sufficient) | Zero new migrations required. | Invariant: Target 0 new migrations unless objectively required. | TECH-2 / ANTIGRAVITY |

---

## 3. Scope Boundaries & Anti-Goals
1. **NO CUSTOM PCB / FLIGHT HARDWARE:** Bench validation only using commercial development hardware.
2. **NO NEW ENGINES:** Zero duplication of HUMS, M7, LISA, or Telemetry ingestion pipelines.
3. **NO DATABASE SCHEMA EXPANSION:** All hardware registration, telemetry envelopes, and logs map cleanly into existing tables (`edge_devices`, `telemetry_event_logs`, `hums_sensors`, `hums_sensor_readings`).
