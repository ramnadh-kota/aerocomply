> **Implementation status (2026-09-30).** The sections below are a design narrative; the classification here is
> authoritative. Where this text disagrees with the code, the code and this block win.
>
> | Capability | Status | Where / how it is verified |
> |---|---|---|
> | Sensors and readings (tenant-checked asset/component), quality flags, NaN/Inf rejection | IMPLEMENTED | `hums_service.create_sensor`, `test_hums_thresholds`, `test_airframes` |
> | Feature extraction (time-domain, DFT frequency-domain, trend), signal windows | IMPLEMENTED | `services/hums/feature_extractors.py`, `signal_processing.py`, `test_hums_feature_engine` |
> | Baselines (versioned, from prior history), deviation, drift/trend, consecutive-deviation health | IMPLEMENTED | `baseline_service`, `health_engine`, `test_hums_baseline_and_health` |
> | Exceedance → finding → evidence → deduplicated M7 signal (one per exceedance) | IMPLEMENTED | `detect_and_record_exceedances`, `exceedance_signal_key`; per-sensor advisory lock and SAVEPOINT insert make it race-safe (`test_concurrency`) |
> | **Per-sensor warning/critical limits** (operator/OEM values, audited with previous values); platform defaults 5.0 / 8.0 mm/s RMS are generic starting values, **not** OEM limits | IMPLEMENTED | `PUT /hums/sensors/{id}/thresholds`, migration 0070, `test_hums_thresholds` |
> | Diagnostic candidates (rule/signature based, confirm/reject lifecycle) | IMPLEMENTED (deterministic) | `diagnostic_engine`, `fault_signatures`, `test_hums_diagnostics` |
> | Degradation model + RUL with confidence and extrapolation distance; insufficient data reported as such | IMPLEMENTED (deterministic; thresholds are configured limits or a typed fallback, never presented as engineering limits) | `degradation_engine`, `prognostic_service`, `test_hums_prognostics` |
> | Starter sensor sets for helicopters and eVTOL (definitions only, no limits or health claims) | IMPLEMENTED | `hums_templates.py` |
> | Batch evaluation stride (every 10 readings + batch end) | IMPLEMENTED | `telemetry_service.evaluate_pending_sensors`, mutation-checked test |
> | Rotorcraft-specific analytics (track & balance, gearbox condition indicators, torque spectra) and eVTOL-specific models (propulsor efficiency, inverter thermal margin, insulation) | NOT IMPLEMENTED — needs OEM data and validated algorithms (EXTERNAL_ONLY) | — |
> | Quality of diagnostics/prognostics on real fleet data | EXTERNAL VALIDATION REQUIRED | all tests use synthetic series |
>
> Every output names its source readings/features, method, window and (where relevant) confidence; nothing is inferred
> from a single reading. Related: `DATA_ACQUISITION_ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `FINAL_RELEASE_READINESS.md`.

# KOTA AEROSPACE — HUMS (HEALTH AND USAGE MONITORING SYSTEM) ARCHITECTURE

## 1. Overview & Objectives
The **Health and Usage Monitoring System (HUMS)** provides continuous, physics-informed condition assessment, fault detection, and Remaining Useful Life (RUL) prognostics for critical rotating machinery, propulsion systems, structural components, and battery energy storage across fixed-wing, rotary-wing (helicopter), drone, and eVTOL platforms.

All HUMS findings are **strictly grounded in empirical sensor data and physical telemetry**. Synthetic or hallucinated health states are forbidden by design.

---

## 2. HUMS Pipeline Architecture

```text
  [ Telemetry / Sensor Stream ] (1Hz – 500Hz)
  (Vibration, Temperatures, Voltages, Motor RPM, Pressures)
               │
               ▼
   [ 1. Feature Extraction Engine ]
     ├── Time Domain: RMS, Peak-to-Peak, Crest Factor, Kurtosis, Skewness
     ├── Frequency Domain: Spectral Energy, Harmonics (1X, 2X, 3X RPM), Sidebands
     └── Domain Metrics: C-Rate, Internal Resistance (IR), Thermal Gradient
               │
               ▼
   [ 2. Baseline & Normalization Engine ]
     ├── Baseline Models: Flight Phase Segmented (Hover, Cruise, Climb)
     ├── Environmental Normalization: OAT, Density Altitude, Wind Compensations
     └── Statistical Baselines: Rolling Mean $\mu_0$, Standard Deviation $\sigma_0$
               │
               ▼
   [ 3. Anomaly & Exceedance Detection ]
     ├── Threshold Exceedance: Amber (Advisory) / Red (Critical) Limits
     ├── Statistical Drift: Mahalanobis Distance, Z-Score ($|z| > 3.0$)
     └── Pattern Classifier: Bearing Fault Frequencies (BPFO, BPFI, BSF, FTF)
               │
               ▼
   [ 4. Prognostics & RUL Estimation ]
     ├── Degradation Trajectory Modeling (Exponential / Paris-Erdogan Law)
     ├── Battery State of Health (SoH) & Capacity Fade Projection
     └── Remaining Useful Life (RUL in Flight Hours / Cycles) with Confidence Bounds
               │
               ▼
   [ 5. Evidence & Signal Dispatcher ]
     ├── Generates HUMSEvidencePackage (Raw slices, FFT charts, timestamps)
     ├── Emits M7 Intelligence Signals
     └── Feeds LISA Grounded Fact Provider
