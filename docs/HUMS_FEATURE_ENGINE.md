# HUMS Feature Engine (H2)

Catalog of every feature the H2 feature engine computes, keyed by the
`sensor.measurement_type` it applies to. See `docs/HUMS_SIGNAL_PROCESSING.md`
for the pipeline these feed into.

## Feature catalog

### All measurement types (time-domain statistics)

Computed by `feature_extractors.time_domain_statistics`. Requires ≥2 valid
samples, else `INSUFFICIENT_DATA`.

| feature_type | Formula | Unit |
|---|---|---|
| `min` | `min(x)` | sensor unit |
| `max` | `max(x)` | sensor unit |
| `mean` | arithmetic mean | sensor unit |
| `median` | median | sensor unit |
| `std` | population standard deviation | sensor unit |
| `variance` | population variance | sensor unit² |
| `range` | `max(x) - min(x)` | sensor unit |
| `p95` | nearest-rank 95th percentile | sensor unit |

### `vibration` (additional shape/frequency features)

Computed by `feature_extractors.vibration_time_domain_features` and
`frequency_domain_features`.

| feature_type | Formula | Requires | Unit |
|---|---|---|---|
| `rms` | `sqrt(mean(x²))` | ≥2 samples | sensor unit |
| `peak` | `max(abs(x))` | ≥2 samples | sensor unit |
| `peak_to_peak` | `max(x) - min(x)` | ≥2 samples | sensor unit |
| `crest_factor` | `peak / rms` | rms ≠ 0 | ratio |
| `kurtosis` | Fisher excess kurtosis: `m4/m2² - 3` | ≥5 samples, std ≠ 0 | unitless |
| `skewness` | `m3/m2^1.5` | ≥5 samples, std ≠ 0 | unitless |
| `dominant_frequency` | largest-magnitude DFT bin excluding DC | ≥8 samples, known sampling rate | Hz |
| `spectral_energy` | `sum(magnitude²)` over the spectrum | ≥8 samples, known sampling rate | unit² |
| `band_energy` | `spectral_energy` restricted to a frequency band (default: all frequencies) | ≥8 samples, known sampling rate | unit² |

A **constant or near-constant signal** correctly reports `crest_factor`,
`kurtosis`, and `skewness` as `INVALID` (zero variance / divide-by-zero)
rather than a misleading value — verified in
`tests/unit/test_hums_feature_engine.py`.

### `temperature`, `pressure`, `rpm`, `torque`, `voltage`, `current` (trend features)

Computed by `feature_extractors.trend_features`.

| feature_type | Formula | Unit |
|---|---|---|
| `trend` | least-squares slope of value vs. time | unit/s |
| `rate_of_change` | `(last - first) / duration` | unit/s |

`pressure` additionally gets:

| feature_type | Formula | Unit |
|---|---|---|
| `deviation` | `mean(x) - baseline` (baseline = first reading in the window — a placeholder; a real deployment would use a nominal operating-envelope value per asset/component type) | unit |

RPM/torque/voltage/current do not yet have bespoke min/max/mean/peak
features beyond the shared time-domain statistics above — extension point
in `feature_service._compute_features`.

Battery-specific features (voltage/current/SOC/cycle count) are **not**
implemented in H2: the existing `Battery` model (H1 audit) already tracks
`cycle_count`/`health_percent` outside the HUMS reading pipeline, and
wiring that into a HUMSSensor-based feature stream is left as a future
extension rather than duplicated here.

## Feature persistence and lineage

Every computed feature (including `INSUFFICIENT_DATA`/`INVALID` ones) is
persisted as a `HUMSFeature` row (`app/models/hums.py`):

```
Feature
  -> source_reading_ids (JSONB list of HUMSSensorReading ids)
  -> sensor_id -> HUMSSensor -> asset_id / component_id
  -> window_start / window_end
  -> quality, calculation_method, processor_version
```

A reviewer can trace any feature back to its exact source readings via
`source_reading_ids`, and every feature's `feature_metadata` JSON carries
calculation-specific context (e.g. `frequency_resolution_hz`,
`quality_summary` of the underlying window).

## Feature quality

| Quality | Meaning |
|---|---|
| `GOOD` | Computed from a fully valid window, formula well-defined |
| `DEGRADED` | Computed, but the window had some excluded (suspect/stale/out-of-range/duplicate) readings |
| `INSUFFICIENT_DATA` | Too few valid samples for this specific feature (thresholds vary: 2 for basic stats/RMS, 5 for kurtosis/skewness, 8 for FFT) |
| `INVALID` | Well-defined inputs but the formula is undefined (e.g. zero variance for kurtosis, zero RMS for crest factor) |

## API

```
GET /hums/assets/{asset_id}/features[?feature_type=]
GET /hums/assets/{asset_id}/features/{feature_type}
GET /hums/components/{component_id}/features[?feature_type=]
GET /hums/sensors/{sensor_id}/features[?feature_type=]
GET /hums/sensors/{sensor_id}/spectrum
```

There is no public `POST /hums/features/process` — feature processing is
an internal side effect of `POST /hums/sensors/{id}/readings` (see
`hums_service.detect_and_record_exceedances`, which now persists the full
feature set on every ingested batch, not just the RMS value it checks
against the H1 exceedance threshold).

`GET .../spectrum` computes the DFT magnitude spectrum **on demand** from
the sensor's latest reading window — it is not persisted, since only the
scalar features (`dominant_frequency`, `spectral_energy`, `band_energy`)
are needed for history/trending; the full magnitude array is only useful
for the frontend's live frequency view.

## H1 integration — what changed, what didn't

- H1's `_compute_rms_feature` no longer has its own RMS formula — it calls
  `feature_extractors.vibration_time_domain_features(...)["rms"]`, the same
  function the persisted feature engine uses. One RMS implementation,
  referenced from both the live health-check path and the persisted
  feature-history path.
- The existing RMS exceedance threshold logic (`VIBRATION_WARNING_RMS` /
  `VIBRATION_CRITICAL_RMS`) is unchanged — same thresholds, same severity
  mapping, same Finding/Evidence/ProactiveSignalRecord chain. All 5 original
  H1 tests pass unmodified.
- New: the Finding description and Evidence/Signal `contributing_factors`
  now also report `crest_factor`, `kurtosis`, and `dominant_frequency` when
  available, giving a richer (but still RMS-triggered) exceedance
  explanation — no second alerting system was introduced.

## Limitations (explicitly not done in H2)

- No bearing/gear-mesh/harmonic/sideband/order-tracking analysis.
- No windowing function (Hann, etc.) applied before the FFT — fine for the
  deterministic synthetic-signal test, would show spectral leakage on real
  noisy data.
- Thresholds (`VIBRATION_WARNING_RMS`/`CRITICAL_RMS`) remain a single
  fleet-wide placeholder, not per-asset-model/OEM-sourced limits — same
  caveat H1 already documented, unchanged in H2.
- No RPM-linked order tracking / shaft-speed normalization, despite the H2
  spec inviting a "foundation" for it — no RPM+vibration co-located demo
  data exists yet to build and test it against, so it was left as a
  documented gap rather than an unverified stub.
- Diagnostics, prognostics/RUL, and the digital twin remain entirely out of
  scope (H4–H6 per the milestone roadmap).
