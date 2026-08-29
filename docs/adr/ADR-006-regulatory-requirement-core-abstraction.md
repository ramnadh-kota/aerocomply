# ADR-006 — Regulatory Requirement as Core Domain Abstraction

## Status
Accepted

## Context
The original v0.1 proposal modeled `AirworthinessDirective` as a first-class table, since AD is the primary MVP use case. But AeroComply must eventually support Service Bulletins, Regulations, Rules, AMC, GM, SIBs, and mandatory notices — all of which share the same shape (issued by an authority, published in a document, carrying an applicability condition and possibly a compliance action) but differ in type-specific metadata. Building AD as its own table risks either (a) duplicating that table per requirement type later, or (b) a disruptive migration to unify them once SB support is needed.

## Decision
Introduce `RegulatoryRequirement` as the generic obligation entity, with a `requirement_type` discriminator (`AD | SB | REGULATION | RULE | AMC | GM | SIB | NOTICE | OTHER`) and a `type_metadata jsonb` column for type-specific fields. The chain becomes:

```
RegulatoryAuthority → RegulatoryDocument → RegulatoryRequirement → ApplicabilityRule → ApplicabilityAssessment
```

v0.1 populates only `requirement_type = AD` with real workflow support; other enum values exist in the schema from day one so adding a new regulatory source type is an enum addition plus type-specific `type_metadata` shape, never a new core table or a migration touching `ApplicabilityRule`/`ApplicabilityAssessment`. A `references_requirement_id` self-relation on `RegulatoryRequirement` supports `AD → SB` linkage (and other requirement-to-requirement references) without a bespoke join table.

## Alternatives Considered
- **Keep `AirworthinessDirective` as its own table, add `ServiceBulletin`/etc. as separate tables later**: rejected — this is exactly the "major schema change to introduce SBs later" the CTO directive prohibits; every downstream table (`ApplicabilityRule`, `ApplicabilityAssessment`, `Evidence` linkage) would need a new FK column or a polymorphic union per requirement type.
- **Fully generic EAV (entity-attribute-value) model for all regulatory content**: rejected — over-engineered for v0.1; loses type safety and query performance for the one type (AD) that actually needs to work well now. The `requirement_type` discriminator + `type_metadata jsonb` hybrid gets the extensibility benefit without EAV's query cost.

## Consequences
- `ApplicabilityRule`, `ApplicabilityAssessment`, `MaintenanceRecord`, and `Evidence` all reference `regulatory_requirement_id` uniformly, regardless of requirement type — no type-specific FKs to maintain.
- Adding SB workflow later means: populate `requirement_type='SB'` rows, define `type_metadata` shape for SB-specific fields, build the review/approval UI — no schema migration to the core chain.
- Queries filtering "just ADs" need a `WHERE requirement_type = 'AD'` clause rather than a dedicated table scan — negligible cost with an index on `requirement_type`.

## Reversal Conditions
Reconsider only if a specific requirement type's `type_metadata` grows so large and query-critical (e.g., needs its own indexes, constraints, or high-volume joins) that it warrants promotion to a dedicated child table — at that point, that one type can be split out via a normal migration without affecting the other types or the core chain.
