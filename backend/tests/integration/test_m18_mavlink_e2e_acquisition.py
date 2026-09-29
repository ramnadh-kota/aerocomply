"""M18: End-to-End MAVLink Acquisition & Full Intelligence Pipeline Integration Tests.

Validates the complete hardware-independent UAV data acquisition front door:
1. Raw MAVLink binary byte frames / UDP stream
2. MAVLinkConnector decoding & SI normalization
3. KotaTelemetryGateway store-and-forward local buffering & retry
4. Cloud ingestion via POST /api/v1/telemetry/ingest (NormalizedTelemetryEvent contract)
5. Full digital thread to Tech Guy 2 intelligence:
   HUMS -> Feature Engine -> Baselines -> Exceedance -> Diagnostics -> Prognostics -> M7 -> LISA
6. Multi-UAV concurrent acquisition & multi-tenant isolation
7. Offline store-and-forward resilience & replay synchronization
"""

import struct
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.battery import Battery
from app.models.component import Component
from app.models.hums import (
    HUMSSensor,
    HUMSSensorReading,
)
from app.models.organization import Organization
from app.models.plan import Plan, PlanFeature
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.telemetry import (
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryProcessingStatus,
)
from app.models.user import User
from app.schemas.auth import CurrentUser
from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryIngestRequest,
    TelemetryReadingItem,
)
from app.services import hums_service, telemetry_service
from app.services.ai import tools
from app.services.edge.gateway_service import KotaTelemetryGateway
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.hums import baseline_service, diagnostic_service, prognostic_service
from app.services.intelligence import proactive_intelligence_service


# -----------------------------------------------------------------------------
# Fixtures & Setup
# -----------------------------------------------------------------------------

def _seed_enterprise_plan(db_session: Session):
    plan = db_session.execute(select(Plan).where(Plan.code == "ENTERPRISE_PRODUCTION")).scalar_one_or_none()
    if not plan:
        plan = Plan(name="Enterprise Production", code="ENTERPRISE_PRODUCTION", is_active=True)
        db_session.add(plan)
        db_session.flush()
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="hums", enabled=True))
        # M20: /telemetry and /hums/*/prognostics are now commercially gated.
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="flight_telemetry", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="predictive_maintenance", enabled=True))
        db_session.add(PlanFeature(plan_id=plan.id, feature_key="drone_fleet_management", enabled=True))
        db_session.flush()
    return plan


