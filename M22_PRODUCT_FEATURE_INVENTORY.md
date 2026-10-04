# KOTA AEROSPACE — M22 CANONICAL PRODUCT FEATURE INVENTORY
**Milestone:** M22 — Unified Product Readiness & End-to-End System Integrity  
**Date:** October 2026  
**Status:** Audit & Implementation Baseline  
**Product Direction:** Drone-first, with segregated Aircraft, Helicopter, and eVTOL capabilities built on a common aerospace foundation.

---

## 1. Executive Summary & Inventory Classification Standard

Each significant functional capability across the Kota Aerospace platform is classified into one of the following statuses based on verified code inspection, runtime test evidence, and architectural integrity:

- **COMPLETE**: Implemented, end-to-end integrated, and verified by passing test suites.
- **COMPLETE WITH LIMITATIONS**: Functional end-to-end with documented operational restrictions (e.g. simulated SITL telemetry in lieu of physical hardware).
- **PARTIAL**: Substantial implementation exists, but user workflow or tenant separation requires specific repairs or extensions.
- **BROKEN**: Implementation exists, but expected runtime behavior fails or breaks data contracts.
- **MISSING**: Required product capability does not exist in the codebase.
- **BLOCKED**: Requires unavailable physical avionics hardware, external regulatory authority APIs, or explicit external approval.
- **NOT VERIFIED**: Evidence is insufficient to confirm operational readiness.

---

## 2. Canonical Module Inventory (Modules 1–25)

### 1. Platform Admin
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/platform/dashboard` (`components/platform/PlatformDashboard`)
  - `/platform/organizations` (`components/platform/OrganizationsManagement`)
  - `/platform/plans` (`components/platform/PlanManagement`)
  - `/platform/product-catalog` (`components/platform/ProductCatalogManagement`)
  - `/platform/subscriptions` (`components/platform/SubscriptionManagement`)
  - `/platform/usage` (`components/platform/PlatformUsageView`)
  - `/platform/audit` (`components/platform/PlatformAuditTrail`)
  - Protected by `PLATFORM_NAV_GROUPS` and `isPlatformRole` in `components/layout/Sidebar.tsx` and `RouteEntitlementGuard.tsx`.
- **Backend Routes & Services:**
  - `backend/app/api/v1/platform.py` (prefix `/api/v1/platform`)
  - `backend/app/services/platform_service.py`
  - Gated by `Permission.PLATFORM_MANAGE`.
- **Database Entities:** `ProductSuite`, `ProductModule`, `ProductPage`, `ProductFeature`, `Plan`, `PlanFeature`, `PlanLimit`, `Subscription`, `Organization`, `AuditEvent`.
- **Authorization & Entitlement:** Platform Admin / Platform Staff roles exclusively. Zero tenant operational permissions.
- **Dependencies:** Core DB session, Auth service, Entitlement service, Audit logger.
- **Existing Tests:** `tests/unit/test_platform_admin_security.py`, `tests/integration/test_customer_journey_platform_e2e.py`, `tests/integration/test_platform_control_plane.py`.
- **Known Defects / Gaps:** Billing metrics are synthetic/unconnected to real Stripe/banking webhooks (displayed truthfully as mock/preview).
- **Priority:** P1

---

### 2. Authentication and Authorization
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/login` (`components/auth/LoginForm.tsx`)
  - `/forgot-password`, `/reset-password`
  - `frontend/lib/auth/SessionContext.tsx`, `frontend/components/auth/AuthGuard.tsx`
  - Automated single-flight token refresh across browser tabs (`aerocomply_token_refreshed`).
- **Backend Routes & Services:**
  - `backend/app/api/v1/auth.py` (`POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`, `PATCH /auth/me`)
  - `backend/app/services/auth_service.py`
  - `backend/app/core/security.py`, `backend/app/core/permissions.py` (granular RBAC: `Permission.*`).
