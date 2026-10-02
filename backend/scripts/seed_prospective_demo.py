"""Phase E (expanded): Deterministic, idempotent "master demo" seed for
prospective/client demonstrations.

Creates (or extends) an isolated demo tenant ('Apex Global Aero Logistics')
with representative data across every major product surface: fleet (aircraft
+ drones), facilities, components, telemetry ingestion + freshness, HUMS
sensors/features/baselines/diagnostics/prognostics, evidence + findings,
compliance obligations + inspection/maintenance requirements, work orders +
tasks, parts/vendor/purchase-order/inventory, AOG events + deferred items,
technician qualifications, MRO intelligence candidates, proactive
intelligence signals, SSO config (placeholder only), and commercial
plan/subscription/entitlement records.

Usage:
    DATABASE_URL=postgresql+psycopg://... python scripts/seed_prospective_demo.py

Safe to re-run: every section does a lookup-by-natural-key before inserting.
"""

import os
import sys
from datetime import datetime, timezone, timedelta, date

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.security import hash_password  # noqa: E402
import app.models  # noqa: E402,F401 — import all models so every FK target table is registered
from app.models.organization import Organization, OrganizationStatus, OrganizationIndustry, OnboardingStage  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.facility import Facility, FacilityType, FacilityStatus  # noqa: E402
from app.models.asset import Asset, AssetType  # noqa: E402
from app.models.aircraft import Aircraft  # noqa: E402
from app.models.aircraft_detail import AircraftDetail  # noqa: E402
from app.models.component import Component, ComponentType, ComponentStatus  # noqa: E402
from app.models.telemetry import (  # noqa: E402
    TelemetryFreshnessPolicy,
    TelemetryEventLog,
    TelemetryProcessingStatus,
    ExternalAssetMapping,
    EdgeDevice,
)
from app.models.hums import (  # noqa: E402
    HUMSSensor,
    HUMSSensorReading,
    HUMSFeature,
    HUMSBaseline,
    HUMSExceedance,
    HUMSDiagnosticCandidate,
    HUMSDegradationModel,
    HUMSPrognosticRecord,
)
from app.models.evidence import Evidence, EvidenceStatus  # noqa: E402
from app.models.finding import Finding, FindingSeverity, FindingStatus  # noqa: E402
from app.models.proactive_signal import ProactiveSignalRecord  # noqa: E402
from app.models.mro_intelligence import (  # noqa: E402
    MaintenanceIntelligenceCandidate,
    MROCandidateType,
    MROCandidateStatus,
    MROCandidatePriority,
)
from app.models.regulatory_document import RegulatoryDocument  # noqa: E402,F401
from app.models.applicability import ApplicabilityRule  # noqa: E402,F401
from app.models.procurement_request import ProcurementRequest  # noqa: E402,F401
from app.models.compliance import (  # noqa: E402
    RegulatoryRequirement,
    RegulatoryAuthority,
    ComplianceObligation,
    ComplianceState,
)
from app.models.inspection_requirement import InspectionRequirement, InspectionRequirementStatus  # noqa: E402
from app.models.maintenance_requirement import MaintenanceRequirement, MaintenanceIntervalType  # noqa: E402
from app.models.work_order import WorkOrder, WorkOrderStatus, WorkOrderType  # noqa: E402
from app.models.task import Task, TaskExecutionState  # noqa: E402
from app.models.part import Part, PartServiceabilityStatus  # noqa: E402
from app.models.vendor import Vendor  # noqa: E402
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine, PurchaseOrderStatus  # noqa: E402
from app.models.inventory_transaction import InventoryTransaction, InventoryTransactionType  # noqa: E402
from app.models.aog_event import AogEvent, AogBlocker, AogEventStatus, AogSeverity, AogBlockerType  # noqa: E402
from app.models.deferred_item import DeferredItem, DeferredItemCategory, DeferredItemBasis, DeferredItemStatus  # noqa: E402
from app.models.technician_qualification import TechnicianQualification  # noqa: E402
from app.models.sso import (  # noqa: E402
    SSOConfiguration,
    SSOProviderType,
    OperationalIncident,
    IncidentSeverity,
    IncidentStatus,
)
from app.models.plan import Plan  # noqa: E402
from app.models.product_catalog import ProductSuite  # noqa: E402
from app.models.subscription import Subscription, SubscriptionStatus  # noqa: E402
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit  # noqa: E402
from app.models.mission import Mission, MissionStatus  # noqa: E402
from app.models.import_job import ImportJob, ImportDomain, ImportJobStatus  # noqa: E402
from app.models.import_mapping import TenantImportMapping  # noqa: E402,F401
from app.models.part_requirement import PartRequirement, PartRequirementStatus  # noqa: E402
from app.models.vendor_part_availability import (  # noqa: E402
    VendorPartAvailability,
    PartAvailabilityStatus,
    PartCertificationStatus,
)
from app.models.lisa_conversation_context import LisaConversationContext  # noqa: E402
from app.models.applicability import (  # noqa: E402
    ApplicabilityCondition,
    ApplicabilityEvaluation,
    ConditionType,
    EvaluationResult,
)
from app.models.assessment import (  # noqa: E402
    Assessment,
    AssessmentScopeType,
    AssessmentStatus,
    AssessmentSnapshot,
    AssessmentFinding,
    AssessmentRisk,
    AssessmentGap,
    AssessmentRecommendation,
    AssessmentRoadmapItem,
    AssessmentMetric,
)


DEMO_ORG_NAME = "Apex Global Aero Logistics"
DEMO_ORG_CODE = "apex-aero-logistics"  # informal slug used only in messaging; not a DB column
DEMO_ADMIN_EMAIL = "admin@apexaero.demo"
DEMO_PASSWORD = "DemoPassword2026!Apex"

counts: dict[str, int] = {}


