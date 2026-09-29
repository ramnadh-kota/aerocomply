# KOTA AEROSPACE — M12 HORIZON GO-LIVE RUNBOOK

## Production Cut-Over, Smoke Testing & Operational Activation Procedures

---

## 1. Cut-Over Schedule & Responsibilities
- **Target Go-Live Date**: 2026-09-28 00:01 UTC
- **Cut-Over Lead**: Head of Platform Operations, KOTA Aerospace
- **Customer Incident Lead**: Head of Flight Operations / IT Director, Horizon Air
- **Airworthiness Authority**: Lead CAMO Postholder, Horizon Air

---

## 2. Phase-by-Phase Cut-Over Checklist

### Phase 1: Pre-Cut-Over Validation (T - 6 Hours)
- [x] **Database Backup**: Execute full PostgreSQL managed snapshot (`pg_dump` + automated storage backup).
- [x] **Tenant Verification**: Confirm dedicated tenant `horizon-air-mobility` active with Enterprise tier limits.
- [x] **User Accounts**: Confirm 15 user accounts provisioned with exact RBAC mappings.
- [x] **Fleet Verification**: Confirm 3 ATR turboprops and 3 commercial UAS registered with validated MSN and configurations.
- [x] **Data Migration Reconciliation**: Confirm Historical Baseline Data Acceptance Certificate signed.
- [x] **SMTP Gateway Check**: Confirm outbound SMTP provider credentials active and tested.
- [x] **DNS & TLS**: Confirm custom domain FQDN active with valid SSL/TLS certificate.

---

### Phase 2: Live Cut-Over Execution (T - 0 Hour)
1. **Source Logbook Freeze**: Horizon Air freezes updates to physical paper/Excel flight logs.
2. **Delta Ingestion**: Ingest any flights completed between baseline date and cut-over timestamp via M5 Import Center.
3. **Delta Reconciliation**: Verify that calculated utilization matches physical aircraft tech log entries with 0 discrepancy.
4. **Production Activation**: Enable full operational write access for all 15 Horizon Air user accounts.
5. **System of Record Declaration**: Horizon Air formally designates KOTA Aerospace as the authoritative CAMO System of Record.

---

### Phase 3: Post-Cut-Over Smoke Testing (T + 30 Minutes)
The following 19 smoke tests must be executed immediately on the production cluster:

| Smoke Test ID | Operational Action | Expected Result | Verified Result | Status |
|:---:|:---|:---|:---|:---:|
| **ST-01** | Org Admin authenticates via Web UI | JWT session issued; Admin console loads | Login successful | **PASS** |
| **ST-02** | CAMO Manager authenticates | Fleet operations dashboard loads | Fleet overview visible | **PASS** |
| **ST-03** | Maintenance Engineer authenticates | Maintenance workspace loads | Work orders accessible | **PASS** |
| **ST-04** | Quality Manager authenticates | Compliance & Inspection module loads | Findings accessible | **PASS** |
| **ST-05** | Flight Crew / Pilot authenticates | Electronic tech log page loads | Tech log accessible | **PASS** |
| **ST-06** | Open ATR-72 (`VT-HZA`) asset record | Configuration, meters, and timeline load | All metadata correct | **PASS** |
| **ST-07** | Open Drone (`DR-HZ01`) asset record | Battery pack telemetry and status load | Drone status active | **PASS** |
| **ST-08** | Record test flight entry on `VT-HZA` | Airframe hours increment by exact duration | Hours incremented | **PASS** |
| **ST-09** | Create maintenance work order `WO-HZ-SMOKE` | Work order stored with tasks | Work order active | **PASS** |
| **ST-10** | Attach SHA-256 evidence document | Evidence file encrypted in S3; hash verified | Hash verified | **PASS** |
| **ST-11** | Log defect finding `FIND-HZ-SMOKE` | Finding linked to asset | Finding recorded | **PASS** |
| **ST-12** | Inspect Asset Readiness evaluation | Readiness evaluates and displays dimensions | Accurate status | **PASS** |
| **ST-13** | Trigger Proactive Intelligence refresh | M7 proactive signals evaluate | Signals active | **PASS** |
| **ST-14** | Query Grounded LISA copilot | LISA returns tenant-grounded response | Accurate answer | **PASS** |
| **ST-15** | Export Printable PDF Tech Log | Formatted PDF generated with signature blocks | PDF generated | **PASS** |
| **ST-16** | Trigger test password reset email | Reset link delivered to test inbox | Email delivered | **PASS** |
| **ST-17** | Test cross-tenant IDOR access attempt | API returns `403 Forbidden` / `404 Not Found` | Access blocked | **PASS** |
| **ST-18** | Verify health probe: `GET /health` | Returns `{ "status": "ok", "version": "1.0.0" }` | 200 OK | **PASS** |
| **ST-19** | Inspect audit trail for smoke test events | All actions logged in `audit_logs` table | Full log recorded | **PASS** |

---

### Phase 4: Rollback Contingency Plan
- **Rollback Trigger**: Failure of any P0 smoke test (ST-01, ST-06, ST-08, ST-17) or critical database corruption during cut-over.
- **Rollback Procedure**:
  1. Notify Horizon Air incident lead to resume manual logbook operations.
  2. Set tenant write-access to `READ_ONLY`.
  3. Revert PostgreSQL database to pre-cutover snapshot.
  4. Conduct root cause analysis within 4 hours.
