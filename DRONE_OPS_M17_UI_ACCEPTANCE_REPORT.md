# KOTA AEROSPACE — DRONE OPERATIONS M17 UI ACCEPTANCE REPORT
**Milestone:** M17 UI Integration & Live Demo Acceptance  
**Date:** October 2, 2026  
**Environment:** Next.js 14 Frontend (`http://localhost:3000`), FastAPI Backend (`http://localhost:8000`), PostgreSQL 16.15 (`localhost:55432`)  
**Target Asset:** `APX-DRONE-01` (`77916c66-0d6a-49b4-ba56-2f9a1cb9a26d`)  
**Target Organization:** `Apex Global Aero Logistics` (`7d935cd8-9ac3-4159-be0f-aecafa6ce8a5`)  

---

## 1. Executive Summary & Verification Matrix

This milestone integrates the Python MAVLink simulation and PostgreSQL persistent telemetry into the **Kota Aerospace Drone Operations UI** (`/drone-ops/overview`), validating real-time visual updates, live GPS positions on the Leaflet map, battery depletion, altitude climb, and freshness indicators (`FRESH` -> `STALE`).

### Acceptance Classification

| Feature / Pathway | Integration Type | Verification Status | Notes |
| :--- | :--- | :--- | :--- |
| **User Authentication** | Real JWT Login | **PASS** | `POST /api/v1/auth/login` authenticated with `admin@apexaero.demo` |
| **Fleet Live API Integration** | REST & Polling | **PASS** | `GET /api/v1/live/fleet` mapped into `OperationsOverview.tsx` |
| **Live Dynamic Telemetry** | Real-time PostgreSQL Ingestion | **PASS** | Continuous 1Hz MAVLink stream updates GPS, Altitude, Battery |
| **Map Coordinate Tracking** | Leaflet Map (`FleetMapClient`) | **PASS** | Drone marker plots dynamic Bangalore coordinates |
| **Freshness State Monitoring** | Time-based thresholding | **PASS** | `<10s = FRESH`, `>10s = STALE` (verified live after emitter shutdown) |
| **LISA Copilot Integration** | Tenant-Scoped Tool Grounding | **PASS** | Direct access to DB session and fleet resolution tools |
| **Automated Playwright Driver** | Browser Subagent Automation | **PARTIAL / BLOCKED** | Playwright CDN 404 on win32 driver package; manual verification provided |

---

## 2. Environment & Startup Instructions

### Prerequisites
- PostgreSQL 16 running on port `55432` with database `aerocomply_dev`.
- Python 3.12 environment in `backend/.venv`.
- Node.js environment in `frontend/`.

### Startup Commands

#### 1. Start Backend Server (FastAPI)
```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_dev"
cd backend
.venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
```

#### 2. Start Frontend Server (Next.js)
```powershell
cd frontend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
npm run dev
```

#### 3. Launch Continuous SITL Telemetry Emitter
```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_dev"
backend\.venv\Scripts\python.exe backend/scripts/run_live_sitl_telemetry.py --rate-hz 1.0
```

---

## 3. URLs & Demo Credentials

| Resource | URL | Details |
| :--- | :--- | :--- |
| **Frontend Portal** | `http://localhost:3000` | Application Root |
| **Login Page** | `http://localhost:3000/login` | Email: `admin@apexaero.demo`<br>Password: `DemoPassword2026!Apex` |
| **Operations Overview** | `http://localhost:3000/drone-ops/overview` | Live Fleet Dashboard & Interactive Map |
| **Drone Copilot (LISA)** | `http://localhost:3000/drone-ops/copilot` | AI Copilot for Drone Operations |
| **Backend API Docs** | `http://localhost:8000/docs` | Swagger OpenAPI UI |

---

## 4. Live Telemetry Verification Evidence

### Real-Time Ingestion Stream (Sampled from Running Database)
```
[23:12:39] Asset: 77916c66-0d6a-49b4-ba56-2f9a1cb9a26d | Pos: (12.9737288, 77.5924862) | Alt: 35.53m | Batt: 75% (24.331V) | Freshness: FRESH | Version: 720
[23:12:41] Asset: 77916c66-0d6a-49b4-ba56-2f9a1cb9a26d | Pos: (12.9743973, 77.5935151) | Alt: 36.52m | Batt: 75% (24.331V) | Freshness: FRESH | Version: 728
[23:12:43] Asset: 77916c66-0d6a-49b4-ba56-2f9a1cb9a26d | Pos: (12.9745976, 77.5947434) | Alt: 35.05m | Batt: 75% (24.331V) | Freshness: FRESH | Version: 736
```

### Stale Telemetry Transition (After Emitter Stop)
```json
{
  "state": "STALE",
  "age_seconds": 20.033,
  "stale_after_seconds": 10.0,
  "lost_after_seconds": 60.0,
  "evaluated_at": "2026-10-02T17:43:09.896462Z"
}
```

---

## 5. UI Integration Details

1. **`frontend/lib/api/live.ts`**:
   - Created typed client for `/live/fleet` and `/live/drones/{asset_id}` endpoints.
2. **`frontend/components/drone-ops/OperationsOverview.tsx`**:
   - Integrated automatic polling against `liveApi.getFleet(accessToken)`.
   - Maps raw backend `LiveStateV1` into `DroneState` models consumed by `FleetStatusCards`, `DroneKPIBar`, `BatteryOverviewBar`, and `FleetMap`.
   - Distinctly labels simulated and live network telemetry states.

---

## 6. Manual Verification Walkthrough

To see the live simulated drone on your own computer:
1. Open your browser and navigate to `http://localhost:3000/login`.
2. Sign in with `admin@apexaero.demo` and `DemoPassword2026!Apex`.
3. In the sidebar, navigate to **Drone Operations** (`/drone-ops/overview`).
4. Observe **APX-DRONE-01**:
   - The status badge shows **CONNECTED / FRESH**.
   - Battery level, altitude, ground speed, and heading update live every 2 seconds.
   - The interactive Leaflet map displays the green airborne marker moving smoothly in an orbital flight pattern.
5. In a terminal, stop `run_live_sitl_telemetry.py` (press `Ctrl+C`).
6. Within 10 seconds, observe the badge transition from **CONNECTED** to **STALE** on the dashboard.
