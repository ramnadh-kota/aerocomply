"""Continuous Live SITL Telemetry Emitter and Database Ingestion Service.

Streams realistic MAVLink v2 binary telemetry for drone APX-DRONE-01,
decodes packets via MAVLinkConnector, and continuously persists state to PostgreSQL.
"""
from __future__ import annotations

import argparse
import math
import os
import signal
import sys
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.asset import Asset
from app.models.data_source import DataSource
from app.models.drone_live_state import DroneLiveState
from app.models.organization import Organization
from app.services.edge.ardupilot_sitl_engine import ArduPilotSITLEngine
from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.live_state_service import apply_event

DEFAULT_DB_URL = "postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_dev"
APEX_ORG_ID = uuid.UUID("7d935cd8-9ac3-4159-be0f-aecafa6ce8a5")
APEX_DRONE_ID = uuid.UUID("77916c66-0d6a-49b4-ba56-2f9a1cb9a26d")


def main():
    parser = argparse.ArgumentParser(description="Run Live SITL Telemetry Bridge")
    parser.add_argument("--rate-hz", type=float, default=1.0, help="Telemetry emission rate in Hz")
    parser.add_argument("--duration-sec", type=int, default=0, help="Total seconds to run (0 = indefinite)")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", DEFAULT_DB_URL)
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    print(f"[*] Connecting to PostgreSQL: {db_url}")
    with SessionLocal() as db:
        drone = db.get(Asset, APEX_DRONE_ID)
        if not drone:
            print(f"[!] Drone {APEX_DRONE_ID} not found in database.")
            return
        drone_reg = drone.registration

        # Ensure DataSource mapping exists for MAVLink sysid 1
        ds = db.execute(
            select(DataSource).where(
                DataSource.organization_id == APEX_ORG_ID,
                DataSource.name == "SITL Demo Gateway",
            )
        ).scalar_one_or_none()

        if not ds:
            ds = DataSource(
                id=uuid.uuid4(),
                organization_id=APEX_ORG_ID,
                name="SITL Demo Gateway",
                connector_type="MAVLINK",
                connection_config={"system_id_map": {"1": str(APEX_DRONE_ID)}},
                status="ACTIVE",
            )
            db.add(ds)
            db.commit()
            print(f"[+] Created DataSource: {ds.id}")
        ds_id = ds.id

    connector = MAVLinkConnector()
    sitl = ArduPilotSITLEngine(sysid=1)
    # Start coordinates: Bangalore Operations Airspace
    center_lat = 12.9716
    center_lon = 77.5946
    radius_deg = 0.003

    sitl.state.lat_deg = center_lat
    sitl.state.lon_deg = center_lon
    sitl.state.alt_rel_m = 35.0
    sitl.state.alt_msl_m = 920.0
    sitl.state.ground_speed_mps = 12.0
    sitl.state.heading_deg = 90.0
    sitl.state.battery_voltage_v = 24.6
    sitl.state.battery_remaining_pct = 92
    sitl.state.armed = True
    sitl.state.flight_mode = "GUIDED"
    sitl.state.gps_fix_type = 3
    sitl.state.satellites = 16
    sitl.state.hdop = 0.75

    print(f"[+] Started Live SITL Emitter for {drone_reg} ({APEX_DRONE_ID})")
    print(f"[*] Streaming live MAVLink frames at {args.rate_hz} Hz...")

    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        print("\n[*] Stopping SITL stream...")
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    start_time = time.time()
    step = 0

    while running:
        t_now = time.time() - start_time
        if args.duration_sec > 0 and t_now >= args.duration_sec:
            break

        # Simulate smooth circular orbit navigation
        angle = (t_now * 0.2) % (2 * math.pi)
        sitl.state.lat_deg = center_lat + radius_deg * math.cos(angle)
        sitl.state.lon_deg = center_lon + radius_deg * math.sin(angle)
        sitl.state.heading_deg = (math.degrees(angle + math.pi / 2)) % 360.0
        sitl.state.alt_rel_m = 35.0 + 5.0 * math.sin(t_now * 0.1)
        sitl.state.battery_remaining_pct = max(10, int(92 - (t_now * 0.1)))
        sitl.state.battery_voltage_v = 22.0 + (sitl.state.battery_remaining_pct / 100.0) * 3.2

        # Step physics and generate frames
        sitl.step_physics(dt=1.0 / args.rate_hz)
        
        # Ingest directly into connector
        frames = [
            sitl.pack_heartbeat(),
            sitl.pack_global_position_int(),
            sitl.pack_sys_status(),
            sitl.pack_gps_raw_int(),
        ]

        all_bytes = b"".join(frames)
        events = connector.feed_bytes(all_bytes)

        if events:
            with SessionLocal() as db:
                for evt in events:
                    apply_event(
                        db,
                        organization_id=APEX_ORG_ID,
                        asset_id=APEX_DRONE_ID,
                        event=evt,
                        data_source_id=ds_id,
                    )
                db.commit()

        step += 1
        if step % 5 == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Frame #{step:04d} | Pos: ({sitl.state.lat_deg:.6f}, {sitl.state.lon_deg:.6f}) | Alt: {sitl.state.alt_rel_m:.1f}m | Batt: {sitl.state.battery_remaining_pct}% | Mode: {sitl.state.flight_mode}")

        time.sleep(1.0 / args.rate_hz)

    print("[+] SITL Telemetry Stream concluded cleanly.")


if __name__ == "__main__":
    main()
