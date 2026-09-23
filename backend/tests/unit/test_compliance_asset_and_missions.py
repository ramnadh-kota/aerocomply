from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch
import uuid
import pytest
from pydantic import ValidationError

from app.core.errors import AeroComplyError, NotFoundError
from app.models.asset import Asset, AssetType
from app.models.compliance import ComplianceAssessment, ComplianceAssessmentStatus
from app.models.mission import Mission, MissionStatus
from app.models.user import User
from app.models.work_order import WorkOrder
from app.schemas.compliance import ComplianceAssessmentCreateRequest
from app.schemas.mission import (
    MissionAuthorizeRequest,
    MissionCreateRequest,
    MissionResponse,
    MissionUpdateRequest,
)
from app.services import compliance_service, mission_service, work_order_service


# ---------------------------------------------------------------------------
# Schema & Enum Tests
# ---------------------------------------------------------------------------

def test_compliance_assessment_accepts_aircraft_only():
    req = ComplianceAssessmentCreateRequest(
        aircraft_id=uuid.uuid4(),
        requirement_id=uuid.uuid4(),
        status="COMPLIANT",
        evaluated_at=date.today(),
    )
    assert req.aircraft_id is not None
    assert req.asset_id is None


def test_compliance_assessment_accepts_asset_only():
    asset_id = uuid.uuid4()
    req = ComplianceAssessmentCreateRequest(
        asset_id=asset_id,
        requirement_id=uuid.uuid4(),
        status="COMPLIANT",
        evaluated_at=date.today(),
    )
    assert req.asset_id == asset_id
    assert req.aircraft_id is None


def test_compliance_assessment_rejects_empty_subject():
    with pytest.raises(ValidationError, match="At least one of aircraft_id or asset_id"):
        ComplianceAssessmentCreateRequest(
            requirement_id=uuid.uuid4(),
            status="COMPLIANT",
            evaluated_at=date.today(),
        )


def test_mission_create_schema():
    asset_id = uuid.uuid4()
    pilot_id = uuid.uuid4()
    req = MissionCreateRequest(
        asset_id=asset_id,
        pilot_user_id=pilot_id,
        purpose="Perimeter LiDAR mapping run",
        operating_area="Facility Sector 4",
    )
    assert req.asset_id == asset_id
    assert req.pilot_user_id == pilot_id
    assert req.purpose == "Perimeter LiDAR mapping run"


def test_mission_status_enum():
    assert MissionStatus.PLANNED == "PLANNED"
    assert MissionStatus.AUTHORIZED == "AUTHORIZED"
    assert MissionStatus.IN_PROGRESS == "IN_PROGRESS"
    assert MissionStatus.COMPLETED == "COMPLETED"
    assert MissionStatus.CANCELLED == "CANCELLED"


def test_mission_authorize_schema():
    req = MissionAuthorizeRequest(notes="Internal flight clear by Operations Lead")
    assert req.notes == "Internal flight clear by Operations Lead"


# ---------------------------------------------------------------------------
# Compliance Service Unit Tests
# ---------------------------------------------------------------------------

def test_create_assessment_for_aircraft_works():
    db = MagicMock()
    org_id = uuid.uuid4()
    aircraft_id = uuid.uuid4()
    resolved_asset_id = uuid.uuid4()
    req_id = uuid.uuid4()

    mock_aircraft = MagicMock(id=aircraft_id, asset_id=resolved_asset_id)

    with (
        patch("app.services.compliance_service.aircraft_service.get_aircraft", return_value=mock_aircraft),
        patch("app.services.compliance_service.resolve_asset_id", return_value=resolved_asset_id),
        patch("app.services.compliance_service.get_requirement", return_value=MagicMock()),
        patch("app.services.compliance_service.record_audit_event"),
    ):
        payload = ComplianceAssessmentCreateRequest(
            aircraft_id=aircraft_id,
            requirement_id=req_id,
            status=ComplianceAssessmentStatus.COMPLIANT,
            evaluated_at=date.today(),
        )
        asmt = compliance_service.create_assessment(
            db, organization_id=org_id, actor_user_id=None, payload=payload
        )
        assert asmt.aircraft_id == aircraft_id
        assert asmt.asset_id == resolved_asset_id
        assert asmt.status == ComplianceAssessmentStatus.COMPLIANT


