# KOTA AEROSPACE — M11 CUSTOMER SOLUTION FIT ARCHITECTURE

## Technical Solution Blueprint for Horizon Regional Air & Drone Mobility

---

## 1. Executive & Architectural Context

This document establishes the technical solution fit for **Horizon Regional Air & Drone Mobility ("Horizon Air")**, a hybrid aerospace operator operating regional fixed-wing turboprop aircraft (ATR-72-600 / ATR-42-600) alongside commercial heavy-lift logistics drones (DJI FlyCart 30 / Harris Aerial Hx8).

The objective is to map Horizon Air's multi-base, multi-asset operations directly onto KOTA Aerospace's existing, verified modular architecture (M5–M10) without creating ad-hoc customer forks or unmaintainable custom code.

---

## 2. Customer System Topology & KOTA Multi-Tenant Fit

```
HORIZON AIR MOBILITY (PROSPECT TENANT)
│
├── Organization: Horizon Regional Air & Drone Mobility (Slug: `horizon-air-mobility`)
├── Subscription Tier: ENTERPRISE (Full Entitlements: Fleet, Operations, Maintenance, Compliance, LISA, Proactive Intelligence)
│
├── Bases & Facilities:
│   ├── Base 1 (Primary Hub / Main Maintenance Hangar): Regional Airport Hub (ICAO: VOHY)
│   ├── Base 2 (Cargo Vertiport & Drone Logistics Depot): Coastal Regional Strip
│   └── Base 3 (Remote Inspection Outstation): Industrial Corridor Logistics Base
│
├── Fleet Assets:
│   ├── Fixed-Wing Aircraft:
│   │   ├── VT-HZA (ATR-72-600, MSN 1450) — Regional Passenger / Feeder Cargo
│   │   ├── VT-HZB (ATR-72-600, MSN 1512) — Regional Scheduled Transport
│   │   └── VT-HZC (ATR-42-600, MSN 1205) — Regional Quick-Change Cargo
│   └── Commercial Heavy-Lift UAS:
│   │   ├── DR-HZ01 (DJI FlyCart 30) — Medical & Priority Cargo Delivery
│   │   ├── DR-HZ02 (DJI FlyCart 30) — Heavy Feeder Logistics
│   │   └── DR-HZ03 (Harris Aerial Hx8) — Linear Infrastructure Inspection & Survey
│
├── Component & Battery Pool:
│   ├── Turboprop Engines (PW127M): Position-tracked with flight hour / cycle tracking
│   ├── Propeller Assemblies (Hamilton 568F): Blade inspection & overhaul interval tracking
│   └── Intelligent Drone Battery Packs (Smart TB30 / Solid-State LiPo): Cycle & internal resistance tracking
│
└── KOTA Platform Layer (Reused Core Services):
    ├── M5 Import Center & Authoritative Historical Baseline Engine
    ├── M6 Operational Command Center & Real-Time Technical Log
    ├── M7 Proactive Aerospace Intelligence (Threshold, Battery, Finding & Compliance Engines)
    ├── Grounded LISA Conversational Copilot (Strict Tenant Row-Level Scoping)
    └── Immutable Cryptographic Evidence & Audit Trail
```

---

## 3. Core Domain Mapping & Service Reuse

| Customer Operational Domain | Horizon Current Tool | KOTA Target Service | Architecture / Reuse Pattern |
|:---|:---|:---|:---|
| **Fleet Asset Management** | Excel Asset Tracker | `asset_service.py`, `aircraft_service.py`, `drone_service.py` | Native support for multi-type fleets with MSN, serials, and configuration trees. |
| **Historical Data Migration** | Disparate Excel Sheets | `import_job_service.py`, `flight_service.create_asset_baseline` | M5 Import Center staging pipeline with carry-in baseline accounting. |
| **Flight & Mission Logging** | Paper Tech Logs & Sheets | `flight_service.record_flight`, `mission_service.py` | Direct technical log recording with automatic meter propagation. |
| **Maintenance Work Orders** | Paper Task Cards & Folders | `maintenance_service.py`, `work_order_service.py` | Digital work orders, scheduled tasks, component replacements, release to service. |
| **Defect Findings & Quality** | WhatsApp / Excel Logs | `finding_service.py`, `inspection_service.py` | Structured finding classification (`CRITICAL`, `MAJOR`, `MINOR`) with corrective action links. |
| **Evidence & Regulatory Files** | Google Drive / Scans | `evidence_service.py` | Multi-tenant S3-backed storage with SHA-256 cryptographic hashing and asset linking. |
| **Regulatory Compliance** | Manual Regulatory Checklists| `compliance_service.py` | Tri-state compliance engine (`COMPLIANT`, `NON_COMPLIANT`, `REVIEW_REQUIRED`, `UNKNOWN`). |
| **Airworthiness Readiness** | Verbal / Whiteboard Status | `asset_service.get_asset_readiness` | 5-dimensional real-time readiness gating (`OPERATIONAL`, `MAINTENANCE`, `COMPLIANCE`, `DEPLOYMENT`, `RELEASE`). |
| **Fleet Decision Support** | Manual Engineering Reviews | `proactive_intelligence_service.py`, `ai/tools.py` | M7 automated proactive signals and grounded LISA natural language queries. |

---

## 4. Invariant & Governance Rules

1. **Zero Database Bypassing**: Horizon Air data must enter KOTA exclusively via authenticated API endpoints or the M5 Import Center.
2. **Strict Baseline Accounting**: Current utilization is calculated as $\text{Baseline Hours/Cycles} + \sum \text{Post-Baseline Flights}$.
3. **No Unauthenticated State Mutations**: Operational actions (Maintenance Release, Compliance Sign-Off, Work Order Closure) require authenticated human authorization.
4. **Tenant Data Partitioning**: All database queries and LISA tool invocations are filtered strictly by `organization_id`.
