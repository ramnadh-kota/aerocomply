"""Tests for the Lisa tool registry (app/services/ai/tools.py): RBAC
enforcement per tool and tenant isolation of the data tools return.
"""
import uuid

import pytest

from app.core.errors import ForbiddenError, NotFoundError
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.auth import CurrentUser
from app.services import aircraft_service
from app.services.ai.tools import execute_tool


def _user(org_id: uuid.UUID, roles: list[str]) -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        organization_id=org_id,
        email="lisa-tool-test@example.com",
        full_name="Tool Test User",
        roles=roles,
    )


def test_unknown_tool_raises(db_session):
    org_id = uuid.uuid4()
    user = _user(org_id, ["ORG_ADMIN"])
    with pytest.raises(Exception) as exc_info:
        execute_tool(db_session, user, "not_a_real_tool", {})
    assert "unknown_tool" in str(exc_info.value) or "Unknown tool" in str(exc_info.value)


def test_viewer_role_can_read_aircraft(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N1AI", msn="MSN-AI-1", aircraft_type="A320"),
    )
    user = _user(org_id, ["VIEWER"])

    result = execute_tool(db_session, user, "get_aircraft", {"aircraft_id": str(aircraft.id)})
    assert result["registration"] == "N1AI"


def test_role_without_permission_is_forbidden(db_session):
    org_id = uuid.uuid4()
    # A role with no grants at all — permissions_for_roles([]) returns an
    # empty set, so every tool must refuse it.
    user = _user(org_id, [])

    with pytest.raises(ForbiddenError):
        execute_tool(db_session, user, "list_aircraft", {})


def test_tool_cannot_see_other_tenant_aircraft(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="N2AI", msn="MSN-AI-2", aircraft_type="A320"),
    )
    user_b = _user(org_b, ["ORG_ADMIN"])

    with pytest.raises(NotFoundError):
        execute_tool(db_session, user_b, "get_aircraft", {"aircraft_id": str(aircraft.id)})


def test_tool_list_scoped_to_tenant(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="N3AI", msn="MSN-AI-3", aircraft_type="A320"),
    )
    user_b = _user(org_b, ["ORG_ADMIN"])

    result = execute_tool(db_session, user_b, "list_aircraft", {})
    assert result["aircraft"] == []


def test_get_control_center_summary_tool(db_session):
    org_id = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N4AI", msn="MSN-AI-4", aircraft_type="A320"),
    )
    user = _user(org_id, ["ORG_ADMIN"])

    result = execute_tool(db_session, user, "get_control_center_summary", {})
    assert result["total_aircraft"] == 1
    assert result["operational"] == 1


def test_get_regulatory_provider_status_tool_always_not_configured(db_session):
    org_id = uuid.uuid4()
    user = _user(org_id, ["ORG_ADMIN"])

    result = execute_tool(db_session, user, "get_regulatory_provider_status", {})
    assert len(result["providers"]) == 5
    assert all(p["status"] == "NOT_CONFIGURED" for p in result["providers"])


def test_maintenance_engineer_cannot_read_compliance_assessments(db_session):
    # MAINTENANCE_ENGINEER holds PART_READ/VENDOR_READ/PROCUREMENT_READ but
    # NOT COMPLIANCE_ASSESS (see app/core/permissions.py) — confirm the
    # tool layer draws this line for real, not just the REST layer.
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N5AI", msn="MSN-AI-5", aircraft_type="A320"),
    )
    user = _user(org_id, ["MAINTENANCE_ENGINEER"])

    with pytest.raises(ForbiddenError):
        execute_tool(
            db_session,
            user,
            "get_compliance_assessments",
            {"aircraft_id": str(aircraft.id)},
        )


def test_compliance_manager_can_read_compliance_assessments(db_session):
    org_id = uuid.uuid4()
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N6AI", msn="MSN-AI-6", aircraft_type="A320"),
    )
    user = _user(org_id, ["COMPLIANCE_MANAGER"])

    result = execute_tool(
        db_session, user, "get_compliance_assessments", {"aircraft_id": str(aircraft.id)}
    )
    assert result["assessments"] == []


def test_no_mutation_tools_exist_in_registry(db_session):
    # Every tool in the Lisa registry is READ-only today (see
    # app/services/ai/tools.py module docstring and the M4 "Lisa Actions"
    # boundary — Lisa may recommend/prepare but must never silently
    # execute a safety-critical mutation). Assert this structurally so a
    # future write-capable tool addition can't slip past this boundary
    # without a deliberate, reviewed change to this test.
    from app.services.ai.tools import TOOL_REGISTRY

    write_verbs = ("create", "update", "approve", "reject", "cancel", "close", "receive", "mark_")
    offending = [t.name for t in TOOL_REGISTRY if any(v in t.name for v in write_verbs)]
    assert offending == [], f"Found apparent mutation tools in read-only Lisa registry: {offending}"