def test_create_assessment_for_drone_asset_works():
    db = MagicMock()
    org_id = uuid.uuid4()
    drone_asset_id = uuid.uuid4()
    req_id = uuid.uuid4()

    mock_asset = MagicMock(id=drone_asset_id, asset_type=AssetType.DRONE)

    with (
        patch("app.services.compliance_service.asset_service.get_asset", return_value=mock_asset),
        patch("app.services.compliance_service.get_requirement", return_value=MagicMock()),
        patch("app.services.compliance_service.record_audit_event"),
    ):
        payload = ComplianceAssessmentCreateRequest(
            asset_id=drone_asset_id,
            requirement_id=req_id,
            status=ComplianceAssessmentStatus.COMPLIANT,
            evaluated_at=date.today(),
        )
        asmt = compliance_service.create_assessment(
            db, organization_id=org_id, actor_user_id=None, payload=payload
        )
        assert asmt.aircraft_id is None
        assert asmt.asset_id == drone_asset_id
        assert asmt.status == ComplianceAssessmentStatus.COMPLIANT


def test_create_assessment_cross_tenant_asset_rejected():
    db = MagicMock()
    org_id = uuid.uuid4()
    other_org_asset_id = uuid.uuid4()
    req_id = uuid.uuid4()

    with (
        patch(
            "app.services.compliance_service.asset_service.get_asset",
            side_effect=NotFoundError("Asset not found"),
        ),
    ):
        payload = ComplianceAssessmentCreateRequest(
            asset_id=other_org_asset_id,
            requirement_id=req_id,
            status=ComplianceAssessmentStatus.COMPLIANT,
            evaluated_at=date.today(),
        )
        with pytest.raises(NotFoundError, match="Asset not found"):
            compliance_service.create_assessment(
                db, organization_id=org_id, actor_user_id=None, payload=payload
            )


# ---------------------------------------------------------------------------
# Mission Service Unit Tests
# ---------------------------------------------------------------------------

def test_create_mission_lifecycle_initial_status_planned():
    db = MagicMock()
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_asset = MagicMock(id=asset_id, organization_id=org_id)
    mock_pilot = MagicMock(id=user_id, organization_id=org_id)

    db.execute.return_value.scalar_one_or_none.return_value = mock_pilot

    with (
        patch("app.services.mission_service.asset_service.get_asset", return_value=mock_asset),
        patch("app.services.mission_service.record_audit_event"),
    ):
        payload = MissionCreateRequest(
            asset_id=asset_id,
            pilot_user_id=user_id,
            purpose="Grid Line Scan",
            operating_area="Corridor 3",
        )
        mission = mission_service.create_mission(
            db, organization_id=org_id, actor_user_id=user_id, payload=payload
        )
        assert mission.status == MissionStatus.PLANNED
        assert mission.purpose == "Grid Line Scan"
        assert mission.organization_id == org_id
        assert mission.asset_id == asset_id
        assert mission.pilot_user_id == user_id


def test_create_mission_cross_tenant_asset_rejected():
    db = MagicMock()
    org_id = uuid.uuid4()
    other_asset_id = uuid.uuid4()

    with patch(
        "app.services.mission_service.asset_service.get_asset",
        side_effect=NotFoundError("Asset not found"),
    ):
        payload = MissionCreateRequest(asset_id=other_asset_id, purpose="Test")
        with pytest.raises(NotFoundError, match="Asset not found"):
            mission_service.create_mission(
                db, organization_id=org_id, actor_user_id=None, payload=payload
            )


