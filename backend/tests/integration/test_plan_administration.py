"""M5: security and behavior tests for plan/plan-feature administration
(app/services/plan_service.py + the /api/v1/platform/plans* routes).

Uses the `client`/`db_session` fixtures from tests/integration/conftest.py.
Both share the SAME underlying connection/transaction for a given test, so
fixtures created via db_session are visible to requests made via client
without any commit-boundary surprises -- just never call db_session.rollback()
mid-test (same caveat as test_entitlement_api.py).
"""
import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole
from app.services.entitlement_service import (
    EntitlementResolutionStatus,
    resolve_entitlements,
)
from app.services.plan_service import (
    create_plan,
    create_plan_feature,
    set_plan_active,
    set_plan_feature_enabled,
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _login(client, email, password="supersecret123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


def _create_platform_admin(db_session, email):
    org = Organization(name="Plan Admin Platform Ops")
    db_session.add(org)
    db_session.flush()
    user = User(
        organization_id=org.id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Platform Admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="PLATFORM_ADMIN", organization_id=org.id))
    db_session.commit()
    return user


def _audit_count(db_session, entity_id):
    return len(
        db_session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == entity_id)
        )
        .scalars()
        .all()
    )


# 1. unauthenticated request -> 401
def test_unauthenticated_request_returns_401(client):
    resp = client.get("/api/v1/platform/plans")
    assert resp.status_code == 401

    resp2 = client.post("/api/v1/platform/plans", json={"name": "X", "code": "X"})
    assert resp2.status_code == 401


# 2. ordinary tenant user -> 403
def test_ordinary_tenant_user_gets_403(client, db_session):
    tokens = _register(client, "Plan Tenant 2", "admin@plan-tenant-2.com")
    headers = _auth(tokens["access_token"])

    resp = client.get("/api/v1/platform/plans", headers=headers)
    assert resp.status_code == 403

    resp2 = client.post(
        "/api/v1/platform/plans", json={"name": "X", "code": "PT2"}, headers=headers
    )
    assert resp2.status_code == 403


# 3. a tenant ORG_ADMIN also gets 403 -- proving tenant-admin status alone
# grants nothing here; only PLATFORM_MANAGE does.
def test_tenant_org_admin_also_gets_403(client, db_session):
    tokens = _register(client, "Plan Tenant 3", "admin@plan-tenant-3.com")
    headers = _auth(tokens["access_token"])
    # register-organization's admin_email user is created with ORG_ADMIN role
    # (see auth flow) -- confirm that role alone is insufficient here.
    resp = client.post(
        "/api/v1/platform/plans", json={"name": "X", "code": "PT3"}, headers=headers
    )
    assert resp.status_code == 403
    resp2 = client.post(
        f"/api/v1/platform/plans/{uuid.uuid4()}/activate", headers=headers
    )
    assert resp2.status_code == 403


