from __future__ import annotations

import datetime
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.asset import Asset, AssetType
from app.models.mro_intelligence import (
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.organization import OnboardingStage, Organization, OrganizationStatus
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus, WorkOrderType
from tests.integration.conftest import grant_features


@pytest.fixture
def h87_org(db_session: Session) -> Organization:
    org = Organization(
        name="H8.7 Predictive Maintenance Org",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    grant_features(db_session, org.id, "mro_intelligence", "work_order_management", "predictive_maintenance")
    return org


@pytest.fixture
def h87_reviewer_token(db_session: Session, h87_org: Organization) -> str:
    user = User(
        id=uuid.uuid4(),
        email=f"reviewer-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password123!"),
        organization_id=h87_org.id,
        full_name="Reviewer User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="ORG_ADMIN", organization_id=h87_org.id))
    db_session.commit()
    return create_access_token(
        user_id=user.id,
        organization_id=h87_org.id,
        roles=["ORG_ADMIN"],
    )


@pytest.fixture
def h87_viewer_token(db_session: Session, h87_org: Organization) -> str:
    user = User(
        id=uuid.uuid4(),
        email=f"viewer-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password123!"),
        organization_id=h87_org.id,
        full_name="Viewer User",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="VIEWER", organization_id=h87_org.id))
    db_session.commit()
    return create_access_token(
        user_id=user.id,
        organization_id=h87_org.id,
        roles=["VIEWER"],
    )


@pytest.fixture
def h87_asset(db_session: Session, h87_org: Organization) -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        organization_id=h87_org.id,
        asset_type=AssetType.DRONE,
        model="Alpha-Heavy Drone",
        serial_number=f"DRONE-{uuid.uuid4().hex[:6]}",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def h87_candidate(db_session: Session, h87_org: Organization, h87_asset: Asset) -> MaintenanceIntelligenceCandidate:
    candidate = MaintenanceIntelligenceCandidate(
        id=uuid.uuid4(),
        organization_id=h87_org.id,
        asset_id=h87_asset.id,
        candidate_type=MROCandidateType.MAINTENANCE_ATTENTION,
        status=MROCandidateStatus.OPEN,
        priority=MROCandidatePriority.HIGH,
        confidence=0.88,
        reason="Elevated motor vibration exceeding baseline harmonics by 3.2 sigma",
        dedup_key=f"dedup-{uuid.uuid4().hex}",
        source_lineage=[{"source_type": "HUMSExceedance", "label": "Motor Bearing Harmonics"}],
        operational_impact="RESTRICTED_OPERATION",
        data_freshness="FRESH",
    )
    db_session.add(candidate)
    db_session.commit()
    db_session.refresh(candidate)
    return candidate


def test_list_candidates_across_fleet(client: TestClient, h87_reviewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate):
    headers = {"Authorization": f"Bearer {h87_reviewer_token}"}
    resp = client.get("/api/v1/mro-intelligence/candidates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    found = next((c for c in data if c["id"] == str(h87_candidate.id)), None)
    assert found is not None
    assert found["priority"] == "HIGH"
    assert found["confidence"] == 0.88


def test_candidate_review_and_accept_lifecycle(client: TestClient, h87_reviewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate):
    headers = {"Authorization": f"Bearer {h87_reviewer_token}"}
    # Review
    resp = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/review",
        json={"notes": "Investigating high-frequency vibration spike"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == MROCandidateStatus.UNDER_REVIEW

    # Accept
    resp = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/accept",
        json={"notes": "Confirmed anomaly; ready for maintenance drafting"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == MROCandidateStatus.ACCEPTED


def test_human_authorized_draft_work_order(client: TestClient, h87_reviewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate, db_session: Session):
    headers = {"Authorization": f"Bearer {h87_reviewer_token}"}
    
    # First accept candidate
    client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/accept",
        json={"notes": "Authorized for work order"},
        headers=headers,
    )

    # Draft work order
    resp = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        json={"title": "Replace Motor Bearing Assembly", "notes": "Authorized by CAMO Manager"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["work_order_status"] == WorkOrderStatus.DRAFT
    assert data["candidate"]["status"] == MROCandidateStatus.RESOLVED
    assert "Converted to Work Order" in data["candidate"]["review_notes"]

    # Verify work order in DB
    wo_id = uuid.UUID(data["work_order_id"])
    wo = db_session.get(WorkOrder, wo_id)
    assert wo is not None
    assert wo.source_type == "PREDICTIVE_INTELLIGENCE"
    assert wo.source_reference == str(h87_candidate.id)
    assert wo.asset_id == h87_candidate.asset_id
    assert wo.status == WorkOrderStatus.DRAFT


def test_prevent_duplicate_draft_work_orders(client: TestClient, h87_reviewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate):
    headers = {"Authorization": f"Bearer {h87_reviewer_token}"}
    # Draft first time
    resp1 = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        json={"notes": "Initial draft"},
        headers=headers,
    )
    assert resp1.status_code == 200

    # Draft second time -> should raise Conflict (409)
    resp2 = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        json={"notes": "Duplicate attempt"},
        headers=headers,
    )
    assert resp2.status_code == 409


def test_cannot_draft_from_rejected_candidate(client: TestClient, h87_reviewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate):
    headers = {"Authorization": f"Bearer {h87_reviewer_token}"}
    # Reject candidate
    resp_reject = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/reject",
        json={"notes": "False alarm; sensor calibration issue"},
        headers=headers,
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["status"] == MROCandidateStatus.REJECTED

    # Attempt drafting work order
    resp_draft = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        headers=headers,
    )
    assert resp_draft.status_code == 409


def test_unauthorized_user_forbidden(client: TestClient, h87_viewer_token: str, h87_candidate: MaintenanceIntelligenceCandidate):
    headers = {"Authorization": f"Bearer {h87_viewer_token}"}
    resp = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        headers=headers,
    )
    assert resp.status_code == 403


def test_cross_tenant_candidate_isolation(client: TestClient, db_session: Session, h87_candidate: MaintenanceIntelligenceCandidate):
    # Other org & user
    other_org = Organization(
        name="Other Org",
        status=OrganizationStatus.ACTIVE,
        onboarding_stage=OnboardingStage.ACTIVE,
    )
    db_session.add(other_org)
    db_session.commit()
    grant_features(db_session, other_org.id, "mro_intelligence", "work_order_management", "predictive_maintenance")

    other_user = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("Password123!"),
        organization_id=other_org.id,
        full_name="Other User",
        is_active=True,
    )
    db_session.add(other_user)
    db_session.flush()
    db_session.add(UserRole(user_id=other_user.id, role_name="ORG_ADMIN", organization_id=other_org.id))
    db_session.commit()

    token = create_access_token(
        user_id=other_user.id,
        organization_id=other_org.id,
        roles=["ORG_ADMIN"],
    )

    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        f"/api/v1/mro-intelligence/candidates/{h87_candidate.id}/draft-work-order",
        headers=headers,
    )
    assert resp.status_code == 404
