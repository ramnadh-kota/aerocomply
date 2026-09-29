"""0061: Suite -> Plan -> Subscription Hierarchy & Constraints.

Revises: 0060
Create Date: 2026-09-29

Changes:
1. Seed the canonical product suites if not present:
   - AIRCRAFT ("Aircraft Suite")
   - DRONE_UAV ("Drone / UAV Suite")
   - HELICOPTER ("Helicopter Suite")
   - EVTOL_AAM ("eVTOL / AAM Suite")
2. Add icon column to product_suites if missing.
3. Add suite_id column to subscriptions (nullable FK -> product_suites.id).
4. Backfill plans.suite_id for existing plans based on asset_scope or default.
5. Make plans.suite_id NOT NULL.
6. Drop single-column unique constraint on plans.code and create composite
   unique constraint uq_plans_suite_id_code on ("suite_id", "code").
7. Backfill subscriptions.suite_id from plans.suite_id.
"""

from collections.abc import Sequence
import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061"
down_revision: str | None = "0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add icon column to product_suites if not exists
    op.add_column("product_suites", sa.Column("icon", sa.String(length=64), nullable=True))

    # 2. Add suite_id to subscriptions
    op.add_column(
        "subscriptions",
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_subscriptions_suite_id", "subscriptions", ["suite_id"])
    op.create_foreign_key(
        "fk_subscriptions_suite_id_product_suites",
        "subscriptions",
        "product_suites",
        ["suite_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 3. Seed canonical suites in product_suites if they don't already exist
    bind = op.get_bind()
    
    canonical_suites = [
        {
            "id": uuid.uuid4(),
            "code": "DRONE_UAV",
            "name": "Drone / UAV Suite",
            "description": "Unmanned aerial vehicles, autonomous systems, and fleet operations.",
            "icon": "drone",
            "display_order": 1,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "AIRCRAFT",
            "name": "Aircraft Suite",
            "description": "Fixed-wing commercial, private, and transport aircraft operations and engineering.",
            "icon": "plane",
            "display_order": 2,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "HELICOPTER",
            "name": "Helicopter Suite",
            "description": "Rotary-wing aircraft, emergency medical services, and utility operations.",
            "icon": "helicopter",
            "display_order": 3,
            "is_active": True,
        },
        {
            "id": uuid.uuid4(),
            "code": "EVTOL_AAM",
            "name": "eVTOL / AAM Suite",
            "description": "Electric vertical takeoff and landing, advanced air mobility, and urban air transit.",
            "icon": "evtol",
            "display_order": 4,
            "is_active": True,
        },
    ]

    for suite_data in canonical_suites:
        existing = bind.execute(
            sa.text("SELECT id FROM product_suites WHERE code = :code"),
            {"code": suite_data["code"]},
        ).fetchone()
        if existing is None:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO product_suites (id, code, name, description, icon, display_order, is_active, created_at, updated_at)
                    VALUES (:id, :code, :name, :description, :icon, :display_order, :is_active, NOW(), NOW())
                    """
                ),
                suite_data,
            )

    # 4. Backfill plans.suite_id
    # Map any existing legacy plans to matching suite or default DRONE_UAV
    bind.execute(
        sa.text(
            """
            UPDATE plans
            SET suite_id = (SELECT id FROM product_suites WHERE code = 'AIRCRAFT' LIMIT 1)
            WHERE suite_id IS NULL AND (UPPER(asset_scope) = 'AIRCRAFT' OR UPPER(code) LIKE '%AIRCRAFT%')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE plans
            SET suite_id = (SELECT id FROM product_suites WHERE code = 'HELICOPTER' LIMIT 1)
            WHERE suite_id IS NULL AND (UPPER(asset_scope) = 'HELICOPTER' OR UPPER(code) LIKE '%HELICOPTER%')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE plans
            SET suite_id = (SELECT id FROM product_suites WHERE code = 'EVTOL_AAM' LIMIT 1)
            WHERE suite_id IS NULL AND (UPPER(asset_scope) IN ('EVTOL', 'EVTOL_AAM') OR UPPER(code) LIKE '%EVTOL%')
            """
        )
    )
    # Default remaining null suite_id to DRONE_UAV
    bind.execute(
        sa.text(
            """
            UPDATE plans
            SET suite_id = (SELECT id FROM product_suites WHERE code = 'DRONE_UAV' LIMIT 1)
            WHERE suite_id IS NULL
            """
        )
    )

    # 5. Make plans.suite_id NOT NULL
    op.alter_column("plans", "suite_id", nullable=False)

    # 6. Replace single-column unique constraint on plans.code with composite
    # UNIQUE(suite_id, code). IF EXISTS (not try/except): a failed statement
    # aborts the whole Postgres transaction, so swallowing the exception
    # left later statements failing with InFailedSqlTransaction.
    op.execute("ALTER TABLE plans DROP CONSTRAINT IF EXISTS uq_plans_code")
    op.execute("DROP INDEX IF EXISTS ix_plans_code")
    op.create_index("ix_plans_code", "plans", ["code"], unique=False)
    op.create_unique_constraint("uq_plans_suite_id_code", "plans", ["suite_id", "code"])

    # 7. Backfill subscriptions.suite_id from plans.suite_id
    bind.execute(
        sa.text(
            """
            UPDATE subscriptions s
            SET suite_id = p.suite_id
            FROM plans p
            WHERE s.plan_id = p.id AND s.suite_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("uq_plans_suite_id_code", "plans", type_="unique")
    # Restore the 0024 shape: UNIQUE constraint uq_plans_code + plain index.
    # NOTE: fails if two suites already hold plans with the same code; rename
    # one before downgrading.
    op.create_unique_constraint("uq_plans_code", "plans", ["code"])
    op.alter_column("plans", "suite_id", nullable=True)

    op.drop_constraint("fk_subscriptions_suite_id_product_suites", "subscriptions", type_="foreignkey")
    op.drop_index("ix_subscriptions_suite_id", table_name="subscriptions")
    op.drop_column("subscriptions", "suite_id")
    op.drop_column("product_suites", "icon")
