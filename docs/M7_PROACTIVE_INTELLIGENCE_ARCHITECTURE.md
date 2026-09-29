# KOTA AEROSPACE — M7 PROACTIVE INTELLIGENCE ARCHITECTURE

**System Designation**: Milestone M7 — Proactive Aerospace Intelligence, Risk & Decision Automation  
**Author**: Developer 2 — Antigravity Intelligence  
**Core Thesis**: Moving KOTA from reactive inquiry (*"Tell me what is happening"*) to proactive deterministic intelligence (*"Tell me what is becoming important, why it matters, what evidence supports it, and what action should be considered"*).

---

## 1. Executive Summary & Core Principles

M7 introduces an autonomous, explainable intelligence layer across KOTA Aerospace. Unlike generic or probabilistic AI architectures, KOTA Proactive Intelligence operates under strict aerospace engineering constraints:

1. **Deterministic Grounding**: Every proactive signal is calculated from live, authoritative domain records (`Asset`, `Flight`, `MaintenanceRequirement`, `Finding`, `WorkOrder`, `Battery`, `ComplianceObligation`, `EvidenceFile`). No simulated probabilities or hallucinated warnings are permitted.
2. **Traceable Evidence Provenance**: Every signal links back to the specific entity IDs, observed metrics, limit thresholds, and deep URLs representing ground truth.
3. **Kleene 3-Valued Logic Preservation**: Missing or unverified data evaluates to `UNKNOWN`, never coerced to `FALSE` (healthy) or `TRUE` (failed).
4. **Human Authorization for Consequential Action**: Intelligence suggests and automates decision support pathways, but consequential operational actions (e.g., grounding, dispatch release, work order authorization) require explicit human sign-off.
5. **Zero Baseline Regressions**: M5 and M6 operational baselines remain 100% intact and passing.

---

## 2. Proactive Intelligence Decision Pathway

```
Operational Data  ───►  Evidence  ───►  Compliance  ───►  Readiness
        │                                                     │
        ▼                                                     ▼
     Signals  ────────►   Risk   ───►  Intelligence ───►   Decision   ───►   Action
 (Early Warning)     (Kleene Logic)    (Explainable)     (Human Auth)     (Automated)
```

---

## 3. Signal Taxonomy & Severity Model

### Signal Types
| Signal Type | Target Domain | Trigger Condition | Severity Default |
|---|---|---|---|
| `THRESHOLD_PROXIMITY` | Scheduled Maintenance | Flight hours / cycles within 10% of requirement threshold | HIGH / CRITICAL |
| `BATTERY_HEALTH_DEGRADATION` | Battery Subsystems | Health SOH < 80% or rapid decline | CRITICAL / HIGH |
| `BATTERY_CYCLE_EXHAUSTION` | Battery Subsystems | Cycle count >= 85% of rated limit (e.g. >= 255/300) | HIGH / CRITICAL |
| `INSPECTION_INTERVAL_EARLY_WARNING` | Asset Utilization | Projected utilization pace breaches inspection interval in < 14 days | HIGH |
| `RECURRING_FINDING_PATTERN` | Defect Intelligence | >= 2 findings in same category/component within rolling 90 days | HIGH |
| `UTILIZATION_PACE_ACCELERATION` | Flight Operations | 14-day flight hours pace > 1.5x of previous 30-day baseline | MEDIUM |
| `COMPLIANCE_VERIFICATION_GAP` | Regulatory Obligations | Obligation marked complete but evidence verification is unverified | HIGH |
| `UNVERIFIED_COMPLIANCE_OBLIGATION` | Compliance Obligation | Obligation status `NON_COMPLIANT` or `OVERDUE` | CRITICAL |
| `MISSING_WORK_ORDER_EVIDENCE` | MRO Execution | Work order completed without any attached evidence records | HIGH |
| `READINESS_DEGRADATION_EXPLAINER` | Fleet Readiness | Operational state degraded due to active findings, overdue WOs, or unverified items | HIGH / CRITICAL |
| `FLEET_WIDE_DEFECT_PATTERN` | Fleet-wide Analytics | >= 3 similar findings across distinct airframes in 90 days | HIGH |
| `SYSTEMIC_OVERDUE_PATTERN` | Maintenance Operations | >= 2 overdue work orders across the fleet | HIGH |
| `RECURRING_DEFECT_CLUSTER` | Asset Component Level | >= 2 active findings on a single airframe | HIGH |

