# Milestone M21 Demo Environment Guide
## Dedicated Demo Organization Setup, Administration & Reset

**Target Organization:** `Kota Aerospace Demo Operations`  
**Purpose:** Provides a realistic, fully populated review environment for the project owner and stakeholders without requiring physical hardware or live flight telemetry.  

---

## 1. Demo Organization Architecture

- **Organization Name:** `Kota Aerospace Demo Operations`
- **Tenant Scope:** Completely isolated tenant partition. Cannot query or modify other customer organizations; customer organizations cannot view demo data.
- **Enabled Feature Capabilities:**
  - `drone_fleet_management`
  - `aircraft_fleet_management`
  - `helicopter_fleet_management`
  - `evtol_fleet_management`
  - `flight_telemetry`
  - `hums`
  - `digital_twin`
  - `mro_intelligence`
  - `predictive_maintenance`
  - `work_order_management`
  - `battery_analytics`
  - `compliance_management`

---

## 2. Seeded Personas & Access Credentials

The demo environment provisions 3 distinct operational personas to demonstrate role-based access control (RBAC):

| Persona | Name | Email | Password | Assigned Roles | Recommended Workflows |
|---|---|---|---|---|---|
| **Demo Ops Director** | Sarah Jenkins | `demo.admin@kotaaerospace.com` | `DemoPassword2026!Kota` | `ORG_ADMIN`, `CAMO_MANAGER` | Fleet console, reviewing MRO candidates, authorizing work orders, LISA grounding, organization configuration. |
| **Lead MRO Engineer** | Marcus Vance | `demo.engineer@kotaaerospace.com` | `DemoPassword2026!Kota` | `MAINTENANCE_ENGINEER` | Work order inspection, component tracking, maintenance finding reviews, deferred item management. |
| **Flight Ops Lead** | Elena Rostova | `demo.pilot@kotaaerospace.com` | `DemoPassword2026!Kota` | `VIEWER` | Flight telemetry monitoring, mission status, fleet map, read-only operational telemetry. |

> [!NOTE]
> For production environments, default passwords should be rotated or accounts provisioned through enterprise SSO.

---

## 3. How to Seed the Demo Environment

### Local Development / Test Database
To seed the local database:
```bash
# Ensure local postgres container is running
python backend/scripts/seed_m21_demo_environment.py --reset
```

### Staging Environment Deployment
To seed the deployed staging environment:
```bash
# Set staging DATABASE_URL
$env:DATABASE_URL = "postgres://<staging_db_user>:<staging_db_pass>@<staging_db_host>/aerocomply_staging"
python backend/scripts/seed_m21_demo_environment.py --reset
```

### Safe Reset Mechanism
The seeder script includes a strict tenant-bounded `--reset` flag:
- It locates the tenant ID for `Kota Aerospace Demo Operations`.
- It deletes records belonging exclusively to that `organization_id` in foreign-key dependency order (AuditEvents, ComplianceObligations, WorkOrders, MROCandidates, ProactiveSignals, HUMSExceedances, HUMSSensors, TelemetryEvents, Missions, Components, Aircraft, Assets, Facilities, Users, Subscriptions).
- **Customer tenants are completely untouched.** A dedicated automated test (`test_m21_demo_reset_safety`) asserts this invariant.

---

## 4. Multi-Asset Fleet Inventory

The demo organization is pre-populated with 9 airframes across 4 aerospace domains:

| Registration / Serial | Asset Type | Airframe Model | Primary Operational Role | Operational Status | Scenario |
|---|---|---|---|---|---|
| `KOTA-DRN-01` | Drone (Hexacopter) | Kota HexaCargo-X6 | Heavy Logistics Delivery | `ACTIVE` (Healthy) | **Scenario A** |
| `KOTA-DRN-02` | Drone (Quadcopter) | Kota SurveyPro-Q4 | Precision Survey & Inspection | `ACTIVE` (Elevated Vibration) | **Scenario B & C** |
| `KOTA-DRN-03` | Drone (Quadcopter) | Kota SurveyPro-Q4 | Aerial Mapping | `ACTIVE` (Vibration Cluster) | **Scenario C** |
| `KOTA-DRN-04` | Drone (Fixed-Wing Hybrid) | Kota MediFly-V2 | Medical Supplies Transport | `ACTIVE` (Stale Telemetry) | **Scenario E** |
| `KOTA-DRN-05` | Drone (Octocopter) | Kota PatrolSentinel-8 | Offshore Facility Patrol | `MAINTENANCE` (Thermal Runaway) | **Scenario F** |
| `N701KA` | Fixed-Wing Aircraft | Cessna 208B Grand Caravan | Regional Passenger & Cargo | `ACTIVE` (Scheduled 100hr) | Baseline |
| `N702KA` | Fixed-Wing Aircraft | Beechcraft King Air 350 | Corporate Charter | `RESTRICTED` (Avionics Conflict) | **Scenario D** |
| `N901KA` | Rotorcraft / Helicopter | Bell 407GXi | Aerial Utility & Survey | `ACTIVE` (Serviceable) | Baseline |
| `EV-01KA` | eVTOL / AAM | Kota AeroShuttle eVTOL-6 | Urban Air Mobility Demonstrator | `STANDBY` (Battery 92%) | Baseline |
