"""0070: per-sensor HUMS vibration thresholds.

Revises: 0069
Additive nullable columns. NULL/NULL = use the platform default limits (a generic starting point, never an OEM limit).
Downgrade drops the columns (configured limits would be lost; exceedances already recorded keep their own threshold).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070"
down_revision: str | None = "0069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hums_sensors", sa.Column("warning_threshold", sa.Float(), nullable=True))
    op.add_column("hums_sensors", sa.Column("critical_threshold", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_hums_sensor_thresholds", "hums_sensors",
        "(warning_threshold IS NULL AND critical_threshold IS NULL) OR "
        "(warning_threshold IS NOT NULL AND critical_threshold IS NOT NULL "
        "AND warning_threshold > 0 AND critical_threshold > warning_threshold)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_hums_sensor_thresholds", "hums_sensors", type_="check")
    op.drop_column("hums_sensors", "critical_threshold")
    op.drop_column("hums_sensors", "warning_threshold")
