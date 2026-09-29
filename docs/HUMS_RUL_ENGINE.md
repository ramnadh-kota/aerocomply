# HUMS RUL Engine — Mathematical Reference (H5)

See `docs/HUMS_PROGNOSTICS.md` for architecture, reference-baseline
strategy, and safety boundaries. This document is the mathematical detail
behind `app/services/hums/degradation_engine.py` — pure functions, fully
unit-tested including quantitative accuracy checks against known synthetic
trajectories (`tests/unit/test_hums_degradation_engine.py`).

**Every value this engine produces is an ESTIMATE, NOT A CERTIFIED LIFE
LIMIT.**

## Linear fit (ordinary least squares)

Standard closed-form OLS:

```
slope     = Σ(x - x̄)(y - ȳ) / Σ(x - x̄)²
intercept = ȳ - slope · x̄
```

Degenerate cases handled explicitly: fewer than 2 points, or zero variance
in `x` (all usage values identical) → returns `None`, never a
divide-by-zero or a fabricated fit.

`fit_error` = population RMSE of residuals. `r_squared` = `1 - SS_res/SS_tot`,
clamped to `[0, ∞) → max(0, ...)` (never negative, even though the raw
formula can go slightly negative for a pathologically bad fit).

## Robust linear fit (Theil-Sen estimator)

```
slope     = median of all pairwise slopes (y_j - y_i)/(x_j - x_i), i < j
intercept = median of (y_i - slope · x_i) over all i
```

Breakdown point ~29% (robust to roughly 1 in 3 points being an outlier) —
verified in
`tests/unit/test_hums_degradation_engine.py::test_fit_robust_linear_resists_outlier`,
where a single wild outlier pulls the OLS slope far from the true value
while the Theil-Sen slope stays close.

## Model selection

```
if len(samples) < MIN_SAMPLES_FOR_DEGRADATION (6):
    INSUFFICIENT_DATA
else:
    fit OLS
    if max(|residual|) / residual_std > 3.0:   # a clear single-point outlier
        fit ROBUST_LINEAR instead
    else:
        keep LINEAR
```

Prefers the simplest model that explains the data (spec section 13) —
never jumps to the robust estimator unless the plain fit shows it's
actually needed.

## Trajectory state classification

Given the fitted slope and the raw value series:

1. **STABLE**: net movement over the observed span is smaller than
   `0.5 × residual_std × sqrt(n)` — negligible relative to noise.
2. **ACCELERATING**: the second half of the series' own slope exceeds the
   first half's by ≥1.5×, same (degrading) direction.
3. **NON_MONOTONIC**: first-half and second-half slopes are both
   meaningfully nonzero but have opposite signs.
4. **DEGRADING** / (falls back to **STABLE**): slope sign in the degrading
   direction.
5. **INSUFFICIENT_DATA**: fewer than `MIN_SAMPLES_FOR_DEGRADATION` points
   or no fit.

`degrading_direction` is a per-feature-type constant
(`degradation_service.DEGRADING_UPWARD_FEATURES`): vibration features
(RMS, kurtosis, crest factor, peak) degrade **upward**; anything not in
that set is treated as degrading **downward** — an extension point for
future feature types with a different degradation sign.

## Threshold crossing

```
signed_slope = slope × degrading_direction
if signed_slope <= 0:
    no crossing predicted (trajectory not moving toward the threshold)
else:
    crossing_usage = current_usage + (threshold - predicted(current_usage)) / signed_slope
```

Never fabricates a crossing point the slope doesn't actually predict — if
the trajectory is flat or moving away from the threshold, `RUL = None`
(verified quantitatively in
`test_rul_none_when_trajectory_moving_away_from_threshold`).

## RUL point estimate

```
rul_point = max(0, crossing_usage - current_usage)
```

### Quantitative validation (H5 spec section 42)

Known synthetic trajectory: `start = 1.0`, `slope = 0.01/usage-unit`,
`threshold = 2.0` → expected crossing at usage `100`.

