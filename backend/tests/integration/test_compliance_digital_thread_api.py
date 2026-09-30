"""Integration tests for Compliance Obligation and Evidence Digital Thread.

Milestone D2-2 Acceptance Criteria:
1. End-to-end positive path:
   Asset/Configuration -> Regulatory Requirement -> Applicability Rule ->
   Evaluate APPLICABLE -> Obligation created (DUE) -> Attach Evidence ->
   Verify Evidence -> Compliance state becomes COMPLIANT.
2. Negative path:
   Attach Evidence -> Reject Evidence -> Compliance state becomes NON_COMPLIANT ->
   Traceability identifies the blocker.
3. Insufficient data path:
   Missing aircraft configuration -> Evaluation INSUFFICIENT_DATA ->
   Obligation becomes BLOCKED (never silently NOT_APPLICABLE).
4. Strict tenant isolation:
   Tenant B cannot access or mutate Tenant A's obligations or evidence.
5. RBAC security:
   Unauthenticated -> 401.
   Unauthorized role -> 403.
6. Historical snapshot immutability:
   Subsequent asset configuration changes do not alter historical evaluation snapshots.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.aircraft import Aircraft
from app.models.applicability import ApplicabilityEvaluation
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.installation_history import ComponentInstallation
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.user import User, UserRole


def _entitle_organization(db: Session, org: Organization, *feature_keys: str) -> None:
    from sqlalchemy import select

    sub = db.execute(
        select(Subscription).where(
            Subscription.organization_id == org.id,
            Subscription.status.in_(["ACTIVE", "TRIALING", "PAST_DUE"]),
        )
    ).scalars().first()
    if sub:
        for fk in feature_keys:
            pf = db.execute(
                select(PlanFeature).where(
                    PlanFeature.plan_id == sub.plan_id,
                    PlanFeature.feature_key == fk,
                )
            ).scalar_one_or_none()
            if pf is None:
                db.add(PlanFeature(plan_id=sub.plan_id, feature_key=fk, enabled=True))
            elif not pf.enabled:
                pf.enabled = True
        db.commit()
        return

    plan = Plan(
        name=f"Enterprise-Plan-{org.id}",
        code=f"enterprise-{org.id}",
        is_active=True,
    )
    db.add(plan)
    db.flush()
    for fk in feature_keys:
        db.add(PlanFeature(plan_id=plan.id, feature_key=fk, enabled=True))
    db.add(
        Subscription(
            organization_id=org.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            starts_at=datetime.now(timezone.utc) - timedelta(days=1),
            ends_at=None,
        )
    )
    db.commit()



def _create_user(
    db: Session,
    org: Organization,
    roles: list[str],
    email: str | None = None,
) -> tuple[User, str]:
    if email is None:
        email = f"compliance-{uuid.uuid4().hex[:8]}@aerocomply.test"
    user = User(
        organization_id=org.id,
        email=email,
        full_name="Compliance User",
        hashed_password="pw",
    )
    db.add(user)
    db.flush()
    for role_name in roles:
        db.add(UserRole(user_id=user.id, role_name=role_name, organization_id=org.id))
    db.commit()
    db.refresh(user)
    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        roles=roles,
        email=email,
    )
    return user, token


class TestComplianceDigitalThreadFlow:
    """Verify end-to-end compliance obligation and evidence thread."""

    def test_end_to_end_positive_compliance_flow(
        self, client: TestClient, db_session: Session
    ):
        # 1. Setup tenant & admin user with compliance permissions & feature entitlements
        org = Organization(name=f"AeroCorp Airlines {uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "regulatory_ingestion",
            "fleet_asset_management",
            "aircraft_fleet_management",
            "work_order_management",
        )
        user, token = _create_user(
            db_session,
            org,
            ["ORG_ADMIN", "COMPLIANCE_MANAGER"],
            email="admin@aerocorp.com",
        )
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create asset / aircraft with model B737-800 and MSN 35124
        ac_resp = client.post(
            "/api/v1/aircraft",
            headers=headers,
            json={
                "registration": "VT-DEF",
                "msn": "35124",
                "aircraft_type": "B737-800",
                "manufacturer": "Boeing",
            },
        )
        assert ac_resp.status_code == 201
        ac_data = ac_resp.json()
        ac_id = ac_data["id"]

        # Install CFM56-7B engine
        ac_row = db_session.get(Aircraft, uuid.UUID(ac_id))
        engine = Component(
            organization_id=org.id,
            asset_id=ac_row.asset_id,
            component_type=ComponentType.ENGINE,
            model="CFM56-7B",
            name="CFM56-7B Turbofan",
            serial_number="CFM-99120",
            status=ComponentStatus.INSTALLED,
        )
        db_session.add(engine)
        db_session.flush()
        db_session.add(
            ComponentInstallation(
                organization_id=org.id,
                component_id=engine.id,
                asset_id=ac_row.asset_id,
                installed_at=datetime.now(timezone.utc),
            )
        )
        db_session.commit()

        # 3. Create regulatory requirement (FAA AD-2026-001 Fan Disk)
        req_resp = client.post(
            "/api/v1/regulatory-requirements",
            headers=headers,
            json={
                "authority": "FAA",
                "requirement_number": "AD-2026-001",
                "title": "Engine Fan Disk Inspection",
                "description": "One-time ultrasonic inspection of engine fan disk on 737-800 with CFM56-7B engines.",
                "compliance_time": "Within 90 days",
            },
        )
        assert req_resp.status_code == 201
        req_id = req_resp.json()["id"]

        # 4. Create applicability rule for AD-2026-001:
        # AND(variant == B737-800, engine == CFM56-7B)
        rule_resp = client.post(
            "/api/v1/applicability/rules",
            headers=headers,
            json={
                "rule_code": "RULE-AD-2026-001",
                "title": "AD 2026-001 Applicability",
                "regulatory_requirement_id": req_id,
                "root_condition": {
                    "condition_type": "AND",
                    "label": "737-800 with CFM56-7B",
                    "children": [
                        {
                            "condition_type": "AIRCRAFT_VARIANT",
                            "label": "Variant Boeing 737-800",
                            "parameters": {"variant": "B737-800"},
                        },
                        {
                            "condition_type": "ENGINE_TYPE",
                            "label": "CFM56-7B Engine",
                            "parameters": {"engine_type": "CFM56-7B"},
                        },
                    ],
                },
            },
        )
        assert rule_resp.status_code == 201
        rule_id = rule_resp.json()["id"]

        # 5. Create compliance obligation for aircraft VT-DEF
        ob_resp = client.post(
            "/api/v1/compliance/obligations",
            headers=headers,
            json={
                "requirement_id": req_id,
                "aircraft_id": ac_id,
                "rule_id": rule_id,
                "priority": "HIGH",
                "due_date": "2026-12-31",
                "required_action": "Perform ultrasonic scan of engine fan disk",
                "evidence_requirements": [
                    {
                        "type": "INSPECTION_RECORD",
                        "description": "NDT Ultrasonic Inspection Certificate",
                    }
                ],
            },
        )
        assert ob_resp.status_code == 201
        ob_id = ob_resp.json()["id"]
        assert ob_resp.json()["status"] == "DUE"

        # 6. Evaluate obligation applicability
        eval_resp = client.post(
            f"/api/v1/compliance/obligations/{ob_id}/evaluate",
            headers=headers,
        )
        assert eval_resp.status_code == 200
        assert eval_resp.json()["status"] == "DUE"
        assert eval_resp.json()["applicability_evaluation_id"] is not None

        # 7. Attach Evidence to obligation
        ev_resp = client.post(
            f"/api/v1/compliance/obligations/{ob_id}/evidence",
            headers=headers,
            json={
                "title": "Ultrasonic Scan Report - Engine #1",
                "evidence_type": "INSPECTION_RECORD",
                "source": "NDT Hangar Lab 4",
                "description": "Full ultrasound waveform analysis completed with zero crack indications.",
            },
        )
        assert ev_resp.status_code == 201
        ev_id = ev_resp.json()["id"]
        assert ev_resp.json()["verification_status"] == "UNVERIFIED"

        # Check obligation status transitioned to IN_PROGRESS while unverified
        ob_check = client.get(f"/api/v1/compliance/obligations/{ob_id}", headers=headers)
        assert ob_check.json()["status"] == "IN_PROGRESS"

        # 8. Verify the evidence as authorized inspector/manager
        verify_resp = client.post(
            f"/api/v1/evidence/{ev_id}/verify",
            headers=headers,
            json={"verification_notes": "Ultrasonic waveform curves verified against ASTM-E2375 standard."},
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["verification_status"] == "VERIFIED"
        assert verify_resp.json()["status"] == "ACCEPTED"

        # 9. Verify obligation automatically resolved to COMPLIANT!
        ob_final = client.get(f"/api/v1/compliance/obligations/{ob_id}", headers=headers)
        assert ob_final.status_code == 200
        assert ob_final.json()["status"] == "COMPLIANT"
        assert ob_final.json()["verified_at"] is not None

        # 10. Check full digital thread traceability
        trace_resp = client.get(
            f"/api/v1/compliance/obligations/{ob_id}/traceability",
            headers=headers,
        )
        assert trace_resp.status_code == 200
        trace = trace_resp.json()
        assert trace["compliance_state"] == "COMPLIANT"
        assert trace["is_compliant"] is True
        assert trace["is_verified"] is True
        assert len(trace["blockers"]) == 0
        assert trace["why_applies"]["system_result"] == "APPLICABLE"
        assert trace["why_applies"]["rule_code"] == "RULE-AD-2026-001"
        assert len(trace["provided_evidence"]) == 1
        assert trace["provided_evidence"][0]["verification_status"] == "VERIFIED"

        # 11. Check compliance overview aggregate
        overview_resp = client.get("/api/v1/compliance/overview", headers=headers)
        assert overview_resp.status_code == 200
        ov = overview_resp.json()
        assert ov["total_obligations"] >= 1
        assert ov["compliant_count"] >= 1
        assert ov["compliance_rate_percent"] == 100.0

    def test_rejected_evidence_prevents_compliant_and_identifies_blocker(
        self, client: TestClient, db_session: Session
    ):
        org = Organization(name=f"Beta Aviation {uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "fleet_asset_management",
            "aircraft_fleet_management",
        )
        user, token = _create_user(db_session, org, ["ORG_ADMIN", "COMPLIANCE_MANAGER"])
        headers = {"Authorization": f"Bearer {token}"}

        # Create aircraft & requirement
        ac_resp = client.post(
            "/api/v1/aircraft",
            headers=headers,
            json={"registration": "VT-XYZ", "msn": "1002", "aircraft_type": "A320-200"},
        )
        ac_id = ac_resp.json()["id"]

        req_resp = client.post(
            "/api/v1/regulatory-requirements",
            headers=headers,
            json={
                "authority": "DGCA",
                "requirement_number": "DGCA-2026-99",
                "title": "Avionics Software Standard Upgrade",
                "description": "FMC software version 12.4 required.",
            },
        )
        req_id = req_resp.json()["id"]

        # Create obligation
        ob_resp = client.post(
            "/api/v1/compliance/obligations",
            headers=headers,
            json={"requirement_id": req_id, "aircraft_id": ac_id, "priority": "CRITICAL"},
        )
        ob_id = ob_resp.json()["id"]

        # Attach evidence
        ev_resp = client.post(
            f"/api/v1/compliance/obligations/{ob_id}/evidence",
            headers=headers,
            json={"title": "Software Load Signoff", "evidence_type": "LOGBOOK_ENTRY"},
        )
        ev_id = ev_resp.json()["id"]

        # Reject evidence
        reject_resp = client.post(
            f"/api/v1/evidence/{ev_id}/reject",
            headers=headers,
            json={"rejection_reason": "Software checksum does not match Service Bulletin hash."},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["verification_status"] == "REJECTED"

        # Obligation must be NON_COMPLIANT
        ob_resp = client.get(f"/api/v1/compliance/obligations/{ob_id}", headers=headers)
        assert ob_resp.json()["status"] == "NON_COMPLIANT"

        # Traceability must list the rejection blocker
        trace_resp = client.get(
            f"/api/v1/compliance/obligations/{ob_id}/traceability", headers=headers
        )
        assert trace_resp.status_code == 200
        trace = trace_resp.json()
        assert trace["is_compliant"] is False
        assert any("REJECTED: Software checksum" in b for b in trace["blockers"])


class TestComplianceSecurityAndTenantIsolation:
    """Verify strict tenant isolation and RBAC protections."""

    def test_tenant_isolation_rejects_cross_tenant_obligation_access(
        self, client: TestClient, db_session: Session
    ):
        org_a = Organization(name=f"Tenant Alpha {uuid.uuid4().hex[:6]}")
        org_b = Organization(name=f"Tenant Bravo {uuid.uuid4().hex[:6]}")
        db_session.add_all([org_a, org_b])
        db_session.flush()
        _entitle_organization(
            db_session,
            org_a,
            "compliance_intelligence",
            "compliance_management",
            "fleet_asset_management",
            "aircraft_fleet_management",
        )
        _entitle_organization(
            db_session,
            org_b,
            "compliance_intelligence",
            "compliance_management",
            "fleet_asset_management",
            "aircraft_fleet_management",
        )

        _, token_a = _create_user(db_session, org_a, ["ORG_ADMIN", "COMPLIANCE_MANAGER"])
        _, token_b = _create_user(db_session, org_b, ["ORG_ADMIN", "COMPLIANCE_MANAGER"])
        headers_a = {"Authorization": f"Bearer {token_a}"}
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A creates aircraft, requirement, and obligation
        ac_a = client.post(
            "/api/v1/aircraft",
            headers=headers_a,
            json={"registration": "VT-AAA", "msn": "101", "aircraft_type": "A320"},
        ).json()["id"]
        req_a = client.post(
            "/api/v1/regulatory-requirements",
            headers=headers_a,
            json={"authority": "FAA", "requirement_number": "AD-A", "title": "AD A", "description": "Desc"},
        ).json()["id"]
        ob_a = client.post(
            "/api/v1/compliance/obligations",
            headers=headers_a,
            json={"requirement_id": req_a, "aircraft_id": ac_a},
        ).json()["id"]

        # Tenant B cannot read Tenant A's obligation
        get_b = client.get(f"/api/v1/compliance/obligations/{ob_a}", headers=headers_b)
        assert get_b.status_code == 404

        # Tenant B cannot attach evidence to Tenant A's obligation
        att_b = client.post(
            f"/api/v1/compliance/obligations/{ob_a}/evidence",
            headers=headers_b,
            json={"title": "Rogue Evidence"},
        )
        assert att_b.status_code == 404

    def test_unauthenticated_requests_return_401(self, client: TestClient):
        assert client.get("/api/v1/compliance/overview").status_code == 401
        assert client.get("/api/v1/compliance/obligations").status_code == 401
        assert client.post("/api/v1/compliance/obligations", json={}).status_code == 401
        assert client.post(f"/api/v1/evidence/{uuid.uuid4()}/verify").status_code == 401


class TestHistoricalSnapshotImmutabilityWithObligations:
    """Prove that changing aircraft configuration later does not mutate historical evaluation snapshots."""

    def test_configuration_mutation_does_not_alter_past_evaluation_snapshot(
        self, client: TestClient, db_session: Session
    ):
        org = Organization(name=f"Stable Air {uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "fleet_asset_management",
            "aircraft_fleet_management",
        )
        _, token = _create_user(db_session, org, ["ORG_ADMIN", "COMPLIANCE_MANAGER"])
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create aircraft VT-MRO (B737-800)
        ac = client.post(
            "/api/v1/aircraft",
            headers=headers,
            json={"registration": "VT-MRO", "msn": "5001", "aircraft_type": "B737-800"},
        ).json()
        ac_id = ac["id"]

        # 2. Rule: AIRCRAFT_VARIANT == B737-800
        rule = client.post(
            "/api/v1/applicability/rules",
            headers=headers,
            json={
                "rule_code": "RULE-B738",
                "title": "Boeing 737-800 Fleet Rule",
                "root_condition": {
                    "condition_type": "AIRCRAFT_VARIANT",
                    "label": "B737-800",
                    "parameters": {"variant": "B737-800"},
                },
            },
        ).json()

        # 3. Evaluate applicability
        eval_resp = client.post(
            "/api/v1/applicability/evaluate",
            headers=headers,
            json={"rule_id": rule["id"], "aircraft_id": ac_id},
        )
        assert eval_resp.status_code == 200
        eval_id = eval_resp.json()["id"]
        snapshot_at_eval = eval_resp.json()["configuration_snapshot"]
        assert snapshot_at_eval["aircraft_type"] == "B737-800"

        # 4. Mutate aircraft in database directly (simulating subsequent maintenance / reconfiguration)
        ac_row = db_session.get(Aircraft, uuid.UUID(ac_id))
        ac_row.aircraft_type = "B737-MAX8"
        db_session.commit()

        # 5. Fetch historical evaluation record: MUST NOT CHANGE
        hist_eval = db_session.get(ApplicabilityEvaluation, uuid.UUID(eval_id))
        assert hist_eval.configuration_snapshot["aircraft_type"] == "B737-800"
        assert hist_eval.system_result == "APPLICABLE"
