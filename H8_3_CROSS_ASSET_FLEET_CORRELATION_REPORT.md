# KOTA AEROSPACE — MILESTONE H8.3 COMPLETION REPORT
## CROSS-ASSET HUMS CORRELATION & FLEET ANOMALY INTELLIGENCE

**Workstream:** Developer 2.1 — Intelligence & Decision Systems  
**Milestone:** H8.3 — Cross-Asset Fleet Correlation  
**Status:** COMPLETE  
**Repository:** `C:\Users\ramna\Documents\Aerocomply`  
**Base / Current Branch:** `staging/m17-drone-ops-review`  
**Evaluation Date:** October 4, 2026  

---

## 1. EXECUTIVE SUMMARY

Milestone H8.3 establishes the Cross-Asset Fleet Correlation capability for Kota Aerospace / AeroComply. Fleet operators can now detect, evaluate, and investigate systemic vibration anomalies, HUMS exceedance clusters, and operational degradation patterns across multiple aircraft, drones, helicopters, and advanced air mobility assets.

Crucially, the implementation enforces the **correlation-is-not-causation governance boundary**: statistical similarity across fleet observations is explicitly distinguished from physical causation. The engine never claims or implies a common root cause, shared physical defect, or fleet-wide failure mechanism solely because multiple airframes exhibit correlated signals. M7 remains the sole canonical owner of proactive intelligence signals and attention ranking, ensuring H8.3 acts as a read-only explanatory and enrichment layer without creating duplicate alerts or competing pipelines.

---

## 2. REPOSITORY & ARCHITECTURE AUDIT

### 2.1 Git Audit
- **Active Working Branch:** `staging/m17-drone-ops-review`
- **Starting Commit:** `6c53358`
- **Working Tree State:** Clean working tree prior to H8.3 implementation.
- **Upstream Coordination:** Shared domain contracts with Developer 1 (MRO / maintenance) and Developer 2.2 (Gateway / Telemetry) remain untouched.

### 2.2 Domain Boundaries Audited
1. **M7 Canonical Signal Ownership:** M7 (`ProactiveSignalRecord`, `app.services.intelligence.proactive_intelligence_service`) remains the sole authority for proactive fleet alerting and operator attention. H8.3 consumes open M7 signals strictly read-only.
2. **H1–H5 HUMS Subsystems:**
   - H1: Sensors (`HUMSSensor`) and raw telemetry exceedances (`HUMSExceedance`).
   - H2: Traceable windowed features (`HUMSFeature`).
   - H3: Statistical baselines (`HUMSBaseline`).
   - H4: Diagnostic candidate hypotheses (`HUMSDiagnosticCandidate`).
   - H5: Prognostic degradation models (`HUMSDegradationModel`, `HUMSPrognosticRecord`).
   - H6: Digital twin component tree lookup (`digital_twin_service.get_asset_component_tree`).
3. **Immutability & Read-Only Governance:**
   `cross_asset_intelligence_service.py` is strictly read-only: zero calls to `db.add()`, `session.add()`, or `.commit()`. All correlation results are computed dynamically on demand and grounded in authoritative PostgreSQL rows.

---

## 3. EXISTING CONTRACTS REUSED

| Component / Model | Module / Schema | Role in H8.3 |
|---|---|---|
| `HUMSExceedance` | `app.models.hums` | Primary observation source for parameter exceedances (`vibration_rms`, `vibration_peak`, etc.) |
| `HUMSFeature` | `app.models.hums` | Source for multi-asset vibration feature anomalies (`kurtosis`, `crest_factor`, `rms`) |
| `HUMSSensor` | `app.models.hums` | Sensor metadata, unit verification, measurement type matching, and telemetry simulation status |
| `ProactiveSignalRecord` | `app.models.proactive_signal` | Read-only M7 signal corroboration and evidence linkage |
| `Asset` & `Aircraft` | `app.models.asset`, `app.models.aircraft` | Authoritative asset identity, type, serial numbers, and registrations |
| `Component` | `app.models.component` | Subsystem and line-replaceable unit (LRU) component correlation |
| `FleetCorrelationContext` | `app.schemas.fleet_intelligence` | Public typed API schema extended additively with `anomaly_correlations` |
| `DataAvailability` | `app.schemas.fleet_intelligence` | Transparent data availability state (`AVAILABLE` vs `DATA_UNAVAILABLE`) |

---

## 4. H8.3 ARCHITECTURE & CORRELATION ENGINE

