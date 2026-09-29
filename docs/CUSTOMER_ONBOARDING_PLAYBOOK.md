# KOTA Aerospace — Customer Onboarding Playbook

## 1. Zero-Code Onboarding Lifecycle

```text
PROSPECT ──► CONTRACTED ──► PROVISIONING ──► CONFIGURATION ──► DATA_MIGRATION ──► INTEGRATION ──► UAT ──► GO_LIVE ──► HYPERCARE ──► ACTIVE
```

### Stage Definitions & Gating Criteria

| Stage | Operational Objective | Verification Gate |
| :--- | :--- | :--- |
| **`PROSPECT`** | Commercial discovery & fleet assessment | Customer aircraft/drone roster established |
| **`CONTRACTED`** | Commercial plan selection & SLA signoff | Selected Plan & Usage Quota confirmed |
| **`PROVISIONING`** | Tenant & initial admin account creation | Call `POST /api/v1/platform/organizations/provision` |
| **`CONFIGURATION`** | Freshness policies & branding configured | Telemetry freshness & branding attributes set |
| **`DATA_MIGRATION`**| Historical flight & maintenance import | CSV/JSON migration batches imported via Import Center |
| **`INTEGRATION`** | Edge devices / SSO / Webhook setup | Register edge gateways via `POST /api/v1/edge/devices` |
| **`UAT`** | Customer validation across dispatch & MRO | Verification of fleet, work orders, and LISA responses |
| **`GO_LIVE`** | Live operational dispatch & flight logging | Transition `onboarding_stage` to `ACTIVE` |
| **`HYPERCARE`** | 30-day intensive telemetry & incident review | Monitor `/api/v1/hypercare/horizon-summary` equivalent |
| **`ACTIVE`** | Standard operational lifecycle | Standard tenant monitoring & usage tracking |

---

## 2. API-Driven Provisioning Runbook

To provision a new customer (e.g. `Apex Global Aero Logistics`):

```bash
curl -X POST "https://api.aerocomply.com/api/v1/platform/organizations/provision" \
  -H "Authorization: Bearer <PLATFORM_ADMIN_JWT>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Apex Global Aero Logistics",
    "industry": "DRONE_UAV",
    "plan_code": "enterprise_custom",
    "admin_email": "ops@apexaero.com",
    "admin_full_name": "Operations Director"
  }'
```

The response returns the created `organization_id`, `subscription_id`, and dispatches an onboarding OTP invitation to the administrator.