```

---

## 3. Subsystem Health Monitors

### 3.1 Propulsion & Rotating Machinery (Fixed-Wing & Helicopters)
- **Bearing Health**: Calculates characteristic frequencies:
  - Ball Pass Frequency Outer ($BPFO$)
  - Ball Pass Frequency Inner ($BPFI$)
  - Ball Spin Frequency ($BSF$)
  - Fundamental Train Frequency ($FTF$)
- **Shaft Imbalance & Misalignment**: Evaluates $1X$ and $2X$ rotational speed harmonics.
- **Gearbox Condition**: Sideband modulation and Gear Mesh Frequency ($GMF$) energy ratios.

### 3.2 Drone & eVTOL Distributed Electric Propulsion (DEP)
- **ESC & Motor Thermal Imbalance**: Multi-rotor motor thermal variance $\Delta T = \max(T_i) - \min(T_i)$. Alert if $\Delta T > 15^\circ\text{C}$ for $> 30\text{s}$.
- **Rotor Imbalance**: Per-arm vibration sensor spectral peaks matched to ESC RPM feedback.

### 3.3 Battery Energy Storage Systems (BESS)
- **State of Health (SoH)**: Ratio of current usable capacity to nominal nameplate capacity:
  $$\text{SoH} = \frac{Q_{\text{usable}}}{Q_{\text{nominal}}} \times 100\%$$
- **Cell Delta Voltage**: Peak-to-peak cell voltage variance across series string:
  $$\Delta V_{\text{cell}} = V_{\max} - V_{\min} \quad (\text{Threshold: Amber } > 50\text{mV}, \text{Red } > 120\text{mV})$$
- **Internal Resistance (IR)**: Dynamically computed during load step transients ($dV / dI$).

---

## 4. Prognostics & Remaining Useful Life (RUL) Engine

1. **Degradation State Tracking**:
   - Condition indicators ($CI_t$) are tracked over cumulative flight hours ($t$).
   - Trajectory fitted using Bayesian linear/exponential parameter updates:
     $$CI(t) = CI_0 \cdot e^{\lambda t} + \epsilon_t$$
2. **Failure Threshold ($CI_{\text{crit}}$)**:
   - Defined by OEM maintenance manual or FAA/EASA airworthiness limits.
3. **RUL Calculation**:
   $$\text{RUL} = \frac{\ln(CI_{\text{crit}} / CI_t)}{\lambda}$$
   - Accompanied by $95\%$ confidence interval bounds $[\text{RUL}_{\text{low}}, \text{RUL}_{\text{high}}]$.

---

## 5. Traceability & Evidence Packaging

Every detected anomaly, exceedance, or degradation warning creates an immutable `HUMSEvidenceRecord`:
- **Asset ID & Component ID**
- **Flight & Timestamp Window** (UTC)
- **Raw Sensor Snippet** (timeseries slice around event)
- **Calculated Metric Values** (RMS, Kurtosis, Spectral Energy)
- **Applicable Threshold & Delta**
- **Operator Maintenance Link** (automatically opens draft maintenance work order or inspection item).
