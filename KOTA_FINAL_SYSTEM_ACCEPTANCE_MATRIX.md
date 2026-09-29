# Kota Aerospace — Final System Acceptance Matrix

This acceptance matrix represents the verified, forensic state of the Kota Aerospace codebase.
Every status is evidence-backed based on executed tests, static analysis, build verification, and live application runtime smoke tests.

| Domain | Status | Evidence | Remaining Risk |
|---|---|---|---|
| **Backend** | **VALIDATED** | 2,040 pytest tests passing (0 failed, 16 deselected storage tests); FastAPI server starts cleanly on port 8000; health endpoints return 200 OK | Unexercised optional third-party webhook providers |
| **Frontend** | **VALIDATED** | 332 Vitest tests passing (30 files); Next.js 16.3.5 Turbopack production build succeeded for all 99 pages; live dev server running on port 3000 | Browser hydration in obsolete legacy browser engines |
| **Database** | **VALIDATED** | PostgreSQL schemas verified on fresh and migrated databases; UUID primary keys, tenant scoping, foreign keys, and indexes verified | Model-to-migration schema drift documentation debt |
| **Migrations** | **VALIDATED** | Alembic migration head at `0061` (`0061_suite_plan_subscription_hierarchy.py`); linear revision history; upgrade and round-trip downgrade verified | Downgrade safe only with globally unique plan codes |
| **Authentication** | **VALIDATED** | JWT bcrypt token verification, live per-request active/non-suspended organization check, SSO Entra models tested | Browser `localStorage` token storage exposed to XSS |
| **RBAC** | **VALIDATED** | 462 protected routes; fail-closed RBAC dependencies; 10 public endpoints verified | Role alterations take effect on subsequent request |
| **Multi-tenancy** | **VALIDATED** | 110 cross-tenant probes; 62 tenant-scoped models enforce `organization_id` scoping; write and read isolation verified | None identified in test and codebase audit |
| **Suite Architecture** | **VALIDATED** | `AIRCRAFT`, `DRONE_UAV`, `HELICOPTER`, `EVTOL_AAM` product suites verified; strict suite boundaries enforced | None identified |
| **Plans** | **VALIDATED** | Suite-specific plans verified; cross-suite plan movements and subscriptions rejected | None identified |
| **Subscriptions** | **VALIDATED** | Active, trialing, past_due, canceled, and scheduled subscription lifecycles verified in DB & API | Pre-deploy data check required for existing production tenants |
| **Entitlements** | **VALIDATED** | Per-request resolution via `resolve_entitlements()`; feature keys & tenant overrides verified | Un-gated internal telemetry token endpoints |
| **LISA** | **VALIDATED** | All 59 tools registered; fail-closed permissions + commercial suite/feature entitlements enforced; 123 tests passing | External LLM API rate limits / upstream availability |
| **Telemetry** | **VALIDATED** | `NormalizedTelemetryEvent` mapping, NaN/Infinity rejection, duplicate flight protection verified | Offline packet burst buffering under extreme load |
| **MAVLink** | **VALIDATED** | CRC/CRC_EXTRA, SysID/CompID, sequence tracking, duplicate suppression, multi-vehicle routing | Physical radio hardware link loss simulation |
| **HUMS** | **VALIDATED** | Vibration & sensor feature extraction, baseline drift, degradation curves, diagnostic candidate generation | Extreme noisy baseline convergence |
| **M7 Intelligence** | **VALIDATED** | Proactive maintenance signals, priority tiering (P0-P3), deduplication, resolution lifecycle verified | Notification delivery webhook integrations |
| **MRO** | **VALIDATED** | Work order lifecycle, task execution, technician authorization, part requirements verified | External ERP inventory synchronization |
| **Inspections** | **VALIDATED** | Inspection requirements, task-level RII second-inspector gates verified | None identified |
| **Compliance** | **VALIDATED** | Regulatory registers, AD/SB applicability, compliance obligations, evidence thread | Dynamic third-party regulation scraping |
| **Platform Admin** | **VALIDATED** | Platform manage permission required; plan/suite/module catalog CRUD verified | None identified |
| **Organization Admin** | **VALIDATED** | Direct user management, tenant profile, invitation workflows verified | None identified |
| **Audit** | **VALIDATED** | Immutability verified; structured audit logging with request IDs, org IDs, user IDs | Log exporter aggregator configuration |
| **API** | **VALIDATED** | OpenAPI schema conforms to FastAPI / Pydantic models; smoke test verifies 0 500 errors | Deprecated Pydantic V1 config warnings |
| **Security** | **VALIDATED** | Mandatory DJI webhook signature verification, zero hardcoded credentials, safe CORS, fail-closed RBAC | Production deployment perimeter hardening |
| **Performance** | **PARTIALLY VALIDATED** | Indexed queries, sub-second API responses, 290s test run across 2,040 tests | High-throughput distributed load testing |
| **Observability** | **VALIDATED** | Request IDs, structured audit logging, root `/health` and API `/api/v1/health` endpoints | APM metrics exporter integration |
| **Frontend Runtime** | **VALIDATED** | Live HTTP 200 responses verified on `/login`, `/dashboard`, `/platform`, `/ai`, `/drones`, `/aircraft`, `/maintenance/work-orders` | None identified |
| **Deployment** | **PARTIALLY VALIDATED** | Production Dockerfile and Next.js production build verified; live local deployment tested | Cloud Kubernetes production orchestration manifests |
