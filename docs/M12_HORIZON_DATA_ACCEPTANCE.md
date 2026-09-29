# KOTA AEROSPACE — M12 HORIZON DATA ACCEPTANCE CERTIFICATE

## Authoritative Historical Baseline Reconciliation & Migration Sign-Off

---

### 1. Document Control & Customer Metadata
- **Customer Organization**: Horizon Regional Air & Drone Mobility Pvt. Ltd. (`horizon-air-mobility`)
- **Subscription Tier**: Enterprise Plan
- **Migration Pipeline**: M5 Import Center (AeroComply Staging & Validation Engine)
- **Certification Date**: 2026-09-27
- **CAMO Authority Sign-Off**: Captain S. Malhotra (Lead CAMO Postholder, Horizon Air)
- **Platform Lead Sign-Off**: Lead Implementation Engineer, KOTA Aerospace

---

### 2. Historical Baseline Migration Invariant
Every migrated aircraft and drone is governed by KOTA's strict baseline accounting formula:
$$\text{Current Authoritative Utilization} = \text{Historical Carry-In Baseline} + \sum_{t \ge \text{Baseline Date}} \text{Post-Migration Flight Records}$$
*Zero double counting: Historical flights prior to the baseline date remain available for inspection and audit traceability but are never re-accumulated into current total flight hours or cycles.*

---

### 3. Fleet Asset Reconciliation Table

| Asset ID | Registration / Serial | Asset Archetype | Source Baseline Cut-off Date | Source Baseline Hours / Cycles | Ingested Baseline Hours / Cycles | Post-Migration Flights Ingested | Current Calculated Total (KOTA) | Variance / Discrepancy | Acceptance Status |
|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **ASSET-01** | `VT-HZA` | ATR-72-600 (MSN 1450) | 2026-08-31 | 3,420.5h / 2,890c | 3,420.5h / 2,890c | 14.5h / 12c (8 flights) | **3,435.0h / 2,902c** | 0.0h / 0c | **ACCEPTED (PASS)** |
| **ASSET-02** | `VT-HZB` | ATR-72-600 (MSN 1512) | 2026-08-31 | 2,110.0h / 1,745c | 2,110.0h / 1,745c | 18.0h / 14c (10 flights)| **2,128.0h / 1,759c** | 0.0h / 0c | **ACCEPTED (PASS)** |
| **ASSET-03** | `VT-HZC` | ATR-42-600 (MSN 1205) | 2026-08-31 | 4,895.0h / 4,120c | 4,895.0h / 4,120c | 9.5h / 8c (5 flights)   | **4,904.5h / 4,128c** | 0.0h / 0c | **ACCEPTED (PASS)** |
| **ASSET-04** | `DR-HZ01` | DJI FlyCart 30 (FC30-0981) | 2026-08-31 | 185.5h / 412m | 185.5h / 412m | 4.5h / 11m (11 missions)| **190.0h / 423m** | 0.0h / 0c | **ACCEPTED (PASS)** |
| **ASSET-05** | `DR-HZ02` | DJI FlyCart 30 (FC30-1044) | 2026-08-31 | 142.0h / 318m | 142.0h / 318m | 6.0h / 14m (14 missions)| **148.0h / 332m** | 0.0h / 0c | **ACCEPTED (PASS)** |
| **ASSET-06** | `DR-HZ03` | Harris Aerial Hx8 (HX8-0042) | 2026-08-31 | 96.5h / 184m | 96.5h / 184m | 2.5h / 5m (5 missions) | **99.0h / 189m** | 0.0h / 0c | **ACCEPTED (PASS)** |

---

### 4. Component Life-Limited Part (LLP) & Battery Acceptance
- **Turboprop Engines (PW127M - 6 installed, 2 spare)**: 100% of serials, current operating hours, and remaining cycles to next overhaul validated against physical log cards.
- **Intelligent Drone Battery Packs (TB30 / Solid-State - 12 packs)**: Initial cycle counts and internal resistance baseline metrics calibrated.
- **Defect Findings & Work Orders**: 64 historical defect findings and 112 historical maintenance accomplishments ingested with full audit traceability.

---

### 5. Formal Data Acceptance Declaration
The undersigned representative of Horizon Regional Air & Drone Mobility Pvt. Ltd. confirms that the historical data migration executed through the KOTA M5 Import Center is accurate, complete, and reconciled with zero discrepancies against physical aircraft logbooks.

**Approved by**: *Capt. S. Malhotra (Lead CAMO Postholder, Horizon Air)*  
**Date**: *2026-09-27*
