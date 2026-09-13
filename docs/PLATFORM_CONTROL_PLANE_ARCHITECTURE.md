# Platform Control Plane Architecture

Status: PROPOSAL — architecture and design only. No migrations, schema changes, application code, or frontend code were written or modified to produce this document. Every factual claim below is tagged **EXISTING** (verified in the current repository), **PROPOSED** (recommended new design, not built), or **FUTURE** (explicitly deferred, not to be built now).

Scope: this document designs a platform-level "Master Admin / Control Plane" that sits above the existing multi-tenant MRO application (KOTA'S AEROSPACE), to manage tenant lifecycle, subscription plans, feature entitlements, usage limits, platform admins, and platform-level audit — building on, not replacing, what already exists.

---

## 1. Current architecture findings

**EXISTING**, cited to exact files:

- **JWT claims** (`backend/app/core/security.py:35-60`): access token carries `sub` (user id), `type: "access"`, `organization_id`, `roles` (list of role name strings), `email`, `full_name`, plus standard `iat`/`exp`/`jti`. Refresh token carries only `sub`, `type: "refresh"`, `organization_id`. There is no separate "platform identity" claim, no token scope beyond `access`/`refresh`, and no MFA-related claim.
- **Session resolution** (`backend/app/core/deps.py:23-63`, `get_current_user`): decodes the bearer token, re-fetches `Organization` by `organization_id` on **every request**, and rejects with 401 if `org.status == OrganizationStatus.SUSPENDED` — this re-check exists specifically so a token issued before suspension can't keep working for its full TTL (see the docstring at lines 27-36). Roles come straight from the JWT claim, not re-queried per request.
- **No separate platform identity today.** A platform admin is an ordinary `User` row belonging to an ordinary `Organization` row (conventionally one named "Platform Operations", see `backend/scripts/create_platform_admin.py:44-47,67-74`), holding the `PLATFORM_ADMIN` role via the same `UserRole` join table every tenant role uses. There is no `platform_users` table, no separate auth flow, no separate JWT type.
- **Tenancy** (`backend/app/db/base.py:25-36`): `TenantScopedMixin` adds a non-nullable, indexed `organization_id` to any model that mixes it in. `Organization` (`backend/app/models/organization.py`) itself does *not* use the mixin (it is the tenant root). `AuditEvent` **does** use `TenantScopedMixin` (`backend/app/models/audit_event.py:10`), meaning `audit_events.organization_id` is **NOT NULL today** — a real constraint, not an assumption.
- **`Organization.status`** (`backend/app/models/organization.py:7-22`): a plain two-value status (`ACTIVE`/`SUSPENDED`), explicitly documented in-code as "never a billing/subscription engine (none exists in this codebase)". Enforced at both login (`auth_service.authenticate`/`refresh_access_token`, `backend/app/services/auth_service.py:73-116`) and per-request (`get_current_user`).
- **Tenancy isolation proof** (`backend/tests/integration/test_tenancy_isolation.py`): registers two tenants and proves Tenant A's token cannot read/write/resolve Tenant B's aircraft, work orders, evidence, inspections, deferred items, purchase orders, assessments, or Lisa-tool-resolved entities. Cross-tenant lookups return 404, not 403, by deliberate convention (documented in the test file header) so existence isn't leaked. This suite says nothing about platform-layer entitlement — it is scoped to tenant-vs-tenant, not platform-vs-tenant.
- **Authorization** (`backend/app/core/permissions.py`): `Permission` is a flat `StrEnum` of ~26 fine-grained tenant permissions (`aircraft:read/write`, `regulation:*`, `compliance:*`, `evidence:*`, `inspection:*`, `user:manage`, `org:manage`, `audit:read`, `part:*`, `vendor:*`, `procurement:*`, `technician:*`, `assessment:*`) plus exactly **one** platform permission: `PLATFORM_MANAGE` (line 54), explicitly commented as "Deliberately its own permission, never bundled into ORG_ADMIN's grant set." `Role.PLATFORM_ADMIN` (lines 57-70) maps to `{PLATFORM_MANAGE}` **only** (`ROLE_PERMISSIONS[Role.PLATFORM_ADMIN]`, lines 200-202) — deliberately minimal, commented "does not implicitly gain any customer operational-data permission." This is confirmed by a real, already-passing test referenced in `docs/FULL_SYSTEM_AUDIT.md:188` (`test_platform_admin_gets_403_from_organization_users_endpoint`) and by `docs/FULL_SYSTEM_AUDIT.md:40` (`test_platform_admin.py`, `test_platform_api.py`).
- **`backend/app/api/v1/platform.py`** + **`backend/app/services/platform_service.py`**: a real, working, minimal platform control-plane seed. Endpoints: `GET/POST /platform/organizations`, `GET /platform/organizations/{id}`, `POST .../activate`, `POST .../suspend`, `POST .../admins` (create an org's first `ORG_ADMIN`). Every endpoint is gated by `Depends(require_permission(Permission.PLATFORM_MANAGE))` — never a frontend check alone. `platform_service.py`'s module docstring is explicit: "This module never exposes customer *operational* data (aircraft, work orders, etc.) — only tenant metadata and counts needed for administration." Every mutating call writes an `AuditEvent` via `record_audit_event` (organization.create, organization.{status}, organization.admin_created).
- **Bootstrap** (`backend/scripts/create_platform_admin.py`): the *only* way to create the first `PLATFORM_ADMIN` is a DB-connected CLI script — there is deliberately no public API for granting `PLATFORM_MANAGE` (the docstring says so explicitly), because it cannot be self-granted through any endpoint.
- **Audit** (`backend/app/services/audit_service.py`, `backend/app/models/audit_event.py`): a thin insert-only helper — `record_audit_event(db, organization_id, user_id, action, entity_type, entity_id, metadata)`. `organization_id` is required (non-nullable). Append-only is enforced at the **database level**, not just by convention: migration `0002_audit_events_immutability.py` creates a Postgres trigger function `reject_audit_event_mutation()` bound to `BEFORE UPDATE` and `BEFORE DELETE` on `audit_events`, raising an exception on either. This is a hard DB-level guarantee, independent of the app.
- **Frontend**: a single Next.js 14 app (no subdomain routing found anywhere in the repo). The platform area exists today at `frontend/app/(app)/platform/organizations/page.tsx` — inside the *same* app-shell route group as every tenant page (`app/(app)/*`), sharing the same `Sidebar`, same session/auth context, same layout. `Sidebar.tsx:109-121` conditionally appends a "Platform" nav group only when `user.roles.includes("PLATFORM_ADMIN")`, with an explicit comment that this is a UX convenience only — "the backend independently enforces PLATFORM_MANAGE on every /platform/* call regardless of what's shown." The organizations page itself calls out (lines 3-7) that it is real-mode only, cross-tenant staff tooling, gated server-side.
- **Migrations**: 23 linear migrations, single head, `0023_aircraft_registration_unique.py`. Relevant ones: `0001_initial_foundation`, `0002_audit_events_immutability` (the trigger), `0021_organization_status` (added `Organization.status`). No subscription/plan/entitlement tables exist anywhere in the chain.
- **32 API routers** in `backend/app/api/v1/`: aircraft, aog, assessments, auth, compliance, control_center, data_import, deferred_items, evidence, health, inspections, inventory, lisa, maintenance, part_requirements, parts, platform, proactive, procurement, purchase_orders, receiving, regulatory, release_readiness, tat, technicians, users, vendor_part_availability, vendors, warehouses, work_orders. Most have real backend depth (per `docs/FULL_SYSTEM_AUDIT.md`); frontend real-mode wiring is confirmed for far fewer pages (~13/82), which matters for how aggressively feature-gating should be enforced client-side vs. server-side.

---

## 2. Recommended platform identity architecture

**Decision: Option B — keep the existing `User` + `PLATFORM_ADMIN` role as the platform identity; add a separate platform-authorization layer (new platform-scoped permissions and a small set of platform-scoped tables) rather than building a parallel `platform_users` system.**

Why (derived directly from Section 1, not a generic pattern):

- A dedicated `PLATFORM_ADMIN` role, a dedicated `PLATFORM_MANAGE` permission, a dedicated router/service pair, and a bootstrap script **already exist and already work**, with tests proving the isolation property that matters most (`PLATFORM_ADMIN` gets 403 on tenant-data endpoints). Building a second, parallel `platform_users` identity system (Option A) would duplicate `User`/`UserRole`/JWT/password-hashing/session machinery that is already correct, well-tested, and audited — for no isolation benefit, since the isolation already comes from **permission scoping**, not from identity separation.
- The existing design's own in-code comments (`permissions.py:65-70`, `platform_service.py:1-9`) already state the intended shape: a platform operator is "still belongs to exactly one organization... but PLATFORM_MANAGE grants them access to cross-tenant endpoints." That is Option B by construction. Reversing this into Option A would be fighting the codebase's own stated design intent for no documented reason.
- Option C (e.g., an external IdP / separate auth service for platform staff) is not justified by anything found: there is one JWT scheme, one `security.py`, one `deps.py`, and introducing a second auth stack would roughly double the auth attack surface and testing burden for a team that has one platform admin endpoint group today.

What Option B concretely adds (**PROPOSED**, not built):

- New fine-grained platform permissions (Section 8) alongside the existing `PLATFORM_MANAGE`, following the exact same `Permission` StrEnum + `ROLE_PERMISSIONS` pattern already in `permissions.py` — no new enum type, no new mechanism.
- The existing hard rule stays intact and should be treated as load-bearing going forward: **`PLATFORM_ADMIN` must never be added to a tenant's `ROLE_PERMISSIONS` set, and no tenant role may be granted any new platform permission.** Any milestone that touches `permissions.py` must keep the existing `test_platform_admin_gets_403_from_organization_users_endpoint`-style test passing (Section 18 expands this).
- A platform admin who genuinely needs to see a tenant's operational data for support must go through the **explicit, audited, non-impersonation access-request flow** in Section 16 (FUTURE) — never through implicit permission escalation.

---

## 3. Recommended tenant entitlement architecture

**PROPOSED.** Entitlement answers "can organization X use feature Y right now" and is a **separate concern** from RBAC (which answers "can this user, within their org, perform this action"). Composition (detailed in Section 10):

```
tenant_has_feature(org_id, FEATURE_X)
  = org.status != SUSPENDED
    AND FEATURE_X in effective_features(org.plan)      # plan defaults
    AND NOT FEATURE_X in tenant_feature_overrides(org)  # per-tenant override, either direction
```

Two layers, mirroring the plan/feature split already implicit in "subscription plans" + "feature entitlements" from the brief:

1. **Plan-level defaults** — what a `Plan` includes out of the box (Section 4/6).
2. **Tenant-level overrides** — a small, explicit override table so a platform admin can grant/revoke a single feature for a single tenant without moving them to a different plan (e.g., a pilot customer trialing one module early). Overrides are rare, auditable exceptions, not the primary mechanism — most tenants should need zero override rows.

Entitlement is evaluated **server-side only**, at the same dependency-injection layer as `require_permission` (Section 7) — never trusted from the frontend, consistent with the codebase's existing stated philosophy (`permissions.py:3-4`: "Permission checks happen at the service layer... never only in the frontend").

---

## 4. Recommended plan architecture

**PROPOSED.** Given the codebase's current maturity (no billing engine exists; `Organization.status` docstring explicitly disclaims any billing intent), the plan model should be intentionally minimal:

- A `Plan` is a named, platform-managed catalog row (e.g., `STARTER`, `PROFESSIONAL`, `ENTERPRISE`) with a set of included `FEATURE_*` identifiers and optional coarse usage limits (Section 11).
- Plans are **platform-scoped, not tenant-scoped** — they are catalog/reference data, analogous to how `RegulatoryAuthority`/`RegulatoryDocument` are already global reference tables that deliberately don't use `TenantScopedMixin` (per the comment in `db/base.py:28-31`). This is a direct precedent already in the codebase for "global, non-tenant-owned catalog table."
- Each `Organization` gets exactly one active `plan_id` at a time (a foreign key, not a duplicated status field — see Section 9's discussion of not conflating this with `Organization.status`).
- No proration, billing cycles, invoicing, or payment fields belong in this layer yet — that is explicitly Section 16 (FUTURE). The MVP plan table only needs to answer "what features does this org get by default."

---

## 5. Recommended feature catalog derived from the repository

Identifiers follow `Permission`'s existing `SCREAMING_SNAKE_CASE`-adjacent convention (module-level, coarse — see rationale below). One row per real backend domain, cross-referenced against the 32 routers in `backend/app/api/v1/`.

| Feature ID (PROPOSED) | Backend domain (EXISTING router/service) | Gateable today (MVP) | Notes |
|---|---|---|---|
| `FEATURE_AIRCRAFT` | `aircraft.py` | Yes | Core; likely always-on for every plan, listed for completeness |
| `FEATURE_WORK_ORDERS` | `work_orders.py` | Yes | Deep backend coverage per audit |
| `FEATURE_TASK_CARDS` | (tasks nested under work_orders) | Yes | Bundle with `FEATURE_WORK_ORDERS` at MVP granularity |
| `FEATURE_TECHNICIANS` | `technicians.py` | Yes | |
| `FEATURE_EVIDENCE` | `evidence.py` | Yes | |
| `FEATURE_INSPECTIONS_RII` | `inspections.py` | Yes | RII independence logic already enforced in service layer regardless of entitlement — entitlement only gates access to the module, not the RII rule itself |
| `FEATURE_DEFERRED_MEL` | `deferred_items.py` | Yes | |
| `FEATURE_RELEASE_READINESS` | `release_readiness.py` | Yes | Recently wired REAL-mode per git log (`48f6219`) |
| `FEATURE_AOG` | `aog.py` | Yes | |
| `FEATURE_MAINTENANCE_PROGRAM` | `maintenance.py`, `control_center.py` | Yes | |
| `FEATURE_INVENTORY` | `inventory.py` | Yes | |
| `FEATURE_PARTS` | `parts.py`, `part_requirements.py` | Yes | |
| `FEATURE_PROCUREMENT` | `procurement.py`, `purchase_orders.py`, `receiving.py` | Yes | Bundle at MVP granularity — these three are one procurement workflow |
| `FEATURE_VENDOR_INTELLIGENCE` | `vendors.py`, `vendor_part_availability.py` | Yes | |
| `FEATURE_COMPLIANCE` | `compliance.py`, `regulatory.py` | Yes | |
| `FEATURE_ASSESSMENTS` | `assessments.py` | Yes | Confirmed API-integration-tested per audit |
| `FEATURE_LISA` | `lisa.py` | **Needs more maturity first** | Cross-cutting tool layer that reaches into most other domains; gating it independently of the domains it reads from is architecturally tricky — recommend gating it as an add-on only after the domain-level features it depends on are stable |
| `FEATURE_DATA_IMPORT` | `data_import.py` | **Needs more maturity first** | Frontend real-mode wiring unconfirmed per `docs/FULL_SYSTEM_AUDIT.md:109` |
| `FEATURE_TAT_ANALYTICS` | `tat.py` | **Needs more maturity first** | Narrow router, unclear frontend consumption |
| `FEATURE_PROACTIVE` | `proactive.py` | **Needs more maturity first** | Same reason |
| `FEATURE_WAREHOUSES` | `warehouses.py` | Yes | Bundle with `FEATURE_INVENTORY` at MVP granularity |

**Design note (explicit, per the task brief):** gating should start **module-level (coarse)**, matching how `Permission` itself groups by domain rather than by individual field or action. Sub-feature gating (e.g., gating RII specifically within inspections, or gating PO approval specifically within procurement) is FUTURE work and should not be attempted until the coarse layer is proven, given that most of these domains have real backend depth but shallower, unconfirmed frontend real-mode wiring (~13/82 pages per the audit) — fine-grained gating on top of unconfirmed frontend wiring would be gating a feature the frontend may not even fully exercise yet.

---

## 6. Recommended database tables

All **PROPOSED**. Kept deliberately minimal — five new tables, justified individually. No existing table is altered except where explicitly noted (Section 12 discusses `audit_events` and concludes no schema change is needed there).

### 6.1 `plans` (platform-scoped)
- Purpose: catalog of subscription plans and their default feature/limit sets.
- Key columns: `id` (UUID PK), `key` (short stable string, e.g. `STARTER`, unique), `name`, `is_active` (bool), `created_at`.
- Relationships: referenced by `organizations.plan_id` (new nullable FK, see 6.2) and by `plan_features`/`plan_limits`.
- Tenancy scope: platform-scoped (no `organization_id` — global reference data, same category as `RegulatoryAuthority`).
- Indexes/constraints: unique on `key`.
- Audit: plan CRUD is a platform action → `AuditEvent` with `organization_id = NULL`-handling per Section 12.

### 6.2 `plan_features` (platform-scoped)
- Purpose: many-to-many between `plans` and feature identifiers (Section 5's catalog).
- Key columns: `id`, `plan_id` (FK → `plans.id`), `feature_key` (string, one of the `FEATURE_*` identifiers — stored as a validated string, not a DB enum, so the catalog can grow without a migration each time, mirroring how `Permission` is an application-level enum rather than a DB enum today).
- Relationships: `plans` 1:N `plan_features`.
- Tenancy scope: platform-scoped.
- Indexes/constraints: unique on `(plan_id, feature_key)`.
- Audit: covered by the plan-change audit event, not per-row.

### 6.3 `tenant_feature_overrides` (tenant-scoped)
- Purpose: rare, explicit per-tenant exception to plan defaults (grant a feature not in the plan, or revoke one that is).
- Key columns: `id`, `organization_id` (FK, **this table uses `TenantScopedMixin`** — it is about one tenant), `feature_key`, `enabled` (bool — true=grant override, false=revoke override), `reason` (text, required — every override should carry a human-readable justification since it's an exception path), `created_by_user_id` (the platform admin who set it), `created_at`, `expires_at` (nullable — supports time-boxed trial grants without new code).
- Relationships: belongs to one `Organization`.
- Tenancy scope: tenant-scoped, but only ever written by platform admins (`PLATFORM_MANAGE`-gated), never by tenant users.
- Indexes/constraints: unique on `(organization_id, feature_key)` (one override row per feature per tenant — flipping it is an update, not a new row, so history lives in `AuditEvent`, not here).
- Audit: every write → `AuditEvent` (`platform.entitlement.override_set`), `organization_id` = the tenant's id (this one legitimately has a real tenant to attribute to — see Section 12).

### 6.4 `organizations.plan_id` (new column on existing table)
- Purpose: which plan an organization is currently on.
- Column: `plan_id` (UUID, nullable FK → `plans.id`, nullable so existing/legacy orgs without a plan don't break; a NULL plan should be treated by `tenant_has_feature` as "no default features," forcing an explicit assignment before entitlement-gated features work — a deliberate fail-closed default).
- This is an additive column on `Organization`, not a new status field — see Section 9 for why it must stay separate from `Organization.status`.
- Index: on `plan_id` for the "list orgs by plan" platform-admin query.

### 6.5 `tenant_usage_limits` / counters (tenant-scoped) — see Section 11 for full design
- Purpose: coarse usage ceilings (e.g., max users, max aircraft) per tenant, sourced from the plan but overridable per-tenant like features.
- Key columns: `id`, `organization_id`, `limit_key` (e.g. `MAX_USERS`, `MAX_AIRCRAFT`), `limit_value` (int, nullable = unlimited), `created_by_user_id`, `created_at`.
- Tenancy scope: tenant-scoped, platform-admin-written only.
- Indexes/constraints: unique on `(organization_id, limit_key)`.
- Audit: every write → `AuditEvent`.

**Explicitly not proposed:** a separate `platform_users` table (see Section 2), a separate `platform_audit_events` table (see Section 12 — reuse `AuditEvent`), a generic `subscriptions`/`invoices`/`billing_events` table (FUTURE, Section 16), and per-action fine-grained entitlement rows (Section 5's coarse-first rationale).

---

## 7. Authorization flow

Mapped onto the **existing** FastAPI dependency-injection chain in `deps.py`, adding one new dependency stage rather than inventing a new mechanism:

```
Request
  → Depends(get_current_user)                         # EXISTING: decodes JWT, re-checks org.status==SUSPENDED, binds identity
  → Depends(require_permission(Permission.X))          # EXISTING: RBAC check against ROLE_PERMISSIONS
  → Depends(require_feature(Feature.Y))                # PROPOSED: new dependency, entitlement check
  → route handler / service function
```

- `require_feature(feature: Feature)` (**PROPOSED**, lives in `deps.py` next to `require_permission`, same shape): looks up `current_user.organization_id`, calls the new `entitlement_service.tenant_has_feature(db, organization_id, feature)` (Section 10), and raises `ForbiddenError` (reusing the existing exception type from `app/core/errors.py`, same as `require_permission` does) if not entitled.
- Ordering matters and should be enforced by convention (and a linter/test, Section 18): `require_permission` before `require_feature` on any endpoint that needs both, so a user who lacks the RBAC permission gets the RBAC error, not an entitlement error that would leak plan information to someone who shouldn't even be evaluating it.
- Platform endpoints (`/platform/*`) never pass through `require_feature` — they are platform administration, not tenant feature-gated. They stay exactly as they are today: `Depends(require_permission(Permission.PLATFORM_MANAGE))` (plus new finer platform permissions per Section 8).
- Tenant-data endpoints gain `require_feature` only for the modules that end up in the MVP-gateable set (Section 5); ungated modules are simply not wrapped, so this is additive and low-risk to existing routers.

---

## 8. Master Admin permission model

The user's 10 MVP capabilities, mapped against reusing the existing `PLATFORM_MANAGE` vs. needing a new `Permission` enum value (same `StrEnum`/`ROLE_PERMISSIONS` pattern as today, no new mechanism):

| # | Capability | Reuse `PLATFORM_MANAGE`? | New permission needed (PROPOSED) |
|---|---|---|---|
| 1 | Create / suspend / reactivate tenant orgs | Yes — already implemented exactly this way | — |
| 2 | Create a tenant's first admin user | Yes — already implemented | — |
| 3 | View platform-wide list of tenants + basic counts | Yes — already implemented (`list_organizations`) | — |
| 4 | Assign a plan to a tenant | No | `PLATFORM_PLAN_MANAGE` |
| 5 | Grant/revoke a per-tenant feature override | No | `PLATFORM_ENTITLEMENT_MANAGE` |
| 6 | Set/view per-tenant usage limits | No | `PLATFORM_ENTITLEMENT_MANAGE` (shared with #5 — both are "entitlement configuration," same authority tier) |
| 7 | View platform-wide audit log (cross-tenant) | Partially — `AUDIT_READ` today is tenant-scoped (a tenant user reads their own org's events); a platform admin needs cross-tenant read | `PLATFORM_AUDIT_READ` (deliberately separate from tenant `AUDIT_READ`, same reasoning as why `PLATFORM_MANAGE` was kept separate from `ORG_MANAGE`) |
| 8 | Create/manage other platform admins | No — this is the highest-risk capability (privilege escalation surface) | `PLATFORM_ADMIN_MANAGE` — deliberately its own permission, not folded into `PLATFORM_MANAGE`, so that day-to-day tenant-lifecycle admins don't automatically get the power to mint new platform admins |
| 9 | View a read-only rollup of a tenant's usage against its limits | No new capability, but no operational data — reuse `PLATFORM_ENTITLEMENT_MANAGE`'s read path (or split a `_READ`/`_WRITE` pair if the team wants least-privilege read-only platform staff) | `PLATFORM_ENTITLEMENT_MANAGE` (or split later) |
| 10 | Request time-boxed, audited support access to a tenant (no impersonation) | No — this is FUTURE (Section 16), needs its own permission when built | `PLATFORM_SUPPORT_ACCESS_REQUEST` (FUTURE, not MVP) |

New MVP permissions to add to `Permission` (**PROPOSED**): `PLATFORM_PLAN_MANAGE`, `PLATFORM_ENTITLEMENT_MANAGE`, `PLATFORM_AUDIT_READ`, `PLATFORM_ADMIN_MANAGE`. All four should default onto `Role.PLATFORM_ADMIN` at MVP (a single platform-operator role is fine for a small internal ops team of one company), but keeping them as **separate enum values from day one** — rather than bundling everything into `PLATFORM_MANAGE`c— means a future "junior platform support" role with only `PLATFORM_AUDIT_READ` + `PLATFORM_ENTITLEMENT_MANAGE`(read) is a `ROLE_PERMISSIONS` edit, not a schema change.

---

## 9. Tenant lifecycle model

Build directly on **existing** `Organization.status` (`ACTIVE`/`SUSPENDED`) — do not add a parallel status field.

**PROPOSED** states and transitions (keeping `OrganizationStatus` as the single source of truth for "can this org's users log in / keep using the app at all"):

```
(created) --activate (implicit, default)--> ACTIVE
ACTIVE --platform admin suspends--> SUSPENDED
SUSPENDED --platform admin reactivates--> ACTIVE
```

This is exactly what `platform.py`'s `/activate` and `/suspend` endpoints already do — no change needed to the enum or the enforcement points (`get_current_user`, `auth_service.authenticate`, `auth_service.refresh_access_token`).

The **plan** (`organizations.plan_id`, Section 6.4) is an orthogonal axis, not a new status:

- `Organization.status` answers: *is this tenant allowed to use the system at all* (login-level gate, already enforced).
- `plan_id` + entitlement tables answer: *which features/limits does this tenant get while active* (feature-level gate, new).

Conflating these (e.g., adding `TRIAL`, `PAST_DUE`, `CANCELED` values directly into `OrganizationStatus`) is explicitly discouraged here — see Section 19 (Risks) for why. If a future billing system needs richer lifecycle states, they should live in a separate `subscription_status` concept (FUTURE, Section 16), leaving `Organization.status` as the narrow, already-battle-tested "can anyone log in" switch it is today.

---

## 10. Feature evaluation model

**PROPOSED** new module: `backend/app/services/entitlement_service.py`, following the codebase's existing one-file-per-domain convention (mirrors `platform_service.py`, `audit_service.py`).

Canonical responsibility, one function:

```python
def tenant_has_feature(db: Session, *, organization_id: UUID, feature: Feature) -> bool:
    org = db.get(Organization, organization_id)
    if org is None or org.status == OrganizationStatus.SUSPENDED:
        return False
    override = _get_override(db, organization_id, feature)
    if override is not None and not _expired(override):
        return override.enabled
    if org.plan_id is None:
        return False  # fail closed: no plan assigned means no gated features
    return feature.value in _plan_feature_keys(db, org.plan_id)
```

Composition order, matching Section 3: suspension check first (fail fast, reuses the same `OrganizationStatus` check `get_current_user` already performs — cheap, same indexed lookup pattern), then tenant override (explicit exception wins in either direction), then plan default (fallback). This function is the single place the logic lives; `require_feature` in `deps.py` (Section 7) is a thin wrapper that calls it and raises `ForbiddenError`. No other module should re-implement this check — any place needing "does this org have feature X" imports `entitlement_service`, the same way permission checks all funnel through `permissions_for_roles`.

---

## 11. Usage/limits model

**PROPOSED**, intentionally coarse for MVP: numeric ceilings, not real-time metering.

- Candidate limits, chosen because they're already countable from existing data the platform service already queries (`platform_service.list_organizations` already computes `user_count` and `aircraft_count` per org): `MAX_USERS`, `MAX_AIRCRAFT`. Both map directly onto counts `platform_service.py` already knows how to compute (lines 29-40), so the read side of this feature requires no new query pattern.
- Stored in `tenant_usage_limits` (Section 6.5): a `(organization_id, limit_key) → limit_value` row, `NULL` value = unlimited (the default for every tenant unless a platform admin sets one).
- Enforcement is **advisory/reporting only at MVP** — i.e., the platform admin dashboard shows "12 / 25 users" as a rollup, and the existing `user:manage`/`org:manage` write paths (e.g., inviting a new user) should ideally consult this before allowing the write, but wiring hard enforcement into `users.py`'s create-user path is scoped as a fast-follow milestone (Section 20), not part of the initial control-plane cut, to avoid touching tenant-facing write paths in the same change that introduces the platform layer.
- No time-series usage tracking, no overage billing, no soft/hard limit tiers at MVP — that's FUTURE (Section 16).

---

## 12. Platform audit model

**Decision: reuse and extend the existing `AuditEvent`/`audit_service` architecture — do not create a parallel `platform_audit_events` table.**

Key constraint verified in Section 1: `AuditEvent` uses `TenantScopedMixin`, so `audit_events.organization_id` is **NOT NULL today**. This is a real constraint, not hand-waving, and it already dictates the design:

- **Tenant-relevant platform actions** (suspend org X, assign a plan to org X, set a feature override for org X, set a usage limit for org X) naturally have a real tenant to attribute to — `organization_id` = that tenant's id, exactly as `platform_service.py` already does today for `platform.organization.create`/`platform.organization.{status}`/`platform.organization.admin_created`. No schema change needed for these; they fit the existing model as-is.
- **Genuinely platform-only actions with no single tenant subject** (e.g., "platform admin X created platform admin Y," "plan `PROFESSIONAL`'s feature set was edited") do **not** have a natural `organization_id`. Given the NOT NULL constraint, two options:
  1. **PROPOSED (recommended): attribute these to the acting platform admin's own organization** (the "Platform Operations" org that already exists per `create_platform_admin.py`'s bootstrap convention). This requires **zero migration** — the column stays NOT NULL, the append-only trigger is completely unaffected, and `AuditEvent`'s existing shape, indexes, and every consumer of it keep working unchanged. The `action` string (e.g., `platform.admin.create`, `platform.plan.feature_set_updated`) and `event_metadata` JSON already carry enough detail to distinguish "this event is about the platform itself" from "this event is about tenant X," so nothing is lost — a platform-audit view simply filters by `action LIKE 'platform.%'` rather than by a nullable `organization_id`.
  2. Alternative (not recommended): make `organization_id` nullable. Rejected because it would touch a column relied on by the append-only trigger's semantics is fine (the trigger doesn't care about nullability) but it *would* require an actual migration, would weaken a currently-strong invariant ("every audit event belongs to a tenant") for a benefit (a `NULL` instead of "attribute to platform's own org") that's marginal, and would require every existing/future consumer of `AuditEvent.organization_id` to add null-handling. Not justified.
- **`Permission.AUDIT_READ` stays tenant-scoped** (a tenant user reads only their own org's `audit_events`, unchanged). The new `PLATFORM_AUDIT_READ` (Section 8) permission gates a **new read path** in `platform_service.py`/`platform.py` — `GET /platform/audit-events` — that queries `AuditEvent` **without** filtering by the caller's own `organization_id` (same "deliberately not org-scoped by the caller" pattern `platform_service.py`'s docstring already describes for its other functions), optionally filtered by a `target_organization_id` query param for "show me all platform+tenant events touching org X."
- The append-only DB trigger (`0002_audit_events_immutability.py`) needs **no changes** — it already enforces immutability at the row level regardless of what `organization_id` value is used, so platform events get the same tamper-evidence guarantee tenant events already have.

---

## 13. Security model

Addressing each item explicitly:

- **Platform admin authentication**: reuses the existing `auth_service`/JWT flow unchanged (Section 2's Option B). No new login surface to secure.
- **MFA readiness**: **not present today** for any user, including `PLATFORM_ADMIN` (no MFA claim, no MFA table). Given `PLATFORM_ADMIN` is the highest-privilege role in the system, MFA for platform admins specifically should be treated as a near-term FUTURE priority (Section 16) — the JWT/`User` schema would need a `mfa_enabled`/`mfa_secret` addition, which is a real migration; not attempted here per the "no migrations" constraint of this task.
- **Session expiration**: reuses existing `access_token_expire_minutes`/`refresh_token_expire_days` settings unchanged. No change proposed; note that platform sessions might reasonably want a *shorter* access-token TTL than tenant sessions given the blast radius of a stolen platform token — worth a config split in a later milestone (FUTURE), not required for MVP.
- **Privilege escalation**: mitigated by keeping `PLATFORM_ADMIN_MANAGE` (Section 8) as its own permission, separate from `PLATFORM_MANAGE` — so compromising a day-to-day platform-ops account (tenant lifecycle only) does not automatically grant the ability to mint new platform admins. There is still no self-service grant path for any platform permission — the bootstrap script's "cannot be self-granted" design principle should extend to all new platform permissions too (only an existing `PLATFORM_ADMIN_MANAGE` holder, via an authenticated endpoint, can grant platform roles — never a raw script default for anyone but the very first bootstrap).
- **Tenant isolation**: entitlement checks (Section 10) never weaken `TenantScopedMixin`-based row isolation — they are an *additional* gate layered before a tenant-scoped query runs, not a replacement for `organization_id` filtering anywhere. `require_feature` never bypasses `require_permission`, and neither ever substitutes for a service-layer `organization_id` filter.
- **CSRF**: out of scope for this design — the existing app is a bearer-token API (not cookie-session-based per what's in `security.py`), so CSRF is already largely mitigated by the current auth scheme; nothing about the platform layer changes that.
- **Auditability**: every platform mutation (org create/suspend/activate, admin create, plan assignment, entitlement override, admin grant) must call `record_audit_event` — same discipline `platform_service.py` already follows for its four existing actions. This should be enforced by a service-layer convention/test (Section 18), not just a code-review habit.
- **Accidental cross-tenant access**: mitigated structurally by `platform_service.py`'s stated boundary ("never exposes customer operational data") — the control plane's new tables (`plans`, `plan_features`, `tenant_feature_overrides`, `tenant_usage_limits`) contain zero operational MRO data (no aircraft, work order, or evidence content), so even a bug in the platform layer cannot leak tenant business data through it.
- **Entitlement bypass**: mitigated by making `entitlement_service.tenant_has_feature` the single choke point (Section 10) and by ordering `require_feature` after `require_permission` at the dependency level, never letting a route call a service function directly without going through the FastAPI dependency chain (the existing codebase convention per `deps.py`'s docstring already states permission checks happen "at the service layer... never only in the frontend" — the same discipline applies to entitlement).
- **Suspended tenant access**: already handled — `OrganizationStatus.SUSPENDED` is checked in `get_current_user` on every request (Section 1) and `entitlement_service.tenant_has_feature` independently re-checks it too (Section 10), so a suspended org fails both the login-level gate and the feature-level gate even if one were somehow bypassed.
- **Platform-admin separation**: `PLATFORM_ADMIN` already cannot read tenant operational data (Section 1's cited test). This document does not weaken that anywhere — no new permission introduced in Section 8 grants any tenant-domain `Permission` value.
- **Emergency account recovery**: not designed here (no password-reset flow exists in the repo for any user type, tenant or platform, per what's in `auth_service.py`/`auth.py`) — this is a pre-existing gap in the whole application, not specific to the platform layer, and is out of scope to fix as part of this proposal. Flagging it as a cross-cutting FUTURE item (Section 16) since a locked-out platform admin with no recovery path is an operational risk once this layer is load-bearing.

---

## 14. Admin URL recommendation

**Recommendation: keep the platform admin area inside the existing single Next.js app at `app.kotasaerospace.com/platform-admin` (or the current `/platform` path), not a separate `admin.kotasaerospace.com` subdomain.**

Justification against the *actual* current frontend architecture, not generic best practice:

- The repo has **one** Next.js app, **one** route-group shell (`app/(app)/*`), **one** `Sidebar`, **one** session context. The platform area already lives inside that same shell (`frontend/app/(app)/platform/organizations/page.tsx`) and already reuses the shared `Breadcrumbs`, `DataTable`, `StatusBadge`, `RealDataPanel` components.
- There is **no subdomain routing infrastructure** anywhere in the repo (no multi-app monorepo split, no separate Vercel project config found, no separate build target) — per the deployment-hardening docs referenced in this task's own context. Standing up `admin.kotasaerospace.com` would require: a new Vercel domain + DNS record, a decision about whether it's a second Next.js app or a second route group with rewrites, a second deploy pipeline or a shared-but-conditionally-rendered build, and a new session-sharing story across origins (cookies/tokens don't cross subdomains by default without extra CORS/cookie-domain configuration) — none of which exists today and all of which is new operational surface for a product that, per the audit, is still working through basic deployment hardening (`docs/FULL_SYSTEM_AUDIT.md` notes active DB-timeout/bootstrap hardening commits as recent, ongoing work).
- Security isolation for the platform area does **not** depend on URL/domain separation in this codebase — it depends entirely on server-side `PLATFORM_MANAGE`-family permission checks (Section 1, Section 13), which are already domain-agnostic. A separate subdomain would add operational complexity without adding a security boundary the backend doesn't already enforce.
- Downside acknowledged: sharing one app means a platform-admin bug in shared components (`Sidebar`, layout, session context) has a larger blast radius than if it were a fully separate app. Given the current single-app maturity level, this is judged the lower-risk tradeoff versus taking on subdomain infrastructure the team hasn't built yet. Revisit this decision only if/when the platform area grows enough functionality (billing dashboards, cross-tenant analytics, support-access tooling) to justify its own deploy lifecycle — that would be a deliberate future re-architecture, not a default.

---

## 15. MVP scope

The user's 10 Master Admin capabilities, scoped to what's buildable directly on top of what exists (cross-referenced to Sections 6-8):

1. Create / suspend / reactivate tenant organizations — **already built** (`platform.py`/`platform_service.py`), no new work.
2. Create a tenant's first admin user — **already built**, no new work.
3. View platform-wide tenant list with basic counts — **already built**, no new work.
4. Assign a plan to a tenant — new: `plans`, `plan_features`, `organizations.plan_id`, `PLATFORM_PLAN_MANAGE`, one new endpoint (`POST /platform/organizations/{id}/plan`).
5. Grant/revoke a per-tenant feature override — new: `tenant_feature_overrides`, `PLATFORM_ENTITLEMENT_MANAGE`, two endpoints (set/clear override).
6. Set/view per-tenant usage limits — new: `tenant_usage_limits`, reuse `PLATFORM_ENTITLEMENT_MANAGE`, two endpoints.
7. View platform-wide (cross-tenant) audit log — new: `PLATFORM_AUDIT_READ`, one new read endpoint over the existing `AuditEvent` table (Section 12), no schema change.
8. Create/manage other platform admins — new: `PLATFORM_ADMIN_MANAGE`, endpoints to grant/revoke `PLATFORM_ADMIN`-family roles on an existing user (never self-service signup) — this is the highest-scrutiny milestone, should ship with its own focused test suite before anything else in this list depends on it.
9. Read-only tenant usage rollup — new: a GET endpoint composing `tenant_usage_limits` + the counts `platform_service` already computes (Section 11); no new write surface.
10. Time-boxed audited support access request — **explicitly FUTURE, not MVP** (Section 16) — flagged by the user's own framing as a "eventually" item; scoping it into MVP would require designing the request/approve/expire state machine, which deserves its own dedicated design pass rather than being squeezed into this cut.

All nine MVP items reuse the existing JWT/permission/audit machinery; the only genuinely new *infrastructure* is the five tables in Section 6 and the four new permissions in Section 8.

---

## 16. Future scope

Explicitly **FUTURE** — deferred, not designed in detail here beyond noting the shape:

- **Billing**: invoices, payment methods, proration, dunning. Would need a genuine `subscriptions`/`invoices` schema and likely a third-party billing provider integration (Stripe or similar) — nothing in the repo today suggests a preferred vendor.
- **Trials**: a time-boxed plan assignment with auto-expiry/downgrade — layers on top of `organizations.plan_id` (Section 6.4) plus an `expires_at`, and a scheduled job to downgrade on expiry (no job/scheduler infrastructure currently exists in the repo, so this needs its own investigation).
- **Upgrades/downgrades**: changing `plan_id` is mechanically trivial once Section 6.4 exists; the FUTURE work is the *policy* (proration, immediate vs. end-of-cycle, notifying the tenant) which depends on billing being designed first.
- **Controlled support access** (explicitly *not* impersonation, per the user's framing): a request → reason → time-limited authorization → audit → auto-expiry flow. Shape: a new `support_access_grants` table (`organization_id`, `platform_admin_user_id`, `reason` (required text), `requested_at`, `approved_by` (a *second* platform admin — two-person rule), `expires_at`, `revoked_at`). While active and unexpired, a narrowly-scoped, **read-only** dependency (`Depends(require_support_access(org_id))`) would let the specific platform admin's specific request read specific tenant read-endpoints — never write, never impersonate the tenant's identity (the audit trail must show "platform admin viewed via support grant," not "tenant user did X"). This is materially more complex than anything in the MVP list and deserves its own design session before being built.
- **MFA**: for platform admins first (highest privilege, smallest user count — easiest place to start), then potentially all users. Requires a real migration (`User` schema change) — explicitly out of scope for this document per the task's constraints.

---

## 17. Migration strategy

Described, not written, respecting the existing single-head chain (current head `0023_aircraft_registration_unique.py`).

Proposed order for a future implementation session, each a separate migration (numbered `0024`+):

1. `0024_plans.py` — create `plans`, `plan_features`.
2. `0025_organization_plan_id.py` — add nullable `plan_id` FK to `organizations`; backfill nothing (NULL = "no plan assigned yet," intentionally fail-closed per Section 6.4).
3. `0026_tenant_entitlement_overrides.py` — create `tenant_feature_overrides`.
4. `0027_tenant_usage_limits.py` — create `tenant_usage_limits`.
5. No migration needed for platform audit (Section 12 — reuses `AuditEvent` as-is).
6. No migration needed for new `Permission`/`Role` values (Section 8) — those are application-level `StrEnum` additions in `permissions.py`, not schema changes; `UserRole.role_name` is already a free-text column keyed against the enum, so granting a new permission set to `PLATFORM_ADMIN` is a code change, not a migration.

Each migration should ship in the same PR as the model class it backs (matching the existing repo convention of one domain slice per migration, e.g. `0020_assessment_domain.py`), and each PR should be independently revertible without breaking the ones before it in the chain.

---

## 18. Testing strategy

A tenancy-isolation-style regression suite for this layer needs to prove, following the exact pattern of `test_tenancy_isolation.py`:

1. **Suspended tenant + entitled feature**: a tenant on a plan that includes `FEATURE_WORK_ORDERS`, then suspended via `/platform/organizations/{id}/suspend`, must get 401 on `get_current_user` (already proven today) — and separately, `entitlement_service.tenant_has_feature` must independently return `False` for a suspended org even if called directly, bypassing the request layer (unit test, not just an integration test — proves the fail-closed check isn't only enforced by the request pipeline).
2. **Platform admin still can't read tenant operational data**: extend the existing confirmed test pattern (`test_platform_admin_gets_403_from_organization_users_endpoint`) to cover every new platform endpoint too — a `PLATFORM_ADMIN` with only `PLATFORM_MANAGE` (not the new finer permissions) must get 403 on plan-assignment/entitlement-override/audit-read/admin-management endpoints, proving the new permissions are genuinely required, not silently granted by `PLATFORM_MANAGE`.
3. **Cross-tenant entitlement lookups are impossible**: Tenant A's `require_feature` check must never be satisfiable by Tenant B's plan/override rows — a targeted test asserting `tenant_has_feature(org_a_id, F)` and `tenant_has_feature(org_b_id, F)` diverge correctly when only one org has an override.
4. **Entitlement bypass via role permission**: a tenant `ORG_ADMIN` with full `Permission` grants but no plan feature must still get 403 from `require_feature` on a gated endpoint — proving RBAC success doesn't imply entitlement success (the two gates are genuinely independent, per Section 7's ordering).
5. **Privilege escalation guard**: a `PLATFORM_ADMIN` without `PLATFORM_ADMIN_MANAGE` cannot grant `PLATFORM_ADMIN` to any user, including themselves re-granting a broader set.
6. **Append-only audit still holds**: a platform-attributed audit event (Section 12, option 1) is still rejected on UPDATE/DELETE by the existing trigger — a one-line addition to whatever test already exercises `0002`'s trigger, run against a platform-sourced row instead of only a tenant-sourced one.
7. **Plan/entitlement composition**: table-driven tests for `tenant_has_feature` covering all four quadrants of (plan includes feature / doesn't) × (override present granting / revoking), plus the "no plan assigned" fail-closed case.

---

## 19. Risks

Specific to this codebase, not generic:

- **Platform-level bypass weakening recent tenancy hardening.** The repo's recent commit history (per git log: `fix(inspections)`, `fix(tasks)`) shows active IDOR/tenancy-hardening work in flight. Introducing `require_feature` as a new dependency stage is a new place a future engineer could accidentally reorder ahead of, or substitute for, a `TenantScopedMixin`-based `organization_id` filter in a service function — e.g., mistakenly thinking "this endpoint checked entitlement, so it's safe" when entitlement says nothing about *which* org's rows a query returns. Mitigation: Section 13's explicit rule that `require_feature` is additive, never a substitute for row-level tenant filtering, must be a reviewed convention, and Section 18's test #4 should be treated as a permanent regression guard.
- **Conflating `Organization.status` with subscription status.** The clearest concrete risk called out by the task brief itself. `Organization.status`'s docstring already explicitly disclaims billing intent (`organization.py:16-19`) — if a future engineer, under time pressure, adds `TRIAL`/`PAST_DUE`/`CANCELED` directly to `OrganizationStatus` instead of introducing the separate `plan_id`/entitlement path this document proposes, every place that currently does `status == SUSPENDED` (three call sites found: `get_current_user`, `auth_service.authenticate`, `auth_service.refresh_access_token`) would need simultaneous, correct updates to treat multiple non-ACTIVE values consistently — a classic partial-rollout bug source. Mitigation: Section 9's explicit separation should be enforced by code review, not just documentation.
- **Fail-open entitlement bugs.** Unlike `OrganizationStatus.SUSPENDED` (an existing, tested, fail-closed check), the new entitlement layer is greenfield. A bug that makes `tenant_has_feature` default to `True` on an unexpected code path (e.g., a plan with no rows, a malformed feature key) would silently grant unpaid access rather than loudly denying paid access — the opposite failure mode of what a security-conscious default should be. Mitigation: Section 10's design already defaults closed at every branch (`org is None or SUSPENDED` → False, `plan_id is None` → False); this must be preserved verbatim in implementation, and test 7 in Section 18 must include explicit "malformed/missing data" cases, not just the happy path.
- **Coarse module-level gating masking real per-endpoint variance.** Several routers bundled together in Section 5 (e.g., `procurement.py` + `purchase_orders.py` + `receiving.py` under one `FEATURE_PROCUREMENT`) have different backend maturity levels individually; gating them as one feature could either over-grant (a tenant gets receiving they haven't paid for because it rode in with procurement) or under-grant (a tenant loses a feature they were using because it got bundled with one they weren't entitled to). Mitigation: revisit the bundling boundaries in Section 5 once real usage data or sales requirements clarify how these are actually packaged commercially — don't treat today's grouping as permanent.
- **Single-operator platform admin org as a single point of trust.** With Option B (Section 2), every platform admin belongs to one "Platform Operations" organization by bootstrap convention. If that org were ever accidentally suspended (e.g., a platform admin fat-fingers their own org ID into the suspend endpoint), every platform admin would be locked out simultaneously with no recovery path (Section 13's emergency-recovery gap). Mitigation: the suspend endpoint should refuse to suspend an organization that has any `PLATFORM_ADMIN`-role user as a safety check — a small, cheap guard worth adding as part of Milestone 2 below.

---

## 20. Exact implementation milestones in dependency order

Each sized as one coherent PR for a future session.

1. **Add new `Permission` values** (`PLATFORM_PLAN_MANAGE`, `PLATFORM_ENTITLEMENT_MANAGE`, `PLATFORM_AUDIT_READ`, `PLATFORM_ADMIN_MANAGE`) to `permissions.py`, grant all four to `Role.PLATFORM_ADMIN` in `ROLE_PERMISSIONS`. No schema change. Ship with a test proving `PLATFORM_ADMIN` still gets 403 on every existing tenant-operational endpoint (regression guard for Section 1's existing test, extended).
2. **Migration `0024_plans.py`**: `plans` + `plan_features` tables, plus a small seed/fixture (not a migration data-write) for local dev. Add the "refuse to suspend an org containing a `PLATFORM_ADMIN` user" guard to `platform_service.set_organization_status` (Section 19's mitigation) in the same PR since it touches the same file.
3. **Migration `0025_organization_plan_id.py`**: nullable `plan_id` FK on `organizations`. Add `PLATFORM_PLAN_MANAGE`-gated endpoint `POST /platform/organizations/{id}/plan`.
4. **`entitlement_service.py`** (Section 10): `tenant_has_feature`, unit-tested against Section 18's table-driven test #7 (using only `plans`/`plan_features`/`organization.plan_id` — no overrides yet, since they don't exist until Milestone 5). No route wiring yet.
5. **Migration `0026_tenant_entitlement_overrides.py`**: `tenant_feature_overrides` table; extend `entitlement_service.tenant_has_feature` to consult it; add `PLATFORM_ENTITLEMENT_MANAGE`-gated endpoints to set/clear an override.
6. **Wire `require_feature` into `deps.py`** (Section 7) and apply it to the first, lowest-risk MVP-gateable router (e.g., `FEATURE_AOG` — small, self-contained) as a proof of the end-to-end pattern before rolling it out further. Ship Section 18's tests #1, #3, #4 in this PR.
7. **Roll `require_feature` out to the remaining MVP-gateable routers** from Section 5's table, one PR per 3-4 routers to keep review size sane.
8. **Migration `0027_tenant_usage_limits.py`** + `GET`/`POST` endpoints for usage limits and the read-only rollup (Section 11, capability #9).
9. **Platform audit read endpoint** (Section 12): `GET /platform/audit-events` gated on `PLATFORM_AUDIT_READ`, no migration.
10. **Platform admin management** (Section 8, capability #8): endpoints to grant/revoke `PLATFORM_ADMIN`-family roles on an existing user, gated on `PLATFORM_ADMIN_MANAGE`, with the two-person-rule / self-grant-prevention tests from Section 18 #5. Deliberately last among MVP milestones given it's the highest-privilege surface — build it once every other piece it might need to protect already exists.
11. **Frontend**: extend `frontend/app/(app)/platform/*` with plan/entitlement/usage/audit views, following the existing `platform/organizations/page.tsx` pattern (`RealDataPanel`, `DataTable`, same session context) — no new app shell, per Section 14.
12. *(FUTURE, not part of this milestone sequence)*: MFA for platform admins, controlled support access, billing — each its own future design + milestone sequence per Section 16.

---

---

## 21. ADDENDUM (2026-09-13) — PROPOSED correction: `subscriptions` table replaces bare `organizations.plan_id`

Status: **PROPOSED**, produced by a follow-up rigorous review that ran 12 edge cases and the full FUTURE-requirements list (trial, start/end date, renewal, cancellation, upgrade, downgrade, grace period, billing provider, invoice reference, subscription status, historical subscriptions, scheduled plan changes) against the schema in Sections 4, 6.2, 6.4, 9, and 17. **This addendum supersedes those sections' specific claim that a single nullable `organizations.plan_id` FK is sufficient.** All other content in Sections 1-20 was re-verified against the current codebase during this review and stands unchanged.

**Finding:** `organizations.plan_id` (Section 6.4) is a snapshot — it can only ever represent "the plan this org has right now." Every future requirement above requires a *timeline* (dates, status, history, provider/invoice references, scheduled future-dated changes), not a snapshot. Adding those later would not be an additive migration — it would require retroactively synthesizing history from a column that never recorded any, and rewiring every read of `org.plan_id` to a different table. That is exactly the kind of destructive future migration this review exists to prevent, so the schema decision is made now even though billing logic stays FUTURE.

**Revised recommendation:** do not add `plan_id` to `organizations` at all. Instead add:

- **`subscriptions`** (tenant-scoped, new table): `id`, `organization_id` (FK), `plan_id` (FK → `plans.id`), `status` (`TRIALING` / `ACTIVE` / `PAST_DUE` / `CANCELED` / `SCHEDULED` — subscription lifecycle, deliberately distinct from `Organization.status`, see Section 9), `starts_at`, `ends_at` (nullable = open-ended), `created_at`. History is preserved by never deleting or overwriting a row — an upgrade/downgrade/cancellation inserts a new row (or closes the old one's `ends_at` and opens a new one), so "what plan was active on date X" is always answerable.
- The tenant's *current* plan is derived, not stored directly: the subscription row for that org with `status IN (ACTIVE, TRIALING)` whose date range covers now (implementation detail — a maintained `is_current` boolean or an ORDER BY/LIMIT query, either is fine — left FUTURE).
- `plan_features`, `tenant_feature_overrides`, `tenant_usage_limits` are unchanged from Section 6 — only the plan-assignment layer changes.
- Migration ordering (revises Section 17): `0024_plans.py` unchanged; **replace** `0025_organization_plan_id.py` with `0025_subscriptions.py` (creates `subscriptions`, no column added to `organizations`); `0026`/`0027` (overrides, usage limits) unchanged.
- `Organization.status` stays exactly as today (Section 9's separation argument is strengthened, not weakened, by this change — subscription lifecycle now has an unambiguous home on `subscriptions.status` instead of any temptation to overload `OrganizationStatus`).
- Cost: one extra table and one extra join inside `entitlement_service.tenant_has_feature` versus a bare FK. Benefit: real history, a landing place for FUTURE billing-provider/invoice-reference columns as a normal additive migration, and clean support for scheduled future-dated plan changes (insert a future-`starts_at` row now) — none of which a bare FK can ever provide without a destructive rebuild.
- **Explicit non-negotiable guarantee carried through unchanged from the edge-case review:** no upgrade, downgrade, or subscription-status change may ever cascade-delete or hide existing tenant operational data (aircraft, work orders, evidence, etc.). Plan/subscription changes only affect which *features* are reachable going forward; data retention has no coupling to these tables.

No migrations, models, or application code were written for this addendum — it remains a schema *decision*, described only, per the same constraint as the rest of this document.

---

## 22. M1 Implementation (2026-09-13)

This section documents what was actually built for Milestone 1 — pure
database/domain foundation, no API, no service layer beyond the models
themselves, no UI, no billing, no usage metering, no entitlement-evaluation
engine. Everything below is tagged EXISTING, IMPLEMENTED M1, or FUTURE; this
document does not claim anything beyond IMPLEMENTED M1 as done.

Migration: `backend/alembic/versions/0024_platform_control_plane_m1.py`
(revision `0024`, down_revision `0023`). Models:
`backend/app/models/plan.py` (`Plan`, `PlanFeature`),
`backend/app/models/subscription.py` (`Subscription`, `SubscriptionStatus`),
`backend/app/models/tenant_entitlement.py` (`TenantFeatureOverride`,
`TenantUsageLimit`). Tests:
`backend/tests/integration/test_platform_control_plane.py` (16 model-level
tests, no API involved since none exists yet).

### 22.1 Tables as implemented — IMPLEMENTED M1

**`plans`** (global/platform-level — no `organization_id`, does not use
`TenantScopedMixin`, the same "shared catalog table" pattern
`TenantScopedMixin`'s own docstring documents for regulatory reference
tables):
- `id` (UUID PK, `UUIDPKMixin`)
- `created_at` (`TimestampMixin`)
- `name` (string, required)
- `code` (string, required, globally unique — `uq_plans_code`, indexed)
- `description` (text, nullable)
- `is_active` (bool, default `true`)
- `updated_at` (timestamp, server-default `now()`, `onupdate=now()`)

**`plan_features`** (global/platform-level, same non-tenant-scoped reasoning
as `plans`):
- `id`, `created_at`
- `plan_id` (FK → `plans.id`, `ON DELETE RESTRICT`, indexed)
- `feature_key` (string, required)
- `enabled` (bool, default `true`)
- `updated_at`
- Unique constraint `uq_plan_features_plan_id_feature_key` on
  `(plan_id, feature_key)` — DB-enforced, verified by
  `test_duplicate_plan_feature_rejected`.

**`subscriptions`** (tenant-scoped via `TenantScopedMixin` — carries
`organization_id`, indexed, `NOT NULL`, no FK to `organizations` is declared
at the DB level, matching the existing convention of every other
`TenantScopedMixin` table in this codebase, e.g. `users`, `aircraft`):
- `id`, `created_at`, `organization_id`
- `plan_id` (FK → `plans.id`, `ON DELETE RESTRICT`, indexed — a plan can
  never be deleted while subscription history references it, verified by
  `test_plan_cannot_be_deleted_when_referenced_by_subscription`)
- `status` (string(16), one of `TRIALING`, `ACTIVE`, `PAST_DUE`, `CANCELED`,
  `SCHEDULED` — plain string constants on `SubscriptionStatus`, matching
  this codebase's existing enum-as-string-class convention, e.g.
  `DeferredItemStatus`, `EvidenceStatus`, not a Postgres/SQLAlchemy `Enum`
  type)
- `starts_at` (timestamp, required)
- `ends_at` (timestamp, nullable — null means open-ended, verified by
  `test_open_ended_subscription`)
- `updated_at`
- Indexes: `organization_id`, `plan_id`, `status`, and a composite
  `ix_subscriptions_org_status_starts_at` on
  `(organization_id, status, starts_at)` to support a future "find the
  effective subscription for this org" query.

**`tenant_feature_overrides`** (tenant-scoped):
- `id`, `created_at`, `organization_id`
- `feature_key` (string, required, indexed)
- `enabled` (bool, required)
- `reason` (text, nullable)
- `created_by_user_id` (FK → `users.id`, nullable — matches
  `TechnicianQualification.granted_by_user_id`'s convention for an optional
  "who did this" actor reference that must never block the row if the user
  is later removed)
- `expires_at` (timestamp, nullable — null means no expiry)

**`tenant_usage_limits`** (tenant-scoped):
- `id`, `created_at`, `organization_id`
- `feature_key` (string, required, indexed)
- `limit_key` (string, required — distinguishes multiple limit dimensions
  on the same feature, e.g. `monthly_queries` vs. some other ceiling)
- `limit_value` (integer, nullable — ignored/should be null when
  `is_unlimited` is true; never a magic sentinel like `-1`)
- `is_unlimited` (bool, default `false`)
- `updated_at`
- Unique constraint `uq_tenant_usage_limits_org_feature_limit` on
  `(organization_id, feature_key, limit_key)` — DB-enforced, verified by
  `test_duplicate_usage_limit_rejected`.

### 22.2 Relationships — IMPLEMENTED M1

`plan_features.plan_id → plans.id` (RESTRICT) and
`subscriptions.plan_id → plans.id` (RESTRICT) are the only foreign keys
declared among the five new tables. `subscriptions`, `tenant_feature_overrides`,
and `tenant_usage_limits` are tied to a tenant only through the plain
`organization_id` column (no DB-level FK to `organizations`, consistent with
every other tenant-scoped table already in this schema).
`tenant_feature_overrides.created_by_user_id → users.id` is nullable and has
no `ON DELETE` action specified (defaults to `NO ACTION`, same as
`TechnicianQualification.granted_by_user_id`).

### 22.3 Constraints/indexes not enforced at the DB level — deliberate M1 gaps

Two invariants described in the original proposal (§21) are intentionally
**not** DB-enforced in M1, because doing so would require a Postgres partial
unique index — a pattern no existing migration in this codebase uses — and
the task's own guidance was not to introduce an exotic constraint style
inconsistent with the rest of the schema:

- **Overlapping ACTIVE subscriptions**: nothing stops two `Subscription`
  rows for the same `organization_id` from both being `ACTIVE`
  simultaneously. Documented in the `Subscription` model docstring and
  exercised (not asserted against) by
  `test_overlapping_active_subscriptions_not_db_enforced`. **FUTURE**: the
  entitlement-resolution service must reject or otherwise resolve this
  ambiguity when it is built.
- **Duplicate active feature overrides**: nothing stops two
  `TenantFeatureOverride` rows for the same `(organization_id, feature_key)`
  from both being non-expired at once. Documented in the
  `TenantFeatureOverride` model docstring and exercised by
  `test_duplicate_active_override_not_db_enforced`. **FUTURE**: same
  resolution service must handle this.

### 22.4 Subscription lifecycle model — IMPLEMENTED M1 (schema only)

`SubscriptionStatus` values: `TRIALING`, `ACTIVE`, `PAST_DUE`, `CANCELED`,
`SCHEDULED`. No state-machine/transition validation exists yet — the column
accepts any of these five strings from any prior value. **FUTURE**: a
subscription lifecycle service to enforce valid transitions (e.g.
`SCHEDULED → ACTIVE`, `ACTIVE → PAST_DUE → CANCELED`) does not exist yet.

### 22.5 Plan vs. subscription — IMPLEMENTED M1

A `Plan` is a platform-global template ("what a Pro plan includes"),
independent of any tenant. A `Subscription` is a tenant-specific historical
fact ("Organization X was on the Pro plan from date A to date B with status
Y"). This is the structure §21 argued for and this implementation follows:
changing a tenant's plan means inserting a new `Subscription` row, never
mutating or deleting the old one and never storing a bare `plan_id` directly
on `Organization` (confirmed: `Organization` was not modified — see
`backend/app/models/organization.py`, unchanged). History is preserved and
queryable, verified by `test_multiple_subscriptions_preserve_history` and
`test_canceled_subscription_remains_historical`.

### 22.6 Feature entitlement model — IMPLEMENTED M1 (schema only)

`PlanFeature` rows describe which `feature_key`s a plan turns on/off — a
plan's full feature surface is stored explicitly (`enabled=True` or `False`
rows both persist) rather than inferred from a feature's absence.
`feature_key` is a free-form indexed string, mirroring this codebase's
existing convention for other small classification strings (e.g.
`Aircraft.aircraft_type`) rather than a lookup table. **FUTURE**: no service
resolves "is feature X enabled for org Y" by combining a subscription's
plan features with tenant overrides — that entitlement-evaluation engine is
explicitly out of scope for M1.

### 22.7 Tenant override model — IMPLEMENTED M1 (schema only)

`TenantFeatureOverride` lets a tenant's effective entitlement for one
`feature_key` diverge from its plan (e.g. a support-granted trial, or a
contractual carve-out), with an optional `reason`, an optional
`created_by_user_id` actor reference, and an optional `expires_at`. As noted
in §22.3, preventing conflicting simultaneous overrides is a **FUTURE**
service responsibility, not a DB constraint.

### 22.8 Usage-limit model — IMPLEMENTED M1 (schema only)

`TenantUsageLimit` stores a configured ceiling for one
`(organization_id, feature_key, limit_key)` combination — either a concrete
`limit_value` or `is_unlimited=true` with `limit_value` left null. **No
usage-metering system exists** — this table records only the configured
ceiling, never an observed usage count; nothing here counts real Lisa
queries or any other tenant activity.

### 22.9 Lisa integration foundation — FUTURE (schema-only note)

No redesign of Lisa (`backend/app/services/lisa/…`,
`backend/app/models/lisa_conversation_context.py`) was made or is proposed
here. This schema is simply capable of representing `LISA` as one
module-level `feature_key` value on `PlanFeature`/`TenantFeatureOverride`/
`TenantUsageLimit` rows (e.g. a plan that does not include `LISA`, or a
tenant-specific `monthly_queries` ceiling on it) once an entitlement
evaluation engine and Lisa call-site checks are built. Nothing in
`app/services/lisa` currently reads or enforces any of these new tables.

### 22.10 Explicitly NOT implemented in M1

- Entitlement-evaluation service/engine (no code anywhere resolves "is
  feature X enabled for organization Y" from these tables)
- Any API endpoints for plans, subscriptions, overrides, or usage limits
- Any UI
- Billing/payment integration of any kind
- Usage metering (no counters, no consumption tracking)
- Automatic audit events for create/update/delete on any of the five new
  tables (unlike `audit_events`' own append-only trigger — see
  `backend/alembic/versions/0002_audit_events_immutability.py` — nothing
  currently writes an `AuditEvent` row when a `Plan`, `PlanFeature`,
  `Subscription`, `TenantFeatureOverride`, or `TenantUsageLimit` changes)
- DB-level enforcement of "at most one ACTIVE subscription per org" and "at
  most one active override per (org, feature_key)" — see §22.3
- Subscription lifecycle transition validation

---

## 23. M2 — Effective entitlement resolution service (2026-09-13)

`app/services/entitlement_service.py::resolve_entitlements(db, *,
organization_id, as_of=None)` is the first (and, as of this addendum, only)
code in this codebase that answers "is feature X enabled for organization
Y" from the M1 tables. It is read-only: no writes, no billing, no usage
metering, no RBAC/user permission checks (it takes only `organization_id`).

Algorithm, matching §22.10's list of what M1 deliberately left undone:

1. **Tenant status short-circuit** — `Organization.status == SUSPENDED`
   returns a `SUSPENDED` result immediately, without inspecting
   subscriptions at all.
2. **Subscription selection** — a subscription is a candidate if its status
   is one of `TRIALING`/`ACTIVE`/`PAST_DUE` and `starts_at <= as_of` and
   (`ends_at IS NULL` or `ends_at > as_of`). `CANCELED` and `SCHEDULED` never
   count, regardless of date overlap. Zero candidates → `NO_SUBSCRIPTION`.
   **More than one candidate → `AMBIGUOUS`**, per §22.3's documented,
   deliberately-unenforced "at most one ACTIVE subscription per org"
   invariant: the service refuses to guess which one wins.
3. **PAST_DUE decision**: PAST_DUE is treated as a *current, granting*
   status (a grace-period convention) — a lapsed invoice does not instantly
   evict a tenant from their own compliance data. This is a judgment call
   with no billing/dunning system in this codebase to confirm or refute it.
4. **Plan resolution + INACTIVE_PLAN decision**: an existing subscription
   whose `Plan.is_active` is false still resolves with its real feature map,
   under a new `INACTIVE_PLAN` status distinct from `ACTIVE` — consistent
   with §22.10 treating "inactive" as "no new subscriptions", not "existing
   subscribers instantly lose access". A subscription referencing a
   genuinely missing plan (defensive only; the RESTRICT FK should prevent
   this) resolves `INVALID`.
5. **Feature resolution** — `PlanFeature` rows seed a `{feature_key: bool}`
   map; non-expired `TenantFeatureOverride` rows (per §22.3, also
   deliberately unenforced against duplicates) are applied on top, override
   wins, expired ignored. No authorization of who wrote an override is
   performed here — that remains unimplemented, per task scope.
6. **Usage limits** — `TenantUsageLimit` rows are surfaced as
   `UsageLimitConfiguration` (feature_key, limit_key, limit_value,
   is_unlimited) — configuration only, never "enforced" or "remaining",
   since no consumption counter exists anywhere in this codebase.
7. `LISA` is treated as an ordinary `feature_key` throughout — no
   special-casing exists anywhere in this module (tested explicitly).

Not implemented (still future work, unchanged from §22.10): API endpoints
calling this service, any UI, billing, usage metering/enforcement,
DB-level uniqueness on "one current subscription"/"one active override",
and any authorization of who may write overrides or usage limits.

See `backend/app/services/entitlement_service.py` module docstring for the
full, more detailed rationale, and
`backend/tests/integration/test_entitlement_resolution.py` for the 22
scenario tests (including cross-tenant isolation, deterministic repeated
resolution, and the RBAC-import-absence structural test).

## 24. M3 — Entitlement API exposure (2026-09-13)

A thin, RBAC-free-of-entitlement-logic REST layer over §23's
`resolve_entitlements`. No new entitlement rules were added anywhere in
this milestone — every route below only derives `organization_id`,
calls the service, and serializes `EntitlementResolution`.

1. `GET /api/v1/entitlements` (`backend/app/api/v1/entitlements.py`) —
   tenant self-service. `organization_id` comes only from `CurrentUser`
   (the authenticated JWT via `app.core.deps.get_current_user`), never a
   query/path param. No entitlement-specific permission gate: this is
   read-only self-information about the caller's own tenant, so any
   authenticated user of that organization may call it — a deliberate
   RBAC/entitlement separation (see §23 point on RBAC independence).
   Always 200 for an authenticated caller; `resolution_status` in the body
   carries ACTIVE/INACTIVE_PLAN/SUSPENDED/NO_SUBSCRIPTION/AMBIGUOUS/INVALID
   exactly as the service returns it — none of these are treated as HTTP
   errors.
2. `GET /api/v1/platform/organizations/{organization_id}/entitlements`
   (added to `backend/app/api/v1/platform.py`, mirroring that file's
   existing route conventions) — platform-admin, any org. Gated by the
   same `Depends(require_permission(Permission.PLATFORM_MANAGE))` used by
   every other route in that file; 404 via the existing
   `platform_service.get_organization` lookup if the org doesn't exist.
3. Response schema: `backend/app/schemas/entitlement.py`,
   `EntitlementResolutionResponse`/`UsageLimitConfigurationResponse`,
   built via `from_resolution()`/`from_configuration()` classmethods since
   the source is a frozen dataclass, not an ORM model. Carries an extra
   `plan_name` field (a same-transaction secondary `Plan` lookup by the
   already-resolved `plan_id` done in the route — enrichment, not new
   entitlement logic) since M2's dataclass has `plan_code` but not a name.
4. Known interaction with existing auth: `app.core.deps.get_current_user`
   already rejects (401) any request — including to `/entitlements` —
   from a user whose organization is currently `SUSPENDED`, re-checked on
   every request. So a suspended tenant's own `/entitlements` call never
   observably returns `resolution_status=SUSPENDED` over HTTP; that
   signal is only reachable directly through
   `entitlement_service.resolve_entitlements` (already covered in §23's
   tests) or through the platform-admin endpoint, whose authorization does
   not depend on the target org's status. Tested explicitly in
   `backend/tests/integration/test_entitlement_api.py`.

See `backend/tests/integration/test_entitlement_api.py` for the full API
contract test suite (tenant isolation, platform-admin cross-org access, 403
for ordinary tenant users on the platform endpoint, 404 for a nonexistent
org, and response-shape checks for overrides/usage limits).

## 25. M5 — Plan / plan-feature administration (2026-09-13)

The first entitlement *mutation* layer, establishing the canonical pattern
for all future entitlement administration (M6+). Scope: CRUD and
activate/deactivate for `Plan`, and CRUD/enable-disable for `PlanFeature`
(both from §22's M1 schema) — global platform-catalog data, not tenant
data.

1. **Authorization boundary.** Every mutation route
   (`backend/app/services/plan_service.py`, wired into
   `backend/app/api/v1/platform.py` as `/platform/plans*`) is gated by the
   same `Depends(require_permission(Permission.PLATFORM_MANAGE))` used by
   every other route in that file. No new permission or role was added.
   An M4 authorization review had recommended a narrower
   `PLATFORM_ENTITLEMENT_OVERRIDE`-style permission, but explicitly scoped
   that recommendation to *future* TENANT-specific entitlement-expansion
   work (e.g. writing `TenantFeatureOverride` rows for one customer) — not
   to this milestone's GLOBAL plan-catalog administration, which M4
   concluded plain `PLATFORM_MANAGE` already correctly covers. That
   narrower permission remains unimplemented and out of scope here;
   tested explicitly in `test_tenant_org_admin_also_gets_403` (an
   `ORG_ADMIN`-role tenant admin gets 403 same as any other tenant user —
   tenant-admin status alone grants nothing on `/platform/*`).
2. **Cross-org manipulation is structurally impossible.** `Plan` and
   `PlanFeature` carry no `organization_id` column at all (per M1's
   design, §22.5/§22.6) — there is no tenant scope to bypass in the first
   place. Asserted directly against the model in
   `test_plan_model_has_no_organization_id`.
3. **Audit coverage.** Every mutation (plan created/updated/activated/
   deactivated, plan-feature created/enabled/disabled) calls
   `record_audit_event` in the same transaction as the mutation, before
   commit, mirroring `platform_service.py`'s exact
   flush-then-audit-then-commit pattern. Read operations (list/get) record
   nothing. Since a plan mutation has no natural tenant subject,
   `AuditEvent.organization_id` (NOT NULL, unchanged) is populated with
   the *acting platform admin's own* `organization_id` — already
   available from `CurrentUser`, already guaranteed non-null. This
   milestone specifically checked whether a concrete, code-referenceable
   "Platform Operations org" singleton exists to attribute to instead: it
   does not. `backend/scripts/create_platform_admin.py` merely
   get-or-creates an `Organization` by a configurable
   `--organization-name` (default `"Platform Operations"`) as a one-time
   bootstrap convenience, and every existing platform-admin test
   (`test_platform_api.py`, `test_entitlement_api.py`) creates its own
   arbitrarily-named organization for the admin user — there is no flag
   column or fixed lookup anywhere in application code. Attributing to the
   actor's own organization is therefore the accurate description of the
   only mechanism that actually exists, not an invented alternative.
4. **Transaction safety.** `create_plan`/`update_plan`/
   `create_plan_feature` add the row and `db.flush()` inside a
   try/except that translates the unique-constraint `IntegrityError`
   (`uq_plans_code`, `uq_plan_features_plan_id_feature_key`, both from
   M1's `0024` migration, unchanged) into a `ConflictError` *before* the
   audit event is ever added — so a duplicate-code/duplicate-feature
   conflict can never leave a partial row or an orphaned audit event; the
   whole attempt rolls back together. Verified in
   `test_duplicate_create_plan_leaves_no_partial_row_or_audit_event` using
   a genuinely-committed seed row (via a separate raw connection) so the
   assertion is immune to the test fixture's own single-flat-transaction
   rollback semantics (the same gotcha documented in
   `app/services/aircraft_service.py` and
   `test_lisa_ask_context_integration.py`).
5. **Deactivation never deletes.** `set_plan_active(..., is_active=False)`
   only flips the column; it never deletes `Plan` or cascades to
   `PlanFeature`/`Subscription` rows (the M1 `RESTRICT` FK already
   guarantees this at the DB level, and the service simply never attempts
   a delete). Verified end-to-end that an existing subscriber's
   `resolve_entitlements` result moves from `ACTIVE` to `INACTIVE_PLAN`
   with its real feature map intact, never to an empty one — exactly M2's
   documented behavior (§23).
6. **Zero changes to M2.** `app/services/entitlement_service.py` was not
   touched. `test_m2_integration_live_read_after_write` proves live
   read-after-write correctness through the real service layer alone:
   create a plan with `PlanFeature(LISA, enabled=False)`, resolve
   (`effective_features["LISA"] is False`), flip it via
   `set_plan_feature_enabled`, resolve again with no other change
   (`effective_features["LISA"] is True`).
7. **New files:** `backend/app/services/plan_service.py`,
   `backend/app/schemas/plan.py`,
   `backend/tests/integration/test_plan_administration.py`. Routes added
   to the existing `backend/app/api/v1/platform.py` (no new router file —
   consistent with that file already hosting every other
   `PLATFORM_MANAGE`-gated route). No migration; Alembic head remains
   `0024`.

---

## 26. M6 — Subscription & tenant entitlement administration (2026-09-13)

Adds mutation services for the three remaining M1 tables that M5 did not
cover: `Subscription`, `TenantFeatureOverride`, `TenantUsageLimit`. Follows
M5's exact create/flush/audit/commit transaction pattern. Zero changes to
`app/services/entitlement_service.py` (M2).

1. **Subscription administration**
   (`app/services/subscription_service.py`): create/get/list-for-org/
   update/cancel/schedule, with an explicit lifecycle transition table
   (no `CANCELED` → anything, no skipping straight into an already-past
   state) and service-level rejection of any create/update that would
   produce two simultaneously-"current" subscriptions for the same
   organization (per M2's own TRIALING/ACTIVE/PAST_DUE + date-range
   candidacy rule) — M1 deliberately left this DB-unenforced, and M6 does
   not silently resolve it by picking a winner; it rejects with a 409
   (`ambiguous_subscription_state`) before the row is ever written.

2. **Tenant feature-override / usage-limit administration**
   (`app/services/tenant_entitlement_admin_service.py`): full CRUD
   (create/list/update/remove) for both tables. Removal is a hard delete
   (no soft-delete column exists on either table) and is always treated as
   restrictive/neutral (it can only return a tenant to plan-default
   behavior), so it never requires the expansion permission.

3. **New permission: `Permission.PLATFORM_ENTITLEMENT_OVERRIDE`**
   (`app/core/permissions.py`) — per M4's recommendation, narrower than
   `PLATFORM_MANAGE`. Ordinary administration (subscription CRUD,
   restrictive/neutral overrides and limits) only needs
   `PLATFORM_MANAGE`; a mutation classified EXPANSIVE additionally
   requires this permission. Granted to `Role.PLATFORM_ADMIN` alongside
   `PLATFORM_MANAGE` in `ROLE_PERMISSIONS`, because `PLATFORM_ADMIN` is
   still the only role with any platform authority at all — there is no
   narrower "platform staff without expansion rights" tier to withhold it
   from yet. Both permissions are checked independently at the service
   layer (not just relying on the one role happening to hold both), so
   the code is structurally correct today and a future milestone could
   introduce a `PLATFORM_MANAGE`-only staff tier without touching this
   enforcement logic. **Known limitation, stated honestly**: until that
   second tier exists, every `PLATFORM_ADMIN` user can already perform
   expansion operations — the permission split exists in code, not yet in
   practice.

4. **Restrictive vs. expansive classification** — deterministic, and does
   NOT duplicate M2's algorithm. It calls `resolve_entitlements` to read
   the organization's *current* effective feature map (the baseline) and
   compares the proposed mutation against it:
   - Feature override: enabling (`enabled=True`) a feature the baseline
     does not already grant is EXPANSIVE; disabling, or enabling a feature
     the baseline already grants, is RESTRICTIVE/NEUTRAL.
   - Usage limit: setting `is_unlimited=True` from `False` is EXPANSIVE;
     increasing `limit_value` beyond the currently configured value on an
     existing row is EXPANSIVE; decreasing, holding constant, or
     configuring a brand-new limit for the first time (there being no
     prior ceiling to compare against) is RESTRICTIVE/NEUTRAL.
   The permission check (`require_expansion_permission_if_needed`) is
   applied at the service layer against the caller's full resolved
   permission set — not as a second stacked `Depends` on the route —
   because whether a mutation is expansive can only be determined after
   comparing it to the org's live baseline.

5. **Authorization boundary**: every `/platform/organizations/{id}/...`
   route in this milestone is gated by `PLATFORM_MANAGE` at minimum,
   exactly like M5's plan routes. `test_subscription_and_tenant_
   entitlement_admin.py`'s M6-O regression proves the full boundary
   end-to-end: an ordinary tenant `ORG_ADMIN` attempting an expansive
   `POST .../feature-overrides` (`LISA: true`) receives 403; a
   `PLATFORM_ADMIN` (holding both permissions) succeeds.

6. **Audit attribution** — unlike Plan/PlanFeature (global catalog data
   with no natural tenant subject, attributed in M5 to the acting
   platform admin's own organization), every row in this milestone
   already carries a real `organization_id` via `TenantScopedMixin`. Audit
   events for subscription/override/usage-limit mutations are attributed
   to *that* organization — the one being administered — which is simpler
   and more natural than M5's problem, not a new convention.

7. **Transaction safety** — same guarantee as M5: mutate, flush inside a
   try/except that translates an `IntegrityError` into a clean
   `ConflictError` *before* the audit event is added, then commit. A
   rejected mutation (duplicate override, duplicate usage limit, ambiguous
   subscription state, invalid lifecycle transition) can never leave a
   partial row or an orphaned audit event. Verified with the same
   raw-connection technique M5 used
   (`test_duplicate_override_leaves_no_partial_row_or_orphan_audit`) to
   stay immune to the test fixture's single-flat-transaction rollback
   gotcha.

8. **M2 remains canonical** — zero changes to
   `app/services/entitlement_service.py`. Live read-after-write tests
   prove the resolver sees every M6 mutation: a new subscription flips
   `NO_SUBSCRIPTION` → `ACTIVE`; an expansive override flips a plan-false
   feature to effectively-true and back on removal; an expired override
   is ignored; cancellation flips `ACTIVE` → `NO_SUBSCRIPTION`; usage
   limits are surfaced as configuration exactly as stored.

9. **No metering, no billing** — usage limits remain configuration-only
   (no consumption counter exists anywhere in this codebase); no billing
   provider fields were added to `Subscription`.

10. **No migration.** All three domains fit the existing M1 schema exactly
    as designed; Alembic head remains `0024`.

11. **New files**: `backend/app/services/subscription_service.py`,
    `backend/app/services/tenant_entitlement_admin_service.py`,
    `backend/app/schemas/subscription.py`,
    `backend/app/schemas/tenant_entitlement.py`,
    `backend/tests/integration/test_subscription_and_tenant_entitlement_admin.py`.
    Routes added to the existing `backend/app/api/v1/platform.py`, same as
    M5. `backend/tests/integration/test_platform_admin.py`'s
    `test_platform_admin_role_grants_only_platform_manage` was updated
    (not removed) to assert the new, deliberately-larger `PLATFORM_ADMIN`
    grant set.

---

*Document produced as architecture/repository analysis for §§1–21; §22 documents an actual implementation completed and committed on 2026-09-13. §23 documents the M2 entitlement-resolution service, also completed 2026-09-13. §25 documents the M5 plan/plan-feature mutation layer, also completed 2026-09-13. §26 documents the M6 subscription and tenant entitlement administration layer, also completed 2026-09-13.*
