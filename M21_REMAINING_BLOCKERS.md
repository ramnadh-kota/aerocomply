# Milestone M21 Remaining Blockers Register

**Project:** Kota Aerospace / AeroComply  
**Updated:** 2026-10-04  
**Author:** Antigravity (Master Technical Lead)  

This document tracks all external dependencies, unresolved blockers, and necessary manual gates that prevent full release or closure of physical hardware validation.

---

## 1. Active Hardware Blockers

### BLK-01: M20 Physical Hardware-in-the-Loop Bench Validation
- **Classification:** External Hardware Dependency
- **Affects:** Phase 9 / Milestone M20
- **Status:** **BLOCKED (GATED ON PHYSICAL BENCH)**
- **Description:** Physical telemetry validation requires edge gateway hardware deployed on a physical test bench. Software interfaces, framing parsers, local queues, retry logic, and provisioning scripts have been implemented and validated via SITL simulation (`test_m19_sitl_harness.py`). Physical execution cannot proceed in a pure virtual/containerized environment.
- **Specific Hardware Components Required:**
  1. Raspberry Pi Compute Module 4 (CM4) or NVIDIA Jetson Orin Nano
  2. Physical UART cable (FTDI 3.3V) connected to Pixhawk / ArduPilot TELEM2 port
  3. LTE Cellular Modem (Quectel EC25 / SIM7600) with provisioned SIM card
  4. 12V–24V DC aerospace power supply bench
- **Resolution Path:** Once the hardware bench is assembled at the Kota Aerospace test facility, execute the commissioning checklist documented in [`M21_HARDWARE_VALIDATION_STATUS.md`](file:///C:/Users/ramna/Documents/Aerocomply/M21_HARDWARE_VALIDATION_STATUS.md).

---

## 2. Operational & Deployment Gates (Non-Blockers for Code, Required for Staging/Prod Deployment)

### DEP-01: Staging Database Migration & Demo Seeding Execution
- **Classification:** Deployment Operation
- **Affects:** Staging Environment (`aerocomply-backend-staging.onrender.com`)
- **Status:** **READY FOR EXECUTION**
- **Description:** The M21 demo seeder script [`backend/scripts/seed_m21_demo_environment.py`](file:///C:/Users/ramna/Documents/Aerocomply/backend/scripts/seed_m21_demo_environment.py) has been validated locally on Postgres port 55432. To make the demo organization reviewable on staging by the project owner, this script must be executed against the staging database with the appropriate connection string.
- **Required Action:** Run `python backend/scripts/seed_m21_demo_environment.py --reset` against staging Render Postgres database.

### DEP-02: Production Code Freeze & Release Authorization
- **Classification:** Governance Gate
- **Affects:** Production Environment (`admin.kotaaerospace.com`, `aerocomply.vercel.app`)
- **Status:** **AWAITING PROJECT OWNER SIGN-OFF**
- **Description:** Per Non-Negotiable Architecture Rules, automated agents must never push directly to `origin/main` or deploy to production without explicit human authorization. All code is committed locally to branch `staging/m17-drone-ops-review`.

---

## 3. Cleared Blockers (Resolved During M21 Execution)

| ID | Issue | Resolution |
|---|---|---|
| **CLR-01** | H8.6 Consolidated Fleet API integration | Verified endpoints; all 17 integration scenarios passing. |
| **CLR-02** | H8.7 Predictive Maintenance human authorization | Built work order drafting workflow with Developer 1 contract integration. |
| **CLR-03** | H8.8 Unified Console frontend integration | Created 4-tab unified console with Next.js build verification. |
| **CLR-04** | Demo data isolation and reset safety | Created idempotent seeder with strict tenant boundary filtering. |
| **CLR-05** | M19.3 SITL Integration | Integrated SITL stream harness with 4/4 passing tests. |
| **CLR-06** | Aircraft 403 entitlement issue | Reconciled plan feature mappings and tenant feature overrides. |
