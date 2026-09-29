# Enterprise Deployment Guide — KOTA Aerospace Platform

## 1. Executive Overview
The KOTA Aerospace platform is deployed as a resilient, multi-tenant cloud or hybrid enterprise system supporting commercial airlines, cargo operators, defense programs, and drone fleet operators.

---

## 2. Infrastructure Architecture

```text
                                  INGRESS & SECURITY
                         [Cloudflare / AWS ALB / TLS 1.3]
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
         [Frontend Pods]                                 [Backend FastAPI API]
      (Next.js 16.3.5 Server)                           (Python 3.12 / Uvicorn)
                 │                                               │
                 │                                               ├────────────────────────┐
                 │                                               ▼                        ▼
                 │                                      [PostgreSQL 16]          [Redis 7 Cluster]
                 │                                      (Authoritative State)   (Cache, Rate Limits,
                 │                                               │               Pub/Sub Freshness)
                 │                                               ▼
                 └────────────────────────────────────► [Neo4j Graph (Derived)]
                                                        (Relational Intelligence)
```

---

## 3. Database & Migrations
- **Primary Database:** PostgreSQL 16+ with ACID compliance.
- **Migration Tool:** Alembic (strictly linear sequence). Current HEAD: `0059`.
- **Command:**
  ```bash
  alembic upgrade head
  ```

---

## 4. Enterprise Identity & SSO Integration
- **Protocol:** OpenID Connect (OIDC) / SAML 2.0.
- **Identity Providers:** Microsoft Entra ID (Azure AD), Okta, PingFederate.
- **Tenant Isolation:** Enforced via `organization_id` mapping from OIDC claims or domain bindings.
- **Role Synchronization:** Automated mapping of enterprise directory groups to KOTA RBAC roles (`CAMO_MANAGER`, `MAINTENANCE_ENGINEER`, `QUALITY_MANAGER`, `PILOT`, `VIEWER`).

---

## 5. Security & Isolation Controls
- **Tenant Data Boundary:** All database queries require explicit `organization_id` filter predicates.
- **Audit Logging:** Immutably recorded in `audit_events` with actor ID, IP, user agent, action timestamp, and cryptographic hash linkage.
- **Data Export & Retention:** Controlled export packages (`FLEET`, `FLIGHTS`, `WORK_ORDERS`, `FINDINGS`) and automated TTL retention rules configured per tenant.
