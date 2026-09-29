# Microsoft Entra ID (Azure AD) — Production SSO Configuration Guide

## 1. Overview

KOTA Aerospace / AeroComply supports enterprise single sign-on (SSO) using OpenID Connect (OIDC) through **Microsoft Entra ID**.

The integration deterministically resolves external identities into native, tenant-isolated KOTA user accounts and role-based access control (RBAC) permissions.

---

## 2. Microsoft Entra ID App Registration

1. **Register Application**:
   - In the Azure Portal / Microsoft Entra admin center, navigate to **Identity → Applications → App registrations**.
   - Select **New registration**.
   - Name: `KOTA Aerospace Production SSO` (or `Horizon Air - AeroComply`).
   - Supported account types: `Accounts in this organizational directory only (Single tenant)`.
   - Redirect URI: `Web` → `https://app.aerocomply.com/auth/sso/callback` (or your customer-specific domain).

2. **Certificates & Secrets**:
   - Navigate to **Certificates & secrets → Client secrets**.
   - Create a new client secret. Note the `Value` securely (stored encrypted in KOTA SSO config).

3. **API Permissions & Claims**:
   - Ensure `openid`, `profile`, and `email` delegated permissions under Microsoft Graph are granted.
   - Under **Token configuration**, add Optional Claims:
     - `email`
     - `preferred_username`
     - `groups` (Security groups or Directory roles)

4. **Security Group Mapping**:
   - Create or assign security groups for role mappings:
     - `Aviation-Admins` → `ORG_ADMIN`
     - `CAMO-Team` → `CAMO_MANAGER`
     - `Maintenance-Engineers` → `MAINTENANCE_ENGINEER`
     - `Quality-Managers` → `QUALITY_MANAGER`
     - `Flight-Viewers` → `VIEWER`

---

## 3. KOTA Aerospace SSO Activation

Using the KOTA Admin Portal or API:

```http
PUT /api/v1/auth/sso/config
Authorization: Bearer <ORG_ADMIN_JWT>
Content-Type: application/json

{
  "provider_type": "ENTRA_ID",
  "issuer_url": "https://login.microsoftonline.com/<ENTRA_TENANT_ID>/v2.0",
  "client_id": "<ENTRA_CLIENT_ID>",
  "client_secret": "<ENTRA_CLIENT_SECRET>",
  "tenant_id": "<ENTRA_TENANT_ID>",
  "is_active": true,
  "enforce_sso": false,
  "default_role": "VIEWER",
  "domain_hint": "horizon.com",
  "role_mappings": {
    "Aviation-Admins": "ORG_ADMIN",
    "CAMO-Team": "CAMO_MANAGER",
    "Maintenance-Engineers": "MAINTENANCE_ENGINEER",
    "Quality-Managers": "QUALITY_MANAGER"
  }
}
```

---

## 4. Security Invariants

- **Zero Plaintext Storage**: Secrets are cryptographically hashed and never logged.
- **Tenant Isolation**: Tokens issued for Tenant A cannot authenticate against Tenant B.
- **Audit Logging**: Every successful SSO session emits an immutable `AUTH_SSO_LOGIN` record into the audit log.
