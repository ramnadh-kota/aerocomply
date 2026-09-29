# KOTA AEROSPACE — MAVLINK PHYSICAL HARDWARE VALIDATION PLAN

## 1. Scope & Objective
This document outlines the mandatory **Physical Hardware Bench Validation Protocol** for verifying MAVLink v1/v2 telemetry ingestion, RF modem resilience, multi-drone stream multiplexing, and fail-safe routing under real-world physical and electromagnetic conditions.

> **Status Notice**: The software logic, CRC extra seed calculation, framing decoders, and router abstractions have passed 100% automated software unit and integration testing. **Physical radio bench testing requires physical laboratory hardware and remains marked as `PENDING PHYSICAL BENCH EXECUTION`.**

---

## 2. Test Setup & Equipment Requirements

### Required Laboratory Hardware:
- **Flight Controllers**:
  - $2\times$ Cube Orange+ / Pixhawk 6X (running ArduPilot / PX4)
  - $1\times$ Holybro Pixhawk 6C
- **Telemetry Radios**:
  - $4\times$ Holybro SiK Telemetry Radio V3 (915MHz / 433MHz)
  - $2\times$ RFD900x Ultra Long Range Modems
- **Serial & Network Interfaces**:
  - $2\times$ FTDI USB-to-UART Serial Adapters
  - $1\times$ Ethernet Edge Gateway running `mavlink-router` or Kota Ingestion Agent
- **RF Attenuator / Shielding Box** (for simulated packet loss & signal degradation).

---

## 3. Physical Test Matrix (12 Mandatory Bench Tests)

| Test ID | Test Name | Procedure & Stimulus | Pass Criteria | Validation Status |
|---|---|---|---|---|
| **TEST-01** | **Single Drone Telemetry** | Stream MAVLink v2 over 915MHz radio at 10Hz for 30 minutes from Pixhawk 6X (SysID 1, CompID 1). | 100% packets parsed; zero crashes; coordinates match physical GPS fixture. | `PENDING PHYSICAL HARDWARE` |
| **TEST-02** | **Multi-Drone Multiplexing** | Stream simultaneous telemetry from 3 physical flight controllers (SysIDs 1, 2, 3) through single RF gateway. | Telemetry correctly routed to 3 distinct asset UUIDs without cross-talk. | `PENDING PHYSICAL HARDWARE` |
| **TEST-03** | **Packet Loss Resilience** | Insert variable RF attenuation (10dB to 40dB) to induce 20% to 50% physical packet drops. | System maintains vehicle online state without crashing; packet loss % accurately logged. | `PENDING PHYSICAL HARDWARE` |
| **TEST-04** | **Duplicate Packet Handling** | Inject duplicate MAVLink frames over serial splitter. | Sliding sequence cache drops duplicates; zero distorted timeseries spikes. | `PENDING PHYSICAL HARDWARE` |
| **TEST-05** | **Out-of-Order Delivery** | Transmit packets with re-ordered sequence numbers across parallel radio links. | Packets re-ordered by timestamp or filtered safely. | `PENDING PHYSICAL HARDWARE` |
| **TEST-06** | **System ID Collision** | Connect two physical flight controllers configured with identical SysID (1) on distinct tenant API keys. | Tenant isolation strictly separates assets by authenticated Organization ID. | `PENDING PHYSICAL HARDWARE` |
| **TEST-07** | **Component ID Segregation** | Transmit simultaneous telemetry from Flight Controller (CompID 1) and Gimbal/Payload (CompID 154). | Messages parsed into distinct telemetry fields (Attitude vs Gimbal Pitch). | `PENDING PHYSICAL HARDWARE` |
| **TEST-08** | **Radio Disconnect & Reconnect** | Unplug physical USB radio during active 20Hz stream; reconnect after 60 seconds. | Ingestion recovers cleanly within 1.0s of reconnect; flight session resumes or closes cleanly. | `PENDING PHYSICAL HARDWARE` |
| **TEST-09** | **Temporary Link Outage** | Shield antenna with RF blanket for 15 seconds. | Heartbeat watchdog triggers `LINK_LOST`; resumes `ACTIVE` upon signal restoration. | `PENDING PHYSICAL HARDWARE` |
| **TEST-10** | **High-Frequency Stress Test** | Configure stream rates to 50Hz for `ATTITUDE` and `VIBRATION` across 4 vehicles. | Ingestion latency remains $< 35\text{ms}$; 0 dropped packets in local queue buffer. | `PENDING PHYSICAL HARDWARE` |
| **TEST-11** | **Long-Duration Endurance** | Continuous 12-hour telemetry stream from bench simulator. | Zero memory leak in Python ingestion daemon; database connection pool healthy. | `PENDING PHYSICAL HARDWARE` |
| **TEST-12** | **End-to-End Pipeline Validation** | Inject high vibration payload from physical shaker table $\rightarrow$ MAVLink $\rightarrow$ Kota $\rightarrow$ HUMS $\rightarrow$ M7 $\rightarrow$ LISA. | Vibration exceedance triggers M7 anomaly signal; LISA explains fault with exact timestamp evidence. | `PENDING PHYSICAL HARDWARE` |

---

## 4. Bench Execution Protocol & Sign-off

When laboratory hardware becomes available:
1. Connect physical modems and verify baud rates (57600 / 115200 bps).
2. Execute automated test script: `python scripts/hardware_bench_mavlink.py --port /dev/ttyUSB0 --baud 57600`.
3. Capture test log artifacts in `bench_logs/` and update sign-off status column.
