"""H2 (extends H1's H10 seed): deterministic, idempotent synthetic HUMS dataset.

Seeds HUMS sensors/readings/features onto assets in an existing QA
organization (falls back to creating one) to demonstrate the full pathway:
    Sensor Reading -> Feature Engine (RMS/peak/crest factor/kurtosis/FFT/
    trend) -> Exceedance -> Finding -> Evidence -> ProactiveSignalRecord

All data is explicitly synthetic/demo — asset registrations are prefixed
"KQA" and every scenario is documented as synthetic in this file and in the
printed output. Uses app.services.hums_service (the real service layer),
not raw ORM, so every row passes the same validation/audit/feature-
processing path a real API caller would. Assets and sensors are looked up
by natural key before creating, so re-running is safe with respect to
those. Known limitation: individual readings/features are NOT deduplicated
on re-run (each run ingests a fresh batch of readings), so repeated runs
grow the feature-history table rather than staying a strict no-op — safe
for a demo dataset, not the same "always a no-op" guarantee
scripts/seed_qa_dataset.py makes for its entities.

Scenarios (H2 spec sections 23-24):
  Aircraft:
    1. Healthy aircraft — steady low vibration.
    2. Aircraft with increasing gearbox vibration — 4 successive batches
       (normal -> small increase -> progressive increase -> critical),
       each large enough not to blend across batches in the rolling
       feature window, ending in a full exceedance/evidence/signal chain.
    3. Aircraft with abnormal temperature trend — steadily rising EGT.
  Drone:
    4. Healthy drone motor.
    5. Drone with motor vibration anomaly — direct jump to critical.
  Helicopter:
    6. Helicopter main/tail rotor gearbox vibration scenario.
  Cross-cutting:
    7. Insufficient data — a sensor with only one reading correctly
       reports INSUFFICIENT_DATA rather than a fabricated health score.

H3 adds baseline-driven health-intelligence scenarios (H3 spec section 29),
seeded by seed_h3_scenarios() below, across aircraft/drone/helicopter:
  H3-1 Healthy               -> HEALTHY
  H3-2 Mild/brief deviation  -> WATCH
  H3-3 Persistent deviation  -> DEGRADED
  H3-4 Accelerating          -> WARNING/CRITICAL
  H3-5 Multi-feature (rms + crest_factor both elevated) -> DEGRADED/WARNING
  H3-6 Insufficient data (too few batches for a baseline) -> INSUFFICIENT_DATA
  H3-7 Stable but noisy      -> HEALTHY/WATCH (never spams a signal)

Note: because this script is not reading-level idempotent (see the
limitation above), re-running it against an organization that already has
H3 demo data from a prior run accumulates additional feature history into
each sensor's baseline, which can shift a scenario's exact resulting state
across repeated runs (e.g. H3-3's "persistent deviation" may land as WATCH
rather than DEGRADED once earlier runs' readings are blended into the
baseline). The underlying baseline/deviation/trend/health engine itself is
verified deterministically against a fresh, isolated database in
tests/unit/test_hums_baseline_and_health_engine.py and
tests/integration/test_hums_baseline_and_health.py — treat this script as a
demo aid, not as the correctness oracle for H3.

PRODUCTION SAFETY: refuses to run unless ENVIRONMENT is "development" or
"staging", matching scripts/seed_qa_dataset.py's convention.

Usage:
    DATABASE_URL=postgresql+psycopg://... ENVIRONMENT=staging \\
        python scripts/seed_hums_dataset.py
"""

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 -- registers every mapped class app/models/__init__.py imports
from app.models.asset import Asset, AssetType
from app.models.hums import HUMSSensor
from app.models.organization import Organization
from app.schemas.hums import HUMSReadingIn, HUMSSensorCreate
from app.services import hums_service

ALLOWED_ENVIRONMENTS = {"development", "staging"}

# Matches hums_service.FEATURE_WINDOW_READING_COUNT -- each demo batch has at
# least this many readings so the rolling feature window reflects that batch
# alone rather than blending with the previous one (see the equivalent
# comment in tests/integration/test_hums_feature_engine.py).
BATCH_SIZE = 20


