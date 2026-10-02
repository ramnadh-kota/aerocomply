# KOTA AEROSPACE — DRONE OPERATIONS DEPLOYMENT READINESS AUDIT

**Target Environment:** Staging & Production Clusters  
**Platform Version:** 1.0.0-rc1  
**Assessment Date:** 2026-10-02  
**Overall Readiness:** SOFTWARE READY / HARDWARE INTEGRATION PENDING  

---

## 1. Environment Configuration & Secrets Checklist

| Configuration Variable | Service | Required Staging Value / Format | Validation Status |
|---|---|---|---|
| `DATABASE_URL` | FastAPI Backend | PostgreSQL connection string with SSL enabled | Verified |
| `JWT_SECRET_KEY` | Auth Service | 256-bit cryptographically secure string | Verified |
| `LISA_AI_PROVIDER` | AI Engine | `openai` / `anthropic` / `azure_openai` | Verified |
| `LISA_API_KEY` | AI Engine | Secret key injected via KMS / Vault | Verified |
| `NEXT_PUBLIC_API_URL` | Frontend Client | Base URL pointing to FastAPI gateway | Verified |
| `MAVLINK_GATEWAY_URL` | Telemetry Ingestion | Edge broker address / MQTT bridge | Verified (SW) |

---

## 2. Database Migrations & Schema Compatibility

- **Alembic Engine:** Fully configured under `backend/alembic/`.
- **Target Schemas:**
  - `assets` (drone extensions: model, registration, serial_number, battery_type).
  - `missions` (purpose, operating_area, pilot_user_id, authorized_at).
  - `proactive_signals` (signal_key, headline, severity, evidence_refs).
  - `live_states` (coordinates, fix quality, freshness, battery SoC).
  - `geofences` (polygon coordinates, altitude limits, status).
- **Rollback Compatibility:** All migrations include backward-compatible downgrade scripts.

---

## 3. Deployment & Rollback Strategy

1. **Pre-Deployment Checks:**
   - Execute backend test suite (`pytest backend/tests/unit`).
   - Execute frontend test suite (`npm run test`, `npm run typecheck`, `npm run build`).
2. **Database Migration:**
   - Run `alembic upgrade head` in staging before swapping application pods.
3. **Container Rollout:**
   - Deploy backend FastAPI container image.
   - Deploy frontend Next.js 16 container image.
4. **Health Check Probes:**
   - Probe `/api/v1/health` (FastAPI backend).
   - Probe `/_health` / `/` (Next.js frontend).
5. **Rollback Procedure:**
   - Revert traffic to prior container tags if health probe fails within 60s.
   - If schema changes require reversal, run `alembic downgrade -1`.

---

## 4. Hardware & External Infrastructure Prerequisites

Before full operational field release, the following external prerequisites must be completed on site:
- **Prerequisite 1:** Direct physical connectivity between field drone telemetry units (e.g. Pixhawk / Auterion) and the MAVLink edge ingestion gateway.
- **Prerequisite 2:** Staging cluster secret provisioning for live LISA LLM provider credentials.
