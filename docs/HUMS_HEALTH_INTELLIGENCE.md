# HUMS Health Intelligence (H3)

**H3 provides deterministic health intelligence from historical HUMS
features. It does not perform full fault diagnosis, fault isolation,
prognostics, RUL prediction, failure-probability modeling, digital twin
state, fleet-wide intelligence, or autonomous safety decisions.** Those
belong to H4 (Diagnostics & Fault Isolation) and H5 (PHM/Prognostics/RUL)
per the roadmap in `docs/HUMS_ARCHITECTURE.md`.

See `docs/HUMS_BASELINE_ENGINE.md` for how baselines are computed — this
document covers what's built on top: deviation, trend, change detection,
and the health-state rule table.

## Architecture

```
H2 Sensor Readings -> Signal Windows -> Extracted Features (HUMSFeature)
                                              |
                                              v
                                    H3 Baseline (HUMSBaseline)
                                              |
                              +---------------+---------------+
                              v                               v
                      Deviation Engine                 Trend Engine
              (app/services/hums/health_engine.py)  (same module)
                              |                               |
                              +---------------+---------------+
                                              v
                                   Change Detection (consecutive
                                   deviation count -- same module)
                                              v
                                    Feature Health (determine_feature_health)
                                              v
                                    Component Health (aggregate_health)
                                              v
                                      Asset Health (aggregate_health)
                                              v
                              ProactiveSignalRecord (reused, not duplicated)
```

