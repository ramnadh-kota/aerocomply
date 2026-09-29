# HUMS Prognostics (H5)

**H5 provides prognostic estimates for decision support. RUL values are
not certified life limits and do not supersede approved maintenance
programs, OEM instructions, regulatory requirements, or authorized
engineering decisions.**

See `docs/HUMS_RUL_ENGINE.md` for the mathematical detail of degradation
fitting, threshold crossing, and uncertainty. This document covers PHM
architecture, reference-baseline strategy, usage normalization,
maintenance segmentation, and safety boundaries.

## The critical lesson from H3, applied here

H3's baseline recomputes from "prior" feature history on every ingestion.
If a **sustained** anomaly persists across many batches, that baseline
gradually absorbs it as new-normal — a real limitation documented in
`docs/HUMS_DIAGNOSTICS.md`. H5 cannot use that same continuously-refreshing
baseline as its degradation *reference*, because the entire point of a
degradation trajectory is to measure a *sustained* departure from a
**stable** starting point. Using a moving target would make the
measured "degradation" shrink as the reference itself drifts toward the
degraded state.

**H5's fix:** `degradation_service.get_reference_baseline` selects a
**fixed** reference — the earliest (`version=1`) `HUMSBaseline` row for a
(sensor, feature_type), which H3 never mutates once superseded. This is
Strategy A ("healthy reference window") combined with Strategy B
("maintenance-reset reference"): if the sensor's component has a more
recent `ComponentInstallation` record, the earliest baseline created
*after* that installation is used instead — so a component replacement
starts a genuinely fresh degradation trajectory rather than measuring
against a predecessor unit's history (verified in
`tests/integration/test_hums_prognostics.py::test_maintenance_reset_starts_new_reference_baseline`).
Strategy C (approved engineering limit) and D (historical) are addressed
via the threshold-sourcing mechanism below, not the reference-baseline
mechanism.

## Usage normalization — reusing existing architecture

