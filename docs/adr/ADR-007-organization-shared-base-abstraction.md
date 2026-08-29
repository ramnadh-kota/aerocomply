# ADR-007 — Shared Organization Abstraction for Operator/CAMO/MRO/Lessor

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
Research across FAA, EASA/UK CAA, DGCA, and CASA continuing-airworthiness frameworks surfaced at least four distinct tenant-facing organizational roles: Operator, CAMO (EASA/UK Part-CAMO concept — manages continuing airworthiness), MRO (performs maintenance, Part-145/equivalent), and Leasing Company (often legal owner, contractual rather than regulatory interest). Regulatory Authorities and OEMs are also referenced constantly but are never AeroComply tenants.

## Decision
All tenant-facing roles share one `Organization` table with an `org_type` discriminator (`OPERATOR | CAMO | MRO | LESSOR | MIXED`), reusing exactly the multi-tenancy, user, and RBAC infrastructure already built in M0. Regulatory Authority and Manufacturer/OEM are modeled as separate, non-tenant reference entities — never as `Organization` rows.

## Alternatives Considered
- **Separate table per role** (e.g., `Operator`, `CAMOOrganization`, `MROOrganization`): rejected — research confirmed real companies commonly hold multiple roles simultaneously (an airline that is its own CAMO; an MRO holding third-party CAMO approval). Separate tables would force either duplicate rows for one legal entity or an awkward multi-table join just to answer "which organizations exist," with no compensating benefit since every role needs identical tenancy/user/RBAC infrastructure.
- **Single `Organization` table with no discriminator, treating Regulatory Authority/OEM as organizations too**: rejected — these are referenced, non-tenant entities (no users, no login, no RBAC needs) and conflating them with tenants would require permission logic to special-case "except when this org row is actually a regulator," a correctness hazard of the same shape M0's explicit RBAC permission catalog was built to avoid.

## Consequences
- One company holding multiple roles (operator + own CAMO) is one row with `org_type = MIXED`, avoiding duplicate-entity bugs.
- `RegulatoryAuthority` (already exists from M0) and a new lightweight `Manufacturer` reference entity remain outside the tenancy/RBAC system entirely, by design.
- A `CHECK` constraint (domain invariant #22) ties `org_type = MIXED` to at least two underlying role flags, preventing a meaningless catch-all value.

## Reversal Conditions
Reconsider only if a specific role (e.g., CAMO) develops materially different data requirements (fields, relationships) than the others such that the shared table becomes mostly-nullable columns — at that point, a role-specific extension table (not a full separate Organization concept) would be the first escalation, not a full split.
