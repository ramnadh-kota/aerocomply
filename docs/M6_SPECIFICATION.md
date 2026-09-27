# KOTA AEROSPACE M6 — OPERATIONAL COMMAND CENTER + CUSTOMER PILOT READINESS SPECIFICATION

## 1. Executive Summary

Milestone 6 (M6) elevates KOTA Aerospace from a data-ingestion and flight-recording platform (established in M5) into the customer's **daily operational command center and fleet control system**.

M6 enables commercial airlines, defense operators, UAV/drone fleet managers, rotorcraft operators, and advanced air mobility (eVTOL) providers to execute daily aerospace operations, track fleet readiness, prioritize maintenance and findings, maintain compliance grounding, and leverage deterministic aerospace intelligence without returning to disconnected spreadsheets.

---

## 2. Core Capabilities Implemented in M6

### M6-A: Operational Command Center (`/dashboard`)
- **Fleet Health Matrix**: Live distribution of fleet operational states (Ready, Restricted, Maintenance Due, Grounded, Awaiting Parts, Unknown) across multi-asset types (Fixed-Wing Aircraft, Drone UAVs, Helicopters, eVTOL).
- **Live Operational Activity Ribbon**: Tracks flights today, flights this week, active missions, fleet total flight hours, and cycle counts incorporating historical carried-in baselines.
- **Attention Required Priority Queue**: Ranked operational attention items (P0/Critical, High, Medium, Low) derived from open findings, overdue work orders, pending inspection intervals, and battery threshold alerts.
- **Daily Operational Briefing**: Plain-language, grounded briefing synthesized directly from live tenant assets, maintenance records, and regulatory obligations.

### M6-B: Multi-Asset Fleet Operations View (`/assets`)
- Comprehensive asset inventory unifying `Aircraft` and `Drone` entities into a standardized aerospace operational table.
- Search, filter by asset type, status, readiness level, and operational state.
- Traceable metrics: Total flight hours, cycle counts, last flight date, active blocker count, and immediate recommended action.
- Direct navigation into dedicated asset workspaces (`/aircraft/[id]`, `/drones/[id]`).

### M6-C & M6-D: Unified Operational Timeline (`GET /api/v1/control-center/timeline`)
- Aggregates chronological events across 7 operational event domains:
  1. Flights & Sorties
  2. Missions & Deployments
  3. Work Orders & Maintenance
  4. Inspection Requirements & Releases
  5. Technical Findings & Defects
  6. Component Installations & Removals
  7. Historical Baseline Accounting Events
- Filterable by asset ID and event category.

### M6-E to M6-H: Maintenance, Readiness, & Evidence Traceability
- Direct drill-down from alert → work order → asset → finding → evidence record.
- Preserved Kleene 3-valued compliance evaluation (Compliant, Non-Compliant, Unknown).
- Deterministic readiness explanation without decorative or fabricated scores.

### M6-I & M6-J: Grounded LISA Intelligence Integration
- LISA consumes live operational state contracts without bypassing domain validation.
- Every recommendation links directly to underlying work orders, inspection gates, or airworthiness directives.

---

## 3. Data Contracts & Architecture

```text
                           KOTA USER / OPERATOR
                                    │
                                    ▼
                      ┌───────────────────────────┐
                      │ OPERATIONAL COMMAND CENTER │
                      │       (/dashboard)        │
                      └─────────────┬─────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
   FLEET HEALTH            OPERATIONAL ACTIVITY      ATTENTION QUEUE
   - Total Assets          - Flights Today / Week    - Overdue Work Orders
   - Ready / Restricted    - Flight Hours & Cycles   - Open Findings
   - Grounded / Maint Due  - Active Missions         - Battery Limit Alerts
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
                        ASSET OPERATIONS WORKSPACE
                                (/assets)
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
   OPERATIONAL LOG          MAINTENANCE CONTROL      UNIFIED TIMELINE
   - Flight Sorties         - Work Orders / Tasks    - Chronological Stream
   - Mission Tasks          - Inspections / Findings - Multi-Source Events
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                                    ▼
                        COMPLIANCE & READINESS
                                    │
                                    ▼
                          GROUNDED INTELLIGENCE
                                 (LISA)
                                    │
                                    ▼
                          OPERATIONAL DECISION
```

---

## 4. API Surface

| Endpoint | Method | Role / Permission | Description |
|---|---|---|---|
| `/api/v1/control-center/summary` | GET | `AIRCRAFT_READ`, `DRONE_READ` | Fleet health, activity, attention items, daily brief |
| `/api/v1/control-center/fleet-operations` | GET | `AIRCRAFT_READ`, `DRONE_READ` | Multi-asset operational workspace rows |
| `/api/v1/control-center/timeline` | GET | `AIRCRAFT_READ`, `COMPLIANCE_ASSESS` | Unified chronological operational event stream |
| `/api/v1/control-center/fleet` | GET | `AIRCRAFT_READ` | Protected legacy aircraft control view |

---

## 5. Customer Pilot Readiness & Verification

All 14 customer operational UAT scenarios have been implemented and verified via automated integration tests:
1. Fleet Overview Inspection
2. Asset Workspace Deep Dive
3. Flight History Traceability
4. Operational Flight Logging
5. Utilization & Baseline Accumulation
6. Maintenance State Transition
7. Inspection Gate Due Detection
8. Technical Finding Logging
9. Compliance Evidence Attachment
10. Regulatory Compliance Impact Assessment
11. Readiness State Restriction (Kleene Logic)
12. Command Center Dynamic Reflection
13. LISA Decision & Root-Cause Explanation
14. Corrective Action & Blocker Resolution
