# Commercial Entitlement Model — KOTA Aerospace Platform

## 1. Overview
The KOTA Aerospace Commercial Entitlement Engine translates product tiering into deterministic, backend-enforced capabilities. Every capability, API endpoint, navigation surface, and background service respects the tenant's commercial edition, assigned feature grants, and custom overrides.

---

## 2. Product Editions & Feature Tiers

| Feature Identifier | Operations Tier | Intelligence Tier | HUMS Tier | Enterprise Tier | Description |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `fleet_management` | ✅ | ✅ | ✅ | ✅ | Aircraft, drone, and asset registry |
| `flight_operations` | ✅ | ✅ | ✅ | ✅ | Flight logs, cycles, hours tracking |
| `maintenance` | ✅ | ✅ | ✅ | ✅ | Work orders, tasks, MRO workflows |
| `compliance` | ✅ | ✅ | ✅ | ✅ | Regulatory requirements, evidence gates |
| `readiness` | ✅ | ✅ | ✅ | ✅ | Release gates, airworthiness checks |
| `telemetry` | ❌ | ✅ | ✅ | ✅ | Time-series sensor ingestion |
| `hums` | ❌ | ❌ | ✅ | ✅ | Vibration, FFT, Kurtosis, health baselines |
| `m7_intelligence` | ❌ | ✅ | ✅ | ✅ | Proactive signals & anomaly detection |
| `lisa` | ❌ | ✅ | ✅ | ✅ | Grounded CAMO copilot & decision assistant |
| `advanced_decision_support` | ❌ | ❌ | ❌ | ✅ | Multi-scenario trade-off simulation |
| `enterprise_sso` | ❌ | ❌ | ❌ | ✅ | Entra ID / OIDC single sign-on |
| `advanced_audit` | ❌ | ❌ | ❌ | ✅ | Cryptographically linked audit logs |
| `api_access` | ❌ | ❌ | ❌ | ✅ | External API keys & webhooks |
| `hardware_integration` | ❌ | ❌ | ✅ | ✅ | KOTA Edge gateway & hardware telemetry |
| `intelligence_graph` | ❌ | ❌ | ❌ | ✅ | Cross-asset relational intelligence |

---

## 3. Entitlement Hierarchy & Resolution
When checking if a tenant has access to a feature, the engine applies resolution in strict hierarchical order:

1. **System / Platform Admin Bypass:** Platform administrative overrides.
2. **Tenant-Specific Feature Override (`TenantFeatureOverride`):** Explicit enables or disables per tenant.
3. **Plan Assignment (`PlanFeature`):** Features granted by the active subscription tier.
4. **Default:** Deny (`False`).

```python
# app/services/entitlement_service.py
has_access = await EntitlementService.check_feature_access(
    db=db,
    organization_id=org.id,
    feature_name="hardware_integration"
)
```

---

## 4. Usage Limits & Enforcement
Commercial plans specify quantitative quotas via `TenantUsageLimit`:

- `ACTIVE_USERS`: Seat allocation.
- `ASSETS`: Tracked aircraft, drones, and rotorcraft.
- `MONTHLY_FLIGHTS`: Logged flight operations per billing cycle.
- `TELEMETRY_HOURLY_RATE`: Sensor ingest bursts per unit time.
- `LISA_DAILY_QUOTA`: Grounded AI query volume.

Limit states:
- **`NORMAL`** (0% – 79%): Normal operations.
- **`WARNING`** (80% – 99%): Informational banner displayed in management console.
- **`EXCEEDED`** (≥ 100%): Soft or hard limit enforcement based on contract terms.

---

## 5. Subscription Lifecycle
Submissions follow a finite state machine:
- `TRIAL`: Evaluation period with bounded asset limits.
- `ACTIVE`: Commercial production status.
- `SUSPENDED`: Administrative hold (limits or contract breach).
- `EXPIRED`: Grace period following lapsed contract.
- `CANCELLED`: Offboarded tenant, data retained per retention policy.
