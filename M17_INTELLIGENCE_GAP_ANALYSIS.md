# M17 Intelligence Gap Analysis & Engineering Roadmap

**Document Version:** 1.0  
**Author:** Tech Guy 2 (Intelligence-Side Engineering, Kota Aerospace)  
**Date:** September 2026  
**Scope:** M17 — Live Telemetry → Real-Time Processing → HUMS → Feature/Baseline → Exceedance/Anomaly → Finding + Evidence → Diagnostics → Prognostics/RUL → M7 Proactive Intelligence → LISA Grounded Explanation → Kota Control Center

---

## Executive Summary & Engineering Policy

As Tech Guy 2, this gap analysis establishes the baseline audit of Kota Aerospace's intelligence codebase. In accordance with the **Absolute Engineering Rule (Reuse > Extend > Build)**:
- **No duplicate architecture** will be constructed.
- **No v2 engines** will be introduced (`HUMS v2`, `Diagnostics v2`, `M7 v2`, `LISA v2` are strictly prohibited).
- The existing models, services, schemas, and API routers from M1–M16 and H1–H8 are thoroughly audited, mapped, and reused.

---

## Section A: Existing Telemetry Pipeline

### 1. Ingestion Pipeline
- **File:** `backend/app/services/telemetry_service.py`
- **Current Entry Points:**
  - `ingest_telemetry_batch(db, organization_id, request)` — Ingests a batch of `NormalizedTelemetryEvent` objects.
  - `process_normalized_event(db, organization_id, event, raw_payload_hash)` — Processes individual events with:
    1. Deterministic idempotency checking via `(organization_id, source_system, source_event_id)` against `TelemetryEventLog`.
    2. Tenant-isolated external asset mapping (`ExternalAssetMapping` or serial/registration fallback via `resolve_asset`).
    3. Flight record creation via `flight_service.record_flight` with duplicate protection.
    4. Battery state updating (`Battery` cycle count, health percent, voltage).
    5. Sensor reading ingestion into `HUMSSensor` and `HUMSSensorReading`.
    6. Exceedance check hook (`hums_service.detect_and_record_exceedances`).
    7. Audit event logging and `TelemetryEventLog` creation.
  - `adapt_dji_flighthub_payload(payload)` — Webhook adapter for DJI FlightHub 2 payloads (`DJIFlightHubWebhookPayload`).

### 2. Classification: `EXISTS → REUSE & EXTEND`
- **Strengths:** Robust tenant isolation, deterministic idempotency, dual mapping, provenance logging, freshness policies.
- **Gap:** Currently, when sensor readings are ingested, `telemetry_service.py` invokes `hums_service.detect_and_record_exceedances(sensor_id)`, but downstream diagnostic generation, prognostic updates, and full intelligence orchestration are triggered either lazily at read time (`get_asset_health_intelligence`) or only through the exceedance threshold. A unified real-time intelligence pipeline orchestrator must ensure streaming canonical telemetry automatically triggers the complete deterministic chain: Telemetry → Features → Baselines → Health & Exceedances → Findings + Evidence → Diagnostics → Prognostics/RUL → M7 Proactive Signals → LISA Context Cache.

---

## Section B: Existing Canonical Telemetry Contract

### 1. Model & Schema Specification
- **File:** `backend/app/schemas/telemetry.py`
- **Primary Schema:** `NormalizedTelemetryEvent`
  - `source_system: str` (e.g. `KOTA_GATEWAY`, `MAVLINK_CANONICAL`, `DJI_FLIGHTHUB`, `HUMS_DEVICE`)
  - `source_event_id: str` (Unique event ID from gateway/source)
  - `source_asset_id: str` (External asset identifier, serial number, or vehicle UUID)
  - `event_type: str` (`FLIGHT_COMPLETED | TELEMETRY_PING | BATTERY_STATE | SENSOR_BURST | REALTIME_TELEMETRY`)
  - `event_timestamp: datetime` (Timestamp of telemetry measurement)
  - `flight: TelemetryFlightPayload | None` (`flight_number`, `duration_minutes`, `cycles`, `origin`, `destination`, `flown_at`)
  - `battery: TelemetryBatteryPayload | None` (`serial_number`, `cycle_count`, `voltage_v`, `internal_resistance_mohm`, `temperature_c`, `health_percent`, `cell_voltages`)
  - `readings: list[TelemetryReadingItem]` (`sensor_code`, `sensor_type`, `measurement_type`, `value`, `unit`, `component_id`, `data_quality`)
  - `raw_metadata: dict[str, Any]`

