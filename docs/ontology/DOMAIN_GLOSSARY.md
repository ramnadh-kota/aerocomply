# AeroComply Domain Glossary v1.0

Terms are drawn from ICAO Annex 8 (Airworthiness of Aircraft) and Annex 6 (Operation of Aircraft), FAA 14 CFR Parts 21/39/43/91/121/145, EASA Part-21/Part-M/Part-ML/Part-CAMO/Part-145/Part-66, UK CAA retained-EASA regulations (UK Reg (EU) 1321/2014 as amended), India DGCA Aircraft Rules 1937/2021 and Civil Aviation Requirements (CARs), and CASA Australia's Civil Aviation Safety Regulations (CASR) Part 39/42. Where authorities use different terms for the same concept, or the same term for different concepts, this is called out explicitly rather than silently picking one.

Each entry gives: the general industry meaning, how AeroComply defines/uses the term, and why — because aviation terminology is genuinely inconsistent across authorities, and collapsing that inconsistency silently is how compliance systems produce wrong answers.

---

## Aircraft identity

**Type Certificate (TC)** — The foundational approval issued by a civil aviation authority (acting as the "State of Design") certifying that a design meets airworthiness standards. Held by the manufacturer ("Type Certificate Holder" / TC holder). *AeroComply usage*: `AircraftType` represents one TC's basic design family (e.g., "Boeing 737", "Airbus A320").

**Type/Model/Series (TMS)**, also called **Aircraft Variant** — A specific certificated model within a type family, each with its own Type Certificate Data Sheet (TCDS) entry, limitations, and often its own eligible engine/equipment list (e.g., 737-800 vs. 737 MAX 8; A320-200 vs. A320neo). *Industry ambiguity*: "type" is used loosely in casual speech to mean what regulators formally call "model" or "TMS." *AeroComply usage*: `AircraftVariant` (a.k.a. Model) is the certificated model — this is the level at which most AD applicability and engine-eligibility rules are actually written, not the parent Type.

**Manufacturer Serial Number (MSN)**, also **Construction Number (c/n)** — A unique, permanent, never-reused identifier assigned by the manufacturer to one physical airframe. *AeroComply usage*: `Aircraft.msn` is the immutable natural key for a physical aircraft, independent of registration or operator.

**Registration** (tail number / registration mark, e.g., N12345, VT-ABC, G-ABCD) — Assigned by the national civil aviation authority of the State of Registry. **Can change** over an aircraft's life (re-registration on sale, lease transfer, change of operator's country). *Critical distinction*: registration identifies *who currently operates/registers* the aircraft; MSN identifies *which physical airframe* it is. AeroComply must never conflate the two as a stable identity key — see [Domain Invariant #1](DOMAIN_INVARIANTS.md).

**State of Registry** vs **State of Design** (ICAO Annex 8) — State of Registry is the country where the aircraft is registered (and whose CAA holds primary continuing-airworthiness oversight). State of Design is the country of the Type Certificate holder (issues ADs against the type design). An aircraft's regulatory obligations flow from *both*: the design authority's ADs apply by design, and the State of Registry (or its delegate, e.g., an EASA member state) enforces/validates them, sometimes adding local mandatory requirements.

## Continuing airworthiness & maintenance organizations

**Continuing Airworthiness** — The set of processes ensuring an aircraft remains compliant with its type design and safe to operate throughout its operational life, as distinct from initial certification. This is precisely AeroComply's product domain.

**CAMO (Continuing Airworthiness Management Organisation)** — EASA/UK CAA term (Part-CAMO, formerly Part-M Subpart G) for the organization responsible for managing an aircraft's continuing airworthiness: tracking AD/SB status, scheduling maintenance, issuing Airworthiness Review Certificates. FAA has no exact equivalent term — the operator itself typically holds this responsibility directly (14 CFR 91.403) or delegates via contract to an approved maintenance provider. *AeroComply usage*: `Organization.org_type` includes `CAMO` as a role a tenant organization can hold, without assuming every tenant is EASA-regulated.

**MRO (Maintenance, Repair, and Overhaul organization)** — An organization approved to perform maintenance (FAA Part 145 / EASA Part-145 / equivalent). Distinct from a CAMO: an MRO *performs* maintenance; a CAMO *manages/decides* what maintenance is required and when. A single company can hold both approvals.

**Operator** — The entity that operates the aircraft commercially or otherwise (may or may not be the registered owner; may or may not be the CAMO). *AeroComply usage*: `Aircraft.operator_organization_id` — deliberately separate from ownership, which is out of M1 scope.

## Regulatory instruments

**Airworthiness Directive (AD)** — A *legally mandatory* corrective action issued by the State of Design's (or validating State's) civil aviation authority when an unsafe condition is found in a product, part, or appliance. Structure is broadly consistent across FAA (14 CFR Part 39), EASA, UK CAA, and CASA: an *applicability* paragraph (by TC holder, model, MSN/serial ranges, sometimes further narrowed by installed engine/component part number or prior modification/SB embodiment), a *required action*, and a *compliance time* (a single deadline or an initial + repetitive interval). ADs can *supersede* earlier ADs (fully or partially replacing them) — the superseded AD's history remains legally and operationally relevant (an aircraft's compliance history references the AD revision that was in force at the time). **Not every regulatory requirement is an AD** — see below.

