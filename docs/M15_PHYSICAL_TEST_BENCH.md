# M15 Physical Hardware Integration & Test Bench Specification

## 1. Executive Summary
This document defines the laboratory test bench setup, sensor interface specifications, edge gateway configuration, and repeatable test procedures for the **KOTA Aerospace M15 Physical Hardware Validation**.

---

## 2. Laboratory Hardware Bill of Materials (BOM)

| Subsystem | Component / Model | Interface / Protocol | Configuration / Range | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Edge Computer** | Raspberry Pi 4 Model B / Industrial DIN-Rail Edge Gateway (Ubuntu Core 22.04 LTS) | Gigabit Ethernet / Wi-Fi 802.11ac, USB 3.0, I2C, SPI | 4GB RAM, ARM Cortex-A72 @ 1.5GHz | Runs `PhysicalEdgeAcquisitionEngine` and buffering daemon |
| **Vibration Sensor** *(Priority 1)* | ADXL345 / IIS3DWB 3-Axis Digital Accelerometer (MEMS) | SPI / USB-FTDI Serial Bridge | $\pm 16\text{g}$, 1000 Hz sampling rate, 13-bit resolution | Measures motor / gearbox / bearing vibration signatures |
| **Temperature Sensor** *(Priority 2)* | PT100 RTD with MAX31865 Precision Amplifier / TMP117 | I2C (Address `0x48`) | $-40^\circ\text{C}$ to $+200^\circ\text{C}$, $\pm 0.1^\circ\text{C}$ accuracy | Monitors motor casing and bearing temperatures |
| **Pressure Sensor** *(Priority 3)* | Honeywell MIP / Keller 21Y Piezoresistive Transducer | SPI ADC (MCP3008) / 0–5V Analog | $0 - 350\text{ bar}$ Hydraulic / $0 - 10\text{ bar}$ Pneumatic | Monitors hydraulic brake and pneumatic line pressure |
| **Electrical Monitor** *(Priority 4)* | TI INA226 High-Side Power & Current Monitor | I2C (Address `0x40`) | $0 - 36\text{V}$, $0 - 50\text{A}$ Shunt ($0.002\,\Omega$) | Measures main avionics bus voltage, current draw, and power |

---

## 3. Physical Wiring & Pinout Map

```text
 Raspberry Pi 4 / Edge Gateway                    Sensor Breakout Board
┌─────────────────────────────────┐               ┌────────────────────────────────┐
│ Pin 1  (3.3V Power)             ├───────────────┤ VCC (ADXL345 / TMP117)         │
│ Pin 6  (GND)                    ├───────────────┤ GND                            │
│ Pin 3  (SDA / GPIO 2)           ├───────────────┤ SDA (I2C Bus 1)                │
│ Pin 5  (SCL / GPIO 3)           ├───────────────┤ SCL (I2C Bus 1)                │
│ Pin 19 (SPI0 MOSI / GPIO 10)    ├───────────────┤ MOSI (SPI ADC / Transducer)    │
│ Pin 21 (SPI0 MISO / GPIO 9)     ├───────────────┤ MISO                           │
│ Pin 23 (SPI0 SCLK / GPIO 11)    ├───────────────┤ SCLK                           │
│ Pin 24 (SPI0 CE0 / GPIO 8)      ├───────────────┤ CS                             │
└─────────────────────────────────┘               └────────────────────────────────┘
```

---

## 4. Software Architecture & Ingestion Flow

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     PHYSICAL LABORATORY BENCH                           │
│                                                                         │
│   [Vibration Sensor]   [Temp Sensor]   [Pressure Transducer]  [INA226]  │
└────────────────┬──────────────┬──────────────────┬───────────────┬──────┘
                 │              │                  │               │
                 ▼              ▼                  ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              PHYSICAL EDGE ACQUISITION DAEMON (M15)                     │
│                                                                         │
│  - VibrationSensorAdapter (RMS, Peak, Crest Factor, Kurtosis calculation)│
│  - TemperatureSensorAdapter (RTD / Thermocouple range check)            │
│  - PressureSensorAdapter (Hydraulic / Pneumatic validation)             │
│  - ElectricalSensorAdapter (Bus Voltage & Shunt Current)                │
│  - Local Offline Ring-Buffer (500 capacity FIFO)                        │
│  - HMAC-SHA256 Envelope Signing & Monotonic Sequence Numbering          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼ (TLS REST / POST /api/v1/edge/ingest)
┌─────────────────────────────────────────────────────────────────────────┐
│                    KOTA ENTERPRISE BACKEND                              │
│                                                                         │
│  - Edge Hardware Service (Device Heartbeat & Envelope Normalization)    │
│  - Core Telemetry Service (Idempotency & Event Logging)                 │
│  - HUMS Exceedance Engine (Threshold evaluation)                        │
│  - M7 Proactive Intelligence (Signal generation)                        │
│  - Grounded LISA CAMO Copilot (Audit & decision support)                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Standardized Laboratory Test Procedures

### Test 1 — Normal Vibration Acquisition
1. Connect ADXL345 accelerometer to motor test rig running at nominal 2400 RPM.
2. Verify sampling rate at 1000 Hz, window size 20 samples.
3. Confirm RMS is within normal bounds ($0.15\text{g} - 0.25\text{g}$).
4. Verify envelope dispatch to KOTA with `processing_status = PROCESSED`.

### Test 2 — Controlled Elevated Vibration Exceedance
1. Introduce controlled mechanical imbalance or test waveform generating $8.5\text{ mm/s}$ RMS vibration.
2. Verify that KOTA's HUMS exceedance engine detects critical threshold breach ($> 8.0\text{ mm/s}$).
3. Verify that finding and M7 proactive intelligence signal are generated and linked to the asset.

### Test 3 — Sensor Disconnection Detection
1. Disconnect physical sensor I2C/SPI jumper wire during active sampling loop.
2. Confirm adapter detects hardware I/O fault, sets `quality = INVALID`, and logs zero fabricated data.

### Test 4 — Network Interruption & Buffer Replay
1. Disable edge network interface (`sudo ip link set eth0 down`).
2. Run 10 sampling cycles. Verify envelopes are buffered in local FIFO queue (`BUFFERED_OFFLINE`).
3. Re-enable network interface (`sudo ip link set eth0 up`).
4. Trigger `reconnect_and_flush()`. Verify all 10 envelopes are processed in exact sequence without duplication.

### Test 5 — Device Restart & Recovery
1. Restart the edge gateway process.
2. Verify device reconnects, sends updated heartbeat, and resumes telemetry ingestion with correct asset mapping.

---

## 6. Tenant Safety & Traceability Invariants
1. **Zero Cross-Tenant Leakage:** Device serial numbers are strictly bound to `organization_id`.
2. **End-to-End Audit Lineage:** Any reading can be queried via `GET /api/v1/edge/lineage/{source_event_id}` returning the complete chain from raw device timestamp down to M7 signals.