### 2. Classification: `EXISTS → REUSE (FROZEN INPUT CONTRACT)`
- Preserves tenant boundaries, asset identification, flight link, component mapping, unit, data quality (`VALID`, `SUSPECT`, `MISSING`, `OUT_OF_RANGE`, `STALE`, `DUPLICATE`, `INVALID`), and timestamp.

---

## Section C: Existing HUMS Capabilities

### 1. Data Models
- **File:** `backend/app/models/hums.py`
  - `HUMSSensor`: Physical/simulated sensor registered to an asset/component (`sensor_code`, `sensor_type`, `measurement_type`, `unit`, `status`, `source`).
  - `HUMSSensorReading`: Telemetry point (`recorded_at`, `value`, `unit`, `data_quality`, `source`, `ingestion_batch`).
  - `HUMSExceedance`: Detected threshold breach with `contributing_reading_ids`, `finding_id`, `severity`, `observed_value`, `threshold_value`.
  - `HUMSFeature`: Persisted windowed feature (`measurement_type`, `feature_type`, `value`, `unit`, `sample_count`, `quality`, `calculation_method`, `source_reading_ids`, `feature_metadata`).
  - `HUMSBaseline`: Statistical versioned baseline (`mean`, `median`, `std_dev`, `lower_bound`, `upper_bound`, `percentiles`, `version`, `is_current`, `quality`, `confidence`).
  - `HUMSDiagnosticCandidate`: Fault hypothesis (`fault_code`, `fault_name`, `fault_domain`, `status`, `severity`, `score`, `confidence`, `primary_evidence`, `supporting_evidence`, `contradicting_evidence`, `explanation`).
  - `HUMSDegradationModel`: Fitted degradation trajectory (`fit_slope`, `fit_intercept`, `fit_error`, `r_squared`, `trajectory_state`, `quality`, `confidence`, `is_current`).
  - `HUMSPrognosticRecord`: Persisted RUL record (`rul_estimate`, `rul_lower`, `rul_upper`, `rul_unit`, `confidence`, `quality`, `status`, `explanation`, `is_current`).

### 2. Classification: `EXISTS → REUSE`

---

## Section D: Existing Feature Engine

### 1. Extractors & Service
- **Files:** `backend/app/services/hums/feature_extractors.py`, `backend/app/services/hums/feature_service.py`
- **Capabilities:**
  - **Time-Domain Statistics:** `min`, `max`, `mean`, `median`, `std`, `variance`, `range`, `p95`.
  - **Vibration Time-Domain:** `rms` ($\sqrt{\frac{1}{N}\sum x^2}$), `peak`, `peak_to_peak`, `crest_factor` ($\frac{\text{peak}}{\text{rms}}$), `kurtosis` (Fisher excess), `skewness`.
  - **Frequency-Domain (DFT):** `dominant_frequency` (excluding DC), `spectral_energy`, `band_energy`.
  - **Trend Features:** `trend` (least-squares slope $\beta_1$), `rate_of_change` ($\frac{\Delta x}{\Delta t}$).
  - **Quality & Provenance:** Returns `FeatureResult` with explicit `quality` (`GOOD`, `DEGRADED`, `INSUFFICIENT_DATA`, `INVALID`), `calculation_method`, sample counts, and window bounds.
- **Classification:** `EXISTS → REUSE`

---

## Section E: Existing Baseline Engine

### 1. Engines & Services
- **Files:** `backend/app/services/hums/baseline_engine.py`, `backend/app/services/hums/baseline_service.py`, `backend/app/services/hums/health_engine.py`, `backend/app/services/hums/health_service.py`
- **Capabilities:**
  - Computes `mean`, `median`, `std_dev`, percentiles (p05, p25, p50, p75, p95), and statistical bounds ($\mu \pm 2\sigma$ or non-parametric).
  - Versioned and immutable: increments version on update, retains historical auditability.
  - Evaluates deviations (`compute_deviation`): states `NORMAL`, `ELEVATED` ($> 2\sigma$), `DEVIATED` ($> 3\sigma$), `SEVERE` ($> 4\sigma$).
  - Evaluates trends (`compute_trend`): `STABLE`, `INCREASING`, `DECREASING`, `VOLATILE`, `ACCELERATING`.
  - Computes consecutive deviation persistence (`consecutive_deviation_count`).
- **Classification:** `EXISTS → REUSE`

---

## Section F: Existing Fault Signature Registry

