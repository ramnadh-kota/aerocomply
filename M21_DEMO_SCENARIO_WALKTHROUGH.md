# Milestone M21 Demo Scenario Walkthrough
## Step-by-Step Operator Review Guide for Scenarios A through F

**Target Audience:** Project Owner, Product Reviewers, Aerospace Stakeholders  
**Console Route:** `/intelligence/fleet`  
**Tenant:** `Kota Aerospace Demo Operations`  
**Recommended Persona:** `demo.admin@kotaaerospace.com` / `DemoPassword2026!Kota`  

---

## Scenario A — Healthy Drone Fleet Operations
**Goal:** Verify normal operating conditions, fresh telemetry pings, and absence of critical alarms.

1. **Navigate to Console:** Open `https://aerocomply.vercel.app/intelligence/fleet` (or `http://localhost:3000/intelligence/fleet`).
2. **Review Fleet Overview Tab:**
   - Note the **Fleet Population** card: 5 Drones, 2 Aircraft, 1 Helicopter, 1 eVTOL.
   - Note the **Telemetry Status**: 8 Assets Fresh, 1 Stale, 0 Missing.
3. **Inspect Asset `KOTA-DRN-01`:**
   - Model: *Kota HexaCargo-X6*. Status: `ACTIVE`.
   - Telemetry: Fresh (<5 minutes ago), Battery: 92%, Vibration RMS: 0.45g (well below 1.8g warning threshold).
   - Compliance: Fully compliant with FAA Part 107 standards.

---

## Scenario B — Degrading Component & Early Fault Detection
**Goal:** Review an early-stage vibration harmonic anomaly detected by HUMS before catastrophic failure.

1. **Switch to Signals & Attention Tab:**
   - Locate Warning Signal: **"Elevated Motor Vibration — Motor bearing 2X RPM harmonic spike observed during cruise phase"**.
   - Severity: `WARNING`. Affected Asset: `KOTA-DRN-02`.
2. **Inspect Source Evidence:**
   - Click the signal card to view evidence drill-down.
   - Sensor: `SENS-VIB-02` on Component `Front-Right Brushless Motor`.
   - Observed RMS: **3.4g** (Threshold: 1.8g).
3. **Switch to Predictive MRO Tab:**
   - Locate Candidate `MAINTENANCE_ATTENTION` for `KOTA-DRN-02`.
   - Reason: *"Elevated motor vibration harmonics indicate premature bearing spalling"*.
   - Confidence: **86%**. Priority: `HIGH`.
   - Status: `OPEN`.

---

## Scenario C — Cross-Asset Fleet Correlation Pattern
**Goal:** Demonstrate H8.3 multi-asset correlation showing common fault modes across identical airframes.

1. **Switch to Cross-Asset Anomaly Patterns Tab:**
   - Review the **Vibration Harmonic Clustering** section.
   - Note that both `KOTA-DRN-02` and `KOTA-DRN-03` share identical 2X RPM harmonic vibration patterns on their `Front-Right Brushless Motor` (`KOTA-MTR-800KV`).
2. **Inspect Correlation Details:**
   - Affected Assets: 2 / 5 Drones in fleet.
   - Root Cause Hypothesis: Manufacturing batch tolerance or harmonic resonance at 800 RPM cruise throttle.
   - Causation Limitations: Explains that correlation indicates shared operational stress rather than confirmed systemic batch defect.

---

## Scenario D — Maintenance Schedule vs Operational Readiness Conflict
**Goal:** Demonstrate H8.4 maintenance conflict detection impacting dispatch readiness.

1. **Switch to Predictive MRO Tab:**
   - Locate Conflict Candidate: `CONFLICT_REVIEW` for Fixed-Wing `N702KA` (*Beechcraft King Air 350*).
   - Reason: *"Scheduled 200-hour avionics inspection due within 4.5 flight hours during active deployment schedule"*.
   - Operational Impact: `RESTRICTED_OPERATION`.
2. **Operator Action:**
   - Click **Review** on the candidate card.
   - Review scheduled downtime vs mission priority.
   - Select **Accept** or **Defer** with notes.

---

## Scenario E — Stale Telemetry & Truthful Uncertainty Semantics
**Goal:** Verify that missing or stale telemetry is never masked as healthy equipment.

1. **Return to Fleet Overview Tab:**
   - Note the amber warning badge: **"1 Asset with Stale Telemetry"**.
   - Locate Asset `KOTA-DRN-04` (*Kota MediFly-V2*).
2. **Inspect Stale Telemetry Card:**
   - Last Telemetry Received: **35 days ago**.
   - Health State: Marked **STALE / UNKNOWN** (not "HEALTHY").
   - Safety Invariant: Platform truthful reporting prevents dispatching an asset whose telemetry freshness has lapsed.

---

## Scenario F — Critical Attention & Human-Authorized Work Order Drafting (H8.7)
**Goal:** Experience the complete end-to-end flow from critical exceedance to human-authorized work order creation.

1. **Switch to Signals & Attention Tab:**
   - Locate Critical Signal: **"Bearing Thermal Exceedance (108.5°C)"** on `KOTA-DRN-05` (*Kota PatrolSentinel-8*).
   - Severity: `CRITICAL`. Priority: `HIGH`.
   - Asset Status: Automatically marked `MAINTENANCE`.
2. **Switch to Predictive MRO Tab:**
   - Locate Candidate `cand_05`: Bearing thermal runaway risk.
   - Note that it has already been converted to **Work Order `WO-PM-CRIT05`** (`DRAFT`).
3. **Draft a New Work Order (Interactive Workflow):**
   - On Candidate `KOTA-DRN-02` (from Scenario B), click **Draft Work Order**.
   - In the modal dialog:
     - Priority: `HIGH`
     - Due Date: Set to 3 days out
     - Title: "Corrective Action: Replace Front-Right Brushless Motor"
   - Click **Authorize & Create Draft Work Order**.
   - Confirm Work Order is created with `source_type="PREDICTIVE_INTELLIGENCE"`.
   - Confirm Candidate status updates to `ACCEPTED` / `RESOLVED`.
   - Verify that duplicate drafting is disallowed.

---

## LISA Grounded Fleet Intelligence Queries
**Goal:** Verify LISA decision support using grounded demo evidence.

1. Click the **LISA Intelligence** floating button in the bottom right corner of the console.
2. Try the following grounded quick-prompts:
   - *"Which assets need immediate maintenance attention?"*  
     -> LISA cites `KOTA-DRN-05` (Critical 108.5°C thermal exceedance) and `KOTA-DRN-02` (vibration harmonic 3.4g).
   - *"Why is KOTA-DRN-04 marked with a freshness warning?"*  
     -> LISA reports that `KOTA-DRN-04` has had no telemetry contact for 35 days and cannot be certified healthy.
   - *"Are there shared vibration patterns across the drone fleet?"*  
     -> LISA identifies the 2X RPM harmonic cluster between `KOTA-DRN-02` and `KOTA-DRN-03`.
   - *"Can you autonomously schedule maintenance for KOTA-DRN-02?"*  
     -> LISA refuses autonomous action and guides the operator to use the human authorization drafting button in the MRO tab.
