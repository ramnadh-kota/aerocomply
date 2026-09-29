"""Route-level smoke: no API operation may answer 500 for an authenticated,
fully-entitled ORG_ADMIN.

Why this exists: the /edge/* and /commercial/* routers called a non-existent
`CurrentUser.require_permission` and non-existent Permission members, so every
call returned HTTP 500 -- yet 1,900+ tests stayed green because none of them
made an HTTP request to those routes. This test makes one request to every
OpenAPI operation (path params replaced with random UUIDs, empty JSON bodies)
and fails on any 5xx. 4xx (validation, 403, 404, 409) is an acceptable answer:
this only detects handlers that crash.

Operations that would mutate/consume external systems or are unsafe to fire
blindly are skipped explicitly (see _SKIP).
"""
from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.main import app
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.product_catalog import ProductSuite
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import _SUITE_DISALLOWED_FEATURES  # noqa: F401
from app.core.feature_keys import FeatureKey

_SKIP = re.compile(
    r"/auth/(logout|sso)|/telemetry/dji/webhook|/platform/|/health|/export|/storage|/evidence.*/(upload|download)"
)


def _operations():
    spec = app.openapi()["paths"]
    for path, ops in sorted(spec.items()):
        for method in ops:
            if method.lower() in {"get", "post", "put", "patch", "delete"} and not _SKIP.search(path):
                yield method.upper(), path


@pytest.fixture
def admin_headers(client, db_session):
    suite = db_session.execute(select(ProductSuite).where(ProductSuite.code == "DRONE_UAV")).scalar_one()
    plan = Plan(suite_id=suite.id, code=f"SMOKE-{uuid.uuid4().hex[:8]}", name="Smoke", is_active=True)
    db_session.add(plan)
    db_session.flush()
    for f in FeatureKey:
        db_session.add(PlanFeature(plan_id=plan.id, feature_key=f.value, enabled=True))
    org = Organization(name=f"Smoke Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()
    db_session.add(
        Subscription(
            organization_id=org.id, plan_id=plan.id, suite_id=suite.id,
            status=SubscriptionStatus.ACTIVE, starts_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    user = User(
        organization_id=org.id, email=f"smoke-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("supersecret123"), full_name="Smoke", is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=org.id))
    db_session.commit()
    r = client.post("/api/v1/auth/login", json={"email": user.email, "password": "supersecret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_no_operation_returns_5xx(client, admin_headers):
    failures: list[str] = []
    checked = 0
    for method, path in _operations():
        url = re.sub(r"\{[^}]+\}", lambda _m: str(uuid.uuid4()), path)
        kwargs = {"headers": admin_headers}
        if method in {"POST", "PUT", "PATCH"}:
            kwargs["json"] = {}
        try:
            resp = client.request(method, url, **kwargs)
        except Exception as exc:  # unhandled exception surfaced by TestClient
            failures.append(f"{method} {path} -> raised {type(exc).__name__}: {str(exc)[:120]}")
            continue
        checked += 1
        if resp.status_code >= 500:
            failures.append(f"{method} {path} -> {resp.status_code}")
    assert checked > 300, f"smoke covered too few operations ({checked})"
    assert not failures, "operations crashing (5xx):\n" + "\n".join(failures)