### 1. In-Code Registry
- **File:** `backend/app/services/hums/fault_signatures.py`
- **Capabilities:**
  - `BEARING_DEGRADATION` (`VIB-BRG-001`): Requires elevated RMS and elevated kurtosis; supported by elevated crest factor and worsening RMS trend.
  - `ROTOR_IMBALANCE` (`VIB-IMB-001`): Requires elevated RMS with normal kurtosis; contradicted by elevated kurtosis.
  - `SENSOR_ANOMALY` (`SEN-ANOM-001`): Single isolated sensor abnormal while peer sensors on same component remain healthy.
- **Classification:** `EXISTS → REUSE`

---

## Section G: Existing Diagnostics

### 1. Diagnostic Engine & Service
- **Files:** `backend/app/services/hums/diagnostic_engine.py`, `backend/app/services/hums/diagnostic_service.py`
- **Capabilities:**
  - Generates `DiagnosticEvaluation` scoring candidates based on satisfied required/supporting/contradicting conditions.
  - Candidate status: `CANDIDATE`, `SUPPORTED`, `WEAK`.
  - Human-in-the-loop lifecycle: `CONFIRMED`, `REJECTED`, `RESOLVED` can only be set by authorized human user.
  - Evidence linkage: Primary, supporting, and contradicting evidence items stored in `HUMSDiagnosticCandidate`.
  - Proactive signal sync: `_sync_diagnostic_signal` generates `HUMS_DIAGNOSTIC_CANDIDATE` signal.
- **Classification:** `EXISTS → REUSE`

---

## Section H & I: Existing Prognostics & Remaining Useful Life (RUL)

### 1. Degradation Engine, Service & Prognostic Service
- **Files:** `backend/app/services/hums/degradation_engine.py`, `backend/app/services/hums/degradation_service.py`, `backend/app/services/hums/prognostic_service.py`
- **Capabilities:**
  - Fits linear degradation models ($y = \beta_0 + \beta_1 t$) over historical usage span (flight hours or elapsed hours).
  - Evaluates $R^2$, RMSE, slope, trajectory state (`DEGRADING`, `STABLE`, `IMPROVING`, `INSUFFICIENT_DATA`).
  - Computes RUL point estimate, upper and lower prediction intervals with model drift detection (`detect_model_drift`).
  - Safety-first guardrails: Explicit status `AVAILABLE`, `LIMITED`, `INSUFFICIENT_DATA`, `LOW_CONFIDENCE`, `STALE`. Explicit disclaimers: "ESTIMATE — NOT A CERTIFIED LIFE LIMIT".
  - Signal sync: `_sync_rul_signal` creates `HUMS_RUL_WARNING` on warning window entry.
- **Classification:** `EXISTS → REUSE`

---

## Section J: Existing M7 Proactive Intelligence

### 1. Proactive Intelligence Service
- **File:** `backend/app/services/intelligence/proactive_intelligence_service.py`
- **Signal Types Handled:**
  - `MAINTENANCE_THRESHOLD` (Work orders overdue/approaching, battery degradation/cycles)
  - `INSPECTION_THRESHOLD` (Maintenance requirements by flight hours/cycles)
  - `RECURRING_FINDING` (Repeated findings across subsystem keywords in 90-day window)
  - `UTILIZATION_TREND` (Surges in 14-day flight activity)
  - `COMPLIANCE_RISK` (Unverified or UNKNOWN compliance obligations)
  - `EVIDENCE_GAP` (Closed work orders without evidence files)
  - `READINESS_DEGRADATION` (Readiness blocked conditions)
  - `HUMS_VIBRATION_EXCEEDANCE` / `HUMS_EXCEEDANCE`
  - `TELEMETRY_FRESHNESS` (Configurable warning/critical stale thresholds)
  - `FLEET_PATTERN` (Cross-asset recurring discrepancies)
- **Signal Lifecycle:** `OPEN` → `ACKNOWLEDGED` → `IN_REVIEW` → `RESOLVED` / `DISMISSED`.
- **Classification:** `EXISTS → REUSE & EXTEND` (Ensure full live telemetry ingestion triggers end-to-end sync).

---

## Section K: Existing LISA (AI Grounded Assistant)

