"""Enforce aircraft registration uniqueness per tenant at the database level

Application-level checks (create_aircraft, the bulk import validator)
already reject a duplicate registration within an organization, but
neither was backed by a database constraint — a plain duplicate
registration could previously be inserted through a race (e.g. two
concurrent POST /aircraft or import commits), silently breaking every
downstream assumption that a registration resolves to exactly one
Aircraft (Lisa entity resolution, AOG lookups, assessments).

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-12

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_aircraft_registration", table_name="aircraft")
    op.create_unique_constraint(
        "uq_aircraft_organization_id_registration", "aircraft", ["organization_id", "registration"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_aircraft_organization_id_registration", "aircraft", type_="unique")
    op.create_index("ix_aircraft_registration", "aircraft", ["registration"])
