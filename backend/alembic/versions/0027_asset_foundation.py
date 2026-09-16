"""Phase 1A: introduce the generic Asset foundation and backfill Aircraft.

Written by hand, matching 0024/0025/0026 (autogenerate is currently broken
on this codebase -- app/models/warehouse.py's Location model is not imported
early enough for FK metadata resolution -- unrelated and out of scope here).

Adds two new, purely additive tables (`assets`, `aircraft_details`) plus one
new nullable column on the existing `aircraft` table (`asset_id`). No
existing table's structure changes, no existing FK is repointed, and no
existing MRO domain table (work_orders, compliance, deferred_items,
aog_events, maintenance_requirements, procurement_requests, purchase_orders)
is touched -- they continue to reference `aircraft.id` exactly as before.
See docs/ARCHITECTURE_ASSET_FOUNDATION.md for the full rationale.

Backfill: for every existing `aircraft` row, insert one `assets` row
(asset_type='AIRCRAFT', copying organization_id/registration/status/
created_at) and one `aircraft_details` row (copying msn/aircraft_type),
then point `aircraft.asset_id` at the new asset. manufacturer/model/
serial_number are left NULL -- the existing Aircraft schema has no reliable
source for them and this migration must not invent values (Phase 1A design,
"IMPORTANT: MANUFACTURER / MODEL / SERIAL NUMBER").

The backfill correlates each new `assets` row back to its source `aircraft`
row via (organization_id, registration), which is safe because migration
0023 already enforces `uq_aircraft_organization_id_registration` at the
database level -- that pair is guaranteed unique across all of `aircraft`.

Post-backfill, a defensive integrity check (a single DO block) verifies the
backfill actually did what it claims before the migration is allowed to
succeed -- every `aircraft` row has a non-null `asset_id`, that asset is
AIRCRAFT-typed, belongs to the same organization as the Aircraft, and has
exactly one AircraftDetail row. Every check is scoped by joining FROM
`aircraft` outward, never by a blanket `COUNT(*) FROM assets` -- so it can
never be tripped up by an unrelated Asset row that isn't linked from any
Aircraft (there should be none at this point in migration history, since
this migration is the first writer of this table, but the check is written
to stay correct even if that ever changes). A violation raises a real
Postgres exception, which aborts the migration's transaction -- nothing is
left half-backfilled.

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("manufacturer", sa.String(128), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("serial_number", sa.String(128), nullable=True),
        sa.Column("registration", sa.String(16), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "organization_id", "registration", name="uq_assets_organization_id_registration"
        ),
    )
    op.create_index("ix_assets_organization_id", "assets", ["organization_id"])

    op.create_table(
        "aircraft_details",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("msn", sa.String(64), nullable=False),
        sa.Column("aircraft_type", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"], name="fk_aircraft_details_asset_id_assets"
        ),
    )

    op.add_column("aircraft", sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_aircraft_asset_id_assets", "aircraft", "assets", ["asset_id"], ["id"]
    )
    op.create_unique_constraint("uq_aircraft_asset_id", "aircraft", ["asset_id"])

    # Backfill: one Asset + one AircraftDetail per existing Aircraft row.
    op.execute(
        """
        INSERT INTO assets (id, created_at, organization_id, asset_type, registration, status)
        SELECT gen_random_uuid(), a.created_at, a.organization_id, 'AIRCRAFT', a.registration, a.status
        FROM aircraft a
        """
    )
    op.execute(
        """
        UPDATE aircraft
        SET asset_id = assets.id
        FROM assets
        WHERE assets.asset_type = 'AIRCRAFT'
          AND assets.organization_id = aircraft.organization_id
          AND assets.registration = aircraft.registration
        """
    )
    op.execute(
        """
        INSERT INTO aircraft_details (asset_id, msn, aircraft_type)
        SELECT aircraft.asset_id, aircraft.msn, aircraft.aircraft_type
        FROM aircraft
        WHERE aircraft.asset_id IS NOT NULL
        """
    )

    # Defensive post-backfill integrity check (Phase 1A hardening). Every
    # query is scoped by joining FROM aircraft outward -- never a blanket
    # COUNT(*) FROM assets -- so it only ever validates the rows this
    # backfill itself is responsible for, never an unrelated Asset row.
    # Each RAISE EXCEPTION aborts the migration's transaction, so a
    # violation here means nothing gets left half-backfilled.
    op.execute(
        """
        DO $$
        DECLARE
            bad_count bigint;
        BEGIN
            -- (1) + (3): every Aircraft row must now have asset_id set.
            SELECT COUNT(*) INTO bad_count FROM aircraft WHERE asset_id IS NULL;
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft row(s) have no asset_id',
                    bad_count;
            END IF;

            -- (2) + (6): every Aircraft's linked Asset must have exactly one
            -- AircraftDetail (uq on aircraft.asset_id + aircraft_details'
            -- shared-PK asset_id together make "exactly one" structural
            -- once this LEFT JOIN finds none missing).
            SELECT COUNT(*) INTO bad_count
            FROM aircraft ac
            LEFT JOIN aircraft_details ad ON ad.asset_id = ac.asset_id
            WHERE ad.asset_id IS NULL;
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft row(s) have an asset with no AircraftDetail',
                    bad_count;
            END IF;

            -- (4): every Aircraft's linked Asset must be AIRCRAFT-typed.
            SELECT COUNT(*) INTO bad_count
            FROM aircraft ac
            JOIN assets a ON a.id = ac.asset_id
            WHERE a.asset_type <> 'AIRCRAFT';
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft row(s) linked to a non-AIRCRAFT asset',
                    bad_count;
            END IF;

            -- (5): organization_id must match between Aircraft and its Asset.
            SELECT COUNT(*) INTO bad_count
            FROM aircraft ac
            JOIN assets a ON a.id = ac.asset_id
            WHERE a.organization_id <> ac.organization_id;
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft row(s) whose asset belongs to a different organization',
                    bad_count;
            END IF;

            -- (7): every AircraftDetail row this backfill created must
            -- reference a real Asset. Already guaranteed by
            -- fk_aircraft_details_asset_id_assets -- checked explicitly here
            -- too so a violation fails with this block's clear message
            -- rather than a bare constraint-violation stack trace.
            SELECT COUNT(*) INTO bad_count
            FROM aircraft_details ad
            LEFT JOIN assets a ON a.id = ad.asset_id
            WHERE a.id IS NULL;
            IF bad_count > 0 THEN
                RAISE EXCEPTION
                    'Asset foundation backfill failed: % aircraft_details row(s) reference a non-existent asset',
                    bad_count;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_aircraft_asset_id", "aircraft", type_="unique")
    op.drop_constraint("fk_aircraft_asset_id_assets", "aircraft", type_="foreignkey")
    op.drop_column("aircraft", "asset_id")
    op.drop_table("aircraft_details")
    op.drop_index("ix_assets_organization_id", table_name="assets")
    op.drop_table("assets")