Per spec section 10's explicit instruction not to duplicate existing
flight-hours/cycles architecture, `degradation_service.build_usage_trajectory`
calls the existing `flight_service.get_utilization(..., until=timestamp)`
(the same M5.3/M5.13 "Historical Baseline + SUM(Flights)" accounting
already used by M7's proactive intelligence) to compute cumulative flight
hours as of each feature observation's timestamp, whenever the asset has
any `Flight` records — labeled `usage_unit="FLIGHT_HOURS"`.

When an asset has no flight records at all (common for early-stage HUMS
demo data), H5 falls back to `usage_unit="HOURS_ELAPSED"` — wall-clock
elapsed hours from a fixed anchor (see below). This is **honestly labeled**
as a lower-fidelity proxy, never silently presented with flight-hour
precision it doesn't have.

### The anchor-consistency bug (caught during implementation)

`HOURS_ELAPSED` needs a zero-point. The first implementation computed it
as "the earliest row in whatever subset of feature rows was passed to
`build_usage_trajectory`" — which silently produced a **different**
zero-point (and therefore a different x-axis) depending on which subset
was passed. The model-fit call passed the full bounded trajectory; the
model-drift check passed only the last 3 rows — two different anchors for
the same trajectory, causing the drift check to compare against a
completely different (and wrong) x-axis than the one the model was fit on,
producing false `MODEL_STALE` flags even for a numerically perfect fit.

**Fix:** `degradation_service.get_usage_anchor` computes the zero-point
once, deterministically, from the reference baseline's
`source_window_start` (or the sensor's earliest feature row if no
reference exists yet) — the same value every time it's called for the
same (sensor, feature_type), regardless of which row subset the caller
happens to be working with.

## Degradation models

Two explainable model types (per spec section 12's explicit permission to
start simple and its warning against overfitting):

- **LINEAR** — ordinary least squares. Default choice.
- **ROBUST_LINEAR** — Theil-Sen estimator (median of all pairwise slopes).
  Automatically selected (`degradation_engine.select_model`) only when the
  plain linear fit's residuals show a clear outlier (`max |residual| / residual_std > 3`)
  — "prefer the simplest model that explains the observed degradation."

`PIECEWISE_LINEAR` and `EXPONENTIAL` are **documented extension points,
not implemented** — see Limitations.

## Trajectory states

`STABLE` / `DEGRADING` / `ACCELERATING` / `NON_MONOTONIC` /
`INSUFFICIENT_DATA` / `UNKNOWN`, determined by `determine_trajectory_state`
using the same "compare first-half vs. second-half slope" heuristic H3's
trend classification already established, applied here to the raw feature
values against the usage axis rather than to H3's own already-classified
trend.

## Maintenance segmentation

Handled entirely through the reference-baseline mechanism above: rather
than a separate "trajectory segment" table, a maintenance reset simply
changes *which* baseline version — and therefore which subset of feature
history (`rows = [r for r in rows if r.window_end >= reference.source_window_start]`
in `fit_and_persist_model`) — the degradation model is fit against. Old
pre-reset history remains in `HUMSFeature` for audit/trace purposes but is
excluded from the current model's fit.

## H4 diagnostic integration

`prognostic_service._find_related_diagnostic` links the strongest
non-rejected `HUMSDiagnosticCandidate` on the same asset as context. This
is surfaced in the prognostic record's explanation
(`"Related H4 diagnostic hypothesis: '...' (status=..., confidence=...) --
treated as contextual input uncertainty, not a confirmed failure mode."`)
— never treated as ground truth that would, say, force a specific
degradation model or threshold. A `REJECTED` diagnostic candidate is
excluded from consideration entirely.

## Threshold sourcing (never fabricated)

| Feature type | Threshold | Type |
|---|---|---|
| `rms` | `hums_service.VIBRATION_CRITICAL_RMS` (the exact same constant H1's exceedance pathway already uses) | `MAINTENANCE_THRESHOLD` |
| anything else | `2 × reference baseline mean` (a documented placeholder multiplier) | `CONFIGURED_PROGNOSTIC_THRESHOLD` |

No threshold is ever labeled `ENGINEERING_LIMIT` — this codebase has no
approved OEM/engineering limit data source, and H5 never invents one. The
`threshold_type` on every `HUMSPrognosticRecord` states exactly which kind
of threshold was used, so a reviewer can never mistake a demo placeholder
for a certified limit.

## RUL & uncertainty

See `docs/HUMS_RUL_ENGINE.md` for the exact prediction-interval formula.
Every non-null RUL carries `rul_lower`/`rul_upper`/`confidence`, and every
explanation ends with **"ESTIMATE — NOT A CERTIFIED LIFE LIMIT."** verbatim
(verified in
`tests/integration/test_hums_prognostics.py::test_prognostic_never_grounds_asset_or_declares_airworthiness`).

## Extrapolation and model drift

- **`LOW_CONFIDENCE_EXTRAPOLATION`**: flagged when the predicted threshold
  crossing lies further into the future than the actual observed usage
  span — confidence is forced to `LOW` regardless of fit quality.
- **`MODEL_STALE`**: flagged when the 3 most recent observations deviate
  from the existing fit by more than an effective-residual-std threshold
  (floored to avoid false positives on near-perfect synthetic fits — see
  the anchor-consistency bug writeup above for why this mattered in
  practice).

## ProactiveSignalRecord integration

`HUMS_RUL_WARNING` (extends the same taxonomy H1/H3/H4 already extended —
no second alert system) fires only for a **meaningful** transition: RUL
point estimate entering a configured warning window (`<=50` usage-units,
a documented placeholder), or `LOW_CONFIDENCE`/`STALE` status — never on
every recomputed RUL value. Dedup key includes the bucket, so repeated
re-evaluation while the signal is still open is a no-op (verified in
`tests/integration/test_hums_prognostics.py::test_rul_warning_signal_fires_once_for_meaningful_transition`).

## MRO / Readiness / Compliance — inputs, never overridden

Same non-negotiable as every prior HUMS milestone: H5 never writes to
readiness, compliance, or maintenance-approval state directly. It exposes
`rul_estimate`/`confidence`/`trajectory_state`/threshold information via
`HUMSPrognosticRecord` and `ProactiveSignalRecord`, both of which the
existing M7 intelligence layer already reads from. H5 never creates a work
order, never sets `GROUNDED`/`AIRWORTHY` on an asset (explicitly verified
in the safety-boundary test above), and never approves maintenance.

## AI Assistant

`get_asset_hums_prognostics` is instructed to phrase every answer as
*"Kota estimates..."* with range and confidence, explicitly forbidden from
stating a bare number as a guaranteed remaining life, and required to
report `INSUFFICIENT_DATA`/null RUL honestly rather than a fabricated
figure.

## Async boundary

Same precedent as H2–H4: no Celery/RQ/cron. Model fitting and RUL
computation run synchronously, triggered at the same read-time point H3's
health signals and H4's diagnostics already use
(`get_asset_health_intelligence`/`get_component_health_intelligence`),
bounded to `MAX_TRAJECTORY_POINTS` (60) feature rows per (sensor,
feature_type) — never an unbounded historical scan.

## Limitations

- Two model types only (`LINEAR`, `ROBUST_LINEAR`) — `PIECEWISE_LINEAR`
  and `EXPONENTIAL` are documented extension points, not implemented.
- The ~90% prediction interval uses a normal-approximation z-multiplier
  (1.645), not an exact Student-t critical value (no statistics dependency
  in this codebase for a t-table) — labeled "approximate" everywhere.
- Only `rms` has a real configured maintenance threshold; every other
  feature type falls back to a documented placeholder multiplier of the
  reference baseline mean, explicitly typed `CONFIGURED_PROGNOSTIC_THRESHOLD`.
- RUL warning window (50 usage-units) and model-staleness constants are
  demo/placeholder values, not derived from any reliability-engineering
  standard.
- No cross-validation/holdout evaluation of model fit — in-sample R² and
  residuals only.
- No RUL for non-vibration measurement types beyond the generic fallback
  threshold (no bespoke degradation direction/threshold tuning for
  temperature/pressure/etc. yet).
- Not fleet-wide PHM, not a Digital Twin, not autonomous maintenance —
  explicitly out of scope per the H5 spec (belongs to H6+).
