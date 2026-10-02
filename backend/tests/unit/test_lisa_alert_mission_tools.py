from unittest.mock import MagicMock
import uuid
import pytest
from app.schemas.auth import CurrentUser
from app.services.ai.tools import TOOL_REGISTRY_BY_NAME, _handle_get_alert_details, _handle_get_mission_details
from app.core.errors import AeroComplyError, NotFoundError

def test_alert_and_mission_tools_registered():
    assert "get_alert_details" in TOOL_REGISTRY_BY_NAME
    assert "get_mission_details" in TOOL_REGISTRY_BY_NAME

    alert_tool = TOOL_REGISTRY_BY_NAME["get_alert_details"]
    assert "alert_id" in alert_tool.input_schema["required"]

    mission_tool = TOOL_REGISTRY_BY_NAME["get_mission_details"]
    assert "mission_id" in mission_tool.input_schema["required"]


def test_get_alert_details_requires_alert_id():
    db = MagicMock()
    user = CurrentUser(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email="operator@kota.aero",
        full_name="Fleet Operator",
        roles=["fleet_manager"],
    )
    with pytest.raises(AeroComplyError):
        _handle_get_alert_details(db, user, {"alert_id": ""})


def test_get_alert_details_not_found(monkeypatch):
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    import app.services.ai.tools as tools_mod
    monkeypatch.setattr(tools_mod.proactive_service, "get_proactive_alerts", lambda *args, **kwargs: [])
    user = CurrentUser(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email="operator@kota.aero",
        full_name="Fleet Operator",
        roles=["fleet_manager"],
    )
    with pytest.raises(NotFoundError):
        _handle_get_alert_details(db, user, {"alert_id": str(uuid.uuid4())})


def test_get_mission_details_requires_valid_uuid():
    db = MagicMock()
    user = CurrentUser(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email="operator@kota.aero",
        full_name="Fleet Operator",
        roles=["fleet_manager"],
    )
    with pytest.raises(AeroComplyError):
        _handle_get_mission_details(db, user, {"mission_id": "not-a-valid-uuid"})
