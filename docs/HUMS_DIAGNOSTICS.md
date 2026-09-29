# HUMS Diagnostics (H4)

**H4 generates explainable diagnostic candidates and fault-isolation
hypotheses. It does not autonomously confirm faults, certify aircraft,
determine airworthiness, or make safety-critical decisions.**

See `docs/HUMS_FAULT_ISOLATION.md` for how a candidate maps to an
asset/component location. This document covers the diagnostic model,
signature/rule engine, evidence correlation, confidence/severity, and the
human-confirmation lifecycle.

## Why H3's structures are reused as the "anomaly" source

The H4 spec explicitly invited this: "If H3's deviation/health structures
can serve as the anomaly source, use them." H3's `FeatureHealthResult`
(deviation state, trend direction, consecutive-deviation count, quality,
confidence) already **is** a per-feature anomaly record — H4 does not
introduce a separate `HUMSAnomaly` table. A signature's conditions are
functions over `dict[feature_type, FeatureHealthResult]`
(`app/services/hums/fault_signatures.py`), so "anomaly correlation" in H4
is literally "read multiple H3 FeatureHealthResults for the same sensor/
component together."

## Why fault signatures are in-code, not a DB table

The H4 spec's section 11 says: *"the exact schema should be determined
after auditing the existing rules architecture."* The H0/H4 audit found
`app/rules_engine/` is an empty stub — this codebase has no existing
DB-driven rule-versioning convention to extend. Building a full
signature-authoring data model for H4 alone, with no UI or workflow to
edit it, would be speculative infrastructure with no precedent elsewhere
in this codebase. Instead, `app/services/hums/fault_signatures.py` is a
versioned Python registry:

```python
FaultSignature(
    fault_code="VIB-BRG-001",
    fault_name="Possible bearing degradation",
    version="1.0",
    required=(...),      # ALL must be satisfied, or no candidate
    supporting=(...),     # weighted evidence, strengthens the score
    contradicting=(...),  # weighted evidence, weakens the score
    minimum_supporting=1,
)
```

Every generated `HUMSDiagnosticCandidate` row records `rule_version`, so a
row stays reproducible even after the code-level signature is later
revised — an explicit extension point for a future DB-driven editor is
documented here rather than built speculatively.

**These are demonstrative synthetic signatures** (`VIB-BRG-001` "possible
bearing degradation", `VIB-IMB-001` "possible rotor imbalance"), not real
aerospace engineering fault-diagnosis criteria for any specific airframe,
engine, or component. They exist to prove the architecture works
end-to-end, not to certify anything.

## Architecture

```
H3 FeatureHealthResult (per sensor, per feature_type)
            |
            v
    Fault Signature Matching  (app/services/hums/diagnostic_engine.py)
      required / supporting / contradicting conditions
            |
            v
    Diagnostic Scoring & Confidence/Severity
            |
            v
    HUMSDiagnosticCandidate (persisted, app/services/hums/diagnostic_service.py)
            |
    +-------+-------+
    v               v
ProactiveSignalRecord   (existing Finding/Evidence chain --
(SUPPORTED only,         NOT auto-created; see "Evidence
 dedup by candidate id)   lineage" below)
```

Module boundaries (same convention as H2/H3):

- `fault_signatures.py` — pure, in-code signature registry + condition
  builders. No DB access.
- `diagnostic_engine.py` — pure scoring/matching functions
  (`evaluate_signature`, `generate_candidates`,
  `detect_sensor_fault_candidate`). No DB access.
- `diagnostic_service.py` — the only module touching the DB: upserts
  `HUMSDiagnosticCandidate` rows, syncs `ProactiveSignalRecord`, records
  audit events, and implements `confirm_candidate`/`reject_candidate`.
- `hums_service.py` — single entry point the API calls
  (`list_asset_diagnostics`, `get_diagnostic`, `confirm_diagnostic`,
  `reject_diagnostic`), same pattern as every other HUMS milestone.

## Scoring (never a black box)

```
score = clamp(0, 1,
    0.4                                                    # REQUIRED_BASE_SCORE (all required conditions met)
  + 0.5 * (satisfied_supporting_weight / total_supporting_weight)
  - 0.3 * (satisfied_contradicting_weight / total_contradicting_weight)
)
```

A candidate is only generated if:
1. **All** required conditions are satisfied.
2. At least `minimum_supporting` supporting conditions are satisfied.
3. The resulting score is `>= MIN_SCORE_THRESHOLD` (0.25) — a safety
   floor: a single weak, unsupported signal never fabricates a diagnosis
   (verified in
   `tests/unit/test_hums_diagnostic_engine.py::test_single_weak_feature_below_threshold_produces_no_candidate`).

Every `DiagnosticEvaluation` retains every condition it checked (satisfied
or not), so `HUMSDiagnosticCandidate.explanation`/`primary_evidence`/
`supporting_evidence`/`contradicting_evidence` can always answer "why was
this candidate generated" down to the individual condition.

## Severity vs. confidence (kept distinct, per spec section 19)

- **Severity** — derived from the worst H3 health state among the
  signature's relevant features (`CRITICAL`/`WARNING` → `HIGH`,
  `DEGRADED` → `MEDIUM`, `WATCH` → `LOW`). Answers: *if this diagnosis is
  correct, how bad is it?*
