# KOTA AEROSPACE — DRONE OPERATIONS SIMULATION SETUP GUIDE

**Objective:** Set up and run ArduPilot SITL / PX4 SITL and the MAVLink telemetry replay pipeline without physical hardware.  
**Classification:** OPERATIONAL RUNBOOK  

---

## 1. Prerequisites & Environment Setup

- **Python Environment:** Python 3.12 with `.venv` in `backend/`
- **Simulation Tools:**
  - Standard MAVLink generator / replay test suite (`backend/tests/unit/test_sitl_simulation_scenarios.py`)
  - Optional ArduPilot SITL binary (`sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550`)
- **Backend Host:** FastAPI gateway listening on port 8000.

---

## 2. Starting the Virtual Drone Simulation

### Method A: Automated In-Process SITL Scenario Suite
Execute the deterministic 10-scenario simulation harness:
```powershell
backend\.venv\Scripts\pytest.exe backend/tests/unit/test_sitl_simulation_scenarios.py -v
```

### Method B: External ArduPilot SITL UDP Stream
1. Launch virtual multirotor:
   ```bash
   sim_vehicle.py -v ArduCopter -f quad --out=udp:127.0.0.1:14550
   ```
2. Start backend MAVLink edge connector bound to UDP port 14550 with the designated test organization ID:
   ```python
   connector = MAVLinkConnector()
   connector.connect_udp("127.0.0.1", 14550)
   ```

---

## 3. Graceful Shutdown & Cleanup Procedure

1. **Stop Simulation:** Terminate SITL process (`Ctrl+C` or `taskkill`).
2. **Clear Broker Buffer:** The in-memory `LiveBroker` replay window automatically resets on process restart or tenant unsubscribe.
3. **Purge Test Organization Data:** Execute soft-delete or cleanup script against designated test organization UUID `00000000-0000-0000-0000-000000000099`.

---

## 4. Transition Guide: Replacing SITL with Real Drone Hardware

To swap the software simulator with physical drone hardware (e.g. Pixhawk 6X / Auterion / Microhard telemetry radio):
1. Configure drone telemetry companion port to forward MAVLink v2 telemetry packets over UDP/TCP to the edge gateway endpoint.
2. Register the physical asset serial number and registration under the production tenant organization in `/drones`.
3. Verify telemetry arrival on `/drone-ops/live-map` (badge shifts from `SIMULATED` to `LIVE_OPERATIONAL`).
