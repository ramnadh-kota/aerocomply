# MRO + Compliance + Readiness Intelligence Integration (H7)

**H7 is an integration/intelligence layer and does not replace the
authoritative MRO system.**

See `docs/H7_COMPLIANCE_READINESS_INTEGRATION.md` for the compliance- and
readiness-specific derivation rules. This document covers the H7
architecture, maintenance candidates, source lineage, correlation logic,
conflict detection, reconciliation, the REST/AI surfaces, RBAC, tenant
isolation, and safety boundaries.

## Architecture overview

H7 is a **read-heavy correlation layer**, not a new system of record.
`app/services/mro_intelligence_service.py`'s module docstring states this
directly: H7 calls existing authoritative services and correlates their
outputs; it never recomputes health, diagnostic, prognostic, compliance, or
readiness logic. The authoritative sources it consumes, and never
re-derives:

- `app.services.hums_service` (H1–H5: health / diagnostics / prognostics)
- `app.services.aerospace_state_service.evaluate_aerospace_intelligence_state`
  (D2.1/D2.4 intelligence state)
- `app.services.intelligence.readiness_intelligence_service`
  `.get_asset_readiness_intelligence` (D2.2 authoritative asset readiness)
- `app.models.compliance.ComplianceObligation` (authoritative compliance
  state — `ComplianceState` values are never re-invented)
- `app.models.work_order.WorkOrder` / `app.models.finding.Finding`
  (maintenance history, used for candidate dedup against existing work)
- `app.services.digital_twin_service.check_asset_consistency` (H6's own
  consistency-warning concept, consulted as one input to conflict
  detection, not duplicated)

The **only** table H7 owns is `MaintenanceIntelligenceCandidate`
(`app/models/mro_intelligence.py`), a lifecycle-managed
correlation/recommendation object. H7 code must **never** write to any
authoritative domain table (Asset/Aircraft lifecycle,
`ComplianceObligation.status`, readiness-state fields,
`HUMSDiagnosticCandidate`, `HUMSPrognosticRecord`, `WorkOrder`) — it only
writes to its own candidate table and to `AuditEvent`. The service module
is entirely deterministic: no ML/LLM scoring appears anywhere in it.

```
HUMS health/diagnostics/prognostics (H1-H5)
Compliance obligations (authoritative)
Readiness intelligence (authoritative)
Work orders / Findings (authoritative)
Digital Twin consistency warnings (H6)
            |
            v
   mro_intelligence_service (correlation only, no re-derivation)
            |
    +-------+--------+--------------------+
    v                v                    v
Maintenance          Compliance /         Integration
Candidates           Readiness /          Conflicts
(persisted)          Operational Impact   (reported only)
                      (computed, not
                       persisted)
```

## Maintenance intelligence concept

A **maintenance intelligence candidate** is a correlated recommendation —
generated when HUMS health/diagnostic/prognostic signals converge with
maintenance or compliance state — that requires explicit human review.
This is distinct from `ProactiveSignalRecord`
(`app/models/proactive_signal.py`): a `ProactiveSignalRecord` is a
transient, single-detector alert, while a `MaintenanceIntelligenceCandidate`
is a lifecycle-managed object generated only by **cross-domain**
correlation (health + diagnostic + prognostic + maintenance + compliance),
never by a single-domain detector.

## Maintenance candidates

### Types (`MROCandidateType`)

A small, deliberately narrow set — new categories should only be added when
an existing one genuinely does not fit:

- `INSPECTION_REVIEW`
- `MAINTENANCE_ATTENTION`
- `COMPLIANCE_REVIEW`
- `CONFLICT_REVIEW`

`generate_maintenance_candidates` currently produces only
`MAINTENANCE_ATTENTION` candidates; the other types are reserved for future
correlation paths.

### Status (`MROCandidateStatus`)