def _get_or_create_asset(db: Session, *, organization_id: uuid.UUID, asset_type: AssetType, label: str) -> Asset:
    existing = db.execute(
        select(Asset).where(
            Asset.organization_id == organization_id,
            Asset.registration == f"KQA-HUMS-{label}",
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    asset = Asset(
        organization_id=organization_id,
        asset_type=asset_type,
        registration=f"KQA-HUMS-{label}",
        serial_number=f"SN-HUMS-{uuid.uuid4().hex[:8]}",
    )
    db.add(asset)
    db.flush()
    print(f"  Created {asset_type.value} asset {asset.registration} ({asset.id}).")
    return asset


def _get_or_create_sensor(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, **kwargs) -> HUMSSensor:
    existing = db.execute(
        select(HUMSSensor).where(
            HUMSSensor.organization_id == organization_id,
            HUMSSensor.asset_id == asset_id,
            HUMSSensor.sensor_code == kwargs["sensor_code"],
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    sensor = hums_service.create_sensor(
        db,
        organization_id=organization_id,
        user_id=None,
        payload=HUMSSensorCreate(asset_id=asset_id, **kwargs),
    )
    print(f"  Created sensor {kwargs['sensor_code']} on asset {asset_id}.")
    return sensor


def _ingest_batch(
    db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, values: list[float], unit: str, base_minutes_ago: int, batch_label: str
) -> None:
    now = datetime.now(UTC)
    readings = [
        HUMSReadingIn(recorded_at=now - timedelta(minutes=base_minutes_ago - i), value=v, unit=unit)
        for i, v in enumerate(values)
    ]
    hums_service.ingest_readings(
        db, organization_id=organization_id, sensor_id=sensor_id, readings=readings, ingestion_batch=batch_label
    )
    hums_service.detect_and_record_exceedances(db, organization_id=organization_id, sensor_id=sensor_id, user_id=None)


def seed(db: Session, *, organization_id: uuid.UUID) -> None:
    # --- Scenario 1: Healthy aircraft ---------------------------------
    aircraft_healthy = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="AC1")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=aircraft_healthy.id,
        sensor_code="GBX-VIB-01", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s",
        installation_location="Main Gearbox",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=sensor.id,
        values=[1.2 + (i % 3) * 0.1 for i in range(BATCH_SIZE)], unit="mm/s",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-aircraft-healthy",
    )
    print(f"  Scenario 1 (Healthy Aircraft): {aircraft_healthy.registration} — steady low vibration.")

    # --- Scenario 2: Aircraft with increasing gearbox vibration -------
    aircraft_degrading = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="AC2")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=aircraft_degrading.id,
        sensor_code="GBX-VIB-02", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s",
        installation_location="Accessory Gearbox",
    )
    progression = [
        ("normal", [1.0, 1.1, 0.9, 1.0, 1.2, 0.8, 1.0, 1.1, 0.9, 1.0] * 2),
        ("small_increase", [2.0, 2.2, 1.8, 2.0, 2.3, 1.7, 2.0, 2.1, 1.9, 2.0] * 2),
        ("progressive_increase", [4.0, 4.3, 3.7, 4.0, 4.5, 3.5, 4.0, 4.2, 3.8, 4.0] * 2),
        ("critical", [9.0, 9.5, 8.5, 9.0, 9.8, 8.2, 9.0, 9.3, 8.7, 9.0] * 2),
    ]
    exceedance = None
    for i, (stage, values) in enumerate(progression):
        exceedance = None
        base_minutes = (len(progression) - i) * (BATCH_SIZE + 5)
        _ingest_batch(
            db, organization_id=organization_id, sensor_id=sensor.id, values=values, unit="mm/s",
            base_minutes_ago=base_minutes, batch_label=f"hums-seed-aircraft-degrading-{stage}",
        )
    exceedances = hums_service.list_features(db, organization_id=organization_id, sensor_id=sensor.id, feature_type="rms")
    print(
        f"  Scenario 2 (Aircraft Progressive Gearbox Degradation): {aircraft_degrading.registration} — "
        f"{len(progression)} stages (normal -> small increase -> progressive increase -> critical), "
        f"{len(exceedances)} RMS feature-history points recorded, ending in a full exceedance/evidence/signal chain."
    )

    # --- Scenario 3: Aircraft with abnormal temperature trend ---------
    aircraft_temp = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="AC3")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=aircraft_temp.id,
        sensor_code="ENG-EGT-01", sensor_type="THERMOCOUPLE", measurement_type="temperature", unit="C",
        installation_location="Engine Exhaust Gas Temperature Probe",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=sensor.id,
        values=[600.0 + i * 3.0 for i in range(BATCH_SIZE)], unit="C",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-aircraft-egt-trend",
    )
    print(f"  Scenario 3 (Aircraft Abnormal Temperature Trend): {aircraft_temp.registration} — steadily rising EGT.")

    # --- Scenario 4: Healthy drone --------------------------------------
    drone_healthy = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="DR1")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=drone_healthy.id,
        sensor_code="MOTOR-VIB-01", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="g",
        installation_location="Motor 1",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=sensor.id,
        values=[0.3 + (i % 4) * 0.02 for i in range(BATCH_SIZE)], unit="g",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-drone-healthy",
    )
    print(f"  Scenario 4 (Healthy Drone): {drone_healthy.registration} — steady low motor vibration.")

    # --- Scenario 5: Drone motor vibration anomaly ----------------------
    drone_anomaly = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="DR2")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=drone_anomaly.id,
        sensor_code="MOTOR-VIB-02", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s",
        installation_location="Motor 3",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=sensor.id,
        values=[7.0, 7.8, 6.5, 7.2, 8.0, 6.8, 7.5, 7.9, 6.9, 7.3] * 2, unit="mm/s",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-drone-motor-anomaly",
    )
    print(f"  Scenario 5 (Drone Motor Vibration Anomaly): {drone_anomaly.registration} — elevated motor vibration.")

    # --- Scenario 6: Helicopter rotor/gearbox vibration -----------------
    helicopter = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.HELICOPTER, label="HELI1")
    sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=helicopter.id,
        sensor_code="MGB-VIB-01", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s",
        installation_location="Main Gearbox",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=sensor.id,
        values=[5.5, 6.0, 5.2, 5.8, 6.3, 5.4, 5.9, 6.1, 5.6, 5.7] * 2, unit="mm/s",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-helicopter-mgb",
    )
    tail_sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=helicopter.id,
        sensor_code="TGB-VIB-01", sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s",
        installation_location="Tail Rotor Gearbox",
    )
    _ingest_batch(
        db, organization_id=organization_id, sensor_id=tail_sensor.id,
        values=[1.5 + (i % 3) * 0.1 for i in range(BATCH_SIZE)], unit="mm/s",
        base_minutes_ago=BATCH_SIZE, batch_label="hums-seed-helicopter-tgb",
    )
    print(f"  Scenario 6 (Helicopter Rotor/Gearbox): {helicopter.registration} — MGB elevated (HIGH), TGB healthy.")

    # --- Scenario 7: Insufficient data -----------------------------------
    sparse_sensor = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=aircraft_healthy.id,
        sensor_code="ENG-TEMP-SPARSE-01", sensor_type="THERMOCOUPLE", measurement_type="temperature", unit="C",
        installation_location="Auxiliary Power Unit",
    )
    hums_service.ingest_readings(
        db, organization_id=organization_id, sensor_id=sparse_sensor.id,
        readings=[HUMSReadingIn(recorded_at=datetime.now(UTC), value=85.0, unit="C")],
        ingestion_batch="hums-seed-sparse",
    )
    summary = hums_service.get_asset_health(db, organization_id=organization_id, asset_id=aircraft_healthy.id)
    sparse_component = next((c for c in summary.components if c.sensor_id == sparse_sensor.id), None)
    status = sparse_component.status if sparse_component else "N/A"
    print(
        f"  Scenario 7 (Insufficient Data): {aircraft_healthy.registration} — 1 reading, "
        f"health status correctly reports '{status}' (never a fabricated RUL/score)."
    )


