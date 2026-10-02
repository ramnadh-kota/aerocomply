"""Deterministic, idempotent seed for the 4 initial Kota Aerospace commercial plans.

Configures:
1. Kota Drone (Code: DRONE_001, Suite: DRONE_UAV)
2. Kota Aircraft (Code: AIRCRAFT_001, Suite: AIRCRAFT)
3. Kota Helicopter (Code: HELICOPTER_001, Suite: HELICOPTER)
4. Kota eVTOL (Code: EVTOL_001, Suite: EVTOL_AAM)

Plans are suite-specific (plans.suite_id is NOT NULL, unique on (suite_id, code)).
The product suites must already exist (created by the migrations / seed_product_catalog.py);
the script aborts without writing anything if one is missing.

Safe to run multiple times: plans are looked up by (suite, code), so a rerun updates in place
and never creates duplicates. Features that the suite boundary forbids are refused.
"""

import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models  # noqa: E402,F401  (register all mappers)
from app.models.plan import Plan, PlanFeature, PlanLimit  # noqa: E402
from app.models.product_catalog import ProductSuite  # noqa: E402
from app.services.entitlement_service import is_feature_allowed_for_suite  # noqa: E402

_INITIAL_PLANS = [
    {
        "name": "Kota Drone",
        "code": "DRONE_001",
        "suite_code": "DRONE_UAV",
        "description": "Commercial autonomous drone operations, fleet tracking, battery analytics, and maintenance.",
        "asset_scope": "DRONE_UAV",
        "is_active": True,
        "features": {
            "drone_fleet_management": True,
            "flight_telemetry": True,
            "battery_analytics": True,
            "work_order_management": True,
            "inspections_management": True,
            "compliance_management": True,
            "advanced_compliance_intelligence": False,
            "ai_assistant": False,
            "predictive_maintenance": False,
        },
        "limits": {
            "max_assets": 100,
            "max_users": 25,
            "monthly_work_orders": 500,
            "storage_gb": 50,
            "monthly_lisa_ai_tokens": 1000000,
            "monthly_api_requests": 100000,
        },
    },
    {
        "name": "Kota Aircraft",
        "code": "AIRCRAFT_001",
        "suite_code": "AIRCRAFT",
        "description": "Fixed-wing commercial aircraft airworthiness, CAMO, MRO work orders, and regulatory compliance.",
        "asset_scope": "AIRCRAFT",
        "is_active": True,
        "features": {
            "work_order_management": True,
            "inspections_management": True,
            "compliance_management": True,
            "advanced_compliance_intelligence": True,
            "procurement_management": True,
            "ai_assistant": True,
            "predictive_maintenance": False,
        },
        "limits": {
            "max_assets": 25,
            "max_users": 50,
            "monthly_work_orders": 200,
            "storage_gb": 200,
            "monthly_lisa_ai_tokens": 2500000,
            "monthly_api_requests": 500000,
        },
    },
    {
        "name": "Kota Helicopter",
        "code": "HELICOPTER_001",
        "suite_code": "HELICOPTER",
        "description": "Rotorcraft airframe lifecycle, dynamic component tracking, inspections, and flight maintenance.",
        "asset_scope": "HELICOPTER",
        "is_active": True,
        "features": {
            "helicopter_fleet_management": True,
            "work_order_management": True,
            "inspections_management": True,
            "compliance_management": True,
            "procurement_management": True,
            "ai_assistant": False,
            "predictive_maintenance": False,
        },
        "limits": {
            "max_assets": 20,
            "max_users": 30,
            "monthly_work_orders": 150,
            "storage_gb": 100,
            "monthly_lisa_ai_tokens": 1500000,
            "monthly_api_requests": 250000,
        },
    },
    {
        "name": "Kota eVTOL",
        "code": "EVTOL_001",
        "suite_code": "EVTOL_AAM",
        "description": "Next-gen eVTOL and Advanced Air Mobility (AAM) operations, AI predictive maintenance, and battery intelligence.",
        "asset_scope": "EVTOL_AAM",
        "is_active": True,
        "features": {
            "evtol_fleet_management": True,
            "flight_telemetry": True,
            "battery_analytics": True,
            "work_order_management": True,
            "inspections_management": True,
            "compliance_management": True,
            "advanced_compliance_intelligence": True,
            "ai_assistant": True,
            "predictive_maintenance": True,
            "procurement_management": True,
        },
        "limits": {
            "max_assets": 50,
            "max_users": 40,
            "monthly_work_orders": 300,
            "storage_gb": 150,
            "monthly_lisa_ai_tokens": 2000000,
            "monthly_api_requests": 350000,
        },
    },
]


