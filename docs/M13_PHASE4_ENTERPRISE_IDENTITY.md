# M13 Phase 4: Enterprise Identity Architecture & Entra ID Integration

## 1. Objective & Scope

M13 Phase 4 integrates Enterprise Identity Providers (specifically **Microsoft Entra ID / Azure AD** via OpenID Connect) into KOTA Aerospace / AeroComply without creating a second authentication or RBAC system.

The enterprise identity integration acts as an authenticated ingestion pathway that resolves securely into KOTA's authoritative domain and authorization models:
```text
Enterprise IdP (Microsoft Entra ID / OIDC)
    ↓
OIDC Authorization Request (State, Nonce, PKCE)
    ↓
Cryptographic Token Validation (Issuer, Audience, Signature, Expiration, Subject)
    ↓
Deterministic External Identity Mapping (ExternalIdentityMapping)
    ↓
Existing KOTA User & Organization (Tenant-Isolated)
    ↓
Existing KOTA RBAC Role (UserRole: ORG_ADMIN, CAMO_MANAGER, MAINTENANCE_ENGINEER, etc.)
    ↓
Authoritative KOTA JWT Session Token
    ↓
Frontend Authenticated State
```

---

## 2. Architecture & Data Model

### 2.1 Database Entities (Alembic Revision `0056`)

#### `sso_configurations`
Stores tenant-scoped SSO parameters configured by `ORG_ADMIN`:
- `id`: UUID (Primary Key)
- `organization_id`: UUID (Foreign Key `organizations.id`, CASCADE)
- `provider_type`: `ENTRA_ID` | `OIDC` | `SAML`
- `issuer_url`: Identity provider issuer endpoint (e.g. `https://login.microsoftonline.com/{tenant_id}/v2.0`)
- `client_id`: Registered Application Client ID
- `client_secret_hash`: SHA-256 hash of client secret (never stored in plaintext)
- `tenant_id`: Microsoft Entra tenant ID
- `is_active`: Boolean
- `enforce_sso`: Boolean
- `default_role`: Default KOTA role assigned if no explicit group match exists (`VIEWER` default)
- `domain_hint`: Optional email domain hint for IdP discovery (e.g. `horizon.com`)
- `role_mappings`: JSONB mapping Entra security groups / app roles to KOTA RBAC roles (e.g. `{"Aviation-Engineers": "MAINTENANCE_ENGINEER", "CAMO-Directors": "CAMO_MANAGER"}`)
- Unique constraint: `(organization_id, provider_type)`

#### `external_identity_mappings`
Maintains a deterministic 1-to-1 link between external IdP subjects and KOTA user accounts:
- `id`: UUID (Primary Key)
- `organization_id`: UUID (Foreign Key `organizations.id`, CASCADE)
- `user_id`: UUID (Foreign Key `users.id`, CASCADE)
- `provider_type`: `ENTRA_ID` | `OIDC`
- `issuer`: Provider issuer URL
- `subject`: IdP subject claim (`sub` or `oid`)
- `email`: Normalized lowercase email address
- `is_active`: Boolean
- `last_authenticated_at`: Timestamp of most recent successful SSO login
- Unique constraint: `(organization_id, provider_type, subject)`

---

## 3. Security & Validation Controls

1. **Deterministic Identity Resolution**:
   - Existing account match: If a user with the claim's verified email already exists in the target organization, the external subject is linked directly without duplicating the account.
   - New user provisioning: If no user exists, a new `User` is created with a strong random disabled password hash and assigned the mapped role.
2. **Strict Tenant Isolation**:
   - SSO callback explicitly validates the targeted `organization_id`.
   - Tokens issued for Organization A's client/tenant cannot be replayed or used against Organization B.
3. **Cryptographic & Claim Validation**:
   - Issuer check against configured `issuer_url`.
   - Audience check against registered `client_id`.
   - Expiration validation against current UTC time.
   - Nonce and state verification to prevent replay and CSRF attacks.
4. **Audit Trail**:
   - Successful SSO authentication logs `AUTH_SSO_LOGIN` into the immutable `audit_events` log.
