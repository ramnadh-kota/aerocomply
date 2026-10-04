# Milestone M21 Hardware Validation Status Report
## Edge Gateway, Physical MAVLink & Telemetry Ingestion

**Project:** Kota Aerospace / AeroComply  
**Target Milestone:** M20 (Physical Edge Gateway & Hardware-in-the-Loop)  
**Date:** 2026-10-04  
**Status:** **BLOCKED (GATED ON PHYSICAL BENCH)**

---

## 1. Executive Summary

Milestone M20 requires validating the Kota Aerospace Edge Gateway hardware deployed on a physical compute module, physically connected to a flight controller via serial UART, communicating over cellular LTE to the cloud ingestion backend.

Because this development agent operates within a virtualized execution environment without physical hardware test bench connections, **Milestone M20 is formally marked BLOCKED**.

All software-side prerequisites, edge queue buffering, framing parsers, retry policies, SITL integration harnesses, and commissioning procedures have been fully built, tested, and validated in simulation (Phase 5 / M19.3, 4/4 passing tests).

---

## 2. Hardware Bench Requirements & Specifications

The physical commissioning requires the following hardware configuration:

| Component | Target Specification | Purpose |
|---|---|---|
| **Compute Module** | Raspberry Pi CM4 (4GB RAM, 32GB eMMC) or Jetson Orin Nano | Edge gateway host running Debian/Ubuntu Linux |
| **Flight Controller** | Pixhawk 6C / Cube Orange running ArduPilot Copter 4.5+ | Autopilot telemetry source |
| **Physical Serial Interface** | FTDI FT232R 3.3V UART to TELEM2 port (115200 baud) | MAVLink 2.0 packet transport |
| **Cellular Modem** | Quectel EC25-E / SIM7600G-H LTE CAT-4 with active SIM | Uplink connection to AeroComply cloud |
| **Power Supply** | Mean Well 12V 5A DC Bench Power Supply | Regulated bench power |

---

## 3. Commissioning Procedure Checklist

Once physical hardware is accessible, follow this commissioning protocol:

### Step 1: Gateway Provisioning
- [ ] Flash Edge Gateway base OS (Ubuntu 22.04 LTS aarch64).
- [ ] Clone repo or deploy `gateway/` package.
- [ ] Configure `gateway/config.yaml` with:
  ```yaml
  device_id: "KOTA-GW-BENCH-01"
  organization_id: "<demo-or-customer-org-uuid>"
  serial_port: "/dev/ttyUSB0"
  baud_rate: 115200
  cloud_endpoint: "https://aerocomply-backend-staging.onrender.com/api/v1/telemetry/events"
  api_key: "<provisioned-edge-token>"
  local_buffer_max_mb: 500
  ```
- [ ] Install systemd unit `kotagateway.service` and enable auto-start on boot.

### Step 2: Physical Serial & MAVLink Stream Validation
- [ ] Connect FTDI TX/RX/GND to Pixhawk TELEM2 port.
- [ ] Verify incoming MAVLink 2.0 heartbeat and `SYS_STATUS` packets using `mavproxy.py` or gateway logs.
- [ ] Validate checksum and framing parser under normal operation (>10 Hz message rate).

### Step 3: Network Disconnect & Buffer Retention Test
- [ ] Disconnect LTE modem or block external network interface.
- [ ] Verify that `gateway/local_queue.py` spools incoming telemetry messages to encrypted SQLite disk queue without dropping packets.
- [ ] Restore network connectivity.
- [ ] Confirm burst-draining of buffered messages to cloud ingestion endpoint in chronological order with original device timestamps preserved.

### Step 4: Downstream Intelligence Verification
- [ ] Verify cloud receives ingested physical packets and records them in `telemetry_event_logs` with `source_system="KOTA_GATEWAY"`.
- [ ] Confirm HUMS feature extraction computes vibration RMS and bearing temperature.
- [ ] Confirm M7 signals fire if threshold exceedances are induced on the bench.
- [ ] Confirm physical telemetry is flagged with `is_simulation=False` throughout the pipeline.

---

## 4. Current Test Evidence

- **SITL Simulation Harness:** Passed (4/4 tests in [`backend/tests/integration/test_m19_sitl_harness.py`](file:///C:/Users/ramna/Documents/Aerocomply/backend/tests/integration/test_m19_sitl_harness.py)).
- **Gateway Local Queue Unit Tests:** Passed.
- **MAVLink Ingestion Parser:** Passed with malformed message resilience.
