# M14 — Commercial Platform Architecture & Multi-Customer Scale

## 1. Executive Summary & Objective

**Milestone**: M14 Commercialization Platform & Multi-Customer Scale  
**Platform**: KOTA Aerospace / AeroComply  
**Baseline**: Certified RC-1 (`v0.1.0-rc1`, Alembic `0058`) → Production Commercialization (`0059`)  

### Core Problem Solved
Transforming KOTA Aerospace from a single customer-operating deployment (`horizon-air-mobility`) into a **multi-customer, repeatable, enterprise-grade SaaS and telemetry platform** capable of onboarding Customer #2, #3, and beyond with **ZERO customer-specific source code changes**.

---

## 2. Multi-Tenant Architectural Topology

```text
                    KOTA AEROSPACE
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
   OPERATIONS        INTELLIGENCE          HUMS
       │                  │                  │
   Fleet/MRO          M7 / LISA          H0-H5
   Compliance         Decisions          Telemetry
   Readiness          Signals            Health
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                 COMMERCIAL PLATFORM
                          │
       ┌──────────────────┼───────────────────┐
       │                  │                   │
   ENTITLEMENTS       ONBOARDING          USAGE/METERING
       │                  │                   │
   PlanLimits        State Machine       Quotas / Ceilings
   Overrides         Zero-Code Factory   Telemetry Streams
       │                  │                   │
       └──────────────────┼───────────────────┘
                          │
                    ENTERPRISE LAYER
                          │
                SSO / RBAC / AUDIT / EXPORTS
                          │
                    EDGE / HARDWARE
                          │
          DEVICE ENVELOPE / GATEWAY BUFFER
```

---

## 3. Commercial Entitlement & Feature Model

### Pre-packaged Commercial Editions

1. **KOTA Operations**:
   - Fleet Management (Aircraft, UAVs, eVTOL)
   - Flight Operations & Baseline Accounting
   - Maintenance & Work Order Execution
   - Airworthiness Compliance & Regulatory Obligations
   - Dispatch Operational Readiness

2. **KOTA Intelligence**:
   - M7 Proactive Intelligence Signals (P0–P3)
   - LISA Grounded AI Copilot
   - Decision Intelligence 2.0 (Simulation & Trade-off Modeling)
   - Cross-Asset Anomaly & Degradation Correlation

3. **KOTA HUMS**:
   - Time-Domain & Frequency-Domain Feature Engineering (RMS, FFT, Kurtosis, Crest Factor)
   - Dynamic Telemetry Freshness Hierarchy
   - Sensor Exceedances & Baseline Engine
   - Prognostics & Remaining Useful Life (RUL)

4. **KOTA Enterprise**:
   - Microsoft Entra ID (OIDC SSO)
   - Advanced 8-Role RBAC & Four-Eyes Approval Workflows
   - Cryptographic Audit Trail & Forensic Export
   - Dedicated Retention Policies & Hypercare Monitoring

---

## 4. Edge Hardware & Gateway Telemetry Integration

- **Device Registration (`edge_devices`)**: Hardware serials, gateway hubs, firmware versions, and last heartbeat timestamps.
- **Canonical Envelope (`DeviceTelemetryEnvelope`)**: Structured ingestion format decoupling physical field sensors from KOTA domain models.
- **Offline Buffering & Deduplication**: Monotonic sequence numbers and timestamp tracking ensure seamless reconnect and replay without double counting.
