# KOTA AEROSPACE — M5 IMPORT ARCHITECTURE

## Data Ingestion, Column Mapping, Staging, Validation, and Domain Synchronization

### 1. Ingestion Flow Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                   Customer Legacy File                      │
│                  (.xlsx, .xls, or .csv)                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Phase 1: Parse & File Hash                  │
│  - Compute SHA-256 file hash (anti-replay check)            │
│  - Inspect worksheets (openpyxl read_only stream)           │
│  - Extract raw rows from selected sheet                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Phase 2: Mapping & Normalization                │
│  - Match against tenant-saved mapping or default preset     │
│  - Auto-detect column synonyms (CANONICAL_SYNONYMS)         │
│  - Canonicalize date formats, flight duration, cycles       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               Phase 3: Validation Engine                    │
│  - Row-level invariant checks                               │
│  - Errors (blocking): missing reg, negative hours, dups     │
│  - Warnings: unmatched optional pilot, long durations       │
│  - Match Strategy: MATCH_EXISTING, CREATE_ASSET, SKIP       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Phase 4: Staged Review                      │
│  - Stored in import_jobs with row_results JSON              │
│  - Preview UI displaying KPIs & error filtering             │
│  - Customer Confirmation Gate                               │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             Phase 5: Authoritative Execution                │
│  - flight_service.record_flight()                           │
│  - asset_service.create_asset() (if CREATE_ASSET strategy)  │
│  - Operational utilization recalculation                    │
│  - Maintenance, Compliance & Readiness Synchronization      │
│  - Immutable Audit Event Recording                          │
└─────────────────────────────────────────────────────────────┘
```

---

### 2. Supported Domains & Canonical Schemas

#### A. Fixed-Wing Aircraft (`AIRCRAFT`)
* Required: `registration`, `msn`, `aircraft_type`
* Optional: `manufacturer`, `model`, `serial_number`, `status`, `facility_id`
* Synonyms Handled: `reg`, `tail_number`, `serial_no`, `airframe_type`, `oem`, `make`

#### B. Drone UAVs (`DRONE`)
* Required: `registration`
* Optional: `manufacturer`, `model`, `serial_number`, `status`, `facility_id`
* Synonyms Handled: `drone_id`, `uav_registration`, `callsign`, `serial`

#### C. Flight & Mission Records (`FLIGHT`)
* Required: `registration` (or `aircraft_registration`), `flown_at` (or `flight_date`), duration (`flight_hours` or `duration_minutes`)
* Optional: `cycles`, `flight_number`, `origin`, `destination`, `departure_time`, `arrival_time`, `mission_type`, `status`, `pilot`, `notes`
* Synonyms Handled: `FH`, `FC`, `Date of Flight`, `From`, `To`, `Mission`, `Captain`, `PIC`, `Flight No`

---

### 3. Normalization Invariants

| Field | Accepted Input Formats | Canonical Output |
|---|---|---|
| **Date / Time** | `2026-09-01`, `01/09/2026`, `09/01/2026`, `01-Sep-2026`, ISO 8601 | UTC `datetime` object |
| **Duration** | `1.5` (hours), `90` (mins), `01:30` (HH:MM), `90 min` | Integer minutes (`90`) |
| **Cycles** | `1`, `2`, `"1.0"` | Integer count (`>= 1`) |
| **Asset Reg** | `" vt-abc "`, `"VT-abc"`, `"VT-ABC"` | Upper-case stripped string (`"VT-ABC"`) |

---

### 4. Carry-In Historical Baseline Integration

When a customer migrates a fleet with existing aggregate operational history:
1. Operator creates an `AssetHistoricalBaseline` record with `flight_hours`, `flight_cycles`, and `effective_at`.
2. Any imported or manually entered flight records with `flown_at >= effective_at` are added to the baseline.
3. Pre-baseline historical flights are retained for logbook lineage and audit compliance but excluded from utilization totals to prevent duplicate counting.
4. Downstream state services (`asset_service.get_asset_utilization()`, `flight_service.get_utilization()`, `aerospace_state_engine`) query the active baseline as the carry-in foundation.

---

### 5. Security & Tenant Isolation Model

* **Storage & Processing**: All database queries are filtered by `organization_id == current_user.organization_id`.
* **Mapping Presets**: Mappings saved in `tenant_import_mappings` are strictly isolated by `organization_id`.
* **Asset Lookup**: Registration matching checks only active assets owned by the tenant (`deleted_at IS NULL`). Cross-tenant asset injection or assignment is blocked.
* **Auditability**: Every validation, configuration, and commit action generates an immutable `AuditEvent` record with actor ID, timestamp, and entity diff.