Module boundaries (mirrors H2's convention):

- `app/services/hums/baseline_engine.py` — pure baseline statistics (no DB).
- `app/services/hums/health_engine.py` — pure deviation/trend/change-
  detection/health-state functions (no DB). This is where the deterministic
  rule table lives.
- `app/services/hums/baseline_service.py` — the only baseline module
  touching the DB: persists/retrieves `HUMSBaseline` rows.
- `app/services/hums/health_service.py` — orchestrates baseline_service +
  health_engine into feature/component/asset health results, and
  integrates meaningful deterioration into the existing
  `ProactiveSignalRecord` (no second alert system).
- `app/services/hums_service.py` — the single entry point the API layer
  calls (`get_asset_baselines`, `get_asset_deviations`, `get_asset_trends`,
  `get_asset_health_intelligence`, `get_component_health_intelligence`),
  same pattern H1/H2 already established.

## Deviation

`health_engine.compute_deviation(current_value, baseline)`:

- `absolute_deviation` = `current - baseline.mean`
- `percentage_deviation` = `absolute_deviation / baseline.mean`, or `None`
  if `baseline.mean == 0` (never divides by zero)
- `standardized_deviation` = `absolute_deviation / baseline.std_dev`, or
  `None` if `baseline.std_dev == 0`

State:

| Condition | State |
|---|---|
| No baseline | `INSUFFICIENT_DATA` |
| Within `[lower_bound, upper_bound]` | `NORMAL` |
| Outside bounds, `std_dev == 0` | `SEVERE` (can't express "how many std devs", so any deviation from a zero-variance baseline is treated as severe rather than silently `NORMAL`) |
| `\|z\| < 2` | `ELEVATED` |
| `2 ≤ \|z\| < 3` | `DEVIATED` |
| `\|z\| ≥ 3` | `SEVERE` |

## Trend

`health_engine.compute_trend(values, timestamps_seconds)` — reuses the same
least-squares slope formula as H2's `feature_extractors.trend_features`
(same math, different classification layer on top):

- **`INSUFFICIENT_DATA`**: fewer than `MIN_SAMPLES_FOR_TREND` (5) points.
- **`ACCELERATING`**: the second half of the window's slope magnitude
  exceeds the first half's by ≥1.5x, same direction (`ACCELERATION_RATIO_THRESHOLD`).
- **`VOLATILE`**: coefficient of variation (`std/|mean|`) > 0.5 AND net
  movement over the window is smaller than one standard deviation — high
  noise, no real net trend.
- **`STABLE`**: net movement over the window is < 0.5 standard deviations.
- **`INCREASING`/`DECREASING`**: slope sign, once the above are ruled out.

Confidence scales with sample count: `HIGH` (≥15), `MEDIUM` (≥8), `LOW`
(≥5).

## Change detection (consecutive deviation)

`health_engine.consecutive_deviation_count(values, baseline)` counts
**trailing** (most-recent-first) values outside the baseline bounds —
distinguishes "3 consecutive abnormal observations" from "1 isolated
abnormal observation" per the H3 spec. No CUSUM/EWMA/ML change-point
detection is implemented — documented extension points only (see
Limitations).

## Health-state rule table

`health_engine.determine_feature_health` — deterministic, in this order:

1. `deviation.state == INSUFFICIENT_DATA` → **INSUFFICIENT_DATA**
2. `SEVERE` + (`ACCELERATING` trend OR ≥5 consecutive) → **CRITICAL**
3. `SEVERE` (otherwise) → **WARNING**
4. `DEVIATED` + (worsening trend OR ≥5 consecutive) → **WARNING**
5. `DEVIATED` (otherwise) → **DEGRADED**
6. `ELEVATED` + ≥3 consecutive → **DEGRADED**
7. `ELEVATED` (otherwise, <3 consecutive) → **WATCH**
8. `NORMAL` → **HEALTHY**

Every result carries an `explanation: list[str]` — plain-language sentences
naming the feature, the deviation magnitude, and the trend/persistence
driving the verdict. **No health state is ever returned without an
explanation** (verified in `tests/unit/test_hums_baseline_and_health_engine.py::test_health_state_critical_for_severe_and_accelerating`).

## Aggregation (component / asset)

`health_engine.aggregate_health(feature_results)` rolls a list of
per-feature results up to one state: **the worst-ranked non-
`INSUFFICIENT_DATA` state wins** (rank: `CRITICAL` > `WARNING` >
`DEGRADED` > `WATCH` > `HEALTHY`). If every contributing feature is
`INSUFFICIENT_DATA`, the aggregate is `INSUFFICIENT_DATA` too — never
silently promoted to `HEALTHY`. `primary_contributors` lists exactly the
feature(s) that produced the worst-ranked state, so a caller can always
answer "why is this DEGRADED" by name, never a bare number.

Component health = `aggregate_health` over every sensor on that component.
Asset health = `aggregate_health` over every feature result across every
sensor on the asset (sensors grouped by `component_id`; sensors with no
`component_id` form an implicit "unassigned" bucket).

## ProactiveSignalRecord integration

`health_service.sync_health_signal` creates a `ProactiveSignalRecord`
(`signal_type = "HUMS_HEALTH_DEGRADATION"`, extending the same taxonomy H1
extended with `HUMS_VIBRATION_EXCEEDANCE` — no second alert system) **only**
for `DEGRADED`/`WARNING`/`CRITICAL` states. `HEALTHY`/`WATCH` never create a
signal — normal variation and brief mild deviations must never spam the
signal feed (verified in
`tests/integration/test_hums_baseline_and_health.py::test_no_signal_spam_for_isolated_normal_variation`).
Dedup key is `(asset_id, component_id, health_state)` — re-evaluating while
already `OPEN`/`ACKNOWLEDGED`/`IN_REVIEW` for that exact state is a no-op.

## Evidence lineage

H3 does not create Finding/Evidence rows the way H1's exceedance pathway
does — a health-intelligence verdict is an **observation/signal**, not
automatically a **Finding** (defect), preserving the spec's
`Observation ≠ Anomaly ≠ Finding ≠ Defect` distinction. The full lineage
(`Sensor Reading → Feature → Baseline → Deviation → Trend → Health
Indicator → Signal`) is reconstructable from stored data:
`HUMSFeature.source_reading_ids` → `HUMSBaseline.source_window_start/end` +
`version` → `HUMSDeviationResponse`/`HUMSTrendResponse` (computed fresh from
those, not separately persisted — see `docs/HUMS_BASELINE_ENGINE.md`) →
`ProactiveSignalRecord.contributing_factors_json`.

## Readiness integration

H3 does **not** write to the readiness engine directly. It feeds
`ProactiveSignalRecord`, which M7's existing intelligence layer already
reads from — the same "HUMS is an input, readiness stays authoritative"
principle H1's exceedance signals already established. No readiness code
was modified for H3.

## API

```
GET /hums/assets/{asset_id}/baseline
GET /hums/assets/{asset_id}/trends
GET /hums/assets/{asset_id}/deviations
GET /hums/assets/{asset_id}/health-intelligence
GET /hums/components/{component_id}/health
```

`GET /hums/assets/{asset_id}/health-intelligence` is **deliberately
separate** from H1's `GET /hums/assets/{asset_id}/health` — the latter
stays frozen on its original simple RMS-threshold logic (`HEALTHY` /
`DEGRADED` / `CRITICAL` / `INSUFFICIENT_DATA`) so H1/H2 tests and any
existing caller's behavior are completely unaffected. H3's endpoint uses a
different, wider vocabulary (adds `WATCH`/`WARNING`) driven by baseline
deviation rather than a fixed threshold — merging them into one endpoint
would have silently changed H1's contract.

## Performance

Per the H3 spec's explicit requirement to avoid recomputing the entire
historical dataset on every request:

- Baseline (re)computation happens **once per ingestion batch**
  (`health_service.refresh_baselines_after_ingestion`, called from
  `hums_service.detect_and_record_exceedances`), never on a
  health-intelligence GET request.
- Every read (`evaluate_feature_health`, and everything built on it) does
  at most: one bounded `HUMSFeature` query (`FEATURE_HISTORY_LIMIT = 50`
  rows, indexed on `(organization_id, sensor_id, feature_type, window_end)`)
  and one indexed `HUMSBaseline` lookup (`is_current = true`) per (sensor,
  feature_type) — never an unbounded scan.

## No background-job assumption

Same precedent as H2: this codebase has no Celery/RQ/cron infrastructure.
`refresh_baselines_after_ingestion` runs synchronously in the ingestion
request path. It is a clean, self-contained function boundary (sensor +
newly-persisted features in, nothing returned but a DB write) that could
move behind a queue consumer later without changing its signature or the
read path's behavior.

## Limitations (explicitly not done in H3)

- No fleet-class baselines, no RPM/flight-phase/operating-context
  segmentation (see `docs/HUMS_BASELINE_ENGINE.md`).
- No CUSUM/EWMA/ML change-point detection — consecutive-deviation counting
  only.
- No fault isolation, fault classification, FMEA, RUL, failure probability,
  survival analysis, Weibull modeling, digital twin, or ML anomaly
  detection — all explicitly out of scope per the H3 spec's "do not
  implement yet" list.
- Baseline versions are created on every ingestion batch with sufficient
  prior history (no throttling) — acceptable at this codebase's batch
  ingestion rate, would need revisiting for high-frequency real telemetry.
- The demo seed data (`scripts/seed_hums_dataset.py`) is not
  reading-level idempotent, so re-running it can shift a scenario's exact
  resulting bucket across repeated runs — the health-engine correctness
  itself is verified against a fresh, isolated database in the automated
  test suite, not by this script's printed output.
