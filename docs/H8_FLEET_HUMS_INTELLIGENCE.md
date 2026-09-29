# H8.0 — Fleet Intelligence Contract & Foundation

Status: FOUNDATION PHASE ONLY (H8.0 + H8.1). Not a complete H8 milestone.

## Purpose

H8 is the fleet-level integration/foundation layer that later H8 milestones
(H8.2+) will build on. H8.0 defines a shared CONTEXT contract
(`app/schemas/fleet_intelligence.py`: `FleetIntelligenceContext`) that
represents fleet intelligence *context*, not persistent state. Every field
in the contract is derived at read time from authoritative records; nothing
is written back to any authoritative table, and there is no
`Fleet`/`FleetHealth`/`FleetAttention`/`FleetSignal`/`FleetState` table.

## Canonical ownership (binding — do not relitigate)

- **M7** (`app/services/intelligence/proactive_intelligence_service.py`) —
  sole owner of proactive signals, signal lifecycle, fleet-pattern rollup,
  fleet alerting/attention ranking. Persisted via `ProactiveSignalRecord`.
- **M14** (`app/services/intelligence/cross_asset_intelligence_service.py`,
  `evaluate_cross_asset_intelligence`) — sole owner of cross-asset
  descriptive analytics (org-wide, query-time). H8.1 extends this module in
  place.
- **M4.2** (`app/services/intelligence/fleet_intelligence_service.py`) —
  presentation/reshape layer only, adds no new intelligence rule. Untouched
  by H8.0/H8.1.
- **H7** (`app/services/mro_intelligence_service.py`) — asset-scoped
  MRO/compliance/readiness intelligence. Untouched, not integrated into H8
  yet.
- **H3/H4/H5** (`app/services/hums_service.py` and `app/services/hums/*`) —
  the ONLY authoritative source for asset/component health (H3),
  diagnostics (H4), and prognostics/RUL (H5). H8/M14 never re-derive these
  values; they only aggregate already-computed/persisted results.

## Data authority boundary

The `FleetIntelligenceContext` contract and every H8.1 metric are DERIVED
descriptive analytics. They are never treated as a substitute source of
truth for asset health, diagnostics, RUL, readiness, or compliance. Every
docstring in `fleet_intelligence.py` and `cross_asset_intelligence_service.py`
states this explicitly.

## Source lineage

`SourceLineageEntry` (in `fleet_intelligence.py`) mirrors the
`SourceLineageRef` convention already established by H7
(`app/schemas/mro_intelligence.py`) and the `DataAvailability` convention
from H6 (`app/schemas/digital_twin.py`): a pointer back to the owning
domain/service/entity, never copied field data, and an explicit
`freshness`/`AVAILABLE` vs `DATA_UNAVAILABLE` state so a missing input is
never silently defaulted to a positive value.

## Tenant boundary

Every H8/M14 function takes `organization_id` from `CurrentUser` only,
following the exact convention used by `mro_intelligence_service.py` /
`readiness_intelligence_service.py`. Fleet-level read access is gated by
the existing `Permission.FLEET_READ` (already used by
`commercial_platform.py`'s `/commercial/cross-asset-intelligence` route and
`edge_hardware.py`) — no new permission was added.

## Persistence

Zero new tables, zero new migrations, zero new fleet models. H8.0/H8.1 read
existing authoritative tables (`Asset`, `Component`, `HUMSSensor`,
`HUMSExceedance`, `HUMSDiagnosticCandidate`, `HUMSPrognosticRecord`,
`ProactiveSignalRecord`, `TelemetryEventLog`) and compute a response on
every request.

## What is explicitly NOT part of H8.0/H8.1

- **M7 is not integrated yet.** Fleet signal detection/attention ranking
  stays exclusively M7's responsibility.
- **H7 is not integrated yet.** No fleet-wide MRO/compliance/readiness
  rollup exists yet.
- **LISA is not integrated yet.** No LISA tool references this contract.
- **Frontend is not implemented yet.** No UI consumes `FleetIntelligenceContext`
  or the H8.1 M14 extensions yet; `/intelligence/fleet` was not touched.

See `docs/H8_CROSS_ASSET_INTELLIGENCE.md` for the M14/H8.1 extension detail.