**Service Bulletin (SB)** — A manufacturer-issued (OEM) recommendation for inspection, modification, or repair. *Not mandatory on its own*; becomes mandatory only when a regulatory authority references it inside an AD (a very common pattern: "accomplish the actions in [SB reference]"), or when a specific operator's maintenance program elects to require it. *AeroComply usage*: modeled as a `RegulatoryRequirement` with `requirement_type = SB` only when we need to track it as an obligation in its own right (typically because an AD references it); an SB with no regulatory mandate behind it is tracked as OEM guidance, not a compliance obligation.

**Regulation / Implementing Rule** — The base legal rule (e.g., an EASA Implementing Regulation, an FAA 14 CFR Part) establishing a continuing requirement (e.g., a periodic inspection program requirement) that isn't tied to one specific unsafe-condition finding the way an AD is. Generally has broader, more static applicability (by category of aircraft/operation) rather than by MSN.

**AMC (Acceptable Means of Compliance)** and **GM (Guidance Material)** — EASA (and now UK CAA) concepts: AMC describes *a* way (not the only way) to comply with an Implementing Rule; GM explains/clarifies but imposes no obligation itself. **Critically, AMC/GM are non-binding** — an operator may use an "Alternative Means of Compliance" (AltMoC) instead. This is fundamentally different from an AD, which is binding as written. *AeroComply implication*: applicability logic for AMC/GM (when eventually modeled) must never be treated as mandatory the way AD applicability is — this is a real correctness hazard if the ontology collapses "regulatory document" and "mandatory obligation" into one thing. This is precisely why `RegulatoryRequirement.requirement_type` exists as a discriminator rather than assuming uniform bindingness.

**SIB (Safety Information Bulletin)** (EASA) / **Special Airworthiness Information Bulletin, SAIB** (FAA) — Informational, non-mandatory safety notices. Can be a precursor to a future AD. Non-binding — same caution as AMC/GM applies.

**Mandatory Modification / Mandatory Continuing Airworthiness Information** — Terms used variably (India DGCA and others) for a locally-mandated requirement, which may be the State of Registry's own adoption/incorporation of a foreign State of Design's AD, or a wholly local requirement. Many national authorities (including India DGCA, per common practice) do not always author fully independent AD technical content for foreign-type-certificated aircraft; instead they issue an adoption notice making the State-of-Design AD mandatory within their jurisdiction. *AeroComply implication*: `RegulatoryDocument` needs to represent both "originating" documents and "adopting/validating" documents from a different authority, linked via `references_requirement_id` — a requirement's *authority of record* for enforcement purposes is not always its *authority of origin*.

**Effective Date** vs **Compliance Time** — Effective date is when the regulatory document itself takes legal effect (starts existing as binding). Compliance time is the deadline (often expressed relative to effective date, e.g., "within the next 600 flight hours" or "before further flight," or as a repetitive interval) by which the *required action* must be accomplished for a *specific* affected aircraft. These are not the same date and must not be modeled as one field.

