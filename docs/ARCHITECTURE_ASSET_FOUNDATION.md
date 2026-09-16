# Asset Foundation (Phase 1A)

Status: implemented (migration 0027). Scope: introduce a generic `Asset`
identity and migrate existing `Aircraft` rows onto it, without touching any
existing MRO workflow table or API. This is the first of several planned
phases toward a unified drone/aircraft asset model (see the Phase 1
architecture design report for the full multi-phase plan) — only Phase 1A is
implemented here.

## Why Asset exists

The product direction requires drones and aircraft to be different asset
types sharing one operational platform (fleet listing, maintenance,
inspection, Lisa queries) rather than becoming two unrelated products. That
requires one stable identity — `Asset` — that every future domain table
(work orders, compliance, flights, …) can eventually key off of regardless
of asset type. Phase 1A introduces only that identity table; it does not yet
repoint any existing domain table to it.

## Why AircraftDetail exists

`Asset` holds only the fields every asset type has in common (tenant
ownership, identity, status, lifecycle). Aircraft-specific fields that have
no meaning for a non-aircraft asset — `msn`, `aircraft_type` — live on a
separate `AircraftDetail` table in a 1:1 relationship with `Asset`, keyed by
a shared primary key (`aircraft_details.asset_id → assets.id`). This mirrors
the split a future `DroneDetail` table will use, so adding a second asset
type later is additive rather than a redesign of `Asset` itself.

## Why Aircraft remains temporarily

`aircraft.id` is referenced by seven existing tables today (`work_orders`,
`aog_events`, `compliance`, `deferred_items`, `maintenance_requirements` ×2,
`procurement_requests`, `purchase_orders`) plus one non-FK reference
(`lisa_conversation_context.current_aircraft_id`). Repointing all of those to
`asset_id` is a separate, larger phase (Phase 1B+) requiring its own
dual-write/backfill/cutover sequence per table. Phase 1A deliberately does
not touch any of them — `Aircraft` stays the system of record for the
existing MRO workflow, unchanged.

## How Aircraft maps to Asset

`aircraft.asset_id` is a new, nullable UUID column with a real foreign key to
`assets.id` and a unique constraint (`uq_aircraft_asset_id`) — a genuine
one-to-one, database-backed mapping, not an application-level dictionary or
an inferred join. Migration 0027 backfills this column for every
pre-existing `Aircraft` row:

1. Insert one `assets` row per `aircraft` row (`asset_type='AIRCRAFT'`,
   copying `organization_id`, `registration`, `status`, `created_at`).
2. Update `aircraft.asset_id` to point at the newly created `assets` row,
   correlating by `(organization_id, registration)` — safe because migration
   0023 already enforces `uq_aircraft_organization_id_registration` at the
   database level, so that pair uniquely identifies one `aircraft` row.
3. Insert one `aircraft_details` row per now-linked `aircraft` row, copying
   `msn` and `aircraft_type`.

`manufacturer`, `model`, and `serial_number` are left `NULL` on every
backfilled `Asset` — the existing `Aircraft` schema has no reliable source
for them, and the backfill must not invent values from `registration`,
`msn`, or `aircraft_type`.

## Why existing MRO foreign keys remain unchanged

Repointing `work_orders.aircraft_id` (and the other six FKs) to `asset_id`
requires a per-table dual-write/backfill/validate/cutover sequence of its
own, and touches services, routes, and Lisa tool handlers that read those
columns. Doing that in the same change as introducing `Asset` would make the
change large, harder to review, and harder to roll back. Phase 1A is scoped
to be purely additive: two new tables, one new nullable column, zero changes
to existing FKs, zero changes to existing API responses.

## Closed gap: new Aircraft rows now dual-write (Phase 1A hardening)

Originally `app/services/aircraft_service.py` (`create_aircraft`) was left
unmodified in the initial Phase 1A implementation — creating an Aircraft
through the existing `/aircraft` API did not create a matching
`Asset`/`AircraftDetail`. This was flagged in the Phase 1A review as a
growing invariant violation and has since been fixed (Phase 1A hardening
pass): `create_aircraft` now creates `Asset`, `AircraftDetail`, and
`Aircraft` together in one transaction (the same `Session`/`db.commit()` it
already used — no second transaction mechanism was introduced). `asset_id`
is never client-supplied; the `Asset` is always created server-side using
the same `organization_id` the caller was already authenticated into. A
failure at any point (including the pre-existing duplicate-registration
race, which can now surface via either `aircraft`'s or `assets`' own unique
constraint) rolls back all three inserts together — see
`backend/tests/integration/test_asset_foundation.py::TestAircraftCreationDualWrite`
for the behavioral coverage, including a test that a failed creation leaves
no orphaned `Asset`/`AircraftDetail` row behind.