def _resolve_suites(db: Session) -> dict[str, ProductSuite]:
    suites: dict[str, ProductSuite] = {}
    for spec in _INITIAL_PLANS:
        code = spec["suite_code"]
        suite = db.execute(select(ProductSuite).where(ProductSuite.code == code)).scalar_one_or_none()
        if suite is None:
            raise RuntimeError(f"Product suite {code!r} not found; run migrations / seed_product_catalog first.")
        suites[code] = suite
    return suites


def seed_plans(db: Session) -> None:
    suites = _resolve_suites(db)
    for plan_spec in _INITIAL_PLANS:
        suite = suites[plan_spec["suite_code"]]
        forbidden = [k for k in plan_spec["features"] if not is_feature_allowed_for_suite(suite.code, k)]
        if forbidden:
            raise RuntimeError(f"Plan {plan_spec['code']}: features {forbidden} are outside the {suite.code} suite boundary.")
        plan = db.execute(
            select(Plan).where(Plan.suite_id == suite.id, Plan.code == plan_spec["code"])
        ).scalar_one_or_none()

        if plan is None:
            plan = Plan(
                suite_id=suite.id,
                name=plan_spec["name"],
                code=plan_spec["code"],
                description=plan_spec["description"],
                asset_scope=plan_spec["asset_scope"],
                is_active=plan_spec["is_active"],
            )
            db.add(plan)
            db.flush()
            print(f"Created Plan: {plan.name} ({plan.code})")
        else:
            plan.name = plan_spec["name"]
            plan.description = plan_spec["description"]
            plan.asset_scope = plan_spec["asset_scope"]
            plan.is_active = plan_spec["is_active"]
            db.add(plan)
            db.flush()
            print(f"Updated Plan: {plan.name} ({plan.code})")

        # Configure Plan Features
        existing_features = {
            pf.feature_key: pf
            for pf in db.execute(
                select(PlanFeature).where(PlanFeature.plan_id == plan.id)
            ).scalars().all()
        }

        for feature_key, enabled in plan_spec["features"].items():
            if feature_key in existing_features:
                pf = existing_features[feature_key]
                pf.enabled = enabled
                db.add(pf)
            else:
                new_pf = PlanFeature(plan_id=plan.id, feature_key=feature_key, enabled=enabled)
                db.add(new_pf)

        # Configure Plan Limits
        existing_limits = {
            pl.limit_key: pl
            for pl in db.execute(
                select(PlanLimit).where(PlanLimit.plan_id == plan.id)
            ).scalars().all()
        }

        for limit_key, limit_val in plan_spec.get("limits", {}).items():
            if limit_key in existing_limits:
                pl = existing_limits[limit_key]
                pl.limit_value = limit_val
                pl.is_unlimited = False if limit_val is not None else True
                db.add(pl)
            else:
                new_pl = PlanLimit(
                    plan_id=plan.id,
                    limit_key=limit_key,
                    limit_value=limit_val,
                    is_unlimited=False if limit_val is not None else True,
                )
                db.add(new_pl)

    db.commit()
    print("Initial plans seeded successfully.")


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()
    try:
        seed_plans(db)
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
