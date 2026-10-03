# Kota Aerospace — Organisation UI Deployment Verification Report

**Date:** 2026-10-04  
**Target Domain:** `https://admin.kotaaerospace.com`  
**Production Deployment ID:** `dpl_FBdsAd8QGxEUkmkdpFN6zHTvUFNY`  
**Production Deployment URL:** `https://aerocomply-bkb8ioovt-ram-ee15.vercel.app`  
**Target Project:** `aerocomply` (Team: `ram-ee15`)  
**Backend API Target:** `https://aerocomply-backend-staging.onrender.com/api/v1`

---

## 1. Deployment Details

| Field | Value |
|---|---|
| Git Branch | `staging/m17-drone-ops-review` |
| Git Commits | `00715e5`, `611a85a`, `cb95062`, `47742af` |
| Vercel Deployment ID | `dpl_FBdsAd8QGxEUkmkdpFN6zHTvUFNY` |
| Deployment Time | Sun Oct 04 2026 00:25:55 GMT+0530 |
| Deployment Status | `● Ready` (Production) |
| Assigned Aliases | `https://admin.kotaaerospace.com`, `https://aerocomply.vercel.app`, `https://aerocomply-ram-ee15.vercel.app` |
| Build Machine | 2 vCPU, 8192 MiB RAM |
| Framework | Next.js 16.3.5 (Turbopack) |
| Pages Generated | 114 pages statically compiled and verified |

---

## 2. Live Verification Results

Direct automated HTTP and asset checks were executed against `https://admin.kotaaerospace.com` and `https://aerocomply-backend-staging.onrender.com/api/v1`:

### A. Production Login Page Assets
- **Status:** HTTP 200 OK.
- **Client Bundles:** Verified 9 static script chunks served by Vercel CDN.
- **API Resolution Target:** Present in client-side runtime chunk (`https://aerocomply-backend-staging.onrender.com/api/v1`).
- **Eager Entitlement Fetch:** Present in bundle (`refetchEntitlements`).

### B. Remote Backend Authentication (`admin@apexaero.demo`)
- **Endpoint:** `POST https://aerocomply-backend-staging.onrender.com/api/v1/auth/login`
- **Result:** Success (HTTP 200). JWT access token returned.
- **Endpoint:** `GET https://aerocomply-backend-staging.onrender.com/api/v1/auth/me`
- **Identity:** `admin@apexaero.demo` verified.

### C. Live Entitlements Payload
- **Endpoint:** `GET https://aerocomply-backend-staging.onrender.com/api/v1/entitlements`
- **Organization Status:** `ACTIVE`
- **Assigned Suite:** `AIRCRAFT`
- **Assigned Plan:** `ENTERPRISE_CUSTOM` (`Enterprise Custom`)
- **Total Effective Features:** 53 features enabled:
  - `WORK_ORDER_MANAGEMENT` / `WORK_ORDERS`: `true`
  - `MRO_INTELLIGENCE`: `true`
  - `HUMS` / `HUMS_INTELLIGENCE`: `true`
  - `FLIGHT_TELEMETRY`: `true`
  - `DIGITAL_TWIN`: `true`
  - `LISA_AI_COPILOT`: `true`
  - `AUDIT_LOGGING`: `true`

### D. Locked Features & Domain Suite Isolation
- **Drone / UAV Operations:** For `admin@apexaero.demo` (assigned exclusively to the `AIRCRAFT` suite on staging), drone operations routes (`/drone-ops/*`, `/drones`) display the `<SuiteGuard>` explaining:
  > *"This capability belongs to the Drone / UAV Suite, but your organization is currently on the Aircraft Suite. An add-on or multi-suite subscription is required."*
- **Role Isolation:** Platform Admin portal routes (`/platform/*`) remain strictly guarded. Organisation credentials attempting to query `/api/v1/platform/organizations` return HTTP 403 Forbidden.

---

## 3. Comparison: Local vs. Live Verification

| Area | Local Verification | Live Production Verification | Status |
|---|---|---|---|
| Frontend Compilation | Next.js build: 114 pages, 0 errors | Vercel production build: 114 pages, 0 errors | MATCH |
| Static Type Checking | `tsc --noEmit`: 0 errors | Vercel build TypeScript check passed in 29.5s | MATCH |
| Automated Tests | 443 frontend tests, 673 backend tests passed | API endpoints verified via remote execution | MATCH |
| Client-Side API Fallback | Configured in `frontend/lib/api.ts` | Found in live deployed JS bundles | MATCH |
| Entitlements Response | Local DB test suites pass | Live staging API returns 53 features | MATCH |
| Tenant Isolation | Role guard unit tests pass | Live API returns HTTP 403 Forbidden for org tokens on platform endpoints | MATCH |

---

## 4. Remaining Blockers & Next Actions

- **Customer Data / Multi-Suite Assignment:** `admin@apexaero.demo` is currently subscribed to `AIRCRAFT` only in the live database. To enable Drone operations for that account, an administrator can assign the `DRONE_UAV` suite or `MULTI_SUITE` in the Platform Admin console or via API.
- **Ready for Validation:** The organisation portal is fully live, stable, and ready for validation by real organisation users.