| Test | Result |
|---|---|
| Noise-free | Crossing = exactly `100.0`, RUL error `< 1%` |
| Moderate noise (±0.03 uniform) | RUL error `< 15%` (documented tolerance) |

Both verified in `tests/unit/test_hums_degradation_engine.py` and
end-to-end through the real API/DB path in
`tests/integration/test_hums_prognostics.py::test_linear_degradation_matches_known_threshold_crossing_within_tolerance`
(error `< 5%` through the full ingestion → feature → baseline → model →
RUL pipeline).

## Uncertainty (prediction interval)

Standard linear-regression prediction-interval formula, including the
leverage term for how far the prediction point is from the fitted data's
center of mass:

```
leverage       = 1/n + (x_pred - x̄)² / Σ(x - x̄)²
prediction_std = residual_std × sqrt(1 + leverage)
margin_value   = z × prediction_std          (z = 1.645, ~90% one-tail normal approximation)
margin_usage   = margin_value / |signed_slope|

rul_lower = max(0, rul_point - margin_usage)
rul_upper = rul_point + margin_usage
```

**Honesty about the statistical claim**: `z = 1.645` is the normal
(Gaussian) approximation's one-tail 95%/two-tail 90% critical value, not
an exact Student-t critical value for small samples (this codebase has no
statistics library dependency for a t-table). Every surfaced range is
therefore labeled an **"approximate"** prediction interval, never claimed
as an exact 90% confidence interval in the strict statistical sense — per
the H5 spec's explicit warning: "do not label an interval '90%' unless the
implementation actually supports that statistical interpretation."

Verified: `test_rul_wider_uncertainty_with_higher_noise` confirms higher
input noise produces a **wider** range with the same underlying slope —
the qualitative behavior a real prediction interval must have, even with
the normal-approximation caveat.

## Confidence

```
if is_low_confidence_extrapolation:
    LOW
elif r_squared >= 0.8 and observed_usage_span >= 10.0:
    HIGH
elif r_squared >= 0.5:
    MEDIUM
else:
    LOW
```

`MIN_USAGE_SPAN_FOR_HIGH_CONFIDENCE = 10.0` is a documented placeholder,
not derived from any statistical power calculation.

## Extrapolation distance

```
extrapolation_distance = max(0, crossing_usage - (current_usage + observed_span/2))
is_low_confidence_extrapolation = extrapolation_distance > observed_usage_span
```

Flags `LOW_CONFIDENCE_EXTRAPOLATION` explicitly in the explanation text
whenever the model is asked to predict further into the future than it has
actual evidence for (H5-I scenario) — verified in
`test_low_confidence_extrapolation_flagged_far_beyond_observed_span` and
`test_extrapolation_not_flagged_within_observed_span` (the negative case).

## Model drift ("MODEL_STALE")

```
effective_std = max(residual_std, 1e-6 × max(1, |predicted values|))
drift_detected = any(|actual - predicted| > 3 × effective_std for the last 3 observations)
```

The `effective_std` floor was added after a real bug surfaced during H5
implementation: a numerically perfect synthetic linear trajectory has
`residual_std ≈ 0`, which made the un-floored `3 × residual_std` threshold
hypersensitive to ordinary floating-point noise, producing false
`MODEL_STALE` flags even when the model was fitting the data exactly. See
`docs/HUMS_PROGNOSTICS.md`'s "anchor-consistency bug" writeup for the
related root cause (a second bug in how the usage axis was computed for
the drift-check window, fixed by `degradation_service.get_usage_anchor`).

## Limitations

- Normal approximation, not exact Student-t — see "Honesty about the
  statistical claim" above.
- No cross-validation/holdout — R²/RMSE are in-sample only.
- Trajectory-state and drift-detection thresholds (1.5× acceleration
  ratio, 3× residual-std for drift, etc.) are documented, reasonable
  constants — not derived from a formal statistical procedure.
- Linear and robust-linear only; no piecewise or exponential degradation
  models (documented extension points in `docs/HUMS_PROGNOSTICS.md`).