### Priority & Severity Scales
- **Severity**: `CRITICAL` | `HIGH` | `MEDIUM` | `LOW` | `INFO`
- **Priority**: `IMMEDIATE` | `UPCOMING` | `WATCHLIST` | `INFORMATIONAL`
- **Lifecycle Status**: `OPEN` → `ACKNOWLEDGED` → `IN_REVIEW` → `RESOLVED` / `DISMISSED`
- **Trend Direction**: `WORSENING` | `STABLE` | `IMPROVING`

---

## 4. Deterministic Evaluator Architecture

The service `ProactiveIntelligenceService` (`backend/app/services/intelligence/proactive_intelligence_service.py`) runs 8 deterministic evaluators against tenant data:

1. **`_eval_maintenance_and_work_orders`**:
   - Compares total airframe hours (`flight_service.get_utilization`) against `MaintenanceRequirement.fh_interval` and `fc_interval`.
   - Identifies open work orders past scheduled target completion dates.
2. **`_eval_battery_health`**:
   - Queries `Battery` records where `status = ACTIVE`.
   - Evaluates `health_percent < 80.0` or `cycle_count >= (max_cycles * 0.85)`.
3. **`_eval_recurring_findings`**:
   - Queries `Finding` records within a rolling 90-day window (`created_at >= now - 90 days`).
   - Clusters by category / title keyword. Detects single-asset and fleet-wide defect trends.
4. **`_eval_utilization_acceleration`**:
   - Compares recent 14-day flight hour pace against earlier baseline. Signals pace surges (>50% increase).
5. **`_eval_compliance_verification_gaps`**:
   - Evaluates `ComplianceObligation` records where status is `NON_COMPLIANT`, `OVERDUE`, or completed without verified evidence.
6. **`_eval_missing_work_order_evidence`**:
   - Inspects completed `WorkOrder` records for missing `EvidenceFile` associations.
7. **`_eval_readiness_explainer`**:
   - Generates deterministic natural-language explanations for why an airframe's readiness state is `BLOCKED` or `RESTRICTED`.
8. **`_eval_fleet_wide_patterns`**:
   - Aggregates systemic patterns across the organization (fleet defect clusters, systemic work order backlogs).

---

## 5. Storage & Persistence (`ProactiveSignalRecord`)

Signals are persisted in PostgreSQL with deduplication:
- **Table**: `proactive_signals`
- **Unique Constraint**: `(organization_id, asset_id, signal_type, trigger_condition)` for active signals.
- **State Transitions**:
  - `acknowledge_signal(signal_id, user_id)`: Records `acknowledged_by`, `acknowledged_at`.
  - `in_review_signal(signal_id, user_id)`: Sets status to `IN_REVIEW`.
  - `resolve_signal(signal_id, user_id)`: Records `resolved_by`, `resolved_at`.
  - `dismiss_signal(signal_id, user_id, reason)`: Records `dismissed_by`, `dismissed_at`, `dismissal_reason`.

---

## 6. LISA AI & Grounded Tool Integration

LISA (Language & Intelligence System for Aerospace) natively invokes proactive intelligence tools:
- **Intent**: `Intent.PROACTIVE_INTELLIGENCE` (e.g. *"What proactive risks exist across our fleet?"*, *"Are there any early warning signals for VT-ABC?"*).
- **Tools**:
  - `get_proactive_intelligence_summary`: Summarizes critical, high, and immediate proactive risks.
  - `get_asset_proactive_signals`: Returns deterministic active signals with evidence and recommended actions for a specific airframe.
- **Orchestration**: `_investigate_proactive_intelligence` formats deterministic insights with evidence provenance without LLM fabrication.

---

## 7. Frontend Integration

1. **Dashboard (`frontend/app/(app)/dashboard/page.tsx`)**:
   - Displays real-time `ProactiveSignalsSection` above attention queues.
   - Highlights critical early warnings, fleet insights, and recommended actions.
   - Allows operators to acknowledge, inspect evidence, or dismiss signals with audit justifications.
2. **Asset Workspace (`frontend/app/(app)/assets/[id]/page.tsx`)**:
   - Dedicated Proactive Intelligence section under the **Intelligence** tab.
   - Filterable by signal status and severity.
   - Traceable Evidence Provenance drawer linking directly to underlying domain entities.
