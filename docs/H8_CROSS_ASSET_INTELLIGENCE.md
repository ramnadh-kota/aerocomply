# H8.1 — M14 Cross-Asset Intelligence Extension

Status: FOUNDATION PHASE ONLY. Extends `app/services/intelligence/cross_asset_intelligence_service.py`
in place — no competing service was created.

## What M14 (extended) is responsible for

`evaluate_cross_asset_intelligence(db, organization_id=...)` returns a
`FleetIntelligenceSummary` dataclass. It is a read-only, query-time
aggregation over existing authoritative PostgreSQL records, strictly
tenant-scoped. It computes NO new health score, diagnosis, or RUL — every
number it returns is either a direct aggregate of an authoritative table or
a bucket count over an already-computed/persisted result from H3/H4/H5/M7.

## Metrics implemented (H8.1)

| Metric | Data source | Notes |
|---|---|---|
| `health_distribution` | `ProactiveSignalRecord` (signal_type=`HUMS_HEALTH_DEGRADATION`, open statuses) + `HUMSSensor` presence | Buckets: healthy / degraded (open MEDIUM) / attention (open HIGH or CRITICAL) / unknown (no HUMS sensors — no health basis). Single bulk query, no per-asset H3 recompute. |
| `hums_coverage` | `HUMSSensor` | assets_total / assets_with_hums / assets_without_hums / coverage_percentage |
| `telemetry_freshness` | `TelemetryEventLog` (bulk, grouped by asset) + `telemetry_service.resolve_effective_freshness_policy` | Reuses the EXISTING freshness policy resolution/threshold semantics verbatim — no new threshold invented. |
| `population_statistics` | `Asset`, component/HUMS/telemetry aggregates above | asset_count, active_asset_count, component_count, assets_with_hums, assets_with_recent/stale/missing_telemetry |
| `component_distribution` | `Component` + `HUMSExceedance` (30-day window) | component_type, component_count, affected_component_count. Descriptive only — no failure prediction. |
| `exceedance_distribution` | `HUMSExceedance` (already queried by the pre-existing M14 logic) | total_exceedances, affected_assets, exceedances_by_type, exceedances_by_asset |
| `diagnostic_distribution` | `HUMSDiagnosticCandidate` (bulk query, non-terminal statuses) | diagnostic_candidate_count, affected_assets, by_fault_domain, by_severity. Direct read of H4's own authoritative rows — no independent scoring/classification. |
| `prognostic_distribution` | `HUMSPrognosticRecord` (bulk query, `is_current=True`) | assets_with_rul, rul_distribution (`<25`/`25-100`/`100-500`/`>=500` buckets), low_confidence_count. Direct read of H5's own authoritative rows — no independent RUL calculation. |

## Why `health_distribution` does not call `hums_service.get_asset_health_intelligence`

`get_asset_health_intelligence` (H3) has real write side effects on every
call: it persists health signals (`ProactiveSignalRecord` via
`health_service.sync_health_signal`), diagnostic candidates, and prognostic
records. Looping it once per asset for a fleet-wide read endpoint would (a)
be an unbounded N+1 across the entire fleet on every analytics read, and
(b) trigger authoritative-table writes from what is supposed to be a
read-only analytical layer — unacceptable for H8.1's scope. Instead,
`health_distribution` bulk-queries the *already persisted* M7
`ProactiveSignalRecord` rows that H3 itself writes whenever a component's
health leaves HEALTHY/WATCH, plus one bulk `HUMSSensor` query to know which
assets have a health basis at all. This is a legitimate reuse of an
existing authoritative, already-computed signal rather than a new scoring
algorithm, and requires exactly two queries regardless of fleet size.

## Performance / N+1 review

- `health_distribution`, `hums_coverage`, `component_distribution`,
  `exceedance_distribution`, `diagnostic_distribution`, and
  `prognostic_distribution` are each ONE bulk query (or reuse an
  already-fetched list) — no per-asset loop.
- `telemetry_freshness` bulk-fetches last-received timestamps in one grouped
  query, but still resolves the freshness *policy* per asset (one lightweight,
  indexed lookup per asset) because no bulk "resolve policy for N assets"
  path exists yet in `telemetry_service`. This is an accepted, documented
  limitation for this foundation phase — a later H8 milestone can add a
  bulk policy-resolution helper if fleet sizes make this a bottleneck.

## Metrics deliberately deferred

None of items 1–8 from the H8.1 spec were skipped outright; all eight were
implemented using existing bulk-friendly data paths (see table above). No
new persistence, scoring, or classification logic was introduced for any of
them.

## Limitations

- `active_asset_count` uses `Asset.status not in (RETIRED, INACTIVE, DECOMMISSIONED)`
  as a simple proxy; there is no separate "active" domain concept in this
  codebase today.
- `telemetry_freshness`'s per-asset policy resolution (see above) is O(N)
  in fleet size; acceptable for the foundation phase, flagged for later
  optimization.
- `rul_distribution` buckets are fixed, coarse ranges (`<25`, `25-100`,
  `100-500`, `>=500`) chosen only for descriptive bucketing — they carry no
  certification or maintenance-scheduling meaning.

## What is explicitly NOT part of H8.1

- **M7 is not integrated yet** beyond read-only reuse of its persisted
  `ProactiveSignalRecord` health signals for bucketing — M7's own
  signal-detection/attention-ranking logic is untouched.
- **H7 is not integrated yet.**
- **LISA is not integrated yet.**
- **Frontend is not implemented yet.**

## API

No new public API surface was added. The existing
`GET /commercial/cross-asset-intelligence` route in
`app/api/v1/commercial_platform.py` (gated by `Permission.FLEET_READ`,
unchanged) already returns the `FleetIntelligenceSummary` dataclass
directly, so it automatically serializes the new fields with no route
changes required. The full public H8 fleet API surface (a dedicated
`/fleet/*` router consuming `FleetIntelligenceContext`) is deferred to a
later H8 milestone.