### 4.1 Candidate Selection & Grouping
The engine (`_correlate_fleet_anomaly_patterns`) evaluates observations over a configurable lookback window (default: 30 days):
1. **Grouping by Parameter / Feature Family:**
   Observations are grouped by anomaly parameter (e.g. `vibration_rms`, `vibration_peak`, `kurtosis`).
2. **Multi-Asset Requirement ($\ge 2$ Assets):**
   An anomaly observed on only a single asset is classified as an **isolated anomaly** and is explicitly excluded from fleet correlation to prevent unsupported alert fatigue.
3. **Sensor Compatibility Gate:**
   Sensors across participating assets are checked for unit compatibility (e.g. `g` vs `mm/s`) and sensor type compatibility (e.g. `VIBRATION` vs `TEMPERATURE`). If incompatible, the correlation is restricted and marked `INCOMPATIBLE_UNITS` or `INCOMPATIBLE_SENSOR_TYPES` with `INSUFFICIENT_EVIDENCE` confidence.
4. **Operational Condition Comparability Gate:**
   Operating regimes are verified across observations. If telemetry denotes divergent flight conditions, `operating_conditions_comparable` is set to `False` and confidence is demoted to `LOW`.
5. **Simulation Isolation Gate:**
   Telemetry source (`SIMULATED`, `IMPORTED`, `LIVE`) is tracked. If any participating sensor is simulated, `is_simulation = True` is stamped on the correlation.

### 4.2 Statistical Analysis & Similarity Metric
Rather than arbitrary heuristic scores or opaque machine learning models, H8.3 implements deterministic statistical dispersion analysis:
- For compatible observations, the engine calculates the population mean $\mu$, sample standard deviation $\sigma$, and coefficient of variation $CV = \frac{\sigma}{\mu}$.
- Statistical similarity is defined as:
  $$S = \text{round}(\max(0.0, \min(1.0, 1.0 - CV)), 3)$$
- Identical or near-identical anomalous vibration magnitudes yield $S \ge 0.85$, while divergent spreads yield lower similarity scores.

### 4.3 Deterministic Identity & Deduplication
To ensure zero duplicate alerts or state thrashing, correlation identifiers are generated deterministically using UUIDv5 over a DNS namespace seed:
```python
seed = f"kota:h83:{organization_id}:{param}:{sorted_participating_asset_ids}"
corr_id = uuid.uuid5(uuid.NAMESPACE_DNS, seed)
```
Repeated evaluations over the same operational dataset produce the exact same ID, guaranteeing idempotent retrieval and zero duplicate record generation.

### 4.4 Transparent Confidence Classification
- **HIGH:** $\ge 3$ participating assets, $\ge 6$ observations, compatible sensors, corroborating M7 signal, and similarity score $S \ge 0.70$.
- **MEDIUM:** $\ge 2$ participating assets, $\ge 4$ observations, compatible sensors, and similarity score $S \ge 0.50$.
- **LOW:** Sparse observations or divergent operational flight conditions.
- **INSUFFICIENT_EVIDENCE:** Incompatible sensor types/units or incomplete telemetry.

---

## 5. CORRELATION VERSUS CAUSATION SAFEGUARDS

In strict compliance with aerospace governance and system invariants, every correlation record contains the mandatory disclaimer:
> *"Statistical correlation detected across fleet observations. Correlation does not imply shared physical origin, common initiating mechanism, or causality. Operational conditions and airframe variations must be reviewed by qualified engineering personnel."*

Furthermore, all string fields generated across the H8.3 pipeline are strictly validated against forbidden causation patterns (`root cause`, `defective`, `failure`, `unsafe`, `unairworthy`, `not airworthy`).

---

## 6. API ENDPOINTS & ACCESS CONTROL

Two new authenticated, tenant-isolated REST endpoints are mounted in `backend/app/api/v1/intelligence.py`:

### 6.1 `GET /api/v1/intelligence/fleet/correlation`
- **Description:** Returns the full `FleetCorrelationContext` including asset correlations, component correlations, signal associations, and `anomaly_correlations`.
- **Query Parameters:**
  - `asset_id`: Filter correlations including a specific asset.
  - `pattern_type`: Filter by pattern type (e.g. `VIBRATION_EXCEEDANCE_PATTERN`).
  - `feature_family`: Filter by parameter (e.g. `vibration_rms`).
  - `confidence`: Filter by confidence (`HIGH`, `MEDIUM`, `LOW`, `INSUFFICIENT_EVIDENCE`).
  - `days`: Lookback window in days (1 to 365, default 30).
