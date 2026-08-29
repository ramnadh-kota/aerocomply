# ADR-009 — Component/ComponentInstance/ComponentInstallation Three-Way Split

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
The CTO's ontology brief asked us to critically analyze whether Component, Part, Serialized Component, and Installation Event should be separate concepts. Research found: (1) "part" and "component" are used near-interchangeably across FAA (14 CFR 43) and EASA (Part-M) continuing-airworthiness text — no authority draws a behavioral distinction between the two terms; (2) not every part is individually serialized — many are batch/lot-tracked consumables with no per-unit identity; (3) a single physical serialized unit can be installed, removed, and later installed elsewhere (including on a different aircraft), so its installation history is a distinct temporal fact from the unit's own identity.

## Decision
Three tables, not four: `Component` (design-level; "Part" and "Component" are treated as the same concept under one name, since no real behavioral distinction exists between the terms), `ComponentInstance` (a specific serialized physical unit — created only for components with `requires_serialization = true`), and `ComponentInstallation` (the time-bounded fact linking one `ComponentInstance` to one position on one parent asset).

## Alternatives Considered
- **Four separate tables (adding a distinct "Part" table alongside "Component")**: rejected after confirming no authority's regulatory text assigns different obligations or behavior to "part" vs. "component" — this would be a synonym duplication adding join overhead and modeling confusion with no compensating clarity or correctness benefit.
- **Single `Component` table with a nullable `serial_number` column, no separate instance table**: rejected — this cannot represent a non-serialized part class as a real constraint (every row could technically have a serial number filled in even when the part doesn't warrant individual traceability), and cannot represent one physical unit's multiple installation periods across its service life (a batch/lot part has no "installation history" in the individually-traceable sense; a serialized part does, and that shape difference needs to be a schema difference, not a convention).
- **Merging ComponentInstance and ComponentInstallation into one row** (adding installation dates directly to the instance): rejected — a single physical unit can be installed, removed, and later reinstalled elsewhere; collapsing the two would either lose that full history (if the instance row is mutated in place) or force awkward duplicate instance rows per installation period (destroying the instance's own stable identity, e.g. for life-limited part tracking in later milestones).

## Consequences
- Non-serialized parts (the majority of consumable hardware) never get a `ComponentInstance` row — deliberately, so the schema never fabricates false individual traceability the real maintenance record doesn't support.
- A life-limited part's cumulative life tracking (explicitly deferred past M1) can later be added as fields/relations on `ComponentInstance` without touching `ComponentInstallation`, because the instance's identity is already independent of any one installation period.
- Evidence linking (§8 of the ontology) can reference a `ComponentInstallation` row directly as a structured evidence type, since it is a well-defined, independently addressable fact.

## Reversal Conditions
Reconsider only if a future regulatory domain genuinely requires treating "part" and "component" as distinct entities with different obligations (no such requirement was found in any of the five jurisdictions researched for v1.0) — until then, this is not expected to change.
