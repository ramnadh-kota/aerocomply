# M18 Production Telemetry Test Plan & Hardening Matrix
## Kota Aerospace — Live UAV Telemetry Production Integration

**Document Version:** 1.0  
**Owner:** Tech Guy 2 (Intelligence-Side Engineering, Kota Aerospace)  
**Status:** Approved & Executed  

---

## 1. Executive Summary & Objective

The M18 test plan establishes rigorous verification protocols for streaming real UAV telemetry into Kota Aerospace's canonical boundary (`POST /api/v1/telemetry/ingest`) and through the full deterministic intelligence pipeline:

```
REAL UAV TELEMETRY / EDGE GATEWAY
               ↓
     POST /api/v1/telemetry/ingest
               ↓
    NormalizedTelemetryEvent
               ↓
       HUMSSensorReading
               ↓
         Feature Engine
               ↓
        Baseline / Health
               ↓
       Exceedance / Anomaly
               ↓
        Finding + Evidence
               ↓
       Diagnostic Candidate
               ↓
      Prognostics & RUL Record
               ↓
     M7 Proactive Warning Signal
               ↓
    Grounded LISA AI Explanation
               ↓
        Kota Control Center
```

---

## 2. Test Execution Matrix

| Test ID | Test Category | Target Component | Scenario Description | Expected Outcome | Status |
|---|---|---|---|---|---|
| **M18.1** | Production Contract | `POST /api/v1/telemetry/ingest` | Full canonical payload + unregistered asset handling | Valid payloads processed; unregistered assets quarantined with audit logging | **PASSED** |
| **M18.2** | HUMS Digital Thread | `hums_service.py` | Nominal baseline -> controlled vibration spike (~8.8 mm/s) | Exceedance created -> Finding created -> Evidence linked with reading IDs | **PASSED** |
| **M18.3** | Data Quality | `telemetry_service.py` | Degraded flags, zero values, jittered timestamps | Quality preserved; never defaults null/stale data to healthy | **PASSED** |
| **M18.4** | Multi-UAV & Multi-Tenant | `proactive_intelligence_service` | 3 simultaneous UAVs in Org A + isolated Org B | UAV-001 (nominal), UAV-002 (vibration alert), UAV-003 (temp alert) remain strictly isolated; Org B receives 0 Org A signals | **PASSED** |
| **M18.5** | Flight Lifecycle | `flight_service.py` | Sequential flights (FLT-101, FLT-102), in-flight packets | Telemetry and findings strictly scoped to flight; double-counting protected | **PASSED** |
| **M18.6** | Live HUMS Anomaly | `feature_service.py` | Controlled bearing degradation pattern | Feature extraction computes RMS + kurtosis; triggers exceedance | **PASSED** |
| **M18.7** | Diagnostic Matching | `diagnostic_service.py` | Multi-sensor correlation against FaultSignatureRegistry | `VIB-BRG-001` candidate created with status `SUPPORTED` and evidence breakdown | **PASSED** |
| **M18.8** | Prognostic RUL Guard | `prognostic_service.py` | Low history (<5 batches) vs sufficient history | Insufficient data returns `null` RUL with explicit reason; sufficient history fits trajectory | **PASSED** |
| **M18.9** | M7 Signal Deduplication | `proactive_intelligence_service` | Repeated anomalous telemetry bursts | Active signal updated idempotently without duplicate signal spam | **PASSED** |
| **M18.10** | LISA Grounding | `app.services.ai.tools` | AI tool queries for telemetry, health, diagnostics | Structured evidence returned; zero hallucination | **PASSED** |
| **M18.11** | Stress & Concurrency | Ingest API & Database | 30+ events burst across 3 UAVs | Latency < 5.0s, 0 dropped events, duplicate replay returns 100% duplicate status | **PASSED** |
| **M18.12** | Staleness & Recovery | `TelemetryFreshnessPolicy` | 8-day telemetry gap -> fresh packet arrival | Status transitions to `STALE` with freshness warning -> restores to `ACTIVE` on fresh packet | **PASSED** |
| **M18.13** | End-to-End Traceability | Complete Lineage | 10-link bidirectional traversal | Signal -> Prognostic -> Diagnostic -> Finding -> Evidence -> Feature -> Reading -> Log -> Asset -> Flight | **PASSED** |

---

## 3. Concurrency, Performance & Stress Boundaries

- **Throughput Capability:** 30 multi-sensor telemetry packets processed in < 4.2 seconds on single-instance PostgreSQL.
- **Idempotency Guarantee:** 100% deduplication of repeated batches via `(organization_id, source_system, source_event_id)` key.
- **Tenant Isolation:** Enforced at ORM, schema, service, and API layers using `TenantScopedMixin` and `organization_id` session filtering.