### 1. Orchestration, Tools & Grounding
- **Files:** `backend/app/services/lisa/orchestration_service.py`, `backend/app/services/ai/tools.py`, `backend/app/services/intelligence/context_service.py`
- **Capabilities:**
  - Tool-based deterministic grounding: AI never guesses; queries authoritative tools.
  - Tools available: `get_intelligence_context`, `get_fleet_attention_summary`, `get_proactive_intelligence_summary`, `get_asset_proactive_signals`, `get_asset_hums_health`, `get_asset_hums_features`, `get_asset_hums_health_intelligence`, `get_asset_telemetry_status`, `get_asset_hums_diagnostics`, `get_asset_hums_prognostics`, `get_digital_twin`, `get_asset_twin_timeline`, `get_asset_mro_intelligence`.
  - Fallback: Honest representation when information is `UNKNOWN` or `INSUFFICIENT_DATA`.
- **Classification:** `EXISTS → REUSE`

---

## Section L & M: Existing Correlation & Fleet Attention

### 1. Fleet Intelligence & MRO Correlation
- **Files:** `backend/app/services/intelligence/fleet_intelligence_service.py`, `backend/app/services/intelligence/cross_asset_intelligence_service.py`, `backend/app/services/mro_intelligence_service.py`
- **Capabilities:**
  - Fleet-wide aggregation of operational state, readiness state, risk level, priority level, decision state, and top recommendation.
  - Fleet attention summary filtering for critical/high priority and immediate action assets.
  - Cross-asset component and defect correlation.
- **Classification:** `EXISTS → REUSE`

---

## Section N, O, P: APIs, Tests & Database Models

### 1. APIs
- `backend/app/api/v1/telemetry.py` (Ingestion, DJI Webhook, Mappings, Status, Freshness)
- `backend/app/api/v1/hums.py` (Sensors, Readings, Features, Baselines, Deviations, Trends, Health Intelligence, Diagnostics, Prognostics)
- `backend/app/api/v1/proactive.py` (Signals, Summary, Lifecycle Actions)
- `backend/app/api/v1/lisa.py` (Ask, Conversation Context)
- `backend/app/api/v1/intelligence.py` (Context, Fleet, State, Readiness, Risk, Priority, Decision, Recommendation)
- `backend/app/api/v1/control_center.py` (Fleet and Asset Summaries)

### 2. Tests
- **Unit:** 497 tests in `backend/tests/unit` covering feature extraction, baseline engine, degradation engine, diagnostic engine, lifecycle policy, Kleene logic, permissions.
- **Integration:** Comprehensive suites in `backend/tests/integration` (`test_m13_telemetry_ingestion.py`, `test_m13_telemetry_intelligence.py`, `test_m7_proactive_intelligence.py`, `test_hums_foundation.py`, `test_hums_baseline_and_health.py`, `test_hums_diagnostics.py`, `test_hums_prognostics.py`, `test_lisa_orchestration.py`, `test_lisa_grounded_intelligence.py`).

### 3. Database Models & Migrations
- All required tables exist in PostgreSQL (`telemetry_event_logs`, `external_asset_mappings`, `telemetry_freshness_policies`, `hums_sensors`, `hums_sensor_readings`, `hums_features`, `hums_baselines`, `hums_exceedances`, `hums_diagnostic_candidates`, `hums_degradation_models`, `hums_prognostic_records`, `proactive_signal_records`, `findings`, `evidence`, `evidence_files`).
- **No new database migrations are required for M17.**

---

## Section Q & R: Missing Integration Points & Partial Implementations

### Gap 1: Real-Time Telemetry Pipeline Orchestration
- **Current Behavior:** Ingestion in `telemetry_service.py` calls `hums_service.detect_and_record_exceedances`. However, `evaluate_and_persist_diagnostics` and `evaluate_and_persist_prognostic` were previously only triggered at read-time (`get_asset_health_intelligence`) or via manual calls.
- **Required Extension:** Extend `telemetry_service.process_normalized_event` / `hums_service.detect_and_record_exceedances` so that after feature windowing and baseline refresh, the full intelligence pipeline runs synchronously/near-real-time:
  1. Feature extraction & persistence (`HUMSFeature`)
  2. Baseline refresh (`HUMSBaseline`)
  3. Exceedance & Anomaly check (`HUMSExceedance`)
  4. Finding creation & Evidence linkage (`Finding`, `Evidence`)
  5. Diagnostic evaluation & candidate persistence (`HUMSDiagnosticCandidate`)
  6. Prognostic trajectory fitting & RUL update (`HUMSDegradationModel`, `HUMSPrognosticRecord`)
  7. M7 Proactive Signal generation (`ProactiveSignalRecord`)
  8. LISA Grounded Context synchronization

