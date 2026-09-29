# M13 Phase 5: Production Observability & Hypercare Architecture

## 1. Objective & Scope

M13 Phase 5 implements production-grade observability and hypercare monitoring for KOTA Aerospace / AeroComply operations.

Observability is tailored directly to aerospace MRO reliability, telemetry ingestion pipelines, HUMS diagnostics, intelligence signals, and customer operational health.

---

## 2. Architecture & Data Model

### 2.1 Database Entities (Alembic Revision `0056`)

#### `operational_incidents`
Tracks real-time system and operational incidents across tiers:
- `id`: UUID (Primary Key)
- `organization_id`: UUID (Foreign Key `organizations.id`, CASCADE)
- `severity`: `P0` (Critical blocker), `P1` (High), `P2` (Medium), `P3` (Low/Informational)
- `service_name`: `AUTH_SSO` | `TELEMETRY` | `HUMS` | `INTELLIGENCE` | `OPERATIONS` | `INFRASTRUCTURE`
- `title`: Incident title summary
- `description`: Detailed operational error / anomaly context
- `status`: `OPEN` | `ACKNOWLEDGED` | `RESOLVED`
- `asset_id`: Optional UUID foreign key to `assets.id`
- `first_detected_at`: Timestamp of initial detection
- `resolved_at`: Timestamp of formal resolution
- `acknowledged_by_user_id`: UUID of the engineer acknowledging the incident
- `details`: JSONB payload containing error codes, forensic payload hashes, or diagnostic traces

---

## 3. Hypercare Control Center Subsystems

The Hypercare Observability API (`GET /api/v1/hypercare/summary`) aggregates health across:

1. **Platform Status**:
   - `OPERATIONAL`: Zero open P0 incidents and healthy ingestion throughput.
   - `DEGRADED`: Active P1 incidents, critical intelligence signals, or rejected events.
   - `CRITICAL`: Open P0 incident or telemetry ingestion pipeline failure.
2. **Telemetry Subsystem**:
   - Total events received, processed, duplicate, rejected, and failed.
   - Active assets reporting count.
3. **HUMS Subsystem**:
   - Sensor inventory, active sensor count, raw readings count, exceedance count, and candidate fault isolating diagnoses.
4. **Intelligence Subsystem**:
   - Active proactive signal records count, critical signal count, and open compliance/maintenance findings count.
5. **Incidents Management**:
   - Real-time tally of open P0, P1, P2, P3 incidents.
6. **Enterprise Authentication**:
   - Verification of active SSO configuration.