HEALTHY_PATTERN = ([1.0 + 0.05 * ((-1) ** i) for i in range(10)]) * 2  # 20 values oscillating 0.95-1.05


def _establish_baseline(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, batches: int, base_minutes: int) -> None:
    # Deterministic (not random) batch-to-batch jitter -- a real fleet's
    # baseline naturally has some spread across flights/sorties; feeding
    # the identical pattern every batch would give ~zero baseline variance
    # and make any deviation read as SEVERE regardless of magnitude, which
    # would defeat the point of a WATCH/DEGRADED/WARNING staged demo.
    for b in range(batches):
        jitter = 1.0 + 0.07 * (((b % 3) - 1))  # cycles -7%, 0%, +7%
        values = [v * jitter for v in HEALTHY_PATTERN]
        _ingest_batch(
            db, organization_id=organization_id, sensor_id=sensor_id, values=values, unit="mm/s",
            base_minutes_ago=base_minutes - b * 10, batch_label=f"h3-baseline-{b}",
        )


def seed_h3_scenarios(db: Session, *, organization_id: uuid.UUID) -> None:
    """H3: baseline-driven health-intelligence scenarios, across aircraft/
    drone/helicopter. All synthetic; see this file's module docstring.
    """
    h3_1 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H3-1")
    s1 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_1.id, sensor_code="H3-VIB-01",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Main Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s1.id, batches=8, base_minutes=200)
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_1.id)
    print(f"  H3-1 (Healthy): {h3_1.registration} — state={intel.state}")

    h3_2 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H3-2")
    s2 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_2.id, sensor_code="H3-VIB-02",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Main Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s2.id, batches=8, base_minutes=200)
    _ingest_batch(db, organization_id=organization_id, sensor_id=s2.id, values=[1.09] * 20, unit="mm/s", base_minutes_ago=0, batch_label="h3-2-brief-deviation")
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_2.id)
    print(f"  H3-2 (Mild/brief deviation): {h3_2.registration} — state={intel.state} (targeting WATCH: single mildly-elevated observation)")

    h3_3 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="H3-3")
    s3 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_3.id, sensor_code="H3-VIB-03",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 2",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s3.id, batches=8, base_minutes=200)
    for i in range(4):
        _ingest_batch(db, organization_id=organization_id, sensor_id=s3.id, values=[1.15] * 20, unit="mm/s", base_minutes_ago=(3 - i) * 10, batch_label=f"h3-3-persistent-{i}")
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_3.id)
    print(f"  H3-3 (Persistent deviation): {h3_3.registration} — state={intel.state} (targeting DEGRADED: sustained moderate deviation, 4 consecutive observations)")

    h3_4 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.HELICOPTER, label="H3-4")
    s4 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_4.id, sensor_code="H3-VIB-04",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Main Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s4.id, batches=8, base_minutes=200)
    for i, mult in enumerate([1.5, 2.5, 5.0]):
        _ingest_batch(db, organization_id=organization_id, sensor_id=s4.id, values=[mult] * 20, unit="mm/s", base_minutes_ago=(2 - i) * 5, batch_label=f"h3-4-accelerating-{i}")
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_4.id)
    print(f"  H3-4 (Accelerating deterioration): {h3_4.registration} — state={intel.state} (targeting WARNING/CRITICAL)")

    h3_5 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H3-5")
    s5 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_5.id, sensor_code="H3-VIB-05",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Accessory Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s5.id, batches=8, base_minutes=200)
    # Multi-feature: elevated RMS AND a distinctly different (non-constant,
    # so crest_factor != 1.0) waveform shape than the baseline pattern.
    multi_values = [1.6 + 0.4 * ((-1) ** i) for i in range(10)] * 2
    for i in range(3):
        _ingest_batch(db, organization_id=organization_id, sensor_id=s5.id, values=multi_values, unit="mm/s", base_minutes_ago=(2 - i) * 10, batch_label=f"h3-5-multi-{i}")
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_5.id)
    contributors = [c.feature_type for comp in intel.components for c in comp.primary_contributors]
    print(f"  H3-5 (Multi-feature deterioration): {h3_5.registration} — state={intel.state} (targeting DEGRADED/WARNING), contributors={contributors}")

    h3_6 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="H3-6")
    s6 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_6.id, sensor_code="H3-VIB-06",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 4",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=s6.id, batches=2, base_minutes=20)  # below MIN_SAMPLES_FOR_BASELINE
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_6.id)
    print(f"  H3-6 (Insufficient data): {h3_6.registration} — state={intel.state} (targeting INSUFFICIENT_DATA -- never fabricated)")

    h3_7 = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H3-7")
    s7 = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h3_7.id, sensor_code="H3-VIB-07",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="APU",
    )
    noisy_pattern = [1.0, 1.4, 0.7, 1.2, 0.8, 1.3, 0.9, 1.1, 0.75, 1.25] * 2
    for b in range(9):
        _ingest_batch(db, organization_id=organization_id, sensor_id=s7.id, values=noisy_pattern, unit="mm/s", base_minutes_ago=(9 - b) * 10, batch_label=f"h3-7-noisy-{b}")
    intel = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h3_7.id)
    print(f"  H3-7 (Stable but noisy): {h3_7.registration} — state={intel.state} (targeting HEALTHY/WATCH -- no signal spam regardless)")


