# ADR-008 — Engine as a First-Class Assessable Asset, Not a Component

## Status
Proposed (part of Aviation Ontology v1.0 — pending CTO approval)

## Context
An installed engine is subject to two independent regulatory streams: its own Type-Certificate-based AD/SB regime (issued against the engine's TC, separate from the airframe's), and its role as a configuration factor in airframe-level AD applicability (many airframe ADs are scoped by installed engine model). An engine also has a well-defined installation position and installation/removal history on the aircraft, structurally similar to a serialized component.

## Decision
`Engine` is modeled as a first-class entity capable of being the *subject* of its own `ApplicabilityAssessment` (via a `subject_type` discriminator: `AIRCRAFT | ENGINE`), symmetric to `Aircraft`. Its physical installation relationship to the aircraft reuses the same time-bounded installation-interval pattern as `ComponentInstallation` (via `EngineInstallation`, structurally identical in shape) rather than either (a) treating the engine as merely a component with no independent applicability, or (b) inventing a wholly separate installation mechanism just for engines.

## Alternatives Considered
- **Engine as a Component subtype**: rejected — a `Component` in this ontology has no mechanism to be independently assessed against its own applicability rules (M1 components are only evaluated as configuration *inputs* to the aircraft's assessment, not as assessment subjects themselves). Making Engine a Component subtype would require building that independent-assessment capability specifically for engines anyway, at which point it is no longer really "just a component" — better to model the distinction honestly now than retrofit it later, which is exactly the kind of schema break ADR-006 (Regulatory Requirement as core abstraction) was written to avoid for a structurally similar reason.
- **Engine as a completely separate asset hierarchy with its own installation mechanism**: rejected — the *installation* relationship (time-bounded, positional, on a parent asset) is identical in shape to component installation; duplicating that mechanism for no behavioral difference would violate the "don't build parallel structures for the same concept" principle without any offsetting benefit.

## Consequences
- `ApplicabilityAssessment` gains a `subject_type`/`subject_id` pair (polymorphic over Aircraft/Engine) instead of assuming Aircraft is the only assessable subject — a real but bounded schema implication, planned into M1 from the start rather than discovered as a retrofit.
- `EngineInstallation` and `ComponentInstallation` share the same interval-integrity invariants (domain invariants #7–#10) since they are structurally the same kind of fact about different asset types.
- A life-limited part carried inside an engine (M2+ scope) will, when modeled, need to track cumulative life *independent of which engine or aircraft it has been installed on* — this ADR's design does not block that, since `ComponentInstance` already exists as a distinct concept from any single installation.

## Worked demonstration: polymorphic subject stays type-safe and auditable

`ApplicabilityAssessment` gains `subject_type` (`AIRCRAFT | ENGINE`) and `subject_id` (a UUID meaning either an `Aircraft.id` or an `Engine.id`, depending on `subject_type`). Type safety and auditability are preserved by construction, not by convention alone:

- **Type safety**: a `CHECK` constraint ties `subject_type` to which of two mutually-exclusive nullable FK columns is populated (`aircraft_subject_id` / `engine_subject_id`) — i.e., the polymorphism is implemented as two real, separately-enforceable foreign keys plus a discriminator, not a single untyped UUID column with no referential integrity. This means the database itself rejects an `ApplicabilityAssessment` row claiming `subject_type = ENGINE` while pointing `aircraft_subject_id` at a real row, or pointing `engine_subject_id` at a nonexistent engine — the same pattern already used correctly for `Evidence.structured_record_id`'s looser polymorphism would have been the wrong choice here, precisely because assessment-subject identity is not "one of several evidence shapes" but a hard correctness requirement (an assessment's meaning depends entirely on which aircraft or engine it is about).
- **Auditability**: every downstream reference to "the subject of this assessment" (in reasoning text, in evidence linking, in the human-decision UI) reads `subject_type` explicitly rather than inferring it — so an audit trail or exported report can never accidentally display an engine-subject assessment as if it were about the host aircraft, or vice versa.

## Reversal Conditions
Reconsider if, in practice, engine-subject assessments turn out to need meaningfully different reasoning/evidence/evidence-linking behavior than aircraft-subject assessments (beyond the `subject_type` discriminator) — at that point, evaluate splitting `ApplicabilityAssessment` into a shared base with subject-specific extensions rather than one polymorphic table.
