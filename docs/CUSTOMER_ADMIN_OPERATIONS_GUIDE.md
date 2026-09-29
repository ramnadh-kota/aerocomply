# KOTA Aerospace — Customer Administration & Operations Handbook

## 1. Getting Started: Customer Onboarding Workflow

When onboarding a new aerospace customer, the standard deployment workflow executes deterministically without code modifications:

1. **Tenant Provisioning**:
   - Create the `Organization` record via the Platform Control Plane or API.
   - Assign the appropriate commercial Plan and Entitlements.
2. **Initial Administrator Setup**:
   - Create the initial `ORG_ADMIN` user.
   - Configure local credentials or establish Microsoft Entra ID SSO integration.
3. **Fleet & Asset Hierarchy Setup**:
   - Register fixed-wing aircraft, helicopters, or commercial drones (`/api/v1/assets`).
   - Import historical operational baseline flight hours and cycles (`/api/v1/data-import`).
   - Register components, engines, and batteries.
4. **Telemetry & Sensor Configuration**:
   - Configure external device serial mappings (`/api/v1/telemetry/mappings`).
   - Configure telemetry freshness policies (`/api/v1/telemetry/freshness-policies`).
   - Register installed HUMS sensors (`/api/v1/hums/sensors`).
5. **Role Delegation**:
   - Invite CAMO Managers, Maintenance Engineers, Quality Managers, and Viewers.

---

## 2. Day-to-Day Operations

### 2.1 Flight Operations & Utilization
- Flights recorded via telemetry webhooks or manual entry update authoritative aircraft and component hours/cycles automatically.
- No parallel utilization calculations exist; historical baseline + valid flights calculate current totals.

### 2.2 Maintenance & Inspections
- Work orders track task-level progress and evidence gates.
- Required Inspection Items (RII) strictly enforce sign-off by an independent inspector who did not perform the task.

### 2.3 Proactive Aerospace Intelligence (M7)
- Early-warning signals alert managers to telemetry freshness decay, HUMS vibration exceedances, and airworthiness blockers before an AOG occurs.

### 2.4 Grounded LISA AI
- Operators interact with LISA to ask questions on work order readiness, fleet state, telemetry freshness, and compliance status.
- LISA provides grounded, evidence-cited answers without hallucinated facts.

### 2.5 Incident Management & Hypercare
- Real-time operational anomalies (P0–P3) can be logged, acknowledged, and resolved in the Hypercare Control Center.
