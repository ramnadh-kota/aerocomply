"""M14.14: Edge Hardware & Telemetry Simulator.

Generates realistic telemetry bursts (vibration, motor current, bearing temperatures)
for an organization's assets and feeds them through the Edge Gateway envelope.

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/simulate_edge_telemetry.py --org-id <UUID> --asset-id <UUID>
"""

import argparse
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
import random

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.organization import Organization
from app.models.asset import Asset
from app.schemas.edge_hardware import DeviceTelemetryEnvelope, EdgeSensorMeasurement, EdgeDeviceCreate
from app.services.edge_hardware_service import register_edge_device, process_device_telemetry_envelope


def run_simulator(org_id_str: str | None = None, asset_id_str: str | None = None, anomaly: bool = False) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()

    try:
        if org_id_str:
            org = db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id_str))).scalar_one_or_none()
        else:
            org = db.execute(select(Organization).order_by(Organization.created_at.asc())).scalars().first()

        if not org:
            print("No organization found to simulate telemetry for.", file=sys.stderr)
            return

        print(f"--- Simulating Edge Telemetry for Org: {org.name} ({org.id}) ---")

        # Find or select asset
        asset = None
        if asset_id_str:
            asset = db.execute(select(Asset).where(Asset.id == uuid.UUID(asset_id_str))).scalar_one_or_none()
        else:
            asset = db.execute(select(Asset).where(Asset.organization_id == org.id)).scalars().first()

        device_id = f"KOTA-EDGE-SN-{str(org.id)[:6].upper()}-01"

        # Register device
        device = register_edge_device(
            db,
            organization_id=org.id,
            payload=EdgeDeviceCreate(
                device_id=device_id,
                device_type="EDGE_GATEWAY",
                firmware_version="2.4.1",
                asset_id=asset.id if asset else None,
                metadata_json={"bus": "CAN_FD", "sampling_hz": 1000},
            ),
        )
        print(f"Registered/Verified Edge Gateway: {device.device_id}")

        now = datetime.now(UTC)
        measurements = []

        # 1. Vibration measurement
        base_rms = 0.45 if anomaly else 0.18 + random.uniform(-0.02, 0.02)
        measurements.append(
            EdgeSensorMeasurement(
                sensor_code="MOT_1_VIB",
                sensor_type="VIBRATION",
                timestamp=now,
                unit="g",
                raw_values={"rms_g": round(base_rms, 3), "peak_g": round(base_rms * 2.8, 3), "crest_factor": 2.8},
                quality="VALID",
            )
        )

        # 2. Temperature measurement
        base_temp = 85.0 if anomaly else 52.0 + random.uniform(-2.0, 3.0)
        measurements.append(
            EdgeSensorMeasurement(
                sensor_code="MOT_1_TEMP",
                sensor_type="TEMPERATURE",
                timestamp=now,
                unit="degC",
                raw_values={"temp_c": round(base_temp, 1)},
                quality="VALID",
            )
        )

        # 3. Voltage / Current
        measurements.append(
            EdgeSensorMeasurement(
                sensor_code="BAT_BUS_METRICS",
                sensor_type="ELECTRICAL",
                timestamp=now,
                unit="V",
                raw_values={"voltage_v": 49.8, "current_a": 34.2},
                quality="VALID",
            )
        )

        envelope = DeviceTelemetryEnvelope(
            device_id=device_id,
            gateway_id=device_id,
            firmware_version="2.4.1",
            source_asset_id=asset.identifier if asset else None,
            sequence_number=random.randint(100, 9999),
            envelope_timestamp=now,
            measurements=measurements,
        )

        res = process_device_telemetry_envelope(db, organization_id=org.id, envelope=envelope)
        db.commit()
        print(f"Successfully processed telemetry burst: {res}")

    except Exception as exc:
        db.rollback()
        print(f"Error during simulation: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Edge Telemetry Simulator")
    parser.add_argument("--org-id", help="Organization UUID")
    parser.add_argument("--asset-id", help="Asset UUID")
    parser.add_argument("--anomaly", action="store_true", help="Generate anomalous exceedance burst")
    args = parser.parse_args()
    run_simulator(args.org_id, args.asset_id, args.anomaly)