**Supersession** — A later regulatory document (typically an AD) can partially or fully replace an earlier one. The superseded document does not vanish: aircraft assessed under the older revision, and historical compliance determinations made against it, must remain queryable ("what was AeroComply's understanding on 1 March 2025" — the CTO's own requirement from the M0 gate).

## Applicability and compliance concepts (AeroComply's core IP — kept deliberately distinct)

**Regulatory Requirement** — The generic obligation entity (an AD, SB-under-mandate, or future requirement type) as *published* by an authority — the "what the rule says," independent of any specific aircraft.

**Applicability Rule** — A *structured, machine-evaluable* encoding of a Regulatory Requirement's applicability paragraph (e.g., "applies to Model X, MSN 1001–1500, with Engine Model Y installed, unless SB Z has been embodied"). Authored/reviewed by a human from the source text; this is deliberately *not* the raw regulatory text — it's AeroComply's structured interpretation of it.

**Applicability Condition** — One atomic predicate inside an Applicability Rule's condition tree (e.g., "engine_model = Y", "msn BETWEEN 1001 AND 1500", "NOT embodied(SB Z)"). Kept as a distinct concept from the Rule itself so that individual conditions can be traced, tested, and reused/composed rather than treating the whole rule as an opaque blob.

**Applicability Assessment** — The *result* of evaluating an Applicability Rule against one specific aircraft's configuration at a point in time: `system_result` (APPLICABLE / NOT_APPLICABLE / REVIEW_REQUIRED / INSUFFICIENT_DATA), confidence, and reasoning trace. Produced solely by the deterministic rules engine.

**Compliance Decision** / **Final Status** — What the *organization* ultimately records as its compliance position for a given aircraft/requirement, after human review of the Applicability Assessment. May equal the system result (human `ACCEPTED`) or diverge from it (human `OVERRIDDEN`, with a mandatory documented reason).

**Human Decision** — The specific act of a qualified, authorized person accepting or overriding a system Applicability Assessment. A first-class, auditable event — never inferred, never defaulted silently.

*Why these five are not collapsed into one entity*: a single "compliance status" field (as the CTO's earlier M0 directive already established for the assessment lifecycle) cannot separately answer "what did the rule say," "what did we compute," and "what did a human decide" — which is exactly the traceability chain AeroComply exists to provide (WHAT → WHY → SOURCE → DATA → EVIDENCE → ACTION, per the founding product vision).

## Physical asset & configuration concepts

**Component** — Industry usage is inconsistent: sometimes means any removable part, sometimes specifically a maintenance-significant item tracked in the maintenance program, sometimes (loosely) any hardware at all. *AeroComply usage*: `Component` is a *design-level* entity — a specific, interchangeable part design (identified by manufacturer + part number), independent of any physical instance. See "Part Number vs Serial Number" below.

**Part Number (P/N)** — Identifies an interchangeable *design*, not a specific physical item. Many physical items can share one part number.

**Serial Number (S/N)** — Identifies one specific physical instance of a serialized part. **Not all parts are serialized** — many are tracked only by part number/batch/lot (consumables, standard hardware) with no individual traceability requirement. This distinction matters: AeroComply cannot assume every `Component` has a serial number.

**Life-Limited Part (LLP)** — A serialized component (overwhelmingly common in engine rotating parts — disks, shafts) with a certified maximum life (cycles or hours) beyond which it must be removed from service permanently, tracked cumulatively *across every aircraft/engine it has ever been installed on* — not reset per installation. This is a distinct, higher-stakes traceability requirement from ordinary component tracking and is explicitly deferred past M1 (see [M1_SCOPE.md](M1_SCOPE.md)) rather than half-modeled.

**Component Installation** — A time-bounded fact: "this specific serialized component instance occupied this position on this parent asset (aircraft or engine) from installation date to removal date (or present)." This is the entity that makes historical configuration reconstruction possible — see [TEMPORAL_MODEL.md](TEMPORAL_MODEL.md).

**Aircraft Configuration** — Not a stored entity in itself, but a *derived, point-in-time view*: the complete set of an aircraft's variant, installed engines (with position), installed components (with position), and embodied modifications, as of a given timestamp. Reconstructed by querying installation/removal history as-of that timestamp, never stored as a mutable "current state" snapshot that could drift from the historical record.

**Modification** — A change to an aircraft's type design baseline (e.g., an installed Supplemental Type Certificate (STC), a major repair per an approved data package) that can itself affect which regulatory requirements apply going forward (a common AD applicability exclusion is "except aircraft modified per STC/SB X"). Deferred past M1 as a fully independent entity — see M1_SCOPE.md — but the ontology's `references_requirement_id` and configuration-snapshot design leave room for it without a later schema break.

## Evidence & provenance concepts

**Evidence** — Any artifact or structured record that supports a compliance conclusion: a maintenance record, an uploaded OEM document, an inspection record, or a structured database fact (e.g., "component installation record proves the excluding modification was embodied"). Evidence is always linked to the specific Applicability Assessment it supports, never left implicit.

**Provenance** — For regulatory data specifically: which authority published it, the original document and revision, publication/effective dates, how it was extracted (manual entry vs. parsed), and which rule/assessment engine version interpreted it. AeroComply must be able to distinguish **source** (what the authority published), **interpretation** (AeroComply's structured rule derived from that source, authored/reviewed by a human), and **decision** (the assessment and eventual human compliance decision) as three separate, separately-versioned layers — never conflated into a single "regulatory record."

---

## Ambiguity register (see full analysis in [AMBIGUITY_ANALYSIS.md](AMBIGUITY_ANALYSIS.md))

| Term | Industry ambiguity | AeroComply resolution |
|---|---|---|
| "Type" | Casually means Type, Model, or TMS interchangeably | Split into `AircraftType` (TC family) and `AircraftVariant` (certificated model/TMS) |
| "Component" | Ranges from "any part" to "maintenance-significant item" | Design-level entity only; physical instance is a separate serialized concept |
| "Configuration" | Sometimes means current state, sometimes full history | Always a derived as-of view, never a stored mutable snapshot |
| "AD" (used generically for "regulatory requirement") | Non-aviation readers (and some casual industry usage) use "AD" to mean any mandatory rule | `RegulatoryRequirement.requirement_type` discriminates AD from SB/Regulation/AMC/GM/SIB/Notice explicitly |
| "Compliant" / "Compliance status" | Conflates system computation with human/organizational decision | Split into `system_result`, `human_decision`, `final_status` (per ADR-005) |
| "Effective date" | Sometimes used loosely to mean compliance deadline | Kept strictly distinct from `compliance_time` |