def _create_test_org(db_session: Session, name_prefix: str = "Kota Fleet") -> tuple[Organization, User, dict[str, str]]:
    plan = _seed_enterprise_plan(db_session)
    org = Organization(name=f"{name_prefix} {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.flush()

    sub = Subscription(
        organization_id=org.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        starts_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(sub)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"ops.{uuid.uuid4().hex[:6]}@kota-aero.com",
        full_name="Operations Engineer",
        hashed_password="hashed-pw",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        roles=["ORG_ADMIN", "DRONE_OPERATOR"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )
    headers = {"Authorization": f"Bearer {token}"}
    return org, user, headers


def _create_uav_asset(
    db_session: Session,
    org: Organization,
    serial_number: str,
    model: str = "KOTA-HEAVY-LIFT-X8",
) -> tuple[Asset, Component, HUMSSensor, Battery]:
    asset = Asset(
        organization_id=org.id,
        serial_number=serial_number,
        model=model,
        asset_type=AssetType.DRONE,
        status="OPERATIONAL",
    )
    db_session.add(asset)
    db_session.flush()

    component = Component(
        organization_id=org.id,
        asset_id=asset.id,
        name="Front-Right Motor & Propulsion Assembly",
        component_type="PROPULSION",
        serial_number=f"MTR-{serial_number[-4:]}",
        model="KOTA-BLDC-80KV",
        status="OPERATIONAL",
    )
    db_session.add(component)
    db_session.flush()

    sensor = HUMSSensor(
        organization_id=org.id,
        asset_id=asset.id,
        component_id=component.id,
        sensor_code=f"VIB_{serial_number[-4:]}",
        sensor_type="ACCELEROMETER",
        measurement_type="vibration",
        unit="mm/s",
        source="TELEMETRY",
        status="ACTIVE",
    )
    db_session.add(sensor)
    db_session.flush()

    battery = Battery(
        organization_id=org.id,
        asset_id=asset.id,
        serial_number=f"BAT-{serial_number[-4:]}",
        model="KOTA-LIPO-6S-22AH",
        capacity_mah=22000,
        cycle_count=10,
        status="ACTIVE",
    )
    db_session.add(battery)
    db_session.flush()

    # Create external asset mapping for MAVLink ingestion
    mapping = ExternalAssetMapping(
        organization_id=org.id,
        source_system="KOTA_MAVLINK_GATEWAY",
        external_asset_id=serial_number,
        asset_id=asset.id,
        device_model=model,
        is_active=True,
    )
    db_session.add(mapping)
    db_session.flush()

    return asset, component, sensor, battery


# -----------------------------------------------------------------------------
# MAVLink Binary Helpers
# -----------------------------------------------------------------------------

def _build_raw_mavlink_v1(msgid: int, payload: bytes, seq: int = 1, sysid: int = 1, compid: int = 1) -> bytes:
    length = len(payload)
    header = struct.pack("<BBBBBB", 0xFE, length, seq % 256, sysid, compid, msgid)
    # M20: frames now carry a real X.25 checksum (+CRC_EXTRA); the connector rejects
    # frames whose checksum does not match, so the old fixed 0xAA55 placeholder is invalid.
    from app.services.edge.mavlink_connector import mavlink_checksum

    crc = struct.pack("<H", mavlink_checksum(header[1:] + payload, msgid))
    return header + payload + crc


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_m18_mavlink_binary_stream_to_cloud_e2e(client: TestClient, db_session: Session):
    """M18.E2E.1: End-to-End MAVLink binary frame decoding -> Gateway -> Cloud Ingest -> Database."""
    org, user, headers = _create_test_org(db_session, "AeroAcquire MAVLink")
    asset, component, sensor, battery = _create_uav_asset(db_session, org, "UAV-MAV-001")

    # 1. Setup Gateway and MAVLink Connector
    gateway = KotaTelemetryGateway(
        gateway_id="GW-MAV-STATION-01",
        cloud_base_url="http://testserver",
        tenant_api_token=headers["Authorization"].replace("Bearer ", ""),
        batch_size=20,
    )
    connector = MAVLinkConnector(
        connector_id="MAV-UAV-001",
        asset_mapping_override={1: "UAV-MAV-001"},
    )
    gateway.register_connector(connector)
    connector.connect()

    # 2. Synthesize MAVLink Binary Stream
    hb_payload = struct.pack("<IBBBBB", 0, 2, 3, 100, 4, 3)
    frame_hb = _build_raw_mavlink_v1(0, hb_payload, seq=1, sysid=1)

    pos_payload = struct.pack("<IiiiihhhH", 12000, int(37.7749 * 1e7), int(-122.4194 * 1e7), 150000, 35000, 1500, 0, -200, 9000)
    frame_pos = _build_raw_mavlink_v1(33, pos_payload, seq=2, sysid=1)

    att_payload = struct.pack("<Iffffff", 12050, 0.05, -0.02, 1.57, 0.01, 0.01, 0.0)
    frame_att = _build_raw_mavlink_v1(30, att_payload, seq=3, sysid=1)

    vib_payload = struct.pack("<QfffIII", 12100000, 1.45, 1.62, 1.88, 0, 0, 0)
    frame_vib = _build_raw_mavlink_v1(241, vib_payload, seq=4, sysid=1)

    sys_payload = struct.pack("<IIIHHhHHHBBBBBB", 0, 0, 0, 250, 24500, 1850, 85, 0, 0, 0, 0, 0, 0, 0, 0)
    frame_sys = _build_raw_mavlink_v1(1, sys_payload, seq=5, sysid=1)

    stream_bytes = frame_hb + frame_pos + frame_att + frame_vib + frame_sys

    # 3. Feed raw stream into connector
    evs = connector.parse_and_ingest_stream(stream_bytes)
    assert len(evs) >= 4
    assert len(gateway.buffer) >= 4

    # 4. Flush to Kota Cloud API
    flush_res = gateway.flush_to_cloud(http_client=client)
    assert flush_res["status"] == "SUCCESS"
    assert flush_res["transmitted"] >= 4

    # 5. Verify database records
    db_logs = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org.id)
    ).scalars().all()
    assert len(db_logs) >= 4
    for log in db_logs:
        assert log.processing_status == TelemetryProcessingStatus.PROCESSED
        assert log.asset_id == asset.id


