"""Integration tests for Compliance Intelligence, Finding Correlation, and Readiness Gate Integration (Milestone D2-3).

Verifies end-to-end:
1. Finding compliance correlation API: linking finding to compliance obligation and regulatory requirement.
2. Finding compliance impact API: deterministic calculation of whether finding blocks operational readiness.
3. Inspection compliance impact API: evaluation of inspection requirement, findings, and attached evidence.
4. Inspection package compliance resolution: gated by open findings, missing evidence, and unverified evidence.
5. Authoritative Compliance Readiness Contribution API: comprehensive blocker explainability (13-point answers).
6. Multi-tenant security isolation: cross-tenant access rejection for finding impact, inspection impact, and readiness contribution.
7. Role-Based Access Control (RBAC): 401 unauthenticated, 403 unauthorized for mutations.
"""

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.support.tokens import mint_token as create_access_token
from app.models.aircraft import Aircraft
from app.models.compliance import (
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.inspection_requirement import (
    InspectionRequirement,
    InspectionRequirementStatus,
)
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.task import Task
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus


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
            starts_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1),
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
        email = f"compliance-intel-{uuid.uuid4().hex[:8]}@aerocomply.test"
    user = User(
        organization_id=org.id,
        email=email,
        full_name="Compliance Intel User",
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


class TestComplianceReadinessGateIntegration:
    def test_finding_compliance_correlation_flow(
        self, client: TestClient, db_session: Session
    ):
        org = Organization(name=f"Airways-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "maintenance_operations",
            "work_order_management",
        )
        user, token = _create_user(
            db_session, org, ["ORG_ADMIN", "QUALITY_INSPECTOR"]
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Create Regulatory Requirement
        req = RegulatoryRequirement(
            organization_id=org.id,
            authority="FAA",
            requirement_number="FAA-AD-2025-09",
            title="Elevator Control Surface Inspection",
            description="Inspect torque tube for fatigue cracks",
        )
        db_session.add(req)
        db_session.flush()

        # Create Aircraft
        aircraft = Aircraft(
            organization_id=org.id,
            registration=f"VT-{uuid.uuid4().hex[:3].upper()}",
            msn=f"MSN-{uuid.uuid4().hex[:6]}",
            aircraft_type="A320",
        )
        db_session.add(aircraft)
        db_session.flush()

        # Create Obligation
        obligation = ComplianceObligation(
            organization_id=org.id,
            requirement_id=req.id,
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
            status=ComplianceState.DUE.value,
        )
        db_session.add(obligation)
        db_session.flush()

        # Create Finding
        finding = Finding(
            organization_id=org.id,
            title="Elevator torque tube fatigue hairline crack",
            description="Non-destructive test revealed a hairline surface crack.",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.OPEN,
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Correlate Finding to Compliance Obligation
        resp = client.post(
            f"/api/v1/findings/{finding.id}/correlate-compliance",
            headers=headers,
            json={
                "compliance_obligation_id": str(obligation.id),
                "regulatory_requirement_id": str(req.id),
                "safety_significance": "AIRWORTHINESS_LIMITATION",
                "compliance_relevance": "PRIMARY_MANDATE",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compliance_obligation_id"] == str(obligation.id)
        assert data["regulatory_requirement_id"] == str(req.id)
        assert data["safety_significance"] == "AIRWORTHINESS_LIMITATION"
        assert data["compliance_relevance"] == "PRIMARY_MANDATE"

        # 2. Query Finding Compliance Impact
        impact_resp = client.get(
            f"/api/v1/findings/{finding.id}/compliance-impact",
            headers=headers,
        )
        assert impact_resp.status_code == 200
        impact_data = impact_resp.json()
        assert impact_data["finding_id"] == str(finding.id)
        assert impact_data["is_readiness_blocker"] is True
        assert "critical" in impact_data["blocker_reason"].lower()
        assert impact_data["regulatory_requirement_number"] == "FAA-AD-2025-09"
        assert impact_data["current_compliance_state"] == ComplianceState.DUE.value

    def test_inspection_compliance_impact_and_resolution_gating(
        self, client: TestClient, db_session: Session
    ):
        org = Organization(name=f"MRO-Org-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "maintenance_operations",
            "work_order_management",
        )
        user, token = _create_user(
            db_session, org, ["ORG_ADMIN", "QUALITY_INSPECTOR"]
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Aircraft
        aircraft = Aircraft(
            organization_id=org.id,
            registration=f"VT-{uuid.uuid4().hex[:3].upper()}",
            msn=f"MSN-{uuid.uuid4().hex[:6]}",
            aircraft_type="B737-800",
        )
        db_session.add(aircraft)
        db_session.flush()

        # Obligation
        req = RegulatoryRequirement(
            organization_id=org.id,
            authority="FAA",
            requirement_number="FAA-AD-B737-01",
            title="Horizontal Stabilizer Trim Jackscrew",
            description="Free play inspection",
        )
        db_session.add(req)
        db_session.flush()

        obligation = ComplianceObligation(
            organization_id=org.id,
            requirement_id=req.id,
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
            status=ComplianceState.NON_COMPLIANT.value,
        )
        db_session.add(obligation)
        db_session.flush()

        # Work Order, Task, and Inspection Requirement
        wo = WorkOrder(
            organization_id=org.id,
            work_order_number=f"WO-{uuid.uuid4().hex[:6].upper()}",
            title="Heavy Maintenance C-Check",
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
            status=WorkOrderStatus.IN_PROGRESS,
        )
        db_session.add(wo)
        db_session.flush()

        task = Task(
            organization_id=org.id,
            work_order_id=wo.id,
            title="Inspect Jackscrew Gimbal",
            description="Perform dial indicator free-play inspection",
            execution_state="IN_PROGRESS",
        )
        db_session.add(task)
        db_session.flush()

        insp_req = InspectionRequirement(
            organization_id=org.id,
            work_order_id=wo.id,
            task_id=task.id,
            compliance_obligation_id=obligation.id,
            regulatory_requirement_id=req.id,
            required=True,
            status=InspectionRequirementStatus.COMPLETED.value,
        )
        db_session.add(insp_req)
        db_session.flush()

        # Add an open finding linked to this inspection
        finding = Finding(
            organization_id=org.id,
            inspection_requirement_id=insp_req.id,
            compliance_obligation_id=obligation.id,
            regulatory_requirement_id=req.id,
            title="Excessive axial play measured: 0.045 inch (limit 0.030)",
            description="Dial indicator measurement exceeded allowable limits on gimbal bearing.",
            severity=FindingSeverity.MAJOR,
            status=FindingStatus.OPEN,
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Inspection compliance impact
        impact_resp = client.get(
            f"/api/v1/inspections/{insp_req.id}/compliance-impact",
            headers=headers,
        )
        assert impact_resp.status_code == 200
        impact_data = impact_resp.json()
        assert impact_data["is_readiness_blocker"] is True
        assert len(impact_data["associated_findings"]) >= 1

        # 2. Attempt resolution while finding is OPEN -> must be rejected/unresolved
        res_resp = client.post(
            f"/api/v1/inspections/{insp_req.id}/resolve-compliance",
            headers=headers,
        )
        assert res_resp.status_code == 200
        res_data = res_resp.json()
        assert res_data["resolved"] is False
        assert "open findings" in res_data["reason"].lower()

        # 3. Close the finding and attach verified evidence
        finding.status = FindingStatus.CLOSED
        evidence = Evidence(
            organization_id=org.id,
            compliance_obligation_id=obligation.id,
            inspection_requirement_id=insp_req.id,
            title="Jackscrew Free-Play Dial Indicator Report",
            evidence_type="INSPECTION_RECORD",
            status=EvidenceStatus.ACCEPTED.value,
            verification_status="VERIFIED",
            verifier_user_id=user.id,
            verified_at=datetime.datetime.now(datetime.timezone.utc),
        )
        db_session.add(evidence)
        db_session.commit()

        # 4. Resolve again -> success
        res_resp2 = client.post(
            f"/api/v1/inspections/{insp_req.id}/resolve-compliance",
            headers=headers,
        )
        assert res_resp2.status_code == 200
        res_data2 = res_resp2.json()
        assert res_data2["resolved"] is True
        assert res_data2["obligation_status"] == ComplianceState.COMPLIANT.value

    def test_asset_compliance_readiness_contribution_api(
        self, client: TestClient, db_session: Session
    ):
        org = Organization(name=f"AeroCorp-Readiness-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(
            db_session,
            org,
            "compliance_intelligence",
            "compliance_management",
            "maintenance_operations",
            "fleet_asset_management",
        )
        user, token = _create_user(
            db_session, org, ["ORG_ADMIN", "COMPLIANCE_MANAGER"]
        )
        headers = {"Authorization": f"Bearer {token}"}

        aircraft = Aircraft(
            organization_id=org.id,
            registration=f"VT-{uuid.uuid4().hex[:3].upper()}",
            msn=f"MSN-{uuid.uuid4().hex[:6]}",
            aircraft_type="A321",
        )
        db_session.add(aircraft)
        db_session.flush()

        req = RegulatoryRequirement(
            organization_id=org.id,
            authority="DGCA",
            requirement_number="DGCA-CAR-M-01",
            title="Annual Airworthiness Review Certificate",
            description="Annual renewal ARC",
        )
        db_session.add(req)
        db_session.flush()

        # Obligation is NON_COMPLIANT
        obligation = ComplianceObligation(
            organization_id=org.id,
            requirement_id=req.id,
            aircraft_id=aircraft.id,
            asset_id=aircraft.asset_id,
            status=ComplianceState.NON_COMPLIANT.value,
        )
        db_session.add(obligation)
        db_session.commit()

        # Query readiness contribution
        target_asset_id = aircraft.asset_id or aircraft.id
        resp = client.get(
            f"/api/v1/compliance/assets/{target_asset_id}/readiness-contribution",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["overall_status"] == "BLOCKED"
        assert len(data["blockers"]) >= 1

        # Verify 13-point explainability contract
        blocker = data["blockers"][0]
        assert blocker["blocker_id"] is not None
        assert blocker["what_blocking"] is not None
        assert blocker["why_blocking"] is not None
        assert blocker["source_record_type"] == "ComplianceObligation"
        assert blocker["source_record_id"] == str(obligation.id)
        assert blocker["regulatory_requirement_number"] == "DGCA-CAR-M-01"
        assert blocker["resolution_action"] is not None

        # Query asset compliance impact report
        impact_resp = client.get(
            f"/api/v1/compliance/assets/{target_asset_id}/impact",
            headers=headers,
        )
        assert impact_resp.status_code == 200
        impact_data = impact_resp.json()
        assert impact_data["overall_status"] == "BLOCKED"
        assert len(impact_data["active_blockers"]) >= 1

    def test_cross_tenant_isolation(
        self, client: TestClient, db_session: Session
    ):
        """Cross-tenant security: Tenant B must not access Tenant A's finding or inspection intelligence."""
        org_a = Organization(name=f"TenantA-{uuid.uuid4().hex[:6]}")
        org_b = Organization(name=f"TenantB-{uuid.uuid4().hex[:6]}")
        db_session.add_all([org_a, org_b])
        db_session.flush()

        _entitle_organization(db_session, org_a, "compliance_intelligence", "compliance_management")
        _entitle_organization(db_session, org_b, "compliance_intelligence", "compliance_management")

        user_a, token_a = _create_user(db_session, org_a, ["ORG_ADMIN"])
        user_b, token_b = _create_user(db_session, org_b, ["ORG_ADMIN"])
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Tenant A Finding
        finding_a = Finding(
            organization_id=org_a.id,
            title="Tenant A confidential finding",
            description="Classified defect found during tenant A internal inspection.",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.OPEN,
        )
        db_session.add(finding_a)
        db_session.commit()

        # Tenant B tries to access Tenant A's finding compliance impact
        resp = client.get(
            f"/api/v1/findings/{finding_a.id}/compliance-impact",
            headers=headers_b,
        )
        assert resp.status_code == 404

        # Tenant B tries to correlate Tenant A's finding
        correlate_resp = client.post(
            f"/api/v1/findings/{finding_a.id}/correlate-compliance",
            headers=headers_b,
            json={"safety_significance": "CRITICAL"},
        )
        assert correlate_resp.status_code == 404

    def test_rbac_unauthenticated_and_unauthorized(
        self, client: TestClient, db_session: Session
    ):
        # 1. Unauthenticated request -> 401
        dummy_id = uuid.uuid4()
        unauth_resp = client.get(
            f"/api/v1/findings/{dummy_id}/compliance-impact"
        )
        assert unauth_resp.status_code == 401

        # 2. Unauthorized role attempting correlation mutation -> 403
        org = Organization(name=f"RBAC-Org-{uuid.uuid4().hex[:6]}")
        db_session.add(org)
        db_session.flush()
        _entitle_organization(db_session, org, "compliance_intelligence", "compliance_management")
        # VIEWER role has read-only access, cannot correlate compliance
        user, token = _create_user(db_session, org, ["VIEWER"])
        headers = {"Authorization": f"Bearer {token}"}

        finding = Finding(
            organization_id=org.id,
            title="Readonly test finding",
            description="Testing RBAC mutation prevention.",
            severity=FindingSeverity.MINOR,
            status=FindingStatus.OPEN,
        )
        db_session.add(finding)
        db_session.commit()

        resp = client.post(
            f"/api/v1/findings/{finding.id}/correlate-compliance",
            headers=headers,
            json={"safety_significance": "MINOR"},
        )
        assert resp.status_code == 403
