# Usage Metering Specification — KOTA Aerospace Platform

## 1. Overview
KOTA Aerospace employs a deterministic, auditable usage metering subsystem to record consumption across high-volume dimensions without impacting transactional flight or maintenance workflows.

---

## 2. Metered Dimensions

| Meter Code | Aggregation Source | Unit | Period |
| :--- | :--- | :--- | :--- |
| `ACTIVE_USERS` | `users` count with active sessions | Count | Monthly |
| `ASSETS` | Active `assets` table rows | Count | Continuous |
| `FLIGHTS` | Recorded `flights` entries | Count | Monthly |
| `TELEMETRY_EVENTS` | Normalized sensor bursts | Count (Thousands) | Monthly |
| `HUMS_ASSETS` | Assets with active vibration sensors | Count | Continuous |
| `LISA_REQUESTS` | Processed copilot interactions | Count | Daily/Monthly |
| `API_CALLS` | Authenticated API gateway invocations | Count (Thousands) | Monthly |
| `STORAGE_GB` | S3 / Object storage evidence files | Gigabytes | Monthly |

---

## 3. Metering Architecture

```text
Operation / Event
       │
       ▼
Domain Service Execution (Flight, Telemetry, LISA)
       │
       ├─────────────────────────────────┐
       ▼                                 ▼
PostgreSQL Domain Write          Usage Counter Increment
(Authoritative Record)           (TenantUsageLimit / Audit)
                                         │
                                         ▼
                               Platform Usage Dashboard
                               Threshold Alert Trigger (70%, 80%, 90%, 100%)
```

---

## 4. Threshold Alerting Engine
Threshold evaluation runs asynchronously upon metric increment or periodic billing sweeps:
- **`70% Threshold`**: Low-water mark logged for internal capacity planning.
- **`80% Threshold`**: Platform Admin warning indicator + Tenant billing contact advisory.
- **`90% Threshold`**: High-water warning with recommended plan upgrade pathway.
- **`100% Threshold`**: Contractual threshold reached. Depending on configuration:
  - *Standard Tier*: Soft overage logged at contract rate.
  - *Trial / Strict Tier*: Non-critical writes gated (read-only grace state).

---

## 5. Security & Isolation
Usage counters are strictly bounded by `organization_id`. Tenant A's telemetry volume has zero visibility or aggregation effect on Tenant B's utilization quotas.
