# Kota Aerospace — Entitlement Architecture Specification

## 1. Overview
The **Entitlement Engine** (`app/services/entitlement_service.py`) provides single-source-of-truth authorization across the entire platform.

Every protected action evaluates:
```text
Caller (User, Roles)
      ↓
Active Organization Context (Organization.is_active, deleted_at IS NULL)
      ↓
Subscription Status (ACTIVE | TRIALING | PAST_DUE)
      ↓
Product Suite Boundary (AIRCRAFT | DRONE_UAV | HELICOPTER | EVTOL_AAM)
      ↓
Plan Features (PlanFeature.enabled == TRUE)
      ↓
Tenant Feature Overrides (TenantFeatureOverride: ENABLED | DISABLED)
      ↓
Effective Feature Authorization
```

---

## 2. Server-Side Resolution Algorithm
Resolution is computed per-request inside `resolve_entitlements(db, organization_id, as_of=now)` without relying on cached JWT claims or client-side declarations.

```text
1. Organization Status Check:
   - If Organization is SUSPENDED -> Status = SUSPENDED (denies all features).
   - If Organization is soft-deleted -> Status = SUSPENDED (denies all features).

2. Subscription Window Evaluation:
   - Query Subscriptions where status in ('ACTIVE', 'TRIALING', 'PAST_DUE') and starts_at <= as_of.
   - Filter to subscriptions where ends_at is NULL or ends_at > as_of.
   - If no valid subscription found -> Status = NO_SUBSCRIPTION (denies all gated features).
   - If multiple valid subscriptions exist for the same suite -> Status = AMBIGUOUS (fail-closed denial).

3. Base Feature Aggregation:
   - Load PlanFeature rows for the active subscription's plan.
   - For all enabled features, verify that the feature is permitted within the subscription's ProductSuite (rejection of cross-suite contamination).

4. Tenant Overrides Application:
   - Load TenantFeatureOverride rows for the organization.
   - Apply explicit overrides (ENABLED overrides plan default to True; DISABLED overrides plan default to False).

5. Result Assembly:
   - Return EntitlementResolution dataclass with `effective_features`, `suite_code`, `modules`, `pages`, and `usage_limits`.
```

---

## 3. Enforcement Touchpoints

| Layer | Implementation | Behavior on Denial |
|---|---|---|
| **REST API Routes** | `Depends(require_feature("feature_key"))` | `403 Forbidden` (`code="feature_not_entitled"`) |
| **LISA AI Tools** | `_require_entitlement(db, user, tool_spec)` | `ForbiddenError` (`code="forbidden"`) |
| **Frontend Route Guards** | `<RouteEntitlementGuard feature="feature_key">` | Redirect to `/dashboard` or locked state banner |
| **Frontend Navigation** | `navFeatureMap.ts` + `useMyEntitlements()` | Unentitled menu items hidden from sidebar |

---

## 4. Tenant Feature Overrides & Governance
- **Expansive Overrides**: Enabling a feature not included in the customer's plan requires Platform Admin privileges (`PLATFORM_MANAGE`) and generates an immutable `AuditEvent`.
- **Restrictive Overrides**: Disabling a feature explicitly for regulatory or billing hold reasons overrides plan entitlements immediately.
