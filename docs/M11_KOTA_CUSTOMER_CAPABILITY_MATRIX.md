# KOTA AEROSPACE — M11 CAPABILITY MATRIX & GAP ANALYSIS

## Prospect: Horizon Regional Air & Drone Mobility ("Horizon Air")

---

## 1. Capability Mapping Matrix

| Customer Capability Need | Horizon Current Tool | KOTA Architecture Module | Status | Required Implementation Action |
|:---|:---|:---|:---|:---|
| **Multi-Asset Fleet Inventory** | Excel Sheets | `AssetService`, `AircraftService`, `DroneService` | **SUPPORTED** | Configure tenant assets with registration, serials, and equipment configurations. |
| **Historical Data Onboarding** | Disparate Excel Logs | `ImportJobService`, `FlightService` Baseline Engine | **DATA MIGRATION** | Map customer Excel columns via M5 Import Center; establish historical baselines. |
| **Electronic Flight Logging** | Paper Tech Logs | `FlightService.record_flight` | **SUPPORTED** | Standard web UI workflow for flight and mission entry with automatic meter propagation. |
| **Work Orders & Task Cards** | Paper Task Cards | `MaintenanceService.create_work_order` | **SUPPORTED** | Digital work order creation, task execution, part replacement, and sign-offs. |
| **Defect Findings & Snags** | WhatsApp / Loose Files | `FindingService.create_finding` | **SUPPORTED** | Finding logging with severity categorization (`CRITICAL`, `MAJOR`, `MINOR`) and WO links. |
| **Evidence & Certificate Storage**| Google Drive Folders | `EvidenceService`, S3 Multi-Tenant Store | **SUPPORTED** | Cryptographic SHA-256 evidence attachment to assets, work orders, and findings. |
| **Tri-State Compliance Engine** | Manual Paper Spreadsheets| `ComplianceService` | **SUPPORTED** | Airworthiness Directive & Service Bulletin tracking preserving `UNKNOWN` state. |
| **5-Dimension Readiness Gating**| Verbal Radio Briefings | `AssetService.get_asset_readiness` | **SUPPORTED** | Multi-dimensional readiness gating (`OPERATIONAL`, `MAINTENANCE`, `COMPLIANCE`, etc.). |
| **Proactive Failure Signals** | Reactive Spreadsheets | `ProactiveIntelligenceService` (M7 Engine) | **SUPPORTED** | Automated proactive alerts for engine cycles, battery wear, and recurring snags. |
| **Conversational Copilot (LISA)**| None | `LISA Tool Registry` (`ai/tools.py`) | **SUPPORTED** | Grounded, tenant-isolated natural language querying across live operational data. |
| **Decision Support Guardrails** | Manual Meetings | Platform Governance Architecture | **SUPPORTED** | Enforce human-in-the-loop authorization for all releases and compliance sign-offs. |
| **Transactional Email Gateway** | Manual Account Sharing | `EmailService` (SMTP) | **CONFIGURATION** | Configure production SMTP credentials (`SMTP_HOST`, `SMTP_PORT`, `SMTP_PASSWORD`). |
| **DJI FlightHub 2 Telemetry API**| DJI FlightHub 2 Web | External Ingestion Adapter | **INTEGRATION** | Scope external REST webhook connector for M13 roadmap; use Import Center in M12. |
| **PDF Tech Log & Form 1 Export**| Pre-printed paper forms | Frontend Export Module | **MINOR ENHANCEMENT** | Implement print-optimized PDF generation for work orders and tech log pages. |
| **Corporate Azure AD SSO** | Username/Password | Authentication / OIDC Layer | **MINOR ENHANCEMENT** | Configure SAML/OIDC enterprise connection in future platform iteration. |

---

## 2. Gap Analysis & Impact Assessment

| Identified Gap | Business Impact | Technical Complexity | Customer Dependency | Regulatory Impact | Effort Estimate | Recommended Phase |
|:---|:---|:---|:---|:---|:---|:---|
| **Production Outbound SMTP** | **High** (Blocks automated user self-invite & self-reset) | **Low** (Configuration only) | **Yes** (Customer must supply SMTP gateway) | Low | 0.5 Days | **M12 Production Activation** |
| **Printable Form 1 / Tech Log PDF** | **Medium** (Required for civil aviation paper backups) | **Low** (Client-side template rendering) | **No** | Medium | 1.5 Days | **M12 Customer Go-Live** |
| **DJI FlightHub 2 Automated Ingestion** | **Low** (Import Center provides full CSV/Excel workaround) | **Medium** (Webhook listener & parser) | **Yes** (DJI API Key) | Low | 4.0 Days | **M13 Enhancement Roadmap** |
| **Azure AD SSO (OIDC/SAML)** | **Low** (Standard JWT authentication functions cleanly) | **Medium** (Enterprise Auth integration) | **Yes** (Azure Tenant ID) | Low | 3.0 Days | **M13 Enhancement Roadmap** |

---

## 3. Configuration vs Customization Governance

1. **Architecture Preservation Principle**: KOTA will **NOT** create a bespoke software branch or custom database schema for Horizon Air. All requirements are satisfied through standard tenant configuration, existing domain services, and reusable frontend enhancements.
2. **Standard Role Alignment**: Horizon Air job titles are mapped directly to KOTA standard platform roles (`ORG_ADMIN`, `CAMO_MANAGER`, `MAINTENANCE_ENGINEER`, `QUALITY_MANAGER`, `VIEWER`).
3. **Data Integrity Standard**: Ingesting Horizon Air's 3-year historical flight records will strictly utilize the M5 Import Center pipeline to guarantee auditability and zero double counting.
