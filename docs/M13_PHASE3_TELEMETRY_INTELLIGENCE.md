# KOTA Aerospace / AeroComply — M13 Phase 3 Telemetry Intelligence & Grounded LISA Architecture

## Telemetry -> HUMS -> M7 Intelligence -> Decision -> Grounded LISA

### 1. Executive Summary & Objective

M13 Phase 3 connects the telemetry ingestion subsystem (Phase 2) and HUMS sensor/health foundations to KOTA Aerospace's authoritative **M7 Proactive Intelligence** engine and **Grounded LISA** explanation agent.

Telemetry intelligence follows the strict **Intelligence Lineage Invariant**:
```text
External Telemetry (M13 Webhook / Ingest)
               ↓
     Telemetry Event Log (Idempotency & Audit)
               ↓
    HUMS Sensor Readings (VALID / SUSPECT / STALE)
               ↓
       HUMS Feature Engine (H2 RMS / Spectrum / Trends)
               ↓
      HUMS Baseline & Health Engine (H3 Deviations)
               ↓
    HUMS Exceedances & CAMO Findings (H1 Thresholds)
               ↓
       CAMO Evidence Thread (Provenance & Lineage)
               ↓
     M7 Proactive Intelligence Signals (Early Warnings)
               ↓
     Authoritative Readiness & Decision Engines
               ↓
      Grounded LISA (Evidence-Based Explanations)
```

---

### 2. Architectural Boundaries & Component Ownership

| Layer | Responsibility | Authoritative Service / Module |
| :--- | :--- | :--- |
| **External Ingestion** | HMAC verification, normalization, idempotency, asset resolution | [`app.services.telemetry_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/telemetry_service.py) |
| **HUMS Subsystem** | Sensor management, reading storage, feature extraction, baselines, exceedance detection | [`app.services.hums_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/hums_service.py), [`app.services.hums`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/hums/) |
| **Proactive Intelligence** | Emerging risk detection, early-warning signals, threshold monitoring, evidence aggregation | [`app.services.intelligence.proactive_intelligence_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/intelligence/proactive_intelligence_service.py) |
| **Readiness & Decision** | Operational dispatch status, 5-dimensional decision trade-offs (Cost, Time, Capability, Cert, AOG) | [`app.services.intelligence.readiness_intelligence_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/intelligence/readiness_intelligence_service.py), [`decision_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/intelligence/decision_service.py) |
| **Grounded LISA** | Question answering, explanation synthesis, grounded tool execution | [`app.services.lisa.orchestration_service`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/lisa/orchestration_service.py), [`app.services.ai.tools`](file:///c:/Users/ramna/Documents/Aerocomply/backend/app/services/ai/tools.py) |

---

### 3. Key Intelligence & Safety Invariants

1. **Deterministic Lineage**: Every proactive signal originating from telemetry contains structured `SignalEvidenceRef` instances pointing directly to the backing `HUMSExceedance`, `HUMSSensorReading`, or `TelemetryEventLog` record.
2. **Preservation of UNKNOWN / Uncertainty Semantics**:
   - $\text{Absence of Telemetry} \neq \text{Healthy}$.
   - Stale telemetry ($> 7$ days) is classified as `STALE` and generates a `TELEMETRY_FRESHNESS` warning.
   - LISA explicitly states when evidence is missing or unverified rather than asserting nominal health.
3. **No Unsupported Predictions**: No failure time or component degradation RUL is fabricated. Explanations state only observed telemetry values, thresholds, and statistical deviations.
4. **Tenant Isolation**: All intelligence queries, signal records, telemetry status checks, and LISA tools enforce strict `organization_id` boundaries. Cross-tenant access is prohibited.

---

### 4. LISA Grounded Tools & Intents

#### 4.1. Registered Tools (`app.services.ai.tools`)
- `get_asset_telemetry_status`: Returns current telemetry state (`ACTIVE`, `STALE`, `NO_TELEMETRY_RECORDED`), last received timestamp, source provider, external asset SN, and recent event logs.
- `get_asset_hums_health`: Returns component-level health status and active exceedance counts.
- `get_asset_hums_health_intelligence`: Returns explainable statistical deviations and trend directions.
- `get_asset_proactive_signals`: Returns active M7 proactive early warnings for the asset.

#### 4.2. Intent & Orchestration (`app.services.lisa`)
- `Intent.TELEMETRY_HUMS`: Matches telemetry, vibration, sensor reading, FlightHub, and health intelligence queries.
- `_investigate_telemetry_hums`: Deterministically queries telemetry status, HUMS health, and proactive signals to construct grounded, auditable answers.

---

### 5. Verified End-to-End Trace

A complete end-to-end trace was verified in integration test `test_end_to_end_telemetry_to_lisa_lineage`:
1. External FlightHub 2 telemetry payload ingested with 20 vibration samples ($9.5\text{ mm/s}$).
2. `TelemetryEventLog` recorded with `status="PROCESSED"`.
3. `HUMSSensorReading` rows stored with `source="TELEMETRY"`.
4. `HUMSExceedance` generated ($9.5 > 8.0\text{ mm/s}$, `severity="CRITICAL"`).
5. `Finding` created with `severity="CRITICAL"`.
6. `Evidence` created with `evidence_type="HUMS_TELEMETRY"` and sensor reading provenance.
7. `ProactiveSignalRecord` generated with `signal_type="HUMS_VIBRATION_EXCEEDANCE"` and `SignalEvidenceRef`.
8. LISA tool execution via `orchestration_service.investigate` retrieved telemetry status and explained the critical exceedance with concrete next steps.

---

### 6. Contract Status & External Dependencies

- **Implemented**: Full Telemetry Ingestion $\rightarrow$ HUMS $\rightarrow$ M7 Proactive Intelligence $\rightarrow$ Grounded LISA pipeline.
- **Synthetic Tested**: Verified using deterministic DJI FlightHub 2 fixtures, multi-asset fleets (drones & turboprops), and cross-tenant boundaries.
- **Live Customer Verified**: **`EXTERNAL DEPENDENCY REMAINS`**. Live integration with Horizon Air Mobility's production FlightHub 2 webhook endpoint is pending customer credential onboarding.
