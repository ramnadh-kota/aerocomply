"""Phase 18.2: deterministic, idempotent seed for the initial platform
product catalog.

Follows the same "standalone script with direct DATABASE_URL access, safe
to re-run" pattern already established by scripts/create_platform_admin.py
-- Plans/PlanFeatures are likewise never seeded by a migration in this
codebase (see app/services/plan_service.py), only ever created through the
platform admin API or a script like this one, so this matches existing
convention rather than inventing a new one.

Seeds truthful suite/module/page/feature rows, each matching real,
already-existing backend code -- no speculative catalog entries. Started
with exactly one (Maintenance/Work Orders, app/api/v1/work_orders.py).
M21.5 added two more, following the same one-deliberate-entry-at-a-time
convention this docstring originally called for: Drone Operations
(app/api/v1/drones.py) and Procurement (app/api/v1/procurement.py) -- both
real routers with real service-layer depth, now also backing the new
require_feature() enforcement wired onto their GET endpoints (see
app/core/deps.py's require_feature and M21_5_REPORT.md). Additional catalog
entries should keep following this same pattern: one script edit per real,
already-existing backend domain, never a speculative one.

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

_CATALOG_ENTRIES = [
    {
        "suite": {
            "code": "maintenance",
            "name": "Maintenance & MRO",
            "description": "Fleet maintenance and engineering operations.",
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
    },
    {
        "suite": {
            "code": "maintenance",
            "name": "Maintenance & MRO",
            "description": "Fleet maintenance and engineering operations.",
        },
        "module": {
            "code": "maintenance_inspections",
            "name": "Inspections",
            "description": "Aircraft and airframe inspection management.",
        },
        "page": {
            "code": "inspections",
            "name": "Inspections",
            "description": "Inspection management and sign-off views.",
            "route": "/maintenance/inspections",
        },
        "feature": {
            "code": "inspections_management",
            "name": "Inspections",
            "description": "Schedule, track, and record airframe and component inspections.",
        },
    },
    {
        "suite": {
            "code": "drone_operations",
            "name": "Operations",
            "description": "Drone, UAS, and autonomous fleet operations.",
        },
        "module": {
            "code": "drone_fleet_operations",
            "name": "Drone Fleet Operations",
            "description": "Drone asset, battery, component, and flight tracking.",
        },
        "page": {
            "code": "drones",
            "name": "Drones",
            "description": "The drone fleet list and detail views.",
            "route": "/drones",
        },
        "feature": {
            "code": "drone_fleet_management",
            "name": "Drone Fleet Management",
            "description": "Register and track drones, batteries, components, and flights.",
        },
    },
    {
        "suite": {
            "code": "drone_operations",
            "name": "Operations",
            "description": "Drone, UAS, and autonomous fleet operations.",
        },
        "module": {
            "code": "flight_telemetry_ops",
            "name": "Flight Telemetry",
            "description": "Live and historical flight telemetry operations.",
        },
        "page": {
            "code": "flight_telemetry",
            "name": "Flight Telemetry",
            "description": "Real-time telemetry and mission playback views.",
            "route": "/flights/telemetry",
        },
        "feature": {
            "code": "flight_telemetry",
            "name": "Flight Telemetry",
            "description": "Live mission tracking and flight telemetry analytics.",
        },
    },
    {
        "suite": {
            "code": "drone_operations",
            "name": "Operations",
            "description": "Drone, UAS, and autonomous fleet operations.",
        },
        "module": {
            "code": "battery_analytics_ops",
            "name": "Battery Operations",
            "description": "UAS battery pack health and lifecycle tracking.",
        },
        "page": {
            "code": "battery_analytics",
            "name": "Battery Analytics",
            "description": "Battery lifecycle and health telemetry views.",
            "route": "/drones/batteries",
        },
        "feature": {
            "code": "battery_analytics",
            "name": "Battery Analytics",
            "description": "Monitor battery cell balance, cycles, and degradation.",
        },
    },
    {
        "suite": {
            "code": "procurement",
            "name": "Procurement",
            "description": "Parts and vendor procurement operations.",
        },
        "module": {
            "code": "procurement_operations",
            "name": "Procurement Operations",
            "description": "Procurement request creation, review, and approval.",
        },
        "page": {
            "code": "procurement_requests",
            "name": "Procurement Requests",
            "description": "The procurement request list and detail views.",
            "route": "/procurement/requests",
        },
        "feature": {
            "code": "procurement_management",
            "name": "Procurement Management",
            "description": "Create, review, and approve procurement requests.",
        },
    },
    {
        "suite": {
            "code": "compliance",
            "name": "Compliance",
            "description": "Airworthiness regulations, standards, and compliance audits.",
        },
        "module": {
            "code": "compliance_governance",
            "name": "Compliance Governance",
            "description": "Regulatory rulebook, evidence collection, and audits.",
        },
        "page": {
            "code": "compliance_register",
            "name": "Compliance Register",
            "description": "Regulatory compliance register and rules.",
            "route": "/compliance",
        },
        "feature": {
            "code": "compliance_management",
            "name": "Compliance Management",
            "description": "Manage regulatory compliance assessments and audit evidence.",
        },
    },
    {
        "suite": {
            "code": "compliance",
            "name": "Compliance",
            "description": "Airworthiness regulations, standards, and compliance audits.",
        },
        "module": {
            "code": "compliance_intelligence",
            "name": "Compliance Intelligence",
            "description": "Continuous compliance validation and discrepancy scanning.",
        },
        "page": {
            "code": "compliance_intelligence_page",
            "name": "Compliance Intelligence",
            "description": "Automated compliance checks and intelligence dashboard.",
            "route": "/compliance/intelligence",
        },
        "feature": {
            "code": "advanced_compliance_intelligence",
            "name": "Advanced Compliance Intelligence",
            "description": "Automated proactive compliance analysis and risk forecasting.",
        },
    },
    {
        "suite": {
            "code": "ai_intelligence",
            "name": "AI",
            "description": "Artificial Intelligence and machine learning capabilities.",
        },
        "module": {
            "code": "lisa_ai_module",
            "name": "AI Assistant",
            "description": "LISA conversational airworthiness assistant.",
        },
        "page": {
            "code": "lisa_ai_page",
            "name": "LISA Assistant",
            "description": "LISA AI assistant chat and query interface.",
            "route": "/lisa",
        },
        "feature": {
            "code": "ai_assistant",
            "name": "AI Assistant",
            "description": "LISA aerospace regulatory and maintenance intelligent copilot.",
        },
    },
    {
        "suite": {
            "code": "ai_intelligence",
            "name": "AI",
            "description": "Artificial Intelligence and machine learning capabilities.",
        },
        "module": {
            "code": "predictive_ops",
            "name": "Predictive Operations",
            "description": "Machine-learning component wear and maintenance forecasting.",
        },
        "page": {
            "code": "predictive_ops_page",
            "name": "Predictive Analytics",
            "description": "Predictive maintenance forecasting views.",
            "route": "/analytics/predictive",
        },
        "feature": {
            "code": "predictive_maintenance",
            "name": "Predictive Maintenance",
            "description": "Predictive airframe and component failure modeling.",
        },
    },
]


def _get_or_create_suite(db: Session, spec: dict) -> ProductSuite:
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


def _get_or_create_module(db: Session, suite: ProductSuite, spec: dict) -> ProductModule:
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


def _get_or_create_page(db: Session, module: ProductModule, spec: dict) -> ProductPage:
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


def _get_or_create_feature(db: Session, module: ProductModule, spec: dict) -> ProductFeature:
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
        for entry in _CATALOG_ENTRIES:
            suite = _get_or_create_suite(db, entry["suite"])
            module = _get_or_create_module(db, suite, entry["module"])
            _get_or_create_page(db, module, entry["page"])
            _get_or_create_feature(db, module, entry["feature"])
        db.commit()
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
