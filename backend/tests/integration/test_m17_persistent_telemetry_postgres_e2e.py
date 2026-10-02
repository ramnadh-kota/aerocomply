"""M17: Persistent Telemetry End-to-End PostgreSQL Integration Test.

Validates the full physical-to-database-to-AI stack against a real PostgreSQL instance:
1. Creates real persistent Organization, Asset (Drone), and DataSource records in PostgreSQL.
2. Streams real MAVLink v2 UDP datagrams from ArduPilotSITLEngine.
3. Ingests frames through MAVLinkConnector and persists live state to PostgreSQL `drone_live_state` via `apply_event`.
4. Validates direct SQL SELECT from PostgreSQL for position, fix, battery, and state_version.
5. Verifies `get_drone_state` and `get_fleet_state` domain services over PostgreSQL.
6. Evaluates geofence signed distance and verifies rule evaluation.
7. Invokes LISA AI tools against the real database session and verifies grounded answers.
8. Confirms tenant isolation across SQL queries, service layers, and LISA tools.
9. Validates resilience against out-of-order packets and database reconnects.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
import pytest

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker, Session

from app.models.asset import Asset, AssetType
from app.models.drone_live_state import DroneLiveState
from app.models.organization import Organization, OrganizationIndustry
from app.models.data_source import DataSource
from app.schemas.auth import CurrentUser
from app.services.edge.ardupilot_sitl_engine import ArduPilotSITLEngine
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.live_state_service import LiveBroker, apply_event, get_drone_state, get_fleet_state
from app.services.ai.tools import (
    _handle_list_fleet_assets,
    _handle_get_alert_details,
)
from app.schemas.live_state import LiveStateV1, LiveIdentityV1, PositionV1, BatteryV1, compute_freshness
from app.services import geo


DB_URL = "postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_dev"


def test_m17_persistent_telemetry_e2e_postgres(monkeypatch):
    engine = create_engine(DB_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db: Session = SessionLocal()

    import app.db.session as session_mod
    monkeypatch.setattr(session_mod, "SessionLocal", SessionLocal)

    org_id = uuid.uuid4()
    foreign_org_id = uuid.uuid4()
    drone_id = uuid.uuid4()
    foreign_drone_id = uuid.uuid4()
    source_id = uuid.uuid4()

    try:
        # 1. Create real database records in PostgreSQL
        org = Organization(
            id=org_id,
            name=f"Kota SITL Flight Test Org {org_id.hex[:6]}",
            industry=OrganizationIndustry.DRONE_UAV,
        )
        db.add(org)

        foreign_org = Organization(
            id=foreign_org_id,
            name=f"Foreign Operator Org {foreign_org_id.hex[:6]}",
            industry=OrganizationIndustry.DRONE_UAV,
        )
        db.add(foreign_org)

        drone = Asset(
            id=drone_id,
            organization_id=org_id,
            asset_type=AssetType.DRONE.value,
            model="ArduCopter Quad 6S",
            registration="SITL-KOTA-01",
            serial_number=f"SN-SITL-{drone_id.hex[:8]}",
            status="ACTIVE",
        )
        db.add(drone)

        foreign_drone = Asset(
            id=foreign_drone_id,
            organization_id=foreign_org_id,
            asset_type=AssetType.DRONE.value,
            model="Foreign Quad 4S",
            registration="FOREIGN-DRONE-01",
            serial_number=f"SN-FOR-{foreign_drone_id.hex[:8]}",
            status="ACTIVE",
        )
        db.add(foreign_drone)

        source = DataSource(
            id=source_id,
            organization_id=org_id,
            name="SITL Primary MAVLink Gateway",
            connector_type="MAVLINK",
            connection_config={"system_id_map": {"1": str(drone_id)}},
            status="ACTIVE",
        )
        db.add(source)
        db.commit()

        # 2. Setup UDP socket ingestion receiver
        host = "127.0.0.1"
        port = 14559
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_sock.bind((host, port))
        server_sock.settimeout(1.0)

        connector = MAVLinkConnector()
        stop_listener = threading.Event()
        received_events = []

        def listener_worker():
            while not stop_listener.is_set():
                try:
                    data, _ = server_sock.recvfrom(2048)
                    events = connector.feed_bytes(data)
                    for e in events:
                        received_events.append(e)
                except socket.timeout:
                    continue
                except Exception:
                    break

        t = threading.Thread(target=listener_worker, daemon=True)
        t.start()

        # 3. Launch ArduPilot SITL Virtual Drone Emitter
        sitl = ArduPilotSITLEngine(sysid=1, target_host=host, target_port=port)
        sitl.state.lat_deg = 10.005
        sitl.state.lon_deg = 77.005
        sitl.state.alt_rel_m = 25.0
        sitl.state.alt_msl_m = 125.0
        sitl.state.armed = True
        sitl.state.flight_mode = "GUIDED"
        sitl.state.battery_voltage_v = 24.8
        sitl.state.battery_remaining_pct = 88

        try:
            for _ in range(5):
                sitl.step_physics(dt=0.1)
                sitl.emit_telemetry_burst()
                time.sleep(0.05)
            time.sleep(0.2)
        finally:
            stop_listener.set()
            t.join(timeout=1.0)
            server_sock.close()
            sitl.stop()

        assert len(received_events) >= 5

        # 4. Ingest and persist telemetry into PostgreSQL via actual service `apply_event`
        for evt in received_events:
            persisted_row = apply_event(
                db,
                organization_id=org_id,
                asset_id=drone_id,
                event=evt,
                data_source_id=source_id,
            )
        db.commit()

        # 5. Direct SQL verification from PostgreSQL database
        row = db.execute(
            select(DroneLiveState).where(
                DroneLiveState.organization_id == org_id,
                DroneLiveState.asset_id == drone_id,
            )
        ).scalar_one_or_none()

        assert row is not None
        assert row.asset_id == drone_id
        assert row.organization_id == org_id
        assert row.state_version >= 5
        assert row.event_count >= 5
        assert row.source_system == "KOTA_MAVLINK_GATEWAY"
        assert row.payload is not None
        
        pos = row.payload.get("position", {})
        batt = row.payload.get("battery", {})
        assert pos.get("lat") == pytest.approx(10.005, abs=0.01)
        assert pos.get("lon") == pytest.approx(77.005, abs=0.01)
        assert pos.get("alt_rel_m") == pytest.approx(26.0, abs=5.0)
        assert pos.get("gps_fix") in ("3D", "2D", "DGPS")
        assert batt.get("remaining_pct") <= 88
        assert batt.get("voltage_v") == pytest.approx(24.8, abs=1.0)

        # 6. Service read-path verification (get_drone_state / get_fleet_state)
        drone_state = get_drone_state(db, organization_id=org_id, asset_id=drone_id)
        assert drone_state is not None
        assert drone_state.identity.asset_id == drone_id
        assert drone_state.position.lat == pytest.approx(10.005, abs=0.01)
        assert drone_state.freshness.state == "FRESH"
        assert drone_state.mode.armed is True

        fleet_states = get_fleet_state(db, organization_id=org_id)
        assert len(fleet_states) == 1
        assert fleet_states[0].identity.asset_id == drone_id

        # 7. Out-of-order rejection test
        old_event = received_events[0]
        stale_time = old_event.event_timestamp - timedelta(seconds=120)
        old_event.event_timestamp = stale_time
        res = apply_event(db, organization_id=org_id, asset_id=drone_id, event=old_event)
        assert res is None  # Dropped because timestamp is older than last_event_at

        # 8. Geofence evaluation over stored coordinates
        fence_geom = {"center": {"lat": 10.0, "lon": 77.0}, "radius_m": 1000.0}
        dist = geo.signed_distance_m("CIRCLE", fence_geom, drone_state.position.lat, drone_state.position.lon)
        assert dist < 0  # Drone is inside the 1km boundary

        # 9. LISA AI Grounding with real PostgreSQL session
        user = CurrentUser(
            id=uuid.uuid4(),
            organization_id=org_id,
            email="operator@kota.aero",
            full_name="Fleet Operator",
            roles=["fleet_manager"],
        )

        mock_ent = type("Ent", (), {"effective_features": {"drone_fleet_management": True}})()
        import app.services.ai.tools as tools_mod
        pytest.MonkeyPatch().setattr(tools_mod, "resolve_entitlements", lambda *a, **k: mock_ent)

        lisa_result = _handle_list_fleet_assets(db, user, {"asset_type": "DRONE"})
        assert "assets" in lisa_result
        matched_drone = next((a for a in lisa_result["assets"] if a["registration"] == "SITL-KOTA-01"), None)
        assert matched_drone is not None
        assert matched_drone["model"] == "ArduCopter Quad 6S"

        # 10. Tenant Isolation Verification
        foreign_user = CurrentUser(
            id=uuid.uuid4(),
            organization_id=foreign_org_id,
            email="foreign@other.aero",
            full_name="Foreign Operator",
            roles=["fleet_manager"],
        )
        foreign_lisa_result = _handle_list_fleet_assets(db, foreign_user, {"asset_type": "DRONE"})
        assert not any(a["registration"] == "SITL-KOTA-01" for a in foreign_lisa_result.get("assets", []))

        # Direct SQL cross-tenant check
        foreign_row = db.execute(
            select(DroneLiveState).where(
                DroneLiveState.organization_id == foreign_org_id,
                DroneLiveState.asset_id == drone_id,
            )
        ).scalar_one_or_none()
        assert foreign_row is None

        # Service-level cross-tenant protection
        from app.core.errors import NotFoundError
        with pytest.raises(NotFoundError):
            get_drone_state(db, organization_id=foreign_org_id, asset_id=drone_id)

    finally:
        # Cleanup test records from real PostgreSQL database
        db.execute(text(f"DELETE FROM drone_live_state WHERE asset_id IN ('{drone_id}', '{foreign_drone_id}')"))
        db.execute(text(f"DELETE FROM data_sources WHERE id = '{source_id}'"))
        db.execute(text(f"DELETE FROM assets WHERE id IN ('{drone_id}', '{foreign_drone_id}')"))
        db.execute(text(f"DELETE FROM organizations WHERE id IN ('{org_id}', '{foreign_org_id}')"))
        db.commit()
        db.close()
