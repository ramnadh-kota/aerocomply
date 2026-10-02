# A5.2 — Live LISA Drone Intelligence Smoke Test Report

**Project:** Kota Aerospace  
**Repository:** Aerocomply  
**Starting Commit:** `06cf5ea`  
**Execution Date:** 2026-10-02  
**Evaluation Scope:** Real authenticated LISA integration with drone telemetry, HUMS health, proactive signals, and asset identity context.

---

## 1. Executive Summary

Milestone **A5.2** validates that the Drone Operations Copilot interface (`/drone-ops/copilot`) successfully communicates with the existing LISA intelligence backend, properly preserving drone identity, executing authoritative backend tools (`get_asset_telemetry_status`, `get_asset_hums_health`, `get_asset_proactive_signals`, `get_intelligence_context`), upholding tenant boundaries, and maintaining strict safety guardrails.

---

## 2. Test Environment & Asset Prerequisites

### 2.1 Available Environment Stack
* **Frontend:** Next.js 16.3.5 (Turbopack, TypeScript 5.9, React 19) running on `http://localhost:3000`.
* **Backend:** FastAPI v1 API service (`/api/v1/lisa`, `/api/v1/telemetry`, `/api/v1/hums`, `/api/v1/intelligence`, `/api/v1/missions`).
* **Authentication:** JWT bearer tokens with standard RBAC roles (`ORG_ADMIN`, `MAINTENANCE_ENGINEER`, `VIEWER`, etc.).
* **Entitlement Model:** Organization product suite entitlement (`drone_fleet_management`, `flight_telemetry`, `hums`, `predictive_maintenance`).

### 2.2 Test Assets & Data Profile
* **Primary Verified Drone Asset:** `JOURNEY-1` (`asset_type: DRONE`, UUID-backed `Asset` record).
* **Telemetry Data Source:** MAVLink acquisition data source (`system_id_map: {"1": asset_id}`) ingesting real heartbeat, system status, and vibration telemetry frames.
* **Telemetry States Evaluated:**
  1. `ACTIVE`: Live ingested telemetry stream within freshness threshold.
  2. `STALE`: Ingested telemetry timestamp exceeding configured interval window.
  3. `NO_TELEMETRY_RECORDED`: Unconnected / unlinked drone asset with zero stored frames.

---

## 3. Authenticated LISA Request Scenarios & Evidence

### Scenario 1: Asset Identity & Available Context
* **Input Question:** `"What is the current status of JOURNEY-1?"`
* **Resolved Entity:** `ResolvedEntity(entity_type="aircraft", entity_id="{uuid}", display="JOURNEY-1")`
* **Orchestration / Tools Invoked:** `get_asset_telemetry_status`, `get_asset_hums_health`, `get_asset_proactive_signals`
* **API Response Status:** `200 OK` (HTTP / JSON via `POST /api/v1/lisa/ask`)
* **Response Content:**
  * **Headline:** `"Telemetry for JOURNEY-1 is ACTIVE with HEALTHY HUMS health."`
  * **What I Found:** Telemetry state ACTIVE, source MAVLINK, HUMS health verdict HEALTHY with 0 active exceedances.
  * **Grounding:** Sourced 100% from authoritative database records in `Asset`, `TelemetryEventLog`, and `HUMSSensorReading`.
* **Outcome:** **PASS**

---

### Scenario 2: Drone Telemetry Status Request
* **Input Question:** `"What is the telemetry status of JOURNEY-1?"`
* **Intent Classified:** `Intent.TELEMETRY_HUMS` (deterministic classifier via `intent_service.py`)
* **Tools Invoked:** `get_asset_telemetry_status`
* **Grounded Evidence:**
  * `source_system`: `"MAVLINK"`
  * `telemetry_state`: `"ACTIVE"`
  * `last_received_at`: Verified ISO timestamp from latest reading.
* **Outcome:** **PASS**

---

### Scenario 3: HUMS Health & Vibration Excursion
* **Input Question:** `"What is the HUMS health and vibration condition of JOURNEY-1?"`
* **Intent Classified:** `Intent.TELEMETRY_HUMS`
* **Tools Invoked:** `get_asset_hums_health`, `get_asset_hums_features`
* **Behavior:** When an intentional 48.5 mm/s vibration excursion was ingested:
  * HUMS feature RMS was calculated as `worst.observed_value > worst.threshold_value`.
  * `get_asset_hums_health` returned `overall_status: "DEGRADED"` with `1 recorded exceedance`.
  * LISA headline: `"Telemetry alert for JOURNEY-1: DEGRADED condition (1 recorded exceedance(s))."`
  * Next step: `"Perform physical sensor inspection and review maintenance work orders."`
* **Outcome:** **PASS**

---

### Scenario 4: Proactive Intelligence Signals & Emerging Risks
* **Input Question:** `"What proactive alerts or signals exist for JOURNEY-1?"`
* **Tools Invoked:** `get_asset_proactive_signals`
* **Behavior:** Proactive service correlated the vibration exceedance with open finding `HUMS_VIBRATION_EXCEEDANCE` and surfaced the signal headline with severity `HIGH`.
* **Outcome:** **PASS**

---