def seed_h4_scenarios(db: Session, *, organization_id: uuid.UUID) -> None:
    """H4: diagnostic candidate generation scenarios (H4 spec section 37).
    All synthetic; demonstrates the full H3 health -> H4 diagnostic pathway,
    including competing hypotheses and the sensor-fault safeguard.
    """
    spiky = [1.0] * 18 + [8.0, -6.0]

    # Scenario B: single-feature anomaly (rms only, kurtosis stays normal)
    # -- required bearing-degradation condition not met -> no candidate.
    h4_b = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H4-B")
    sb = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h4_b.id, sensor_code="H4-VIB-0B",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=sb.id, batches=8, base_minutes=200)
    _ingest_batch(db, organization_id=organization_id, sensor_id=sb.id, values=[1.3] * 20, unit="mm/s", base_minutes_ago=0, batch_label="h4-b-single-feature")
    diags_b = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=h4_b.id)
    print(f"  H4-B (Single-feature anomaly): {h4_b.registration} — {len(diags_b)} candidate(s) (targeting 0: rms-only doesn't satisfy bearing signature's required kurtosis condition)")

    # Scenario C/D/E: multi-feature correlated + persistent -> strong
    # candidate with a weaker, contradicted alternative preserved.
    h4_c = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H4-C")
    sc = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h4_c.id, sensor_code="H4-VIB-0C",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Accessory Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=sc.id, batches=8, base_minutes=200)
    _ingest_batch(db, organization_id=organization_id, sensor_id=sc.id, values=spiky, unit="mm/s", base_minutes_ago=0, batch_label="h4-c-correlated")
    intel_c = hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h4_c.id)
    diags_c = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=h4_c.id)
    print(f"  H4-C/D/E (Correlated + persistent + competing hypotheses): {h4_c.registration} — health={intel_c.state}, candidates:")
    for d in diags_c:
        print(f"      {d.fault_code} {d.fault_name} — status={d.status} confidence={d.confidence} score={d.score}")

    # Scenario F: sensor fault -- one of two sensors on the same component
    # goes bad while its sibling stays healthy.
    h4_f = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="H4-F")
    from app.models.component import Component, ComponentStatus, ComponentType

    component_f = Component(
        organization_id=organization_id, asset_id=h4_f.id, component_type=ComponentType.MOTOR,
        name="Motor 2", serial_number=f"H4F-CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db.add(component_f)
    db.flush()
    sf_bad = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h4_f.id, component_id=component_f.id, sensor_code="H4-VIB-0F-BAD",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 2",
    )
    sf_good = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h4_f.id, component_id=component_f.id, sensor_code="H4-VIB-0F-GOOD",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 2 (redundant)",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=sf_bad.id, batches=8, base_minutes=200)
    _establish_baseline(db, organization_id=organization_id, sensor_id=sf_good.id, batches=8, base_minutes=200)
    _ingest_batch(db, organization_id=organization_id, sensor_id=sf_bad.id, values=spiky, unit="mm/s", base_minutes_ago=0, batch_label="h4-f-sensor-fault")
    hums_service.get_component_health_intelligence(db, organization_id=organization_id, component_id=component_f.id)
    diags_f = hums_service.list_component_diagnostics(db, organization_id=organization_id, component_id=component_f.id)
    fault_codes_f = [d.fault_code for d in diags_f]
    print(f"  H4-F (Sensor fault safeguard): {h4_f.registration} — candidates: {fault_codes_f} (targeting SEN-ANOM-001, not an immediate physical-component diagnosis)")

    # Scenario H: insufficient evidence -- anomaly exists but too little
    # history exists yet for a trustworthy baseline/diagnosis.
    h4_h = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.HELICOPTER, label="H4-H")
    sh = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h4_h.id, sensor_code="H4-VIB-0H",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Main Gearbox",
    )
    _establish_baseline(db, organization_id=organization_id, sensor_id=sh.id, batches=2, base_minutes=20)  # below MIN_SAMPLES_FOR_BASELINE
    _ingest_batch(db, organization_id=organization_id, sensor_id=sh.id, values=spiky, unit="mm/s", base_minutes_ago=0, batch_label="h4-h-insufficient")
    diags_h = hums_service.list_asset_diagnostics(db, organization_id=organization_id, asset_id=h4_h.id)
    print(f"  H4-H (Insufficient evidence): {h4_h.registration} — {len(diags_h)} candidate(s) (targeting 0: no baseline yet means no fabricated diagnosis)")


