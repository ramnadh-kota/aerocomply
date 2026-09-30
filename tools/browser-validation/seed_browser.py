import os, json, uuid, sys
from datetime import UTC, datetime, timedelta
import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import app.models  # noqa
from app.core.security import hash_password
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription
from app.models.user import User, UserRole
sys.path.insert(0, ".")
from tests.unit.test_m20_mavlink_integrity import heartbeat, sys_status, vibration

PW = "M20Preview!123"
B = "http://localhost:8001/api/v1"
db = Session(create_engine(os.environ["DATABASE_URL"]))

FEATS = ["drone_fleet_management", "flight_telemetry", "hums", "battery_analytics", "work_order_management",
         "lisa_ai_copilot", "predictive_maintenance", "compliance_management", "inspections_management"]
suite = db.execute(select(ProductSuite).where(ProductSuite.code == "DRONE_UAV")).scalar_one()
plan = db.execute(select(Plan).where(Plan.suite_id == suite.id, Plan.code == "BROWSER-FULL")).scalar_one_or_none()
if not plan:
    plan = Plan(suite_id=suite.id, code="BROWSER-FULL", name="Drone Professional (browser test)", is_active=True)
    db.add(plan); db.flush()
    for f in FEATS: db.add(PlanFeature(plan_id=plan.id, feature_key=f, enabled=True))
org = db.execute(select(Organization).where(Organization.name == "Browser Drone Co")).scalar_one_or_none()
if not org:
    org = Organization(name="Browser Drone Co"); db.add(org); db.flush()
    db.add(Subscription(organization_id=org.id, plan_id=plan.id, suite_id=suite.id, status="ACTIVE",
                        starts_at=datetime.now(UTC) - timedelta(days=1)))
    u = User(organization_id=org.id, email="browser-drone@example.com", hashed_password=hash_password(PW),
             full_name="Browser Drone Admin", is_active=True, email_verified=True)
    db.add(u); db.flush(); db.add(UserRole(user_id=u.id, role_name="ORG_ADMIN", organization_id=org.id))
db.commit()

def login(email):
    r = httpx.post(B + "/auth/login", json={"email": email, "password": PW}); r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["access_token"]}

h = login("browser-drone@example.com")
existing = httpx.get(B + "/drones", headers=h).json()
assets = {d["registration"]: d["id"] for d in (existing if isinstance(existing, list) else existing.get("items", []))}
for reg in ("BRW-001", "BRW-002"):
    if reg not in assets:
        r = httpx.post(B + "/drones", headers=h, json={"registration": reg, "manufacturer": "DJI", "model": "M300"})
        r.raise_for_status(); assets[reg] = r.json()["id"]

srcs = httpx.get(B + "/data-sources", headers=h).json()["items"]
mav = next((s for s in srcs if s["name"] == "MAVLink gateway"), None)
if not mav:
    r = httpx.post(B + "/data-sources", headers=h, json={"name": "MAVLink gateway", "connector_type": "MAVLINK",
        "connection_config": {"system_id_map": {"1": assets["BRW-001"], "2": assets["BRW-002"]}, "expected_interval_seconds": 60}})
    r.raise_for_status(); mav = r.json()
    httpx.patch(f"{B}/data-sources/{mav['id']}", headers=h, json={"status": "ACTIVE"}).raise_for_status()
seq = 0
def n():
    global seq; seq += 1; return seq
frames = heartbeat(seq=n()) + sys_status(seq=n(), remaining=88)
frames += b"".join(vibration(1.5, 1.6, 1.7, seq=n()) for _ in range(6)) + vibration(45.0, 52.0, 48.0, seq=n())
frames += heartbeat(seq=n(), sysid=2) + b"".join(vibration(2.0, 2.0, 2.0, seq=n(), sysid=2) for _ in range(3))
rep = httpx.post(f"{B}/data-sources/{mav['id']}/ingest", headers={**h, "Content-Type": "application/octet-stream"}, content=frames).json()
print(json.dumps({"assets": assets, "source": mav["id"], "report": rep}))
json.dump({"assets": assets, "source": mav["id"]}, open(os.path.join(os.environ.get("BROWSER_SCRATCH", "."), "browser_seed.json"), "w"))
