> **Implementation status (2026-09-30).** The sections below are a design narrative; this block is authoritative.
>
> | Capability | Status | Verification |
> |---|---|---|
> | Tool registry: **60 tools**, each with a required RBAC permission and feature; unknown tool = error | IMPLEMENTED | `test_lisa_tool_matrix` pins the inventory |
> | Per-call checks in order: permission → subscription state → suite → feature (comma list = any-of) | IMPLEMENTED | `ai/tools.py::_require_entitlement`; **multi-suite organizations** are matched on the suites they actually hold (a previous defect locked them out); `SUITE_ENTITLEMENT_REQUIRED` vs `forbidden` codes |
> | Tenant comes only from the authenticated user; no tool accepts an organization argument | IMPLEMENTED | inventory test + smuggled-org-id test |
> | Matrix over every tool: role without permission, no/cancelled subscription, plan without feature, wrong suite, hostile/malformed ids (clean error or empty result, never an unexpected exception) | IMPLEMENTED | 257 parametrised cases |
> | `list_fleet_assets`: airframes filtered to the families the organization is entitled to (helicopter and eVTOL orgs get their fleet through LISA) | IMPLEMENTED | `test_lisa_tool_matrix`, `test_customer_journey_airframes` |
> | Entity / reference resolution of drones, helicopters, eVTOL by name, id or serial | IMPLEMENTED | `test_lisa_asset_resolution`, `test_lisa_entity_resolution` |
> | Grounding: answers cite the tools actually run; no fabricated evidence | IMPLEMENTED | `test_lisa_grounded_intelligence`, journey tests |
> | Aircraft-table tools (`get_aircraft`, AOG, maintenance-due, control center…) only see `Aircraft` rows | IMPLEMENTED with that scope — helicopter/eVTOL/drone assets are reached through the asset-based tools |
> | Answer quality / model behaviour on real customer questions; the LLM provider itself | EXTERNAL VALIDATION REQUIRED | provider is configured per deployment; without it LISA reports "not configured" |
>
> Metrics: `kota_lisa_tool_duration_seconds`, `kota_lisa_tool_errors_total`; rate limited by the `lisa` policy (per user).
> Related: `ENTITLEMENT_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`.

# KOTA AEROSPACE — LISA (INTELLIGENT SAFETY & OPERATIONS ASSISTANT) ARCHITECTURE

## 1. Overview & Core Philosophy
**LISA** (Logistical & Intelligent Safety Assistant) is the authoritative conversational and operational reasoning interface for Kota Aerospace.

LISA operates under strict **grounded truth and fail-closed security guarantees**:
1. **Never Hallucinate Operational Reality**: All assertions regarding fleet status, maintenance schedules, HUMS telemetry, M7 signals, or compliance records must originate directly from verified backend database records.
2. **Multi-Tenant & Entitlement Bounded**: Every tool invocation evaluates the user's organization scope, RBAC permissions, and active subscription suite entitlements before returning data or taking action.
3. **Deterministic Tool Execution**: LLM reasoning is restricted to intent classification, argument extraction, tool orchestration, and natural language synthesis of verified data.

---

## 2. Tool Execution Architecture

```text
  [ User Query in Web / Mobile / API ]
                 │
                 ▼
   [ Authentication & Request Context ]
     ├── Authenticated User UUID
     ├── Current Active Organization UUID
     ├── User Role & Permissions (e.g. ORG_ADMIN, PILOT, MECHANIC)
     └── Resolved Suite & Plan Entitlements (e.g. DRONE_UAV -> ENTERPRISE)
                 │
                 ▼
     [ LISA Intent & Plan Generator ]
     ├── Selects candidate tools from 59 registered tools
     └── Matches query intent to required aerospace domain
                 │
                 ▼
     [ Tool Authorization Guardrail ]
     ├── Check 1: Tool Permission (_require_permission)
     ├── Check 2: Suite Entitlement (_require_entitlement)
     └── Check 3: Tenant Scope Filter (organization_id injection)
                 │
        ┌────────┴────────┐
        │                 │
    (Passed)           (Denied)
        │                 │
        ▼                 ▼
  [ Database Query /   [ Return Structured Error ]
    Domain Service ]   ("403 Forbidden: Entitlement required")
        │                 │
        └────────┬────────┘
                 │
                 ▼
     [ Grounded Response Synthesizer ]
     └── Formats verified facts with links to Assets, Flights, MRO, Reports
```

---

## 3. Tool Registry & Authorization Matrix (60 tools)

Every tool registered in `app/services/ai/tools.py` implements deterministic authorization:

| Tool Category | Example Tools | Required Permission | Required Entitlement | Scope |
|---|---|---|---|---|
| **Fleet & Assets** | `get_fleet_summary`, `get_asset_details`, `list_aircraft` | `fleet:read` | `fleet_management` | Organization scoped |
| **Telemetry & Live** | `get_latest_telemetry`, `get_telemetry_history` | `telemetry:read` | `telemetry_live` | Asset & Org scoped |
| **HUMS & Health** | `get_hums_overview`, `get_rul_prognostics`, `get_vibration_spectra` | `hums:read` | `hums_advanced` | Asset & Org scoped |
| **M7 Intelligence** | `get_m7_signals`, `get_anomaly_findings`, `explain_m7_alert` | `intelligence:read` | `m7_proactive_intel` | Org scoped |
| **MRO & Maintenance**| `get_work_orders`, `create_work_order`, `get_part_inventory` | `maintenance:read` / `write`| `mro_suite` | Org scoped |
| **Compliance & Audit**| `get_compliance_status`, `check_airworthiness_directives` | `compliance:read` | `compliance_engine` | Org scoped |
| **Reporting & Export**| `generate_fleet_report`, `export_telemetry_csv` | `reports:generate` | `advanced_reporting` | Org scoped |

---

## 4. Grounded Reasoning Workflow Examples

### Example 1: Operational Question — *"Which drones require urgent maintenance?"*
1. **LISA Orchestration**: Calls `get_m7_signals(severity="CRITICAL", category="DRONE")` and `get_open_work_orders(status="URGENT")`.
2. **Context Resolution**: Injects `organization_id` from request context.
3. **Database Fact Extraction**:
   - Drone `UAV-Bravo-04` has high motor vibration ($Z > 3.8$) and open Work Order `#WO-9021`.
   - Drone `UAV-Alpha-01` has battery capacity fade ($\text{SoH} = 74\% < 80\%$).
4. **Synthesis**:
   > *"2 drones in your fleet currently require urgent maintenance:*
   > *1. **UAV-Bravo-04**: Critical motor vibration exceedance on Arm 3. Work Order #WO-9021 is open.*
   > *2. **UAV-Alpha-01**: Battery SoH has degraded to 74% (below 80% threshold). Inspection required before next flight."*

---

## 5. Security & Isolation Assurances

1. **No Raw SQL Execution**: Tools utilize typed SQLAlchemy queries with parameterized filters.
2. **Strict Organization Isolation**: Every database query explicitly includes `filter(Model.organization_id == current_user.org_id)`.
3. **Audit Logging**: Every LISA prompt, selected tool, execution time, and authorization decision is recorded in `ai_tool_audit_log` for compliance verification.