- **Database Entities:** `User`, `UserRole`, `Organization`.
- **Authorization & Entitlement:** JWT access tokens (short-lived, 15m) + refresh tokens (stored hashed with expiry).
- **Dependencies:** PostgreSQL, bcrypt password hashing.
- **Existing Tests:** `tests/integration/test_auth.py`, `tests/integration/test_m20_commercial_entitlement_lifecycle.py`.
- **Known Defects / Gaps:** None in core authentication. Token rotation and concurrency-safe single-flight refresh are verified.
- **Priority:** P0

---

### 3. Organization Management
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/tenant/profile`, `/tenant/dashboard`, `/tenant/settings`, `/tenant/users`, `/tenant/roles`
  - `components/organization/*`, `components/tenant/*`
- **Backend Routes & Services:**
  - `backend/app/api/v1/tenant.py` (`/api/v1/tenant/*`)
  - `backend/app/services/tenant_service.py`
- **Database Entities:** `Organization`, `User`, `UserRole`, `TenantRetentionPolicy`.
- **Authorization & Entitlement:** `Permission.ORG_MANAGE`, `Permission.USER_READ`, `Permission.USER_WRITE`.
- **Dependencies:** Tenant-scoped isolation mixin `TenantScopedMixin`.
- **Existing Tests:** `tests/integration/test_tenant_service.py`, `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P1

---

### 4. Product Catalog and Product Configuration
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/platform/product-catalog`
  - `components/platform/ProductCatalogManagement.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/product_catalog.py` (`/api/v1/platform/suites`, `modules`, `pages`, `features`)
  - `backend/app/services/product_catalog_service.py`
- **Database Entities:** `ProductSuite`, `ProductModule`, `ProductPage`, `ProductFeature` (Alembic migration 0070–0072).
- **Authorization & Entitlement:** `Permission.PLATFORM_MANAGE`.
- **Dependencies:** Platform service.
- **Existing Tests:** `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P1

---

### 5. Plans, Subscriptions, Entitlements, and Usage Limits
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/platform/plans`, `/platform/subscriptions`, `/platform/entitlements`
  - `/tenant/subscription`, `/tenant/entitlements`, `/tenant/usage`
  - `frontend/lib/entitlements/EntitlementContext.tsx`, `frontend/components/auth/FeatureGuard.tsx`, `SuiteGuard.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/entitlements.py` (`GET /api/v1/entitlements`)
  - `backend/app/api/v1/platform.py` (subscriptions and plan feature assignment)
  - `backend/app/services/entitlement_service.py` (`resolve_entitlements`, `_SUITE_DISALLOWED_FEATURES`)
  - `backend/app/core/deps.py` (`require_feature(...)`)
- **Database Entities:** `Plan`, `PlanFeature`, `PlanLimit`, `Subscription`, `TenantFeatureOverride`, `TenantUsageLimit`.
- **Authorization & Entitlement:** `require_feature` independently verified on all backend endpoints.
- **Dependencies:** DB session, Organization, Subscription.
- **Existing Tests:** `tests/integration/test_m20_commercial_entitlement_lifecycle.py`, `tests/integration/test_m20_route_gating.py`.
- **Priority:** P0

---

### 6. Organization Onboarding and Provisioning
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/platform/provisioning`, `/onboarding`
  - `components/onboarding/WelcomeTour.tsx`
- **Backend Routes & Services:**
  - `backend/app/services/provisioning_service.py`
  - `backend/app/api/v1/platform.py`
- **Database Entities:** `Organization`, `Subscription`, `User`, `AuditEvent`.
- **Authorization & Entitlement:** `Permission.PLATFORM_MANAGE`.
- **Dependencies:** Auth service, Entitlement service, Audit logger.
- **Existing Tests:** `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P1

---

### 7. Drone Operations
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/drone-ops/overview`, `/drone-ops/live-map`, `/drone-ops/missions`, `/drone-ops/telemetry`, `/drone-ops/health`, `/drone-ops/copilot`, `/drone-ops/alerts`
  - Sub-pages with stub guidance: `/drone-ops/maintenance`, `/drone-ops/airspace`, `/drone-ops/analytics`, `/drone-ops/integrations`
  - Full-screen operational shell: `components/drone-ops/DroneOpsLayout.tsx`, `components/drone-ops/DroneOpsSidebar.tsx`
  - Wrapped in `<SuiteGuard requiredSuite="DRONE_UAV">`
- **Backend Routes & Services:**
  - `backend/app/api/v1/drones.py` (`/api/v1/drones/*`)
  - `backend/app/services/drone_service.py`, `battery_service.py`, `readiness_service.py`
  - Gated by `require_feature("drone_fleet_management")`.
- **Database Entities:** `Asset` (type=DRONE), `Battery`, `Component`, `Flight`, `MaintenanceRequirement`.
- **Authorization & Entitlement:** `Permission.DRONE_READ`, `Permission.DRONE_WRITE`, `drone_fleet_management`.
- **Dependencies:** Telemetry pipeline, HUMS service, MRO intelligence.
- **Existing Tests:** `tests/integration/test_drone_operations.py`, `tests/integration/test_m17_end_to_end_intelligence_chain.py`.
- **Known Limitations:** Physical drone telemetry bench is simulated via SITL/M19.3 Gateway.
- **Priority:** P0

---

### 8. Aircraft Operations
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/aircraft`, `/aircraft/[id]`
  - `components/aircraft-visual/AircraftContextLayer.tsx`, `AssetRegistrationModal.tsx`
  - Wrapped in `<SuiteGuard requiredSuite="AIRCRAFT">`
- **Backend Routes & Services:**
  - `backend/app/api/v1/aircraft.py` (`/api/v1/aircraft/*`)
  - `backend/app/services/aircraft_service.py`
  - Gated by `require_feature("aircraft_fleet_management")`.
- **Database Entities:** `Aircraft` (MSN, registration, manufacturer, model, hours, cycles, status).
- **Authorization & Entitlement:** `Permission.AIRCRAFT_READ`, `Permission.AIRCRAFT_WRITE`, `aircraft_fleet_management`.
- **Dependencies:** Work orders, findings, regulatory compliance.
- **Existing Tests:** `tests/integration/test_aircraft_service.py`, `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P0

---

### 9. Helicopter Operations
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/helicopters`, `/helicopters/[id]`
- **Backend Routes & Services:**
  - `backend/app/api/v1/helicopters.py`
  - Gated by `require_feature("helicopter_fleet_management")`.
- **Database Entities:** `Asset` (type=HELICOPTER with rotor system detail).
- **Authorization & Entitlement:** `Permission.HELICOPTER_READ`, `Permission.HELICOPTER_WRITE`, `helicopter_fleet_management`.
- **Dependencies:** HUMS feature baselines (rotor track & balance).
- **Existing Tests:** `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P2

---

### 10. eVTOL Operations
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/evtols`, `/evtols/[id]`
- **Backend Routes & Services:**
  - `backend/app/api/v1/evtols.py`
  - Gated by `require_feature("evtol_fleet_management")`.
- **Database Entities:** `Asset` (type=EVTOL with propulsor and battery detail).
- **Authorization & Entitlement:** `Permission.EVTOL_READ`, `Permission.EVTOL_WRITE`, `evtol_fleet_management`.
- **Dependencies:** Battery analytics, electric propulsion HUMS.
- **Existing Tests:** `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P2

---

### 11. Fleet Intelligence
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/intelligence/fleet`, `/fleet/health`
  - `components/intelligence/FleetIntelligenceConsole.tsx`, `CrossAssetRollupCard.tsx`, `AttentionQueue.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/mro_intelligence.py` (`GET /api/v1/intelligence/fleet/overview`, `GET /api/v1/signals`)
  - `backend/app/services/intelligence/cross_asset_intelligence_service.py`
  - Gated by `require_feature("mro_intelligence")`.
- **Database Entities:** `ProactiveSignalRecord`, `MaintenanceIntelligenceCandidate`, `Asset`.
- **Authorization & Entitlement:** `Permission.MAINTENANCE_READ`.
- **Dependencies:** H8.0–H8.6 aggregation engines, M7 proactive signals.
- **Existing Tests:** 138/138 integration tests passing (`tests/integration/test_cross_asset_intelligence_api.py`, `test_mro_intelligence_api.py`).
- **Priority:** P0

---

### 12. HUMS and Telemetry
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/drone-ops/telemetry`, `/drone-ops/health`, `/data-sources`
  - `components/live/TelemetryStreamViewer.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/telemetry.py` (`POST /api/v1/telemetry/events`, `POST /api/v1/telemetry/batch`)
  - `backend/app/api/v1/hums.py` (`/api/v1/hums/*`)
  - `backend/app/services/telemetry_service.py`, `hums_service.py`
- **Database Entities:** `TelemetryEventLog`, `HUMSSensor`, `HUMSFeature`, `HUMSBaseline`, `HUMSExceedance`, `HUMSPrognosticRecord`.
- **Authorization & Entitlement:** `flight_telemetry`, `hums`.
- **Dependencies:** Ingestion pipeline, rule evaluation engine.
- **Existing Tests:** `tests/integration/test_hums_thresholds.py`, `tests/integration/test_m17_persistent_telemetry_postgres_e2e.py`.
- **Known Limitations:** Ingests MAVLink/SITL or CSV streams; physical avionics bus requires on-site gateway deployment (M20 blocked).
- **Priority:** P1

---

### 13. MRO and Maintenance
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/maintenance/work-orders`, `/maintenance/tasks`, `/maintenance/planning`, `/maintenance/discrepancies`, `/maintenance/release-readiness`
  - `components/maintenance/*`
- **Backend Routes & Services:**
  - `backend/app/api/v1/work_orders.py`, `tasks.py`, `maintenance.py`, `release_readiness.py`
  - `backend/app/services/work_order_service.py`, `task_service.py`, `mro_candidate_service.py`
  - Gated by `require_feature("work_order_management")`.
- **Database Entities:** `WorkOrder`, `Task`, `MaintenanceIntelligenceCandidate`.
- **Authorization & Entitlement:** `Permission.WORK_ORDER_READ`, `Permission.WORK_ORDER_WRITE`.
- **Dependencies:** Asset registry, User/Technician qualifications.
- **Existing Tests:** `tests/integration/test_work_orders.py`, `tests/integration/test_predictive_maintenance_workflow.py`.
- **Priority:** P0

---

### 14. Compliance and Evidence
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/compliance`, `/regulations`, `/compliance/regulatory-register`, `/assessments`, `/evidence`, `/audit`
  - `components/compliance/*`, `components/evidence/*`
- **Backend Routes & Services:**
  - `backend/app/api/v1/compliance.py`, `regulatory.py`, `evidence.py`
  - `backend/app/services/compliance_service.py`, `evidence_service.py`
  - Gated by `require_feature("compliance_management")`.
- **Database Entities:** `RegulatoryAuthority`, `RegulatoryRequirement`, `ComplianceObligation`, `Evidence`.
- **Authorization & Entitlement:** `Permission.COMPLIANCE_READ`, `Permission.COMPLIANCE_WRITE`, `Permission.EVIDENCE_WRITE`.
- **Dependencies:** DB session, file storage abstraction.
- **Existing Tests:** `tests/integration/test_compliance_engine.py`, `tests/integration/test_evidence_records.py`.
- **Priority:** P1

---

### 15. Missions and Flight Operations
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/drone-ops/missions`, `/pilot`
  - `components/drone-ops/MissionList.tsx`, `MissionPlannerModal.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/missions.py` (`/api/v1/missions/*`)
  - `backend/app/services/mission_service.py`
  - Gated by `require_feature("drone_fleet_management")`.
- **Database Entities:** `Mission`, `Flight`, `Asset`.
- **Authorization & Entitlement:** `Permission.DRONE_READ`, `Permission.DRONE_WRITE`.
- **Dependencies:** Pilot assignment, drone asset state.
- **Existing Tests:** `tests/integration/test_drone_operations.py`.
- **Known Limitations:** Flight plan authorization is software-advisory and simulated; does not file FAA 14 CFR Part 107 or Part 135 waivers externally.
- **Priority:** P1

---

### 16. Maps and Live Tracking
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/drone-ops/live-map`
  - `components/drone-ops/LiveFleetMap.tsx`, `DroneMapOverlay.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/live.py`, `backend/app/api/v1/geofences.py`
  - Realtime telemetry SSE / polling stream.
- **Database Entities:** `TelemetryEventLog`, `Geofence`.
- **Authorization & Entitlement:** `flight_telemetry`, `Permission.DRONE_READ`.
- **Dependencies:** Leaflet/Mapbox GL map renderer, telemetry event buffer.
- **Existing Tests:** `tests/integration/test_m17_persistent_telemetry_postgres_e2e.py`.
- **Known Limitations:** Mapbox token fallback to OpenStreetMap tiles when external key is not provided.
- **Priority:** P1

---

### 17. Alerts and Notifications
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/notifications`, `/drone-ops/alerts`
  - `components/notifications/NotificationDrawer.tsx`, `components/drone-ops/AlertsTable.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/proactive.py`, `backend/app/api/v1/hums.py` (exceedance triggers)
  - `backend/app/services/proactive_signal_service.py`
- **Database Entities:** `ProactiveSignalRecord`, `HUMSExceedance`.
- **Authorization & Entitlement:** Tenant-isolated notification delivery.
- **Dependencies:** Rule engine, exceedance evaluator.
- **Existing Tests:** `tests/integration/test_proactive_signals.py`, `tests/integration/test_cross_asset_intelligence_api.py`.
- **Priority:** P1

---

### 18. LISA AI Assistant and Tool Orchestration
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/ai`, `/drone-ops/copilot`
  - `components/ai/LisaChatDrawer.tsx`, `LisaConsole.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/ai.py`
  - `backend/app/services/ai/orchestrator.py`, `backend/app/services/ai/tools.py`
  - Gated by `require_feature("lisa_ai_copilot")`.
- **Database Entities:** Tenant-scoped asset, finding, and work order records.
- **Authorization & Entitlement:** Enforces caller's tenant boundaries and user RBAC across all 18 tool executions (`execute_tool`).
- **Dependencies:** Gemini / LLM client (with deterministic fallback).
- **Existing Tests:** `tests/integration/test_lisa_security_entitlements.py`, `tests/integration/test_lisa_tool_matrix.py`.
- **Priority:** P0

---

### 19. Edge Gateway and Telemetry Ingestion
- **Classification:** COMPLETE WITH LIMITATIONS
- **Frontend Routes & Components:**
  - `/data-sources`, `/drone-ops/telemetry`
- **Backend Routes & Services:**
  - `gateway/` (Edge gateway daemon, MAVLink proxy, SITL adapter, local queue)
  - `backend/app/api/v1/device_gateway.py` (`/api/v1/gateway/*`)
- **Database Entities:** `TelemetryEventLog`.
- **Authorization & Entitlement:** Device API token authentication with tenant binding.
- **Dependencies:** MAVLink / pymavlink protocol stack.
- **Existing Tests:** `tests/integration/test_m19_2_edge_gateway_telemetry.py`, `tests/integration/test_m19_3_sitl_integration.py`.
- **Known Limitations:** Validated with SITL ArduCopter/PX4 simulation; physical companion computer hardware deployment is marked BLOCKED for M20.
- **Priority:** P1

---

### 20. Reporting and Analytics
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/reports`, `/executive`, `/organization/readiness`
  - `components/reports/ReportGenerator.tsx`, `ExecutiveKpis.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/reports.py`, `backend/app/api/v1/observability.py`
- **Database Entities:** Read aggregates across `Aircraft`, `Asset`, `WorkOrder`, `Flight`.
- **Authorization & Entitlement:** `Permission.REPORT_READ`.
- **Dependencies:** Analytics rollup queries.
- **Existing Tests:** `tests/integration/test_observability.py`.
- **Priority:** P2

---

### 21. Audit Logs and Administrative Activities
- **Classification:** COMPLETE
- **Frontend Routes & Components:**
  - `/audit`, `/tenant/audit`, `/platform/audit`
  - `components/audit/AuditLogTable.tsx`
- **Backend Routes & Services:**
  - `backend/app/api/v1/audit.py`, `backend/app/api/v1/platform.py`
  - `backend/app/services/audit_service.py`
  - Gated by `require_feature("audit_logging")` or `Permission.PLATFORM_MANAGE`.
- **Database Entities:** `AuditEvent` (immutable record of actor, action, tenant, diff, IP).
- **Authorization & Entitlement:** `Permission.AUDIT_READ`.
- **Dependencies:** Audit interceptor.
- **Existing Tests:** `tests/integration/test_audit_trail.py`.
- **Priority:** P1

---

### 22. Demo and Sample Data
- **Classification:** PARTIAL (Requires M22 Split)
- **Frontend Routes & Components:**
  - `frontend/lib/demo/demoPlatform.ts`, `demoStore.ts`, `demoTenant.ts`
  - `frontend/lib/data-mode/DataModeContext.tsx`
- **Backend Routes & Services:**
  - `backend/scripts/seed_m21_demo_environment.py` (M21 combined single tenant `Kota Aerospace Demo Operations`)
- **Database Entities:** Full tenant-isolated mock graph.
- **Gaps Identified:**
  - M21 populated a single mixed tenant (`Kota Aerospace Demo Operations`).
  - M22 requires two independent demonstration tenant configurations:
    1. `Kota Drone Operations Demo` (Drone-only vertical, `DRONE_UAV` suite/industry)
    2. `Kota Aircraft Operations Demo` (Aircraft-only vertical, `AIRCRAFT` suite/industry)
- **Priority:** P0

---

### 23. Frontend Navigation, Responsive UI, and Accessibility
- **Classification:** PARTIAL (Requires Strict Suite Exclusion in Sidebar)
- **Frontend Routes & Components:**
  - `frontend/components/layout/Sidebar.tsx`
  - `frontend/components/layout/Topbar.tsx`
  - `frontend/components/auth/RouteEntitlementGuard.tsx`
  - `frontend/components/auth/SuiteGuard.tsx`
- **Gaps Identified:**
  - `Sidebar.tsx` currently keeps unheld product suites in the nav as grayed-out locked items (`opacity: 0.5`, lock icon) rather than strictly hiding un-subscribed vertical asset modules (e.g. Drone tenant sees Aircraft and Helicopter; Aircraft tenant sees Drone Ops and Drones).
  - Aircraft navigation (`/aircraft`, `/engines`) must be completely hidden from Drone-only tenants.
  - Drone navigation (`/drone-ops/overview`, `/drones`) must be completely hidden from Aircraft-only tenants.
- **Priority:** P0

---

### 24. Backend APIs and Integrations
- **Classification:** COMPLETE
- **Backend Routes & Services:**
  - All 48 REST endpoints registered in `backend/app/api/v1/router.py`.
  - All route guards enforce tenant boundary via `current_user.organization_id` and commercial boundary via `require_feature(...)`.
- **Existing Tests:** Entire backend pytest suite passes with zero regressions.
- **Priority:** P0

---

### 25. Security, Tenant Isolation, Reliability, and Deployment
- **Classification:** COMPLETE
- **Backend Routes & Services:**
  - Global `TenantScopedMixin` enforces `organization_id` on all customer rows.
  - Direct cross-tenant access attempts return 404/403.
  - Staging deployment running schema revision `0072` at commit `9bf6f45` verified 100% healthy.
- **Existing Tests:** `tests/integration/test_tenant_isolation.py`, `tests/integration/test_customer_journey_platform_e2e.py`.
- **Priority:** P0

---

## 3. Inventory Action Plan (P0 / P1 Deliverables)

1. **[P0] Navigation Filtering Repair:** Update `Sidebar.tsx` and `navFeatureMap.ts` so that unheld vertical asset classes (Aircraft vs Drone vs Helicopter vs eVTOL) are excluded from tenant navigation entirely.
2. **[P0] Two Separate Demonstration Tenants:**
   - Extend `seed_m21_demo_environment.py` (or introduce `seed_m22_demo_tenants.py`) to create and populate:
     - `Kota Drone Operations Demo`
     - `Kota Aircraft Operations Demo`
   - Update frontend synthetic mock dataset in `demoPlatform.ts` and `demoTenant.ts` to reflect the two separate tenants.
3. **[P1] Documentation Artifacts:** Complete all 10 required acceptance reports and matrices.
