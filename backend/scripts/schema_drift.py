"""Model <-> database schema drift, as stable comparable keys.

Used by tests/integration/test_schema_drift_guard.py and for regenerating the accepted baseline:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.schema_drift > tests/integration/schema_drift_baseline.json

(run it against a database freshly migrated with `alembic upgrade head`, never a long-lived dev DB).

A key is [kind, table, name]. `kind` follows Alembic's autogenerate vocabulary:
  add_index / add_fk / add_column / add_table / add_constraint   the MODEL declares it, the DB lacks it  (may be a real gap)
  remove_index / remove_fk / remove_column / remove_constraint   the DB has it, the MODEL does not say so (usually harmless)
  modify_nullable / modify_type                                   the two disagree about a column
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection


def _flatten(diff: list[Any]) -> list[tuple]:
    flat: list[tuple] = []
    for d in diff:
        flat.extend(d if isinstance(d, list) else [d])
    return flat


def _key(item: tuple) -> list[str]:
    kind = item[0]
    if kind in ("add_index", "remove_index"):
        idx = item[1]
        return [kind, idx.table.name, idx.name or ",".join(c.name for c in idx.columns)]
    if kind == "add_fk":
        fk = item[1]
        return [kind, fk.parent.name, ",".join(c.name for c in fk.columns) + "->" + ",".join(e.target_fullname for e in fk.elements)]
    if kind == "remove_fk":
        fk = item[1]
        return [kind, fk.table.name, ",".join(fk.column_keys) + "->" + (fk.referred_table.name if fk.referred_table is not None else "?")]
    if kind == "modify_nullable":
        return [kind, item[2], item[3]]
    if kind == "modify_type":
        return [kind, item[2], item[3]]
    if kind == "remove_column":
        return [kind, item[2], item[3].name]
    if kind in ("add_column",):
        return [kind, item[2], item[3].name]
    if kind in ("remove_constraint", "add_constraint"):
        cn = item[1]
        return [kind, cn.table.name, cn.name or type(cn).__name__]
    if kind in ("add_table", "remove_table"):
        return [kind, item[1].name, ""]
    return [kind, str(item[1])[:60], ""]


def drift_keys(connection: Connection) -> list[list[str]]:
    import app.models  # noqa: F401  (registers every model on Base.metadata)
    from app.db.base import Base

    ctx = MigrationContext.configure(connection, opts={"compare_type": True})
    return sorted(_key(i) for i in _flatten(compare_metadata(ctx, Base.metadata)))


if __name__ == "__main__":
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        json.dump(drift_keys(conn), sys.stdout, indent=0)