## H8.2 — M7 Fleet Signal Integration

H8.2 adds `FleetSignalContext` (`app/schemas/fleet_intelligence.py`) and
`evaluate_fleet_signal_aggregation` / `FleetSignalSummary`
(`app/services/intelligence/cross_asset_intelligence_service.py`).

**H8 consumes M7 signals and does not recreate M7 detection, ranking,
lifecycle, or pattern logic.**

### What H8.2 does

- Bulk-queries M7's OWN persisted `ProactiveSignalRecord` rows for the
  organization (one query, status in `OPEN`/`ACKNOWLEDGED`/`IN_REVIEW`) —
  no per-asset loop calling into M7, no N+1.
- Buckets those rows by M7's existing `severity` field
  (`app.schemas.intelligence_signal.SignalSeverity`: CRITICAL/HIGH/
  MEDIUM/LOW) and M7's existing `signal_type` field
  (`app.schemas.intelligence_signal.SignalType`) — no new severity or
  signal-type vocabulary is introduced.
- Counts distinct affected assets (`asset_id`) and components
  (`component_id`), both already columns on `ProactiveSignalRecord`.
- Exposes M7's own `FLEET_PATTERN`-typed signal rows **as-is** (filtered
  from the same bulk query) — H8.2 does not call
  `_evaluate_fleet_patterns` and does not re-run any pattern detection.
- Composes the M7 signal count with H8.1's M14 population statistics
  (`FleetPopulationStatistics.asset_count`) into a single descriptive
  ratio string, e.g. `"2/5"` (2 of 5 fleet assets have active signals).
  This is the only correlation built in H8.2; deeper multi-domain
  correlation (M7+M14+H4+H5+H6) is explicitly reserved for H8.3.

### What H8.2 deliberately does NOT do

- Does **not** call `proactive_intelligence_service.sync_and_get_signals`
  or `get_proactive_summary` from within its own aggregation — both
  persist new/updated `ProactiveSignalRecord` rows as a side effect of
  evaluation, which is inappropriate to trigger fleet-wide from a
  read-only aggregation endpoint. H8.2 only reads the table M7 already
  wrote to (consistent with H8.1's approach to `HUMS_HEALTH_DEGRADATION`
  signals).
- Does not assign severity, priority, or attention ranking to any signal.
- Does not create, update, resolve, acknowledge, or dismiss any signal.
- Does not compute its own fleet pattern / recurring-finding correlation.

### Signal lifecycle, attention, and pattern ownership