def seed_h5_scenarios(db: Session, *, organization_id: uuid.UUID) -> None:
    """H5: prognostics/RUL scenarios (H5 spec section 40). All synthetic;
    demonstrates the H3 health -> H4 diagnostic -> H5 prognostic pathway
    including uncertainty, extrapolation, and maintenance-reset segmentation.
    """
    import random

    from app.models.component import Component, ComponentStatus, ComponentType
    from app.models.installation_history import ComponentInstallation

    # H5-A: healthy, stable -- no meaningful RUL warning.
    h5_a = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H5-A")
    sa = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_a.id, sensor_code="H5-VIB-0A",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Gearbox",
    )
    for b in range(10):
        _ingest_batch(db, organization_id=organization_id, sensor_id=sa.id, values=[1.0] * 20, unit="mm/s", base_minutes_ago=(10 - b) * 60, batch_label=f"h5-a-{b}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_a.id, user_id=None)
    prog_a = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=h5_a.id)
    rms_a = next((p for p in prog_a if p.feature_type == "rms"), None)
    print(f"  H5-A (Healthy/stable): {h5_a.registration} — status={rms_a.status if rms_a else 'N/A'}, RUL={rms_a.rul_estimate if rms_a else None} (targeting no meaningful warning)")

    # H5-B/H5-H: known linear degradation -- quantitative crossing check.
    h5_b = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H5-B")
    sb = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_b.id, sensor_code="H5-VIB-0B",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Accessory Gearbox",
    )
    slope, start, n_batches = 0.15, 1.0, 20
    for b in range(n_batches):
        val = start + slope * b
        _ingest_batch(db, organization_id=organization_id, sensor_id=sb.id, values=[val] * 20, unit="mm/s", base_minutes_ago=(n_batches - b) * 60, batch_label=f"h5-b-{b}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_b.id, user_id=None)
    prog_b = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=h5_b.id)
    rms_b = next((p for p in prog_b if p.feature_type == "rms"), None)
    expected_crossing = (8.0 - start) / slope
    expected_rul = expected_crossing - (n_batches - 1)
    print(
        f"  H5-B/H (Known linear degradation): {h5_b.registration} — RUL={rms_b.rul_estimate if rms_b else None} "
        f"{rms_b.rul_unit if rms_b else ''} (expected ~{round(expected_rul, 1)}, confidence={rms_b.confidence if rms_b else 'N/A'})"
    )

    # H5-C: accelerating degradation -> shorter RUL, ACCELERATING trajectory.
    h5_c = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.HELICOPTER, label="H5-C")
    sc = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_c.id, sensor_code="H5-VIB-0C",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Main Gearbox",
    )
    for i, val in enumerate([1.0, 1.05, 1.1, 1.15, 1.5, 2.5, 4.0, 6.0]):
        _ingest_batch(db, organization_id=organization_id, sensor_id=sc.id, values=[val] * 20, unit="mm/s", base_minutes_ago=(8 - i) * 60, batch_label=f"h5-c-{i}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_c.id, user_id=None)
    models_c = hums_service.list_asset_degradation_models(db, organization_id=organization_id, asset_id=h5_c.id)
    rms_model_c = next((m for m in models_c if m.feature_type == "rms"), None)
    print(f"  H5-C (Accelerating degradation): {h5_c.registration} — trajectory={rms_model_c.trajectory_state if rms_model_c else 'N/A'} (targeting ACCELERATING)")

    # H5-D: high-noise degradation -> wider uncertainty, lower confidence.
    h5_d = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="H5-D")
    sd = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_d.id, sensor_code="H5-VIB-0D",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 1",
    )
    random.seed(7)
    for b in range(20):
        val = 1.0 + 0.15 * b + random.uniform(-0.5, 0.5)
        _ingest_batch(db, organization_id=organization_id, sensor_id=sd.id, values=[val] * 20, unit="mm/s", base_minutes_ago=(20 - b) * 60, batch_label=f"h5-d-{b}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_d.id, user_id=None)
    prog_d = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=h5_d.id)
    rms_d = next((p for p in prog_d if p.feature_type == "rms"), None)
    print(f"  H5-D (High-noise degradation): {h5_d.registration} — RUL range=[{rms_d.rul_lower if rms_d else None},{rms_d.rul_upper if rms_d else None}], confidence={rms_d.confidence if rms_d else 'N/A'} (targeting wider range/lower confidence than H5-B)")

    # H5-E: insufficient history -> RUL null, INSUFFICIENT_DATA.
    h5_e = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H5-E")
    se = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_e.id, sensor_code="H5-VIB-0E",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Engine",
    )
    _ingest_batch(db, organization_id=organization_id, sensor_id=se.id, values=[1.0, 1.1, 1.2], unit="mm/s", base_minutes_ago=0, batch_label="h5-e-sparse")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_e.id, user_id=None)
    prog_e = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=h5_e.id)
    rms_e = next((p for p in prog_e if p.feature_type == "rms"), None)
    print(f"  H5-E (Insufficient history): {h5_e.registration} — status={rms_e.status if rms_e else 'N/A'}, RUL={rms_e.rul_estimate if rms_e else None} (targeting None/INSUFFICIENT_DATA)")

    # H5-F: maintenance reset -- degradation, then component replacement, then a fresh healthy trajectory.
    h5_f = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.AIRCRAFT, label="H5-F")
    component_f = Component(
        organization_id=organization_id, asset_id=h5_f.id, component_type=ComponentType.ENGINE,
        name="Engine 1", serial_number=f"H5F-CMP-{uuid.uuid4().hex[:6]}", status=ComponentStatus.INSTALLED,
    )
    db.add(component_f)
    db.flush()
    sf = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_f.id, component_id=component_f.id, sensor_code="H5-VIB-0F",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Engine 1",
    )
    now = datetime.now(UTC)
    for b in range(8):
        _ingest_batch(db, organization_id=organization_id, sensor_id=sf.id, values=[1.0 + 0.5 * b] * 20, unit="mm/s", base_minutes_ago=(20 - b) * 60, batch_label=f"h5-f-pre-{b}")
    db.add(ComponentInstallation(organization_id=organization_id, component_id=component_f.id, asset_id=h5_f.id, installed_at=now - timedelta(minutes=11 * 60)))
    db.flush()
    for b in range(8):
        _ingest_batch(db, organization_id=organization_id, sensor_id=sf.id, values=[1.0 + 0.05 * b] * 20, unit="mm/s", base_minutes_ago=(9 - b) * 60, batch_label=f"h5-f-post-{b}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_f.id, user_id=None)
    baselines_f = hums_service.get_asset_baselines(db, organization_id=organization_id, asset_id=h5_f.id)
    rms_baseline_f = next((b for b in baselines_f if b.feature_type == "rms"), None)
    print(f"  H5-F (Maintenance reset): {h5_f.registration} — reference baseline mean={rms_baseline_f.mean if rms_baseline_f else None} (targeting the post-reset ~1.0-1.35 window, not the pre-reset ~1.0-4.5 window)")

    # H5-I: extrapolation warning -- slow degradation, threshold far away.
    h5_i = _get_or_create_asset(db, organization_id=organization_id, asset_type=AssetType.DRONE, label="H5-I")
    si = _get_or_create_sensor(
        db, organization_id=organization_id, asset_id=h5_i.id, sensor_code="H5-VIB-0I",
        sensor_type="ACCELEROMETER", measurement_type="vibration", unit="mm/s", installation_location="Motor 3",
    )
    for b in range(8):
        val = 1.0 + 0.002 * b  # extremely slow drift
        _ingest_batch(db, organization_id=organization_id, sensor_id=si.id, values=[val] * 20, unit="mm/s", base_minutes_ago=(8 - b) * 10, batch_label=f"h5-i-{b}")
    hums_service.get_asset_health_intelligence(db, organization_id=organization_id, asset_id=h5_i.id, user_id=None)
    prog_i = hums_service.list_asset_prognostics(db, organization_id=organization_id, asset_id=h5_i.id)
    rms_i = next((p for p in prog_i if p.feature_type == "rms"), None)
    print(f"  H5-I (Extrapolation warning): {h5_i.registration} — status={rms_i.status if rms_i else 'N/A'} (targeting LOW_CONFIDENCE)")


def seed_h6_scenarios(db: Session, *, organization_id: uuid.UUID) -> None:
    """H6: Digital Twin scenarios. Deliberately does NOT create new assets —
    the twin is a read-only aggregation, so it demonstrates itself directly
    against assets/components already created by the H1-H5 seed functions
    above (in particular H5-F's component-replacement scenario, which
    already has real ComponentInstallation genealogy across a maintenance
    reset — exactly H6-B/H6-C's target scenario).
    """
    from app.services import digital_twin_service

    h5_f = db.execute(select(Asset).where(Asset.organization_id == organization_id, Asset.registration == "KQA-HUMS-H5-F")).scalars().first()
    if not h5_f:
        print("  H6: H5-F asset not found (run seed_h5_scenarios first) — skipping H6 demo.")
        return

    snapshot = digital_twin_service.get_asset_snapshot(db, organization_id=organization_id, asset_id=h5_f.id)
    print(f"  H6-A/D/E/F (Twin snapshot): {h5_f.registration} — health={snapshot.health.state if snapshot.health else None}, "
          f"diagnostics={len(snapshot.diagnostics)}, prognostics={len(snapshot.prognostics)}, readiness={snapshot.readiness.readiness_state}")

    components = digital_twin_service.get_asset_component_tree(db, organization_id=organization_id, asset_id=h5_f.id)
    for c in components:
        genealogy = digital_twin_service.get_component_genealogy(db, organization_id=organization_id, component_id=c.component.id)
        print(f"  H6-B/C (Component genealogy): {c.component.name} — {len(genealogy)} installation span(s) across its lifecycle")

    timeline = digital_twin_service.get_asset_timeline(db, organization_id=organization_id, asset_id=h5_f.id)
    print(f"  H6-G (Timeline): {h5_f.registration} — {len(timeline)} unified lifecycle event(s)")

    warnings = digital_twin_service.check_asset_consistency(db, organization_id=organization_id, asset_id=h5_f.id)
    print(f"  H6-H (Consistency check): {h5_f.registration} — {len(warnings)} warning(s) (targeting 0 for well-formed seed data)")


def main() -> None:
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment not in ALLOWED_ENVIRONMENTS:
        print(f"Refusing to run: ENVIRONMENT={environment!r} is not in {ALLOWED_ENVIRONMENTS}.")
        sys.exit(1)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL environment variable is required.", file=sys.stderr)
        sys.exit(1)

    qa_org_id = os.environ.get("QA_ORG_ID")
    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        if qa_org_id:
            org = db.get(Organization, uuid.UUID(qa_org_id))
            if not org:
                print(f"Organization {qa_org_id} not found.")
                sys.exit(1)
        else:
            org = db.execute(select(Organization).where(Organization.name.ilike("QA%"))).scalars().first()
            if not org:
                org = Organization(name=f"QA HUMS Demo {uuid.uuid4().hex[:6]}")
                db.add(org)
                db.flush()
                print(f"No existing QA organization found — created {org.name} ({org.id}).")

        print(f"Seeding HUMS dataset into organization {org.name} ({org.id})")
        seed(db, organization_id=org.id)
        db.commit()
        print("Seeding H3 baseline & health-intelligence scenarios...")
        seed_h3_scenarios(db, organization_id=org.id)
        db.commit()
        print("Seeding H4 diagnostics & fault-isolation scenarios...")
        seed_h4_scenarios(db, organization_id=org.id)
        db.commit()
        print("Seeding H5 prognostics & RUL scenarios...")
        seed_h5_scenarios(db, organization_id=org.id)
        db.commit()
        print("Demonstrating H6 digital twin aggregation...")
        seed_h6_scenarios(db, organization_id=org.id)
        db.commit()
        print("Done.")


if __name__ == "__main__":
    main()