- **Authorization:** Requires authenticated tenant user with `Permission.AIRCRAFT_READ`.

### 6.2 `GET /api/v1/intelligence/fleet/correlation/{correlation_id}`
- **Description:** Returns the complete detail and evidence references for a specific correlation ID.
- **Error Handling:** Returns `404 Not Found` if the correlation ID does not exist within the tenant organization.

---

## 7. FRONTEND INTELLIGENCE UI INTEGRATION

1. **Typed Client (`frontend/lib/api/intelligence.ts`):**
   - Added `FleetAnomalyPatternCorrelation` and `FleetCorrelationContext` interfaces.
   - Added `getFleetCorrelation()` and `getFleetCorrelationDetail()` API methods.
2. **Fleet Intelligence Control Center (`frontend/app/(app)/intelligence/fleet/page.tsx`):**
   - Added a compact **Cross-Asset Fleet Correlation & Anomaly Intelligence (H8.3)** section.
   - Visual badges for Pattern Type, Feature Family, Confidence Tier (green/amber/gray), Simulation status, and Sensor Compatibility.
   - Displays statistical similarity percentage, participating asset tags linked to asset intelligence views, engineering considerations, and the statutory correlation disclaimer.

---

## 8. SYNTHETIC MULTI-ASSET SCENARIOS (VALIDATION SUITE)

The test suite in `backend/tests/integration/test_h8_3_fleet_hums_correlation.py` covers Scenarios A through H:

| Scenario | Objective | Observed Result | Status |
|---|---|---|---|
| **Scenario A** | Similar vibration patterns across 3 compatible assets | `HIGH` confidence, $S \ge 0.85$, `SUPPORTED` lifecycle, 6 evidence references, corroborating M7 signal links | **PASS** |
| **Scenario B** | Isolated anomaly on single asset | Excluded from fleet correlation (`anomaly_correlations == []`) | **PASS** |
| **Scenario C** | Incompatible sensors (unit mismatch: `g` vs `mm/s`) | Marked `INCOMPATIBLE_UNITS`, $S = 0.0$, `INSUFFICIENT_EVIDENCE` | **PASS** |
| **Scenario D** | Sparse observations ($N < 4$) | Marked `INSUFFICIENT_EVIDENCE`, `CANDIDATE` lifecycle | **PASS** |
| **Scenario E** | Divergent operational flight conditions | `operating_conditions_comparable = False`, confidence qualified to `LOW` | **PASS** |
| **Scenario F** | Repeated evaluation stability | Deterministic UUIDv5 matches across runs; zero new signal alerts created in DB | **PASS** |
| **Scenario G** | Multi-tenant boundary isolation | Identical data in Org 1 and Org 2 strictly isolated; zero cross-tenant leakage | **PASS** |
| **Scenario H** | Simulation vs real telemetry distinction | Preserves `is_simulation = True` for simulated sensors and `False` for live sensors | **PASS** |
| **Translation** | Pydantic model serialization | `get_fleet_correlation_context` cleanly serializes dataclasses to Pydantic models | **PASS** |
| **API Client** | REST endpoint contract | Filtering, detail lookup, and 404 error handling verified via FastAPI `TestClient` | **PASS** |

---

## 9. TEST EVIDENCE & QUALITY GATES

### 9.1 Targeted H8.3 Test Suite
- **Command:** `pytest backend/tests/integration/test_h8_3_fleet_hums_correlation.py -v`
- **Result:** **34 passed in 4.09s** (100% passing)

### 9.2 Full Regression Test Suite
- **Command:** `pytest backend/tests/integration/test_h8_0_fleet_foundation.py backend/tests/integration/test_h8_2_m7_signal_integration.py backend/tests/integration/test_h8_3_fleet_hums_correlation.py backend/tests/integration/test_h8_4_fleet_mro_intelligence.py backend/tests/integration/test_m7_proactive_intelligence.py backend/tests/integration/test_m7_uat_scenarios.py -q`
- **Result:** **107 passed in 11.00s** (100% passing across all H8 and M7 suites)

---

## 10. ACCEPTANCE MATRIX (H83-01 to H83-16)

