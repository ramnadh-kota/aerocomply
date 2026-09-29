# KOTA AEROSPACE — M11 CUSTOMER IMPLEMENTATION PLAN

## Implementation Blueprint for Horizon Regional Air & Drone Mobility ("Horizon Air")

---

## 1. 10-Phase Implementation Roadmap (Targeting M12 Go-Live)

| Phase | Title | Lead Owner | Dependencies | Core Deliverables | Acceptance Gate Criteria |
|:---|:---|:---|:---|:---|:---|
| **Phase 1** | Dedicated Tenant Provisioning | Platform Lead | Commercial Agreement | Organization (`horizon-air-mobility`), Enterprise Subscription, S3 storage bucket, TLS domain binding. | Organization active, isolated, and accessible via customer FQDN. |
| **Phase 2** | User & Role Provisioning | Horizon IT Lead | Phase 1 | Provision 1 Org Admin, 2 CAMO Managers, 4 Maintenance Engineers, 2 Quality Managers, 6 Flight Crew/Pilots. | All 15 users authenticated with verified RBAC permission boundaries. |
| **Phase 3** | Fleet Asset Onboarding | CAMO Postholder | Phase 2 | Register 3 ATR turboprops (`VT-HZA`, `VT-HZB`, `VT-HZC`) and 3 cargo drones (`DR-HZ01`, `DR-HZ02`, `DR-HZ03`) with configurations. | Assets visible in Command Center with correct MSN, serials, and configurations. |
| **Phase 4** | Historical Data Migration | Data Specialist | Phase 3, Sample Data | Ingest 3-year historical flight records, LLP meters, component tracking, and inspection logs via M5 Import Center. | 100% rows validated; error rate 0.0%; zero raw SQL insertion. |
| **Phase 5** | Baseline Reconciliation | Lead CAMO / Quality | Phase 4 | Establish authoritative carry-in baselines; verify calculation formula: $\text{Utilization} = \text{Baseline} + \text{Post-Baseline Flights}$. | Source utilization matches KOTA calculated utilization with 0 discrepancy. |
| **Phase 6** | Operational & SMTP Config | DevOps Lead | Phase 1, Phase 5 | Configure outbound SMTP email gateway, notification rules, maintenance interval thresholds, and inspection checklists. | User invitation tokens and reset emails successfully delivered to live inboxes. |
| **Phase 7** | Customer UAT Execution | Quality Manager | Phase 6 | Execute comprehensive 25-scenario UAT suite covering Operations, Maintenance, Quality, Compliance, Intelligence, and LISA. | 25/25 UAT scenarios marked PASS with signed customer approval. |
| **Phase 8** | Operational Role Training | Training Lead | Phase 7 | Conduct role-based operational training workshops for Flight Ops, Engineering, Quality, and Executive teams. | 100% of core users complete workflow simulation training. |
| **Phase 9** | Production Activation (M12) | Steering Committee | Phase 7, Phase 8 | Switch KOTA from parallel staging to primary system of record; establish cut-over flight log entry. | First live revenue flight and work order recorded directly in KOTA. |
| **Phase 10**| Hypercare & Post-Go-Live Support | Customer Success | Phase 9 | 30-day daily operational monitoring, telemetry health reviews, weekly feedback triage, and SLA compliance tracking. | Zero P0/P1 incidents during 30-day hypercare window. |

---

## 2. Technical & Commercial Scope Summary

### A. Included in Core Implementation Scope
1. **Platform Licensing**: Enterprise Tier deployment for 1 Dedicated Organization, up to 25 Active Users, and up to 15 Registered Assets (Turboprops & Commercial UAS).
2. **Data Migration Scope**: Up to 50,000 historical flight records, 500 component records, and 200 regulatory compliance items migrated via M5 Import Center.
3. **Core Modules Included**:
   - Multi-Asset Fleet Foundation & Configuration
   - Real-Time Flight & Mission Operations Log
   - Digital Maintenance Work Orders, Tasks & Component Swap-Outs
   - Quality Inspections, Defect Findings & Corrective Actions
   - Tri-State Regulatory Compliance Engine & Airworthiness Directives
   - 5-Dimensional Asset Readiness Gating
   - M7 Proactive Aerospace Intelligence Engine
   - Grounded LISA Conversational Copilot
   - Immutable Cryptographic Audit Trail (SHA-256)
4. **Training & Enablement**: 4 structured role-based training sessions with interactive user guides and video walk-throughs.
5. **Support & SLA**:
   - P0 (Critical Outage): 15-minute response, 2-hour temporary containment target.
   - P1 (Major Workflow Blocked): 1-hour response, 8-hour remediation target.
   - P2 (Degraded Feature): 4-hour response.
   - P3 (Minor Request): Next release cycle.

### B. Excluded from Core Scope (Roadmap M13+)
- Automated direct hardware IoT telemetry streaming via DJI FlightHub 2 webhook API (Manual CSV/Excel import via Import Center provided).
- Corporate Single Sign-On (Azure AD / Okta SAML 2.0 / OIDC enterprise connector).
- Custom integration with third-party ERP accounting systems (e.g. SAP / NetSuite).

---

## 3. Customer Acceptance & Sign-Off Criteria

The customer implementation is formally accepted upon satisfying the following 5 criteria:
1. **Data Accuracy**: Historical flight hours and cycles for all 6 fleet assets match source records exactly with zero double counting.
2. **Workflow Completion**: A complete operational cycle (Flight Log $\rightarrow$ Snag Finding $\rightarrow$ Work Order $\rightarrow$ Task Execution $\rightarrow$ Evidence Attachment $\rightarrow$ Release to Service $\rightarrow$ Readiness Update) is executed successfully by customer staff.
3. **Regulatory Safety**: Civil aviation compliance assessments correctly reflect regulatory state and preserve `UNKNOWN` where evidence is absent.
4. **Intelligence Grounding**: LISA accurately answers fleet status, maintenance due dates, and readiness blocker queries using customer data only.
5. **Security & Isolation**: Complete tenant isolation verified with zero cross-tenant visibility.