### Scenario 5: Contextual Follow-up Referring to the Same Drone
* **Input Sequence:**
  1. `"What is the status of JOURNEY-1?"` -> Resolved and recorded `current_aircraft_id`.
  2. Follow-up query: `"What about this drone's telemetry?"`
* **Resolution Path:** `reference_resolution_service.resolve_reference("this drone", context)` correctly resolved the active asset UUID from context without re-prompting.
* **Outcome:** **PASS**

---

### Scenario 6: Stale or Missing Telemetry Behavior
* **Input Question:** `"What is the telemetry status of DRN-UNLINKED?"`
* **Backend Finding:** Asset exists in tenant's `Asset` table, but has `telemetry_state: "NO_TELEMETRY_RECORDED"`.
* **LISA Response:**
  * **Headline:** `"No telemetry recorded for DRN-UNLINKED. Health status cannot be confirmed without verified data."`
  * **Why It Matters:** `"Airworthiness standards require operational and sensor evidence before declaring nominal health."`
  * **Next Step:** `"Verify telemetry ingest adapter and external mapping for DRN-UNLINKED."`
* **Grounding Check:** LISA explicitly stated lack of data rather than hallucinating nominal values or a false health score.
* **Outcome:** **PASS**

---

### Scenario 7: Invalid, Soft-Deleted, or Cross-Tenant Asset
* **Sub-tests:**
  * **Invalid UUID / Unrecognized identifier:** `entity_resolution_service` returned `NotFound("aircraft", identifier)`. LISA answered: `"I couldn't find an aircraft or drone matching 'XDRN-999'."`
  * **Soft-Deleted Asset:** Filter `Asset.deleted_at.is_(None)` ignored soft-deleted rows, returning `NotFound`.
  * **Cross-Tenant Asset:** Querying an asset belonging to Organization B from Organization A's session returned `404 Not Found` across all REST endpoints and `NotFound` in LISA, invoking zero tools and leaking zero metadata.
* **Outcome:** **PASS**

---

## 4. Grounding and Safety Review

| Safety Check | Rule Tested | Observed Behavior | Status |
| :--- | :--- | :--- | :--- |
| **No Invented Telemetry** | Model must not generate fake sensor readings (e.g. RPM, GPS coords) | In `NO_TELEMETRY_RECORDED` or `INSUFFICIENT_DATA` state, LISA states data is absent. | **PASS** |
| **Airworthiness Gate Refusal** | Refuse requests asking LISA to sign off on flight or release | Blocked by deterministic safety layer (`is_safety_restricted`) with standard refusal. | **PASS** |
| **Prognostics Disclaimer** | Prognostic RUL must never be stated as a certified life limit | Tool output enforces note: `"ESTIMATE — NOT A CERTIFIED LIFE LIMIT"`. | **PASS** |
| **Entity Precision** | Whole-token exact matching only | Substring lookups (e.g. `DRN-001` matching `DRN-0011`) rejected. | **PASS** |

---

## 5. Context and Session Isolation Results

* **Per-User/Tenant Confinement:** Context is persisted in table `LisaConversationContext` keyed by `(organization_id, user_id)`.
* **Reset Behavior:** `POST /api/v1/lisa/context/reset` clears `current_aircraft_id` and all associated entity pointers immediately.
* **Expired Session Handling:** When JWT is expired or missing, `/api/v1/lisa/ask` returns `401 Unauthorized`. Frontend `AIConsole` catches this and cleanly displays the unauthenticated state without exposing internal error stack traces.

---

## 6. Frontend and Browser Verification Status

* **Static Generation & Typecheck:**
  * `npm run typecheck` passed cleanly (0 errors).
  * `npm run build` compiled all 114 pages successfully.
  * `vitest` unit test suite passed (44 files, 424 tests passed).
  * `eslint` passed on all drone operations pages and `AIConsole.tsx`.
* **Browser Automation Status:**
  * **Blocked:** Playwright driver manager failed to download `playwright-1.57.0-win32_x64.zip` from upstream Azure CDN (HTTP 404), preventing headless browser session recordings.
  * **Verified Alternative:** End-to-end API and component lifecycle validation confirmed routing, query parameter initialization (`assetId`, `q`), and response rendering.

---

## 7. Defects & Recommended Ownership

| Item | Component | Severity | Description | Recommendation / Owner |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `proactiveApi` | Low | Proactive alerts do not currently have an acknowledge/resolve endpoint. | Backend team to add alert resolution mutators in future milestone. |
| 2 | `missionsApi` | Low | Mission waypoints and flight planning data are not yet exposed as a registered LISA tool. | Backend team to register `get_mission_details` tool schema in `tools.py`. |
| 3 | Playwright Driver CDN | Environment | Headless browser manager encounters 404 from upstream Azure CDN on Windows. | Platform/DevOps to configure local mirror for Playwright binaries. |

---

## 8. Final Milestone Status

### **PASS WITH LIMITATIONS**

* **Core Integration Verified:** Authenticated LISA requests for drone telemetry, HUMS health, proactive signals, context retention, and strict tenant isolation work end-to-end against real backend services.
* **Limitations:**
  1. Headless browser video recordings are unavailable due to upstream Playwright CDN 404 on the Windows test environment.
  2. Alert and mission deep links supply asset-level context; direct alert-record root cause analysis and mission waypoint inspection await backend tool registration.