# 4. PLATFORM_MANAGE succeeds for full plan CRUD + activate/deactivate
def test_platform_manage_can_crud_plans(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-4.com")
    admin_headers = _auth(_login(client, "ops@plan-co-4.com")["access_token"])

    create_resp = client.post(
        "/api/v1/platform/plans",
        json={"name": "Starter", "code": "PT4-STARTER", "description": "desc"},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    plan = create_resp.json()
    assert plan["is_active"] is True

    list_resp = client.get("/api/v1/platform/plans", headers=admin_headers)
    assert list_resp.status_code == 200
    assert any(p["id"] == plan["id"] for p in list_resp.json())

    get_resp = client.get(f"/api/v1/platform/plans/{plan['id']}", headers=admin_headers)
    assert get_resp.status_code == 200

    patch_resp = client.patch(
        f"/api/v1/platform/plans/{plan['id']}",
        json={"name": "Starter Renamed"},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Starter Renamed"

    deactivate_resp = client.post(
        f"/api/v1/platform/plans/{plan['id']}/deactivate", headers=admin_headers
    )
    assert deactivate_resp.status_code == 200
    assert deactivate_resp.json()["is_active"] is False

    activate_resp = client.post(
        f"/api/v1/platform/plans/{plan['id']}/activate", headers=admin_headers
    )
    assert activate_resp.status_code == 200
    assert activate_resp.json()["is_active"] is True


# 5. PLATFORM_MANAGE succeeds for plan-feature CRUD
def test_platform_manage_can_crud_plan_features(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-5.com")
    admin_headers = _auth(_login(client, "ops@plan-co-5.com")["access_token"])

    plan_resp = client.post(
        "/api/v1/platform/plans", json={"name": "P5", "code": "PT5"}, headers=admin_headers
    )
    plan_id = plan_resp.json()["id"]

    create_resp = client.post(
        f"/api/v1/platform/plans/{plan_id}/features",
        json={"feature_key": "LISA", "enabled": False},
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["enabled"] is False

    list_resp = client.get(f"/api/v1/platform/plans/{plan_id}/features", headers=admin_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    patch_resp = client.patch(
        f"/api/v1/platform/plans/{plan_id}/features/LISA",
        json={"enabled": True},
        headers=admin_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["enabled"] is True


# 6. unauthorized modification blocked for plan features too (ordinary tenant)
def test_ordinary_tenant_user_gets_403_for_plan_feature_mutation(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-6.com")
    admin_headers = _auth(_login(client, "ops@plan-co-6.com")["access_token"])
    plan_resp = client.post(
        "/api/v1/platform/plans", json={"name": "P6", "code": "PT6"}, headers=admin_headers
    )
    plan_id = plan_resp.json()["id"]

    tokens = _register(client, "Plan Tenant 6", "admin@plan-tenant-6.com")
    tenant_headers = _auth(tokens["access_token"])
    resp = client.post(
        f"/api/v1/platform/plans/{plan_id}/features",
        json={"feature_key": "X", "enabled": True},
        headers=tenant_headers,
    )
    assert resp.status_code == 403


# 7. duplicate plan code -> clean conflict, not a 500
def test_duplicate_plan_code_returns_clean_conflict(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-7.com")
    admin_headers = _auth(_login(client, "ops@plan-co-7.com")["access_token"])

    resp1 = client.post(
        "/api/v1/platform/plans", json={"name": "A", "code": "PT7-DUP"}, headers=admin_headers
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        "/api/v1/platform/plans", json={"name": "B", "code": "PT7-DUP"}, headers=admin_headers
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "duplicate_plan_code"


# 8. duplicate plan-feature -> clean conflict, not a 500
def test_duplicate_plan_feature_returns_clean_conflict(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-8.com")
    admin_headers = _auth(_login(client, "ops@plan-co-8.com")["access_token"])
    plan_resp = client.post(
        "/api/v1/platform/plans", json={"name": "P8", "code": "PT8"}, headers=admin_headers
    )
    plan_id = plan_resp.json()["id"]

    resp1 = client.post(
        f"/api/v1/platform/plans/{plan_id}/features",
        json={"feature_key": "DUPFEAT", "enabled": True},
        headers=admin_headers,
    )
    assert resp1.status_code == 201

    resp2 = client.post(
        f"/api/v1/platform/plans/{plan_id}/features",
        json={"feature_key": "DUPFEAT", "enabled": False},
        headers=admin_headers,
    )
    assert resp2.status_code == 409
    assert resp2.json()["error"]["code"] == "duplicate_plan_feature"


# 9. cross-org manipulation is structurally impossible -- plans carry no
# organization_id at all, so there is no org-scoping to bypass in the first
# place. Confirmed directly against the model.
def test_plan_model_has_no_organization_id():
    assert not hasattr(Plan, "organization_id")
    assert not hasattr(PlanFeature, "organization_id")


# 10. every mutation produces exactly one audit event
def test_each_mutation_produces_exactly_one_audit_event(client, db_session):
    admin = _create_platform_admin(db_session, "ops@plan-co-10.com")

    plan = create_plan(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        name="P10",
        code="PT10",
    )
    assert _audit_count(db_session, plan.id) == 1

    plan = set_plan_active(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        is_active=False,
    )
    assert _audit_count(db_session, plan.id) == 2

    feature = create_plan_feature(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key="F10",
        enabled=False,
    )
    assert _audit_count(db_session, feature.id) == 1

    feature = set_plan_feature_enabled(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key="F10",
        enabled=True,
    )
    assert _audit_count(db_session, feature.id) == 2


# 11. read endpoints (list/get) produce zero audit events
def test_read_endpoints_produce_zero_audit_events(client, db_session):
    _create_platform_admin(db_session, "ops@plan-co-11.com")
    admin_headers = _auth(_login(client, "ops@plan-co-11.com")["access_token"])
    plan_resp = client.post(
        "/api/v1/platform/plans", json={"name": "P11", "code": "PT11"}, headers=admin_headers
    )
    plan_id = plan_resp.json()["id"]
    before = db_session.execute(select(AuditEvent)).scalars().all()
    before_count = len(before)

    client.get("/api/v1/platform/plans", headers=admin_headers)
    client.get(f"/api/v1/platform/plans/{plan_id}", headers=admin_headers)
    client.get(f"/api/v1/platform/plans/{plan_id}/features", headers=admin_headers)

    after = db_session.execute(select(AuditEvent)).scalars().all()
    assert len(after) == before_count


# 12. deactivating a plan with an active subscription does not lose the
# tenant's features -- resolve_entitlements still returns INACTIVE_PLAN
# with the real feature map, not an empty/lost one.
def test_deactivate_plan_with_active_subscription_preserves_features(client, db_session):
    admin = _create_platform_admin(db_session, "ops@plan-co-12.com")
    tokens = _register(client, "Plan Tenant 12", "admin@plan-tenant-12.com")
    org_resp = client.get("/api/v1/entitlements", headers=_auth(tokens["access_token"]))
    org_id = org_resp.json()["organization_id"]

    plan = create_plan(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        name="P12",
        code="PT12",
    )
    create_plan_feature(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key="LISA",
        enabled=True,
    )
    from datetime import UTC, datetime, timedelta

    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org_id)
    assert result.resolution_status == EntitlementResolutionStatus.ACTIVE
    assert result.effective_features["LISA"] is True

    set_plan_active(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        is_active=False,
    )

    result2 = resolve_entitlements(db_session, organization_id=org_id)
    assert result2.resolution_status == EntitlementResolutionStatus.INACTIVE_PLAN
    assert result2.effective_features["LISA"] is True


# M2 integration verification: live read-after-write correctness through the
# real service layer, zero changes to entitlement_service.py itself.
def test_m2_integration_live_read_after_write(client, db_session):
    admin = _create_platform_admin(db_session, "ops@plan-co-13.com")
    tokens = _register(client, "Plan Tenant 13", "admin@plan-tenant-13.com")
    org_resp = client.get("/api/v1/entitlements", headers=_auth(tokens["access_token"]))
    org_id = org_resp.json()["organization_id"]

    plan = create_plan(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        name="P13",
        code="PT13",
    )
    create_plan_feature(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key="LISA",
        enabled=False,
    )
    from datetime import UTC, datetime, timedelta

    sub = Subscription(
        organization_id=org_id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.commit()

    result = resolve_entitlements(db_session, organization_id=org_id)
    assert result.effective_features["LISA"] is False

    set_plan_feature_enabled(
        db_session,
        actor_user_id=admin.id,
        actor_organization_id=admin.organization_id,
        plan_id=plan.id,
        feature_key="LISA",
        enabled=True,
    )

    result2 = resolve_entitlements(db_session, organization_id=org_id)
    assert result2.effective_features["LISA"] is True


# Transaction safety: a duplicate-code conflict during create_plan leaves
# NEITHER a partial plan row NOR an audit event.
#
# Note: create_plan's IntegrityError-recovery calls db.rollback(). Verified
# directly (see scratch repro) that in THIS fixture's setup -- a Session bound
# straight to a single already-active Connection transaction, no savepoint --
# that rollback() undoes the *entire* flat test transaction, not just the
# failed call, exactly the same documented gotcha called out in
# app/services/aircraft_service.py and
# tests/integration/test_lisa_ask_context_integration.py's
# test_duplicate_aircraft_registration_is_rejected_so_lisa_never_sees_ambiguity.
# So this test seeds the "existing" plan through a genuinely-committed,
# separate connection (the session-scoped `engine` fixture, autocommitted)
# rather than through db_session, so its row's survival can be verified from
# outside db_session's transaction regardless of any rollback the service
# performs inside it.
def test_duplicate_create_plan_leaves_no_partial_row_or_audit_event(db_session, engine):
    admin = _create_platform_admin(db_session, "ops@plan-co-14.com")

    with engine.connect() as raw_conn:
        raw_conn.execute(
            Plan.__table__.insert().values(
                id=uuid.uuid4(), name="First", code="PT14-DUP", is_active=True
            )
        )
        raw_conn.commit()

    from app.core.errors import ConflictError

    raised = False
    try:
        create_plan(
            db_session,
            actor_user_id=admin.id,
            actor_organization_id=admin.organization_id,
            name="Second",
            code="PT14-DUP",
        )
    except ConflictError:
        raised = True
    assert raised

    with engine.connect() as raw_conn:
        rows = raw_conn.execute(
            select(Plan).where(Plan.code == "PT14-DUP")
        ).all()
    assert len(rows) == 1  # still only the genuinely-committed first plan

    with engine.connect() as raw_conn:
        audit_rows = raw_conn.execute(
            select(AuditEvent).where(AuditEvent.action == "platform.plan.created")
        ).all()
    assert audit_rows == []  # the failed second create left no committed audit event

    # cleanup: this row was committed outside db_session's rolled-back
    # transaction, so it must be removed explicitly.
    with engine.connect() as raw_conn:
        raw_conn.execute(Plan.__table__.delete().where(Plan.__table__.c.code == "PT14-DUP"))
        raw_conn.commit()
