> **Implementation status (2026-09-30):** this document is a design/target description. The implemented behaviour is documented in `DATA_ACQUISITION_ARCHITECTURE.md`, `ENTITLEMENT_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `OBSERVABILITY_ARCHITECTURE.md`, `PRODUCTION_RUNBOOK.md` and `FINAL_RELEASE_READINESS.md`. Steps that touch payment, DNS/SSO or physical hardware are not automated or validated. Organization creation, plan/subscription assignment, data-source setup and asset mapping are implemented and covered by `test_customer_journey*.py`. Where this text disagrees with those, those win.

# KOTA AEROSPACE — CUSTOMER ONBOARDING OPERATING MODEL

## 1. Executive Journey Overview
Kota Aerospace provides a streamlined, suite-driven onboarding experience tailored specifically for commercial aerospace operators, UAV/drone service providers, helicopter charter operations, and eVTOL developers.

```text
  [ 1. User Registration ]
  Create Account (Email / Pass / SSO) ──> Verify Email
               │
               ▼
  [ 2. Organization Setup ]
  Create New Organization OR Accept Invite to Existing Organization
               │
               ▼
  [ 3. Suite Selection ]
  Select Operational Domain: [ Aircraft Suite | Drone Suite | Helicopter Suite | eVTOL Suite ]
               │
               ▼
  [ 4. Plan & Tier Selection ]
  Choose Tier: [ Starter | Professional | Enterprise ] (Monthly / Annual)
               │
               ▼
  [ 5. Subscription Activation ]
  Billing Setup / Trial Activation ──> Entitlements Instantly Evaluated & Provisioned
               │
               ▼
  [ 6. Workspace Configuration ]
  Invite Team Members ──> Assign RBAC Roles (Admin, Pilot, Mechanic, Safety Officer)
               │
               ▼
  [ 7. Data Ingestion & Integration ]
  Connect Live Feeds (MAVLink / MQTT / API) OR Import Batch Flight & MRO Logs
               │
               ▼
  [ 8. Asset Registration ]
  Register Aircraft / Drones / Batteries / Engines (Tail Number, Serial, Model)
               │
               ▼
  [ 9. Active Operations & Intelligence ]
  Live Telemetry ──> Automated HUMS ──> M7 Anomaly Detection ──> LISA Operations
```

---

## 2. Detailed Onboarding Workflows

### 2.1 Drone Fleet Customer Journey (e.g. Precision Ag, Inspection, Delivery)
1. **Suite & Plan**:
   - Customer selects **Drone Suite $\rightarrow$ Professional**.
   - Entitlements granted: `fleet_management`, `mavlink_ingestion`, `battery_lifecycle`, `hums_standard`, `m7_proactive_intel`, `lisa_assistant`.
2. **Data Integration**:
   - Operator creates API key for GCS (Mission Planner / QGroundControl / Auterion) or configures DJI Cloud API webhook.
3. **Asset Registration**:
   - Registers 5 drones (e.g., DJI Matrice 350 RTK, Freefly Astro) and 20 intelligent flight batteries.
4. **Flight & Operations**:
   - Pilot launches mission; real-time MAVLink telemetry streams to Kota platform.
   - Platform automatically segments flight into Takeoff, Survey Grid, Return-to-Home, and Landing.
   - Battery cycle count and voltage divergence are automatically updated.

### 2.2 Commercial Aircraft Customer Journey (e.g. Part 135 Charter / Part 121 Regional)
1. **Suite & Plan**:
   - Customer selects **Aircraft Suite $\rightarrow$ Enterprise**.
   - Entitlements granted: `aircraft_fleet`, `mro_suite`, `faa_easa_compliance`, `airworthiness_directives`, `hums_advanced`, `prognostics_rul`, `audit_reports`.
2. **Initial Data Import**:
   - Maintenance manager uploads historical airframe, engine, and APU logs via Batch CSV Import (`POST /api/v1/data-import/aircraft/validate`).
3. **Asset & Component Setup**:
   - Registers fleet (e.g., King Air 350i, Cessna Citation CJ4) with time-tracking (Total Time Airframe, Engine Cycles).
4. **Compliance & Maintenance**:
   - System cross-references tail numbers against FAA Airworthiness Directives (ADs) and scheduled 100-hour / annual inspections.

---

## 3. Multi-Suite Organizations
An enterprise organization can operate multiple suites simultaneously under a single tenant account:
- Example: An energy utility uses **Drone Suite (Professional)** for powerline inspections and **Helicopter Suite (Enterprise)** for heavy maintenance and executive transport.
- The organization holds two distinct subscriptions:
  - `Subscription 1`: Org X + Drone Suite + Professional
  - `Subscription 2`: Org X + Helicopter Suite + Enterprise
- Users seamlessly toggle between active suite contexts in the top navigation bar with dynamic entitlement switching.

## Background services and suites
Production needs two extra processes besides the API: `python -m app.worker --schedule` (queue, retries, retention, dunning) and, if you ingest MAVLink/MQTT over the network, `python -m app.listeners`. Enable the Aircraft, Drone, Helicopter or eVTOL suite on the organization's plan; features and navigation follow the plan. Retention is OFF by default. See `PRODUCTION_RUNBOOK.md`.