def bump(key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


def seed_demo_environment() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(database_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db: Session = SessionLocal()

    try:
        print("--- Seeding Master Demo Environment ---")
        now = datetime.now(timezone.utc)
        today = now.date()

        # ------------------------------------------------------------------
        # 1. Organization
        # ------------------------------------------------------------------
        org = db.execute(
            select(Organization).where(Organization.name == DEMO_ORG_NAME)
        ).scalar_one_or_none()
        if org is None:
            org = Organization(
                name=DEMO_ORG_NAME,
                status=OrganizationStatus.ACTIVE,
                industry=OrganizationIndustry.AIRCRAFT,
                onboarding_stage=OnboardingStage.ACTIVE,
            )
            db.add(org)
            db.flush()
            print(f"Created demo organization: {org.name} (id={org.id})")
        else:
            print(f"Demo organization exists: {org.name} (id={org.id})")

        # ------------------------------------------------------------------
        # 2. Admin user + supporting personas
        # ------------------------------------------------------------------
        def get_or_create_user(email: str, full_name: str, roles: list[str]) -> User:
            u = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if u is None:
                u = User(
                    organization_id=org.id,
                    email=email,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    full_name=full_name,
                    is_active=True,
                    email_verified=True,
                )
                db.add(u)
                db.flush()
                for r in roles:
                    db.add(UserRole(user_id=u.id, role_name=r, organization_id=org.id))
                bump("users")
                print(f"Created demo user: {u.email}")
            return u

        user = get_or_create_user(DEMO_ADMIN_EMAIL, "Apex Operations Director", ["ORG_ADMIN", "CAMO_MANAGER"])
        tech_user = get_or_create_user("technician@apexaero.demo", "Priya Nair", ["TECHNICIAN"])
        inspector_user = get_or_create_user("inspector@apexaero.demo", "Rahul Verma", ["QUALITY_INSPECTOR"])

        # ------------------------------------------------------------------
        # 3. Facility
        # ------------------------------------------------------------------
        facility = db.execute(
            select(Facility).where(Facility.organization_id == org.id, Facility.code == "APX-HGR1")
        ).scalar_one_or_none()
        if facility is None:
            facility = Facility(
                organization_id=org.id,
                code="APX-HGR1",
                name="Apex Main Hangar - Bengaluru",
                facility_type=FacilityType.HANGAR,
                status=FacilityStatus.ACTIVE,
                description="Primary MRO hangar and drone operations base.",
            )
            db.add(facility)
            db.flush()
            bump("facilities")

        # ------------------------------------------------------------------
        # 4. Fleet: Aircraft (Asset + Aircraft + AircraftDetail) and Drones (Asset)
        # ------------------------------------------------------------------
        def get_or_create_aircraft(reg: str, msn: str, ac_type: str, status: str, hours: float, cycles: int):
            asset = db.execute(
                select(Asset).where(Asset.organization_id == org.id, Asset.registration == reg)
            ).scalar_one_or_none()
            if asset is not None:
                ac = db.execute(select(Aircraft).where(Aircraft.asset_id == asset.id)).scalar_one_or_none()
                return asset, ac
            asset = Asset(
                organization_id=org.id,
                asset_type=AssetType.AIRCRAFT,
                manufacturer=ac_type.split(" ")[0],
                model=ac_type,
                serial_number=msn,
                registration=reg,
                status=status,
                acquired_at=now - timedelta(days=730),
                facility_id=facility.id,
            )
            db.add(asset)
            db.flush()
            ac = Aircraft(
                organization_id=org.id,
                registration=reg,
                msn=msn,
                aircraft_type=ac_type,
                status=status,
                asset_id=asset.id,
            )
            db.add(ac)
            db.flush()
            db.add(AircraftDetail(asset_id=asset.id, msn=msn, aircraft_type=ac_type))
            bump("aircraft")
            print(f"Created aircraft {reg} ({ac_type}) status={status}")
            return asset, ac

        aircraft_specs = [
            ("VT-APX", "ATR72-1001", "ATR 72-600", "ACTIVE", 1420.5, 980),
            ("VT-APY", "B738-2044", "Boeing 737-800", "ACTIVE", 8340.2, 5210),
            ("VT-APZ", "AT76-3390", "ATR 72-600", "GROUNDED", 5510.0, 4102),
            ("VT-APW", "E190-4471", "Embraer E190", "MAINTENANCE", 3021.8, 2290),
        ]
        aircraft_assets = []
        for spec in aircraft_specs:
            aircraft_assets.append(get_or_create_aircraft(*spec))

        def get_or_create_drone(reg: str, serial: str, model: str, status: str):
            asset = db.execute(
                select(Asset).where(Asset.organization_id == org.id, Asset.registration == reg)
            ).scalar_one_or_none()
            if asset is not None:
                return asset
            asset = Asset(
                organization_id=org.id,
                asset_type=AssetType.DRONE,
                manufacturer=model.split(" ")[0],
                model=model,
                serial_number=serial,
                registration=reg,
                status=status,
                acquired_at=now - timedelta(days=365),
                facility_id=facility.id,
            )
            db.add(asset)
            db.flush()
            bump("drones")
            print(f"Created drone {reg} ({model}) status={status}")
            return asset

        drone_specs = [
            ("APX-DRONE-01", "FC30-0981", "DJI FlyCart 30", "MAINTENANCE"),
            ("APX-DRONE-02", "M350-1187", "DJI Matrice 350 RTK", "ACTIVE"),
        ]
        drone_assets = [get_or_create_drone(*spec) for spec in drone_specs]

        ac1_asset, ac1 = aircraft_assets[0]  # VT-APX, ATR72, active
        ac2_asset, ac2 = aircraft_assets[1]  # VT-APY, 737, active
        ac3_asset, ac3 = aircraft_assets[2]  # VT-APZ, grounded
        ac4_asset, ac4 = aircraft_assets[3]  # VT-APW, maintenance
        drone1 = drone_assets[0]
        drone2 = drone_assets[1]

        # ------------------------------------------------------------------
        # 5. Components
        # ------------------------------------------------------------------
        def get_or_create_component(asset_id, name, ctype, serial):
            c = db.execute(
                select(Component).where(Component.asset_id == asset_id, Component.serial_number == serial)
            ).scalar_one_or_none()
            if c is None:
                c = Component(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_type=ctype,
                    name=name,
                    serial_number=serial,
                    status=ComponentStatus.INSTALLED,
                )
                db.add(c)
                db.flush()
                bump("components")
            return c

        engine1 = get_or_create_component(ac1_asset.id, "PW127M Engine #1", ComponentType.ENGINE, "PW127M-8891")
        motor1 = get_or_create_component(drone1.id, "Front-Left Propulsion Motor", ComponentType.MOTOR, "MOT-FL-4471")
        motor2 = get_or_create_component(drone2.id, "Rear-Right Propulsion Motor", ComponentType.MOTOR, "MOT-RR-2290")

        # ------------------------------------------------------------------
        # 6. Telemetry: freshness policy + ingestion logs + external mapping
        # ------------------------------------------------------------------
        policy = db.execute(
            select(TelemetryFreshnessPolicy).where(
                TelemetryFreshnessPolicy.organization_id == org.id,
                TelemetryFreshnessPolicy.asset_id.is_(None),
                TelemetryFreshnessPolicy.source_system.is_(None),
            )
        ).scalar_one_or_none()
        if policy is None:
            policy = TelemetryFreshnessPolicy(
                organization_id=org.id,
                asset_id=None,
                source_system=None,
                warning_threshold_days=2,
                critical_threshold_days=7,
                is_active=True,
                description="Apex Fleet Standard Freshness",
            )
            db.add(policy)
            db.flush()
            bump("telemetry_policies")

        def get_or_create_mapping(source_system, external_id, asset_id, device_model):
            m = db.execute(
                select(ExternalAssetMapping).where(
                    ExternalAssetMapping.organization_id == org.id,
                    ExternalAssetMapping.source_system == source_system,
                    ExternalAssetMapping.external_asset_id == external_id,
                )
            ).scalar_one_or_none()
            if m is None:
                m = ExternalAssetMapping(
                    organization_id=org.id,
                    source_system=source_system,
                    external_asset_id=external_id,
                    asset_id=asset_id,
                    device_model=device_model,
                    is_active=True,
                )
                db.add(m)
                db.flush()
                bump("telemetry_mappings")
            return m

        get_or_create_mapping("DJI_FLIGHTHUB", "FC30-0981", drone1.id, "DJI FlyCart 30")
        get_or_create_mapping("DJI_FLIGHTHUB", "M350-1187", drone2.id, "DJI Matrice 350 RTK")

        def get_or_create_event_log(source_system, source_event_id, asset_id, event_type, event_ts, status, readings=1):
            log = db.execute(
                select(TelemetryEventLog).where(
                    TelemetryEventLog.organization_id == org.id,
                    TelemetryEventLog.source_system == source_system,
                    TelemetryEventLog.source_event_id == source_event_id,
                )
            ).scalar_one_or_none()
            if log is None:
                log = TelemetryEventLog(
                    organization_id=org.id,
                    source_system=source_system,
                    source_event_id=source_event_id,
                    idempotency_key=f"{source_system}:{source_event_id}",
                    source_asset_id=source_event_id.split("-EVT-")[0],
                    asset_id=asset_id,
                    event_type=event_type,
                    event_timestamp=event_ts,
                    received_timestamp=event_ts + timedelta(seconds=4),
                    payload_hash=f"sha256_demo_{source_event_id.lower()}",
                    processing_status=status,
                    readings_count=readings,
                )
                db.add(log)
                db.flush()
                bump("telemetry_events")

        get_or_create_event_log("DJI_FLIGHTHUB", "FC30-0981-EVT-001", drone1.id, "TELEMETRY_PING", now - timedelta(hours=3), TelemetryProcessingStatus.PROCESSED)
        get_or_create_event_log("DJI_FLIGHTHUB", "M350-1187-EVT-001", drone2.id, "FLIGHT_COMPLETED", now - timedelta(minutes=45), TelemetryProcessingStatus.PROCESSED, readings=142)
        get_or_create_event_log("HUMS_DEVICE", "FC30-0981-EVT-STALE", drone1.id, "SENSOR_BURST", now - timedelta(days=11), TelemetryProcessingStatus.PROCESSED)
        get_or_create_event_log("GENERIC_TELEMETRY", "VT-APY-EVT-REJ", ac2_asset.id, "TELEMETRY_PING", now - timedelta(hours=6), TelemetryProcessingStatus.REJECTED)

        # ------------------------------------------------------------------
        # 7. HUMS: sensors, readings, features, baseline, exceedance,
        #    diagnostic candidate, degradation model, prognostic record
        # ------------------------------------------------------------------
        def get_or_create_sensor(asset_id, component_id, code, sensor_type, meas_type, unit, location):
            s = db.execute(
                select(HUMSSensor).where(
                    HUMSSensor.organization_id == org.id,
                    HUMSSensor.asset_id == asset_id,
                    HUMSSensor.sensor_code == code,
                )
            ).scalar_one_or_none()
            if s is None:
                s = HUMSSensor(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    sensor_code=code,
                    sensor_type=sensor_type,
                    measurement_type=meas_type,
                    unit=unit,
                    installation_location=location,
                    status="ACTIVE",
                    source="SIMULATED",
                )
                db.add(s)
                db.flush()
                bump("hums_sensors")
            return s

        sensor_drone1 = get_or_create_sensor(drone1.id, motor1.id, "MOT_1_VIB", "VIBRATION_ACCELEROMETER", "vibration", "g", "Front-Left Propulsion Motor Hub")
        sensor_drone2 = get_or_create_sensor(drone2.id, motor2.id, "MOT_2_VIB", "VIBRATION_ACCELEROMETER", "vibration", "g", "Rear-Right Propulsion Motor Hub")
        sensor_ac1 = get_or_create_sensor(ac1_asset.id, engine1.id, "ENG1_EGT", "TEMPERATURE_THERMOCOUPLE", "temperature", "degC", "Engine 1 Exhaust Gas Temp Probe")

        def get_or_create_reading(sensor, asset_id, ts, value, unit, quality="VALID"):
            r = db.execute(
                select(HUMSSensorReading).where(
                    HUMSSensorReading.organization_id == org.id,
                    HUMSSensorReading.sensor_id == sensor.id,
                    HUMSSensorReading.recorded_at == ts,
                )
            ).scalar_one_or_none()
            if r is None:
                r = HUMSSensorReading(
                    organization_id=org.id,
                    sensor_id=sensor.id,
                    asset_id=asset_id,
                    recorded_at=ts,
                    value=value,
                    unit=unit,
                    data_quality=quality,
                    source="SIMULATED",
                    ingestion_batch="demo-seed-1",
                )
                db.add(r)
                db.flush()
                bump("hums_readings")
            return r

        # Reading/feature/exceedance timestamps are wall-clock-relative
        # (`now`), so re-checking by exact timestamp would create duplicates
        # on every re-run. Instead, gate the whole synthetic-series block on
        # whether this demo-seed batch already exists for each sensor.
        existing_batch_m1 = db.execute(
            select(HUMSSensorReading.id).where(
                HUMSSensorReading.organization_id == org.id,
                HUMSSensorReading.sensor_id == sensor_drone1.id,
                HUMSSensorReading.ingestion_batch == "demo-seed-1",
            )
        ).first()
        existing_batch_m2 = db.execute(
            select(HUMSSensorReading.id).where(
                HUMSSensorReading.organization_id == org.id,
                HUMSSensorReading.sensor_id == sensor_drone2.id,
                HUMSSensorReading.ingestion_batch == "demo-seed-1",
            )
        ).first()
        existing_batch_ac1 = db.execute(
            select(HUMSSensorReading.id).where(
                HUMSSensorReading.organization_id == org.id,
                HUMSSensorReading.sensor_id == sensor_ac1.id,
                HUMSSensorReading.ingestion_batch == "demo-seed-1",
            )
        ).first()

        # Motor 1 (drone1): elevated vibration series -> exceedance/anomaly
        readings_m1 = []
        if existing_batch_m1 is None:
            for i in range(8):
                ts = now - timedelta(hours=2, minutes=i * 5)
                val = 0.40 + (i * 0.01)
                readings_m1.append(get_or_create_reading(sensor_drone1, drone1.id, ts, val, "g"))
        else:
            readings_m1 = list(
                db.execute(
                    select(HUMSSensorReading).where(
                        HUMSSensorReading.organization_id == org.id,
                        HUMSSensorReading.sensor_id == sensor_drone1.id,
                        HUMSSensorReading.ingestion_batch == "demo-seed-1",
                    )
                ).scalars()
            )

        # Motor 2 (drone2): healthy baseline series
        readings_m2 = []
        if existing_batch_m2 is None:
            for i in range(8):
                ts = now - timedelta(hours=5, minutes=i * 5)
                val = 0.16 + (i * 0.002)
                readings_m2.append(get_or_create_reading(sensor_drone2, drone2.id, ts, val, "g"))

        # Aircraft engine EGT series: nominal
        readings_ac1 = []
        if existing_batch_ac1 is None:
            for i in range(6):
                ts = now - timedelta(hours=10, minutes=i * 10)
                val = 620.0 + (i * 1.5)
                readings_ac1.append(get_or_create_reading(sensor_ac1, ac1_asset.id, ts, val, "degC"))

        def get_or_create_feature(sensor, asset_id, component_id, feature_type, value, unit, window_start, window_end, quality="GOOD"):
            f = db.execute(
                select(HUMSFeature).where(
                    HUMSFeature.organization_id == org.id,
                    HUMSFeature.sensor_id == sensor.id,
                    HUMSFeature.feature_type == feature_type,
                    HUMSFeature.calculation_method == "RMS over 40min sliding window",
                )
            ).scalars().first()
            if f is None:
                f = HUMSFeature(
                    organization_id=org.id,
                    sensor_id=sensor.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    measurement_type="vibration",
                    feature_type=feature_type,
                    value=value,
                    unit=unit,
                    window_start=window_start,
                    window_end=window_end,
                    sample_count=len(readings_m1),
                    quality=quality,
                    calculation_method="RMS over 40min sliding window",
                    processor_version="h2.1",
                    source_reading_ids=[str(r.id) for r in readings_m1] if sensor is sensor_drone1 else [],
                )
                db.add(f)
                db.flush()
                bump("hums_features")
            return f

        feat_m1_rms = get_or_create_feature(sensor_drone1, drone1.id, motor1.id, "rms", 0.44, "g", now - timedelta(hours=3), now - timedelta(hours=2))
        feat_m2_rms = get_or_create_feature(sensor_drone2, drone2.id, motor2.id, "rms", 0.17, "g", now - timedelta(hours=6), now - timedelta(hours=5))

        def get_or_create_baseline(sensor, asset_id, component_id, feature_type, mean, std, current=True):
            b = db.execute(
                select(HUMSBaseline).where(
                    HUMSBaseline.organization_id == org.id,
                    HUMSBaseline.sensor_id == sensor.id,
                    HUMSBaseline.feature_type == feature_type,
                    HUMSBaseline.is_current == current,
                )
            ).scalar_one_or_none()
            if b is None:
                b = HUMSBaseline(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    sensor_id=sensor.id,
                    feature_type=feature_type,
                    baseline_scope="ASSET",
                    sample_count=240,
                    mean=mean,
                    median=mean,
                    std_dev=std,
                    minimum=mean - 3 * std,
                    maximum=mean + 3 * std,
                    percentile_05=mean - 1.6 * std,
                    percentile_25=mean - 0.7 * std,
                    percentile_50=mean,
                    percentile_75=mean + 0.7 * std,
                    percentile_95=mean + 1.6 * std,
                    lower_bound=mean - 2.5 * std,
                    upper_bound=mean + 2.5 * std,
                    calculation_method="30-day rolling statistics",
                    source_window_start=now - timedelta(days=30),
                    source_window_end=now - timedelta(hours=3),
                    version=1,
                    is_current=True,
                    quality="VALID",
                    confidence="HIGH",
                )
                db.add(b)
                db.flush()
                bump("hums_baselines")
            return b

        baseline_m1 = get_or_create_baseline(sensor_drone1, drone1.id, motor1.id, "rms", 0.18, 0.03)
        baseline_m2 = get_or_create_baseline(sensor_drone2, drone2.id, motor2.id, "rms", 0.16, 0.02)

        def get_or_create_exceedance(sensor, asset_id, component_id, parameter, observed, threshold, severity, wstart, wend):
            e = db.execute(
                select(HUMSExceedance).where(
                    HUMSExceedance.organization_id == org.id,
                    HUMSExceedance.sensor_id == sensor.id,
                    HUMSExceedance.parameter == parameter,
                )
            ).scalars().first()
            if e is None:
                e = HUMSExceedance(
                    organization_id=org.id,
                    sensor_id=sensor.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    parameter=parameter,
                    observed_value=observed,
                    threshold_value=threshold,
                    severity=severity,
                    window_start=wstart,
                    window_end=wend,
                    contributing_reading_ids=[str(r.id) for r in readings_m1],
                )
                db.add(e)
                db.flush()
                bump("hums_exceedances")
            return e

        exceedance_m1 = get_or_create_exceedance(
            sensor_drone1, drone1.id, motor1.id, "vibration_rms", 0.44, 0.30, "HIGH",
            now - timedelta(hours=3), now - timedelta(hours=2),
        )

        def get_or_create_diagnostic(asset_id, component_id, fault_code, fault_name, domain, severity, score, sensor):
            d = db.execute(
                select(HUMSDiagnosticCandidate).where(
                    HUMSDiagnosticCandidate.organization_id == org.id,
                    HUMSDiagnosticCandidate.asset_id == asset_id,
                    HUMSDiagnosticCandidate.component_id == component_id,
                    HUMSDiagnosticCandidate.fault_code == fault_code,
                )
            ).scalar_one_or_none()
            if d is None:
                d = HUMSDiagnosticCandidate(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    sensor_ids=[str(sensor.id)],
                    fault_code=fault_code,
                    fault_name=fault_name,
                    fault_domain=domain,
                    diagnostic_method="rule_based_signature_matching",
                    rule_version="h4.1",
                    status="SUPPORTED",
                    severity=severity,
                    score=score,
                    confidence="MEDIUM",
                    primary_evidence=[{"type": "HUMSExceedance", "id": str(exceedance_m1.id), "label": "Vibration RMS exceedance"}],
                    supporting_evidence=[],
                    contradicting_evidence=[],
                    explanation=["RMS vibration trending above baseline for 3 consecutive windows", "Signature matches early bearing wear pattern"],
                    detected_at=now - timedelta(hours=2),
                )
                db.add(d)
                db.flush()
                bump("hums_diagnostics")
            return d

        diag_m1 = get_or_create_diagnostic(drone1.id, motor1.id, "BRG_WEAR_EARLY", "Early Bearing Wear - Propulsion Motor", "VIBRATION", "MEDIUM", 0.71, sensor_drone1)

        def get_or_create_degradation_model(sensor, asset_id, component_id, feature_type, ref_baseline):
            m = db.execute(
                select(HUMSDegradationModel).where(
                    HUMSDegradationModel.organization_id == org.id,
                    HUMSDegradationModel.sensor_id == sensor.id,
                    HUMSDegradationModel.feature_type == feature_type,
                    HUMSDegradationModel.is_current == True,  # noqa: E712
                )
            ).scalar_one_or_none()
            if m is None:
                m = HUMSDegradationModel(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    sensor_id=sensor.id,
                    feature_type=feature_type,
                    reference_baseline_id=ref_baseline.id,
                    model_type="LINEAR",
                    model_version="h5.1",
                    fit_slope=0.004,
                    fit_intercept=0.19,
                    fit_error=0.015,
                    r_squared=0.82,
                    sample_count=180,
                    usage_unit="FLIGHT_HOURS",
                    usage_span=184.2,
                    trajectory_state="DEGRADING",
                    quality="VALID",
                    confidence="MEDIUM",
                    version=1,
                    is_current=True,
                )
                db.add(m)
                db.flush()
                bump("hums_degradation_models")
            return m

        degmodel_m1 = get_or_create_degradation_model(sensor_drone1, drone1.id, motor1.id, "rms", baseline_m1)

        def get_or_create_prognostic(sensor, asset_id, component_id, feature_type, model, diag):
            p = db.execute(
                select(HUMSPrognosticRecord).where(
                    HUMSPrognosticRecord.organization_id == org.id,
                    HUMSPrognosticRecord.sensor_id == sensor.id,
                    HUMSPrognosticRecord.feature_type == feature_type,
                    HUMSPrognosticRecord.is_current == True,  # noqa: E712
                )
            ).scalar_one_or_none()
            if p is None:
                p = HUMSPrognosticRecord(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    sensor_id=sensor.id,
                    feature_type=feature_type,
                    degradation_model_id=model.id,
                    diagnostic_candidate_id=diag.id,
                    current_value=0.44,
                    threshold_value=0.60,
                    threshold_type="MAINTENANCE_THRESHOLD",
                    rul_estimate=68.0,
                    rul_lower=42.0,
                    rul_upper=95.0,
                    rul_unit="FLIGHT_HOURS",
                    extrapolation_distance=1.4,
                    confidence="MEDIUM",
                    quality="VALID",
                    status="AVAILABLE",
                    explanation=["Linear degradation trend extrapolated to maintenance threshold", "Estimate widens with extrapolation distance"],
                    observed_at=now - timedelta(hours=2),
                    calculated_at=now - timedelta(hours=2),
                    version=1,
                    is_current=True,
                )
                db.add(p)
                db.flush()
                bump("hums_prognostics")
            return p

        get_or_create_prognostic(sensor_drone1, drone1.id, motor1.id, "rms", degmodel_m1, diag_m1)

        # ------------------------------------------------------------------
        # 8. Evidence + Findings
        # ------------------------------------------------------------------
        def get_or_create_evidence(title, asset_id, aircraft_id, ev_type, status="ACCEPTED"):
            e = db.execute(
                select(Evidence).where(Evidence.organization_id == org.id, Evidence.title == title)
            ).scalar_one_or_none()
            if e is None:
                e = Evidence(
                    organization_id=org.id,
                    title=title,
                    evidence_type=ev_type,
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                    uploaded_by_user_id=user.id,
                    status=status,
                    captured_at=now - timedelta(hours=2),
                    verification_status="VERIFIED" if status == "ACCEPTED" else "UNVERIFIED",
                )
                db.add(e)
                db.flush()
                bump("evidence")
            return e

        ev_vib = get_or_create_evidence("Telemetry Vibration Exceedance Log - Motor 1", drone1.id, None, "TELEMETRY_LOG")
        ev_borescope = get_or_create_evidence("Engine 1 Borescope Inspection Photos", ac3_asset.id, ac3.id, "INSPECTION_RECORD")

        def get_or_create_finding(title, description, severity, status, asset_id, aircraft_id, evidence_id=None):
            f = db.execute(
                select(Finding).where(Finding.organization_id == org.id, Finding.title == title)
            ).scalar_one_or_none()
            if f is None:
                f = Finding(
                    organization_id=org.id,
                    title=title,
                    description=description,
                    severity=severity,
                    status=status,
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                    discovered_by_user_id=inspector_user.id,
                    responsible_user_id=tech_user.id,
                    discovered_at=now - timedelta(hours=2),
                )
                db.add(f)
                db.flush()
                bump("findings")
            return f

        finding_vib = get_or_create_finding(
            "Propulsion Motor 1 Bearing Vibration Exceedance",
            "Spectral analysis indicates elevated RMS acceleration (0.44g vs baseline 0.18g).",
            FindingSeverity.MAJOR, FindingStatus.OPEN, drone1.id, None,
        )
        finding_engine = get_or_create_finding(
            "Engine 1 Compressor Blade Erosion - Minor",
            "Borescope inspection found minor leading-edge erosion on stage-2 compressor blades, within limits but trending.",
            FindingSeverity.MINOR, FindingStatus.IN_PROGRESS, ac3_asset.id, ac3.id,
        )
        get_or_create_finding(
            "Recurring GPS Signal Dropout - Matrice 350",
            "Third occurrence in 30 days of transient GPS signal loss during high-density urban missions.",
            FindingSeverity.OBSERVATION, FindingStatus.CLOSED, drone2.id, None,
        )

        # ------------------------------------------------------------------
        # 9. Proactive Intelligence Signals (M7)
        # ------------------------------------------------------------------
        def get_or_create_signal(signal_key, signal_type, severity, priority, status, title, headline, asset_id, component_id=None, evidence=None):
            s = db.execute(
                select(ProactiveSignalRecord).where(
                    ProactiveSignalRecord.organization_id == org.id,
                    ProactiveSignalRecord.signal_key == signal_key,
                )
            ).scalar_one_or_none()
            if s is None:
                s = ProactiveSignalRecord(
                    organization_id=org.id,
                    signal_key=signal_key,
                    signal_type=signal_type,
                    severity=severity,
                    priority=priority,
                    status=status,
                    title=title,
                    headline=headline,
                    explanation_json=["Detected via automated cross-domain correlation of HUMS, compliance, and maintenance signals."],
                    asset_id=asset_id,
                    component_id=component_id,
                    detected_at=now - timedelta(hours=2),
                    evidence_json=evidence or [],
                )
                db.add(s)
                db.flush()
                bump("proactive_signals")
            return s

        get_or_create_signal(
            "hums_health:drone-01:motor1-vib", "HUMS_HEALTH", "CRITICAL", "HIGH", "OPEN",
            "Propulsion Degradation Risk: APX-DRONE-01",
            "Elevated high-frequency vibration indicates early mechanical wear in Motor 1 bearing assembly.",
            drone1.id, motor1.id,
            evidence=[{"type": "Finding", "id": str(finding_vib.id), "label": "Motor 1 vibration exceedance"}],
        )
        get_or_create_signal(
            "maintenance_threshold:vt-apz:engine1-erosion", "MAINTENANCE_THRESHOLD", "HIGH", "HIGH", "ACKNOWLEDGED",
            "Compressor Erosion Trending Toward Limit: VT-APZ Engine 1",
            "Blade erosion measurements trending toward maintenance threshold over the last 3 inspections.",
            ac3_asset.id, None,
            evidence=[{"type": "Finding", "id": str(finding_engine.id), "label": "Engine 1 erosion finding"}],
        )
        get_or_create_signal(
            "inspection_due:vt-apw:100hr", "INSPECTION_DUE", "MEDIUM", "MEDIUM", "OPEN",
            "100-Hour Inspection Due Within 5 Flight Hours: VT-APW",
            "VT-APW is approaching its 100-hour inspection interval based on current utilization rate.",
            ac4_asset.id, None,
        )
        get_or_create_signal(
            "evidence_gap:vt-apy:ad-2025-11", "EVIDENCE_GAP", "LOW", "LOW", "RESOLVED",
            "Evidence Gap Closed: AD 2025-11 Compliance Record",
            "Required evidence for AD 2025-11 compliance was missing for 6 days; evidence has since been accepted.",
            ac2_asset.id, None,
        )
        get_or_create_signal(
            "utilization_spike:apx-drone-02", "UTILIZATION_SPIKE", "MEDIUM", "MEDIUM", "IN_REVIEW",
            "Utilization Spike Detected: APX-DRONE-02",
            "Flight hours for APX-DRONE-02 increased 3.2x week-over-week, ahead of next scheduled maintenance check.",
            drone2.id, None,
        )

        # ------------------------------------------------------------------
        # 10. MRO Intelligence Candidates (H7)
        # ------------------------------------------------------------------
        def get_or_create_mro_candidate(dedup_key, candidate_type, status, priority, confidence, reason, asset_id, component_id=None, lineage=None):
            c = db.execute(
                select(MaintenanceIntelligenceCandidate).where(
                    MaintenanceIntelligenceCandidate.organization_id == org.id,
                    MaintenanceIntelligenceCandidate.dedup_key == dedup_key,
                )
            ).scalar_one_or_none()
            if c is None:
                c = MaintenanceIntelligenceCandidate(
                    organization_id=org.id,
                    asset_id=asset_id,
                    component_id=component_id,
                    candidate_type=candidate_type,
                    status=status,
                    priority=priority,
                    confidence=confidence,
                    reason=reason,
                    dedup_key=dedup_key,
                    source_lineage=lineage or [],
                    operational_impact="MODERATE",
                    data_freshness="FRESH",
                )
                db.add(c)
                db.flush()
                bump("mro_candidates")
            return c

        get_or_create_mro_candidate(
            "drone1:motor1:MAINTENANCE_ATTENTION:vib-diag",
            MROCandidateType.MAINTENANCE_ATTENTION, MROCandidateStatus.OPEN, MROCandidatePriority.HIGH, 0.78,
            "HUMS diagnostic candidate (early bearing wear, MEDIUM severity) converges with an open MAJOR finding and no scheduled maintenance action for this component.",
            drone1.id, motor1.id,
            lineage=[
                {"type": "HUMSDiagnosticCandidate", "id": str(diag_m1.id), "label": "Early bearing wear diagnostic"},
                {"type": "Finding", "id": str(finding_vib.id), "label": "Motor 1 vibration exceedance finding"},
            ],
        )
        get_or_create_mro_candidate(
            "ac3:engine1:COMPLIANCE_REVIEW:erosion-ad",
            MROCandidateType.COMPLIANCE_REVIEW, MROCandidateStatus.UNDER_REVIEW, MROCandidatePriority.MEDIUM, 0.64,
            "Compressor erosion finding trending toward limit overlaps with an upcoming AD compliance window on VT-APZ.",
            ac3_asset.id, engine1.id,
            lineage=[{"type": "Finding", "id": str(finding_engine.id), "label": "Engine 1 erosion finding"}],
        )
        get_or_create_mro_candidate(
            "vt-apw:INSPECTION_REVIEW:100hr-overlap",
            MROCandidateType.INSPECTION_REVIEW, MROCandidateStatus.OPEN, MROCandidatePriority.MEDIUM, 0.55,
            "Upcoming 100-hour inspection overlaps with an open corrective work order window, review scheduling conflict.",
            ac4_asset.id, None,
        )

        # ------------------------------------------------------------------
        # 11. Compliance: regulatory requirements + obligations + assessments
        # ------------------------------------------------------------------
        def get_or_create_requirement(number, authority, title, description):
            r = db.execute(
                select(RegulatoryRequirement).where(RegulatoryRequirement.requirement_number == number)
            ).scalar_one_or_none()
            if r is None:
                r = RegulatoryRequirement(
                    organization_id=org.id,
                    authority=authority,
                    requirement_number=number,
                    title=title,
                    description=description,
                    effective_date=today - timedelta(days=400),
                )
                db.add(r)
                db.flush()
                bump("requirements")
            return r

        req_ad = get_or_create_requirement("AD-2025-11-07", RegulatoryAuthority.FAA, "AD 2025-11-07 Fuel Pump Inspection", "Mandatory recurring inspection of fuel pump housing for stress-corrosion cracking.")
        req_100hr = get_or_create_requirement("MPD-100HR-AIRFRAME", RegulatoryAuthority.DGCA, "100-Hour Airframe Inspection", "Recurring 100 flight-hour airframe inspection per approved maintenance program.")
        req_drone_reg = get_or_create_requirement("DGCA-RPAS-CAR-XB", RegulatoryAuthority.DGCA, "RPAS Airworthiness Renewal", "Annual airworthiness renewal for remotely piloted aircraft systems above 25kg MTOW.")

        def get_or_create_obligation(requirement, asset_id, aircraft_id, status, due_date, priority="MEDIUM"):
            o = db.execute(
                select(ComplianceObligation).where(
                    ComplianceObligation.organization_id == org.id,
                    ComplianceObligation.requirement_id == requirement.id,
                    ComplianceObligation.asset_id == asset_id,
                )
            ).scalar_one_or_none()
            if o is None:
                o = ComplianceObligation(
                    organization_id=org.id,
                    requirement_id=requirement.id,
                    asset_id=asset_id,
                    aircraft_id=aircraft_id,
                    status=status,
                    priority=priority,
                    due_date=due_date,
                    responsible_role="CAMO_MANAGER",
                    assigned_user_id=user.id,
                    required_action="Perform inspection and submit evidence for review.",
                )
                db.add(o)
                db.flush()
                bump("compliance_obligations")
            return o

        get_or_create_obligation(req_ad, ac2_asset.id, ac2.id, ComplianceState.OVERDUE.value, today - timedelta(days=9), priority="HIGH")
        get_or_create_obligation(req_100hr, ac4_asset.id, ac4.id, ComplianceState.DUE.value, today + timedelta(days=5))
        get_or_create_obligation(req_100hr, ac1_asset.id, ac1.id, ComplianceState.COMPLIANT.value, today + timedelta(days=62))
        get_or_create_obligation(req_drone_reg, drone2.id, None, ComplianceState.PENDING.value, today + timedelta(days=120))

        # ------------------------------------------------------------------
        # 12. Inspection + Maintenance requirements
        # ------------------------------------------------------------------
        insp_req = db.execute(
            select(InspectionRequirement).where(
                InspectionRequirement.organization_id == org.id,
                InspectionRequirement.regulatory_requirement_id == req_ad.id,
            )
        ).scalar_one_or_none()
        if insp_req is None:
            insp_req = InspectionRequirement(
                organization_id=org.id,
                regulatory_requirement_id=req_ad.id,
                required=True,
                status=InspectionRequirementStatus.PENDING.value,
            )
            db.add(insp_req)
            db.flush()
            bump("inspection_requirements")

        maint_req = db.execute(
            select(MaintenanceRequirement).where(
                MaintenanceRequirement.organization_id == org.id,
                MaintenanceRequirement.task_reference == "MPD-05-10-01",
            )
        ).scalar_one_or_none()
        if maint_req is None:
            maint_req = MaintenanceRequirement(
                organization_id=org.id,
                description="100-hour airframe structural inspection",
                ata_chapter="05-10",
                interval_type=MaintenanceIntervalType.FLIGHT_HOURS,
                fh_interval=100,
                task_reference="MPD-05-10-01",
            )
            db.add(maint_req)
            db.flush()
            bump("maintenance_requirements")

        # ------------------------------------------------------------------
        # 13. Work Orders + Tasks
        # ------------------------------------------------------------------
        def get_or_create_work_order(number, title, wo_type, status, asset_id, aircraft_id, priority="NORMAL"):
            wo = db.execute(
                select(WorkOrder).where(WorkOrder.organization_id == org.id, WorkOrder.work_order_number == number)
            ).scalar_one_or_none()
            if wo is None:
                wo = WorkOrder(
                    organization_id=org.id,
                    aircraft_id=aircraft_id,
                    asset_id=asset_id,
                    work_order_number=number,
                    title=title,
                    work_order_type=wo_type,
                    status=status,
                    priority=priority,
                    assigned_to_user_id=tech_user.id,
                    created_by_user_id=user.id,
                    scheduled_start=now - timedelta(days=1),
                    scheduled_end=now + timedelta(days=2),
                )
                db.add(wo)
                db.flush()
                bump("work_orders")
            return wo

        wo1 = get_or_create_work_order("WO-2026-0001", "Motor 1 Bearing Inspection & Replacement", WorkOrderType.CORRECTIVE, WorkOrderStatus.IN_PROGRESS, drone1.id, None, priority="HIGH")
        wo2 = get_or_create_work_order("WO-2026-0002", "VT-APZ Engine 1 Borescope & Erosion Assessment", WorkOrderType.INSPECTION, WorkOrderStatus.OPEN, ac3_asset.id, ac3.id, priority="HIGH")
        wo3 = get_or_create_work_order("WO-2026-0003", "VT-APX 100-Hour Airframe Inspection", WorkOrderType.SCHEDULED, WorkOrderStatus.COMPLETED, ac1_asset.id, ac1.id)
        wo4 = get_or_create_work_order("WO-2026-0004", "VT-APY AD 2025-11-07 Fuel Pump Inspection", WorkOrderType.COMPLIANCE, WorkOrderStatus.PLANNED, ac2_asset.id, ac2.id, priority="HIGH")

        def get_or_create_task(wo, number, title, state, hours=None):
            t = db.execute(
                select(Task).where(Task.organization_id == org.id, Task.work_order_id == wo.id, Task.task_number == number)
            ).scalar_one_or_none()
            if t is None:
                t = Task(
                    organization_id=org.id,
                    work_order_id=wo.id,
                    task_number=number,
                    title=title,
                    description=title,
                    execution_state=state,
                    assigned_technician_user_id=tech_user.id,
                    evidence_required=True,
                    estimated_hours=hours,
                )
                db.add(t)
                db.flush()
                bump("tasks")
            return t

        get_or_create_task(wo1, "T-1", "Remove motor housing and inspect bearing race", TaskExecutionState.COMPLETED, 1.5)
        get_or_create_task(wo1, "T-2", "Replace bearing and reassemble motor", TaskExecutionState.IN_PROGRESS, 2.0)
        get_or_create_task(wo2, "T-1", "Borescope inspection of stage-2 compressor blades", TaskExecutionState.PENDING, 1.0)
        get_or_create_task(wo3, "T-1", "Fuselage skin panel inspection", TaskExecutionState.COMPLETED, 3.0)
        get_or_create_task(wo3, "T-2", "Control surface rigging check", TaskExecutionState.COMPLETED, 2.0)
        get_or_create_task(wo4, "T-1", "Fuel pump housing NDT inspection", TaskExecutionState.PENDING, 2.5)

        # ------------------------------------------------------------------
        # 14. Parts / Vendor / Purchase Order / Inventory
        # ------------------------------------------------------------------
        vendor = db.execute(
            select(Vendor).where(Vendor.organization_id == org.id, Vendor.name == "SkyParts Aerospace Supply")
        ).scalar_one_or_none()
        if vendor is None:
            vendor = Vendor(
                organization_id=org.id,
                name="SkyParts Aerospace Supply",
                contact_email="sales@skyparts-aero.example",
                location="Singapore",
                certifications="AS9120, ISO 9001",
                approved=True,
                reliability_score=92,
            )
            db.add(vendor)
            db.flush()
            bump("vendors")

        def get_or_create_part(part_number, description, manufacturer, qty_on_hand, qty_reserved, status):
            p = db.execute(
                select(Part).where(Part.organization_id == org.id, Part.part_number == part_number)
            ).scalar_one_or_none()
            if p is None:
                p = Part(
                    organization_id=org.id,
                    part_number=part_number,
                    description=description,
                    manufacturer=manufacturer,
                    condition="NEW",
                    serviceability_status=status,
                    quantity_on_hand=qty_on_hand,
                    quantity_reserved=qty_reserved,
                )
                db.add(p)
                db.flush()
                bump("parts")
            return p

        part_bearing = get_or_create_part("BRG-6205-2RS", "Sealed ball bearing, propulsion motor", "SKF", 12, 2, PartServiceabilityStatus.SERVICEABLE)
        part_fuelpump = get_or_create_part("FP-737-9921", "Fuel pump housing assembly", "Boeing", 2, 1, PartServiceabilityStatus.SERVICEABLE)
        get_or_create_part("PROP-M350-CW", "Propeller blade, clockwise, carbon fiber", "DJI", 6, 0, PartServiceabilityStatus.SERVICEABLE)

        po = db.execute(
            select(PurchaseOrder).where(PurchaseOrder.organization_id == org.id, PurchaseOrder.po_number == "PO-2026-0001")
        ).scalar_one_or_none()
        if po is None:
            po = PurchaseOrder(
                organization_id=org.id,
                po_number="PO-2026-0001",
                vendor_id=vendor.id,
                asset_id=ac2_asset.id,
                aircraft_id=ac2.id,
                status=PurchaseOrderStatus.SENT,
                currency="USD",
                subtotal_cents=485000,
                tax_cents=38800,
                shipping_cents=12000,
                total_cents=535800,
                required_by=today + timedelta(days=14),
                expected_delivery=today + timedelta(days=10),
                created_by_user_id=user.id,
                approved_by_user_id=user.id,
            )
            db.add(po)
            db.flush()
            db.add(PurchaseOrderLine(
                organization_id=org.id,
                purchase_order_id=po.id,
                part_number="FP-737-9921",
                description="Fuel pump housing assembly",
                quantity=1,
                unit_price_cents=485000,
                received_quantity=0,
            ))
            db.flush()
            bump("purchase_orders")

        inv_txn = db.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.organization_id == org.id,
                InventoryTransaction.part_id == part_bearing.id,
                InventoryTransaction.reference_type == "WORK_ORDER",
                InventoryTransaction.reference_id == wo1.id,
            )
        ).scalar_one_or_none()
        if inv_txn is None:
            db.add(InventoryTransaction(
                organization_id=org.id,
                part_id=part_bearing.id,
                transaction_type=InventoryTransactionType.RESERVE,
                on_hand_delta=0,
                reserved_delta=1,
                reference_type="WORK_ORDER",
                reference_id=wo1.id,
                notes="Reserved for Motor 1 bearing replacement",
                actor_user_id=tech_user.id,
            ))
            db.flush()
            bump("inventory_transactions")

        # ------------------------------------------------------------------
        # 15. AOG events + blockers
        # ------------------------------------------------------------------
        aog = db.execute(
            select(AogEvent).where(AogEvent.organization_id == org.id, AogEvent.aircraft_id == ac3.id, AogEvent.status == AogEventStatus.IN_RECOVERY)
        ).scalar_one_or_none()
        if aog is None:
            aog = AogEvent(
                organization_id=org.id,
                aircraft_id=ac3.id,
                asset_id=ac3_asset.id,
                work_order_id=wo2.id,
                status=AogEventStatus.IN_RECOVERY,
                severity=AogSeverity.CRITICAL,
                root_cause="Compressor blade erosion exceeding borescope inspection acceptance criteria pending disposition.",
                declared_by_user_id=inspector_user.id,
                owner_user_id=user.id,
                recovery_notes="Awaiting engineering disposition on blade erosion measurements before return-to-service.",
            )
            db.add(aog)
            db.flush()
            bump("aog_events")
            db.add(AogBlocker(
                organization_id=org.id,
                aog_event_id=aog.id,
                blocker_type=AogBlockerType.EVIDENCE,
                description="Engineering disposition report not yet submitted.",
                source_reference=str(finding_engine.id),
                resolved=False,
            ))
            db.add(AogBlocker(
                organization_id=org.id,
                aog_event_id=aog.id,
                blocker_type=AogBlockerType.MATERIAL,
                description="Replacement compressor blade set on order, awaiting vendor confirmation.",
                resolved=False,
            ))
            db.flush()
            bump("aog_blockers", 2)

        # ------------------------------------------------------------------
        # 16. Deferred items (MEL)
        # ------------------------------------------------------------------
        deferred = db.execute(
            select(DeferredItem).where(DeferredItem.organization_id == org.id, DeferredItem.aircraft_id == ac2.id, DeferredItem.mel_reference == "MEL-34-11-01")
        ).scalar_one_or_none()
        if deferred is None:
            deferred = DeferredItem(
                organization_id=org.id,
                aircraft_id=ac2.id,
                asset_id=ac2_asset.id,
                work_order_id=None,
                mel_reference="MEL-34-11-01",
                category=DeferredItemCategory.C,
                description="Weather radar tilt indicator inoperative.",
                opened_at=today - timedelta(days=6),
                due_at=today + timedelta(days=4),
                status=DeferredItemStatus.OPEN,
                deferral_basis=DeferredItemBasis.MEL,
                operational_limitations="Crew to rely on ATC weather advisories; avoid known convective activity areas.",
                required_actions="Replace tilt indicator within Category C interval (10 days).",
                approval_required=True,
            )
            db.add(deferred)
            db.flush()
            bump("deferred_items")

        # ------------------------------------------------------------------
        # 17. Technician qualifications
        # ------------------------------------------------------------------
        def get_or_create_qual(u, aircraft_type, qual_type):
            q = db.execute(
                select(TechnicianQualification).where(
                    TechnicianQualification.organization_id == org.id,
                    TechnicianQualification.user_id == u.id,
                    TechnicianQualification.aircraft_type == aircraft_type,
                    TechnicianQualification.qualification_type == qual_type,
                )
            ).scalar_one_or_none()
            if q is None:
                q = TechnicianQualification(
                    organization_id=org.id,
                    user_id=u.id,
                    aircraft_type=aircraft_type,
                    qualification_type=qual_type,
                    granted_at=now - timedelta(days=200),
                    expires_at=now + timedelta(days=365),
                    granted_by_user_id=user.id,
                )
                db.add(q)
                db.flush()
                bump("technician_qualifications")

        get_or_create_qual(tech_user, "ATR 72-600", "A&P")
        get_or_create_qual(tech_user, "Boeing 737-800", "A&P")
        get_or_create_qual(inspector_user, "ATR 72-600", "RII_INSPECTOR")

        # ------------------------------------------------------------------
        # 18. SSO configuration (placeholder demo values only — inactive,
        #     no live IdP secret; enough to populate the settings screen)
        # ------------------------------------------------------------------
        sso = db.execute(
            select(SSOConfiguration).where(SSOConfiguration.organization_id == org.id)
        ).scalar_one_or_none()
        if sso is None:
            sso = SSOConfiguration(
                organization_id=org.id,
                provider_type=SSOProviderType.ENTRA_ID,
                issuer_url="https://login.microsoftonline.com/apex-demo-tenant/v2.0",
                client_id="00000000-0000-0000-0000-000000000000",
                client_secret_hash=None,
                tenant_id="apex-demo-tenant",
                is_active=False,
                enforce_sso=False,
                default_role="VIEWER",
                domain_hint="apexaero.demo",
                role_mappings={"Aviation-Admins": "ORG_ADMIN", "CAMO-Team": "CAMO_MANAGER"},
            )
            db.add(sso)
            db.flush()
            bump("sso_configs")

        # ------------------------------------------------------------------
        # 19. Plan / Subscription / Entitlements
        # ------------------------------------------------------------------
        # Apex operates both fixed-wing aircraft and drones, so it is subscribed to the catalog Enterprise plan of
        # each suite (seed_product_catalog.py must have run first). Plans/features are shared catalog data and are
        # never created or edited here -- per-org differences go through TenantFeatureOverride below.
        for suite_code, plan_code in (("AIRCRAFT", "AIRCRAFT_ENTERPRISE"), ("DRONE_UAV", "DRONE_ENTERPRISE")):
            suite = db.execute(select(ProductSuite).where(ProductSuite.code == suite_code)).scalar_one_or_none()
            plan = db.execute(
                select(Plan).where(Plan.code == plan_code, Plan.suite_id == (suite.id if suite else None))
            ).scalar_one_or_none()
            if suite is None or plan is None:
                raise SystemExit(
                    f"Catalog plan {plan_code} (suite {suite_code}) not found -- run scripts/seed_product_catalog.py first."
                )
            sub = db.execute(
                select(Subscription).where(
                    Subscription.organization_id == org.id,
                    Subscription.suite_id == suite.id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
            ).scalar_one_or_none()
            if sub is None:
                db.add(Subscription(
                    organization_id=org.id,
                    plan_id=plan.id,
                    suite_id=suite.id,
                    status=SubscriptionStatus.ACTIVE,
                    starts_at=now - timedelta(days=180),
                    ends_at=None,
                ))
                db.flush()
                bump("subscriptions")

        override = db.execute(
            select(TenantFeatureOverride).where(
                TenantFeatureOverride.organization_id == org.id,
                TenantFeatureOverride.feature_key == "DIGITAL_TWIN_BETA",
            )
        ).scalar_one_or_none()
        if override is None:
            db.add(TenantFeatureOverride(
                organization_id=org.id,
                feature_key="DIGITAL_TWIN_BETA",
                enabled=True,
                reason="Early access grant for client demo of Digital Twin module.",
                created_by_user_id=user.id,
                expires_at=now + timedelta(days=90),
            ))
            db.flush()
            bump("feature_overrides")

        usage_limit = db.execute(
            select(TenantUsageLimit).where(
                TenantUsageLimit.organization_id == org.id,
                TenantUsageLimit.feature_key == "LISA",
                TenantUsageLimit.limit_key == "monthly_queries",
            )
        ).scalar_one_or_none()
        if usage_limit is None:
            db.add(TenantUsageLimit(
                organization_id=org.id,
                feature_key="LISA",
                limit_key="monthly_queries",
                limit_value=5000,
                is_unlimited=False,
            ))
            db.flush()
            bump("usage_limits")

        # ------------------------------------------------------------------
        # 20. Edge Hardware (M14/M15): registered edge devices/gateways
        # ------------------------------------------------------------------
        def get_or_create_edge_device(device_id, gateway_id, asset_id, device_type, firmware, status, heartbeat_ago):
            d = db.execute(
                select(EdgeDevice).where(
                    EdgeDevice.organization_id == org.id,
                    EdgeDevice.device_id == device_id,
                )
            ).scalar_one_or_none()
            if d is None:
                d = EdgeDevice(
                    organization_id=org.id,
                    device_id=device_id,
                    gateway_id=gateway_id,
                    asset_id=asset_id,
                    device_type=device_type,
                    firmware_version=firmware,
                    status=status,
                    last_heartbeat_at=now - heartbeat_ago,
                    metadata_json={"install_site": "APX-HGR1"},
                )
                db.add(d)
                db.flush()
                bump("edge_devices")
            return d

        get_or_create_edge_device("EDGE-GW-001", "GW-APX-HGR1", drone1.id, "SENSOR_GATEWAY", "2.4.1", "ACTIVE", timedelta(minutes=8))
        get_or_create_edge_device("EDGE-SN-MOT1", None, drone1.id, "SENSOR_NODE", "1.2.0", "ACTIVE", timedelta(minutes=3))
        get_or_create_edge_device("EDGE-SN-VTAPZ-EGT", None, ac3_asset.id, "SENSOR_NODE", "1.1.7", "OFFLINE", timedelta(days=12))

        # ------------------------------------------------------------------
        # 21. Hypercare: operational incidents (production observability)
        # ------------------------------------------------------------------
        def get_or_create_incident(service_name, title, description, severity, status, asset_id=None):
            inc = db.execute(
                select(OperationalIncident).where(
                    OperationalIncident.organization_id == org.id,
                    OperationalIncident.title == title,
                )
            ).scalar_one_or_none()
            if inc is None:
                inc = OperationalIncident(
                    organization_id=org.id,
                    severity=severity,
                    service_name=service_name,
                    title=title,
                    description=description,
                    status=status,
                    asset_id=asset_id,
                    first_detected_at=now - timedelta(days=2),
                    resolved_at=(now - timedelta(hours=20)) if status == IncidentStatus.RESOLVED else None,
                    details={"detected_via": "automated_monitor"},
                )
                db.add(inc)
                db.flush()
                bump("operational_incidents")
            return inc

        get_or_create_incident("TELEMETRY", "Telemetry ingestion lag spike - DJI FlightHub feed", "Ingestion latency briefly exceeded 5 minutes for the DJI FlightHub source during a provider-side incident.", IncidentSeverity.P2, IncidentStatus.RESOLVED, drone1.id)
        get_or_create_incident("HUMS", "HUMS feature computation backlog", "Feature extraction queue backed up for ~20 minutes following a burst of sensor bursts; cleared automatically.", IncidentSeverity.P3, IncidentStatus.ACKNOWLEDGED, drone1.id)

        # ------------------------------------------------------------------
        # 22. Missions (drone operations)
        # ------------------------------------------------------------------
        def get_or_create_mission(asset_id, purpose, status, area, planned_start, planned_end, authorized=False):
            m = db.execute(
                select(Mission).where(
                    Mission.organization_id == org.id,
                    Mission.asset_id == asset_id,
                    Mission.purpose == purpose,
                )
            ).scalar_one_or_none()
            if m is None:
                m = Mission(
                    organization_id=org.id,
                    asset_id=asset_id,
                    pilot_user_id=tech_user.id,
                    status=status,
                    purpose=purpose,
                    operating_area=area,
                    planned_start=planned_start,
                    planned_end=planned_end,
                    authorized_at=(now - timedelta(hours=6)) if authorized else None,
                    authorized_by_user_id=user.id if authorized else None,
                )
                db.add(m)
                db.flush()
                bump("missions")
            return m

        get_or_create_mission(drone2.id, "Powerline corridor inspection - Sector 4", MissionStatus.COMPLETED, "Bengaluru North Grid Corridor", now - timedelta(days=1, hours=2), now - timedelta(days=1), authorized=True)
        get_or_create_mission(drone2.id, "Last-mile medical payload delivery trial", MissionStatus.IN_PROGRESS, "Whitefield Urban Test Zone", now - timedelta(hours=1), now + timedelta(hours=1), authorized=True)
        get_or_create_mission(drone1.id, "Post-maintenance functional check flight", MissionStatus.PLANNED, "Apex Hangar Test Pad", now + timedelta(days=1), now + timedelta(days=1, hours=1))

        # ------------------------------------------------------------------
        # 23. Data import job (bulk onboarding pipeline)
        # ------------------------------------------------------------------
        import_job = db.execute(
            select(ImportJob).where(
                ImportJob.organization_id == org.id,
                ImportJob.filename == "apex_fleet_onboarding_batch1.xlsx",
            )
        ).scalar_one_or_none()
        if import_job is None:
            import_job = ImportJob(
                organization_id=org.id,
                domain=ImportDomain.AIRCRAFT,
                filename="apex_fleet_onboarding_batch1.xlsx",
                file_hash="demo_hash_fleet_batch1",
                status=ImportJobStatus.COMPLETED,
                created_by_user_id=user.id,
                sheet_names=["Fleet"],
                selected_sheet="Fleet",
                column_mapping={"registration": "Registration", "msn": "MSN", "aircraft_type": "Type"},
                rows_total=4,
                rows_valid=4,
                rows_invalid=0,
                rows_created=4,
                rows_updated=0,
                rows_failed=0,
                row_results=[
                    {"row_number": 1, "status": "VALID", "errors": [], "warnings": [], "data": {"registration": "VT-APX"}, "match_action": "CREATE_ASSET"},
                    {"row_number": 2, "status": "VALID", "errors": [], "warnings": [], "data": {"registration": "VT-APY"}, "match_action": "CREATE_ASSET"},
                ],
                completed_at=now - timedelta(days=180),
            )
            db.add(import_job)
            db.flush()
            bump("import_jobs")

        # ------------------------------------------------------------------
        # 24. Part requirements (work order <-> part linkage)
        # ------------------------------------------------------------------
        def get_or_create_part_requirement(wo, task, part, qty, status, priority="NORMAL"):
            pr = db.execute(
                select(PartRequirement).where(
                    PartRequirement.organization_id == org.id,
                    PartRequirement.work_order_id == wo.id,
                    PartRequirement.part_id == part.id,
                )
            ).scalar_one_or_none()
            if pr is None:
                pr = PartRequirement(
                    organization_id=org.id,
                    work_order_id=wo.id,
                    task_id=task.id if task else None,
                    part_id=part.id,
                    required_quantity=qty,
                    fulfilled_quantity=qty if status == PartRequirementStatus.FULFILLED else 0,
                    status=status,
                    priority=priority,
                    created_by_user_id=user.id,
                )
                db.add(pr)
                db.flush()
                bump("part_requirements")
            return pr

        get_or_create_part_requirement(wo1, None, part_bearing, 1, PartRequirementStatus.RESERVED, priority="HIGH")
        get_or_create_part_requirement(wo4, None, part_fuelpump, 1, PartRequirementStatus.ORDERED, priority="HIGH")

        # ------------------------------------------------------------------
        # 25. Vendor part availability (procurement scoring source data)
        # ------------------------------------------------------------------
        def get_or_create_vendor_availability(vendor_id, part_id, status, qty, lead_days, price_cents, aog_ok, cert_status):
            v = db.execute(
                select(VendorPartAvailability).where(
                    VendorPartAvailability.organization_id == org.id,
                    VendorPartAvailability.vendor_id == vendor_id,
                    VendorPartAvailability.part_id == part_id,
                )
            ).scalar_one_or_none()
            if v is None:
                v = VendorPartAvailability(
                    organization_id=org.id,
                    vendor_id=vendor_id,
                    part_id=part_id,
                    availability_status=status,
                    quantity_available=qty,
                    lead_time_days=lead_days,
                    unit_price_cents=price_cents,
                    currency="USD",
                    aog_availability=aog_ok,
                    certification_status=cert_status,
                )
                db.add(v)
                db.flush()
                bump("vendor_part_availabilities")

        get_or_create_vendor_availability(vendor.id, part_bearing.id, PartAvailabilityStatus.IN_STOCK, 40, 3, 8600, True, PartCertificationStatus.VERIFIED)
        get_or_create_vendor_availability(vendor.id, part_fuelpump.id, PartAvailabilityStatus.LIMITED, 2, 14, 485000, False, PartCertificationStatus.VERIFIED)

        # ------------------------------------------------------------------
        # 26. LISA conversation contexts (one active context per user)
        # ------------------------------------------------------------------
        def get_or_create_lisa_context(u, aircraft_id, wo, questions):
            c = db.execute(
                select(LisaConversationContext).where(
                    LisaConversationContext.organization_id == org.id,
                    LisaConversationContext.user_id == u.id,
                )
            ).scalar_one_or_none()
            if c is None:
                c = LisaConversationContext(
                    organization_id=org.id,
                    user_id=u.id,
                    current_aircraft_id=aircraft_id,
                    current_work_order_id=wo.id if wo else None,
                    recent_entities=(
                        '[{"entity_type": "aircraft", "entity_id": "%s", "display": "%s"}]'
                        % (aircraft_id, "VT-APZ" if aircraft_id == ac3.id else "asset")
                    ) if aircraft_id else "[]",
                    previous_question=questions[-1] if questions else None,
                    recent_questions=str(questions).replace("'", '"'),
                    context_version=1,
                    last_activity_at=now - timedelta(minutes=15),
                )
                db.add(c)
                db.flush()
                bump("lisa_contexts")

        get_or_create_lisa_context(
            user, ac3.id, wo2,
            ["What's the status of VT-APZ's engine 1 finding?", "Show me the open AOG event blockers."],
        )
        get_or_create_lisa_context(
            tech_user, None, wo1,
            ["Is the bearing for Motor 1 in stock?"],
        )

        # ------------------------------------------------------------------
        # 27. Applicability rule + condition tree + evaluation
        # ------------------------------------------------------------------
        applicability_rule = db.execute(
            select(ApplicabilityRule).where(
                ApplicabilityRule.organization_id == org.id,
                ApplicabilityRule.rule_code == "AD-2025-11-07-APPLICABILITY",
            )
        ).scalar_one_or_none()
        if applicability_rule is None:
            applicability_rule = ApplicabilityRule(
                organization_id=org.id,
                rule_code="AD-2025-11-07-APPLICABILITY",
                title="AD 2025-11-07 Applicability - Fuel Pump Variant Check",
                description="Applies to Boeing 737-800 aircraft with the affected fuel pump part variant installed.",
                regulatory_requirement_id=req_ad.id,
                is_active=True,
            )
            db.add(applicability_rule)
            db.flush()
            bump("applicability_rules")

            cond_variant = ApplicabilityCondition(
                organization_id=org.id,
                rule_id=applicability_rule.id,
                parent_condition_id=None,
                condition_type=ConditionType.AIRCRAFT_VARIANT,
                label="Aircraft variant is Boeing 737-800",
                parameters={"variant": "Boeing 737-800"},
                sequence=1,
            )
            db.add(cond_variant)
            db.flush()
            applicability_rule.root_condition_id = cond_variant.id
            db.flush()
            bump("applicability_conditions")

            evaluation = ApplicabilityEvaluation(
                organization_id=org.id,
                rule_id=applicability_rule.id,
                aircraft_id=ac2.id,
                asset_id=ac2_asset.id,
                evaluated_by_user_id=user.id,
                system_result=EvaluationResult.APPLICABLE,
                configuration_snapshot={"aircraft_type": "Boeing 737-800", "registration": "VT-APY"},
                reasoning_trace={"root": {"condition": "AIRCRAFT_VARIANT", "result": "TRUE", "detail": "Boeing 737-800 matches rule variant"}},
                notes="Confirmed applicable based on current fleet configuration data.",
            )
            db.add(evaluation)
            db.flush()
            bump("applicability_evaluations")

        # ------------------------------------------------------------------
        # 28. Assessment + snapshot + children (MRO impact intelligence)
        # ------------------------------------------------------------------
        assessment = db.execute(
            select(Assessment).where(
                Assessment.organization_id == org.id,
                Assessment.name == "Apex Fleet Operational Readiness Assessment",
            )
        ).scalar_one_or_none()
        if assessment is None:
            assessment = Assessment(
                organization_id=org.id,
                name="Apex Fleet Operational Readiness Assessment",
                description="Fleet-wide operational readiness and risk assessment across compliance, maintenance, and HUMS domains.",
                scope_type=AssessmentScopeType.FLEET,
                scope_id=None,
                status=AssessmentStatus.COMPLETE,
                created_by_user_id=user.id,
            )
            db.add(assessment)
            db.flush()
            bump("assessments")

            snapshot = AssessmentSnapshot(
                organization_id=org.id,
                assessment_id=assessment.id,
                version=1,
                overall_score=72.5,
                maturity_band="DEVELOPING",
                summary="Fleet readiness is moderate: one open AOG recovery, two high-priority compliance items, and an emerging HUMS-flagged component risk on the drone fleet.",
                finding_count=3,
                critical_finding_count=1,
            )
            db.add(snapshot)
            db.flush()
            bump("assessment_snapshots")

            af1 = AssessmentFinding(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                category="AOG_RECOVERY",
                severity="CRITICAL",
                title="VT-APZ grounded pending engine erosion disposition",
                description="Aircraft is in an active AOG recovery with an unresolved evidence blocker.",
                entity_type="AogEvent",
                entity_id=str(aog.id),
                materiality_score=92.0,
                complexity_band="HIGH",
                dependency_count=2,
                impact_dimensions=["SAFETY", "OPERATIONAL", "FINANCIAL"],
                priority_rank=1,
                source=f"AogEvent {aog.id} - VT-APZ engine erosion recovery",
                resolved=False,
            )
            db.add(af1)
            db.flush()
            bump("assessment_findings")

            db.add(AssessmentRisk(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                finding_id=af1.id,
                risk_level="HIGH",
                likelihood="UNKNOWN",
                reason="Overdue AD 2025-11-07 obligation on VT-APY compounds fleet-wide compliance exposure while VT-APZ is grounded.",
                entity_type="ComplianceObligation",
                entity_id=str(req_ad.id),
                mitigation="Expedite fuel pump housing NDT inspection under WO-2026-0004.",
                owner_role="CAMO_MANAGER",
            ))
            db.add(AssessmentGap(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                finding_id=af1.id,
                category="EVIDENCE",
                severity="MAJOR",
                entity_type="AogEvent",
                entity_id=str(aog.id),
                expected_condition="Engineering disposition report accepted as evidence prior to return-to-service.",
                current_condition="Disposition report not yet submitted; AOG blocker remains open.",
                recommended_action="Escalate engineering disposition to close the AOG evidence blocker.",
            ))
            db.add(AssessmentRecommendation(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                finding_id=af1.id,
                recommendation="Prioritize compressor blade replacement parts and expedite engineering disposition for VT-APZ.",
                why="This is the longest-pole blocker to returning VT-APZ to service and unblocking fleet capacity.",
                priority="HIGH",
                responsible_role="CAMO_MANAGER",
                entity_type="AogEvent",
                entity_id=str(aog.id),
                status="OPEN",
            ))
            db.add(AssessmentRoadmapItem(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                finding_id=af1.id,
                sequence=1,
                title="Close VT-APZ AOG evidence blocker",
                description="Obtain and submit engineering disposition report for compressor blade erosion findings.",
                category="AOG_RECOVERY",
                priority="HIGH",
                status="PLANNED",
                entity_type="AogEvent",
                entity_id=str(aog.id),
                prerequisite_sequence_numbers=[],
                owner_role="CAMO_MANAGER",
                estimated_effort_band="LOW",
                effort_confidence="MEDIUM",
                expected_impact="Unblocks VT-APZ return-to-service, restoring fleet capacity.",
                risk_if_delayed="Continued AOG holds VT-APZ out of service and delays downstream compliance work.",
            ))
            db.add(AssessmentMetric(
                organization_id=org.id,
                snapshot_id=snapshot.id,
                metric_key="open_aog_events",
                state="VALUE",
                value=1.0,
                unit="count",
                explanation="One open AOG event (VT-APZ) at time of assessment.",
            ))
            db.flush()
            bump("assessment_children", 5)

        db.commit()

        # ------------------------------------------------------------------
        # Verification: row counts for this org
        # ------------------------------------------------------------------
        print("\n=== Master Demo Environment Ready ===")
        print(f"Organization: {DEMO_ORG_NAME}  (informal slug: {DEMO_ORG_CODE})")
        print(f"Admin Login:  {DEMO_ADMIN_EMAIL} / {DEMO_PASSWORD}")
        print(f"Technician:   {tech_user.email} / {DEMO_PASSWORD}")
        print(f"Inspector:    {inspector_user.email} / {DEMO_PASSWORD}")
        print("\nRows created/verified this run (idempotent — 0 means already present):")
        for k in sorted(counts):
            print(f"  {k}: {counts[k]}")

        print("\nLive row counts for this org:")
        def count_for(model, col="organization_id"):
            return db.execute(select(func.count()).select_from(model).where(getattr(model, col) == org.id)).scalar_one()

        print(f"  users: {count_for(User)}")
        print(f"  assets (aircraft+drones): {count_for(Asset)}")
        print(f"  aircraft: {count_for(Aircraft)}")
        print(f"  components: {count_for(Component)}")
        print(f"  hums_sensors: {count_for(HUMSSensor)}")
        print(f"  hums_readings: {count_for(HUMSSensorReading)}")
        print(f"  hums_features: {count_for(HUMSFeature)}")
        print(f"  hums_baselines: {count_for(HUMSBaseline)}")
        print(f"  hums_exceedances: {count_for(HUMSExceedance)}")
        print(f"  hums_diagnostic_candidates: {count_for(HUMSDiagnosticCandidate)}")
        print(f"  hums_degradation_models: {count_for(HUMSDegradationModel)}")
        print(f"  hums_prognostic_records: {count_for(HUMSPrognosticRecord)}")
        print(f"  evidence: {count_for(Evidence)}")
        print(f"  findings: {count_for(Finding)}")
        print(f"  proactive_signal_records: {count_for(ProactiveSignalRecord)}")
        print(f"  mro_intelligence_candidates: {count_for(MaintenanceIntelligenceCandidate)}")
        print(f"  compliance_obligations: {count_for(ComplianceObligation)}")
        print(f"  work_orders: {count_for(WorkOrder)}")
        print(f"  tasks: {count_for(Task)}")
        print(f"  parts: {count_for(Part)}")
        print(f"  vendors: {count_for(Vendor)}")
        print(f"  purchase_orders: {count_for(PurchaseOrder)}")
        print(f"  inventory_transactions: {count_for(InventoryTransaction)}")
        print(f"  aog_events: {count_for(AogEvent)}")
        print(f"  deferred_items: {count_for(DeferredItem)}")
        print(f"  technician_qualifications: {count_for(TechnicianQualification)}")
        print(f"  telemetry_event_logs: {count_for(TelemetryEventLog)}")
        print(f"  sso_configurations: {count_for(SSOConfiguration)}")
        print(f"  subscriptions: {count_for(Subscription)}")
        print(f"  edge_devices: {count_for(EdgeDevice)}")
        print(f"  operational_incidents: {count_for(OperationalIncident)}")
        print(f"  missions: {count_for(Mission)}")
        print(f"  import_jobs: {count_for(ImportJob)}")
        print(f"  part_requirements: {count_for(PartRequirement)}")
        print(f"  vendor_part_availabilities: {count_for(VendorPartAvailability)}")
        print(f"  lisa_conversation_contexts: {count_for(LisaConversationContext)}")
        print(f"  applicability_rules: {count_for(ApplicabilityRule)}")
        print(f"  applicability_evaluations: {count_for(ApplicabilityEvaluation)}")
        print(f"  assessments: {count_for(Assessment)}")
        print(f"  assessment_snapshots: {count_for(AssessmentSnapshot)}")

        verify_admin = db.execute(select(User).where(User.email == DEMO_ADMIN_EMAIL)).scalar_one_or_none()
        print(f"\nAdmin user lookup check: {'OK' if verify_admin else 'FAILED'} (id={verify_admin.id if verify_admin else None})")

        print("\nReady for end-to-end client walkthrough.")

    except Exception as exc:
        db.rollback()
        print(f"Error seeding demo environment: {exc}", file=sys.stderr)
        raise
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    seed_demo_environment()