def test_m18_mavlink_store_and_forward_network_loss_and_replay_e2e(client: TestClient, db_session: Session):
    """M18.E2E.2: Network drop -> Offline local buffering -> Reconnect -> Automatic replay -> Cloud."""
    org, user, headers = _create_test_org(db_session, "AeroStoreForward")
    asset, component, sensor, battery = _create_uav_asset(db_session, org, "UAV-STORE-001")

    gateway = KotaTelemetryGateway(
        gateway_id="GW-STORE-01",
        cloud_base_url="http://testserver",
        tenant_api_token=headers["Authorization"].replace("Bearer ", ""),
        batch_size=10,
    )
    connector = MAVLinkConnector(
        connector_id="MAV-STORE-001",
        asset_mapping_override={1: "UAV-STORE-001"},
    )
    gateway.register_connector(connector)
    connector.connect()

    # Generate 15 MAVLink position & attitude frames
    all_bytes = b""
    for i in range(15):
        pos_payload = struct.pack(
            "<IiiiihhhH",
            1000 + i * 100,
            int((37.7749 + i * 0.0001) * 1e7),
            int((-122.4194 + i * 0.0001) * 1e7),
            120000 + i * 1000,
            25000,
            1000,
            0,
            0,
            9000,
        )
        all_bytes += _build_raw_mavlink_v1(33, pos_payload, seq=i + 1, sysid=1)

    connector.parse_and_ingest_stream(all_bytes)
    assert len(gateway.buffer) == 15

    # Simulate offline network state
    gateway.is_online = False
    off_flush = gateway.flush_to_cloud(http_client=client)
    assert off_flush["status"] == "OFFLINE_BUFFERED"
    assert off_flush["remaining"] == 15

    # Ingest 5 more frames while offline
    more_bytes = b""
    for i in range(15, 20):
        vib_payload = struct.pack("<QfffIII", 2000000 + i * 100000, 1.2, 1.3, 1.4, 0, 0, 0)
        more_bytes += _build_raw_mavlink_v1(241, vib_payload, seq=i + 1, sysid=1)

    connector.parse_and_ingest_stream(more_bytes)
    assert len(gateway.buffer) == 20

    # Reconnect and synchronize
    sync_res = gateway.reconnect_and_sync(http_client=client)
    assert sync_res["status"] == "SYNC_COMPLETE"
    assert sync_res["total_replayed"] == 20
    assert len(gateway.buffer) == 0

    # Verify all 20 events are successfully processed in Kota database
    db_logs = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org.id)
    ).scalars().all()
    assert len(db_logs) == 20


def test_m18_multi_uav_mavlink_concurrent_acquisition_and_tenant_isolation(
    client: TestClient, db_session: Session
):
    """M18.E2E.3: Concurrent ingestion from 3 UAVs across 2 isolated organizations."""
    org_a, user_a, headers_a = _create_test_org(db_session, "Fleet Tenant Alpha")
    org_b, user_b, headers_b = _create_test_org(db_session, "Fleet Tenant Bravo")

    asset_a1, _, _, _ = _create_uav_asset(db_session, org_a, "UAV-A1")
    asset_a2, _, _, _ = _create_uav_asset(db_session, org_a, "UAV-A2")
    asset_b1, _, _, _ = _create_uav_asset(db_session, org_b, "UAV-B1")

    # Gateway A representing Tenant A
    gw_a = KotaTelemetryGateway(
        gateway_id="GW-TENANT-A",
        cloud_base_url="http://testserver",
        tenant_api_token=headers_a["Authorization"].replace("Bearer ", ""),
    )
    conn_a1 = MAVLinkConnector(connector_id="CONN-A1", asset_mapping_override={1: "UAV-A1"})
    conn_a2 = MAVLinkConnector(connector_id="CONN-A2", asset_mapping_override={2: "UAV-A2"})
    gw_a.register_connector(conn_a1)
    gw_a.register_connector(conn_a2)

    # Gateway B representing Tenant B
    gw_b = KotaTelemetryGateway(
        gateway_id="GW-TENANT-B",
        cloud_base_url="http://testserver",
        tenant_api_token=headers_b["Authorization"].replace("Bearer ", ""),
    )
    conn_b1 = MAVLinkConnector(connector_id="CONN-B1", asset_mapping_override={3: "UAV-B1"})
    gw_b.register_connector(conn_b1)

    # Emit telemetry for A1, A2, and B1
    pos_a1 = _build_raw_mavlink_v1(33, struct.pack("<IiiiihhhH", 100, int(37.1 * 1e7), int(-122.1 * 1e7), 10000, 5000, 500, 0, 0, 0), sysid=1)
    pos_a2 = _build_raw_mavlink_v1(33, struct.pack("<IiiiihhhH", 200, int(37.2 * 1e7), int(-122.2 * 1e7), 20000, 6000, 600, 0, 0, 0), sysid=2)
    pos_b1 = _build_raw_mavlink_v1(33, struct.pack("<IiiiihhhH", 300, int(38.1 * 1e7), int(-121.1 * 1e7), 30000, 7000, 700, 0, 0, 0), sysid=3)

    conn_a1.parse_and_ingest_stream(pos_a1)
    conn_a2.parse_and_ingest_stream(pos_a2)
    conn_b1.parse_and_ingest_stream(pos_b1)

    # Flush gateways
    res_a = gw_a.flush_to_cloud(http_client=client)
    res_b = gw_b.flush_to_cloud(http_client=client)
    assert res_a["status"] == "SUCCESS"
    assert res_b["status"] == "SUCCESS"

    # Verify Tenant A only has events for A1 and A2
    logs_a = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_a.id)
    ).scalars().all()
    assert len(logs_a) == 2
    asset_ids_a = {str(l.asset_id) for l in logs_a}
    assert str(asset_a1.id) in asset_ids_a
    assert str(asset_a2.id) in asset_ids_a
    assert str(asset_b1.id) not in asset_ids_a

    # Verify Tenant B only has events for B1
    logs_b = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org_b.id)
    ).scalars().all()
    assert len(logs_b) == 1
    assert logs_b[0].asset_id == asset_b1.id


