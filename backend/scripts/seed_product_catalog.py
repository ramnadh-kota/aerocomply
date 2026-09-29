"""Phase 18.5: deterministic, idempotent seed for the initial platform
product suites, modules, pages, features, and suite-specific plans.

Canonical Suites:
- AIRCRAFT ("Aircraft Suite")
- DRONE_UAV ("Drone / UAV Suite")
- HELICOPTER ("Helicopter Suite")
- EVTOL_AAM ("eVTOL / AAM Suite")

Each Suite receives:
- Modules, Pages, Features
- Starter, Professional, Enterprise plans

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/seed_product_catalog.py
"""

import os
import sys
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.plan import Plan, PlanFeature, PlanLimit  # noqa: E402
from app.models.product_catalog import (  # noqa: E402
    ProductFeature,
    ProductModule,
    ProductPage,
    ProductSuite,
)

_SUITES_DATA = [
    {
        "suite": {
            "code": "DRONE_UAV",
            "name": "Drone / UAV Suite",
            "description": "Unmanned aerial vehicles, autonomous systems, batteries, and fleet operations.",
            "icon": "drone",
            "display_order": 1,
            "is_active": True,
        },
        "modules": [
            {
                "module": {
                    "code": "drone_fleet_operations",
                    "name": "Drone Fleet Operations",
                    "description": "Drone asset, battery, component, and flight tracking.",
                    "display_order": 1,
                },
                "pages": [
                    {"code": "drones", "name": "Drones", "route": "/drones", "display_order": 1},
                    {"code": "fleet_registry", "name": "Fleet Registry", "route": "/assets", "display_order": 2},
                ],
                "features": [
                    {"code": "drone_fleet_management", "name": "Drone Fleet Management", "description": "Register and track drones, components, and health."},
                ],
            },
            {
                "module": {
                    "code": "drone_flight_ops",
                    "name": "Flight Operations & Telemetry",
                    "description": "Live flight telemetry and drone mission tracking.",
                    "display_order": 2,
                },
                "pages": [
                    {"code": "flight_telemetry", "name": "Flight Telemetry", "route": "/flights/telemetry", "display_order": 1},
                    {"code": "pilot_workflow", "name": "Pilot Workflow", "route": "/pilot", "display_order": 2},
                ],
                "features": [
                    {"code": "flight_telemetry", "name": "Flight Telemetry", "description": "Real-time telemetry and mission playback."},
                    {"code": "drone_missions", "name": "Drone Missions", "description": "Automated and piloted drone mission management."},
                ],
            },
            {
                "module": {
                    "code": "drone_battery_ops",
                    "name": "Battery Management",
                    "description": "UAS battery pack health, cycles, and degradation telemetry.",
                    "display_order": 3,
                },
                "pages": [
                    {"code": "battery_analytics", "name": "Battery Analytics", "route": "/drones/batteries", "display_order": 1},
                ],
                "features": [
                    {"code": "battery_analytics", "name": "Battery Analytics", "description": "Monitor cell balance, cycles, and health."},
                ],
            },
            {
                "module": {
                    "code": "drone_maintenance_ops",
                    "name": "Maintenance & MRO",
                    "description": "Work order creation, tasks, and maintenance release.",
                    "display_order": 4,
                },
                "pages": [
                    {"code": "work_orders", "name": "Work Orders", "route": "/maintenance/work-orders", "display_order": 1},
                    {"code": "tasks", "name": "Tasks", "route": "/maintenance/tasks", "display_order": 2},
                    {"code": "inspections", "name": "Inspections", "route": "/maintenance/inspections", "display_order": 3},
                ],
                "features": [
                    {"code": "work_order_management", "name": "Work Order Management", "description": "Track maintenance work orders and tasks."},
                    {"code": "inspections_management", "name": "Inspections Management", "description": "Schedule and record airframe and motor inspections."},
                    {"code": "release_readiness", "name": "Release Readiness", "description": "Enforce release gates and airworthiness sign-off."},
                ],
            },
            {
                "module": {
                    "code": "drone_compliance_ops",
                    "name": "Compliance & Regulations",
                    "description": "Airspace compliance, regulatory assessments, and audit logs.",
                    "display_order": 5,
                },
                "pages": [
                    {"code": "compliance", "name": "AeroComply", "route": "/compliance", "display_order": 1},
                    {"code": "regulations", "name": "Regulations", "route": "/regulations", "display_order": 2},
                    {"code": "assessments", "name": "Assessments", "route": "/assessments", "display_order": 3},
                    {"code": "audit", "name": "Audit Trail", "route": "/audit", "display_order": 4},
                ],
                "features": [
                    {"code": "compliance_management", "name": "Compliance Management", "description": "Manage regulatory obligations and audits."},
                    {"code": "advanced_compliance_intelligence", "name": "Advanced Compliance Intelligence", "description": "Automated proactive compliance scanning."},
                    {"code": "audit_logging", "name": "Audit Logging", "description": "Cryptographically-traceable audit logging."},
                ],
            },
            {
                "module": {
                    "code": "drone_intelligence_ops",
                    "name": "Intelligence & LISA AI",
                    "description": "HUMS, prognostics, predictive maintenance, and conversational AI copilot.",
                    "display_order": 6,
                },
                "pages": [
                    {"code": "fleet_health", "name": "Fleet Health", "route": "/fleet/health", "display_order": 1},
                    {"code": "fleet_intel", "name": "Fleet Intelligence", "route": "/intelligence/fleet", "display_order": 2},
                    {"code": "ai_command", "name": "AI Command Center", "route": "/ai", "display_order": 3},
                ],
                "features": [
                    {"code": "hums", "name": "HUMS & Telemetry Intelligence", "description": "Vibration, temperature, and electrical health analysis."},
                    {"code": "predictive_maintenance", "name": "Predictive Maintenance", "description": "RUL estimation and failure forecasting."},
                    {"code": "mro_intelligence", "name": "MRO Intelligence", "description": "Proactive signal correlation and dispatch."},
                    {"code": "lisa_ai_copilot", "name": "LISA AI Assistant", "description": "Conversational airworthiness and maintenance copilot."},
                    {"code": "digital_twin", "name": "Digital Twin", "description": "Asset state tracking and sensor mapping."},
                ],
            },
            {
                "module": {
                    "code": "drone_procurement_ops",
                    "name": "Procurement & Parts",
                    "description": "Part sourcing, inventory, and vendor management.",
                    "display_order": 7,
                },
                "pages": [
                    {"code": "procurement", "name": "Procurement", "route": "/procurement", "display_order": 1},
                    {"code": "parts", "name": "Parts Search", "route": "/procurement/parts", "display_order": 2},
                    {"code": "purchase_orders", "name": "Purchase Orders", "route": "/procurement/purchase-orders", "display_order": 3},
                ],
                "features": [
                    {"code": "procurement_management", "name": "Procurement Management", "description": "Create and manage part procurement requests."},
                ],
            },
        ],
        "plans": [
            {
                "code": "DRONE_STARTER",
                "name": "Drone Starter",
                "description": "Starter commercial tier for drone and UAS operators.",
                "features": ["drone_fleet_management", "work_order_management", "compliance_management", "procurement_management"],
                "limits": {"max_drones": 10, "max_users": 5, "telemetry_retention_days": 30},
            },
            {
                "code": "DRONE_PROFESSIONAL",
                "name": "Drone Professional",
                "description": "Professional tier for commercial drone fleets with telemetry and AI copilot.",
                "features": [
                    "drone_fleet_management", "flight_telemetry", "battery_analytics", "drone_missions",
                    "work_order_management", "inspections_management", "release_readiness",
                    "compliance_management", "advanced_compliance_intelligence", "audit_logging",
                    "hums", "predictive_maintenance", "mro_intelligence", "lisa_ai_copilot", "digital_twin",
                    "procurement_management"
                ],
                "limits": {"max_drones": 100, "max_users": 50, "telemetry_retention_days": 365},
            },
            {
                "code": "DRONE_ENTERPRISE",
                "name": "Drone Enterprise",
                "description": "Enterprise tier for large-scale autonomous operations.",
                "features": [
                    "drone_fleet_management", "flight_telemetry", "battery_analytics", "drone_missions",
                    "work_order_management", "inspections_management", "release_readiness",
                    "compliance_management", "advanced_compliance_intelligence", "audit_logging",
                    "hums", "predictive_maintenance", "mro_intelligence", "lisa_ai_copilot", "digital_twin",
                    "procurement_management"
                ],
                "limits": {"max_drones": 1000, "max_users": 500, "telemetry_retention_days": 2555},
            },
        ],
    },
    {
        "suite": {
            "code": "AIRCRAFT",
            "name": "Aircraft Suite",
            "description": "Fixed-wing commercial, private, and transport aircraft operations and engineering.",
            "icon": "plane",
            "display_order": 2,
            "is_active": True,
        },
        "modules": [
            {
                "module": {
                    "code": "aircraft_fleet_operations",
                    "name": "Aircraft Fleet Operations",
                    "description": "Aircraft registry, MSN, registration, and airframe tracking.",
                    "display_order": 1,
                },
                "pages": [
                    {"code": "aircraft", "name": "Aircraft", "route": "/aircraft", "display_order": 1},
                    {"code": "fleet_registry", "name": "Fleet Registry", "route": "/assets", "display_order": 2},
                ],
                "features": [
                    {"code": "aircraft_fleet_management", "name": "Aircraft Fleet Management", "description": "Manage airframe registry, MSN, and aircraft status."},
                    {"code": "aircraft_operations", "name": "Aircraft Operations", "description": "Commercial and regional airline flight operations."},
                ],
            },
            {
                "module": {
                    "code": "aircraft_mro_ops",
                    "name": "Aircraft Maintenance & MRO",
                    "description": "Heavy check planning, work orders, tasks, and technician tracking.",
                    "display_order": 2,
                },
                "pages": [
                    {"code": "work_orders", "name": "Work Orders", "route": "/maintenance/work-orders", "display_order": 1},
                    {"code": "tasks", "name": "Tasks", "route": "/maintenance/tasks", "display_order": 2},
                    {"code": "planning", "name": "Planning", "route": "/maintenance/planning", "display_order": 3},
                    {"code": "technicians", "name": "Technicians", "route": "/maintenance/technicians", "display_order": 4},
                    {"code": "hangar", "name": "Hangar Floor", "route": "/maintenance/hangar", "display_order": 5},
                ],
                "features": [
                    {"code": "work_order_management", "name": "Work Order Management", "description": "Line and base maintenance work orders."},
                    {"code": "aircraft_mro", "name": "Aircraft MRO Intelligence", "description": "Maintenance tracking, MEL, and defect management."},
                ],
            },
            {
                "module": {
                    "code": "aircraft_inspections_ops",
                    "name": "Inspections & Release",
                    "description": "RII, scheduled checks, non-destructive testing, and release readiness.",
                    "display_order": 3,
                },
                "pages": [
                    {"code": "inspections", "name": "Inspections", "route": "/maintenance/inspections", "display_order": 1},
                    {"code": "release_readiness", "name": "Release Readiness", "route": "/maintenance/release-readiness", "display_order": 2},
                    {"code": "evidence", "name": "Evidence", "route": "/evidence", "display_order": 3},
                ],
                "features": [
                    {"code": "inspections_management", "name": "Inspections Management", "description": "Airframe and powerplant inspection management."},
                    {"code": "release_readiness", "name": "Release Readiness", "description": "Deterministic release readiness and airworthiness gates."},
                ],
            },
            {
                "module": {
                    "code": "aircraft_compliance_ops",
                    "name": "AeroComply & Regulations",
                    "description": "FAA/EASA/DGCA airworthiness directives, compliance register, and audits.",
                    "display_order": 4,
                },
                "pages": [
                    {"code": "compliance", "name": "AeroComply", "route": "/compliance", "display_order": 1},
                    {"code": "regulations", "name": "Regulations", "route": "/regulations", "display_order": 2},
                    {"code": "assessments", "name": "Assessments", "route": "/assessments", "display_order": 3},
                    {"code": "audit", "name": "Audit Trail", "route": "/audit", "display_order": 4},
                ],
                "features": [
                    {"code": "compliance_management", "name": "Compliance Management", "description": "Manage airworthiness directives and compliance obligations."},
                    {"code": "advanced_compliance_intelligence", "name": "Advanced Compliance Intelligence", "description": "Automated proactive compliance auditing."},
                    {"code": "audit_logging", "name": "Audit Logging", "description": "Immutable compliance and maintenance audit trail."},
                ],
            },
            {
                "module": {
                    "code": "aircraft_intelligence_ops",
                    "name": "Predictive Intelligence & LISA",
                    "description": "HUMS, engine health monitoring, RUL forecasting, and conversational AI.",
                    "display_order": 5,
                },
                "pages": [
                    {"code": "telemetry", "name": "Flight Telemetry", "route": "/flights/telemetry", "display_order": 1},
                    {"code": "fleet_health", "name": "Fleet Health", "route": "/fleet/health", "display_order": 2},
                    {"code": "fleet_intel", "name": "Fleet Intelligence", "route": "/intelligence/fleet", "display_order": 3},
                    {"code": "ai_command", "name": "AI Command Center", "route": "/ai", "display_order": 4},
                ],
                "features": [
                    {"code": "flight_telemetry", "name": "Flight Telemetry", "description": "Live flight tracking and avionics telemetry."},
                    {"code": "hums", "name": "HUMS Engine & Airframe Health", "description": "Vibration analysis, FFT, and exceedance monitoring."},
                    {"code": "predictive_maintenance", "name": "Predictive Maintenance", "description": "Component degradation modeling and RUL."},
                    {"code": "mro_intelligence", "name": "MRO Intelligence", "description": "Intelligence-guided maintenance recommendations."},
                    {"code": "lisa_ai_copilot", "name": "LISA AI Assistant", "description": "Grounded aerospace engineering AI assistant."},
                    {"code": "digital_twin", "name": "Digital Twin", "description": "Digital twin configuration and historical thread."},
                ],
            },
            {
                "module": {
                    "code": "aircraft_procurement_ops",
                    "name": "Procurement & Spares",
                    "description": "Certified aerospace parts, PMA/OEM suppliers, and purchase orders.",
                    "display_order": 6,
                },
                "pages": [
                    {"code": "procurement", "name": "Procurement", "route": "/procurement", "display_order": 1},
                    {"code": "parts", "name": "Parts Search", "route": "/procurement/parts", "display_order": 2},
                    {"code": "purchase_orders", "name": "Purchase Orders", "route": "/procurement/purchase-orders", "display_order": 3},
                ],
                "features": [
                    {"code": "procurement_management", "name": "Procurement Management", "description": "Aerospace parts purchasing and vendor intelligence."},
                ],
            },
        ],
        "plans": [
            {
                "code": "AIRCRAFT_STARTER",
                "name": "Aircraft Starter",
                "description": "Starter commercial tier for private and small commercial aircraft operators.",
                "features": ["aircraft_fleet_management", "work_order_management", "compliance_management", "procurement_management"],
                "limits": {"max_aircraft": 5, "max_users": 5, "telemetry_retention_days": 90},
            },
            {
                "code": "AIRCRAFT_PROFESSIONAL",
                "name": "Aircraft Professional",
                "description": "Professional tier for commercial airlines, charter operators, and MROs.",
                "features": [
                    "aircraft_fleet_management", "aircraft_operations", "aircraft_mro",
                    "work_order_management", "inspections_management", "release_readiness",
                    "compliance_management", "advanced_compliance_intelligence", "audit_logging",
                    "flight_telemetry", "hums", "predictive_maintenance", "mro_intelligence", "lisa_ai_copilot", "digital_twin",
                    "procurement_management"
                ],
                "limits": {"max_aircraft": 50, "max_users": 50, "telemetry_retention_days": 365},
            },
            {
                "code": "AIRCRAFT_ENTERPRISE",
                "name": "Aircraft Enterprise",
                "description": "Enterprise tier for flag carriers and major defense/aviation enterprises.",
                "features": [
                    "aircraft_fleet_management", "aircraft_operations", "aircraft_mro",
                    "work_order_management", "inspections_management", "release_readiness",
                    "compliance_management", "advanced_compliance_intelligence", "audit_logging",
                    "flight_telemetry", "hums", "predictive_maintenance", "mro_intelligence", "lisa_ai_copilot", "digital_twin",
                    "procurement_management"
                ],
                "limits": {"max_aircraft": 500, "max_users": 500, "telemetry_retention_days": 2555},
            },
        ],
    },
    {
        "suite": {
            "code": "HELICOPTER",
            "name": "Helicopter Suite",
            "description": "Rotary-wing aircraft, emergency medical services, and utility operations.",
            "icon": "helicopter",
            "display_order": 3,
            "is_active": True,
        },
        "modules": [
            {
                "module": {
                    "code": "helicopter_fleet_operations",
                    "name": "Helicopter Fleet Operations",
                    "description": "Rotorcraft registry and fleet tracking.",
                    "display_order": 1,
                },
                "pages": [
                    {"code": "helicopter_fleet", "name": "Fleet Registry", "route": "/assets", "display_order": 1},
                ],
                "features": [
                    {"code": "helicopter_fleet_management", "name": "Helicopter Fleet Management", "description": "Track rotary-wing fleet and operations."},
                ],
            },
        ],
        "plans": [
            {
                "code": "HELICOPTER_STARTER",
                "name": "Helicopter Starter",
                "description": "Starter commercial tier for helicopter operations.",
                "features": ["helicopter_fleet_management", "work_order_management", "compliance_management"],
                "limits": {"max_helicopters": 5, "max_users": 5},
            },
            {
                "code": "HELICOPTER_PROFESSIONAL",
                "name": "Helicopter Professional",
                "description": "Professional tier for commercial and EMS helicopter fleets.",
                "features": [
                    "helicopter_fleet_management", "work_order_management", "inspections_management", "release_readiness",
                    "compliance_management", "flight_telemetry", "hums", "predictive_maintenance", "lisa_ai_copilot"
                ],
                "limits": {"max_helicopters": 30, "max_users": 30},
            },
        ],
    },
    {
        "suite": {
            "code": "EVTOL_AAM",
            "name": "eVTOL / AAM Suite",
            "description": "Electric vertical takeoff and landing, advanced air mobility, and urban air transit.",
            "icon": "evtol",
            "display_order": 4,
            "is_active": True,
        },
        "modules": [
            {
                "module": {
                    "code": "evtol_fleet_operations",
                    "name": "eVTOL Fleet Operations",
                    "description": "Advanced air mobility fleet and battery powertrain management.",
                    "display_order": 1,
                },
                "pages": [
                    {"code": "evtol_fleet", "name": "Fleet Registry", "route": "/assets", "display_order": 1},
                    {"code": "battery_analytics", "name": "Powertrain & Battery", "route": "/drones/batteries", "display_order": 2},
                ],
                "features": [
                    {"code": "evtol_fleet_management", "name": "eVTOL Fleet Management", "description": "Manage eVTOL airframes and electric powertrains."},
                    {"code": "battery_analytics", "name": "Battery Analytics", "description": "Monitor high-voltage battery degradation."},
                ],
            },
        ],
        "plans": [
            {
                "code": "EVTOL_STARTER",
                "name": "eVTOL Starter",
                "description": "Starter tier for urban air mobility test fleets.",
                "features": ["evtol_fleet_management", "battery_analytics", "work_order_management", "compliance_management"],
                "limits": {"max_evtol": 5, "max_users": 5},
            },
            {
                "code": "EVTOL_PROFESSIONAL",
                "name": "eVTOL Professional",
                "description": "Professional tier for commercial AAM and passenger eVTOL operators.",
                "features": [
                    "evtol_fleet_management", "battery_analytics", "work_order_management", "inspections_management",
                    "release_readiness", "compliance_management", "flight_telemetry", "hums", "predictive_maintenance", "lisa_ai_copilot"
                ],
                "limits": {"max_evtol": 50, "max_users": 50},
            },
        ],
    },
]


