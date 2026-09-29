# HUMS Signal Processing (H2)

This document covers the H2 milestone: turning raw HUMS sensor readings into
validated, traceable engineering features. It extends the H1 foundation
(`docs/HUMS_ARCHITECTURE.md`) — read that first for the overall pathway and
what remains unimplemented (diagnostics, prognostics/RUL, digital twin).

## Pipeline

```
Sensor Reading (HUMSSensorReading)
      |
      v
Data Quality Validation  (app/services/hums/signal_processing.py)
      |
      v
Preprocessing (dedupe, sort, sampling-rate estimation)
      |
      v
SignalWindow
      |
      v
Feature Extraction  (app/services/hums/feature_extractors.py)
      |
      v
HUMSFeature rows (persisted, app/services/hums/feature_service.py)
      |
      v
Existing H1 health/exceedance evaluator (app/services/hums_service.py)
```

Module boundaries:

- **`app/services/hums/signal_processing.py`** — pure functions/dataclasses.
  No DB access. `build_signal_window()` takes raw `(id, timestamp, value,
  unit, declared_quality)` tuples and returns a `SignalWindow`: sorted,
  deduplicated, quality-classified, with an estimated sampling rate.
- **`app/services/hums/feature_extractors.py`** — pure functions computing
  `FeatureResult` objects from a list of floats (+ timestamps for trend
  features). No DB access, no knowledge of SignalWindow's internals beyond
  what's passed in.
- **`app/services/hums/feature_service.py`** — the only module in this
  package that touches the DB. `process_window()` builds a window, runs the
  feature set appropriate to the sensor's `measurement_type`, and persists
  each result as a `HUMSFeature` row.
- **`app/services/hums_service.py`** (H1) — unchanged responsibility: turns
  a feature into an Exceedance/Finding/Evidence/ProactiveSignalRecord. It
  now calls `feature_service.process_window()` on every ingested batch and
  reads the persisted feature values, instead of computing RMS inline.

## Data-quality classification

Every reading is (re-)classified during windowing, regardless of what the
caller declared:

| State | Meaning |
|---|---|
| `VALID` | Passed all checks, used in feature calculation |
| `SUSPECT` | Caller-declared; excluded from calculation |
| `MISSING` | Caller-declared |
| `OUT_OF_RANGE` | Outside a documented sanity bound (placeholder ±1,000,000 — see `signal_processing.py`'s `_SANITY_MIN`/`_SANITY_MAX` comment: a real deployment sources this per sensor type) |
| `STALE` | Older than 6 hours relative to the newest reading in the batch |
| `DUPLICATE` | Same `(timestamp, value)` pair seen twice in the batch |
| `INVALID` | NaN, or declared invalid by the caller |

Only `VALID` readings feed feature calculation. A window's `overall_quality`
is `INSUFFICIENT_DATA` (no valid readings), `DEGRADED` (some readings
excluded), or `GOOD` (all readings valid) — this downgrades every feature's
own quality unless that feature already reports `INSUFFICIENT_DATA`/
`INVALID` for its own reason (e.g. zero variance for kurtosis).

## Preprocessing

- Sort ascending by `recorded_at`.
- Deduplicate identical `(timestamp, value)` pairs.
- Estimate sampling rate as `1 / median(consecutive deltas)` — robust to a
  few irregular gaps, `None` if fewer than 2 valid readings remain.

No detrending/filtering is implemented yet (extension point, not required
for H2's feature set).

## FFT / frequency-domain

No numpy/scipy dependency — this codebase has none, and a DFT over a few
dozen-to-few-hundred samples per window doesn't justify adding one. The
implementation in `feature_extractors._dft_magnitudes` is a direct,
textbook O(n²) discrete Fourier transform:

```
X[k] = (1/n) * sum_t( x[t] * exp(-2πi * k * t / n) )   for k in 0..n//2
```

Validated against a synthetic sine wave in
`tests/unit/test_hums_feature_engine.py::test_fft_detects_known_sine_wave_frequency`:
a 50 Hz signal sampled at 1000 Hz over 200 samples resolves to exactly 50 Hz
(the frequency happens to land on a bin exactly; general tolerance is one
frequency-resolution bin, `sampling_rate / n`).

Dominant frequency excludes bin 0 (DC) — otherwise a nonzero-mean signal
would trivially "win" on mean alone rather than actual oscillation.

## Extension points (documented, not built)

- Bearing/gear-mesh frequencies, harmonics, sidebands, envelope analysis,
  order tracking (RPM-linked vibration normalization) — H2 spec explicitly
  scopes these out; `_TREND_MEASUREMENT_TYPES`/`_VIBRATION_MEASUREMENT_TYPES`
  in `feature_service.py` is the extension point for a new
  `measurement_type`.
- Configurable window sizes: `hums_service.FEATURE_WINDOW_READING_COUNT`
  (currently a fixed 20-reading rolling window) — not yet exposed as a
  per-sensor configuration value.
- Windowing functions (Hann, etc.) for the FFT — not applied; the direct
  DFT above has no windowing, which is acceptable for the deterministic
  synthetic-signal test but would show spectral leakage on real noisy data.

## Asynchronous processing

This codebase has no background-job infrastructure (no Celery/RQ/cron)
anywhere — see `app/services/evidence_reconciliation_service.py`'s module
docstring for the same observation made earlier in this codebase.
`feature_service.process_window()` is called synchronously from the ingest
request path, but is a clean, self-contained function boundary (readings
in, features out) that could move behind a queue consumer later without
changing its signature.
