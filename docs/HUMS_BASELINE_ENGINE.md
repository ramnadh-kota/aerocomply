# HUMS Baseline Engine (H3)

H3 provides deterministic health intelligence from historical HUMS features.
It does not perform full fault diagnosis, prognostics, RUL prediction, or
autonomous safety decisions.

This document covers baseline calculation. See
`docs/HUMS_HEALTH_INTELLIGENCE.md` for deviation, trend, and health-state
logic built on top of it.

## Why not `AssetHistoricalBaseline`?

The H0/H3 audit confirmed `AssetHistoricalBaseline`
(`app/models/asset_baseline.py`) is a carry-in **flight-hours/cycles**
accounting record ("Current Asset State = Historical Baseline + SUM(Flights
after baseline)") — a completely different concept from a per-sensor-feature
statistical baseline (mean/std/percentiles of, say, vibration RMS). Reusing
it would have meant overloading one model with two unrelated meanings. H3
introduces `HUMSBaseline` instead — a new, narrowly-scoped model, not a
duplicate of anything H1/H2 already had.

## Data model

`HUMSBaseline` (`app/models/hums.py`): one row per (sensor, feature_type,
version). Append-only/versioned — a recompute never overwrites a row, it
inserts a new one with `version + 1` and flips the previous row's
`is_current` to `False`. This keeps a past health verdict's baseline
lineage reconstructable ("what baseline was this DEGRADED call made
against?").

No separate `HUMSFeatureDeviation`/`HUMSTrend` table exists. Deviation and
trend are computed on demand from a bounded `HUMSFeature` query
(`FEATURE_HISTORY_LIMIT = 50` rows) plus the current `HUMSBaseline` row —
cheap enough that persisting them separately would only be a second,
harder-to-keep-consistent copy of derived data. See
`docs/HUMS_HEALTH_INTELLIGENCE.md`'s performance section for the numbers.

## Baseline scope

`baseline_scope` is `ASSET` (today's only real path — one baseline per
sensor, which is 1:1 with an asset+installation location) or `COMPONENT`
(implicitly available since every `HUMSBaseline` row carries
`component_id` when the sensor has one). `FLEET` is a **documented
extension point only** — not implemented, because the domain model doesn't
yet have a clean "asset class" grouping (e.g. "all Model X engines across
the fleet") to key a fleet baseline off of. Implementing it without that
grouping would mean inventing one, which H3 deliberately avoids.

## Calculation method

`app/services/hums/baseline_engine.py::compute_baseline_stats` — a pure
function over a list of floats:

- `mean`, `median`, `std_dev` (population, via `statistics.pstdev`)
- `minimum`, `maximum`
- `percentile_05/25/50/75/95` (nearest-rank)
- `lower_bound` = `percentile_05`, `upper_bound` = `percentile_95` — a
  **robust percentile range**, not `mean ± N·std`. Chosen because H3's
  synthetic/early-fleet data has no guarantee of being normally
  distributed, and a percentile range degrades gracefully with skewed data
  where a std-dev range would not. `calculation_method` on every row states
  this explicitly (`"percentile_05_95_robust_range"`) so a caller never has
  to guess which convention was used.

## Baseline quality and confidence

| Sample count | Quality | Confidence |
|---|---|---|
| < 5 (`MIN_SAMPLES_FOR_BASELINE`) | *(no baseline created — returns `None`)* | — |
| 5–14 | `LIMITED` | `LOW` |
| 15–29 (`LIMITED_SAMPLES_THRESHOLD`) | `LIMITED` | `MEDIUM` |
| ≥ 30 (`GOOD_SAMPLES_THRESHOLD`) | `VALID` | `HIGH` |

These are small, explicitly documented constants — not a statistical power
calculation. `STALE` and `INVALID` are reserved quality states
(`STALE`: a baseline older than `BASELINE_STALE_AFTER` = 30 days, eligible
for recompute; `INVALID`: reserved for a future data-corruption case, not
currently produced) — see `baseline_service.py`.

A weak baseline is never presented as a trustworthy one: every downstream
deviation/health result carries the baseline's own `quality`/`confidence`
forward, and `docs/HUMS_HEALTH_INTELLIGENCE.md`'s health-state table shows
exactly how `INSUFFICIENT_DATA` propagates rather than getting silently
coerced into `HEALTHY`.

## The self-exclusion invariant (critical correctness property)

**A baseline must never include the observation it will next be compared
against.** This was caught during implementation: computing a baseline from
history that included the very reading being evaluated let an anomaly
"absorb" itself into its own normal range (a single extreme reading could
become its own 95th percentile, making it read as `NORMAL`).

The fix: baseline (re)computation happens **once per ingestion**, in
`app/services/hums/health_service.py::refresh_baselines_after_ingestion`,
called right after `feature_service.process_window` persists a batch's new
`HUMSFeature` rows — using feature history that explicitly excludes the IDs
just inserted (`HUMSFeature.id.notin_(newly_persisted_ids)`). Health
evaluation (`evaluate_feature_health`) then only **reads** the
already-computed current baseline (`baseline_service.get_current_baseline`,
no recompute) and compares the latest feature value against it. This also
gives the performance property H3 requires: baseline recomputation is
bounded to ingestion rate, never to the rate of health-intelligence API
reads (see `docs/HUMS_HEALTH_INTELLIGENCE.md` section on performance).

## Operating context

H3 does not implement RPM/flight-phase/altitude/load-segmented baselines —
that requires co-located context data (e.g. RPM alongside vibration) this
codebase's HUMS seed/demo data doesn't yet provide. Rather than fabricate a
context-aware baseline, every asset-scoped baseline's `context_notes` field
states the limitation explicitly (e.g. *"No RPM/flight-phase/operating-
context segmentation available — asset-wide baseline only."*), and
`baseline_scope`/`HEALTH_FEATURES_BY_MEASUREMENT_TYPE` in
`health_service.py` are the extension points for adding segmented baselines
once that data exists.

## API

```
GET /hums/assets/{asset_id}/baseline       -- current baselines for every sensor on the asset
```

Baseline rows are also embedded implicitly in `.../deviations`, `.../trends`,
and `.../health-intelligence` responses (each `HUMSDeviationResponse`
carries the baseline values it was computed against). There is no public
"recompute baseline" endpoint — recomputation is an ingestion side effect,
consistent with H2's precedent of not exposing internal feature-processing
as a public write endpoint.

## Limitations

- No fleet-class baselines (documented extension point only).
- No operating-context segmentation (RPM/phase/altitude/load) — asset-wide
  baseline only, with an explicit `context_notes` disclaimer.
- `BASELINE_STALE_AFTER` (30 days) and the sample-count thresholds are
  placeholder demo constants, not derived from any certification or
  reliability-engineering standard.
- Baseline recomputation creates a new version on every ingestion batch
  that has enough prior history — for a very high-frequency real ingestion
  rate this would need throttling (e.g. "recompute at most once per hour"),
  which is not implemented; acceptable for the batch-oriented ingestion
  this codebase actually has today.
