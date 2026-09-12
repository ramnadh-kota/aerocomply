# ROADMAP STATUS (capability-based, built from scratch — no prior milestone-phase roadmap doc found in-repo)

Maturity levels (highest truthfully earned, low to high): EXISTS < WORKS_IN_TESTS < INTEGRATED < BROWSER_VERIFIED < PRODUCTION_READY. None of the domains below were confirmed at BROWSER_VERIFIED or PRODUCTION_READY in this pass — no live server was run against the frontend, so that ceiling applies uniformly pending a follow-up session.

| Domain | Backend | Frontend | Tests | Integration | Overall Maturity |
|---|---|---|---|---|---|
| aircraft | Router+service exist, 55-line service | REAL-mode wiring confirmed | No dedicated test file found (UNKNOWN indirect coverage) | Lisa tool present | INTEGRATED |
| work_orders | Router+service exist | REAL-mode wiring confirmed | No dedicated API test found | Lisa tool present | INTEGRATED |
| technicians | Router+service (275 LOC) | REAL-mode wiring confirmed | test_technician_service.py | Lisa tool present | INTEGRATED |
| control_center | Router+service | REAL-mode wiring confirmed | test_control_center_service.py | Lisa tool present | INTEGRATED |
| aog / aog_recovery | Two services, 833 LOC combined | REAL-mode wiring confirmed (aog-recovery page) | test_aog_service.py, test_aog_recovery_service.py | Lisa tool present | INTEGRATED |
| parts | Router+service | REAL-mode wiring confirmed | test_part_service.py | Lisa tool present | INTEGRATED |
| purchase_orders | Router+service (282 LOC) | REAL-mode wiring confirmed | test_purchase_order_service.py | Lisa tool present | INTEGRATED |
| assessments | Router (206 LOC) + assessment engine | REAL-mode wiring confirmed (assessment-intelligence page) | test_assessment_engine.py, test_assessments_api.py, test_lisa_assessment_tools.py | Lisa tool present | INTEGRATED |
| evidence | Router+service (147 LOC) | REAL-mode wired: `lib/api/evidence.ts` + `components/evidence/RealTaskGatePanel.tsx` on `maintenance/work-orders/[id]`, browser-verified 2026-09-12 (create → UPLOADED → SUBMITTED, remaining transitions confirmed via direct API calls against the same service path). Standalone `app/(app)/evidence` list/detail pages remain DEMO-only (different data model — assessment-linked documents — with no backend equivalent) | test_evidence_lifecycle.py (unit) | Lisa tool present | INTEGRATED |
| inspections | Router+service (224 LOC) | REAL-mode wiring added 2026-09-12 (`maintenance/inspections` list + `[id]` detail, `lib/api/inspections.ts`); browser-verified list (empty + DEMO fallback) and mobile viewport, detail create/transition flow unverified against live data due to shared dev-DB being emptied mid-session by other agents' work | test_inspection_lifecycle.py (unit) | Lisa tool present | INTEGRATED |
| deferred_items | Router+service (163 LOC) | REAL-mode wiring confirmed 2026-09-12 (`maintenance/deferred` page, `lib/api/deferred-items.ts`) | test_deferred_item_service.py | Lisa tool present | INTEGRATED |
| release_readiness | Router (23 LOC, thin) + service (150 LOC) | No dedicated frontend area found | test_release_readiness_service.py (unit) | Lisa tool present | WORKS_IN_TESTS |
| compliance | Router (136 LOC) + service (204 LOC) | Frontend page exists but no REAL-mode signal found | test_compliance_service.py | Lisa tool present; applicability engine explicitly NOT backend-resident | WORKS_IN_TESTS |
| regulatory | Router+service (100 LOC) | Frontend "regulations" page exists, REAL-mode unconfirmed | test_regulatory_service.py | Lisa tool present | WORKS_IN_TESTS |
| procurement / part_requirements / vendor_fit / vendor_part_availability | Routers+services all present and tested individually | procurement/purchase-orders page REAL; other procurement sub-areas UNKNOWN | test_procurement_service.py, test_part_requirement_service.py, test_vendor_fit_service.py; no test found for vendor_part_availability | Lisa tools present | INTEGRATED (purchase-orders leg) / WORKS_IN_TESTS (rest) |
| inventory / receiving / warehouses | Routers+services present | maintenance/parts page REAL; receiving/warehouses UNKNOWN | test_inventory_transaction_service.py, test_inventory_concurrency.py, test_receiving_service.py, test_warehouse_service.py | Lisa tool present | WORKS_IN_TESTS (receiving/warehouses) / INTEGRATED (parts leg) |
| maintenance (program) | Router+service (264 LOC) | "maintenance-program" area folder exists, REAL-mode unconfirmed | test_maintenance_service.py | Lisa tool present | WORKS_IN_TESTS |
| platform / users / auth | Routers+services present | settings page REAL-mode confirmed; platform admin area exists | test_platform_admin.py, test_platform_api.py, test_users_api.py, test_auth_flow.py | n/a | INTEGRATED |
| proactive | Router (28 LOC) + service (185 LOC) | No dedicated frontend area identified | test_proactive_service.py | Lisa tool present | WORKS_IN_TESTS |
| data_import | Router+service (280 LOC) | "data-import" frontend area exists, REAL-mode unconfirmed | test_data_import.py, test_data_import_api.py | n/a | WORKS_IN_TESTS |
| Lisa / AI | ~4,000 LOC across services/ai + services/lisa, tool registry delegates to all canonical services with permission gating | "ai" frontend area exists; live end-to-end wiring UNCONFIRMED | 6 lisa/ai integration test files + test_ai_safety.py, test_provider_selection.py, test_openai_compatible_provider.py | Confirmed via direct code read (tools.py) | INTEGRATED (backend); frontend leg UNKNOWN |
| Tenancy/Security | Recent dedicated hardening commit (f67055b) + tests (tenant_isolation, suspended_org_token_revocation, audit_immutability) | n/a | 3+ dedicated security/tenancy test files | Per-model completeness UNKNOWN | WORKS_IN_TESTS (partial — coverage breadth unverified) |

## Notes on inflation risk

Every "INTEGRATED" row above is based on (a) a confirmed backend router+service+model+schema chain and (b) a confirmed `useDataMode`/`isReal` code pattern in the matching frontend page — it is NOT based on a live browser session hitting the running app, so none of these should be advertised externally as "working in production" without that follow-up. Rows marked WORKS_IN_TESTS have real backend test coverage but unconfirmed or absent frontend wiring, or (for compliance) a self-documented backend gap.
