# KOTA AEROSPACE — M5 SPECIFICATION

## Operational Flight Records + Customer Data Migration + Intelligence Continuity

### 1. Executive Summary

Milestone 5 (M5) provides KOTA Aerospace with an end-to-end customer migration and daily operational recordkeeping engine. It eliminates dual-path bifurcations by ensuring that **legacy data imported from spreadsheets (.xlsx, .xls, .csv)** and **live daily operational records created via UI/API** traverse the exact same authoritative domain services, updating utilization counters, maintenance requirements, compliance obligations, fleet readiness, and decision intelligence identically.

---

### 2. Core Architectural Principles

#### Principle 1: Single Domain Path Invariant (Section 4 / M5.14)
The bulk import mechanism is strictly an ingestion and normalization pipeline, NOT a parallel persistence mechanism. All staged records are committed via:
* `flight_service.record_flight()`
* `asset_service.create_asset()` / `aircraft_service.create_aircraft()`

Direct raw SQL table insertions that bypass validation, lifecycle hooks, or audit events are prohibited.

#### Principle 2: Historical Baseline Carry-In Accounting Rule (Section 8 / M5.13)
For customers migrating from legacy systems with pre-existing flight counters, carry-in values are represented explicitly via the `AssetHistoricalBaseline` entity rather than synthetic flight records.
```text
Current Utilization =
    Active Baseline Counter (effective_at)
    + SUM(Flight Records where flown_at >= Baseline.effective_at)
```
Historical flights occurring prior to the baseline effective date remain queryable in flight history for traceability and auditability, but are excluded from the summation to prevent double-counting.

#### Principle 3: Strict Tenant Isolation (Section 30)
All operations are scoped to the authenticated user's `organization_id`:
* File parsing, file hashing, and import jobs.
* Column mapping presets and defaults.
* Asset lookups and registration matching.
* Carry-in historical baselines.
* Flight and mission records.

Cross-tenant matching or data leakage triggers immediate HTTP 404/403 errors.

---

### 3. Data Models

#### `AssetHistoricalBaseline` (`asset_historical_baselines`)
* `id`: UUID (PK)
* `organization_id`: UUID (Tenant Scope)
* `asset_id`: UUID (FK -> `assets.id`)
* `flight_hours`: Float
* `flight_cycles`: Integer
* `effective_at`: DateTime (UTC)
* `source`: String (e.g., `LOGBOOK_AUDIT`, `LEGACY_MRO`, `MANUAL`)
* `evidence_reference`: String (e.g., certificate / signoff document ID)
* `notes`: String
* `is_active`: Boolean (creating a new baseline deactivates previous baselines)
* `created_by_user_id`: UUID
* `created_at`: DateTime (UTC)

#### `TenantImportMapping` (`tenant_import_mappings`)
* `id`: UUID (PK)
* `organization_id`: UUID (Tenant Scope)
* `domain`: String (`AIRCRAFT`, `DRONE`, `FLIGHT`)
* `name`: String
* `mapping`: JSON dict (`{ "Source Header": "canonical_target" }`)
* `is_default`: Boolean
* `created_by_user_id`: UUID
* `created_at`: DateTime (UTC)

#### `Flight` (`flights` - Extended Operational Fields)
* `flight_number`: String
* `origin`: String (ICAO/IATA/pad ID)
* `destination`: String (ICAO/IATA/pad ID)
* `departure_time`: DateTime (UTC)
* `arrival_time`: DateTime (UTC)
* `mission_type`: String (`PASSENGER`, `CARGO`, `TRAINING`, `SURVEY`, `INSPECTION`, etc.)
* `status`: String (`SCHEDULED`, `EN_ROUTE`, `COMPLETED`, `CANCELLED`, `DIVERTED`)
* `source`: String (`MANUAL`, `EXCEL_IMPORT`, `CSV_IMPORT`, `API`, `TELEMETRY`)
* `source_row_id`: String (import row reference for traceability)

---

### 4. Import Center Pipeline

```text
1. Upload & Hash
   ├── Validate file type (.xlsx, .xls, .csv) and size (<= 50,000 rows)
   ├── Calculate SHA-256 file hash for replay detection
   └── Identify sheet names for multi-sheet workbooks

2. Parsing & Mapping
   ├── Extract rows from selected sheet
   ├── Auto-detect column synonyms (e.g., "Tail Number" -> "registration", "FH" -> "flight_hours")
   └── Apply tenant-saved mapping configuration

3. Normalization
   ├── Dates: ISO 8601, DD/MM/YYYY, MM/DD/YYYY, YYYY/MM/DD, DD-Mon-YYYY
   ├── Durations: decimal hours, HH:MM, integer minutes
   ├── Cycles: integer counts
   └── Strings: trim whitespace, canonical uppercase identifiers

4. Validation Engine
   ├── Errors (blocking): Missing required fields, negative hours/cycles, duplicate identities in file
   └── Warnings (non-blocking): Unmatched optional pilots, long durations (>24h)

5. Asset Matching
   ├── MATCH_EXISTING: Match existing tenant asset by registration or ID
   ├── CREATE_ASSET: Automatically provision new asset upon import confirmation
   └── SKIP: Ignore unmatched records

6. Staging & Customer Confirmation Gate
   ├── User inspects valid rows, warnings, and errors in review UI
   └── Explicit confirmation required before committing transactions

7. Domain Execution
   ├── Executes authoritative flight_service.record_flight()
   ├── Increments asset utilization & battery cycles (for drones)
   └── Feeds maintenance calculations, compliance engine, and readiness
```

---

### 5. API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/data-import/{domain}/validate` | Upload file, parse, map, validate, and stage import job |
| `GET` | `/api/v1/data-import/jobs` | List organization import jobs |
| `GET` | `/api/v1/data-import/jobs/{id}` | Get import job details and row validation results |
| `POST` | `/api/v1/data-import/jobs/{id}/configure` | Reconfigure sheet, column mapping, or match strategy |
| `POST` | `/api/v1/data-import/jobs/{id}/commit` | Authorize and execute domain import transaction |
| `POST` | `/api/v1/data-import/mappings` | Save custom column mapping preset |
| `GET` | `/api/v1/data-import/mappings` | List saved mappings for tenant |
| `DELETE` | `/api/v1/data-import/mappings/{id}` | Delete saved mapping |
| `POST` | `/api/v1/assets/{id}/baseline` | Establish historical carry-in baseline |
| `GET` | `/api/v1/assets/{id}/baseline` | Get active historical baseline for asset |
| `GET` | `/api/v1/assets/{id}/baselines` | List baseline audit history for asset |
| `GET` | `/api/v1/assets/{id}/flights` | List flight history with operational filters |
| `POST` | `/api/v1/assets/{id}/flights` | Record manual operational flight |