All three remain exclusively M7's (`app.services.intelligence
.proactive_intelligence_service`): signal lifecycle state transitions
(`acknowledge_signal`/`set_signal_in_review`/`resolve_signal`
/`dismiss_signal`), severity/priority assignment (`_evaluate_*`
functions), and fleet pattern detection (`_evaluate_fleet_patterns`).
H8.2 is a pure downstream reader.

### Freshness semantics reused

`detected_at` timestamps on `ProactiveSignalRecord` are surfaced directly
in `recent_signals`/`fleet_patterns` (most-recent-first, bounded to 10) —
no new freshness threshold. HUMS/telemetry freshness semantics are
unchanged from H8.1 (`resolve_effective_freshness_policy`).

### Source lineage

Any consumer wiring `FleetSignalContext` into `FleetIntelligenceContext`
should stamp `source_domain="M7"`, `source_service=
"app.services.intelligence.proactive_intelligence_service"`,
`source_entity="ProactiveSignalRecord"` per `SourceLineageEntry`'s
existing convention.

### Tenant isolation

`evaluate_fleet_signal_aggregation(db, organization_id=...)` filters every
query by `organization_id`, matching the existing pattern throughout H8.

### Limitations

- Zero new tables/migrations/models — purely a read-time aggregation of
  the existing `ProactiveSignalRecord` table.
- No new public API route was added; the function is an internal service
  entry point only (H8.6 is the public Fleet API milestone).
- No LISA tool references this aggregation (H8.7).
- No frontend surface consumes it (H8.8).
- `signals_by_asset`/`recent_signals` are bounded/small by design — this
  is a summary aggregation, not a paginated signal browser (M7's own
  `sync_and_get_signals` remains the source for full signal listing).

## H8.3: Fleet HUMS Correlation

H8.3 correlates existing HUMS, signal, diagnostic, prognostic, and
Digital Twin outputs. It does not recompute or replace the authoritative
engines that produce those outputs.

Entry point: `app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_hums_correlation(db, *, organization_id)` ->
`FleetCorrelationSummary`. Schema contract:
`app.schemas.fleet_intelligence.FleetCorrelationContext` (and its
sub-models `AssetCorrelationEntry`, `ComponentTypeCorrelationEntry`,
`SignalDiagnosticAssociation`, `SignalPrognosticAssociation`).

### Inputs / consumed sources

| Domain | Source | Access pattern |
|---|---|---|
| M7 signals | `ProactiveSignalRecord` (open-status rows) | bulk SELECT, reuses H8.2's `_compute_fleet_signal_summary` |
| M14 population | `Asset` (non-deleted, org-scoped) | bulk SELECT, reuses H8.1's asset query |
| H4 diagnostics | `HUMSDiagnosticCandidate` (non-terminal status) | bulk SELECT, mirrors H8.1's `_compute_diagnostic_distribution` filter |
| H5 prognostics | `HUMSPrognosticRecord` (is_current=True) | bulk SELECT, mirrors H8.1's `_compute_prognostic_distribution` filter |
| H6 digital twin | `digital_twin_service.get_asset_component_tree` | read-only, per-asset, bounded to the affected-asset set only (see Performance) |
| Components | `Component` (org-scoped) | bulk SELECT |

### Correlation rules (all deterministic -- no fabricated score)

1. Affected asset = an asset with at least one open M7 signal, OR at
   least one non-terminal H4 diagnostic candidate, OR at least one
   current H5 prognostic record. Assets with none of these are simply
   absent from `asset_correlations` -- never a fabricated healthy entry.
2. Signal-diagnostic association (SIGNAL_ASSOCIATED_WITH_DIAGNOSTIC_CANDIDATE):
   a signal and a diagnostic candidate share the same asset_id; when
   both rows also carry a component_id, it must match too
   (basis=SAME_ASSET_AND_COMPONENT), otherwise basis=SAME_ASSET.
3. Signal-prognostic association (SIGNAL_ASSOCIATED_WITH_RUL_ESTIMATE):
   identical same-asset[-and-component] rule applied to
   HUMSPrognosticRecord.
4. Component-type correlation: components sharing the same
   component_type AND (when both set) the same model are grouped
   (basis=SAME_COMPONENT_TYPE_AND_MODEL or SAME_COMPONENT_TYPE), but
   only emitted when 2+ distinct components in that group are
   referenced by at least one M7 signal / H4 candidate / H5 record --
   a same-type/model population observation, never a shared root-cause
   claim.
5. Evidence completeness per affected asset: COMPLETE when 2+ of
   {M7, H4, H5} have data for that asset, PARTIAL when exactly one
   does, INSUFFICIENT_DATA when none do (kept explicit rather than
   defaulted, though unreachable today since affected-asset membership
   itself requires evidence).
6. Fleet ratio: affected_asset_count / total_fleet_assets, exactly
   H8.2's existing ratio composition pattern, expressed as a percentage.

No new numeric correlation/confidence score is introduced anywhere. Any
existing authoritative score (M7 severity, H4 score/confidence, H5
confidence/rul_estimate) is surfaced by direct passthrough with its
source domain implicit in the field name/association, never blended into
a new composite number.

### Evidence lineage

- active_signal_count / highest_signal_severity -- M7's own severity
  field on ProactiveSignalRecord, tallied/maxed, never reassigned.
- diagnostic_candidate_count -- count of H4's own
  HUMSDiagnosticCandidate rows per asset.
- prognostic_record_count / has_rul_estimate -- count and presence
  check over H5's own HUMSPrognosticRecord.rul_estimate, never
  recalculated.
- component_count -- H6's get_asset_component_tree node count when
  available (bounded lookup), else a direct Component table count as a
  documented fallback.
- signal_diagnostic_associations / signal_prognostic_associations --
  pointers (IDs) to the exact M7/H4/H5 rows involved, never a copy of
  their business-logic fields (mirrors SourceLineageEntry's
  "pointer, not a copy" convention).

### Language safety boundary

Every free-text field uses ASSOCIATED / OBSERVED / CORRELATED / AFFECTED
POPULATION phrasing. H8.3 never emits ROOT CAUSE, DEFECTIVE, FAILURE (as
a diagnosis), UNSAFE, or (NOT) AIRWORTHY language -- these are never
computed or asserted by H8.3 since it has no access to (and does not
introduce) any authoritative field that would justify them. This is
enforced by test_no_causation_language_in_multi_source_scenario in
tests/integration/test_h8_3_fleet_hums_correlation.py, which scans every
string field of a multi-source correlation result for forbidden
patterns.

### Tenant isolation

`evaluate_fleet_hums_correlation(db, organization_id=...)` filters every
one of its bulk queries (Asset, ProactiveSignalRecord,
HUMSDiagnosticCandidate, HUMSPrognosticRecord, Component, Aircraft) by
organization_id, matching H8.0-H8.2's existing pattern.
CurrentUser.organization_id is the only source for this value at any
future call site.

### Safety boundary (non-ownership of H4/H5/M7/H6 logic)

H8.3 never calls a write/side-effecting function: not
diagnostic_service.confirm_candidate/reject_candidate, not
prognostic_service's fitting/calculation entry points, not
proactive_intelligence_service.sync_and_get_signals/get_proactive_summary
(both persist rows as a side effect -- H8.1/H8.2 already established
this exclusion; H8.3 follows the same rule). It only reads
HUMSDiagnosticCandidate/HUMSPrognosticRecord/ProactiveSignalRecord rows
that H4/H5/M7 already computed and persisted, and calls H6's read-only
get_asset_component_tree. No db.add/session.add/.commit() call exists
anywhere in this extension -- verified by a source-scan test.

### Performance / N+1 avoidance

Every domain (M7, M14, H4, H5, components) is fetched with exactly one
bulk query, composed in Python -- no per-asset loop calling any service.
The only per-asset call is digital_twin_service.get_asset_component_tree,
which is not bulk-queryable today; per the H8.3 spec's explicit
escalation option, this call is scoped to the AFFECTED-ASSET SET ONLY
(never the whole fleet) and further capped at _MAX_TWIN_LOOKUPS (50)
assets -- beyond that cap, component_count falls back to a direct,
already-bulk-fetched Component table count per asset, and the
correlation's explanation list states this fallback occurred.

### Limitations

- Zero new tables/migrations/models -- a read-time correlation over
  already-persisted M7/H4/H5 rows plus H6's existing read path.
- No new public API route (H8.6 is the public Fleet API milestone).
- No LISA tool references this correlation (H8.7).
- No frontend surface consumes it (H8.8).
- Digital-twin (H6) component context beyond the 50-affected-asset cap
  falls back to a direct component count rather than full twin detail --
  documented, not silently dropped.
- evidence_completeness=INSUFFICIENT_DATA is defined but currently
  unreachable given how affected-asset membership is defined; kept
  explicit for forward-compatibility rather than removed.

### Explicit non-ownership

H8.3 does not own, and never recomputes: H3 health scoring, H4 fault
diagnosis/classification, H5 RUL/degradation modeling, M7 signal
detection/severity/lifecycle/attention ranking, or H6 twin-state
assembly. All of these remain exclusively owned by their respective
milestones, per this document's existing data-authority boundary
statement (see app.schemas.fleet_intelligence's module docstring).

### Deferred to H8.4 / H8.5 (as of H8.3)

H8.4 (Fleet MRO Intelligence: maintenance recommendations, work-order
prioritization, candidate ranking, scheduling, parts planning,
compliance/maintenance conflict resolution) and H8.5 (Fleet Readiness &
Operational Context: readiness rollup redesign, operational decision
scoring, AOG optimization, fleet availability optimization) are
explicitly out of scope for H8.3 and were not started as of that
milestone. H8.4 is implemented below.

## H8.4: Fleet MRO Intelligence

**H8.4 aggregates existing H7 asset-level MRO intelligence into fleet
context. It does not create, modify, approve, schedule, or execute
maintenance actions.**

H8.4 (`app.services.intelligence.cross_asset_intelligence_service
.evaluate_fleet_mro_aggregation`, contract:
`app.schemas.fleet_intelligence.FleetMROContext`) is a descriptive,
read-time AGGREGATION of H7's own asset-scoped MRO intelligence
(`app.services.mro_intelligence_service`) across the fleet, composed with
H8.2's M7 signal aggregation and H8.3's fleet correlation. It introduces
no new maintenance-candidate generation, compliance evaluation, readiness
calculation, conflict detection, scheduling, or work-order logic.

### Ownership

- **H7** (`app.services.mro_intelligence_service`) remains the sole
  owner of: `MaintenanceIntelligenceCandidate` generation
  (`generate_maintenance_candidates`), compliance-impact classification
  (`get_compliance_impact`), readiness-impact classification
  (`get_readiness_impact`), operational-impact classification
  (`get_operational_impact`), conflict detection (`detect_conflicts`),
  and candidate lifecycle mutation (`review_candidate`/
  `accept_candidate`/`reject_candidate`/`defer_candidate`/
  `reconcile_asset_mro_intelligence`). H8.4 calls only H7's READ
  functions (`get_compliance_impact`, `get_readiness_impact`,
  `detect_conflicts`) and reads H7's own persisted
  `MaintenanceIntelligenceCandidate` table directly. It never calls any
  H7 lifecycle mutation.
- **M7** (`app.services.intelligence.proactive_intelligence_service`)
  remains the sole owner of proactive signal detection/severity/
  lifecycle/attention ranking; H8.4 reuses H8.2's own bulk-read signal
  aggregation (`_compute_fleet_signal_summary`) for the attention
  comparison, never recomputing it.
- **H8.3** (`evaluate_fleet_hums_correlation`) remains the sole owner of
  the M7/H4/H5/H6 correlation; H8.4 calls it as-is to determine which
  assets have HUMS evidence, for the no-inference safety boundary below.

### Candidate aggregation

`_aggregate_mro_candidates` bulk-queries
`MaintenanceIntelligenceCandidate` for the organization across ALL
statuses (one query, no per-asset loop) and buckets rows by H7's OWN
vocabulary:

- `by_status`: full lifecycle counts (OPEN/UNDER_REVIEW/ACCEPTED/
  REJECTED/DEFERRED/RESOLVED) -- reporting only, H8.4 never transitions a
  status.
- `by_severity` / `by_type`: computed over the ACTIVE subset only
  (OPEN/UNDER_REVIEW/DEFERRED), mirroring H7's own
  `_list_open_candidates` definition of "currently relevant". Uses H7's
  own `MROCandidatePriority` and `MROCandidateType` values verbatim -- no
  second severity/type scale is introduced.
- `affected_asset_count` / `affected_component_count`: distinct
  `asset_id`/`component_id` across all candidates.

Zero candidates for an organization with registered assets is a valid
`AVAILABLE` result (the query itself succeeded), never `DATA_UNAVAILABLE`
-- that state is reserved for when the organization has no registered
fleet assets at all.

### Component correlation

`_correlate_mro_components` groups ACTIVE candidates by
`component_id`, joins to `Component` for `component_type` context, and
reports `candidate_count`/`affected_asset_count`/`candidate_types` per
component. Language is strictly "associated with N existing MRO
intelligence candidates" -- never "defective"/"failed".

### Compliance impact aggregation

`ComplianceObligation` carries no persisted "impact" field to bulk-read
directly (H7's compliance-impact mapping is computed at read time from
`ComplianceObligation.status`), so `_aggregate_mro_compliance_impact`
calls H7's own `get_compliance_impact` per asset, BOUNDED to the first
`_MAX_MRO_PER_ASSET_LOOKUPS` (50) assets with an ACTIVE candidate --
mirroring H8.3's `_MAX_TWIN_LOOKUPS` precedent for an asset-scoped H7/H6
function with no bulk path. H7's `UNKNOWN` overall_impact (no compliance
obligations found -- "evidence missing") is tallied separately as
`evidence_missing_asset_count` and is NEVER folded into
`NON_COMPLIANT` -- this is asserted directly by
`test_compliance_impact_evidence_missing_never_becomes_non_compliant` in
`tests/integration/test_h8_4_fleet_mro_intelligence.py`.

### Readiness impact aggregation

`_aggregate_mro_readiness_impact` calls H7's own `get_readiness_impact`
per bounded asset and reports TWO SEPARATE distributions --
`by_readiness_impact` (H7's own classifier output) and
`by_authoritative_readiness_state` (the untouched authoritative
`readiness_state` from `readiness_intelligence_service`) -- mirroring H7's
own `ReadinessImpactResult` convention. They are never merged into a
single field or a new fleet readiness score.

### Operational impact aggregation

`_aggregate_mro_operational_impact` counts H7's OWN persisted
`MaintenanceIntelligenceCandidate.operational_impact` field directly off
the already-bulk-fetched ACTIVE candidates -- no per-asset H7 call is
needed here since the field is already persisted on the candidate row.
H7 currently sets this field to `None` at candidate creation (see
`generate_maintenance_candidates`); those rows are bucketed `"NOT_SET"`
rather than silently dropped or assumed `LOW`. No independent
optimization/availability score is computed.

### Conflict aggregation

`detect_conflicts` has no bulk path (conflicts are computed at read time,
never persisted), so `_aggregate_mro_conflicts` calls H7's own
`detect_conflicts` per bounded asset (same 50-asset cap and same bounded
set as compliance/readiness) and tallies `conflict_count` and
`by_check_type` (H7's own check names: `DIGITAL_TWIN_CONSISTENCY`,
`READINESS_VS_COMPLIANCE`, `DIAGNOSTIC_VS_MAINTENANCE`,
`COMPONENT_CONFIGURATION`, `PROGNOSTIC_FRESHNESS`,
`COMPLIANCE_VS_EVIDENCE`). Conflicts are reported only -- H8.4 never
calls anything that resolves or mutates a conflict.

### Fleet maintenance "attention" -- two separate evidence streams

`attention_comparison` (`FleetMROAttentionComparison`) exposes H7's
candidate priority distribution and H8.2's M7 signal severity
distribution SIDE BY SIDE, explicitly documented as never combined into
a single "Fleet Maintenance Priority/Risk/Urgency Score" -- H8.4
introduces no such score.

### H8.3 integration and the critical no-inference safety boundary

`_identify_hums_only_assets` is the most important function in H8.4. It
takes H8.3's own `evaluate_fleet_hums_correlation` output (asset-level
M7/H4/H5 evidence, unmodified) and the FULL set of asset IDs that have
ANY H7 `MaintenanceIntelligenceCandidate` (any status, not just active --
even a RESOLVED/REJECTED candidate means H7 has already evaluated that
asset). For every H8.3-affected asset that is NOT in that candidate-asset
set, H8.4 emits a `HUMSOnlyAssetEntry` carrying ONLY H8.3's own
already-computed evidence counts (`active_signal_count`,
`diagnostic_candidate_count`, `prognostic_record_count`,
`has_rul_estimate`) plus an explicit note that no H7 candidate exists for
that asset and none is implied.

This means: if an M7 signal, H4 diagnostic candidate, or H5 prognostic
record exists for an asset but H7 has never generated a
`MaintenanceIntelligenceCandidate` for it, H8.4 reports the HUMS evidence
under `hums_only_assets` and NOWHERE else -- it is never counted in
`candidates`, never appears in `component_correlations`, and the
`hums_only_assets` entry's own language is strictly descriptive
("HUMS ... evidence is reported for context only; no maintenance
candidate is implied"), never "maintenance required"/"recommend
maintenance"/an affirmative claim that a candidate exists.

Tested directly in `tests/integration/test_h8_4_fleet_mro_intelligence.py`:
`test_hums_evidence_without_candidate_is_context_only`,
`test_hums_evidence_and_diagnostic_without_candidate`,
`test_candidate_with_hums_correlation_shown_separately_not_merged`,
`test_h7_candidate_without_hums_correlation_shown_alone`, and
`test_resolved_candidate_still_excludes_asset_from_hums_only` (a
non-active candidate still counts as "H7 has looked at this asset" and
must not resurface as HUMS-only context).

### Tenant isolation

`evaluate_fleet_mro_aggregation(db, organization_id=...)` filters every
bulk query (Asset, MaintenanceIntelligenceCandidate, Component) and every
bounded per-asset H7 call by `organization_id`, matching H8.0-H8.3's
existing pattern. `CurrentUser.organization_id` is the only source for
this value at any future call site.

### Safety boundary

H8.4 never calls `generate_maintenance_candidates`, `accept_candidate`,
`reject_candidate`, `review_candidate`, `defer_candidate`, or
`reconcile_asset_mro_intelligence` -- verified by
`test_no_calls_to_h7_lifecycle_mutation_functions`, a source-scan test.
No `db.add`/`session.add`/`.commit()` call exists anywhere in the H8.4
extension -- verified by `test_no_db_mutation_calls_in_service_source`.
`test_aggregation_does_not_persist_results` additionally asserts
`db_session.dirty` is unchanged after a call.

### Data lineage

- `candidates.*` -- direct bulk read of H7's own
  `MaintenanceIntelligenceCandidate` table; every count traces back to a
  specific H7-persisted row.
- `component_correlations` -- H7 candidate rows joined to `Component`
  for `component_type` only (ID/type lookup, never copied business
  logic).
- `compliance_impact` / `readiness_impact` / `conflicts` -- H7's own
  read functions (`get_compliance_impact`/`get_readiness_impact`/
  `detect_conflicts`), called verbatim, bounded per-asset.
- `operational_impact` -- H7's own persisted
  `MaintenanceIntelligenceCandidate.operational_impact` field.
- `attention_comparison.proactive_signal_severity_distribution` -- H8.2's
  own bulk-read M7 signal aggregation, reused as-is.
- `hums_only_assets` -- H8.3's own `evaluate_fleet_hums_correlation`
  output, reused as-is.

### Database

Zero new migrations, zero new tables. H8.4 reads H7's existing
`mro_intelligence_candidates` table and calls H7's existing service
functions; nothing new is persisted.

### API / Frontend / LISA

No new public route. No frontend changes. No LISA tools. H8.4 is an
internal service function only, consumed by a future H8.6 consolidated
Fleet Intelligence API.

### Performance / N+1 avoidance

`MaintenanceIntelligenceCandidate`, `Asset`, and `Component` are each
fetched with exactly one bulk query, composed in Python. Operational
impact aggregation reads a field already present on the bulk-fetched
candidate rows -- no additional query. The only per-asset calls are the
three BOUNDED H7 read functions (`get_compliance_impact`,
`get_readiness_impact`, `detect_conflicts`), each capped at
`_MAX_MRO_PER_ASSET_LOOKUPS` (50) and scoped to the same
active-candidate-bearing asset set -- never the whole fleet. Beyond the
cap, the aggregation's `explanation` field states the limitation
explicitly rather than silently truncating.

### Known limitations

- The three bounded per-asset H7 calls (compliance/readiness/conflicts)
  are, worst case, up to 150 individual service calls (3 x 50) when a
  fleet has 50+ assets with active candidates -- each of those H7
  functions internally calls further HUMS/compliance reads. This mirrors
  H8.3's accepted per-asset digital-twin lookup limitation and is
  documented rather than hidden; a true bulk compliance/readiness/
  conflict read path does not exist in H7 today.
- `operational_impact` aggregation reflects H7's current behavior of
  leaving `operational_impact=None` on every candidate at creation time
  (see `generate_maintenance_candidates`) -- most candidates will
  currently bucket into `"NOT_SET"` until a future H7 change populates
  this field at creation.
- `evidence_completeness=INSUFFICIENT_DATA` from H8.3 (reused as-is via
  `hums_only_assets`' source correlation) remains defined but
  effectively unreachable, per H8.3's own documented limitation.

### Deferred to H8.5 / H8.6

H8.5 (Fleet Readiness & Operational Context: a new fleet readiness
engine, availability/AOG optimization, operational decision scoring,
scheduling optimization) and H8.6 (the final consolidated Fleet
Intelligence API) are explicitly out of scope for H8.4 and were not
started.
