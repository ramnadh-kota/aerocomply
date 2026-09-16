"""Phase 18.2: deterministic, idempotent seed for the initial platform
product catalog.

Follows the same "standalone script with direct DATABASE_URL access, safe
to re-run" pattern already established by scripts/create_platform_admin.py
-- Plans/PlanFeatures are likewise never seeded by a migration in this
codebase (see app/services/plan_service.py), only ever created through the
platform admin API or a script like this one, so this matches existing
convention rather than inventing a new one.

Seeds exactly ONE truthful suite/module/page/feature, matching real,
already-existing backend code (app/api/v1/work_orders.py,
app/services/work_order_service.py) rather than inventing a larger,
speculative catalog. Future catalog entries (Drone, additional MRO domains,
etc.) are out of this milestone's scope -- add them the same way, one
deliberate seed/admin-API call at a time, not by expanding this script.

Usage (reads DATABASE_URL from the environment, same as the app):

    DATABASE_URL=postgresql+psycopg://... python scripts/seed_product_catalog.py

Safe to re-run: each entity is looked up by its stable `code` first: if it
already exists, this script reports it and moves on without modifying
anything.
"""

import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.product_catalog import (  # noqa: E402
    ProductFeature,
    ProductModule,
    ProductPage,
    ProductSuite,
)

_CATALOG = {
    "suite": {
        "code": "maintenance",
        "name": "Maintenance",
        "description": "Fleet maintenance operations.",
    },
    "module": {
        "code": "maintenance_operations",
        "name": "Maintenance Operations",
        "description": "Work order creation, tracking, and task execution.",
    },
    "page": {
        "code": "work_orders",
        "name": "Work Orders",
        "description": "The work order list and detail views.",
        "route": "/maintenance/work-orders",
    },
    "feature": {
        "code": "work_order_management",
        "name": "Work Order Management",
        "description": "Create, track, and manage maintenance work orders.",
    },
}


def _get_or_create_suite(db: Session) -> ProductSuite:
    spec = _CATALOG["suite"]
    existing = db.execute(
        select(ProductSuite).where(ProductSuite.code == spec["code"])
    ).scalar_one_or_none()
    if existing is not None:
        print(f"Suite {spec['code']!r} already exists (id={existing.id}). Skipping.")
        return existing
    suite = ProductSuite(**spec)
    db.add(suite)
    db.flush()
    print(f"Created suite {spec['code']!r} (id={suite.id}).")
    return suite


def _get_or_create_module(db: Session, suite: ProductSuite) -> ProductModule:
    spec = _CATALOG["module"]
    existing = db.execute(
        select(ProductModule).where(ProductModule.code == spec["code"])
    ).scalar_one_or_none()
    if existing is not None:
        print(f"Module {spec['code']!r} already exists (id={existing.id}). Skipping.")
        return existing
    module = ProductModule(suite_id=suite.id, **spec)
    db.add(module)
    db.flush()
    print(f"Created module {spec['code']!r} (id={module.id}).")
    return module


def _get_or_create_page(db: Session, module: ProductModule) -> ProductPage:
    spec = _CATALOG["page"]
    existing = db.execute(
        select(ProductPage).where(ProductPage.code == spec["code"])
    ).scalar_one_or_none()
    if existing is not None:
        print(f"Page {spec['code']!r} already exists (id={existing.id}). Skipping.")
        return existing
    page = ProductPage(module_id=module.id, **spec)
    db.add(page)
    db.flush()
    print(f"Created page {spec['code']!r} (id={page.id}).")
    return page


def _get_or_create_feature(db: Session, module: ProductModule) -> ProductFeature:
    spec = _CATALOG["feature"]
    existing = db.execute(
        select(ProductFeature).where(ProductFeature.code == spec["code"])
    ).scalar_one_or_none()
    if existing is not None:
        print(f"Feature {spec['code']!r} already exists (id={existing.id}). Skipping.")
        return existing
    feature = ProductFeature(module_id=module.id, **spec)
    db.add(feature)
    db.flush()
    print(f"Created feature {spec['code']!r} (id={feature.id}).")
    return feature


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        suite = _get_or_create_suite(db)
        module = _get_or_create_module(db, suite)
        _get_or_create_page(db, module)
        _get_or_create_feature(db, module)
        db.commit()
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
