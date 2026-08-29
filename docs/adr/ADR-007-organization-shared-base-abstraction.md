# ADR-007 — Shared Organization Abstraction for Operator/CAMO/MRO/Lessor

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
Research across FAA, EASA/UK CAA, DGCA, and CASA continuing-airworthiness frameworks surfaced at least four distinct tenant-facing organizational roles: Operator, CAMO (EASA/UK Part-CAMO concept — manages continuing airworthiness), MRO (performs maintenance, Part-145/equivalent), and Leasing Company (often legal owner, contractual rather than regulatory interest). Regulatory Authorities and OEMs are also referenced constantly but are never AeroComply tenants.

## Decision
All tenant-facing roles share one `Organization` table with an `org_type` discriminator holding **exactly one** value from `OPERATOR | CAMO | MRO | LESSOR` — no `MIXED` value in M1. Regulatory Authority and Manufacturer/OEM are modeled as separate, non-tenant reference entities — never as `Organization` rows.

**Amendment (CTO review, post-v1.0)**: the original draft of this ADR proposed an `org_type = MIXED` value for organizations holding more than one role, backed by domain invariant #22 requiring "underlying boolean role columns." No such columns were ever added to the actual proposed schema — the invariant referenced fields that did not exist, a real inconsistency the CTO's review correctly rejected. Two ways to fix this were considered (see Alternatives); the org_type enum is kept single-valued for M1, and a proper `OrganizationRole` child table (`Organization 1—N OrganizationRole`, each row one of `OPERATOR/CAMO/MRO/LESSOR`) is documented as the deliberate M2+ path for real multi-role support, rather than inventing boolean flag columns now just to make the old invariant technically true.

## Alternatives Considered
- **Separate table per role** (e.g., `Operator`, `CAMOOrganization`, `MROOrganization`): rejected — research confirmed real companies commonly hold multiple roles simultaneously (an airline that is its own CAMO; an MRO holding third-party CAMO approval). Separate tables would force either duplicate rows for one legal entity or an awkward multi-table join just to answer "which organizations exist," with no compensating benefit since every role needs identical tenancy/user/RBAC infrastructure.
- **Single `Organization` table with no discriminator, treating Regulatory Authority/OEM as organizations too**: rejected — these are referenced, non-tenant entities (no users, no login, no RBAC needs) and conflating them with tenants would require permission logic to special-case "except when this org row is actually a regulator," a correctness hazard of the same shape M0's explicit RBAC permission catalog was built to avoid.
- **(Post-review) Add boolean role columns (`is_operator`, `is_camo`, `is_mro`, `is_lessor`) to back an `org_type = MIXED` value**: rejected — this would satisfy the letter of the original invariant #22 but was never actually part of the proposed schema; adding it now purely to make a pre-existing invariant true, rather than because the domain need was independently justified, is exactly the kind of "invent a field to satisfy a rule" the CTO's review correctly flagged as backwards reasoning. A real multi-role need deserves a real modeling answer (`OrganizationRole`), not four parallel boolean flags bolted onto one table.
- **(Post-review) `OrganizationRole` child table now, in M1`**: rejected for M1 specifically (not rejected outright — see Reversal Conditions) — no current M1 requirement (RBAC, applicability evaluation, dashboard) actually depends on an organization holding more than one role simultaneously; adding the table now would be schema growth without a driving use case, which the CTO's standing instruction ("do not expand M1 unnecessarily") weighs against until real onboarding data shows the need.

## Consequences
- A company genuinely holding multiple roles (e.g., an airline that is also its own CAMO) must, in M1, pick one primary `org_type` to register as — a real, acknowledged scope limitation (see [M1_SCOPE.md](../ontology/M1_SCOPE.md)), not a silently-broken data model. This is judged an acceptable M1 tradeoff: it affects which role label displays, not any compliance-correctness path (applicability evaluation never depends on `org_type`).
- `RegulatoryAuthority` (already exists from M0) and a new lightweight `Manufacturer` reference entity remain outside the tenancy/RBAC system entirely, by design.
- Domain invariant #22 is rewritten to state only what the actual M1 schema enforces (`org_type` is one required value from the four-item enum) — it no longer references nonexistent boolean columns.

## Reversal Conditions
Reconsider (and implement the `OrganizationRole` child table) once real customer onboarding surfaces organizations that genuinely need to be registered under more than one role simultaneously — at that point, add `OrganizationRole(organization_id, role)` as a proper one-to-many table (one row per held role) rather than reintroducing a `MIXED` enum value or boolean flag columns. This is a pure additive migration (a new child table) with no change to `Organization` itself, so deferring it costs nothing structurally.
