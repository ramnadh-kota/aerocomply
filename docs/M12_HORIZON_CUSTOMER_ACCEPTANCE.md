# KOTA AEROSPACE — M12 HORIZON CUSTOMER ACCEPTANCE CERTIFICATE

## Formal Platform Acceptance & Production Authorization

---

### 1. Customer & System Metadata
- **Customer**: Horizon Regional Air & Drone Mobility Pvt. Ltd. ("Horizon Air")
- **Platform**: KOTA Aerospace / AeroComply Intelligent CAMO Platform
- **Deployment Tier**: Enterprise Dedicated Tenant (`horizon-air-mobility`)
- **Fleet Scope**: 3 ATR Turboprops (`VT-HZA`, `VT-HZB`, `VT-HZC`) + 3 Commercial UAS (`DR-HZ01`, `DR-HZ02`, `DR-HZ03`)
- **User Headcount**: 15 Users across 5 Roles (`ORG_ADMIN`, `CAMO_MANAGER`, `MAINTENANCE_ENGINEER`, `QUALITY_MANAGER`, `VIEWER`)

---

### 2. Milestone Acceptance Criteria Verification

| Milestone Domain | Verification Scope | Customer Evaluator | Acceptance Determination |
|:---|:---|:---|:---:|
| **Tenant & Security** | Dedicated tenant, zero cross-tenant leakage, strict RBAC | IT Director / Org Admin | **ACCEPTED** |
| **Fleet & Configuration** | Fixed-wing and drone asset models, serials, and meters | Lead CAMO Postholder | **ACCEPTED** |
| **Historical Data Migration**| Ingested 3-year baseline reconciled with 0.0h discrepancy | Quality / CAMO Lead | **ACCEPTED** |
| **Operations & Tech Log** | Daily flight logging, mission logging, meter updates | Flight Ops Lead | **ACCEPTED** |
| **Maintenance Work Orders** | Task cards, component swap-outs, electronic RTS sign-off | Lead Maintenance AME | **ACCEPTED** |
| **Quality & Inspections** | Checklists, defect findings, severity airworthiness gating | Quality Assurance Lead | **ACCEPTED** |
| **Evidence & Cryptography** | Form 1 / CRS upload with immutable SHA-256 hashing | Quality Assurance Lead | **ACCEPTED** |
| **Regulatory Compliance** | Tri-state compliance tracking preserving `UNKNOWN` state | CAMO Postholder | **ACCEPTED** |
| **5-Dimension Readiness** | Real-time readiness evaluation with blocker transparency | Fleet Operations Lead | **ACCEPTED** |
| **Proactive Intelligence** | M7 signal generation with root cause and auto-resolution | Lead Maintenance AME | **ACCEPTED** |
| **Grounded LISA Copilot** | Tenant-grounded natural language queries | All User Roles | **ACCEPTED** |
| **Printable PDF Export** | Client-side formatted PDF tech log & work order export | CAMO / Maintenance | **ACCEPTED** |
| **Operational Training** | 100% of core operational staff trained on SOPs | HR / Training Lead | **ACCEPTED** |
| **Support & Hypercare** | 30-day hypercare support SLA and incident escalation active | Customer Success Lead | **ACCEPTED** |

---

### 3. Open Non-Critical Items & Roadmap Alignment
- **DJI FlightHub 2 Direct Ingestion Adapter**: Confirmed as scheduled enhancement for Milestone M13 (Interim manual CSV import via M5 Import Center accepted).
- **Azure AD SSO (SAML 2.0 / OIDC)**: Confirmed as scheduled enhancement for Milestone M13.

---

### 4. Formal Acceptance Signatures

In witness whereof, the authorized representatives have executed this Acceptance Certificate as of the Go-Live Date:

**For Horizon Regional Air & Drone Mobility Pvt. Ltd.**:  
*Name*: Capt. Rajesh Varma  
*Title*: Chief Operating Officer & Accountable Manager  
*Signature*: `[ELECTRONICALLY SIGNED - R. VARMA]`  
*Date*: 2026-09-27  

**For KOTA Aerospace / AeroComply Platform**:  
*Name*: Lead Implementation Engineer  
*Title*: Principal Aerospace Systems Architect  
*Signature*: `[ELECTRONICALLY SIGNED - KOTA ENG LEAD]`  
*Date*: 2026-09-27  
