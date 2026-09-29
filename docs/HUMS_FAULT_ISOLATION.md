# HUMS Fault Isolation (H4)

See `docs/HUMS_DIAGNOSTICS.md` for the full diagnostic candidate model,
scoring, and lifecycle. This document covers specifically how a diagnostic
candidate is **located** — mapped from an asset down to the narrowest
component/subsystem the actual evidence supports, never further.

## The isolation hierarchy this codebase actually has

The H4 spec's target hierarchy is:

```
Asset -> System -> Subsystem -> Component -> Potential fault mode
```

The H0/H4 audit confirmed this codebase's domain model does **not** have
separate `System`/`Subsystem` entities — only `Asset` and `Component`
(`app/models/component.py`), where `Component.component_type` (ENGINE,
AVIONICS, MOTOR, GPS, SENSOR, etc.) is the closest existing concept to a
"system" classification. **H4 isolates to exactly this real hierarchy —
`Asset -> Component (with its component_type) -> Fault mode` — and does
not fabricate a deeper System/Subsystem layer that doesn't exist in the
domain model.** This is a deliberate, documented scope boundary, not an
oversight: inventing a fake hierarchy to match the spec's illustrative
diagram would produce isolation claims the data can't actually support.

## How isolation is bounded by evidence

Every `HUMSDiagnosticCandidate` carries `asset_id` and (when the
originating `HUMSSensor` has one) `component_id`. If a sensor has no
`component_id` (not yet installed against a tracked component), its
candidates are asset-scoped only — H4 never guesses a component. This
mirrors the same "unassigned sensors" bucket H3's
`get_asset_health_intelligence` already established for component
grouping (`by_component[None]`).

**"Only isolate as far as the evidence supports" (H4 spec section 21)** is
enforced structurally, not by an extra rule: a fault signature's
`required`/`supporting` conditions only ever reference `feature_type`
values present in the evaluated sensor's own feature set. There is no
signature in this codebase's registry that claims a *specific* fault mode
(e.g. "bearing" vs. "gear tooth") from evidence that only supports a
*general* one (e.g. "elevated vibration on this component") — the two
demonstrative signatures (`VIB-BRG-001`, `VIB-IMB-001`) are themselves the
most specific claims the current evidence vocabulary (RMS, crest factor,
kurtosis, trend) can honestly support. A future, more specific signature
(e.g. requiring a particular frequency band matching a known bearing
defect frequency) would need genuine frequency-band evidence to back it —
not implemented in H4 (see `docs/HUMS_SIGNAL_PROCESSING.md`'s
`band_energy` feature, which exists but isn't yet wired into a
bearing-frequency-specific signature).

## Per-sensor vs. per-component evaluation

`diagnostic_service.evaluate_and_persist_diagnostics` evaluates fault
signatures **per sensor** (each sensor's own `dict[feature_type,
FeatureHealthResult]`), because the two demonstrative vibration signatures
are about one sensor's own RMS/kurtosis/crest-factor pattern, not a
cross-sensor combination. The **sensor-fault safeguard**
(`detect_sensor_fault_candidate`) is the one check that operates across
all sensors *on the same component* — it specifically needs to compare
one sensor's abnormality against its siblings' normalcy to distinguish
"this sensor is malfunctioning" from "this component has a real fault."

## Isolation examples this architecture actually produces

**Evidence supports only component-level abnormality** (e.g. a single
elevated feature that doesn't satisfy any signature's required
conditions): **no candidate is generated at all** — H4 never emits a
vague "something might be wrong with this component" candidate; either
the evidence supports a specific fault-signature match, or nothing is
claimed (verified in
`tests/unit/test_hums_diagnostic_engine.py::test_single_weak_feature_below_threshold_produces_no_candidate`).

**Evidence supports a specific signature**: the candidate's `fault_name`
("Possible bearing degradation"), `component_id`, and `sensor_ids` name
exactly the sensor(s)/component the matched evidence came from — never
escalated to "propulsion system" or "aircraft" when only one sensor on one
component actually deviated.

## Component graph / knowledge graph

The H4 spec section 22 allows Neo4j as a *derived* relationship/index layer
if one exists, with PostgreSQL remaining authoritative. The H0 audit
confirmed `app/graph/` is an empty stub — no Neo4j integration exists
anywhere in this codebase. H4 does not introduce one; `Component.asset_id`
(a plain PostgreSQL foreign key) is the only relationship H4 traverses, and
it remains the sole source of truth, consistent with every prior HUMS
milestone's explicit non-negotiable ("PostgreSQL remains the authoritative
source of truth").

## Readiness / Compliance / MRO — inputs, never overridden

Fault isolation output (`component_id`, `fault_name`, severity) is
available to the existing readiness/compliance/MRO systems exactly the way
H1's exceedances and H3's health-degradation signals already are: via
`ProactiveSignalRecord`, which the existing M7 intelligence layer already
consumes. H4 does not call into or modify the readiness engine, the
compliance engine, or work-order creation directly — see
`docs/HUMS_DIAGNOSTICS.md`'s "Existing Finding/Evidence/Compliance/
Readiness" section for the full non-negotiable list of what H4 must never
do autonomously.

## Limitations

- No System/Subsystem layer — isolates to `Asset -> Component` only, per
  this codebase's actual domain model (see above).
- No frequency-band-specific fault signatures (e.g. bearing defect
  frequencies, gear-mesh harmonics) — `band_energy`/`dominant_frequency`
  features exist (H2) but aren't yet wired into a signature that claims a
  specific fault mode from them.
- Sensor-fault detection requires ≥2 sensors per component; a
  single-sensor component has no basis to distinguish sensor fault from
  physical fault, and H4 does not guess in that case.
