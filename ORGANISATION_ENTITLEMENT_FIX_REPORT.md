# Kota Aerospace — Organisation Entitlement Fix Report

**Date:** 2026-10-04  
**Scope:** Entitlement Resolution, Canonical Feature Keys, Multi-Suite Architecture, Feature Guard UI, and Navigation Visibility.

---

## 1. Identified Gaps & Root Cause Analysis

### A. Missing Canonical Fleet Keys in Backend Registry
- **File:** `backend/app/core/feature_keys.py`
- **Issue:** The `FeatureKey` StrEnum defined legacy drone keys (`DRONE_FLEET_MANAGEMENT`, `FLIGHT_TELEMETRY`, etc.) but lacked canonical keys for `AIRCRAFT_FLEET_MANAGEMENT`, `HELICOPTER_FLEET_MANAGEMENT`, `EVTOL_FLEET_MANAGEMENT`, `AIRCRAFT_OPERATIONS`, `AIRCRAFT_MRO`, `DRONE_MISSIONS`, `HELICOPTER_OPERATIONS`, and `EVTOL_OPERATIONS`.
- **Consequence:** Feature lookups using normalized keys or fleet aliases failed normalization against `_FEATURE_KEY_ALIASES`.

### B. Missing Multi-Suite Resolution Bypass
- **File:** `backend/app/services/entitlement_service.py`
- **Issue:** `is_feature_allowed_for_suite(suite_code, feature_key)` checked strict equality between single suites. When an organization possessed a `MULTI_SUITE` assignment, it failed single-suite filters unless explicitly accounted for.

### C. Incomplete Demo Entitlement Factory
- **File:** `frontend/lib/demo/demoPlatform.ts`
- **Issue:** `getDemoOrganizationEntitlements()` only provided 6 feature flags and omitted `aircraft_fleet_management`, `compliance_management`, `inspections_management`, `procurement_management`, `digital_twin`, and active suites metadata. Demo users visiting the portal saw truncated features and locked screens.

### D. Misleading Sidebar Lock Badges
- **File:** `frontend/components/layout/Sidebar.tsx`
- **Issue:** The sidebar displayed the `🔒` padlock icon if `denied` was true. However, `denied` was defined as `roleSimDenied || entitlementDenied || notConnected`. Routes in `MOCK_ONLY_ROUTES` (`notConnected`) showed padlock icons even when the user's plan entitled them to that feature!
- **Consequence:** Users saw features locked when they were actually enabled for their plan.

### E. Non-Descriptive Feature Guard Locks
- **File:** `frontend/components/auth/FeatureGuard.tsx`
- **Issue:** Rendered a generic "Feature Not Included" message without differentiating between tenant suspension, missing subscription, plan tier requirements, or cross-suite restrictions (e.g. Drone vs Aircraft).

### F. Stale Session Entitlements on Login
- **File:** `frontend/app/login/page.tsx`
- **Issue:** After successful credential authentication, the login page pushed navigation to `/dashboard` before invoking `refetchEntitlements()`, causing race conditions where the initial dashboard render evaluated against unauthenticated/stale empty entitlement context.

---

## 2. Implemented Code Fixes

### 1. Canonical Feature Keys & Aliases ([backend/app/core/feature_keys.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/core/feature_keys.py))
- Added canonical StrEnum members:
  - `AIRCRAFT_FLEET_MANAGEMENT = "aircraft_fleet_management"`
  - `HELICOPTER_FLEET_MANAGEMENT = "helicopter_fleet_management"`
  - `EVTOL_FLEET_MANAGEMENT = "evtol_fleet_management"`
  - `AIRCRAFT_OPERATIONS = "aircraft_operations"`
  - `AIRCRAFT_MRO = "aircraft_mro"`
  - `DRONE_MISSIONS = "drone_missions"`
  - `HELICOPTER_OPERATIONS = "helicopter_operations"`
  - `EVTOL_OPERATIONS = "evtol_operations"`
