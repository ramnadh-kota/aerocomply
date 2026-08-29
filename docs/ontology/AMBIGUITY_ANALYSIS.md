# AeroComply Ambiguity Analysis v1.0

Aviation terminology is genuinely inconsistent across authorities and even within one authority's own documents. This document is the authoritative record of every concept where that ambiguity could have caused AeroComply to build the wrong thing, what we chose, why, and what we deliberately left unmodeled rather than guess at. (A condensed cross-reference table lives in [DOMAIN_GLOSSARY.md](DOMAIN_GLOSSARY.md); this document is the full analysis it points back to.)

For each concept: **Industry meaning** (what practitioners across the researched jurisdictions actually mean, including where they disagree) → **AeroComply meaning** (what we build) → **Why** (the reasoning) → **Deliberately not modeled yet** (the part of the ambiguity we're choosing not to resolve in M1).

---

## 1. "Type" (Aircraft Type / Model / Variant / TMS)

**Industry meaning**: "Type" is used at three different precision levels depending on context — a Type Certificate family ("Boeing 737"), a specific certificated model within that family ("737-800"), and colloquially sometimes just "the aircraft" generically. FAA parlance often says "Type/Model/Series" (TMS) for the certificated-model level; EASA's TCDS structure calls the same level "variant" or lists it under one TC with multiple approved models.

**AeroComply meaning**: `AircraftType` = the TC family; `AircraftVariant` = the certificated model/TMS level.

**Why**: AD applicability is almost always written at the certificated-model level, not the parent type family — collapsing the two would force every applicability rule to either over-apply (wrongly binding a 737-800-specific AD to all 737s) or need an ad hoc model-list exception on every rule, which is worse than just having the right two-level hierarchy from the start.

**Deliberately not modeled yet**: sub-variant configuration standards below the TCDS model level (e.g., specific software/avionics standard within one certificated model) — these exist in reality but are not yet common enough in our researched AD applicability text to justify a fourth hierarchy level in M1; when needed, they fit inside `Aircraft`'s own configuration snapshot (via installed components/modifications) rather than requiring a new type-hierarchy tier.

## 2. "Component" vs. "Part"

**Industry meaning**: FAA (14 CFR 43) tends to say "part"; EASA (Part-M/Part-145) tends to say "component." Neither authority's text assigns different obligations to the two terms — they are used near-interchangeably for "a piece of hardware installed on or intended for installation on an aircraft."

**AeroComply meaning**: One entity, `Component`, used for both. No separate `Part` table (ADR-009).

**Why**: We checked specifically for a behavioral distinction (different obligations, different tracking requirements) between the two terms across all five researched jurisdictions and found none — only a naming preference difference. Modeling them separately would be a synonym duplication with no correctness benefit, and duplication invites the two "copies" to drift apart in practice (one gets a field the other doesn't, etc.).

**Deliberately not modeled yet**: a controlled vocabulary mapping AeroComply's internal `Component` to each authority's preferred term for display purposes (i.e., showing "Part Number" to an FAA-context user and "Component" to an EASA-context user) — a UI/localization concern, not a data-model concern, deferred past M1.

## 3. "Configuration"

**Industry meaning**: Used to mean both "the aircraft's current physical state" (a snapshot) and, more loosely, "the aircraft's full configuration history" — maintenance and engineering conversations shift between these meanings without always flagging which is intended.

**AeroComply meaning**: `Aircraft Configuration` is never a stored thing — it is always a derived, as-of-timestamp query result (ADR-010).

**Why**: A mutable "current configuration" record is the single easiest way to introduce silent data corruption in this whole system (it can drift from the installation history that's supposed to be its source), and the ambiguity of "current vs. historical" evaporates entirely once configuration is defined as "the answer to an as-of query," because that query works identically for `NOW()` and any past timestamp.

**Deliberately not modeled yet**: a materialized/cached "current configuration" read-side view for performance — explicitly deferred until as-of query performance is a measured problem (ADR-010's Reversal Conditions), not built preemptively.

## 4. "AD" used generically for "any mandatory regulatory requirement"

**Industry meaning**: Practitioners (and especially non-specialist software audiences) often say "AD" loosely to mean any mandatory compliance item, when technically only a true Airworthiness Directive carries that specific legal mandatory-by-default weight; a Service Bulletin, Regulation, AMC, GM, or SIB each has different (and sometimes non-mandatory) legal weight.

**AeroComply meaning**: `RegulatoryRequirement.requirement_type` is an explicit discriminator (AD/SB/Regulation/Rule/AMC/GM/SIB/Notice/Other); nothing is assumed mandatory just because it's a "regulatory document."

**Why**: this is a correctness-critical distinction, not a pedantic one — treating a non-binding AMC or SIB as if it carries AD-level mandatory force would be a materially wrong compliance answer, exactly the kind of "AI/system presents unsupported conclusions as facts" failure the founding product vision explicitly prohibits.

**Deliberately not modeled yet**: type-specific applicability *evaluation* logic for anything other than AD (SB-under-mandate is the only other type with a clear evaluation path reused from AD; AMC/GM's non-binding semantics need their own logic, explicitly M2+ per [M1_SCOPE.md](M1_SCOPE.md)).

## 5. "Compliant" / "Compliance Status"

**Industry meaning**: Used colloquially to mean one single yes/no state, collapsing "what the rule says," "what our system computed," and "what our organization has decided/documented" into one word.

**AeroComply meaning**: Three distinct fields — `system_result`, `human_decision`, `final_status` — never one.

**Why**: already established at the M0 architecture level (ADR-005); restated here because it is *also* a terminology-ambiguity issue, not purely an architecture one — the word "compliant" itself is the ambiguity, and the schema's three-field split is how we resolve it without banning the word from conversation (users can still say "is it compliant," the system just always answers with the right one of the three fields, in context).

**Deliberately not modeled yet**: an aggregate fleet-level or organization-level single "compliance score" (mentioned in the original product Dashboard vision) — that is explicitly a *derived reporting metric* computed by aggregating many `final_status` values, never a stored field that could be mistaken for a fourth authoritative state.

## 6. "Effective Date"

**Industry meaning**: Sometimes used to mean "when the document became law," sometimes loosely to mean "the deadline by which affected aircraft must comply" — the second usage is technically wrong (that's the compliance time) but appears often enough in casual industry conversation to be a real source of confusion.

**AeroComply meaning**: `effective_date` (on `RegulatoryDocument`) and `compliance_time` (on `RegulatoryRequirement`) are always kept as separate fields with no derivation formula between them.

**Why**: Research found no consistent computable relationship between the two across the studied jurisdictions (compliance time can be a fixed date, an hours/cycles interval, or "before further flight") — collapsing them or deriving one from the other would misrepresent some real fraction of actual requirements.

**Deliberately not modeled yet**: a structured, machine-evaluable representation of compliance-time *types* (fixed date vs. hours/cycles interval vs. "before further flight") — M1 stores `compliance_time` as a value the rules engine can reason about only in simple cases; fully general compliance-time evaluation logic (e.g., tracking operational hours toward an interval-based deadline) is M2+ scope, since it requires operational-hours data AeroComply does not yet ingest.

## 7. "Engine" — component or asset?

**Industry meaning**: Maintenance programs sometimes list engines under the aircraft's overall "component" inventory for tracking-list purposes, while treating them, functionally, as having their own certification and compliance stream entirely separate from the airframe.

**AeroComply meaning**: Engine is a first-class assessable asset (ADR-008), installed via the same interval-table mechanism as a component, but never itself a `Component` row.

**Why**: fully explained in ADR-008 — the deciding factor was whether the entity needs independent applicability-assessment capability (it does), not how it happens to appear on an inventory list.

**Deliberately not modeled yet**: Auxiliary Power Units (APUs) and propellers, which share exactly the same "own-TC, own-AD-stream, installed-on-airframe" shape as engines — not included in M1's entity list purely for scope discipline, not because the ambiguity analysis found a reason to treat them differently; when added (M2+), they should reuse the `Engine`-shaped pattern (or a shared abstraction over it), not reinvent one.
