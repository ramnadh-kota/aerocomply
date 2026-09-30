import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription
from app.models.user import User, UserRole

PW = "M20Preview!123"
db = Session(create_engine(os.environ["DATABASE_URL"]))


def tenant(org_name, email, suite_code, plan_code, feats):
    suite = db.execute(select(ProductSuite).where(ProductSuite.code == suite_code)).scalar_one()
    plan = db.execute(select(Plan).where(Plan.suite_id == suite.id, Plan.code == plan_code)).scalar_one_or_none()
    if not plan:
        plan = Plan(suite_id=suite.id, code=plan_code, name=f"{suite_code} browser test", is_active=True)
        db.add(plan)
        db.flush()
        for f in feats:
            db.add(PlanFeature(plan_id=plan.id, feature_key=f, enabled=True))
    org = db.execute(select(Organization).where(Organization.name == org_name)).scalar_one_or_none()
    if not org:
        org = Organization(name=org_name)
        db.add(org)
        db.flush()
        db.add(Subscription(organization_id=org.id, plan_id=plan.id, suite_id=suite.id, status="ACTIVE",
                            starts_at=datetime.now(UTC) - timedelta(days=1)))
        u = User(organization_id=org.id, email=email, hashed_password=hash_password(PW), full_name=f"{org_name} Admin",
                 is_active=True, email_verified=True)
        db.add(u)
        db.flush()
        db.add(UserRole(user_id=u.id, role_name="ORG_ADMIN", organization_id=org.id))
    db.commit()


tenant("Browser Heli Co", "browser-heli@example.com", "HELICOPTER", "BROWSER-HELI",
       ["helicopter_fleet_management", "flight_telemetry", "hums", "work_order_management", "lisa_ai_copilot", "predictive_maintenance"])
tenant("Browser EVTOL Co", "browser-evtol@example.com", "EVTOL_AAM", "BROWSER-EVTOL",
       ["evtol_fleet_management", "battery_analytics", "flight_telemetry", "hums", "work_order_management", "lisa_ai_copilot"])
print("seeded")
sys.exit(0)