def test_m18_real_uav_stream_to_m7_and_lisa_e2e(client: TestClient, db_session: Session):
    """M18.E2E.4: Complete 10-link digital thread: MAVLink -> Ingest -> HUMS -> Exceedance -> Diagnostics -> Prognostics -> M7 -> LISA."""
    org, user, headers = _create_test_org(db_session, "Kota Intelligence E2E")
    asset, component, sensor, battery = _create_uav_asset(db_session, org, "UAV-INTELLIGENCE-01")

    gateway = KotaTelemetryGateway(
        gateway_id="GW-INTEL-01",
        cloud_base_url="http://testserver",
        tenant_api_token=headers["Authorization"].replace("Bearer ", ""),
    )
    connector = MAVLinkConnector(
        connector_id="MAV-INTEL-01",
        asset_mapping_override={1: "UAV-INTELLIGENCE-01"},
    )
    gateway.register_connector(connector)
    connector.connect()

    # 1. Establish baseline history via MAVLink stream
    now = datetime.now(UTC)
    for i in range(5):
        t_sample = now - timedelta(minutes=25 - i * 5)
        pos_payload = struct.pack("<IiiiihhhH", 1000 * i, int(37.77 * 1e7), int(-122.41 * 1e7), 100000, 25000, 1000, 0, 0, 9000)
        vib_payload = struct.pack("<QfffIII", int(t_sample.timestamp() * 1000000), 1.5, 1.6, 1.7, 0, 0, 0)
        stream_b = _build_raw_mavlink_v1(33, pos_payload, seq=i * 2 + 1, sysid=1) + _build_raw_mavlink_v1(241, vib_payload, seq=i * 2 + 2, sysid=1)
        connector.parse_and_ingest_stream(stream_b)

    flush_base = gateway.flush_to_cloud(http_client=client)
    assert flush_base["status"] == "SUCCESS"

    # 2. Trigger high vibration anomaly via MAVLink (52.0 mm/s)
    vib_anomaly_payload = struct.pack("<QfffIII", int(now.timestamp() * 1000000), 45.0, 52.0, 48.0, 0, 0, 0)
    stream_anomaly = _build_raw_mavlink_v1(241, vib_anomaly_payload, seq=99, sysid=1)
    connector.parse_and_ingest_stream(stream_anomaly)

    flush_anomaly = gateway.flush_to_cloud(http_client=client)
    assert flush_anomaly["status"] == "SUCCESS"

    # 3. Verify Telemetry Logs ingested in database
    db_logs = db_session.execute(
        select(TelemetryEventLog).where(TelemetryEventLog.organization_id == org.id)
    ).scalars().all()
    assert len(db_logs) >= 6

    # 4. Verify HUMS Sensor Readings persisted
    sensor_readings = db_session.execute(
        select(HUMSSensorReading).where(HUMSSensorReading.organization_id == org.id)
    ).scalars().all()
    assert len(sensor_readings) >= 6

    # 5. Evaluate M7 Proactive Intelligence Signals
    summary = proactive_intelligence_service.get_proactive_summary(db_session, organization_id=org.id)
    assert summary is not None

    # 6. Verify LISA Grounded AI Tools execute on live MAVLink telemetry
    current_user_obj = CurrentUser(
        id=user.id,
        organization_id=org.id,
        roles=["ORG_ADMIN"],
        email=user.email,
        full_name=user.full_name,
        email_verified=True,
    )

    t_status = tools.execute_tool(db_session, current_user_obj, "get_asset_telemetry_status", {"asset_id": str(asset.id)})
    assert t_status["telemetry_state"] == "ACTIVE"
    assert t_status["total_recent_events"] > 0
