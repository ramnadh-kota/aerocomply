# M16 Edge Platform Architecture & Productization

## 1. Executive Summary
The KOTA Edge Platform transforms laboratory-grade physical sensor acquisition (M15) into a repeatable, multi-tenant enterprise edge management layer. It governs the operational lifecycle of edge gateways and sensor nodes deployed on regional passenger aircraft, cargo turboprops, and heavy-lift UAS fleets.

---

## 2. Architectural Hierarchy & Separation of Concerns

```text
                  ┌──────────────────────────────────────────────┐
                  │                 KOTA CLOUD                   │
                  │                                              │
                  │  - Device Provisioning & Revocation Control  │
                  │  - Versioned Configuration Authority         │
                  │  - Canonical Telemetry Ingestion (M13)       │
                  │  - Authoritative PostgreSQL Database         │
                  │  - Grounded LISA & M7 Intelligence Engines   │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼ (TLS 1.3 REST / Signed Envelopes)
                  ┌──────────────────────────────────────────────┐
                  │           KOTA EDGE GATEWAY DAEMON           │
                  │                                              │
                  │  - Physical Acquisition Engine               │
                  │  - Monotonic Sequence & HMAC Signer          │
                  │  - Local Persistent FIFO Resilience Buffer   │
                  │  - Canonical Heartbeat & Observability Hub   │
                  │  - Safe Command Execution Engine             │
                  └──────────────────────┬───────────────────────┘
                                         │
                        ┌────────────────┴────────────────┐
                        │        PHYSICAL SENSORS         │
                        │                                 │
                        │  - Priority 1: ADXL345 (Vib)    │
                        │  - Priority 2: PT100 (Temp)     │
                        │  - Priority 3: Pressure Xducer  │
                        │  - Priority 4: INA226 (Elec)    │
                        └─────────────────────────────────┘
```

---

## 3. Core Boundaries & Ownership
- **TECH-2 / ANTIGRAVITY:** Owns the edge daemon, sensor adapters, device provisioning, configuration versioning, local resilience buffering, canonical telemetry envelopes, and technical observability.
- **TECH-1 / CLAUDE:** Consumes ingested telemetry for HUMS diagnostics, baseline drift, prognostics, cross-asset pattern clustering, and M7 proactive signals.
- **DEVELOPER-1:** Integrates intelligence into operational work orders, release readiness gates, compliance tracking, and MRO action.