| ID | Acceptance Criterion | Status | Evidence |
|---|---|---|---|
| H83-01 | Existing H8.0–H8.2 contracts reused or changes justified | **PASS** | Reused `FleetCorrelationContext`, `DataAvailability`, and existing aggregation patterns. |
| H83-02 | Cross-asset vibration and exceedance correlation implemented | **PASS** | `_correlate_fleet_anomaly_patterns` groups and correlates HUMS exceedances and features. |
| H83-03 | Sensor and operating-condition compatibility considered | **PASS** | Validates sensor units/types and checks flight regime comparability. |
| H83-04 | Confidence and data quality transparent and evidence-based | **PASS** | Defined tiers (`HIGH`, `MEDIUM`, `LOW`, `INSUFFICIENT_EVIDENCE`) based on sample size and dispersion. |
| H83-05 | Correlation explicitly distinguished from causation | **PASS** | Verified disclaimer and absence of forbidden causation vocabulary. |
| H83-06 | M7 remains canonical fleet-signal owner | **PASS** | M7 signals consumed read-only; no signal table mutation or ranking override. |
| H83-07 | H8.3 does not generate duplicate canonical alerts | **PASS** | Verified by `test_scenario_f`: zero DB signal rows created on repeated evaluations. |
| H83-08 | Evidence and source signal references traceable | **PASS** | `evidence_references` and `supporting_signal_ids` attached to every correlation item. |
| H83-09 | Tenant isolation and authorization verified | **PASS** | Verified by `test_scenario_g` and permission-guarded FastAPI endpoints. |
| H83-10 | Simulation and real telemetry classification preserved | **PASS** | Verified by `test_scenario_h`: `is_simulation` flag preserved without mixing. |
| H83-11 | Sparse, stale, incompatible, and missing data handled safely | **PASS** | Covered by Scenarios C, D, E with explicit fallback flags and notes. |
| H83-12 | Deterministic synthetic multi-asset scenarios pass | **PASS** | All Scenarios A–H implemented and passing in integration test suite. |
| H83-13 | Relevant H8 and M7 regression tests pass | **PASS** | 107/107 integration and regression tests passing. |
| H83-14 | Performance and failure isolation reviewed | **PASS** | Bounded lookback queries, staged candidate filtering, and error containment in place. |
| H83-15 | Documentation and known limitations complete | **PASS** | Comprehensive documentation provided in this report. |
| H83-16 | Changes isolated from other developer work | **PASS** | Only H8.3 files touched; no edits to Developer 1 maintenance or Developer 2.2 gateway code. |

---

## 11. CHANGED FILES

1. `backend/app/schemas/fleet_intelligence.py`
   - Added `FleetAnomalyPatternCorrelation` Pydantic model with strict validation and governance disclaimer.
   - Updated `AssetCorrelationEntry` with `has_rul_estimate`.
   - Updated `FleetCorrelationContext` to include `anomaly_correlations`.
2. `backend/app/services/intelligence/cross_asset_intelligence_service.py`
   - Added `FleetAnomalyPatternCorrelation` dataclass and updated `FleetCorrelationSummary`.
   - Implemented `_correlate_fleet_anomaly_patterns` with sensor compatibility, statistical similarity, and M7 integration.
   - Implemented `get_fleet_correlation_context` for REST endpoint schema conversion.
3. `backend/app/api/v1/intelligence.py`
   - Mounted `GET /api/v1/intelligence/fleet/correlation` (with filtering) and `GET /api/v1/intelligence/fleet/correlation/{correlation_id}`.
4. `backend/tests/integration/test_h8_3_fleet_hums_correlation.py`
   - Added helpers and tests for Scenarios A through H and API endpoints (34/34 passing).
5. `frontend/lib/api/intelligence.ts`
   - Added TypeScript types and API client functions (`getFleetCorrelation`, `getFleetCorrelationDetail`).
6. `frontend/app/(app)/intelligence/fleet/page.tsx`
   - Integrated the Cross-Asset Fleet Correlation & Anomaly Intelligence UI component.

---

## 12. KNOWN LIMITATIONS & NEXT MILESTONES

### Known Limitations
1. **Uncalibrated Cross-Modality Sensor Translation:** Cross-asset correlation currently requires compatible units and sensor types; cross-modal estimation (e.g. converting raw piezo g-levels to optical strain micro-strain) is deliberately excluded until physical calibration curves are configured.
2. **Read-Only Invariant:** H8.3 does not auto-generate MRO work orders. Corrective actions remain strictly in human engineer and Developer 1 maintenance domain.

### Next Recommended Milestone
- **Milestone H8.5 / Lisa AI Fleet Intelligence Grounding:** Ground Lisa AI queries in H8.3 cross-asset correlation evidence and M7 proactive signals for natural-language fleet health queries.