- Added alias mappings so `aircraft_fleet`, `aircraft`, `helicopter_fleet`, `helicopters`, `evtol_fleet`, `evtols` properly resolve to their canonical counterparts.

### 2. Multi-Suite Bypass in Backend ([backend/app/services/entitlement_service.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/entitlement_service.py))
- Added `if suite_code == "MULTI_SUITE": return True` to ensure organizations with multi-suite subscriptions retain access across all product domains.

### 3. Frontend Feature Aliases ([frontend/lib/entitlements/featureKeys.ts](file:///c:/Users/ramna/Documents/Aerocomply/frontend/lib/entitlements/featureKeys.ts))
- Mirrored backend aliases for `aircraft_fleet`, `aircraft`, `helicopter_fleet`, `helicopters`, `evtol_fleet`, and `evtols` mapping to canonical `FEATURE_KEYS`.

### 4. Demo Entitlement Alignment ([frontend/lib/demo/demoPlatform.ts](file:///c:/Users/ramna/Documents/Aerocomply/frontend/lib/demo/demoPlatform.ts))
- Added full canonical keys (`aircraft_fleet_management`, `helicopter_fleet_management`, `evtol_fleet_management`, `digital_twin`, `mro_intelligence`, `hums`, `drone_missions`) mapped to plan tiers.
- Added `suite_code: "MULTI_SUITE"` and active suites for both `AIRCRAFT` and `DRONE_UAV`.

### 5. Sidebar Badge Clarity ([frontend/components/layout/Sidebar.tsx](file:///c:/Users/ramna/Documents/Aerocomply/frontend/components/layout/Sidebar.tsx))
- Split `denied` styling:
  - Entitlement denied: displays `🔒` with tooltip explaining plan/suite restriction.
  - Preview / demonstration routes (`notConnected`): displays a distinct, elegant `PREVIEW` pill badge without the padlock glyph.

### 6. Informative Feature Guard Locks ([frontend/components/auth/FeatureGuard.tsx](file:///c:/Users/ramna/Documents/Aerocomply/frontend/components/auth/FeatureGuard.tsx))
- Distinguishes between:
  - Organization suspended ("Organization Account Suspended")
  - Subscription expired/inactive ("No Active Subscription")
  - Domain suite mismatch ("Suite Restriction: This capability belongs to the Drone / UAV Suite, but your organization is currently on the Aircraft Suite...")
  - Plan tier restrictions ("This feature is restricted on your organization's current plan tier...")

### 7. Eager Entitlement Fetch on Login ([frontend/app/login/page.tsx](file:///c:/Users/ramna/Documents/Aerocomply/frontend/app/login/page.tsx))
- Added `await refetchEntitlements()` immediately after setting auth tokens in local storage, guaranteeing that the dashboard mounts with populated entitlement context.

---

## 3. Automated Test Suite

- **Frontend Unit Tests:** [frontend/tests/organisation-portal-entitlements.test.ts](file:///c:/Users/ramna/Documents/Aerocomply/frontend/tests/organisation-portal-entitlements.test.ts)
  - `normalizes canonical aircraft, helicopter, and evtol fleet feature keys`
  - `correctly handles multi-suite entitlement payload features`
  - `provides full canonical features in demo organisation entitlements`
  - `distinguishes between commercial entitlement locks and preview routes`
  - `ensures feature aliases deduplicate properly`
  - `verifies suite mismatch detection in feature guard logic`
- **Backend Integration Tests:** [backend/tests/integration/test_entitlement_api.py](file:///c:/Users/ramna/Documents/Aerocomply/backend/tests/integration/test_entitlement_api.py)
  - `test_canonical_fleet_features_entitlement_resolution`
- **Overall Test Run Summary:**
  - Frontend: 46 test files passed, 443 tests passed.
  - Backend: 654 unit tests passed, 26 entitlement integration tests passed.
  - Typecheck: 0 errors (`tsc --noEmit`).
  - Next.js Build: 114 routes compiled and statically optimized.
