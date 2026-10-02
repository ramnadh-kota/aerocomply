# KOTA AEROSPACE — DRONE OPERATIONS SIMULATION TEST SCENARIOS

**Specification:** 10 Deterministic Software-in-the-Loop (SITL) Test Scenarios  
**Validation Suite:** `backend/tests/unit/test_sitl_simulation_scenarios.py`  

---

## Scenario Catalog

### Scenario 1: Normal Flight and Movement
- **Input:** Sequence of `HEARTBEAT` (seq 1), `GPS_RAW_INT` (seq 2, 3D fix, 12 sats), `GLOBAL_POSITION_INT` (seq 3, lat 10.005, lon 77.005, alt 25m).
- **Expected Outcome:** `LiveStateEventV1` position updated to `lat=10.005`, `lon=77.005`, `alt_rel_m=25.0`, `gps_fix=3D`, `satellites=12`.
- **Status:** **VERIFIED (PASSED)**

### Scenario 2: Multiple Virtual Drones
- **Input:** Interleaved streams from virtual drone sysid 1 and sysid 2.
- **Expected Outcome:** Two distinct vehicle tracking states maintained concurrently in `MAVLinkConnector.vehicles`.
- **Status:** **VERIFIED (PASSED)**

### Scenario 3: GPS Fix Changes
- **Input:** Dynamic transitions: `0: NO_GPS` → `3: 3D` → `5: RTK_FLOAT` → `6: RTK_FIXED`.
- **Expected Outcome:** Fix quality accurately reflected; invalid coordinates suppressed when `NO_GPS`.
- **Status:** **VERIFIED (PASSED)**

### Scenario 4: Geofence Entry & Exit
- **Input:** Circular boundary (radius 200m). Virtual drone moves from center (dist = -200m) to exterior (dist = +50m).
- **Expected Outcome:** Signed distance calculation accurately flips from negative (interior) to positive (breach).
- **Status:** **VERIFIED (PASSED)**

### Scenario 5: Telemetry Staleness
- **Input:** Time progression after last packet: 0s → 15s → 75s.
- **Expected Outcome:** `compute_freshness` computes `FRESH` (0s), `STALE` (15s), `LOST` (75s).
- **Status:** **VERIFIED (PASSED)**

### Scenario 6: Telemetry Interruption & Recovery
- **Input:** Telemetry stream disconnect followed by reconnect with reset sequence counters (`seq=3`).
- **Expected Outcome:** Stream resets cleanly without packet rejection.
- **Status:** **VERIFIED (PASSED)**

### Scenario 7: Invalid Coordinates & Malformed Packets
- **Input:** Packet with corrupted X.25 CRC checksum.
- **Expected Outcome:** Packet dropped (`len(events) == 0`), `crc_errors` and `parse_errors` incremented.
- **Status:** **VERIFIED (PASSED)**

### Scenario 8: Delayed or Out-of-Order Messages
- **Input:** Packets arrive in order `seq=10` → `seq=11` → `seq=9` (delayed).
- **Expected Outcome:** Delayed packet (`seq=9`) dropped without corrupting newer battery/position state.
- **Status:** **VERIFIED (PASSED)**

### Scenario 9: Duplicate Telemetry Messages
- **Input:** Identical packet `seq=5` sent twice.
- **Expected Outcome:** First packet parsed; second packet dropped by deduplication filter (`duplicates == 1`).
- **Status:** **VERIFIED (PASSED)**

### Scenario 10: Tenant Isolation
- **Input:** Telemetry published under Organization A. Client for Organization B attempts stream replay.
- **Expected Outcome:** Organization A receives 1 event; Organization B receives 0 events.
- **Status:** **VERIFIED (PASSED)**