`update`/`delete` paths for `Aircraft` do not exist yet in this codebase, so
there is currently no other write path that could drift `Aircraft` and its
`Asset` apart post-creation — if one is added in a later phase, it must
account for keeping `Asset`/`AircraftDetail` in sync too.

Two related items remain **open**, out of scope for this hardening pass and
left for Phase 1B:
- No generic Asset-creation write API exists (by design — see the API
  section below), so nothing outside `create_aircraft` can create an
  `Asset`. Once a generic write path is introduced, it must enforce (at the
  service layer, since the database cannot express this cleanly across two
  tables without a trigger) that an `AIRCRAFT`-typed `Asset` never exists
  without a matching `AircraftDetail`.
- `Aircraft.organization_id == Asset.organization_id`,
  `Aircraft.registration == Asset.registration`,
  `Aircraft.status == Asset.status`, `Aircraft.msn == AircraftDetail.msn`,
  and `Aircraft.aircraft_type == AircraftDetail.aircraft_type` are true at
  creation time but are not database-enforced ongoing invariants (matching
  this codebase's existing `TenantScopedMixin` convention of application-,
  not database-, enforced tenant consistency). This is currently safe only
  because no update endpoint exists for `Aircraft` yet.

## Tenant isolation

`Asset` uses the existing `TenantScopedMixin` — `organization_id` is a
plain, indexed, non-nullable column, **not** a foreign key, matching every
other tenant-scoped table in this codebase (tenant scoping is an
application-layer invariant here, not a database-enforced one — see
`app/db/base.py` and the 0026 migration's docstring for the existing
precedent). `organization_id` is always taken from the authenticated
caller's JWT-derived context (`CurrentUser.organization_id`, via
`app.core.deps.get_current_user`) in every new service function
(`app/services/asset_service.py`) — never from a request body, query
parameter, or URL. `AircraftDetail` does not carry its own
`organization_id`: it is only ever reached through its parent `Asset`, which
the service layer always filters by tenant before returning.

A cross-tenant lookup by ID returns `404 Not Found` (via the existing
`NotFoundError`), matching the codebase's existing convention (a `403` would
confirm the record's existence to an unauthorized tenant) — see
`backend/tests/integration/test_tenancy_isolation.py` for the precedent this
follows, and `test_asset_foundation.py::TestAssetApiTenantIsolation` for the
new coverage.

The `(organization_id, registration)` unique constraint on `assets` is
correctly scoped per-tenant (matching `aircraft`'s existing
`uq_aircraft_organization_id_registration`): the same registration string
may exist in two different organizations, and multiple registration-less
assets may exist within one organization (standard SQL `UNIQUE` treats `NULL`
values as distinct from each other).

## API

`GET /assets` and `GET /assets/{asset_id}` are the only new endpoints —
read-only, reusing `Permission.AIRCRAFT_READ` rather than introducing a new
`asset:read` permission (every `Asset` in this phase is `AIRCRAFT`-typed and
already gated by that permission on `/aircraft`, so a second permission would
grant nothing new yet). No existing `/aircraft/*` endpoint changed. A write
API, a permission dedicated to assets, and endpoints for a second asset type
are explicitly out of scope for Phase 1A.

## What Phase 1B+ still needs to do

- Repoint the seven MRO foreign keys from `aircraft_id` to `asset_id`, one
  table at a time, each with its own dual-write/backfill/validate/cutover
  migration.
- Introduce `DroneDetail`, `Component`/`Battery`, `Flight`,
  `Project`/`ProjectAssetAssignment`.
- Extend Lisa's tool layer to operate against the generic `Asset`
  abstraction.
- Evaluate Postgres Row Level Security once the shared-identity foundation
  (`Asset`) is in place — the cheapest point to add it is before more tables
  accumulate on top, but it was explicitly out of scope for Phase 1A.