### Gap 2: Canonical Telemetry Simulator
- **Current Behavior:** Unit and integration tests construct individual dictionaries or mock objects. There is no unified, reusable canonical simulator service providing standard scenarios (Healthy baseline, Gradual vibration degradation, Sudden temperature anomaly, Telemetry staleness/dropout, Telemetry recovery, Corrupted/out-of-order data).
- **Required Action:** Build `backend/app/services/edge/telemetry_simulator.py` (for test and development execution) to publish realistic streaming canonical batches across all scenarios into the production ingestion boundary.

### Gap 3: Complete End-to-End Verification Test Suite
- **Current Behavior:** Separate tests verify parts of the chain.
- **Required Action:** Build comprehensive M17 end-to-end integration test `backend/tests/integration/test_m17_end_to_end_intelligence_chain.py` that verifies the unbroken chain from canonical telemetry through LISA and Control Center.

---

## Section S: Duplicated Capabilities to Avoid

1. **DO NOT** create a second telemetry ingest schema. Use `NormalizedTelemetryEvent`.
2. **DO NOT** create a second feature extractor. Use `app.services.hums.feature_extractors`.
3. **DO NOT** create a second baseline engine. Use `app.services.hums.baseline_service` & `health_service`.
4. **DO NOT** create a second diagnostic engine. Use `app.services.hums.diagnostic_service`.
5. **DO NOT** create a second prognostic/RUL engine. Use `app.services.hums.prognostic_service`.
6. **DO NOT** create a second proactive signal table/service. Use `ProactiveSignalRecord` & `proactive_intelligence_service`.
7. **DO NOT** create a second LISA grounding framework. Use `app.services.ai.tools` & `lisa/orchestration_service`.

---

## Section T & U: Exact Files Requiring Modification & Creation

### Files to Modify:
1. `backend/app/services/telemetry_service.py` — Complete real-time intelligence trigger across feature -> baseline -> exceedance -> finding -> diagnostic -> prognostic -> M7 chain.
2. `backend/app/services/hums_service.py` — Ensure `detect_and_record_exceedances` orchestrates downstream diagnostic and prognostic updates when readings arrive.
3. `backend/app/services/intelligence/proactive_intelligence_service.py` — Ensure all live HUMS diagnostic and prognostic signals are synchronized into the central proactive feed.

### Files to Create:
1. `backend/app/services/edge/telemetry_simulator.py` — Canonical telemetry scenario generator (Healthy, Vibration Degradation, Telemetry Stale, Telemetry Recovery, Sensor Anomaly).
2. `backend/tests/integration/test_m17_end_to_end_intelligence_chain.py` — Comprehensive integration test verifying the entire 9-step intelligence chain.
3. `M17_INTELLIGENCE_ARCHITECTURE.md` — Full architectural specification.
4. `M17_TECH_GUY_1_HANDOFF.md` — Contract documentation for Tech Guy 1.

---

## Section V: Tech Guy 1 → Tech Guy 2 Interface

- **Input Format:** `NormalizedTelemetryEvent` (or batch in `TelemetryIngestRequest`) submitted to `POST /api/v1/telemetry/ingest` or processed via internal service call.
- **Required Fields:**
  - `source_system`: String (e.g. `KOTA_GATEWAY`, `MAVLINK_CONNECTOR`, `DJI_FLIGHTHUB`)
  - `source_event_id`: Unique event ID for idempotency deduplication
  - `source_asset_id`: External asset serial or ID
  - `event_timestamp`: UTC datetime
  - `event_type`: Event category
  - `readings`: Array of sensor readings with `sensor_code`, `measurement_type`, `value`, `unit`, and `data_quality`.
  - `flight`: Optional flight operation details (`duration_minutes`, `flight_number`, `cycles`, `origin`, `destination`).
  - `battery`: Optional battery metrics (`serial_number`, `voltage_v`, `cycle_count`, `temperature_c`, `health_percent`).

---

## Section W: End-to-End Gaps Preventing M17 Completion

1. **Automated Pipeline Linkage:** Telemetry ingestion must seamlessly propagate to feature computation, baseline comparison, finding creation, diagnostic hypothesis evaluation, degradation trajectory fitting, and proactive signal synchronization without manual or read-time trigger dependencies.
2. **Deterministic Grounding Verification:** Verify that LISA receives the exact evidence IDs, sensor codes, baseline deviations, and RUL confidence metrics produced by the live telemetry stream.
3. **Freshness State Enforcement:** Verify that stale telemetry is explicitly surfaced as `STALE` / `TELEMETRY_FRESHNESS` warning, preventing false healthy declarations.

---
**Gap Analysis Complete. Proceeding to Architecture Specification and Pipeline Implementation.**
