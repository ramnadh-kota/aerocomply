# KOTA AEROSPACE — M12 HORIZON OPERATIONAL SOP

## Standard Operating Procedures for Daily Aerospace Operations & Airworthiness Management

---

## 1. Scope & Applicability
This Standard Operating Procedure (SOP) governs the daily use of the KOTA Aerospace / AeroComply Intelligent CAMO Platform by all flight operations, maintenance, quality, and management personnel at **Horizon Regional Air & Drone Mobility Pvt. Ltd.**

---

## 2. Daily Operational Protocols by Domain

### SOP-01: Flight & Mission Logging (Flight Operations)
1. **Timing**: Within 30 minutes of engine shutdown / rotor stop.
2. **Actor**: Commercial Pilot-in-Command (Fixed-Wing) or Remote Pilot-in-Command (UAS).
3. **Execution**:
   - Navigate to **Operations $\rightarrow$ New Flight / Mission Log**.
   - Input departure airport/vertiport, arrival point, off-block/on-block times, flight duration (minutes), cycles/landings, and fuel/battery percentage consumed.
   - If technical discrepancies occurred, check **"Log Technical Defect"** to link an immediate Finding.
   - Click **"Submit Flight Log"**.
4. **Verification**: Confirm that asset total hours, engine cycles, and battery telemetry update immediately.

---

### SOP-02: Defect Findings & Snag Management (Quality & Line Maintenance)
1. **Trigger**: Pilot defect report, scheduled inspection check, or ramp audit.
2. **Actor**: Licensed Maintenance Engineer (AME) or Quality Auditor.
3. **Execution**:
   - Open asset in **Fleet Operations $\rightarrow$ Findings Tab $\rightarrow$ Log Finding**.
   - Enter title, ATA chapter, descriptive narrative, and select Severity:
     - `CRITICAL`: Immediate safety-of-flight hazard $\rightarrow$ *Automatically transitions Asset Readiness to `BLOCKED`*.
     - `MAJOR`: Significant defect requiring scheduled rectification within approved MEL limits.
     - `MINOR`: Cosmetic or non-airworthiness defect.
   - Link photo/document evidence if available.
   - Click **"Create Finding"**.

---

### SOP-03: Maintenance Work Order & Release to Service (Engineering)
1. **Trigger**: Open finding, scheduled interval check (A-Check / 100h Drone Inspection), or Airworthiness Directive compliance.
2. **Actor**: Lead Maintenance Engineer (`MAINTENANCE_ENGINEER`).
3. **Execution**:
   - Create Work Order in **Maintenance $\rightarrow$ New Work Order**.
   - Attach standardized task cards and assign technicians.
   - If components are swapped, record old serial removal and new serial installation with initial meter carry-in.
   - Attach signed Form 1 or Certificate of Release to Service (CRS) PDF. KOTA automatically generates an immutable SHA-256 hash.
   - Perform electronic sign-off: Click **"Release to Service (RTS)"**.
4. **Result**: Work order transitions to `COMPLETED`; linked Finding auto-resolves; asset airworthiness readiness automatically recalculates.

---

### SOP-04: Regulatory Compliance & Airworthiness Directives (CAMO)
1. **Actor**: CAMO Postholder (`CAMO_MANAGER`).
2. **Execution**:
   - Review incoming ADs / SBs in **Compliance Module**.
   - Record assessment: `COMPLIANT`, `NON_COMPLIANT`, `REVIEW_REQUIRED`, or preserve `UNKNOWN` if awaiting OEM service letter clarification.
   - *Rule*: Never record compliance without attaching authorized evidence.

---

### SOP-05: Proactive Intelligence Review & LISA Consultation (Management)
1. **Daily Routine**: Every morning at 07:00 local time, the CAMO Manager and Maintenance Controller open **Fleet Operations $\rightarrow$ Attention Queue**.
2. **Review Active Signals**:
   - Inspect threshold warnings, battery degradation alerts, and recurring defect signals.
   - Query LISA: *"What maintenance tasks are due today across the ATR and drone fleet?"*
   - Drill into linked evidence before issuing work orders.
3. **Decision Rule**: All AI recommendations are advisory; human authorization is mandatory for all maintenance releases and operational dispatches.
