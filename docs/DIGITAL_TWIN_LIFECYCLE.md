# Digital Asset & Component Twin — Lifecycle (H6)

See `docs/DIGITAL_TWIN_ARCHITECTURE.md` for the architecture and
source-of-truth policy. This document covers component genealogy, the
unified timeline, and the H3/H4/H5 consistency guarantees in more detail.

## Component genealogy

"Where has this component been?" is answered entirely from the existing
`ComponentInstallation` table (`app/models/installation_history.py`,
H1/M17.2C) — every row for a given `component_id`, across every
`asset_id` it has ever pointed to, ordered chronologically:

```
GET /digital-twin/components/{component_id}/genealogy
```

```json
[
  {"asset_id": "...", "asset_registration": "KA-001", "installed_at": "2026-01-10T...", "removed_at": "2026-08-15T...", "is_current": false},
  {"asset_id": "...", "asset_registration": "KA-102", "installed_at": "2026-08-17T...", "removed_at": null, "is_current": true}
]
```

Verified end-to-end in
`tests/integration/test_digital_twin.py::test_component_genealogy_tracks_movement_between_assets`:
a component installed on asset A, removed, and reinstalled on asset B
produces exactly two genealogy entries with the correct `is_current` flags
— demonstrating H6 spec scenario H6-B (component moves between two
aircraft).

## Maintenance-reset integration with H5

H5's reference-baseline strategy (`docs/HUMS_PROGNOSTICS.md`) already
consumes `ComponentInstallation.installed_at` to decide when a degradation
trajectory should restart. H6 doesn't duplicate that logic — it simply
*displays* the same installation records H5 already reads, so a reviewer
looking at the component genealogy and the H5 reference-baseline
explanation are looking at the same underlying facts, never two
independently-derived (and potentially conflicting) stories.

## Usage: lifetime vs. since-install vs. since-overhaul

The H6 spec (section 18) asks for these to be kept distinct rather than
collapsed into one number. Today's implementation surfaces:

- **Asset-level usage** (`DigitalTwinAssetSnapshot.usage`) — total flight
  hours/cycles for the *asset*, via the existing
  `asset_service.get_asset_utilization` (M5.3/M5.13 accounting, already
  handling historical-baseline carry-in correctly).
- **Component-since-install** — the component snapshot's `installed_at`
  field lets a caller compute "usage since this installation" by
  cross-referencing the asset's flight records after that timestamp (the
  same computation H5's `degradation_service.build_usage_trajectory`
  already performs internally for RUL purposes).

**Not yet implemented**: a first-class "component lifetime usage" number
that sums usage across *every* installation span for a component (i.e.
its total accumulated flight hours across every aircraft it's ever flown
on, not just the current one). This would require summing
`flight_service.get_utilization`-style calculations per genealogy span —
a real, bounded computation, but not built in H6 to keep the milestone's
scope to what has actual UI/AI consumers today (per spec section 30: "only
implement endpoints that have real UI/AI consumers"). Documented extension
point.

## Timeline event types

| `event_type` | Source | Meaning |
|---|---|---|
| `ASSET_CREATED` | `Asset.created_at` | Asset record created |
| `COMPONENT_INSTALLED` / `COMPONENT_REMOVED` | `ComponentInstallation` | Installation lifecycle |
| `DIAGNOSTIC_CANDIDATE_GENERATED` | `HUMSDiagnosticCandidate.detected_at` | H4 candidate created |
| `PROGNOSTIC_UPDATED` | `HUMSPrognosticRecord.calculated_at` | H5 RUL/degradation model refreshed |
| `FINDING_CREATED` | `Finding.discovered_at` | MRO finding raised |
| `WORK_ORDER_CREATED` | `WorkOrder.created_at` | Work order opened |

Every event carries `source_type`/`source_id` so a UI can navigate
directly to the authoritative record — the timeline is a lens onto
existing data, not a copy of it.

**Not included** (documented gap, not an oversight): health-state
*transitions* (H3) and diagnostic *status changes* (H4 CONFIRMED/REJECTED)
don't yet appear as distinct timeline entries — only the initial
detection/generation timestamp is surfaced, because H3 doesn't persist a
"health changed at T" event (it's evaluated fresh on each read, per H3's
own architecture) and H4's `updated_at` on a status change isn't yet
threaded into the timeline query. Extension point for a future milestone.

## Consistency checks — what's covered, what isn't

Covered (see `docs/DIGITAL_TWIN_ARCHITECTURE.md` for the full list and
reasoning): sensor-component reference validity, duplicate open
installations, installation/asset mismatch.

**Not covered** (documented, not implemented): "prognostic references
removed component incorrectly" and "health record references nonexistent
asset" from the spec's example list — these would require iterating
`HUMSPrognosticRecord`/health-evaluation inputs against
`Component.deleted_at`/`Asset` existence at scale, which is a reasonable
next increment but wasn't load-bearing for the H6 milestone's core
"prove the aggregation architecture works" goal. The three checks that
*are* implemented were chosen because they're the ones a real bug (or a
future manual data-repair script) is most likely to actually produce,
based on this codebase's existing `partial unique index on removed_at IS
NULL` invariant and the `HUMSSensor.component_id` foreign-key-but-nullable
relationship.

## Rebuild / reconciliation

There is no `rebuild_twin(asset_id)` function, and none is needed: because
no twin state is ever persisted, **every call to `get_asset_snapshot` (or
any other digital_twin_service function) already is a full rebuild from
authoritative data.** There is nothing to reconcile a stale cache against,
because there is no cache. See
`docs/DIGITAL_TWIN_ARCHITECTURE.md`'s "Core principle" section for why
this is the intended design, not a missing feature.

If a future milestone introduces a genuine performance need for a
persisted current-state cache (H6 spec section 53's `HUMSTwinCurrentState`
concept), it must be explicitly derived/rebuildable from these same
functions — never an independent write path.