def _get_or_create_suite(db: Session, spec: dict) -> ProductSuite:
    existing = db.execute(
        select(ProductSuite).where(ProductSuite.code == spec["code"])
    ).scalar_one_or_none()
    if existing is not None:
        for k, v in spec.items():
            setattr(existing, k, v)
        db.flush()
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
        for k, v in spec.items():
            setattr(existing, k, v)
        existing.suite_id = suite.id
        db.flush()
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
        for k, v in spec.items():
            setattr(existing, k, v)
        existing.module_id = module.id
        db.flush()
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
        for k, v in spec.items():
            setattr(existing, k, v)
        existing.module_id = module.id
        db.flush()
        return existing
    feature = ProductFeature(module_id=module.id, **spec)
    db.add(feature)
    db.flush()
    print(f"Created feature {spec['code']!r} (id={feature.id}).")
    return feature


def _get_or_create_plan(db: Session, suite: ProductSuite, plan_spec: dict) -> Plan:
    existing = db.execute(
        select(Plan).where(Plan.suite_id == suite.id, Plan.code == plan_spec["code"])
    ).scalar_one_or_none()
    if existing is None:
        # Also check by code alone
        existing = db.execute(
            select(Plan).where(Plan.code == plan_spec["code"])
        ).scalar_one_or_none()
    if existing is not None:
        existing.suite_id = suite.id
        existing.name = plan_spec["name"]
        existing.description = plan_spec.get("description")
        existing.asset_scope = suite.code
        db.flush()
        plan = existing
    else:
        plan = Plan(
            name=plan_spec["name"],
            code=plan_spec["code"],
            description=plan_spec.get("description"),
            suite_id=suite.id,
            asset_scope=suite.code,
            is_active=True,
        )
        db.add(plan)
        db.flush()
        print(f"Created plan {plan.code!r} for suite {suite.code!r} (id={plan.id}).")

    # Sync plan features
    for feat_key in plan_spec.get("features", []):
        pf = db.execute(
            select(PlanFeature).where(PlanFeature.plan_id == plan.id, PlanFeature.feature_key == feat_key)
        ).scalar_one_or_none()
        if pf is None:
            db.add(PlanFeature(plan_id=plan.id, feature_key=feat_key, enabled=True))
    
    # Sync plan limits
    for limit_key, limit_val in plan_spec.get("limits", {}).items():
        pl = db.execute(
            select(PlanLimit).where(PlanLimit.plan_id == plan.id, PlanLimit.limit_key == limit_key)
        ).scalar_one_or_none()
        if pl is None:
            db.add(PlanLimit(plan_id=plan.id, limit_key=limit_key, limit_value=limit_val, is_unlimited=False))

    db.flush()
    return plan


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        for item in _SUITES_DATA:
            suite = _get_or_create_suite(db, item["suite"])
            for mod_item in item.get("modules", []):
                module = _get_or_create_module(db, suite, mod_item["module"])
                for page_spec in mod_item.get("pages", []):
                    _get_or_create_page(db, module, page_spec)
                for feat_spec in mod_item.get("features", []):
                    _get_or_create_feature(db, module, feat_spec)
            for plan_spec in item.get("plans", []):
                _get_or_create_plan(db, suite, plan_spec)
        db.commit()
        print("Product catalog and plans seed completed successfully.")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
