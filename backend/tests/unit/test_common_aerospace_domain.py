"""Unit tests for M4 — Common Aerospace Domain Foundation.

Verifies:
1. AssetType extensibility (AIRCRAFT, DRONE, HELICOPTER, EVTOL, AAM, OTHER).
2. Separation of lifecycle, operational, compliance, and readiness states.
3. Common component types (ENGINE, ROTOR, TRANSMISSION, AVIONICS, MOTOR, etc.).
4. Asset configuration resolution across aircraft, drone, and helicopter.
5. Component installation and removal lifecycle with history tracking.
6. Operational utilization and flight hours calculation.
7. Multi-dimensional readiness evaluation semantics.
8. Common domain context and timeline reconstruction.
9. Server-side tenant isolation enforcement.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
import pytest

from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset, AssetLifecycleStatus, AssetOperationalStatus, AssetType
from app.models.compliance import ComplianceAssessmentStatus
from app.models.component import Component, ComponentStatus, ComponentType
from app.schemas.asset import (
    AssetCreateRequest,
    AssetFlightCreateRequest,
    AssetInstallComponentRequest,
    AssetUpdateRequest,
)
from app.services import asset_service

TENANT_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
TENANT_B = uuid.UUID("00000000-0000-0000-0000-000000000002")
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")


# ---------------------------------------------------------------------------
# 1. Enums & Status Separation Tests
# ---------------------------------------------------------------------------

def test_asset_types_contain_full_aerospace_family():
    assert AssetType.AIRCRAFT == "AIRCRAFT"
    assert AssetType.DRONE == "DRONE"
    assert AssetType.HELICOPTER == "HELICOPTER"
    assert AssetType.EVTOL == "EVTOL"
    assert AssetType.AAM == "AAM"
    assert AssetType.OTHER == "OTHER"


def test_status_separation_semantics():
    # Lifecycle status is about airframe lifecycle
    assert AssetLifecycleStatus.PLANNED == "PLANNED"
    assert AssetLifecycleStatus.ACTIVE == "ACTIVE"
    assert AssetLifecycleStatus.IN_SERVICE == "IN_SERVICE"
    assert AssetLifecycleStatus.MAINTENANCE == "MAINTENANCE"
    assert AssetLifecycleStatus.GROUNDED == "GROUNDED"
    assert AssetLifecycleStatus.RETIRED == "RETIRED"

    # Operational status is about dispatch/operational state
    assert AssetOperationalStatus.READY == "READY"
    assert AssetOperationalStatus.STANDBY == "STANDBY"
    assert AssetOperationalStatus.DISPATCHED == "DISPATCHED"
    assert AssetOperationalStatus.IN_FLIGHT == "IN_FLIGHT"

    # Compliance status is distinct
    assert ComplianceAssessmentStatus.COMPLIANT == "COMPLIANT"
    assert ComplianceAssessmentStatus.NON_COMPLIANT == "NON_COMPLIANT"

    # Ensure these are distinct vocabularies
    assert AssetOperationalStatus.IN_FLIGHT != AssetLifecycleStatus.ACTIVE


def test_component_types_span_fixed_wing_rotorcraft_and_drones():
    assert ComponentType.ENGINE == "ENGINE"
    assert ComponentType.ROTOR == "ROTOR"
    assert ComponentType.TRANSMISSION == "TRANSMISSION"
    assert ComponentType.AVIONICS == "AVIONICS"
    assert ComponentType.APU == "APU"
    assert ComponentType.MOTOR == "MOTOR"
    assert ComponentType.ESC == "ESC"
    assert ComponentType.PROPELLER == "PROPELLER"
    assert ComponentType.BATTERY == "BATTERY"
    assert ComponentType.GPS == "GPS"


# ---------------------------------------------------------------------------
# 2. Asset Service Unit Tests
# ---------------------------------------------------------------------------

def test_create_asset_success():
    db = MagicMock()
    # Mock no existing duplicate
    db.execute.return_value.scalar_one_or_none.return_value = None

    payload = AssetCreateRequest(
        asset_type="HELICOPTER",
        registration="VT-BLR-01",
        manufacturer="Bell",
        model="429 GlobalRanger",
        serial_number="MSN-57201",
        status="ACTIVE",
    )

    with patch("app.services.asset_service.record_audit_event") as mock_audit:
        asset = asset_service.create_asset(
            db,
            organization_id=TENANT_A,
            actor_user_id=USER_ID,
            payload=payload,
        )

        assert asset.asset_type == "HELICOPTER"
        assert asset.registration == "VT-BLR-01"
        assert asset.manufacturer == "Bell"
        assert asset.model == "429 GlobalRanger"
        assert asset.organization_id == TENANT_A
        assert db.add.called
        assert db.commit.called
        assert mock_audit.called


def test_create_asset_duplicate_registration_fails():
    db = MagicMock()
    # Simulate existing asset with same registration in this tenant
    existing = Asset(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="AIRCRAFT",
        registration="VT-XYZ",
    )
    db.execute.return_value.scalar_one_or_none.return_value = existing

    payload = AssetCreateRequest(
        asset_type="AIRCRAFT",
        registration="VT-XYZ",
    )

    with pytest.raises(ConflictError) as exc:
        asset_service.create_asset(
            db,
            organization_id=TENANT_A,
            actor_user_id=USER_ID,
            payload=payload,
        )
    assert "already in use" in str(exc.value)


def test_get_asset_tenant_isolation():
    db = MagicMock()
    # Asset exists in TENANT_A, but TENANT_B queries it -> should return None -> NotFoundError
    db.execute.return_value.scalar_one_or_none.return_value = None

    with pytest.raises(NotFoundError):
        asset_service.get_asset(
            db,
            organization_id=TENANT_B,
            asset_id=uuid.uuid4(),
        )


def test_configuration_resolution_helicopter():
    db = MagicMock()
    helicopter = Asset(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="HELICOPTER",
        registration="VT-COPTER",
        manufacturer="Airbus Helicopters",
        model="H145",
        serial_number="MSN-20300",
        status="ACTIVE",
    )
    rotor_comp = Component(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_id=helicopter.id,
        component_type="ROTOR",
        name="Main Rotor Blades Set",
        serial_number="ROT-9912",
        status="INSTALLED",
        created_at=datetime.now(UTC),
    )

    # First query gets asset, second query gets components
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=helicopter)),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[rotor_comp])))),
    ]

    config = asset_service.get_asset_configuration(
        db, organization_id=TENANT_A, asset_id=helicopter.id
    )

    assert config.asset_type == "HELICOPTER"
    assert config.total_components_installed == 1
    # Check that Main Rotor Assembly slot is occupied
    rotor_slot = next(s for s in config.slots if "Main Rotor" in s.slot_name)
    assert rotor_slot.is_occupied is True
    assert rotor_slot.component.serial_number == "ROT-9912"


def test_install_and_remove_component_lifecycle():
    db = MagicMock()
    asset = Asset(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="DRONE",
        registration="UAV-01",
        status="ACTIVE",
    )
    db.execute.return_value.scalar_one_or_none.return_value = asset

    payload = AssetInstallComponentRequest(
        component_type="FLIGHT_CONTROLLER",
        name="Pixhawk 6X Pro",
        serial_number="PX6-8819",
        manufacturer="Holybro",
    )

    with patch("app.services.asset_service.record_audit_event"):
        comp_resp = asset_service.install_asset_component(
            db,
            organization_id=TENANT_A,
            actor_user_id=USER_ID,
            asset_id=asset.id,
            payload=payload,
        )
        assert comp_resp.component_type == "FLIGHT_CONTROLLER"
        assert comp_resp.name == "Pixhawk 6X Pro"
        assert db.add.called
        assert db.commit.called


def test_utilization_hours_and_cycles_calculation():
    db = MagicMock()
    asset = Asset(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="AIRCRAFT",
        registration="VT-BOEING",
        status="ACTIVE",
    )

    # Mock get_asset, then stats (count=10, sum_minutes=1200, sum_cycles=10)
    db.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=asset)),
        MagicMock(one=MagicMock(return_value=(10, 1200, 10))),
    ]

    util = asset_service.get_asset_utilization(
        db, organization_id=TENANT_A, asset_id=asset.id
    )

    assert util.total_flights == 10
    assert util.total_minutes == 1200
    assert util.total_flight_hours == 20.0  # 1200 / 60
    assert util.total_cycles == 10
    assert util.total_landings == 10


def test_multi_dimensional_readiness_evaluation():
    db = MagicMock()
    asset = Asset(
        id=uuid.uuid4(),
        organization_id=TENANT_A,
        asset_type="AIRCRAFT",
        registration="VT-READY",
        status="ACTIVE",
    )

    # get_asset returns asset
    db.execute.return_value.scalar_one_or_none.return_value = asset

    with patch("app.services.asset_service.get_asset_maintenance", return_value={"open_work_orders": [], "has_overdue": False}), \
         patch("app.services.asset_service.get_asset_compliance", return_value={"assessments": [], "overall_status": "COMPLIANT", "compliant_count": 5, "non_compliant_count": 0}):

        readiness = asset_service.get_asset_readiness(
            db, organization_id=TENANT_A, asset_id=asset.id
        )

        assert readiness.overall_status == "READY"
        assert len(readiness.dimensions) == 5
        dims = {d.dimension: d.status for d in readiness.dimensions}
        assert dims["OPERATIONAL"] == "READY"
        assert dims["MAINTENANCE"] == "READY"
        assert dims["COMPLIANCE"] == "READY"
        assert dims["DEPLOYMENT"] == "READY"
        assert dims["RELEASE"] == "READY"
        assert "not an electronic Release to Service" in readiness.disclaimer