`OPEN`, `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `DEFERRED`, `RESOLVED`.

### Priority (`MROCandidatePriority`)

`HIGH`, `MEDIUM`, `LOW` — derived from the correlated component health
state (`CRITICAL` → `HIGH`, `WARNING` → `MEDIUM`, `DEGRADED` → `LOW`).

### Lifecycle transitions

`ALLOWED_CANDIDATE_TRANSITIONS` (`app/models/mro_intelligence.py`) is
checked by `mro_intelligence_service._transition` before any status write,
rejecting an invalid transition with a `ConflictError`:

| From | Allowed to |
|---|---|
| `OPEN` | `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `DEFERRED`, `RESOLVED` |
| `UNDER_REVIEW` | `ACCEPTED`, `REJECTED`, `DEFERRED`, `RESOLVED` |
| `DEFERRED` | `UNDER_REVIEW`, `ACCEPTED`, `REJECTED`, `RESOLVED` |
| `ACCEPTED` | `RESOLVED` |
| `REJECTED` | (terminal — no further transitions) |
| `RESOLVED` | (terminal — no further transitions) |

`accept_candidate` records the human decision only — it does **not**
auto-create a work order. `resolved_at`/`resolved_by` are stamped on any
transition into `ACCEPTED`, `REJECTED`, or `RESOLVED`, and every transition
is recorded as an `AuditEvent`.

## Source lineage design

`source_lineage` (JSONB list of `{source_type, source_id, label}`) stores
**IDs and labels only — never copies of the source records' field data**.
This is stated explicitly in both the model and schema docstrings: because
a candidate only ever references other rows by ID, it is always
re-derivable from, and can never drift out of sync with, the authoritative
systems it points at. If it instead copied field values (e.g. a fault
name, a health state string) at generation time, those copies would go
stale the moment the underlying HUMS/compliance/maintenance record changed
— reintroducing the exact twin-state-drift problem H6's Digital Twin
architecture already avoided by never persisting derived state. H7 follows
the same discipline for the same reason.

## Correlation logic

`generate_maintenance_candidates` (`mro_intelligence_service.py`) is the
sole candidate-generation path:

1. For each component in the asset's H3 health intelligence
   (`hums_service.get_asset_health_intelligence`), skip unless the
   component state is `DEGRADED`, `WARNING`, or `CRITICAL`.
2. Require **at least one corroborating H4/H5 signal** — an open
   `HUMSDiagnosticCandidate` or an `HUMSPrognosticRecord` on the same
   component. H3 health alone, with no corroborating H4/H5 signal, is
   explicitly *not* treated as a convergent finding.
3. Skip if an open `WorkOrder` or `Finding` already covers the same
   asset/component (`_existing_work_order_covers`) — a candidate is never
   created to duplicate work already tracked in the authoritative
   maintenance domain.
4. Compute a deterministic `dedup_key`
   (`asset_id:component_id:candidate_type:sha256(sorted source refs)[:16]`)
   and skip if an `OPEN`/`UNDER_REVIEW`/`DEFERRED` candidate with the same
   key already exists — generation is idempotent.
5. Otherwise persist a new `MAINTENANCE_ATTENTION` candidate with priority
   derived from component state and confidence `0.75` when both a
   diagnostic and a prognostic corroborate, else `0.55`.

The dedup key is **not** globally unique the way `ProactiveSignalRecord
.signal_key` is: a `RESOLVED`/`REJECTED` candidate may be superseded by a
new `OPEN` one sharing the same key once the underlying signal set changes
again.

## Operational impact

`get_operational_impact` derives an `OperationalImpactLevel`
(`LOW`/`MEDIUM`/`HIGH`/`UNKNOWN`) from readiness impact and RUL-horizon
proximity:

- Readiness impact `UNKNOWN` → operational impact `UNKNOWN` ("no
  authoritative mission-criticality data exists; operational impact cannot
  be determined").
- `RESTRICTED_OPERATION`/`READINESS_AT_RISK` → `HIGH`.
- `REVIEW_REQUIRED`/`INSPECTION_REQUIRED`/`MAINTENANCE_DUE` → `MEDIUM`.
- Otherwise, any prognostic with `rul_estimate < 25` usage-units → `MEDIUM`;
  else `LOW`.

## Conflict detection

`detect_conflicts` runs **six additive, report-only** consistency checks —
never auto-resolved. H6's `digital_twin_service.check_asset_consistency` is
consulted as one input (structural reference-integrity warnings, surfaced
under the `DIGITAL_TWIN_CONSISTENCY` check name); the remaining five checks
are distinct because they correlate **across** the
readiness/compliance/maintenance/diagnostic/prognostic domains that H6
itself does not cross-check:

| Check | Condition |
|---|---|
| `DIGITAL_TWIN_CONSISTENCY` | Any H6 consistency warning for the asset (e.g. sensor/component reference mismatch, duplicate open installation) |
| `READINESS_VS_COMPLIANCE` | Authoritative readiness is `READY` while a compliance obligation's impact is `NON_COMPLIANT`/`OVERDUE` (severity `HIGH`) |
| `DIAGNOSTIC_VS_MAINTENANCE` | A `HIGH`-severity, non-rejected/resolved diagnostic candidate exists with no open `WorkOrder` for the asset (severity `HIGH`) |
| `COMPONENT_CONFIGURATION` | A diagnostic candidate references a `component_id` not currently on the asset's component tree (severity `MEDIUM`) |
| `PROGNOSTIC_FRESHNESS` | A prognostic record with `quality`/`confidence` of `STALE` exists while authoritative readiness is `READY` (severity `LOW`) |
| `COMPLIANCE_VS_EVIDENCE` | A compliance obligation is `COMPLIANT` with no `completed_at`/`verified_at` timestamp (severity `MEDIUM`) |

Each conflict carries `source_a`/`source_b` `SourceLineageRef`s (IDs/labels
only, same lineage convention as candidates) so a reviewer can trace the
conflict back to the exact records involved.

## Reconciliation

`reconcile_asset_mro_intelligence` is the only lifecycle-mutating
correlation entry point (gated by `MRO_INTELLIGENCE_REVIEW`, not `_READ`):

- An `OPEN`/`UNDER_REVIEW`/`DEFERRED` candidate is transitioned to
  `RESOLVED` when the underlying health/diagnostic signal that generated it
  has cleared (its component is no longer degraded **and** none of its
  linked diagnostic refs are still open).
- A candidate is **flagged** (returned in `flagged_candidate_ids`, status
  left unchanged) when its component is no longer degraded but it carries
  no diagnostic corroboration to fall back on — an ambiguous case
  surfaced for human judgment rather than auto-resolved.

Reconciliation **never mutates any authoritative table** — only rows in
`MaintenanceIntelligenceCandidate` (via `resolved_at`) — and it does not
touch `WorkOrder`, `Finding`, `ComplianceObligation`, readiness state, or
any HUMS record.

## REST API surface

All routes are under `/mro-intelligence` (`app/api/v1/mro_intelligence.py`):

| Method | Path | Permission |
|---|---|---|
| GET | `/mro-intelligence/assets/{asset_id}` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/assets/{asset_id}/maintenance-candidates` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/assets/{asset_id}/compliance-impact` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/assets/{asset_id}/readiness-impact` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/assets/{asset_id}/operational-impact` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/assets/{asset_id}/conflicts` | `MRO_INTELLIGENCE_READ` |
| POST | `/mro-intelligence/assets/{asset_id}/reconcile` | `MRO_INTELLIGENCE_REVIEW` |
| GET | `/mro-intelligence/components/{component_id}` | `MRO_INTELLIGENCE_READ` |
| GET | `/mro-intelligence/candidates/{candidate_id}` | `MRO_INTELLIGENCE_READ` |
| POST | `/mro-intelligence/candidates/{candidate_id}/review` | `MRO_INTELLIGENCE_REVIEW` |
| POST | `/mro-intelligence/candidates/{candidate_id}/accept` | `MRO_INTELLIGENCE_REVIEW` |
| POST | `/mro-intelligence/candidates/{candidate_id}/reject` | `MRO_INTELLIGENCE_REVIEW` |
| POST | `/mro-intelligence/candidates/{candidate_id}/defer` | `MRO_INTELLIGENCE_REVIEW` |

`GET /assets/{asset_id}/maintenance-candidates` both generates new
candidates (`generate_maintenance_candidates`) and merges them with
existing persisted candidates in one response — a single call always
returns the current, up-to-date candidate list for the asset.

## AI tools

Six read-only `ToolSpec` entries are registered in
`app/services/ai/tools.py`, each a thin wrapper over the corresponding
service function and gated by `MRO_INTELLIGENCE_READ`:

- `get_asset_mro_intelligence`
- `get_asset_maintenance_candidates`
- `get_asset_compliance_impact`
- `get_asset_readiness_impact`
- `get_asset_operational_impact`
- `get_asset_integration_conflicts`

None of these tools can mutate a candidate's lifecycle (review/accept/
reject/defer/reconcile are not exposed to the AI assistant). Their
descriptions explicitly frame the results as correlations over existing
authoritative services, not a new readiness/compliance engine, and state
that candidates are advisory review items requiring human accept/reject/
defer — never confirmed faults or automatic work orders.

## RBAC

Two permissions gate H7 (`app/core/permissions.py`):

- `MRO_INTELLIGENCE_READ` — all read endpoints and all six AI tools.
- `MRO_INTELLIGENCE_REVIEW` — candidate lifecycle mutation
  (review/accept/reject/defer) and `/reconcile`.

There is **no** `MRO_INTELLIGENCE_WRITE`: H7 never mutates any
authoritative domain table, only its own `MaintenanceIntelligenceCandidate`
lifecycle, which is gated by the separate, narrower `_REVIEW` permission —
reviewing/accepting/rejecting/deferring a candidate is a human
decision-of-record, not a data-read.

Both permissions are granted to: `HUMS_WRITE`-holding maintenance/asset
roles, `COMPLIANCE_MANAGER`, `CAMO_MANAGER`, `QUALITY_MANAGER`, and
`MAINTENANCE_ENGINEER`. `VIEWER` receives `MRO_INTELLIGENCE_READ` only —
consistent with every other read/write permission pair in this system,
`VIEWER` never receives a review/write-capable permission.

## Tenant isolation

Every service function takes an explicit `organization_id` and filters all
queries on it — the same `organization_id` scoping pattern every other
domain service in this codebase already uses. `MaintenanceIntelligenceCandidate`
is `TenantScopedMixin`, and its indexes
(`ix_mro_candidates_org_asset`, `ix_mro_candidates_org_status`,
`ix_mro_candidates_org_dedup_key`) are all composite on
`organization_id` first. H7 introduces no new isolation boundary to get
wrong — it reuses every underlying service's own tenant filtering and adds
its own `organization_id` filter on top for the one table it owns.

## Safety boundaries

- H7 never recomputes health, diagnostic, prognostic, compliance, or
  readiness logic — it only correlates the authoritative outputs of the
  services that already own that logic.
- H7 never writes to `Asset`/`Aircraft` lifecycle state,
  `ComplianceObligation.status`, readiness-state fields,
  `HUMSDiagnosticCandidate`, `HUMSPrognosticRecord`, or `WorkOrder`.
- Accepting a candidate records a human decision only; it never
  auto-creates a work order or finding.
- Conflicts are reported only, never auto-resolved.
- Reconciliation only ever mutates rows in
  `MaintenanceIntelligenceCandidate`.
- **H7 is an integration/intelligence layer and does not replace the
  authoritative MRO system.**

## Known limitations

- `generate_maintenance_candidates` currently emits only
  `MAINTENANCE_ATTENTION` candidates; `INSPECTION_REVIEW`,
  `COMPLIANCE_REVIEW`, and `CONFLICT_REVIEW` are reserved types with no
  generation path yet.
- Candidate priority/confidence thresholds (e.g. `0.75`/`0.55` confidence,
  the `<25` usage-unit RUL horizon for operational impact) are documented
  placeholder heuristics, not derived from any reliability-engineering or
  MRO-industry standard.
- Component health correlation requires an H3 component-level state of
  `DEGRADED`/`WARNING`/`CRITICAL`; asset-level-only signals with no
  component attribution do not generate candidates.
- Conflict detection is a fixed set of six checks; it is not a general
  constraint-satisfaction or rules engine and does not detect conflict
  types outside this list.
- No async/background job runs candidate generation, conflict detection,
  or reconciliation — all three execute synchronously when their
  corresponding endpoint or AI tool is called, consistent with every prior
  HUMS milestone's documented async boundary (no Celery/RQ/cron in this
  codebase).
- Not a work-order system, not a parts/inventory system, and not a
  replacement for the authoritative MRO system of record — H7 only
  correlates and recommends.