- **Confidence** — derived from the score and the feature confidences
  feeding it (`>=0.75` → `HIGH`, `>=0.5` → `MEDIUM`, else `LOW`). Answers:
  *how strong is the current evidence for this diagnosis?*

A candidate can be `severity=HIGH, confidence=LOW` — a potentially serious
fault that the evidence doesn't yet strongly support — and the two are
never conflated into one number
(`tests/unit/test_hums_diagnostic_engine.py::test_severity_distinct_from_confidence`).

## Candidate status / lifecycle

| Status | Set by |
|---|---|
| `SUPPORTED` | Evaluation engine (score ≥ 0.5) |
| `WEAK` | Evaluation engine (score in [0.25, 0.5)) |
| `CANDIDATE` | Initial/default state (not currently reached — every persisted row is SUPPORTED or WEAK on creation) |
| `CONFIRMED` | **Only** `POST /hums/diagnostics/{id}/confirm` — an authenticated, `HUMS_WRITE`-permitted human action |
| `REJECTED` | **Only** `POST /hums/diagnostics/{id}/reject` (requires a `reason`) |
| `RESOLVED` | Reserved for future workflow integration — not currently set by any code path |
| `UNSUPPORTED` | Reserved; not currently reached (candidates below the score threshold aren't persisted at all) |

**Once a candidate is `CONFIRMED`, `REJECTED`, or `RESOLVED`
(`HUMAN_LOCKED_STATUSES` in `diagnostic_service.py`), re-evaluation never
overwrites it** — verified in
`tests/integration/test_hums_diagnostics.py::test_confirm_and_reject_lifecycle_requires_authorized_action`.
Score/evidence snapshots as of the human decision are preserved.

## Alternative hypotheses (never collapsed)

`generate_candidates` evaluates **every** applicable signature and returns
**all** that matched, sorted strongest-first. `VIB-BRG-001` (bearing
degradation, requires elevated kurtosis) and `VIB-IMB-001` (rotor
imbalance, `contradicting` condition is elevated kurtosis) are
deliberately competing: a spiky, high-kurtosis vibration signal supports
bearing degradation strongly while simultaneously *contradicting* rotor
imbalance, so rotor imbalance survives only as a weaker, explicitly
contradicted alternative — not deleted, not hidden
(`tests/unit/test_hums_diagnostic_engine.py::test_competing_hypotheses_preserved_not_collapsed`).

## Sensor-fault safeguard

`diagnostic_engine.detect_sensor_fault_candidate`: if exactly one sensor
on a component shows meaningful deterioration (`DEGRADED`+) while every
other sensor on that same component reads `HEALTHY`/`WATCH`, a
`SEN-ANOM-001` ("possible sensor anomaly, not a physical fault") candidate
is generated **alongside** (not instead of) any physical-fault candidates
for that sensor — recommending the reviewer verify calibration/wiring
before condemning the component. Requires ≥2 sensors on the component to
apply (a single-sensor component has no basis for distinguishing "sensor
fault" from "physical fault"). If multiple sensors are simultaneously
abnormal, this is treated as better explained by a shared physical cause,
not a sensor fault.

## Temporal and operating-context correlation

**Temporal correlation** is implicit: every feature evaluated for one
diagnostic pass comes from the same bounded recent feature-history window
H3 already uses (`FEATURE_HISTORY_LIMIT` rows), so signals correlated in
that window are naturally correlated in the diagnosis. H4 does **not**
implement a separate configurable multi-window temporal-clustering engine
— that's a documented extension point, not built, because the current
architecture's single shared window already satisfies the spec's core
requirement without the added complexity.

**Operating-context correlation** (RPM/flight-phase/altitude/load) is
**not implemented** — same limitation H3 already documented for baselines:
this codebase's HUMS data has no co-located operating-context stream to
correlate against. Fabricating context-aware evidence was explicitly
disallowed by the spec ("Do not fabricate context when unavailable"), so
it is left as a documented extension point.

## Evidence lineage

```
Sensor Reading -> HUMSFeature -> HUMSBaseline -> Deviation -> Trend
    -> FeatureHealthResult ("anomaly") -> Fault Signature Match
    -> HUMSDiagnosticCandidate -> ProactiveSignalRecord
```

`HUMSDiagnosticCandidate.primary_evidence`/`supporting_evidence`/
`contradicting_evidence` each carry the full per-feature snapshot (current
value, baseline value, deviation state, trend direction, consecutive
count) at the moment the candidate was generated/refreshed — a reviewer
can trace "possible bearing degradation" back to the exact measurements
without a separate lookup.

## Existing Finding/Evidence/Compliance/Readiness — not duplicated, not auto-populated

H4 does **not** create a `Finding` or `Evidence` row automatically. A
diagnostic candidate is an **observation/hypothesis**, not a **Finding**
(defect) — preserving the existing
`Observation ≠ Anomaly ≠ Finding ≠ Defect` distinction. H4 surfaces
"suggested next inspection target" information via the candidate's
`fault_name`/`component_id`/explanation for a human to act on through the
**existing** Finding/Work Order/Inspection workflows — HUMS never creates
or approves a work order itself. Compliance and readiness are similarly
never written to directly by H4; `ProactiveSignalRecord` (which M7's
existing intelligence layer already reads) is the only integration point,
exactly as H1's exceedance pathway and H3's health-degradation pathway
already established.

## AI Assistant

`get_asset_hums_diagnostics` (ToolSpec registry, `app/services/ai/tools.py`)
reports exactly the stored candidate fields — status, severity, confidence,
score, evidence, alternatives. Its description explicitly instructs the
model to always state a candidate requires engineering confirmation and to
never claim a candidate is confirmed, that an aircraft is unsafe, or that
maintenance is required.

## Safety boundary tests (H4 spec section 39)

`tests/integration/test_hums_diagnostics.py` explicitly verifies H4 does
NOT: auto-confirm a candidate, auto-create a Finding, auto-ground an asset
(asset lifecycle `status` is asserted unchanged), or let cross-tenant/
unauthorized-role actions confirm/reject a candidate belonging to another
organization or without `HUMS_WRITE`.

## Async boundary

Same precedent as H2/H3: no Celery/RQ/cron in this codebase. Diagnostic
evaluation runs synchronously inside `get_asset_health_intelligence`/
`get_component_health_intelligence` (the same read-time trigger point H3's
`sync_health_signal` already established), bounded to per-sensor H3
evaluation calls — never an unbounded historical scan. Could move behind a
queue consumer later without changing `evaluate_and_persist_diagnostics`'s
signature.

## Future ML extension (not built)

`diagnostic_engine.py`'s `DiagnosticEvaluation`/`FaultSignature` shapes are
the clean interface a future statistical or ML-assisted scorer would
implement against (same inputs: `dict[feature_type, FeatureHealthResult]`,
same output: a scored, explained evaluation) — but H4 itself is 100%
rule-based and deterministic. Any future ML layer must augment, never
silently replace, the deterministic evidence trail.

## Limitations

- Two demonstrative vibration signatures only (`VIB-BRG-001`,
  `VIB-IMB-001`) plus the sensor-fault safeguard — not a comprehensive
  fault-signature library for any real aircraft/engine/component.
- No operating-context (RPM/phase/altitude) correlation.
- No configurable multi-window temporal clustering — a single shared
  H3 feature-history window only.
- Baseline drift: if a sustained anomaly persists across many ingestion
  batches, H3's baseline (which recomputes from "prior" history on every
  batch) can gradually absorb it as the new normal, weakening later
  diagnostic sensitivity to the *same, still-ongoing* anomaly — the same
  known limitation H3 documents for its own baseline, not fixed in H4.
  Diagnostics are most reliable against a freshly-emerging anomaly.
- No RESOLVED/UNSUPPORTED workflow is wired up yet (reserved states).
- Not RUL, prognostics, failure probability, survival analysis, Weibull
  modeling, digital twin, or fleet-wide intelligence — all explicitly out
  of scope per the H4 spec (belongs to H5+).
