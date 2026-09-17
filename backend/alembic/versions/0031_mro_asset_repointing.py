"""Phase 18.5 (Asset Foundation Phase 1B): additive asset_id compatibility
columns on the 7 genuinely asset-level MRO relationships identified by the
repository audit -- work_orders, aog_events, compliance_assessments,
deferred_items, maintenance_requirement_applicabilities,
maintenance_accomplishments, procurement_requests, purchase_orders (8
columns across 7 models; purchase_orders' aircraft_id was already
nullable).

Written by hand, matching prior migrations' precedent (autogenerate is
currently broken on this codebase).

Classification performed before this migration (see docs/
ARCHITECTURE_ASSET_FOUNDATION.md for the full writeup): every column added
here represents an operational event/record about a specific physical
asset (an AOG declaration, a compliance determination, a deferred defect, a
work order, a maintenance requirement's applicability/accomplishment, a
procurement/purchase request) -- exactly the kind of relationship Asset
Foundation Phase 1A introduced Asset to eventually own. Two things were
deliberately NOT touched:
  - lisa_conversation_context.current_aircraft_id: ephemeral AI chat
    scratch state, not a domain record -- out of scope.
  - Every other aircraft_id/aircraft.py column (Aircraft itself, and
    genuinely aircraft-specific concepts) -- unchanged.

Purely additive, matching Phase 1A's own precedent: each new asset_id
column is NULLABLE. Aircraft.asset_id is itself nullable (Aircraft remains
fully usable even where unset -- see app/models/aircraft.py's own
docstring), so forcing NOT NULL on any of these new columns would be
unsafe without proof every single referencing row's aircraft has a
mapped asset -- which cannot be guaranteed for historical/edge-case rows.
The backfill below populates asset_id everywhere aircraft.asset_id is
already set and leaves it NULL otherwise, never guessing.

No existing column, constraint, service, or API changes in this
migration -- see this milestone's commit message for why rewiring every
service/router to asset_id is explicitly deferred, not attempted here.

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, fk_constraint_name, index_name)
_TABLES: list[tuple[str, str, str]] = [
    ("work_orders", "fk_work_orders_asset_id_assets", "ix_work_orders_asset_id"),
    ("aog_events", "fk_aog_events_asset_id_assets", "ix_aog_events_asset_id"),
    (
        "compliance_assessments",
        "fk_compliance_assessments_asset_id_assets",
        "ix_compliance_assessments_asset_id",
    ),
    ("deferred_items", "fk_deferred_items_asset_id_assets", "ix_deferred_items_asset_id"),
    (
        "maintenance_requirement_applicabilities",
        "fk_maintenance_requirement_applicabilities_asset_id_assets",
        "ix_maintenance_requirement_applicabilities_asset_id",
    ),
    (
        "maintenance_accomplishments",
        "fk_maintenance_accomplishments_asset_id_assets",
        "ix_maintenance_accomplishments_asset_id",
    ),
    (
        "procurement_requests",
        "fk_procurement_requests_asset_id_assets",
        "ix_procurement_requests_asset_id",
    ),
    ("purchase_orders", "fk_purchase_orders_asset_id_assets", "ix_purchase_orders_asset_id"),
]


def upgrade() -> None:
    for table, fk_name, ix_name in _TABLES:
        op.add_column(table, sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(fk_name, table, "assets", ["asset_id"], ["id"], ondelete="RESTRICT")
        op.create_index(ix_name, table, ["asset_id"])

        # Backfill only where the referenced aircraft already has a known
        # asset -- never guessed, never forced. aircraft_id is nullable on
        # purchase_orders only; the WHERE clause naturally skips NULL
        # aircraft_id rows there (a purchase order with no aircraft has no
        # asset to backfill from either).
        op.execute(
            f"""
            UPDATE {table} t
            SET asset_id = a.asset_id
            FROM aircraft a
            WHERE t.aircraft_id = a.id AND a.asset_id IS NOT NULL
            """
        )


def downgrade() -> None:
    for table, fk_name, ix_name in _TABLES:
        op.drop_index(ix_name, table_name=table)
        op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_column(table, "asset_id")
