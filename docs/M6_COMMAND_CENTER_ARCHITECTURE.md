# KOTA AEROSPACE — M6 OPERATIONAL COMMAND CENTER ARCHITECTURE

## Overview

The M6 Operational Command Center is the operational nerve center for KOTA Aerospace. It connects live telemetry, flight records, maintenance execution, regulatory compliance, component tracking, and deterministic AI intelligence into a single coherent interface for aerospace fleet operators.

---

## 1. Domain Layer & Service Integration

### 1.1 Summary Aggregation (`ControlCenterService.get_summary`)
- **Fleet Health Computation**: Aggregates operational status across `Aircraft` and `Drone` tables scoped to the caller's tenant (`organization_id`). Handles 6 standardized states: `READY`, `RESTRICTED`, `MAINTENANCE_DUE`, `GROUNDED`, `AWAITING_PARTS`, `UNKNOWN`.
- **Operational Activity Tracking**: Computes flights conducted today (`flight_date == today`), flights in the past 7 days, active missions in progress, and total flight hours / cycles derived by summing verified flight records with `AssetHistoricalBaseline` records.
- **Attention Queue Resolution**: Surfaces P0–P3 prioritized actionable items directly from:
  - Open and in-progress `Finding` records with critical/major severity.
  - Overdue or emergency `WorkOrder` records.
  - Overdue `InspectionRequirement` records.
  - `Battery` records with low health percentage or excessive cycle wear.
- **Daily Operational Brief**: Generates grounded operational briefings based on live tenant data without hardcoding or hallucinated figures.

### 1.2 Multi-Asset Fleet Operations (`ControlCenterService.get_fleet_operations`)
- Unifies both fixed-wing aircraft and unmanned drone fleets into a single high-density operational grid (`ControlCenterFleetOperationRow`).
- Calculates readiness status in strict alignment with Developer 2.1 / 2.2 Kleene 3-valued logic (Invariant #23: unknown compliance obligations resolve to `UNKNOWN_INTEL` / `UNKNOWN`, never defaulting to ready).
- Computes active blockers count and next actionable maintenance or compliance task.

### 1.3 Unified Chronological Operational Timeline (`ControlCenterService.get_fleet_timeline`)
- Merges events across seven domains:
  1. `FLIGHT`: Individual sorties, block times, departure/arrival ICAO codes, and flight hours.
  2. `MISSION`: Multi-stage operational deployments, target objectives, and statuses.
  3. `MAINTENANCE`: Work order creations, releases, technician assignments, and completions.
  4. `INSPECTION`: Inspection intervals due, checks completed, and sign-offs.
  5. `FINDING`: Discrepancies, structural defects, bird strikes, hydraulic leaks logged.
  6. `COMPONENT`: Part installations, removals, time-since-overhaul (TSO) resets.
  7. `BASELINE`: Historical import and opening baseline adjustments from legacy systems.

---

## 2. Multi-Tenant Security & RBAC Isolation

1. **Tenant Isolation**: Every database query in `ControlCenterService` strictly filters by `organization_id`. Cross-tenant data leakage is structurally impossible at the repository layer.
2. **Role-Based Access Control (RBAC)**:
   - Command Center Endpoints require valid JWT credentials.
   - Summaries and Fleet views require `AIRCRAFT_READ` or `DRONE_READ` permissions.
   - Operational Timelines require `AIRCRAFT_READ` and `COMPLIANCE_ASSESS` permissions.

---

## 3. UI/UX Architecture

- **Path**: `frontend/app/(app)/dashboard/page.tsx`
- **Design Language**: Dark-mode aerospace command console with dense typography, subtle micro-interactions, responsive grid layouts, and color-coded status badges (`READY`: Emerald, `RESTRICTED`: Amber, `GROUNDED`/`CRITICAL`: Rose, `UNKNOWN`: Slate).
- **Zero Decorative Placeholders**: All cards, charts, lists, and activity counters are bound to live backend contracts (`/api/v1/control-center/*`).