def test_create_mission_cross_tenant_pilot_rejected():
    db = MagicMock()
    org_id = uuid.uuid4()
    asset_id = uuid.uuid4()
    cross_tenant_pilot_id = uuid.uuid4()

    # Pilot query returns None (not found in org)
    db.execute.return_value.scalar_one_or_none.return_value = None

    with patch("app.services.mission_service.asset_service.get_asset", return_value=MagicMock()):
        payload = MissionCreateRequest(
            asset_id=asset_id,
            pilot_user_id=cross_tenant_pilot_id,
            purpose="Test",
        )
        with pytest.raises(NotFoundError, match="Pilot user not found in organization"):
            mission_service.create_mission(
                db, organization_id=org_id, actor_user_id=None, payload=payload
            )


def test_get_mission_and_update_mission():
    db = MagicMock()
    org_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    existing_mission = Mission(
        id=mission_id,
        organization_id=org_id,
        asset_id=uuid.uuid4(),
        status=MissionStatus.PLANNED,
        purpose="Initial purpose",
    )

    db.execute.return_value.scalar_one_or_none.return_value = existing_mission

    # 1. get_mission
    retrieved = mission_service.get_mission(db, organization_id=org_id, mission_id=mission_id)
    assert retrieved.id == mission_id

    # 2. update_mission
    with patch("app.services.mission_service.record_audit_event"):
        updated = mission_service.update_mission(
            db,
            organization_id=org_id,
            actor_user_id=None,
            mission_id=mission_id,
            payload=MissionUpdateRequest(purpose="Updated purpose", operating_area="New Zone"),
        )
        assert updated.purpose == "Updated purpose"
        assert updated.operating_area == "New Zone"


def test_authorize_mission_operational_authorization():
    db = MagicMock()
    org_id = uuid.uuid4()
    mission_id = uuid.uuid4()
    approver_id = uuid.uuid4()

    mission = Mission(
        id=mission_id,
        organization_id=org_id,
        asset_id=uuid.uuid4(),
        status=MissionStatus.PLANNED,
        purpose="Survey Flight",
    )
    db.execute.return_value.scalar_one_or_none.return_value = mission

    with patch("app.services.mission_service.record_audit_event"):
        authorized = mission_service.authorize_mission(
            db,
            organization_id=org_id,
            actor_user_id=approver_id,
            mission_id=mission_id,
            payload=MissionAuthorizeRequest(notes="Internal flight clear by Operations Lead"),
        )
        assert authorized.status == MissionStatus.AUTHORIZED
        assert authorized.authorized_at is not None
        assert authorized.authorized_by_user_id == approver_id
        assert "Internal flight clear by Operations Lead" in (authorized.notes or "")


def test_authorize_mission_cannot_authorize_cancelled_or_completed():
    db = MagicMock()
    org_id = uuid.uuid4()
    mission_id = uuid.uuid4()

    cancelled_mission = Mission(
        id=mission_id,
        organization_id=org_id,
        asset_id=uuid.uuid4(),
        status=MissionStatus.CANCELLED,
        purpose="Survey Flight",
    )
    db.execute.return_value.scalar_one_or_none.return_value = cancelled_mission

    with pytest.raises(AeroComplyError, match="Cannot authorize a mission in CANCELLED status"):
        mission_service.authorize_mission(
            db, organization_id=org_id, actor_user_id=None, mission_id=mission_id
        )


# ---------------------------------------------------------------------------
# Work Order Filter & Tenant Isolation Unit Tests
# ---------------------------------------------------------------------------

def test_list_work_orders_filters_by_asset_id_and_preserves_tenant():
    db = MagicMock()
    org_id = uuid.uuid4()
    drone_asset_id = uuid.uuid4()

    mock_wo = WorkOrder(
        id=uuid.uuid4(),
        organization_id=org_id,
        asset_id=drone_asset_id,
        work_order_number="WO-DRN-001",
        status="OPEN",
        priority="MEDIUM",
    )

    db.execute.return_value.scalars.return_value.all.return_value = [mock_wo]

    results = work_order_service.list_work_orders(
        db, organization_id=org_id, asset_id=drone_asset_id
    )
    assert len(results) == 1
    assert results[0].asset_id == drone_asset_id
    assert results[0].organization_id == org_id

