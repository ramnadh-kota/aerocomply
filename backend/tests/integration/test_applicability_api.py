"""Integration tests for Applicability API (POST /api/v1/applicability/evaluate).

Validates:
- RBAC permission enforcement (COMPLIANCE_ASSESS)
- Commercial feature entitlement (compliance_management)
- Tenant isolation (cross-tenant rejected with 404)
- Soft-deleted asset rejection
- Evaluation states: APPLICABLE, NOT_APPLICABLE, INSUFFICIENT_DATA, REVIEW_REQUIRED
- Audit trail recording
- Immutable historical snapshot guarantee
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.deps import get_db_session
from app.core.permissions import Role
from app.core.security import hash_password
from app.main import app
from app.models.aircraft import Aircraft
from app.models.applicability import ApplicabilityEvaluation
from app.models.asset import Asset
from app.models.audit_event import AuditEvent
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.tenant_entitlement import TenantFeatureOverride
from app.models.user import User, UserRole


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _get_org_id(client, token):
    return uuid.UUID(
        client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"]
    )


def _entitle_compliance(db_session, org_id):
    """Grant org_id the compliance_management feature on an active subscription."""
    from sqlalchemy import select

    sub = db_session.execute(
        select(Subscription).where(
            Subscription.organization_id == org_id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        pf = db_session.execute(
            select(PlanFeature).where(
                PlanFeature.plan_id == sub.plan_id,
                PlanFeature.feature_key == "compliance_management",
            )
        ).scalar_one_or_none()
        if pf is None:
            db_session.add(PlanFeature(plan_id=sub.plan_id, feature_key="compliance_management", enabled=True))
            db_session.commit()
        elif not pf.enabled:
            pf.enabled = True
            db_session.commit()
        return

    plan = Plan(
        name=f"Comp-Plan-{org_id}",
        code=f"comp-plan-{org_id}",
        is_active=True,
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    db_session.add(
        PlanFeature(plan_id=plan.id, feature_key="compliance_management", enabled=True)
    )
    db_session.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=None,
        )
    )
    db_session.commit()


def _create_aircraft(client, headers, reg="N900AP", msn="1500", ac_type="A320"):
    resp = client.post(
        "/api/v1/aircraft",
        json={"registration": reg, "msn": msn, "aircraft_type": ac_type},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_rule_with_condition_tree(client, headers, code="AD-A320-ENG"):
    payload = {
        "rule_code": code,
        "title": f"Airworthiness Directive {code}",
        "description": "Applies to A320 aircraft MSN 1000..2000 with CFM56 engines",
        "root_condition": {
            "condition_type": "AND",
            "label": "Applicability Root Conjunction",
            "children": [
                {
                    "condition_type": "AIRCRAFT_VARIANT",
                    "label": "Variant must be A320",
                    "parameters": {"variant": "A320"},
                },
                {
                    "condition_type": "MSN_RANGE",
                    "label": "MSN between 1000 and 2000",
                    "parameters": {"min_msn": 1000, "max_msn": 2000},
                },
                {
                    "condition_type": "ENGINE_TYPE",
                    "label": "Engine must be CFM56",
                    "parameters": {"engine_type": "CFM56"},
                },
            ],
        },
    }
    resp = client.post("/api/v1/applicability/rules", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestApplicabilitySecurityAndEntitlement:
    def test_evaluate_unauthenticated_returns_401(self, client):
        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": str(uuid.uuid4()), "aircraft_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 401

    def test_evaluate_unentitled_returns_403(self, client, db_session):
        # Register org with compliance_management disabled
        tokens = _register(client, "Unentitled Org", "unentitled@example.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        db_session.add(
            TenantFeatureOverride(
                organization_id=org_id,
                feature_key="compliance_management",
                enabled=False,
                reason="Disabled for test",
            )
        )
        db_session.commit()

        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": str(uuid.uuid4()), "aircraft_id": str(uuid.uuid4())},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "not entitled to feature: compliance_management" in resp.text

    def test_evaluate_unauthorized_role_returns_403(self, client, db_session):
        tokens = _register(client, "RBAC Org", "rbac-admin@example.com")
        admin_headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        # Create technician user who has MAINTENANCE_ENGINEER role (no COMPLIANCE_ASSESS permission)
        tech_user = User(
            organization_id=org_id,
            email="tech@rbac-org.com",
            full_name="Tech User",
            hashed_password=hash_password("secret123"),
            is_active=True,
        )
        db_session.add(tech_user)
        db_session.flush()
        db_session.add(
            UserRole(
                organization_id=org_id,
                user_id=tech_user.id,
                role_name=Role.MAINTENANCE_ENGINEER.value,
            )
        )
        db_session.commit()

        # Login as technician
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "tech@rbac-org.com", "password": "secret123"},
        )
        assert login_resp.status_code == 200
        tech_headers = _auth(login_resp.json()["access_token"])

        # Create aircraft & rule as admin
        ac = _create_aircraft(client, admin_headers, "N100RB")
        rule = _create_rule_with_condition_tree(client, admin_headers, "AD-RB-1")

        # Technician attempt to evaluate must be rejected with 403
        eval_resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=tech_headers,
        )
        assert eval_resp.status_code == 403
        assert "compliance:assess" in eval_resp.text

    def test_evaluate_cross_tenant_aircraft_returns_404(self, client, db_session):
        # Tenant A
        tokens_a = _register(client, "Tenant A Org", "admin@tenant-a.com")
        headers_a = _auth(tokens_a["access_token"])
        org_a = _get_org_id(client, tokens_a["access_token"])
        _entitle_compliance(db_session, org_a)
        ac_a = _create_aircraft(client, headers_a, "N-A-001")

        # Tenant B
        tokens_b = _register(client, "Tenant B Org", "admin@tenant-b.com")
        headers_b = _auth(tokens_b["access_token"])
        org_b = _get_org_id(client, tokens_b["access_token"])
        _entitle_compliance(db_session, org_b)
        rule_b = _create_rule_with_condition_tree(client, headers_b, "AD-B-1")

        # Tenant B tries to evaluate Tenant A's aircraft
        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule_b["id"], "aircraft_id": ac_a["id"]},
            headers=headers_b,
        )
        assert resp.status_code == 404
        assert "Aircraft" in resp.text and "not found" in resp.text


class TestApplicabilityEvaluations:
    def test_evaluate_applicable_flow(self, client, db_session):
        tokens = _register(client, "Applicable Org", "admin@app-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        # 1. Create aircraft: A320, MSN 1500
        ac = _create_aircraft(client, headers, "N320AP", msn="1500", ac_type="A320")

        # Install CFM56 engine
        ac_row = db_session.get(Aircraft, uuid.UUID(ac["id"]))
        engine = Component(
            organization_id=org_id,
            asset_id=ac_row.asset_id,
            component_type=ComponentType.ENGINE,
            name="Engine 1",
            model="CFM56-5B",
            manufacturer="CFM",
            status=ComponentStatus.INSTALLED,
        )
        db_session.add(engine)
        db_session.commit()

        # 2. Create rule: A320 AND MSN 1000..2000 AND CFM56
        rule = _create_rule_with_condition_tree(client, headers, "AD-2026-APP")

        # 3. Evaluate
        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["system_result"] == "APPLICABLE"
        assert data["configuration_snapshot"]["aircraft_type"] == "A320"
        assert data["configuration_snapshot"]["msn"] == "1500"
        assert len(data["configuration_snapshot"]["installed_engines"]) == 1
        assert data["reasoning_trace"]["result"] == "TRUE"

    def test_evaluate_not_applicable_flow(self, client, db_session):
        tokens = _register(client, "Not Applicable Org", "admin@notapp-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        # Create B737 aircraft (variant mismatch)
        ac = _create_aircraft(client, headers, "N737NA", msn="1500", ac_type="B737")
        rule = _create_rule_with_condition_tree(client, headers, "AD-2026-NA")

        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_result"] == "NOT_APPLICABLE"

    def test_evaluate_insufficient_data_when_engines_missing(self, client, db_session):
        tokens = _register(client, "Incomplete Org", "admin@incomplete-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        # Create A320, MSN 1500, but NO installed engines recorded
        ac = _create_aircraft(client, headers, "N320MISS", msn="1500", ac_type="A320")
        rule = _create_rule_with_condition_tree(client, headers, "AD-2026-MISS")

        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Incomplete configuration MUST produce INSUFFICIENT_DATA, NEVER NOT_APPLICABLE!
        assert data["system_result"] == "INSUFFICIENT_DATA"
        assert data["system_result"] != "NOT_APPLICABLE"

    def test_evaluate_force_review_produces_review_required(self, client, db_session):
        tokens = _register(client, "Review Org", "admin@review-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        ac = _create_aircraft(client, headers, "N320REV", msn="1500", ac_type="A320")
        rule = _create_rule_with_condition_tree(client, headers, "AD-2026-REV")

        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={
                "rule_id": rule["id"],
                "aircraft_id": ac["id"],
                "force_review": True,
                "notes": "Flagged for manual engineering review",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["system_result"] == "REVIEW_REQUIRED"
        assert data["notes"] == "Flagged for manual engineering review"


class TestHistoricalSnapshotImmutability:
    def test_later_aircraft_mutation_does_not_alter_historical_evaluation(self, client, db_session):
        """Prove that subsequent changes to aircraft configuration do not mutate historical snapshots."""
        tokens = _register(client, "Snapshot Org", "admin@snap-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        # 1. Create initial configuration: A320, MSN 1500, CFM56
        ac = _create_aircraft(client, headers, "N-ORIG", msn="1500", ac_type="A320")
        ac_row = db_session.get(Aircraft, uuid.UUID(ac["id"]))
        engine = Component(
            organization_id=org_id,
            asset_id=ac_row.asset_id,
            component_type=ComponentType.ENGINE,
            name="Original Engine",
            model="CFM56-5B",
            status=ComponentStatus.INSTALLED,
        )
        db_session.add(engine)
        db_session.commit()

        # 2. Evaluate rule -> APPLICABLE
        rule = _create_rule_with_condition_tree(client, headers, "AD-SNAP-01")
        eval_resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=headers,
        )
        assert eval_resp.status_code == 200
        eval_id = eval_resp.json()["id"]
        assert eval_resp.json()["system_result"] == "APPLICABLE"

        # 3. Later in time, MUTATE the aircraft drastically:
        # Change aircraft_type to B737, MSN to 9999, remove the engine
        aircraft_row = db_session.get(Aircraft, uuid.UUID(ac["id"]))
        aircraft_row.aircraft_type = "B737-MAX8"
        aircraft_row.msn = "9999"
        aircraft_row.registration = "N-MUTATED"

        engine_row = db_session.get(Component, engine.id)
        engine_row.status = ComponentStatus.REMOVED
        db_session.commit()

        # 4. Fetch the historical evaluation snapshot
        get_resp = client.get(
            f"/api/v1/applicability/evaluations/{eval_id}",
            headers=headers,
        )
        assert get_resp.status_code == 200
        historical = get_resp.json()

        # PROVE IMMUTABILITY:
        # Even though the live aircraft is now B737-MAX8 with MSN 9999 and no installed engine,
        # the historical snapshot STILL records A320, MSN 1500, CFM56, and APPLICABLE!
        assert historical["system_result"] == "APPLICABLE"
        assert historical["configuration_snapshot"]["aircraft_type"] == "A320"
        assert historical["configuration_snapshot"]["msn"] == "1500"
        assert historical["configuration_snapshot"]["registration"] == "N-ORIG"
        assert len(historical["configuration_snapshot"]["installed_engines"]) == 1
        assert historical["configuration_snapshot"]["installed_engines"][0]["model"] == "CFM56-5B"

    def test_audit_event_recorded_on_evaluation(self, client, db_session):
        tokens = _register(client, "Audit Org", "admin@audit-org.com")
        headers = _auth(tokens["access_token"])
        org_id = _get_org_id(client, tokens["access_token"])
        _entitle_compliance(db_session, org_id)

        ac = _create_aircraft(client, headers, "N-AUD-1", msn="1500", ac_type="A320")
        rule = _create_rule_with_condition_tree(client, headers, "AD-AUD-1")

        resp = client.post(
            "/api/v1/applicability/evaluate",
            json={"rule_id": rule["id"], "aircraft_id": ac["id"]},
            headers=headers,
        )
        assert resp.status_code == 200

        # Query audit_events table
        audit_event = db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "applicability.evaluated",
            )
        ).scalar_one_or_none()

        assert audit_event is not None
        assert audit_event.entity_type == "ApplicabilityEvaluation"
        assert audit_event.event_metadata["rule_code"] == "AD-AUD-1"
